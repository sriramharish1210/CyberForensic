from utils.db import get_db

conn = get_db()
cur = conn.cursor()

# Delete all records
cur.execute("DELETE FROM custody_log")
cur.execute("DELETE FROM evidence")

# Reset auto-increment IDs (important for demo starting from ID 1)
cur.execute("DELETE FROM sqlite_sequence WHERE name='evidence'")
cur.execute("DELETE FROM sqlite_sequence WHERE name='custody_log'")

conn.commit()
conn.close()

print("Database reset successful.")
