import sqlite3
from datetime import datetime

DB_PATH = "arbitrage.db"

def create_database():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Таблица пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            full_name TEXT NOT NULL,
            country TEXT,
            city TEXT,
            phone TEXT,
            wallet_address TEXT,
            registration_status TEXT DEFAULT 'pending',
            balance REAL DEFAULT 0,
            total_profit REAL DEFAULT 0,
            trade_count INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            approved_at DATETIME,
            approved_by TEXT
        )
    ''')
    
    # Таблица сделок
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            asset TEXT NOT NULL,
            amount REAL NOT NULL,
            profit REAL NOT NULL,
            buy_exchange TEXT NOT NULL,
            sell_exchange TEXT NOT NULL,
            trade_time DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица заявок на вывод
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            wallet_address TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            requested_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            processed_at DATETIME,
            processed_by TEXT
        )
    ''')
    
    # Таблица пополнений
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS deposits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Создаём администратора
    admin_email = "cb777899@gmail.com"
    cursor.execute("SELECT * FROM users WHERE email = ?", (admin_email,))
    if not cursor.fetchone():
        cursor.execute('''
            INSERT INTO users (email, password_hash, full_name, registration_status, balance, approved_at, approved_by)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (admin_email, "admin123", "Администратор", "approved", 0, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), "system"))
        print("✅ Администратор создан")
    
    conn.commit()
    conn.close()
    print(f"✅ База данных создана: {DB_PATH}")

if __name__ == "__main__":
    create_database()
    print("Готово! Теперь файл arbitrage.db создан.")
