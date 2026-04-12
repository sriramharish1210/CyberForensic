from utils.db import get_db

conn = get_db()
cur = conn.cursor()

print("---- EVIDENCE TABLE ----")
cur.execute("SELECT * FROM evidence")
for row in cur.fetchall():
    print(dict(row))

print("\n---- CUSTODY LOG TABLE ----")
cur.execute("SELECT * FROM custody_log")
for row in cur.fetchall():
    print(dict(row))

print("\n---- VERIFICATION LOG TABLE ----")
cur.execute("SELECT * FROM verification_log")
for row in cur.fetchall():
    print(dict(row))
    
conn.close()
