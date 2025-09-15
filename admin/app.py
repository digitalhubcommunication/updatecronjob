from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
import os
from datetime import datetime, timedelta
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
import hashlib

app = Flask(__name__)
app.secret_key = "supersecretkey"
DB_PATH = "/home/manage.expresscronjob.com/cronjobs.db"

def init_db():
    if not os.path.exists(DB_FILE):
        conn = sqlite3.connect(DB_FILE)
        conn.execute("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL,
                mobile TEXT,
                domain TEXT,
                active_package TEXT,
                expire_date TEXT,
                order_update_url TEXT,
                price_update_url TEXT,
                file_update_url TEXT
                status TEXT DEFAULT 'Enable'
            )
        """)
        conn.execute("""
            CREATE TABLE cron_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                domain TEXT NOT NULL,
                url TEXT NOT NULL,
                status TEXT NOT NULL,
                interval INTEGER NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE cron_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                result TEXT NOT NULL,
                FOREIGN KEY (job_id) REFERENCES cron_jobs (id)
            )
        """)
        conn.execute("""
            CREATE TABLE packages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                validity INTEGER NOT NULL,
                price REAL NOT NULL,
                interval TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'enabled'
            )
        """)
        conn.commit()
        conn.close()

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function



@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        email = request.form["email"]
        password = request.form["password"]

        conn = get_db_connection()
        user = conn.execute(
            "SELECT * FROM members WHERE username = ? AND email = ?", (username, email)
        ).fetchone()
        conn.close()

        if user:
            # Only allow login if role is 'admin'
            if user["role"] != "admin":
                return render_template("login.html", error="Access denied: admin only")

            stored_password = user["password"]
            if stored_password.startswith("pbkdf2:sha256:"):
                if check_password_hash(stored_password, password):
                    session["user_id"] = user["id"]
                    session["user_name"] = user["name"]
                    session["role"] = user["role"]
                    return redirect(url_for("dashboard"))
            else:
                if hashlib.md5(password.encode()).hexdigest() == stored_password:
                    session["user_id"] = user["id"]
                    session["user_name"] = user["name"]
                    session["role"] = user["role"]
                    return redirect(url_for("dashboard"))

        return render_template("login.html", error="Invalid credentials")

    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get('name')
        username = request.form.get('username')
        email = request.form.get('email')
        phone = request.form.get('phone')
        telegram_username = request.form.get('telegram_username')
        telegram_chat_id = request.form.get('telegram_chat_id')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if password != confirm_password:
            flash("Passwords do not match", "error")
            return render_template('register.html')

        conn = get_db_connection()
        cursor = conn.cursor()

        # Check for duplicates
        cursor.execute("SELECT * FROM members WHERE username = ? OR email = ? OR phone = ?", (username, email, phone))
        existing_user = cursor.fetchone()

        if existing_user:
            conn.close()
            flash("Username, email or phone already exists", "error")
            return render_template('register.html')

        # Hash password using pbkdf2:sha256
        hashed_password = generate_password_hash(password, method="pbkdf2:sha256")

        cursor.execute(
            """INSERT INTO members  
            (name, username, email, phone, telegram_username, telegram_chat_id, password, role)  
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (name, username, email, phone, telegram_username, telegram_chat_id, hashed_password, 'user')
        )

        conn.commit()
        conn.close()
        flash("You have registered successfully!", "success")
        return redirect(url_for('register'))

    return render_template('register.html')


@app.route("/") 
def home(): 

    return render_template("index.html")

