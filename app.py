from flask import Flask, render_template, request, redirect, session
from utils.db import get_db
from utils.auth import hash_password, verify_password, login_user, logout_user

import os
from datetime import datetime
from utils.hash_utils import generate_file_hash, generate_log_hash

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from flask import send_file

app = Flask(__name__)
app.secret_key = "super_secret_key"

UPLOAD_FOLDER = "uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

@app.route("/")
def home():
    if "user_id" in session:
        return redirect("/dashboard")
    return redirect("/login")


# ---------------- REGISTER ----------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = hash_password(request.form["password"])
        role = request.form["role"]

        conn = get_db()
        cur = conn.cursor()

        try:
            cur.execute(
                "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                (username, password, role),
            )
            conn.commit()
            return redirect("/login")
        except:
            return "Username already exists"
        finally:
            conn.close()

    return render_template("register.html")


# ---------------- LOGIN ----------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = cur.fetchone()
        conn.close()

        if user and verify_password(user["password"], password):
            login_user(user)
            return redirect("/dashboard")

        return "Invalid credentials"

    return render_template("login.html")


# ---------------- DASHBOARD ----------------
@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect("/login")

    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT * FROM evidence")
    evidences = cur.fetchall()

    conn.close()

    return render_template(
        "dashboard.html",
        role=session["role"],
        evidences=evidences
    )

# ---------------- UPLOAD ----------------
@app.route("/upload", methods=["GET", "POST"])
def upload():
    if "user_id" not in session or session["role"] != "investigator":
        return "Unauthorized", 403

    if request.method == "POST":
        file = request.files["file"]

        if file:
            filename = file.filename
            filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)

            file.save(filepath)

            # Generate hash
            file_hash = generate_file_hash(filepath)

            conn = get_db()
            cur = conn.cursor()

            # Insert into evidence table
            cur.execute("""
                INSERT INTO evidence 
                (filename, file_hash, uploaded_by, upload_time, current_custodian, status)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                filename,
                file_hash,
                session["user_id"],
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                session["user_id"],
                "active"
            ))

            evidence_id = cur.lastrowid

            # Create first custody log
            cur.execute("""
                INSERT INTO custody_log
                (evidence_id, action, from_user, to_user, timestamp, previous_hash, log_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                evidence_id,
                "uploaded",
                session["user_id"],
                session["user_id"],
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "GENESIS",
                file_hash
            ))

            conn.commit()
            conn.close()

            return "Evidence uploaded successfully"

    return render_template("upload.html")

# ---------------- TRANSFER----------------
@app.route("/transfer/<int:evidence_id>", methods=["GET", "POST"])
def transfer(evidence_id):
    if "user_id" not in session or session["role"] != "investigator":
        return "Unauthorized", 403

    conn = get_db()
    cur = conn.cursor()

    # Get evidence
    cur.execute("SELECT * FROM evidence WHERE id = ?", (evidence_id,))
    evidence = cur.fetchone()

    if not evidence:
        conn.close()
        return "Evidence not found"

    if request.method == "POST":
        new_custodian = request.form["new_custodian"]
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Get last log hash
        cur.execute("""
            SELECT log_hash FROM custody_log
            WHERE evidence_id = ?
            ORDER BY id DESC LIMIT 1
        """, (evidence_id,))
        last_log = cur.fetchone()
        previous_hash = last_log["log_hash"]

        # Create new log hash
        data_string = f"{evidence_id}{session['user_id']}{new_custodian}{timestamp}{previous_hash}"
        new_log_hash = generate_log_hash(data_string)

        # Insert new custody log
        cur.execute("""
            INSERT INTO custody_log
            (evidence_id, action, from_user, to_user, timestamp, previous_hash, log_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            evidence_id,
            "transferred",
            session["user_id"],
            new_custodian,
            timestamp,
            previous_hash,
            new_log_hash
        ))

        # Update current custodian
        cur.execute("""
            UPDATE evidence SET current_custodian = ?
            WHERE id = ?
        """, (new_custodian, evidence_id))

        conn.commit()
        conn.close()

        return "Evidence transferred successfully"

    # Get list of users for dropdown
    cur.execute("SELECT id, username FROM users")
    users = cur.fetchall()
    conn.close()

    return render_template("transfer.html", evidence=evidence, users=users)

# ---------------- VERIFY ----------------
@app.route("/verify/<int:evidence_id>")
def verify(evidence_id):
    if "user_id" not in session:
        return redirect("/login")

    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT * FROM evidence WHERE id = ?", (evidence_id,))
    evidence = cur.fetchone()

    conn.close()

    if not evidence:
        return render_template(
            "verify.html",
            evidence_id=evidence_id,
            status="not_found"
        )

    file_path = os.path.join(app.config["UPLOAD_FOLDER"], evidence["filename"])

    if not os.path.exists(file_path):
        return render_template(
            "verify.html",
            evidence_id=evidence_id,
            status="missing"
        )

    # Recalculate hash
    current_hash = generate_file_hash(file_path)

    if current_hash == evidence["file_hash"]:
        status = "verified"
    else:
        status = "tampered"

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO verification_log (evidence_id, verified_by, result)
    VALUES (?, ?, ?)
    """, (evidence_id, session["user_id"], status))

    conn.commit()
    conn.close()

    return render_template(
        "verify.html",
        evidence_id=evidence_id,
        status=status
    )

