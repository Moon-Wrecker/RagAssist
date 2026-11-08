import sqlite3
import os

db_path = r'C:\Users\ASUS\.gemini\antigravity\conversation_summaries.db'
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cur.fetchall()
    print("Tables:", tables)
    for table_name, in tables:
        cur.execute(f"PRAGMA table_info({table_name});")
        print(f"Schema for {table_name}:", cur.fetchall())
        cur.execute(f"SELECT COUNT(*) FROM {table_name};")
        print(f"Row count for {table_name}:", cur.fetchone())
else:
    print("DB not found")
