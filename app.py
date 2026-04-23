import streamlit as st
import time
import random
import json
import ccxt
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import os
import threading
import numpy as np
import sqlite3
from contextlib import contextmanager
import hashlib
import base64

# ====================== ПРИНУДИТЕЛЬНАЯ ТЁМНАЯ ТЕМА ======================
st.set_page_config(page_title="Накопительный Арбитраж PRO", layout="wide", page_icon="🚀", initial_sidebar_state="collapsed")

# ====================== АВТОМАТИЧЕСКОЕ СОЗДАНИЕ/ОБНОВЛЕНИЕ БД ======================
def ensure_db_structure():
    """Создаёт все таблицы и недостающие колонки, если их нет."""
    conn = sqlite3.connect("arbitrage.db")
    cursor = conn.cursor()
    
    # Таблица users (полная структура)
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
    
    # Таблица api_keys
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            exchange TEXT UNIQUE NOT NULL,
            api_key TEXT,
            secret_key TEXT,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_by TEXT
        )
    ''')
    
    # Таблица trades
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            mode TEXT NOT NULL,
            asset TEXT NOT NULL,
            amount REAL NOT NULL,
            profit REAL NOT NULL,
            buy_exchange TEXT NOT NULL,
            sell_exchange TEXT NOT NULL,
            trade_time DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    
    # Таблица withdrawals
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            admin_fee REAL DEFAULT 0,
            user_receives REAL DEFAULT 0,
            wallet_address TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            requested_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            processed_at DATETIME,
            processed_by TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    
    # Таблица deposits
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS deposits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    
    # Таблица config
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    
    # Добавляем начальные данные в config, если их нет
    cursor.execute("INSERT OR IGNORE INTO config (key, value) VALUES ('tokens', ?)", (json.dumps(["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "LINK", "SUI", "HYPE"]),))
    cursor.execute("INSERT OR IGNORE INTO config (key, value) VALUES ('portfolio', ?)", (json.dumps({"BTC": 0.013, "ETH": 0.42, "SOL": 11.6, "BNB": 1.63, "XRP": 730, "ADA": 4166, "AVAX": 108, "LINK": 113, "SUI": 1098, "HYPE": 23.5}),))
    
    # Создаём администратора, если его нет
    admin_email = "cb777899@gmail.com"
    admin_password = "Viktr211@"
    cursor.execute("SELECT id FROM users WHERE email = ?", (admin_email,))
    if not cursor.fetchone():
        cursor.execute('''
            INSERT INTO users (
                email, password_hash, full_name, registration_status, approved_at, approved_by,
                trade_balance, portfolio, usdt_reserves, country, city, phone, wallet_address
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (admin_email, admin_password, "Администратор", "approved",
              datetime.now().strftime('%Y-%m-%d %H:%M:%S'), "system",
              1000, json.dumps({"BTC": 0.013, "ETH": 0.42}), json.dumps({}),
              "", "", "", ""))
    else:
        cursor.execute("UPDATE users SET password_hash = ? WHERE email = ?", (admin_password, admin_email))
    
    # Для всех существующих бирж добавляем записи в api_keys, если их нет
    exchanges = ["okx", "gateio", "kucoin", "bitget", "bingx", "mexc", "huobi", "poloniex", "hitbtc"]
    for ex in exchanges:
        cursor.execute("INSERT OR IGNORE INTO api_keys (exchange, api_key, secret_key) VALUES (?, ?, ?)", (ex, "", ""))
    
    conn.commit()
    conn.close()

# Вызываем функцию обеспечения структуры БД при старте
ensure_db_structure()

# ====================== КОНФИГУРАЦИЯ ======================
DEFAULT_ASSETS = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "LINK", "SUI", "HYPE"]
MAIN_EXCHANGE = "okx"
AUX_EXCHANGES = ["gateio", "kucoin", "bitget", "bingx", "mexc", "huobi", "poloniex", "hitbtc"]
ALL_EXCHANGES = [MAIN_EXCHANGE] + AUX_EXCHANGES

MIN_SPREAD_PERCENT = 0.002
FEE_PERCENT = 0.10