# ---------------- VERIFICATION LOGS ----------------
@app.route("/verification_logs")
def verification_logs():
    if "user_id" not in session:
        return redirect("/login")

    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute("""
        SELECT v.id, v.evidence_id, v.result, v.timestamp, u.username
        FROM verification_log v
        JOIN users u ON v.verified_by = u.id
        ORDER BY v.timestamp DESC
        """)

        logs = cur.fetchall()

    except Exception as e:
        return f"Database Error: {e}"

    conn.close()

    return render_template("verification_logs.html", logs=logs)

# ---------------- COC ----------------
@app.route("/custody/<int:evidence_id>")
def custody(evidence_id):
    if "user_id" not in session:
        return redirect("/login")

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
    SELECT c.action, u1.username AS from_user, u2.username AS to_user, c.timestamp
    FROM custody_log c
    LEFT JOIN users u1 ON c.from_user = u1.id
    LEFT JOIN users u2 ON c.to_user = u2.id
    WHERE c.evidence_id = ?
    ORDER BY c.timestamp ASC
    """, (evidence_id,))

    logs = cur.fetchall()

    conn.close()

    return render_template("custody.html", logs=logs, evidence_id=evidence_id)

# ----------------PDF REPORT----------------
@app.route("/generate_report/<int:evidence_id>")
def generate_report(evidence_id):
    if "user_id" not in session:
        return redirect("/login")

    conn = get_db()
    cur = conn.cursor()

    # Evidence
    cur.execute("SELECT * FROM evidence WHERE id=?", (evidence_id,))
    evidence = cur.fetchone()

    # Verification logs
    cur.execute("""
    SELECT result, timestamp FROM verification_log
    WHERE evidence_id=?
    """, (evidence_id,))
    ver_logs = cur.fetchall()

    # Custody logs
    cur.execute("""
    SELECT action, timestamp FROM custody_log
    WHERE evidence_id=?
    """, (evidence_id,))
    custody_logs = cur.fetchall()

    conn.close()

    # Create PDF
    filename = f"reports/report_EV_{evidence_id}.pdf"
    doc = SimpleDocTemplate(filename)
    styles = getSampleStyleSheet()

    content = []

    content.append(Paragraph(f"Evidence Report - EV-{evidence_id}", styles["Title"]))
    content.append(Spacer(1, 10))

    content.append(Paragraph(f"Filename: {evidence['filename']}", styles["Normal"]))
    content.append(Paragraph(f"Hash: {evidence['file_hash']}", styles["Normal"]))
    content.append(Spacer(1, 10))

    content.append(Paragraph("Verification Logs:", styles["Heading2"]))
    for log in ver_logs:
        content.append(Paragraph(f"{log['timestamp']} - {log['result']}", styles["Normal"]))

    content.append(Spacer(1, 10))

    content.append(Paragraph("Custody Logs:", styles["Heading2"]))
    for log in custody_logs:
        content.append(Paragraph(f"{log['timestamp']} - {log['action']}", styles["Normal"]))

    doc.build(content)

    return send_file(filename, as_attachment=True)

# ---------------- LOGOUT ----------------
@app.route("/logout")
def logout():
    logout_user()
    return redirect("/login")



if __name__ == "__main__":
    app.run(debug=True)
