from utils.db import get_db
import sqlite3

conn = get_db()
cur = conn.cursor()

# ---------------- USERS ----------------
cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    password TEXT,
    role TEXT
)
""")

# ---------------- EVIDENCE ----------------
cur.execute("""
CREATE TABLE IF NOT EXISTS evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT,
    file_hash TEXT,
    uploaded_by INTEGER,
    upload_time TEXT,
    current_custodian INTEGER,
    status TEXT,
    file_size INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
)
""")

# ---------------- CUSTODY LOG ----------------
cur.execute("""
CREATE TABLE IF NOT EXISTS custody_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    evidence_id INTEGER,
    action TEXT,
    from_user INTEGER,
    to_user INTEGER,
    timestamp TEXT,
    previous_hash TEXT,
    log_hash TEXT
)
""")

# ---------------- VERIFICATION LOG ----------------
cur.execute("""
CREATE TABLE IF NOT EXISTS verification_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    evidence_id INTEGER,
    verified_by INTEGER,
    result TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
)
""")

# ---------------- RETENTION POLICIES (NEW) ----------------
cur.execute("""
CREATE TABLE IF NOT EXISTS retention_policies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    days INTEGER,
    auto_delete BOOLEAN,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

conn.commit()
conn.close()

print("Database initialized successfully")


# ---------------- SAFE COLUMN MIGRATION ----------------
conn = sqlite3.connect("database.db")
cur = conn.cursor()

# Add file_size if missing
try:
    cur.execute("ALTER TABLE evidence ADD COLUMN file_size INTEGER")
    print("file_size column added")
except Exception as e:
    print("file_size may already exist:", e)

# Add created_at if missing
try:
    cur.execute("ALTER TABLE evidence ADD COLUMN created_at TEXT DEFAULT CURRENT_TIMESTAMP")
    print("created_at column added")
except Exception as e:
    print("created_at may already exist:", e)

conn.commit()
conn.close()