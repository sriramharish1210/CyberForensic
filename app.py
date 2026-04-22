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
app.config["UPLOAD_FOLDER"] = os.path.join(os.getcwd(), "uploads")
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

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
        username=session["username"],
        evidences=evidences
    )

# ---------------- UPLOAD ----------------
@app.route("/upload", methods=["GET", "POST"])
def upload():
    if "user_id" not in session or session["role"] != "investigator":
        return "Unauthorized", 403

    if request.method == "POST":
        file = request.files.get("file")

        if not file or file.filename == "":
            return "No file selected"

        try:
            filename = file.filename
            filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)

            print("UPLOAD PATH:", filepath)

            # SAVE FIRST
            file.save(filepath)

            print("FILE SAVED:", os.path.exists(filepath))

            # NOW get size
            file_size = os.path.getsize(filepath)

            # Generate hash
            file_hash = generate_file_hash(filepath)

        except Exception as e:
            print("UPLOAD ERROR:", str(e))
            return "Upload failed: " + str(e)

        conn = get_db()
        cur = conn.cursor()

        # FIXED SQL
        cur.execute("""
            INSERT INTO evidence 
            (filename, file_hash, file_size, uploaded_by, upload_time, current_custodian, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            filename,
            file_hash,
            file_size,
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

        return render_template("upload_success.html", evidence_id=evidence_id, filename=filename)

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
        from_user_id = session["user_id"]
        to_user_id = request.form.get("new_custodian")

        if not to_user_id:
            conn.close()
            return "No user selected"

        # CRITICAL FIX: validate role
        cur.execute("SELECT role FROM users WHERE id = ?", (to_user_id,))
        user_check = cur.fetchone()

        if not user_check or user_check["role"] != "investigator":
            conn.close()
            return "Unauthorized transfer", 403

        # Prevent self-transfer
        if int(to_user_id) == from_user_id:
            conn.close()
            return "Cannot transfer to yourself", 400

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Get last hash
        cur.execute("""
            SELECT log_hash FROM custody_log
            WHERE evidence_id = ?
            ORDER BY id DESC LIMIT 1
        """, (evidence_id,))
        last_log = cur.fetchone()
        previous_hash = last_log["log_hash"] if last_log else "GENESIS"

        # Generate new hash
        data_string = f"{evidence_id}{from_user_id}{to_user_id}{timestamp}{previous_hash}"
        new_log_hash = generate_log_hash(data_string)

        # Insert log
        cur.execute("""
            INSERT INTO custody_log
            (evidence_id, action, from_user, to_user, timestamp, previous_hash, log_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            evidence_id,
            "transferred",
            from_user_id,
            to_user_id,
            timestamp,
            previous_hash,
            new_log_hash
        ))

        # Update evidence
        cur.execute("""
            UPDATE evidence SET current_custodian = ?
            WHERE id = ?
        """, (to_user_id, evidence_id))

        conn.commit()

        # Get usernames
        cur.execute("SELECT username FROM users WHERE id=?", (from_user_id,))
        from_user = cur.fetchone()["username"]

        cur.execute("SELECT username FROM users WHERE id=?", (to_user_id,))
        to_user = cur.fetchone()["username"]

        conn.close()

        return render_template(
            "transfer_success.html",
            evidence_id=evidence_id,
            from_user=from_user,
            to_user=to_user
        )

    #FIXED GET: only investigators
    cur.execute("""
        SELECT id, username FROM users
        WHERE role = 'investigator'
        AND id != ?
    """, (session["user_id"],))
    investigators = cur.fetchall()

    conn.close()

    return render_template("transfer.html", evidence=evidence, investigators=investigators)

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
            status="not_found",
            reason="Evidence not found in database"
        )

    file_path = os.path.join(app.config["UPLOAD_FOLDER"], evidence["filename"])

    print("VERIFYING FILE:", file_path)

    # ---------------- NEW LOGIC ----------------
    status = "verified"
    reason = "Integrity intact"

    if not os.path.exists(file_path):
        print("FILE EXISTS:", False)

        files_in_folder = os.listdir(app.config["UPLOAD_FOLDER"])

        status = "tampered"

        if len(files_in_folder) == 0:
            reason = "Evidence file deleted"
        else:
            reason = "Original file missing (possible rename or replacement)"

    else:
        print("FILE EXISTS:", True)
        print("FILE SIZE:", os.path.getsize(file_path))

        current_hash = generate_file_hash(file_path)
        current_size = os.path.getsize(file_path)

        print("EXPECTED HASH:", evidence["file_hash"])
        print("CURRENT HASH:", current_hash)

        if current_hash != evidence["file_hash"]:
            status = "tampered"
            reason = "File content modified (hash mismatch)"

        elif evidence["file_size"] is not None and current_size != evidence["file_size"]:
            status = "tampered"
            reason = "File size changed (possible replacement)"

        else:
            status = "verified"
            reason = "Integrity intact"

    # ---------------- LOG ----------------
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO verification_log (evidence_id, verified_by, result)
    VALUES (?, ?, ?)
    """, (evidence_id, session["user_id"], status))

    conn.commit()
    conn.close()

    # ---------------- RETURN ----------------
    return render_template(
        "verify.html",
        evidence_id=evidence_id,
        status=status,
        reason=reason
    )

# ---------------- VERIFICATION LOGS ----------------
@app.route("/verification_logs/<int:evidence_id>")
def verification_logs(evidence_id):
    if "user_id" not in session:
        return redirect("/login")

    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute("""
        SELECT v.id, v.evidence_id, v.result, v.timestamp, u.username
        FROM verification_log v
        JOIN users u ON v.verified_by = u.id
        WHERE v.evidence_id = ?
        ORDER BY v.timestamp DESC
        """, (evidence_id,))

        logs = cur.fetchall()

    except Exception as e:
        return f"Database Error: {e}"

    conn.close()

    return render_template(
        "verification_logs.html",
        logs=logs,
        evidence_id=evidence_id
    )

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

#ADMIN PANEL
# ----------------MANAGE USERS ----------------
@app.route("/manage_users")
def manage_users():
    if "user_id" not in session or session.get("role") != "admin":
        return "Access Denied"

    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT id, username, role FROM users")
    users = cur.fetchall()

    conn.close()

    return render_template("manage_users.html", users=users)

# ---------------- EVIDENCE CONTROL ----------------
@app.route("/evidence_control")
def evidence_control():
    if "user_id" not in session or session.get("role") != "admin":
        return "Access Denied"

    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT * FROM evidence")
    evidences = cur.fetchall()

    conn.close()

    return render_template("evidence_control.html", evidences=evidences)

# ---------------- SYSTEM LOGS ----------------
@app.route("/system_logs")
def system_logs():
    if "user_id" not in session or session.get("role") != "admin":
        return "Access Denied"

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT * FROM verification_log
        ORDER BY timestamp DESC
    """)

    logs = cur.fetchall()
    conn.close()

    return render_template("system_logs.html", logs=logs)

