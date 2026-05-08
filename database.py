import sqlite3

DB_NAME = "activolt.db"


def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Таблиця користувачів (авторизація)
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                        user_id INTEGER PRIMARY KEY,
                        full_name TEXT,
                        is_authorized INTEGER DEFAULT 1
                    )''')

    # Таблиця об'єктів (PAS)
    cursor.execute('''CREATE TABLE IF NOT EXISTS assets (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT,
                        status TEXT,
                        location TEXT
                    )''')

    # Таблиця журналу аварій (OZA)
    cursor.execute('''CREATE TABLE IF NOT EXISTS accidents (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        asset_id INTEGER,
                        description TEXT,
                        photo_id TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY(asset_id) REFERENCES assets(id)
                    )''')

    # Додаємо тестові дані, якщо база порожня
    cursor.execute("SELECT COUNT(*) FROM assets")
    if cursor.fetchone()[0] == 0:
        cursor.executemany('INSERT INTO assets (name, status, location) VALUES (?, ?, ?)',
                           [('ПС-110 "Північна"', 'Норма', 'м. Івано-Франківськ'),
                            ('Трансформатор Т-1', 'Потребує ремонту', 'с. Крихівці')])
    conn.commit()
    conn.close()


def add_user(user_id, full_name):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO users (user_id, full_name, is_authorized) VALUES (?, ?, 1)',
                   (user_id, full_name))
    conn.commit()
    conn.close()


def get_assets():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM assets')
    data = cursor.fetchall()
    conn.close()
    return data


def add_accident(asset_id, description, photo_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO accidents (asset_id, description, photo_id) VALUES (?, ?, ?)',
                   (asset_id, description, photo_id))
    conn.commit()
    conn.close()


def get_recent_accidents():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Використовуємо JOIN, щоб отримати назву об'єкта з таблиці assets
    cursor.execute('''
        SELECT a.name, acc.description, acc.created_at 
        FROM accidents acc
        JOIN assets a ON acc.asset_id = a.id
        ORDER BY acc.created_at DESC
        LIMIT 10
    ''')
    data = cursor.fetchall()
    conn.close()
    return data