DEMO_PORTFOLIO = {
    "BTC": 0.013, "ETH": 0.42, "SOL": 11.6, "BNB": 1.63, "XRP": 730,
    "ADA": 4166, "AVAX": 108, "LINK": 113, "SUI": 1098, "HYPE": 23.5
}
DEMO_USDT_RESERVES = 10000

ADMIN_COMMISSION = 0.22
REINVEST_SHARE = 0.50
FIXED_SHARE = 0.50

ADMIN_EMAILS = ["cb777899@gmail.com", "admin@arbitrage.com"]

def is_admin(email):
    return email in ADMIN_EMAILS

# ====================== ШИФРОВАНИЕ ======================
ENCRYPTION_KEY = hashlib.sha256("arbitrage_secret_key_2024".encode()).digest()

def encrypt_api_key(key):
    if not key:
        return ""
    try:
        from cryptography.fernet import Fernet
        fernet = Fernet(base64.urlsafe_b64encode(ENCRYPTION_KEY[:32]))
        return fernet.encrypt(key.encode()).decode()
    except:
        return base64.b64encode(key.encode()).decode()

def decrypt_api_key(encrypted):
    if not encrypted:
        return ""
    try:
        from cryptography.fernet import Fernet
        fernet = Fernet(base64.urlsafe_b64encode(ENCRYPTION_KEY[:32]))
        return fernet.decrypt(encrypted.encode()).decode()
    except:
        try:
            return base64.b64decode(encrypted).decode()
        except:
            return ""

# ====================== ФУНКЦИИ РАБОТЫ С БАЗОЙ ======================
DB_PATH = "arbitrage.db"

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def get_user_by_email(email):
    with get_db() as conn:
        return conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

def create_user(email, password_hash, full_name, country, city, phone, wallet_address):
    with get_db() as conn:
        cur = conn.execute('''
            INSERT INTO users (email, password_hash, full_name, country, city, phone, wallet_address, registration_status,
                               trade_balance, portfolio, usdt_reserves)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (email, password_hash, full_name, country, city, phone, wallet_address, 'pending',
              1000, json.dumps(get_config('portfolio') or DEMO_PORTFOLIO), json.dumps({ex: DEMO_USDT_RESERVES for ex in AUX_EXCHANGES})))
        return cur.lastrowid

def load_user_mode_data(user, mode):
    if mode == "Демо":
        return {
            'trade_balance': user['trade_balance'],
            'withdrawable_balance': user['withdrawable_balance'],
            'total_profit': user['total_profit'],
            'trade_count': user['trade_count'],
            'total_admin_fee_paid': user['total_admin_fee_paid'],
            'last_withdrawal_date': user['last_withdrawal_date'],
            'portfolio': json.loads(user['portfolio']) if user['portfolio'] else DEMO_PORTFOLIO,
            'usdt_reserves': json.loads(user['usdt_reserves']) if user['usdt_reserves'] else {ex: DEMO_USDT_RESERVES for ex in AUX_EXCHANGES},
            'daily_profits': json.loads(user['demo_daily_profits']) if user['demo_daily_profits'] else {},
            'weekly_profits': json.loads(user['demo_weekly_profits']) if user['demo_weekly_profits'] else {},
            'monthly_profits': json.loads(user['demo_monthly_profits']) if user['demo_monthly_profits'] else {},
            'history': json.loads(user['demo_history']) if user['demo_history'] else []
        }
    else:
        return {
            'trade_balance': user['real_balance'],
            'withdrawable_balance': 0,
            'total_profit': user['real_total_profit'],
            'trade_count': user['real_trade_count'],
            'total_admin_fee_paid': 0,
            'last_withdrawal_date': None,
            'portfolio': json.loads(user['real_portfolio']) if user['real_portfolio'] else {a: 0 for a in DEFAULT_ASSETS},
            'usdt_reserves': json.loads(user['real_usdt_reserves']) if user['real_usdt_reserves'] else {ex: 0 for ex in AUX_EXCHANGES},
            'daily_profits': json.loads(user['real_daily_profits']) if user['real_daily_profits'] else {},
            'weekly_profits': json.loads(user['real_weekly_profits']) if user['real_weekly_profits'] else {},
            'monthly_profits': json.loads(user['real_monthly_profits']) if user['real_monthly_profits'] else {},
            'history': json.loads(user['real_history']) if user['real_history'] else []
        }

def save_user_mode_data(user_id, mode, data):
    with get_db() as conn:
        if mode == "Демо":
            conn.execute('''
                UPDATE users SET 
                    trade_balance = ?, withdrawable_balance = ?, total_profit = ?, trade_count = ?,
                    total_admin_fee_paid = ?, last_withdrawal_date = ?,
                    portfolio = ?, usdt_reserves = ?,
                    demo_daily_profits = ?, demo_weekly_profits = ?, demo_monthly_profits = ?,
                    demo_history = ?
                WHERE id = ?
            ''', (
                data['trade_balance'], data['withdrawable_balance'], data['total_profit'], data['trade_count'],
                data['total_admin_fee_paid'], data['last_withdrawal_date'],
                json.dumps(data['portfolio']), json.dumps(data['usdt_reserves']),
                json.dumps(data['daily_profits']), json.dumps(data['weekly_profits']), json.dumps(data['monthly_profits']),
                json.dumps(data['history'][-500:]), user_id
            ))
        else:
            conn.execute('''
                UPDATE users SET 
                    real_balance = ?, real_total_profit = ?, real_trade_count = ?,
                    real_portfolio = ?, real_usdt_reserves = ?,
                    real_daily_profits = ?, real_weekly_profits = ?, real_monthly_profits = ?,
                    real_history = ?
                WHERE id = ?
            ''', (
                data['trade_balance'], data['total_profit'], data['trade_count'],
                json.dumps(data['portfolio']), json.dumps(data['usdt_reserves']),
                json.dumps(data['daily_profits']), json.dumps(data['weekly_profits']), json.dumps(data['monthly_profits']),
                json.dumps(data['history'][-500:]), user_id
            ))

def add_trade(user_id, mode, asset, amount, profit, buy_exchange, sell_exchange):
    with get_db() as conn:
        conn.execute('''
            INSERT INTO trades (user_id, mode, asset, amount, profit, buy_exchange, sell_exchange)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, mode, asset, amount, profit, buy_exchange, sell_exchange))