# ---------------- CREATE POLICY ----------------
@app.route('/admin/create_policy', methods=['POST'])
def create_policy():
    name = request.form['name']
    days = int(request.form['days'])
    auto_delete = request.form.get('auto_delete') == 'on'

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO retention_policies (name, days, auto_delete)
        VALUES (?, ?, ?)
    """, (name, days, auto_delete))

    conn.commit()
    conn.close()

    return redirect('/admin/dashboard')

# ---------------- APLLY POLICY ----------------
from datetime import datetime, timedelta
import os

@app.route('/admin/apply_policy')
def apply_policy():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT days, auto_delete FROM retention_policies ORDER BY id DESC LIMIT 1")
    policy = cur.fetchone()

    if not policy:
        return "No policy set"

    days, auto_delete = policy
    cutoff = datetime.now() - timedelta(days=days)

    cur.execute("SELECT id, file_path, created_at FROM evidence")
    evidences = cur.fetchall()

    for ev in evidences:
        ev_id, file_path, created_at = ev

        created_at = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S")

        if created_at < cutoff:
            if auto_delete:
                try:
                    os.remove(file_path)
                except:
                    pass

                cur.execute("DELETE FROM evidence WHERE id=?", (ev_id,))

    conn.commit()
    conn.close()

    return "Policy Applied Successfully"

# ---------------- POLICY----------------
@app.route('/policy')
def policy_page():
    return render_template('policy.html')

#AUDT PANEL
# ---------------- VERIFICATION LOGS ----------------
@app.route("/all_verification_logs")
def all_verification_logs():
    if "user_id" not in session or session.get("role") != "auditor":
        return "Access Denied"

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT v.id, v.evidence_id, v.result, v.timestamp, u.username
        FROM verification_log v
        JOIN users u ON v.verified_by = u.id
        ORDER BY v.timestamp DESC
    """)

    logs = cur.fetchall()
    conn.close()

    return render_template("verification_logs.html", logs=logs)

# ---------------- INTEGRITY CHECKS ----------------
@app.route("/integrity_checks")
def integrity_checks():
    if session.get("role") != "auditor":
        return "Access Denied"

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT evidence_id, result, timestamp
        FROM verification_log
        ORDER BY timestamp DESC
    """)

    logs = cur.fetchall()
    conn.close()

    return render_template("integrity_checks.html", logs=logs)

# ---------------- TIMELINE VIEW ----------------
@app.route("/timeline_view")
def timeline_view():
    if session.get("role") != "auditor":
        return "Access Denied"

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT * FROM custody_log
        ORDER BY timestamp DESC
    """)

    logs = cur.fetchall()
    conn.close()

    return render_template("timeline.html", logs=logs)

# ---------------- AUDIT DASHBOARD ----------------
@app.route("/auditor/dashboard")
def auditor_dashboard():
    if "user_id" not in session or session.get("role") != "auditor":
        return "Access Denied"

    conn = get_db()
    cur = conn.cursor()

    # Total evidence
    cur.execute("SELECT COUNT(*) as total FROM evidence")
    total = cur.fetchone()["total"]

    # Latest verification per evidence
    cur.execute("""
        SELECT e.id, e.filename, u.username AS custodian,
               v.result, v.timestamp
        FROM evidence e
        LEFT JOIN users u ON e.current_custodian = u.id
        LEFT JOIN verification_log v ON v.evidence_id = e.id
        WHERE v.id IN (
            SELECT MAX(id) FROM verification_log GROUP BY evidence_id
        )
        ORDER BY v.timestamp DESC
    """)

    records = cur.fetchall()

    # Count stats
    verified = sum(1 for r in records if r["result"] == "verified")
    tampered = sum(1 for r in records if r["result"] == "tampered")

    conn.close()

    return render_template(
        "auditor_dashboard.html",
        total=total,
        verified=verified,
        tampered=tampered,
        records=records
    )

# ---------------- LOGOUT ----------------
@app.route("/logout")
def logout():
    logout_user()
    return redirect("/login")



if __name__ == "__main__":
    app.run(debug=True)