@app.route("/dashboard")
@login_required
def dashboard():
    # Only allow admin
    if session.get("role") != "admin":
        return "Access Denied", 403

    conn = get_db_connection()

    # Total Domains (unique non-empty domains)
    total_domains = conn.execute("""
        SELECT COUNT(DISTINCT domain) 
        FROM users 
        WHERE domain IS NOT NULL AND TRIM(domain) != ''
    """).fetchone()[0]

    # Total Users
    total_users = conn.execute("SELECT COUNT(id) FROM users").fetchone()[0]

    # Online Domains → status = 'Disable'
    online_domains = conn.execute("""
        SELECT COUNT(DISTINCT domain) 
        FROM users
        WHERE status = 'Disable' AND domain IS NOT NULL AND TRIM(domain) != ''
    """).fetchone()[0]

    # Offline Domains → status = 'Enable'
    offline_domains = conn.execute("""
        SELECT COUNT(DISTINCT domain) 
        FROM users
        WHERE status = 'Enable' AND domain IS NOT NULL AND TRIM(domain) != ''
    """).fetchone()[0]

    # Total Cron URLs → cron_jobs table → count of all URLs
    total_urls = conn.execute("SELECT COUNT(id) FROM cron_jobs").fetchone()[0]

    # Active Users → status = 'Enable'
    active_users = conn.execute("SELECT COUNT(id) FROM users WHERE status = 'Enable'").fetchone()[0]

    # Inactive Users → status = 'Disable'
    inactive_users = conn.execute("SELECT COUNT(id) FROM users WHERE status = 'Disable'").fetchone()[0]

    # Expired Accounts → expire_date < today
    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")
    expired_accounts = conn.execute("""
        SELECT COUNT(id) FROM users 
        WHERE expair_date IS NOT NULL AND expair_date < ?
    """, (today,)).fetchone()[0]

    conn.close()

    # Now render dashboard.html
    return render_template("dashboard.html", 
                           total_domains=total_domains, 
                           total_users=total_users,
                           online_domains=online_domains,
                           offline_domains=offline_domains,
                           total_urls=total_urls,
                           active_users=active_users,
                           inactive_users=inactive_users,
                           expired_accounts=expired_accounts)


@app.route("/add", methods=["GET", "POST"])
@login_required
def add_cron():
    if request.method == "POST":
        domain = request.form["domain"]
        url = request.form["url"]
        interval_value = int(request.form["interval_value"])
        interval_unit = request.form["interval_unit"]

        # Convert to seconds
        if interval_unit == "minutes":
            interval = interval_value * 60
        elif interval_unit == "hours":
            interval = interval_value * 3600
        else:
            interval = interval_value  # default is seconds

        conn = get_db_connection()
        conn.execute(
            "INSERT INTO cron_jobs (domain, url, interval, status) VALUES (?, ?, ?, 'online')",
            (domain, url, interval)
        )
        conn.commit()
        conn.close()
        return redirect(url_for("cron_list"))
    return render_template("add_cron.html")


@app.route("/cron-list")
@login_required
def cron_list():
    conn = get_db_connection()
    jobs = conn.execute("SELECT * FROM cron_jobs").fetchall()
    conn.close()
    return render_template("job_list.html", jobs=jobs)

