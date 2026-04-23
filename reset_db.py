import sqlite3
import os
import json
from datetime import datetime

DB_PATH = "arbitrage.db"

# 1. Удаляем старую базу, если она есть
if os.path.exists(DB_PATH):
    os.remove(DB_PATH)
    print("Старая база удалена.")

# 2. Создаём новую базу с полной структурой (как ожидает код)
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Таблица пользователей (все поля, которые использует create_user)
cursor.execute('''
    CREATE TABLE users (
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

# 3. Добавляем администратора
admin_email = "cb777899@gmail.com"
admin_password = "Viktr211@"
cursor.execute('''
    INSERT INTO users (
        email, password_hash, full_name, registration_status, approved_at, approved_by,
        trade_balance, portfolio, usdt_reserves
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
''', (
    admin_email, admin_password, "Администратор", "approved",
    datetime.now().strftime('%Y-%m-%d %H:%M:%S'), "system",
    1000, json.dumps({"BTC": 0.013, "ETH": 0.42}), json.dumps({})
))

conn.commit()
conn.close()

print("✅ Новая база данных создана с правильной структурой.")
print(f"🔑 Администратор: {admin_email} / пароль: {admin_password}")
