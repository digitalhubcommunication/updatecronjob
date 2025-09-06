import time
import requests
import sqlite3
import datetime
import os
import traceback
import threading

DB_PATH = os.path.abspath("../cronjobs.db")  # Adjust path if needed

def get_db_connection():
    conn = sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def execute_with_retry(sql, params=(), retries=5, delay=0.3):
    for attempt in range(retries):
        try:
            conn = get_db_connection()
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(sql, params)
            conn.commit()
            conn.close()
            return
        except sqlite3.OperationalError as e:
            if 'locked' in str(e).lower():
                print(f"🔄 DB locked (write), retrying {attempt+1}/{retries}...")
                time.sleep(delay)
            else:
                raise
    raise sqlite3.OperationalError("Max retries exceeded (write lock).")

def execute_query_with_retry(sql, params=(), retries=5, delay=0.3):
    for attempt in range(retries):
        try:
            conn = get_db_connection()
            cursor = conn.execute(sql, params)
            result = cursor.fetchall()
            conn.close()
            return result
        except sqlite3.OperationalError as e:
            if 'locked' in str(e).lower():
                print(f"🔄 DB locked (read), retrying {attempt+1}/{retries}...")
                time.sleep(delay)
            else:
                raise
    raise sqlite3.OperationalError("Max retries exceeded (read lock).")

def ensure_last_run_column():
    try:
        cols = execute_query_with_retry("PRAGMA table_info(cron_jobs)")
        if "last_run" not in [col["name"] for col in cols]:
            print("➕ Adding 'last_run' column...")
            execute_with_retry("ALTER TABLE cron_jobs ADD COLUMN last_run INTEGER DEFAULT 0")
    except Exception as e:
        print(f"⚠️ Ensure column error: {e}")
        traceback.print_exc()

def log_history(job_id, url, status_code, duration, result):
    try:
        execute_with_retry("""
            INSERT INTO updateprice_logs 
            (cron_job_id, url, status_code, response_time, result) 
            VALUES (?, ?, ?, ?, ?)
        """, (job_id, url, status_code, duration, result[:500]))
    except Exception as e:
        print(f"⚠️ Log insert failed for Job {job_id}: {e}")

def update_status(job_id, new_status):
    try:
        execute_with_retry("UPDATE cron_jobs SET status = ? WHERE id = ?", (new_status, job_id))
    except Exception as e:
        print(f"⚠️ Status update failed: {e}")

def update_last_run(job_id, timestamp):
    try:
        execute_with_retry("UPDATE cron_jobs SET last_run = ? WHERE id = ?", (timestamp, job_id))
    except Exception as e:
        print(f"⚠️ last_run update failed: {e}")

def run_single_job(job):
    job_id = job['id']
    url = job['url']
    interval = job['interval']
    last_run = job['last_run'] or 0
    now_ts = int(time.time())

    if now_ts - last_run < interval:
        print(f"⏳ Job {job_id} not due yet ({interval - (now_ts - last_run)}s)")
        return

    print(f"🚀 Running Job #{job_id}: {url}")
    start_time = time.time()
    timeout_flag = threading.Event()

    def timeout_handler():
        if not timeout_flag.is_set():
            print(f"⏰ Job {job_id} timed out after 30s — skipping offline marking")
            log_history(job_id, url, 0, 30, "Timeout: exceeded 30 seconds (handler)")
            update_last_run(job_id, int(time.time()))

    timer = threading.Timer(30.0, timeout_handler)
    timer.start()

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }

    for attempt in range(3):
        try:
            response = requests.get(url, headers=headers, timeout=30)
            timeout_flag.set()
            timer.cancel()

            duration = round(time.time() - start_time, 2)
            log_history(job_id, url, response.status_code, duration, response.text)

            if 200 <= response.status_code < 300:
                if job['status'] != 'offline':
                    update_status(job_id, 'online')
                print(f"✅ Job {job_id} success ({response.status_code}) in {duration}s")
            else:
                update_status(job_id, 'offline')
                print(f"⚠️ Job {job_id} returned {response.status_code}")
            break

        except Exception as e:
            timeout_flag.set()
            timer.cancel()
            duration = round(time.time() - start_time, 2)
            log_history(job_id, url, 0, duration, f"Error: {str(e)}")

            if "timed out" in str(e).lower():
                print(f"⚠️ Job {job_id} timed out — keeping status unchanged")
            else:
                update_status(job_id, 'offline')
                print(f"❌ Job {job_id} failed: {e}")

    update_last_run(job_id, int(time.time()))

def run_due_cron_jobs():
    ensure_last_run_column()
    jobs = execute_query_with_retry("SELECT * FROM cron_jobs WHERE status IN ('enable', 'online')")
    print(f"✅ Found {len(jobs)} jobs to check")

    threads = []
    for job in jobs:
        thread = threading.Thread(target=run_single_job, args=(job,))
        thread.start()
        threads.append(thread)

    for thread in threads:
        thread.join()

if __name__ == "__main__":
    print("📡 Cron Price Update Runner started.")
    while True:
        print(f"\n[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Checking due cron jobs...")
        try:
            run_due_cron_jobs()
        except Exception as err:
            print(f"🔥 Unhandled error: {err}")
            traceback.print_exc()
        time.sleep(30)