@app.route("/delete/<int:job_id>")
@login_required
def delete_cron(job_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM cron_jobs WHERE id = ?", (job_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("cron_list"))

@app.route("/edit/<int:job_id>", methods=["GET", "POST"])
@login_required
def edit_cron(job_id):
    conn = get_db_connection()
    job = conn.execute("SELECT * FROM cron_jobs WHERE id = ?", (job_id,)).fetchone()
    if request.method == "POST":
        domain = request.form["domain"]
        url = request.form["url"]
        interval = int(request.form["interval"])
        conn.execute(
            "UPDATE cron_jobs SET domain = ?, url = ?, interval = ? WHERE id = ?",
            (domain, url, interval, job_id)
        )
        conn.commit()
        conn.close()
        return redirect(url_for("cron_list"))
    conn.close()
    return render_template("edit_cron.html", job=job)

@app.route("/toggle/<int:job_id>")
@login_required
def toggle_status(job_id):
    conn = get_db_connection()
    job = conn.execute("SELECT status FROM cron_jobs WHERE id = ?", (job_id,)).fetchone()
    new_status = "offline" if job["status"] == "online" else "online"
    conn.execute("UPDATE cron_jobs SET status = ? WHERE id = ?", (new_status, job_id))
    conn.commit()
    conn.close()
    return redirect(url_for("cron_list"))

@app.route('/history')
@login_required
def history():
    page = request.args.get('page', default=1, type=int)
    query = request.args.get('q', default="", type=str).strip().lower()
    per_page = 10
    offset = (page - 1) * per_page

    conn = get_db_connection()

    # First, check if email field exists → If your cron_history table has 'email' column
    # You can verify: SELECT email FROM cron_history LIMIT 1;

    if query:
        like_query = f"%{query}%"
        results = conn.execute("""
            SELECT id, job_id, email, result, timestamp
            FROM cron_history
            WHERE CAST(job_id AS TEXT) LIKE ?
               OR LOWER(email) LIKE ?
               OR LOWER(result) LIKE ?
               OR LOWER(timestamp) LIKE ?
            ORDER BY timestamp DESC
            LIMIT ? OFFSET ?
        """, (like_query, like_query, like_query, like_query, per_page, offset)).fetchall()

        total = conn.execute("""
            SELECT COUNT(*)
            FROM cron_history
            WHERE CAST(job_id AS TEXT) LIKE ?
               OR LOWER(email) LIKE ?
               OR LOWER(result) LIKE ?
               OR LOWER(timestamp) LIKE ?
        """, (like_query, like_query, like_query, like_query)).fetchone()[0]
    else:
        results = conn.execute("""
            SELECT id, job_id, email, result, timestamp
            FROM cron_history
            ORDER BY timestamp DESC
            LIMIT ? OFFSET ?
        """, (per_page, offset)).fetchall()

        total = conn.execute("SELECT COUNT(*) FROM cron_history").fetchone()[0]

    conn.close()

    return render_template(
        'history.html',
        history=results,
        page=page,
        total=total,
        query=query,
        per_page=per_page
    )




@app.route("/settings")
@login_required
def settings():
    return render_template("settings.html")

@app.route("/manage-clients")
@login_required
def manage_clients():
    page = int(request.args.get("page", 1))
    per_page = 10
    offset = (page - 1) * per_page

    conn = get_db_connection()
    total = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    clients = conn.execute("""
        SELECT * FROM users
        ORDER BY id DESC
        LIMIT ? OFFSET ?
    """, (per_page, offset)).fetchall()
    conn.close()

    return render_template("manage_clients.html", clients=clients, page=page, per_page=per_page, total=total)


@app.route('/edit-client/<int:client_id>', methods=['GET', 'POST'])
@login_required
def edit_client(client_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        mobile = request.form.get('mobile')
        status = request.form.get('status')
        order_update_url = request.form.get('order_update_url')
        price_update_url = request.form.get('price_update_url')
        file_update_url = request.form.get('file_update_url')

        cursor.execute("""
            UPDATE users SET
                name = ?, email = ?, mobile = ?, status = ?,
                order_update_url = ?, price_update_url = ?, file_update_url = ?
            WHERE id = ?
        """, (name, email, mobile, status,
              order_update_url, price_update_url, file_update_url, client_id))
        
        conn.commit()
        conn.close()
        return redirect(url_for('manage_clients'))

    # GET request → show the form
    cursor.execute("SELECT * FROM users WHERE id = ?", (client_id,))
    client = cursor.fetchone()
    conn.close()

    if not client:
        return "Client not found", 404

    return render_template("edit_client.html", client=client)


@app.route("/delete-user/<int:user_id>")
@login_required
def delete_user(user_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("manage_clients"))


@app.route("/packages")
@login_required
def package():
    conn = get_db_connection()
    packages = conn.execute("SELECT * FROM packages").fetchall()
    conn.close()
    return render_template("package.html", packages=packages)

@app.route("/active-package", methods=["GET", "POST"])
@login_required
def active_package():
    conn = get_db_connection()
    users = conn.execute("SELECT id, name, email FROM users").fetchall()
    packages = conn.execute("SELECT * FROM packages WHERE status = 'enabled'").fetchall()
    message = ""
    selected_user_id = selected_package_id = None

    if request.method == "POST":
        user_id = int(request.form["user_id"])
        package_id = int(request.form["package_id"])
        selected_user_id = user_id
        selected_package_id = package_id

        # Get selected package validity
        pkg = conn.execute("SELECT validity FROM packages WHERE id = ?", (package_id,)).fetchone()
        if pkg:
            # Calculate expiry date
            expire_date = (datetime.now() + timedelta(days=pkg["validity"])).strftime("%Y-%m-%d")

            # Update user's package info
            conn.execute("""
                UPDATE users
                SET active_package = ?, expair_date = ?, status = 'Enable'
                WHERE id = ?
            """, (package_id, expire_date, user_id))
            conn.commit()
            message = "Package assigned successfully."

    conn.close()
    return render_template(
        "active_package.html",
        users=users,
        packages=packages,
        message=message,
        selected_user_id=selected_user_id,
        selected_package_id=selected_package_id
    )

@app.route("/upgrade-users-schema")
def upgrade_users_schema():
    conn = get_db_connection()
    try:
        conn.execute("ALTER TABLE users ADD COLUMN active_package TEXT")
    except:
        pass
    try:
        conn.execute("ALTER TABLE users ADD COLUMN expire_date TEXT")
    except:
        pass
    try:
        conn.execute("ALTER TABLE users ADD COLUMN status TEXT DEFAULT 'Enable'")
    except:
        pass
    conn.commit()
    conn.close()
    return "Users table upgraded!"


@app.route("/add-package", methods=["GET", "POST"])
@login_required
def add_package():
    if request.method == "POST":
        name = request.form["name"]
        validity = int(request.form["validity"])
        price = float(request.form["price"])
        interval_value = request.form["interval_value"]
        interval_unit = request.form["interval_unit"]
        interval = f"{interval_value} {interval_unit}"
        conn = get_db_connection()
        conn.execute(
            "INSERT INTO packages (name, validity, price, interval, status) VALUES (?, ?, ?, ?, 'enabled')",
            (name, validity, price, interval)
        )
        conn.commit()
        conn.close()
        return redirect(url_for("package"))
    return render_template("add_package.html")

@app.route("/edit-package/<int:package_id>", methods=["GET", "POST"])
@login_required
def edit_package(package_id):
    conn = get_db_connection()
    pkg = conn.execute("SELECT * FROM packages WHERE id = ?", (package_id,)).fetchone()

    if request.method == "POST":
        name = request.form["name"]
        validity = int(request.form["validity"])
        price = float(request.form["price"])
        interval_time = request.form["interval_time"]
        interval_unit = request.form["interval_unit"]
        interval = f"{interval_time} {interval_unit}"
        
        conn.execute(
            "UPDATE packages SET name = ?, validity = ?, price = ?, interval = ? WHERE id = ?",
            (name, validity, price, interval, package_id)
        )
        conn.commit()
        conn.close()
        return redirect(url_for("package"))

    conn.close()
    return render_template("edit_package.html", package=pkg)

@app.route("/delete-package/<int:package_id>")
@login_required
def delete_package(package_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM packages WHERE id = ?", (package_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("package"))

@app.route("/toggle-package/<int:package_id>")
@login_required
def toggle_package(package_id):
    conn = get_db_connection()
    current_status = conn.execute("SELECT status FROM packages WHERE id = ?", (package_id,)).fetchone()["status"]
    new_status = "disabled" if current_status == "enabled" else "enabled"
    conn.execute("UPDATE packages SET status = ? WHERE id = ?", (new_status, package_id))
    conn.commit()
    conn.close()
    return redirect(url_for("package"))

@app.route("/manage-package")
@login_required
def manage_package():
    conn = get_db_connection()
    packages = conn.execute("SELECT * FROM packages").fetchall()
    conn.close()
    return render_template("manage_package.html", packages=packages)

@app.route("/updateprice_logs")
@login_required
def updateprice_logs():
    conn = get_db_connection()
    logs = conn.execute("SELECT * FROM updateprice_logs ORDER BY id DESC").fetchall()
    conn.close()
    return render_template("updateprice_logs.html", logs=logs)
    
@app.route("/clear_updateprice_logs", methods=["POST"])
@login_required
def clear_updateprice_logs():
    conn = get_db_connection()
    conn.execute("DELETE FROM updateprice_logs")
    conn.commit()
    conn.close()
    flash("All update price logs cleared successfully.", "success")
    return redirect(url_for("updateprice_logs"))


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5001)

