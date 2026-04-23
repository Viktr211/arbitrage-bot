import sqlite3
from datetime import datetime

DB_PATH = "arbitrage.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
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
            approved_at DATETIME,
            approved_by TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            trade_balance REAL DEFAULT 1000,
            withdrawable_balance REAL DEFAULT 0,
            total_profit REAL DEFAULT 0,
            total_admin_fee_paid REAL DEFAULT 0,
            trade_count INTEGER DEFAULT 0,
            portfolio TEXT,
            usdt_reserves TEXT,
            last_withdrawal_date DATETIME,
            demo_portfolio TEXT,
            demo_usdt_reserves TEXT,
            demo_daily_profits TEXT,
            demo_weekly_profits TEXT,
            demo_monthly_profits TEXT,
            demo_history TEXT,
            real_balance REAL DEFAULT 0,
            real_total_profit REAL DEFAULT 0,
            real_trade_count INTEGER DEFAULT 0,
            real_portfolio TEXT,
            real_usdt_reserves TEXT,
            real_daily_profits TEXT,
            real_weekly_profits TEXT,
            real_monthly_profits TEXT,
            real_history TEXT
        )
    ''')
    conn.commit()
    conn.close()

def fix_admin():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    admin_email = "cb777899@gmail.com"
    new_password = "Viktr211@"

    # Проверяем, есть ли пользователь
    cursor.execute("SELECT id FROM users WHERE email = ?", (admin_email,))
    if cursor.fetchone():
        cursor.execute("UPDATE users SET password_hash = ? WHERE email = ?", (new_password, admin_email))
        print(f"✅ Пароль для {admin_email} обновлён.")
    else:
        cursor.execute('''
            INSERT INTO users (
                email, password_hash, full_name, registration_status, trade_balance,
                approved_at, approved_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (admin_email, new_password, "Администратор", "approved", 1000,
              datetime.now().strftime('%Y-%m-%d %H:%M:%S'), "system"))
        print(f"✅ Администратор {admin_email} создан.")
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    fix_admin()
    print("Готово. Теперь входите с паролем: Viktr211@")
