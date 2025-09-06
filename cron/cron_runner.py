import sqlite3
import time
import requests
from datetime import datetime, timedelta
import pytz

# DB File Path
DB = '../cronjobs.db'
# Timezone
BD_TZ = pytz.timezone("Asia/Dhaka")

# --- Helper Functions ---

def get_active_users():
    with sqlite3.connect(DB, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        today = datetime.now(BD_TZ).date()
        users = conn.execute("""
            SELECT * FROM users
            WHERE status = 'Enable'
            AND active_package IS NOT NULL
            AND expair_date IS NOT NULL
        """).fetchall()
        valid_users = [u for u in users if datetime.strptime(u['expair_date'], "%Y-%m-%d").date() >= today]
        return valid_users

def get_package_interval(package_name):
    with sqlite3.connect(DB, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        result = conn.execute("SELECT interval FROM packages WHERE name = ?", (package_name,)).fetchone()
        return int(result['interval']) if result else 5  # default 5 seconds if not found

def log_history(domain, email, method, result):
    try:
        with sqlite3.connect(DB, timeout=10) as conn:
            timestamp = datetime.now(BD_TZ).strftime("%Y-%m-%d %H:%M:%S")
            conn.execute(
                "INSERT INTO cron_history (job_id, email, result, timestamp) VALUES (?, ?, ?, ?)",
                (domain, email, f"{method}: {result}", timestamp)
            )
            conn.commit()
    except Exception as e:
        print(f"Error logging history: {e}")

# --- Main Runner ---

def run_jobs():
    print("Cron Runner Started...")

    # Per-user last run trackers
    last_run_order = {}
    last_run_file = {}
    last_run_price = datetime.now(BD_TZ) - timedelta(minutes=30)
    last_clear_history = datetime.now(BD_TZ)
    last_users_refresh = datetime.now(BD_TZ) - timedelta(minutes=1)

    method_toggle = True
    active_users = get_active_users()

    while True:
        now = datetime.now(BD_TZ)

        # Refresh active users every 1 minute
        if (now - last_users_refresh).total_seconds() >= 60:
            active_users = get_active_users()
            print(f"{now.strftime('%Y-%m-%d %H:%M:%S')} - Refreshed active users: {len(active_users)} users")
            last_users_refresh = now

        # Clear cron_history every 10 minutes
        if (now - last_clear_history).total_seconds() >= 600:
            try:
                with sqlite3.connect(DB, timeout=10) as conn:
                    conn.execute("DELETE FROM cron_history")
                    conn.commit()
                print(f"{now.strftime('%Y-%m-%d %H:%M:%S')} - cron_history table cleared.")
            except Exception as e:
                print(f"Error clearing cron_history: {e}")
            last_clear_history = now

        # Price update every 30 minutes
        if (now - last_run_price).total_seconds() >= 1800:
            for user in active_users:
                url = user['price_update_url']
                if url:
                    try:
                        response = requests.get(url, timeout=10)
                        log_history(user['domain'], user['email'], "GET", f"Price update: {response.status_code}")
                        print(f"[{user['domain']}] Price update done: {response.status_code}")
                    except Exception as e:
                        log_history(user['domain'], user['email'], "GET", f"Price update error: {str(e)}")
                        print(f"[{user['domain']}] Price update error: {str(e)}")
            last_run_price = now

        # Per-user job handling
        for user in active_users:
            interval = get_package_interval(user['active_package'])

            # Order update
            if user['order_update_url']:
                last_time_order = last_run_order.get(user['id'], now - timedelta(seconds=interval + 1))
                if (now - last_time_order).total_seconds() >= interval:
                    try:
                        method = "GET" if method_toggle else "POST"
                        response = requests.get(user['order_update_url'], timeout=10) if method == "GET" else requests.post(user['order_update_url'], timeout=10)
                        log_history(user['domain'], user['email'], method, f"Order update: {response.status_code}")
                        print(f"[{user['domain']}] Order update done: {response.status_code}")
                    except Exception as e:
                        log_history(user['domain'], user['email'], method, f"Order update error: {str(e)}")
                        print(f"[{user['domain']}] Order update error: {str(e)}")
                    last_run_order[user['id']] = now

            # File update
            if user['file_update_url']:
                last_time_file = last_run_file.get(user['id'], now - timedelta(seconds=interval + 1))
                if (now - last_time_file).total_seconds() >= interval:
                    try:
                        method = "POST" if method_toggle else "GET"
                        response = requests.post(user['file_update_url'], timeout=10) if method == "POST" else requests.get(user['file_update_url'], timeout=10)
                        log_history(user['domain'], user['email'], method, f"File update: {response.status_code}")
                        print(f"[{user['domain']}] File update done: {response.status_code}")
                    except Exception as e:
                        log_history(user['domain'], user['email'], method, f"File update error: {str(e)}")
                        print(f"[{user['domain']}] File update error: {str(e)}")
                    last_run_file[user['id']] = now

        # Toggle GET/POST
        method_toggle = not method_toggle

        # Sleep to avoid high CPU usage
        time.sleep(1)

# --- Main Entry ---
if __name__ == '__main__':
    run_jobs()
