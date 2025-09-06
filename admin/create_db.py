import sqlite3

DB_NAME = 'cronjobs.db'

conn = sqlite3.connect(DB_NAME)
cur = conn.cursor()

# Create cron_jobs table
cur.execute("""
CREATE TABLE IF NOT EXISTS cron_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain TEXT NOT NULL,
    url TEXT NOT NULL,
    interval_seconds INTEGER,
    interval_minutes INTEGER,
    interval_hours INTEGER
)
""")

# Create cron_history table
cur.execute("""
CREATE TABLE IF NOT EXISTS cron_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER,
    timestamp TEXT,
    result TEXT,
    FOREIGN KEY(job_id) REFERENCES cron_jobs(id)
)
""")

conn.commit()
conn.close()

print(f"Database '{DB_NAME}' initialized with required tables.")