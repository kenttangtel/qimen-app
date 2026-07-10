from dotenv import load_dotenv
import os, psycopg2
load_dotenv()
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()
cur.execute("SELECT id FROM users LIMIT 1")
r = cur.fetchone()
print(r[0] if r else None)
cur.close()
conn.close()
