from utils.db import get_db

conn = get_db()
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    password TEXT,
    role TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT,
    file_hash TEXT,
    uploaded_by INTEGER,
    upload_time TEXT,
    current_custodian INTEGER,
    status TEXT
)
""")

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

cur.execute("""
CREATE TABLE IF NOT EXISTS verification_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    evidence_id INTEGER,
    verified_by INTEGER,
    result TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
)
""")

conn.commit()
conn.close()

print("Database initialized successfully")
