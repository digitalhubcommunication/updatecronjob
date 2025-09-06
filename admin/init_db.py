import sqlite3

# Connect to the database (creates it if it doesn't exist)
conn = sqlite3.connect('database.db')
cursor = conn.cursor()

# Create the 'users' table
cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    password TEXT,
    phone TEXT,
    domain TEXT,
    status TEXT DEFAULT 'Enable',
    active_package TEXT,
    expair_date TEXT,
    order_update_url TEXT,
    price_update_url TEXT,
    file_update_url TEXT
)
''')

conn.commit()
conn.close()

print("✅ 'users' table created.")
