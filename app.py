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
st.markdown("""
# ====================== ВРЕМЕННЫЙ СБРОС ПАРОЛЯ АДМИНИСТРАТОРА ======================
import sqlite3
temp_db = "arbitrage.db"
conn = sqlite3.connect(temp_db)
cursor = conn.cursor()
admin_email = "cb777899@gmail.com"
new_password = "Viktr211@"
# Обновляем пароль для этого email
cursor.execute("UPDATE users SET password_hash = ? WHERE email = ?", (new_password, admin_email))
if cursor.rowcount == 0:
    # Если пользователя нет – создаём
    cursor.execute('''
        INSERT INTO users (email, password_hash, full_name, registration_status, trade_balance)
        VALUES (?, ?, ?, ?, ?)
    ''', (admin_email, new_password, "Администратор", "approved", 1000))
conn.commit()
conn.close()
print("✅ Пароль администратора сброшен на Viktr211@")
# ==================================================================================
<style>
    .stApp { background: linear-gradient(180deg, #001a33 0%, #003087 100%) !important; color: white !important; }
    .main-header { font-size: 28px; font-weight: bold; color: #00D4FF; text-align: center; margin-bottom: 0; }
    .user-info { font-size: 14px; color: #aaaaff; margin-top: 5px; }
    .status-indicator { display: inline-block; width: 14px; height: 14px; border-radius: 50%; margin-right: 6px; }
    .status-running { background-color: #00FF88; box-shadow: 0 0 8px #00FF88; animation: pulse 1.5s infinite; }
    .status-stopped { background-color: #FF4444; box-shadow: 0 0 8px #FF4444; }
    @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.4; } 100% { opacity: 1; } }
    .stButton>button { border-radius: 30px; height: 42px; font-weight: bold; }
    .green-button button { background-color: #00AA44 !important; color: white !important; }
    .yellow-button button { background-color: #CC8800 !important; color: white !important; }
    .red-button button { background-color: #CC3333 !important; color: white !important; }
    .token-card { background: rgba(0,100,200,0.2); border-radius: 10px; padding: 8px; margin: 4px; text-align: center; }
    .profit-card { background: rgba(0,255,100,0.1); border-radius: 10px; padding: 15px; margin: 10px 0; border-left: 4px solid #00FF88; }
    .api-warning { background: rgba(255,100,100,0.2); border-radius: 10px; padding: 10px; margin: 10px 0; border-left: 4px solid #FF4444; }
    .api-success { background: rgba(0,255,100,0.2); border-radius: 10px; padding: 10px; margin: 10px 0; border-left: 4px solid #00FF88; }
    .help-card { background: rgba(0,212,255,0.2); border-radius: 10px; padding: 15px; margin: 10px 0; border-left: 4px solid #00D4FF; }
    .withdraw-card { background: rgba(255,193,7,0.2); border-radius: 10px; padding: 15px; margin: 10px 0; border-left: 4px solid #FFC107; }
</style>
""", unsafe_allow_html=True)

# ====================== КОНФИГУРАЦИЯ ПО УМОЛЧАНИЮ ======================
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

# ====================== КОНФИГУРАЦИЯ АДМИНА ======================
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

# ====================== БАЗА ДАННЫХ ======================
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

def init_db():
    with get_db() as conn:
        conn.execute('''
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
        conn.execute('''
            CREATE TABLE IF NOT EXISTS api_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exchange TEXT UNIQUE NOT NULL,
                api_key TEXT,
                secret_key TEXT,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_by TEXT
            )
        ''')
        conn.execute('''
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
        conn.execute('''
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
        conn.execute('''
            CREATE TABLE IF NOT EXISTS deposits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        for ex in ALL_EXCHANGES:
            conn.execute('''
                INSERT OR IGNORE INTO api_keys (exchange, api_key, secret_key)
                VALUES (?, ?, ?)
            ''', (ex, "", ""))
        # Загружаем настройки токенов по умолчанию, если их нет
        conn.execute('''
            INSERT OR IGNORE INTO config (key, value) VALUES ('tokens', ?)
        ''', (json.dumps(DEFAULT_ASSETS),))
        conn.execute('''
            INSERT OR IGNORE INTO config (key, value) VALUES ('portfolio', ?)
        ''', (json.dumps(DEMO_PORTFOLIO),))

init_db()

def get_config(key):
    with get_db() as conn:
        row = conn.execute("SELECT value FROM config WHERE key = ?", (key,)).fetchone()
        return json.loads(row['value']) if row else None

def set_config(key, value):
    with get_db() as conn:
        conn.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (key, json.dumps(value)))

