from utils.db import get_db

conn = get_db()
cur = conn.cursor()

cur.execute("DELETE FROM users")
cur.execute("DELETE FROM sqlite_sequence WHERE name='users'")

conn.commit()
conn.close()

print("All users deleted successfully.")
