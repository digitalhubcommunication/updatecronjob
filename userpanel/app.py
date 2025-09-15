from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
import os
from datetime import datetime, timedelta
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "supersecretkey"
DB_PATH = "/home/beta.expresscronjob.com/cronjobs.db"

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
                file_update_url TEXT,
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
                email TEXT NOT NULL,
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

@app.route("/")
def home():
    conn = get_db_connection()
    packages = conn.execute("SELECT * FROM packages WHERE status = 'enabled'").fetchall()
    conn.close()
    return render_template("Auth/home.html", packages=packages, now=datetime.now())

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first.", "error")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form['name']
        email = request.form['email']
        mobile = request.form['mobile']
        domain = request.form['domain']
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        if password != confirm_password:
            flash("Passwords do not match", "error")
            return render_template('Auth/u_register.html')

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM users WHERE name = ? OR domain = ? OR mobile = ?", (name, domain, mobile))
        existing_user = cursor.fetchone()

        if existing_user:
            conn.close()
            flash("Username, domain, or phone number already in use", "error")
            return render_template('Auth/u_register.html')

        hashed_password = generate_password_hash(password)
        cursor.execute(
            "INSERT INTO users (name, email, mobile, domain, password) VALUES (?, ?, ?, ?, ?)",
            (name, email, mobile, domain, hashed_password)
        )
        conn.commit()
        conn.close()
        flash("You have registered successfully!", "success")
        return redirect(url_for('login'))

    return render_template('Auth/u_register.html')

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form['email']
        password = request.form['password']

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            session["email"] = user["email"]
            flash("Login successful!", "success")
            return redirect(url_for("u_dashboard"))
        else:
            flash("Invalid email or password", "error")
            return render_template("Auth/u_login.html")

    return render_template("Auth/u_login.html")

@app.route("/u/dashboard")
@login_required
def u_dashboard():
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    conn.close()
    return render_template("Auth/u_dashboard.html", user=user)

@app.route("/domain", methods=["GET", "POST"])
@login_required
def user_domain():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],))
    user = cursor.fetchone()

    if request.method == "POST":
        new_status = "Disable" if user["status"] == "Enable" else "Enable"
        cursor.execute("UPDATE users SET status = ? WHERE id = ?", (new_status, session["user_id"]))
        conn.commit()
        cursor.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],))
        user = cursor.fetchone()
        flash(f"Domain status updated to {new_status}.", "success")

    conn.close()
    return render_template("Auth/domain.html", user=user)

@app.route('/cronjob_history')
@login_required
def cronjob_history():
    page = int(request.args.get('page', 1))
    per_page = 10
    offset = (page - 1) * per_page

    email = session.get("email")
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM cron_history WHERE email = ?", (email,))
    total_records = cursor.fetchone()[0]
    total_pages = (total_records + per_page - 1) // per_page

    cursor.execute("SELECT * FROM cron_history WHERE email = ? ORDER BY timestamp DESC LIMIT ? OFFSET ?", (email, per_page, offset))
    histories = cursor.fetchall()
    conn.close()

    return render_template("Auth/cronjob_history.html", histories=histories, page=page, total_pages=total_pages)


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row  # So you can access columns like user["name"]
    cursor = conn.cursor()

    # Fetch user info
    cursor.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],))
    user = cursor.fetchone()

    if request.method == "POST":
        # Toggle status: Enable <-> Disable
        current_status = user["status"]
        new_status = "Disable" if current_status == "Enable" else "Enable"

        cursor.execute("UPDATE users SET status = ? WHERE id = ?", (new_status, session["user_id"]))
        conn.commit()

        # Refresh user data after update
        cursor.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],))
        user = cursor.fetchone()

        flash(f"Account status updated to {new_status}.", "success")

    conn.close()
    return render_template("Auth/profile.html", user=user)

@app.route("/update_password", methods=["POST"])
@login_required
def update_password():
    current_password = request.form["current_password"]
    new_password = request.form["new_password"]
    confirm_password = request.form["confirm_password"]

    conn = get_db_connection()
    cursor = conn.cursor()

    # Get user from DB
    cursor.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],))
    user = cursor.fetchone()

    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("profile"))

    # Check current password
    if not check_password_hash(user["password"], current_password):
        flash("Current password is incorrect.", "danger")
        return redirect(url_for("profile"))

    # Validate new password
    if new_password != confirm_password:
        flash("New passwords do not match.", "danger")
        return redirect(url_for("profile"))

    # Hash and update new password
    hashed_password = generate_password_hash(new_password)
    cursor.execute("UPDATE users SET password = ? WHERE id = ?", (hashed_password, session["user_id"]))
    conn.commit()
    conn.close()

    flash("Password updated successfully.", "success")
    return redirect(url_for("profile"))

@app.route("/dhru_fusion_settings", methods=["GET", "POST"])
@login_required
def dhru_fusion_settings():
    conn = get_db_connection()
    cursor = conn.cursor()

    user_id = session["user_id"]

    if request.method == "POST":
        api_url = request.form["api_url"].strip()
        api_username = request.form["api_username"].strip()
        api_key = request.form["api_key"].strip()

        # Check if record exists
        cursor.execute("SELECT * FROM dhru_settings WHERE user_id = ?", (user_id,))
        existing = cursor.fetchone()

        if existing:
            # Update
            cursor.execute("""
                UPDATE dhru_settings 
                SET api_url = ?, api_username = ?, api_key = ?
                WHERE user_id = ?
            """, (api_url, api_username, api_key, user_id))
        else:
            # Insert
            cursor.execute("""
                INSERT INTO dhru_settings (user_id, api_url, api_username, api_key)
                VALUES (?, ?, ?, ?)
            """, (user_id, api_url, api_username, api_key))

        conn.commit()
        flash("Dhru Fusion settings updated successfully.", "success")

    # Fetch latest settings to prefill form
    cursor.execute("SELECT * FROM dhru_settings WHERE user_id = ?", (user_id,))
    settings = cursor.fetchone()

    conn.close()
    return render_template("Auth/dhru_fusion_settings.html", settings=settings)

@app.route("/dhru_api_setting")
@login_required
def dhru_api_setting():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Fetch current user's Dhru API settings
    cursor.execute("SELECT * FROM dhru_settings WHERE user_id = ?", (session["user_id"],))
    dhru_data = cursor.fetchone()

    conn.close()
    return render_template("Auth/dhru_api_setting.html", dhru_data=dhru_data)

@app.route("/cloudfire_setting")
@login_required
def cloudfire_setting():
    return render_template("Auth/cloudfire_setting.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully.", "success")
    return redirect(url_for("home"))

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)