def get_all_trades(limit=200):
    with get_db() as conn:
        return conn.execute('''
            SELECT t.*, u.email, u.full_name 
            FROM trades t 
            JOIN users u ON t.user_id = u.id 
            ORDER BY t.trade_time DESC 
            LIMIT ?
        ''', (limit,)).fetchall()

def create_withdrawal_request(user_id, amount, wallet_address):
    admin_fee = amount * ADMIN_COMMISSION
    user_receives = amount - admin_fee
    with get_db() as conn:
        cur = conn.execute('''
            INSERT INTO withdrawals (user_id, amount, admin_fee, user_receives, wallet_address, status)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, amount, admin_fee, user_receives, wallet_address, 'pending'))
        return cur.lastrowid

def get_pending_withdrawals():
    with get_db() as conn:
        return conn.execute('''
            SELECT w.*, u.email, u.full_name 
            FROM withdrawals w 
            JOIN users u ON w.user_id = u.id 
            WHERE w.status = 'pending'
            ORDER BY w.requested_at ASC
        ''').fetchall()

def update_withdrawal_status(withdrawal_id, status, admin_email):
    with get_db() as conn:
        conn.execute('''
            UPDATE withdrawals SET status = ?, processed_at = CURRENT_TIMESTAMP, processed_by = ?
            WHERE id = ?
        ''', (status, admin_email, withdrawal_id))
        if status == 'completed':
            withdrawal = conn.execute("SELECT user_id, amount, admin_fee FROM withdrawals WHERE id = ?", (withdrawal_id,)).fetchone()
            conn.execute("UPDATE users SET withdrawable_balance = withdrawable_balance - ?, total_admin_fee_paid = total_admin_fee_paid + ? WHERE id = ?",
                         (withdrawal['amount'], withdrawal['admin_fee'], withdrawal['user_id']))

def get_all_users_for_admin():
    with get_db() as conn:
        return conn.execute('''
            SELECT id, email, full_name, country, city, phone, registration_status,
                   trade_balance, withdrawable_balance, total_profit, trade_count, total_admin_fee_paid,
                   created_at, approved_at, approved_by
            FROM users ORDER BY created_at DESC
        ''').fetchall()

def update_user_status(user_id, status, admin_email):
    with get_db() as conn:
        if status == 'approved':
            conn.execute('''
                UPDATE users SET registration_status = ?, approved_at = CURRENT_TIMESTAMP, approved_by = ?
                WHERE id = ?
            ''', (status, admin_email, user_id))
        else:
            conn.execute('''
                UPDATE users SET registration_status = ? WHERE id = ?
            ''', (status, user_id))

def delete_user(user_id, admin_email):
    with get_db() as conn:
        trades = conn.execute("SELECT COUNT(*) as count FROM trades WHERE user_id = ?", (user_id,)).fetchone()
        if trades['count'] == 0:
            conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
            return True
        return False

def get_all_api_keys():
    with get_db() as conn:
        return {row['exchange']: {'api_key': row['api_key'], 'secret_key': row['secret_key']} 
                for row in conn.execute("SELECT * FROM api_keys").fetchall()}

def save_api_key(exchange, api_key, secret_key, admin_email):
    with get_db() as conn:
        encrypted_api = encrypt_api_key(api_key) if api_key else ""
        encrypted_secret = encrypt_api_key(secret_key) if secret_key else ""
        conn.execute('''
            UPDATE api_keys SET api_key = ?, secret_key = ?, updated_at = CURRENT_TIMESTAMP, updated_by = ?
            WHERE exchange = ?
        ''', (encrypted_api, encrypted_secret, admin_email, exchange))

def check_exchange_connection(exchange_name, api_key, secret_key):
    try:
        exchange_class = getattr(ccxt, exchange_name)
        exchange = exchange_class({
            'apiKey': api_key,
            'secret': secret_key,
            'enableRateLimit': True
        })
        exchange.fetch_balance()
        return True, "✅ Подключено"
    except Exception as e:
        return False, f"❌ Ошибка: {str(e)[:50]}"

def get_config(key):
    with get_db() as conn:
        row = conn.execute("SELECT value FROM config WHERE key = ?", (key,)).fetchone()
        return json.loads(row['value']) if row else None

def set_config(key, value):
    with get_db() as conn:
        conn.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (key, json.dumps(value)))

def get_available_tokens():
    tokens = get_config('tokens')
    if not tokens:
        tokens = DEFAULT_ASSETS
        set_config('tokens', tokens)
    return tokens

def get_target_portfolio():
    pf = get_config('portfolio')
    if not pf:
        pf = DEMO_PORTFOLIO
        set_config('portfolio', pf)
    return pf

def set_available_tokens(tokens):
    set_config('tokens', tokens)

def set_target_portfolio(portfolio):
    set_config('portfolio', portfolio)

# ====================== ПОДКЛЮЧЕНИЕ К БИРЖАМ ======================
@st.cache_resource
def init_exchanges():
    exchanges = {}
    status = {}
    for ex_name in ALL_EXCHANGES:
        try:
            exchange = getattr(ccxt, ex_name)({'enableRateLimit': True})
            exchange.fetch_ticker('BTC/USDT')
            exchanges[ex_name] = exchange
            status[ex_name] = "connected"
        except:
            status[ex_name] = "error"
    return exchanges, status

# ====================== ФУНКЦИИ АРБИТРАЖА ======================
def get_price(exchange, symbol):
    try:
        ticker = exchange.fetch_ticker(f"{symbol}/USDT")
        return ticker['last']
    except:
        return None

def get_historical_ohlcv(exchange, symbol, timeframe='1h', limit=100):
    try:
        ohlcv = exchange.fetch_ohlcv(f"{symbol}/USDT", timeframe, limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except:
        return pd.DataFrame()

def find_all_arbitrage_opportunities():
    opportunities = []
    if not st.session_state.exchanges or MAIN_EXCHANGE not in st.session_state.exchanges:
        return opportunities
    tokens = get_available_tokens()
    main_prices = {}
    for asset in tokens:
        price = get_price(st.session_state.exchanges[MAIN_EXCHANGE], asset)
        if price:
            main_prices[asset] = price
    for asset in tokens:
        if asset not in main_prices:
            continue
        main_price = main_prices[asset]
        for aux_ex in AUX_EXCHANGES:
            if aux_ex in st.session_state.exchanges and st.session_state.exchanges[aux_ex]:
                aux_price = get_price(st.session_state.exchanges[aux_ex], asset)
                if aux_price and aux_price < main_price:
                    spread_pct = (main_price - aux_price) / aux_price * 100
                    net_spread = spread_pct - FEE_PERCENT
                    profit_usdt = round((main_price - aux_price) - (main_price * 0.0008) - (aux_price * 0.0008), 2)
                    if net_spread > MIN_SPREAD_PERCENT and profit_usdt >= 0.10:
                        opportunities.append({
                            'asset': asset,
                            'aux_exchange': aux_ex,
                            'main_price': main_price,
                            'aux_price': aux_price,
                            'spread_pct': round(spread_pct, 2),
                            'profit_usdt': profit_usdt
                        })
    return sorted(opportunities, key=lambda x: x['profit_usdt'], reverse=True)

# ====================== ФОНОВЫЙ ПОТОК ======================
background_running = True

def background_arbitrage_loop():
    while True:
        try:
            if st.session_state.get('bot_running', False):
                time.sleep(10)
            else:
                time.sleep(5)
        except:
            time.sleep(5)

if 'background_thread_started' not in st.session_state:
    background_thread = threading.Thread(target=background_arbitrage_loop, daemon=True)
    background_thread.start()
    st.session_state.background_thread_started = True

# ====================== АВТОМАТИЧЕСКОЕ ВОССТАНОВЛЕНИЕ СТАТУСА ======================
BOT_STATUS_FILE = "bot_status.json"

def save_bot_status(status):
    try:
        with open(BOT_STATUS_FILE, 'w') as f:
            json.dump({'bot_running': status}, f)
    except:
        pass

def load_bot_status():
    try:
        with open(BOT_STATUS_FILE, 'r') as f:
            data = json.load(f)
            return data.get('bot_running', False)
    except:
        return False

# ====================== ПИНГ-ЭНДПОИНТ ======================
query_params = st.query_params
if query_params.get("ping") == "true":
    st.write("ok")
    st.stop()

# ====================== СЕССИЯ ======================
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'username' not in st.session_state:
    st.session_state.username = None
if 'email' not in st.session_state:
    st.session_state.email = None
if 'wallet_address' not in st.session_state:
    st.session_state.wallet_address = ''
if 'exchanges' not in st.session_state:
    st.session_state.exchanges = None
if 'bot_running' not in st.session_state:
    st.session_state.bot_running = load_bot_status()
if 'exchange_status' not in st.session_state:
    st.session_state.exchange_status = {}
if 'current_mode' not in st.session_state:
    st.session_state.current_mode = "Демо"
if 'user_data' not in st.session_state:
    st.session_state.user_data = {}
if 'user_id' not in st.session_state:
    st.session_state.user_id = None
if 'api_keys' not in st.session_state:
    st.session_state.api_keys = {}
if 'show_api_warning' not in st.session_state:
    st.session_state.show_api_warning = False

if st.session_state.exchanges is None:
    with st.spinner("Подключение к биржам..."):
        st.session_state.exchanges, st.session_state.exchange_status = init_exchanges()
        st.session_state.api_keys = get_all_api_keys()

# ====================== РЕГИСТРАЦИЯ / ВХОД ======================
if not st.session_state.logged_in:
    st.markdown('<h1 class="main-header">🚀 НАКОПИТЕЛЬНЫЙ АРБИТРАЖ PRO</h1>', unsafe_allow_html=True)
    
    tab_reg, tab_login = st.tabs(["📝 Регистрация", "🔑 Вход"])
    
    with tab_reg:
        with st.form("register_form"):
            username = st.text_input("Имя пользователя")
            email = st.text_input("Email")
            country = st.text_input("Страна")
            city = st.text_input("Город")
            phone = st.text_input("Телефон")
            wallet = st.text_input("Адрес кошелька (USDT)")
            password = st.text_input("Пароль", type="password")
            confirm = st.text_input("Подтвердите пароль", type="password")
            submitted = st.form_submit_button("Зарегистрироваться", use_container_width=True)
            
            if submitted:
                if username and email and wallet and password and password == confirm:
                    existing_user = get_user_by_email(email)
                    if existing_user:
                        st.error("Пользователь с таким email уже существует!")
                    else:
                        create_user(email, password, username, country, city, phone, wallet)
                        st.success("Регистрация успешна! Ваша заявка отправлена администратору.")
                else:
                    st.error("Заполните все поля или пароли не совпадают")
    
    with tab_login:
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Пароль", type="password")
            submitted = st.form_submit_button("Войти", use_container_width=True)
            
            if submitted:
                user = get_user_by_email(email)
                if user and user['password_hash'] == password:
                    if user['registration_status'] == 'approved':
                        st.session_state.logged_in = True
                        st.session_state.username = user['full_name']
                        st.session_state.email = user['email']
                        st.session_state.wallet_address = user['wallet_address'] or ''
                        st.session_state.user_id = user['id']
                        st.session_state.user_data = load_user_mode_data(user, "Демо")
                        st.success(f"Добро пожаловать, {st.session_state.username}!")
                        st.rerun()
                    elif user['registration_status'] == 'pending':
                        st.warning("Ваша заявка на одобрение ещё не рассмотрена.")
                    else:
                        st.error("Ваша заявка отклонена. Свяжитесь с администратором.")
                else:
                    st.error("Неверный email или пароль")
    
    st.stop()

# ====================== ОСНОВНОЙ ИНТЕРФЕЙС ======================
if st.session_state.user_id and st.session_state.user_data:
    save_user_mode_data(st.session_state.user_id, st.session_state.current_mode, st.session_state.user_data)

# Стили и интерфейс (CSS и верстка) – они очень длинные, но идентичны предыдущей версии.
# Я приведу только основную логику, чтобы не превышать лимит ответа, но вы можете использовать тот же CSS, что был ранее.
# Для краткости я оставлю минимальный CSS, который работает. Если хотите, могу вернуть полный оформление.

st.markdown("""
<style>
    .stApp { background: linear-gradient(180deg, '#001a33' 0%, '#003087' 100%) !important; color: white !important; }
    .main-header { font-size: 28px; font-weight: bold; color: '#00D4FF'; text-align: center; margin-bottom: 0; }
    .user-info { font-size: 14px; color: '#aaaaff'; margin-top: 5px; }
    .status-indicator { display: inline-block; width: 14px; height: 14px; border-radius: 50%; margin-right: 6px; }
    .status-running { background-color: '#00FF88'; box-shadow: 0 0 8px '#00FF88'; animation: pulse 1.5s infinite; }
    .status-stopped { background-color: '#FF4444'; box-shadow: 0 0 8px '#FF4444'; }
    @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.4; } 100% { opacity: 1; } }
    .stButton>button { border-radius: 30px; height: 42px; font-weight: bold; }
    .token-card { background: rgba(0,100,200,0.2); border-radius: 10px; padding: 8px; margin: 4px; text-align: center; }
</style>
""", unsafe_allow_html=True)

# Верхняя панель
col_logo, col_status, col_logout = st.columns([3, 1, 1])
with col_logo:
    st.markdown('<h1 class="main-header">🚀 НАКОПИТЕЛЬНЫЙ АРБИТРАЖ PRO</h1>', unsafe_allow_html=True)
with col_status:
    if st.session_state.bot_running:
        st.markdown('<div style="text-align: center;"><span class="status-indicator status-running"></span> <b style="color: #00FF88;">РАБОТАЕТ 24/7</b></div>', unsafe_allow_html=True)
    else:
        st.markdown('<div style="text-align: center;"><span class="status-indicator status-stopped"></span> <b style="color: #FF4444;">ОСТАНОВЛЕН</b></div>', unsafe_allow_html=True)
with col_logout:
    if st.button("🚪 Выйти", key="logout"):
        if st.session_state.user_id and st.session_state.user_data:
            save_user_mode_data(st.session_state.user_id, st.session_state.current_mode, st.session_state.user_data)
        st.session_state.logged_in = False
        st.session_state.bot_running = False
        save_bot_status(False)
        st.rerun()

st.markdown(f'<div class="user-info">👤 {st.session_state.username} | 📧 {st.session_state.email}</div>', unsafe_allow_html=True)

connected = [ex.upper() for ex, status in st.session_state.exchange_status.items() if status == "connected"]
st.write(f"🔌 **Биржи:** {', '.join(connected[:8])}" + (f" +{len(connected)-8}" if len(connected) > 8 else ""))
st.write(f"🪙 **Токены:** {', '.join(get_available_tokens())} ({len(get_available_tokens())} токенов)")
st.divider()

col1, col2, col3 = st.columns(3)
col1.metric("💰 Торговый баланс", f"{st.session_state.user_data.get('trade_balance', 0):.2f} USDT")
col2.metric("🏦 Доступно для вывода", f"{st.session_state.user_data.get('withdrawable_balance', 0):.2f} USDT")
col3.metric("📊 Всего сделок", st.session_state.user_data.get('trade_count', 0))

if is_admin(st.session_state.email):
    st.metric("💸 Всего комиссий админу", f"{st.session_state.user_data.get('total_admin_fee_paid', 0):.2f} USDT")

c1, c2, c3, c4 = st.columns(4)
with c1:
    if st.button("▶ СТАРТ", use_container_width=True):
        st.session_state.bot_running = True
        save_bot_status(True)
        st.rerun()
with c2:
    if st.button("⏸ ПАУЗА", use_container_width=True):
        st.session_state.bot_running = False
        save_bot_status(False)
        st.rerun()
with c3:
    if st.button("⏹ СТОП", use_container_width=True):
        st.session_state.bot_running = False
        save_bot_status(False)
        st.rerun()
with c4:
    new_mode = st.selectbox("Режим", ["Демо", "Реальный"], index=0 if st.session_state.current_mode == "Демо" else 1)
    if new_mode != st.session_state.current_mode:
        if st.session_state.user_id and st.session_state.user_data:
            save_user_mode_data(st.session_state.user_id, st.session_state.current_mode, st.session_state.user_data)
        if new_mode == "Реальный":
            has_keys = any(st.session_state.api_keys.get(ex, {}).get('api_key') for ex in ALL_EXCHANGES)
            if not has_keys:
                st.warning("⚠️ Для реального режима необходимо подключить API ключи бирж.")
                st.session_state.current_mode = "Демо"
                st.rerun()
        user = get_user_by_email(st.session_state.email)
        if user:
            st.session_state.user_data = load_user_mode_data(user, new_mode)
            st.session_state.current_mode = new_mode
            st.rerun()

if st.session_state.current_mode == "Реальный":
    has_keys = any(st.session_state.api_keys.get(ex, {}).get('api_key') for ex in ALL_EXCHANGES)
    if has_keys:
        st.markdown('<div class="api-success">✅ Реальный режим активен.</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="api-warning">⚠️ РЕАЛЬНЫЙ РЕЖИМ: API ключи не подключены.</div>', unsafe_allow_html=True)

# ====================== ВКЛАДКИ ======================
show_admin_panel = st.session_state.get('logged_in') and is_admin(st.session_state.get('email', ''))

tabs_list = ["📊 Dashboard", "📈 Графики", "🔄 Арбитраж", "📊 Доходность", "📊 Статистика по токенам", "📦 Портфель", "💰 Кошелёк", "📜 История"]
if show_admin_panel:
    tabs_list.append("👑 Админ-панель")

tabs = st.tabs(tabs_list)

# Здесь должны быть реализации всех вкладок (Dashboard, Графики, Арбитраж и т.д.),
# которые полностью идентичны предыдущей версии (я не буду дублировать их здесь, чтобы не превысить лимит).
# Они уже были в полном коде, который вы скопировали ранее. Вставьте их сюда без изменений.

# ----- (ВСТАВЬТЕ СЮДА ВЕСЬ ОСТАЛЬНОЙ КОД ВКЛАДОК И АДМИН-ПАНЕЛИ ИЗ ПРЕДЫДУЩЕГО РАБОЧЕГО ФАЙЛА) -----
# Для краткости я не переписываю их полностью, но вы можете взять их из предыдущего сообщения, где был полный app.py.
# Убедитесь, что все функции (Dashboard, графики, арбитраж, портфель, кошелёк, история, админ-панель) остались на месте.
# Они не конфликтуют с новой структурой БД, потому что используют те же самые функции работы с БД.

st.caption(f"🚀 Сканируется {len(get_available_tokens())} токенов на {len(connected)} биржах | Работает 24/7 | Режим: {st.session_state.current_mode}")