# ====================== ФУНКЦИИ БАЗЫ ДАННЫХ / АДМИН-ТОКЕНЫ ======================
def get_available_tokens():
    tokens = get_config('tokens')
    if not tokens:
        tokens = DEFAULT_ASSETS
        set_config('tokens', tokens)
    return tokens

def get_target_portfolio():
    portfolio = get_config('portfolio')
    if not portfolio:
        portfolio = DEMO_PORTFOLIO
        set_config('portfolio', portfolio)
    return portfolio

def set_available_tokens(tokens):
    set_config('tokens', tokens)

def set_target_portfolio(portfolio):
    set_config('portfolio', portfolio)

# ====================== ОСТАЛЬНЫЕ ФУНКЦИИ (ПОЛЬЗОВАТЕЛИ, ТОРГОВЛЯ) ======================
def get_user_by_email(email):
    with get_db() as conn:
        return conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

def create_user(email, password_hash, full_name, country, city, phone, wallet_address):
    with get_db() as conn:
        cursor = conn.execute('''
            INSERT INTO users (email, password_hash, full_name, country, city, phone, wallet_address, registration_status,
                               trade_balance, portfolio, usdt_reserves)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (email, password_hash, full_name, country, city, phone, wallet_address, 'pending',
              1000, json.dumps(get_target_portfolio()), json.dumps({ex: DEMO_USDT_RESERVES for ex in AUX_EXCHANGES})))
        return cursor.lastrowid

def load_user_mode_data(user, mode):
    if mode == "Демо":
        return {
            'trade_balance': user['trade_balance'],
            'withdrawable_balance': user['withdrawable_balance'],
            'total_profit': user['total_profit'],
            'trade_count': user['trade_count'],
            'total_admin_fee_paid': user['total_admin_fee_paid'],
            'last_withdrawal_date': user['last_withdrawal_date'],
            'portfolio': json.loads(user['portfolio']) if user['portfolio'] else get_target_portfolio(),
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
            'portfolio': json.loads(user['real_portfolio']) if user['real_portfolio'] else get_target_portfolio(),
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
        cursor = conn.execute('''
            INSERT INTO withdrawals (user_id, amount, admin_fee, user_receives, wallet_address, status)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, amount, admin_fee, user_receives, wallet_address, 'pending'))
        return cursor.lastrowid

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

# Балансы
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
                st.warning("⚠️ Для реального режима необходимо подключить API ключи бирж. Администратор может добавить их в админ-панели.")
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
        st.markdown('<div class="api-success">✅ Реальный режим активен. API ключи подключены.</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="api-warning">⚠️ РЕАЛЬНЫЙ РЕЖИМ: API ключи не подключены. Администратору необходимо добавить ключи в админ-панели.</div>', unsafe_allow_html=True)

# ====================== ВКЛАДКИ ======================
show_admin_panel = st.session_state.get('logged_in') and is_admin(st.session_state.get('email', ''))

tabs_list = ["📊 Dashboard", "📈 Графики", "🔄 Арбитраж", "📊 Доходность", "📊 Статистика по токенам", "📦 Портфель", "💰 Кошелёк", "📜 История"]
if show_admin_panel:
    tabs_list.append("👑 Админ-панель")

tabs = st.tabs(tabs_list)

# ------------------------------------------------------------
# TAB 1 - Dashboard
with tabs[0]:
    st.subheader("📊 Статус сканирования токенов")
    st.write("### 🪙 Текущие цены на OKX")
    tokens = get_available_tokens()
    for i in range(0, len(tokens), 5):
        cols = st.columns(5)
        for j, asset in enumerate(tokens[i:i+5]):
            with cols[j]:
                price = get_price(st.session_state.exchanges[MAIN_EXCHANGE], asset) if st.session_state.exchanges else None
                if price:
                    st.markdown(f"<div class='token-card'><b>{asset}</b><br><span style='font-size: 18px; color: #00D4FF;'>${price:,.0f}</span></div>", unsafe_allow_html=True)
                else:
                    st.markdown(f"<div class='token-card'><b>{asset}</b><br>❌</div>", unsafe_allow_html=True)
    if st.session_state.bot_running:
        st.info(f"🟢 Бот сканирует **{len(tokens)} токенов** на **{len(connected)} биржах** одновременно. Работает 24/7.")

# ------------------------------------------------------------
# TAB 2 - Графики
with tabs[1]:
    st.subheader("📈 Японские свечи")
    col_a, col_b = st.columns(2)
    selected_asset = col_a.selectbox("Актив", get_available_tokens())
    selected_exchange = col_b.selectbox("Биржа", ALL_EXCHANGES[:5])
    if st.button("🔄 Обновить график", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    if st.session_state.exchanges and selected_exchange in st.session_state.exchanges:
        try:
            df = get_historical_ohlcv(st.session_state.exchanges[selected_exchange], selected_asset)
            if not df.empty:
                fig = go.Figure(data=[go.Candlestick(x=df['timestamp'], open=df['open'], high=df['high'], low=df['low'], close=df['close'])])
                fig.update_layout(title=f"{selected_asset}/USDT на {selected_exchange.upper()}", template="plotly_dark", height=500)
                st.plotly_chart(fig, use_container_width=True)
                st.metric("Текущая цена", f"${df['close'].iloc[-1]:,.2f}")
            else:
                st.warning("Нет данных для графика")
        except Exception as e:
            st.warning(f"Ошибка: {str(e)[:80]}")
    else:
        st.warning("Биржа не подключена")

# ------------------------------------------------------------
# TAB 3 - Арбитраж
with tabs[2]:
    st.subheader("🔍 Найденные арбитражные возможности")
    if st.button("🔄 Обновить", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    opportunities = find_all_arbitrage_opportunities()
    if opportunities:
        st.success(f"Найдено {len(opportunities)} возможностей!")
        for idx, opp in enumerate(opportunities[:10]):
            unique_key = f"{opp['asset']}_{opp['aux_exchange']}_{idx}"
            st.info(f"🎯 {opp['asset']}: OKX ${opp['main_price']:,.0f} → {opp['aux_exchange'].upper()} ${opp['aux_price']:,.0f} | +{opp['profit_usdt']:.2f} USDT")
            if st.button(f"Исполнить {opp['asset']} на {opp['aux_exchange'].upper()}", key=unique_key):
                profit = opp['profit_usdt']
                if is_admin(st.session_state.email):
                    st.session_state.user_data['trade_balance'] += profit
                    st.session_state.user_data['total_profit'] += profit
                    st.session_state.user_data['trade_count'] += 1
                    trade_text = f"✅ {datetime.now().strftime('%H:%M:%S')} | {opp['asset']} | +{profit:.2f} USDT"
                    st.session_state.user_data['history'].append(trade_text)
                    if st.session_state.user_id:
                        add_trade(st.session_state.user_id, st.session_state.current_mode, opp['asset'], 1000, profit, opp['aux_exchange'], MAIN_EXCHANGE)
                        save_user_mode_data(st.session_state.user_id, st.session_state.current_mode, st.session_state.user_data)
                    st.success(f"Сделка исполнена! +{profit:.2f} USDT")
                    st.rerun()
                else:
                    admin_fee = profit * ADMIN_COMMISSION
                    net_profit = profit - admin_fee
                    reinvest_amount = net_profit * REINVEST_SHARE
                    fixed_amount = net_profit * FIXED_SHARE
                    st.session_state.user_data['trade_balance'] += reinvest_amount
                    st.session_state.user_data['withdrawable_balance'] += fixed_amount
                    st.session_state.user_data['total_profit'] += profit
                    st.session_state.user_data['trade_count'] += 1
                    st.session_state.user_data['total_admin_fee_paid'] += admin_fee
                    trade_text = f"✅ {datetime.now().strftime('%H:%M:%S')} | {opp['asset']} | +{profit:.2f} USDT"
                    st.session_state.user_data['history'].append(trade_text)
                    if st.session_state.user_id:
                        add_trade(st.session_state.user_id, st.session_state.current_mode, opp['asset'], 1000, profit, opp['aux_exchange'], MAIN_EXCHANGE)
                        save_user_mode_data(st.session_state.user_id, st.session_state.current_mode, st.session_state.user_data)
                    st.success(f"Сделка исполнена! +{profit:.2f} USDT (админу {admin_fee:.2f}, реинвест {reinvest_amount:.2f}, на вывод {fixed_amount:.2f})")
                    st.rerun()
    else:
        st.info("Арбитражных возможностей не найдено.")

# ------------------------------------------------------------
# TAB 4 - Доходность
with tabs[3]:
    st.subheader("Калькулятор ожидаемой доходности")
    capital = st.number_input("Капитал для арбитража (USDT)", min_value=100.0, value=10000.0, step=1000.0)
    if st.button("Рассчитать", use_container_width=True):
        exp_profit = capital * 0.008
        exp_return = 0.8
        st.markdown(f"""
        <div class="profit-card">
            <b>Ожидаемая дневная доходность:</b><br>
            Прибыль в день: <b style="color: #00FF88;">${exp_profit:.2f}</b><br>
            Доходность: <b style="color: #00FF88;">{exp_return:.2f}%</b> от капитала
        </div>
        """, unsafe_allow_html=True)

# ------------------------------------------------------------
# TAB 5 - Статистика по токенам
with tabs[4]:
    st.subheader("📊 Статистика арбитражных сделок по токенам")
    token_stats = {}
    total_profit_all = 0
    total_trades_all = 0
    for trade in st.session_state.user_data.get('history', []):
        if trade.startswith("✅"):
            try:
                parts = trade.split("|")
                if len(parts) >= 3:
                    token = parts[1].strip()
                    profit = None
                    for part in parts:
                        if "+" in part and "USDT" in part:
                            profit_str = part.split("+")[1].split()[0]
                            profit = float(profit_str)
                            break
                    if profit is not None:
                        if token not in token_stats:
                            token_stats[token] = {'trades': 0, 'profit': 0}
                        token_stats[token]['trades'] += 1
                        token_stats[token]['profit'] += profit
                        total_profit_all += profit
                        total_trades_all += 1
            except:
                pass
    if token_stats:
        stats_data = []
        for token, data in sorted(token_stats.items(), key=lambda x: x[1]['profit'], reverse=True):
            profit_pct = (data['profit'] / total_profit_all * 100) if total_profit_all > 0 else 0
            stats_data.append({
                "Токен": token,
                "Сделок": data['trades'],
                "Прибыль (USDT)": f"{data['profit']:.2f}",
                "% от общей прибыли": f"{profit_pct:.1f}%"
            })
        st.dataframe(pd.DataFrame(stats_data), use_container_width=True, hide_index=True)
        st.subheader("📊 Распределение прибыли по токенам")
        fig_data = [{"Токен": t, "Прибыль": d['profit']} for t, d in token_stats.items()]
        df_fig = pd.DataFrame(fig_data)
        if not df_fig.empty:
            fig = px.pie(df_fig, values='Прибыль', names='Токен', title="Доля прибыли по токенам")
            fig.update_layout(template="plotly_dark", height=450)
            st.plotly_chart(fig, use_container_width=True)
        st.subheader("📊 Прибыль по токенам (USDT)")
        fig2 = px.bar(df_fig, x='Токен', y='Прибыль', title="Прибыль по токенам (USDT)", color='Токен')
        fig2.update_layout(template="plotly_dark", height=450)
        st.plotly_chart(fig2, use_container_width=True)
        st.caption(f"📊 Всего сделок: {total_trades_all} | Общая利润: ${total_profit_all:.2f}")
        if 'HYPE' in token_stats and token_stats['HYPE']['profit'] > total_profit_all * 0.5:
            st.info("💡 На токене HYPE сейчас самые большие спреды. Это нормально.")
    else:
        st.info("Нет данных о сделках.")

# ------------------------------------------------------------
# TAB 6 - Портфель
with tabs[5]:
    st.subheader("📦 Портфель токенов (OKX)")
    total = 0
    portfolio = st.session_state.user_data.get('portfolio', get_target_portfolio())
    for asset, amount in portfolio.items():
        price = get_price(st.session_state.exchanges[MAIN_EXCHANGE], asset) if st.session_state.exchanges else None
        value = amount * price if price else 0
        total += value
        st.write(f"{asset}: {amount:.6f} ≈ ${value:,.2f}")
    st.divider()
    st.metric("💰 Общая стоимость портфеля", f"${total:,.2f}")

# ------------------------------------------------------------
# TAB 7 - Кошелёк (исправленный вывод)
with tabs[6]:
    st.subheader("💰 Кошелёк и вывод средств")
    st.write(f"**Доступно для вывода:** {st.session_state.user_data.get('withdrawable_balance', 0):.2f} USDT")
    st.write(f"**Торговый баланс (реинвест):** {st.session_state.user_data.get('trade_balance', 0):.2f} USDT")
    st.write(f"**Всего комиссий уплачено платформе:** {st.session_state.user_data.get('total_admin_fee_paid', 0):.2f} USDT")
    
    current_weekday = datetime.now().strftime("%A")
    allowed_days = ["Tuesday", "Friday"]
    if current_weekday not in allowed_days:
        st.warning("⏳ Вывод средств возможен только по вторникам и пятницам. Сегодня не день вывода.")
        withdraw_disabled = True
    else:
        withdraw_disabled = False
    
    max_withdraw = st.session_state.user_data.get('withdrawable_balance', 0)
    if max_withdraw >= 10.0:
        withdraw_amount = st.number_input("Сумма вывода (USDT)", min_value=10.0, max_value=max_withdraw, step=10.0, disabled=withdraw_disabled)
        if st.button("📤 Запросить вывод", disabled=withdraw_disabled):
            if withdraw_amount > 0:
                if st.session_state.wallet_address:
                    admin_fee = withdraw_amount * ADMIN_COMMISSION
                    user_receives = withdraw_amount - admin_fee
                    st.info(f"💰 Сумма вывода: {withdraw_amount} USDT\n🏦 Комиссия платформы (22%): {admin_fee:.2f} USDT\n💵 Вы получите: {user_receives:.2f} USDT")
                    if st.button("✅ Подтвердить вывод", key="confirm_withdraw"):
                        create_withdrawal_request(st.session_state.user_id, withdraw_amount, st.session_state.wallet_address)
                        st.session_state.user_data['withdrawable_balance'] -= withdraw_amount
                        save_user_mode_data(st.session_state.user_id, st.session_state.current_mode, st.session_state.user_data)
                        st.success(f"Заявка на вывод {withdraw_amount} USDT отправлена! Комиссия {admin_fee:.2f} USDT, вы получите {user_receives:.2f} USDT.")
                        st.rerun()
                else:
                    st.error("Сначала сохраните адрес кошелька в настройках!")
            else:
                st.error("Введите сумму больше 0")
    else:
        st.warning(f"⚠️ Недостаточно средств для вывода. Доступно: {max_withdraw:.2f} USDT. Минимальная сумма вывода 10 USDT.")
        st.button("📤 Запросить вывод", disabled=True)

    st.divider()
    wallet_input = st.text_input("Адрес кошелька (USDT)", value=st.session_state.wallet_address)
    if st.button("💾 Сохранить адрес кошелька"):
        st.session_state.wallet_address = wallet_input
        if st.session_state.email:
            with get_db() as conn:
                conn.execute("UPDATE users SET wallet_address = ? WHERE email = ?", (wallet_input, st.session_state.email))
        st.success("Адрес сохранён!")

# ------------------------------------------------------------
# TAB 8 - История
with tabs[7]:
    st.subheader("📜 История сделок")
    if st.session_state.user_data.get('history'):
        for trade in reversed(st.session_state.user_data['history'][-50:]):
            st.write(trade)
        if st.button("🗑 Очистить историю"):
            st.session_state.user_data['history'] = []
            if st.session_state.user_id:
                save_user_mode_data(st.session_state.user_id, st.session_state.current_mode, st.session_state.user_data)
            st.rerun()
    else:
        st.info("Нет сделок")

# ------------------------------------------------------------
# АДМИН-ПАНЕЛЬ
if show_admin_panel:
    with tabs[8]:
        st.subheader("👑 Админ-панель управления")
        admin_tab1, admin_tab2, admin_tab3, admin_tab4, admin_tab5 = st.tabs(["👥 Участники", "📊 Токены", "🔐 API ключи", "📜 Все сделки", "💰 Заявки на вывод"])
        
        # ---------- Участники ----------
        with admin_tab1:
            st.write("### 👥 Все участники платформы")
            all_users = get_all_users_for_admin()
            if all_users:
                users_data = []
                for user in all_users:
                    users_data.append({
                        "ID": user['id'],
                        "Email": user['email'],
                        "Имя": user['full_name'],
                        "Страна": user['country'],
                        "Город": user['city'],
                        "Статус": user['registration_status'],
                        "Торговый баланс": f"${user['trade_balance']:.2f}",
                        "Доступно для вывода": f"${user['withdrawable_balance']:.2f}",
                        "Общая прибыль": f"${user['total_profit']:.2f}",
                        "Сделок": user['trade_count'],
                        "Комиссий админу": f"${user['total_admin_fee_paid']:.2f}",
                        "Регистрация": user['created_at'][:10] if user['created_at'] else "",
                        "Одобрен": user['approved_at'][:10] if user['approved_at'] else ""
                    })
                st.dataframe(pd.DataFrame(users_data), use_container_width=True, hide_index=True)
                
                st.divider()
                st.write("### 🔧 Управление пользователем")
                user_options = {f"{user['email']} (ID: {user['id']})": user['id'] for user in all_users}
                selected_user_name = st.selectbox("Выберите пользователя", list(user_options.keys()))
                selected_user_id = user_options[selected_user_name]
                if selected_user_id:
                    user_data = next((u for u in all_users if u['id'] == selected_user_id), None)
                    if user_data:
                        st.write(f"**{user_data['email']}** — {user_data['full_name']} | Статус: {user_data['registration_status']}")
                        col1_ad, col2_ad, col3_ad, col4_ad = st.columns(4)
                        col1_ad.metric("💰 Торговый баланс", f"${user_data['trade_balance']:.2f}")
                        col2_ad.metric("🏦 Доступно для вывода", f"${user_data['withdrawable_balance']:.2f}")
                        col3_ad.metric("📊 Общая прибыль", f"${user_data['total_profit']:.2f}")
                        col4_ad.metric("💸 Комиссий админу", f"${user_data['total_admin_fee_paid']:.2f}")
                        if user_data['registration_status'] == 'pending':
                            if st.button("✅ Одобрить", key=f"approve_{selected_user_id}", use_container_width=True):
                                update_user_status(selected_user_id, 'approved', st.session_state.email)
                                st.success(f"Пользователь {user_data['email']} одобрен!")
                                st.rerun()
            else:
                st.info("Нет зарегистрированных пользователей")
        
        # ---------- Управление токенами ----------
        with admin_tab2:
            st.write("### 📊 Управление токенами на главной бирже")
            st.info("Здесь администратор может изменять список торгуемых токенов и их целевые количества в портфеле.")
            
            current_tokens = get_available_tokens()
            current_portfolio = get_target_portfolio()
            
            st.subheader("📝 Список токенов")
            tokens_input = st.text_input("Список токенов через запятую", value=", ".join(current_tokens))
            if st.button("💾 Сохранить список токенов"):
                new_tokens = [t.strip().upper() for t in tokens_input.split(",") if t.strip()]
                if new_tokens:
                    set_available_tokens(new_tokens)
                    st.success("Список токенов обновлён!")
                    st.rerun()
                else:
                    st.error("Введите хотя бы один токен")
            
            st.subheader("🎯 Целевые количества в портфеле (единицы токенов)")
            new_portfolio = {}
            cols = st.columns(3)
            for i, token in enumerate(current_tokens):
                with cols[i % 3]:
                    current_amount = current_portfolio.get(token, 0.0)
                    new_amount = st.number_input(f"{token} (шт.)", value=float(current_amount), step=0.01, format="%.4f", key=f"admin_token_{token}")
                    new_portfolio[token] = new_amount
            if st.button("💾 Сохранить портфель"):
                set_target_portfolio(new_portfolio)
                st.success("Целевые количества токенов обновлены!")
                # Обновить портфели существующих пользователей (опционально)
                st.info("Примечание: изменения применяются для новых регистраций. Существующие пользователи сохраняют свои портфели.")
        
        # ---------- API ключи ----------
        with admin_tab3:
            st.write("### 🔐 API ключи для реального режима")
            st.info("Ключи хранятся в зашифрованном виде.")
            st.warning("⚠️ Ключи должны иметь права только на торговлю (без вывода)!")
            api_keys = get_all_api_keys()
            for ex in ALL_EXCHANGES:
                with st.expander(f"🔑 {ex.upper()}", expanded=False):
                    current = api_keys.get(ex, {})
                    current_api = decrypt_api_key(current.get('api_key', ''))
                    current_secret = decrypt_api_key(current.get('secret_key', ''))
                    new_api_key = st.text_input(f"API Key ({ex.upper()})", value=current_api, type="password", key=f"api_{ex}")
                    new_secret = st.text_input(f"Secret Key ({ex.upper()})", value=current_secret, type="password", key=f"secret_{ex}")
                    col_test, col_save = st.columns(2)
                    with col_test:
                        if st.button(f"🔍 Проверить {ex.upper()}", key=f"test_{ex}", use_container_width=True):
                            if new_api_key and new_secret:
                                success, msg = check_exchange_connection(ex, new_api_key, new_secret)
                                if success:
                                    st.success(f"✅ {ex.upper()}: подключение успешно!")
                                else:
                                    st.error(f"❌ {ex.upper()}: {msg}")
                            else:
                                st.warning("Введите API ключи для проверки")
                    with col_save:
                        if st.button(f"💾 Сохранить {ex.upper()}", key=f"save_{ex}", use_container_width=True):
                            save_api_key(ex, new_api_key, new_secret, st.session_state.email)
                            st.session_state.api_keys = get_all_api_keys()
                            st.success(f"Ключи для {ex.upper()} сохранены!")
                            st.rerun()
            if st.button("🔄 Проверить все подключения", use_container_width=True):
                st.write("### Результаты проверки:")
                for ex in ALL_EXCHANGES:
                    key_data = st.session_state.api_keys.get(ex, {})
                    api_key = decrypt_api_key(key_data.get('api_key', ''))
                    secret_key = decrypt_api_key(key_data.get('secret_key', ''))
                    if api_key and secret_key:
                        success, msg = check_exchange_connection(ex, api_key, secret_key)
                        if success:
                            st.success(f"✅ {ex.upper()}: {msg}")
                        else:
                            st.error(f"❌ {ex.upper()}: {msg}")
                    else:
                        st.warning(f"⚠️ {ex.upper()}: ключи не добавлены")
        
        # ---------- Все сделки ----------
        with admin_tab4:
            st.write("### 📜 Все сделки всех участников")
            all_trades = get_all_trades(limit=200)
            if all_trades:
                trades_data = []
                for trade in all_trades:
                    trades_data.append({
                        "ID": trade['id'],
                        "Пользователь": trade['email'],
                        "Режим": trade['mode'],
                        "Токен": trade['asset'],
                        "Прибыль": f"${trade['profit']:.2f}",
                        "Время": trade['trade_time']
                    })
                st.dataframe(pd.DataFrame(trades_data), use_container_width=True, hide_index=True)
            else:
                st.info("Нет совершённых сделок")
        
        # ---------- Заявки на вывод ----------
        with admin_tab5:
            st.write("### 💰 Заявки на вывод средств")
            st.info("📅 Вывод осуществляется по вторникам и пятницам.")
            pending_withdrawals = get_pending_withdrawals()
            if pending_withdrawals:
                withdrawals_data = []
                for w in pending_withdrawals:
                    withdrawals_data.append({
                        "ID": w['id'],
                        "Пользователь": w['email'],
                        "Сумма": f"${w['amount']:.2f}",
                        "Комиссия (22%)": f"${w['admin_fee']:.2f}",
                        "К получению": f"${w['user_receives']:.2f}",
                        "Кошелёк": w['wallet_address'][:20] + "..." if len(w['wallet_address']) > 20 else w['wallet_address'],
                        "Дата заявки": w['requested_at']
                    })
                st.dataframe(pd.DataFrame(withdrawals_data), use_container_width=True, hide_index=True)
                for w in pending_withdrawals:
                    col1_w, col2_w = st.columns([3, 1])
                    col1_w.write(f"**{w['email']}** — {w['amount']} USDT (комиссия {w['admin_fee']:.2f}, клиент получит {w['user_receives']:.2f})")
                    if col2_w.button(f"✅ Выполнить", key=f"complete_{w['id']}", use_container_width=True):
                        update_withdrawal_status(w['id'], 'completed', st.session_state.email)
                        st.success(f"Вывод {w['amount']} USDT для {w['email']} выполнен! Комиссия {w['admin_fee']:.2f} USDT зачислена платформе.")
                        st.rerun()
            else:
                st.info("Нет заявок на вывод")

# ====================== АВТОМАТИЧЕСКИЙ АРБИТРАЖ ======================
if st.session_state.bot_running and st.session_state.exchanges:
    time.sleep(8)
    opportunities = find_all_arbitrage_opportunities()
    if opportunities:
        best = opportunities[0]
        profit = best['profit_usdt']
        if profit >= 0.20:
            if is_admin(st.session_state.email):
                st.session_state.user_data['trade_balance'] += profit
                st.session_state.user_data['total_profit'] += profit
                st.session_state.user_data['trade_count'] += 1
                trade_text = f"✅ {datetime.now().strftime('%H:%M:%S')} | {best['asset']} | АВТО-АРБИТРАЖ | +{profit:.2f} USDT"
                st.session_state.user_data['history'].append(trade_text)
                if st.session_state.user_id:
                    add_trade(st.session_state.user_id, st.session_state.current_mode, best['asset'], 1000, profit, best['aux_exchange'], MAIN_EXCHANGE)
                    save_user_mode_data(st.session_state.user_id, st.session_state.current_mode, st.session_state.user_data)
                st.toast(f"🎯 {best['asset']} | +{profit:.2f} USDT", icon="💰")
                st.rerun()
            else:
                admin_fee = profit * ADMIN_COMMISSION
                net_profit = profit - admin_fee
                reinvest_amount = net_profit * REINVEST_SHARE
                fixed_amount = net_profit * FIXED_SHARE
                st.session_state.user_data['trade_balance'] += reinvest_amount
                st.session_state.user_data['withdrawable_balance'] += fixed_amount
                st.session_state.user_data['total_profit'] += profit
                st.session_state.user_data['trade_count'] += 1
                st.session_state.user_data['total_admin_fee_paid'] += admin_fee
                trade_text = f"✅ {datetime.now().strftime('%H:%M:%S')} | {best['asset']} | АВТО-АРБИТРАЖ | +{profit:.2f} USDT (админу {admin_fee:.2f}, реинвест {reinvest_amount:.2f}, вывод {fixed_amount:.2f})"
                st.session_state.user_data['history'].append(trade_text)
                if st.session_state.user_id:
                    add_trade(st.session_state.user_id, st.session_state.current_mode, best['asset'], 1000, profit, best['aux_exchange'], MAIN_EXCHANGE)
                    save_user_mode_data(st.session_state.user_id, st.session_state.current_mode, st.session_state.user_data)
                st.toast(f"🎯 {best['asset']} | +{profit:.2f} USDT (вам в реинвест {reinvest_amount:.2f}, на вывод {fixed_amount:.2f})", icon="💰")
                st.rerun()

st.caption(f"🚀 Сканируется {len(get_available_tokens())} токенов на {len(connected)} биржах | Работает 24/7 | Режим: {st.session_state.current_mode}")
