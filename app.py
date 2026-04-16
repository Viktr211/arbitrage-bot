python
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

st.set_page_config(page_title="Накопительный Арбитраж PRO", layout="wide", page_icon="🚀")

# ====================== СТИЛЬ ======================
st.markdown("""
<style>
    .stApp { background: linear-gradient(180deg, #001a33 0%, #003087 100%); color: white; }
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
</style>
""", unsafe_allow_html=True)

# ====================== КОНФИГУРАЦИЯ ======================
DEFAULT_ASSETS = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "LINK", "SUI", "HYPE"]
MAIN_EXCHANGE = "okx"
AUX_EXCHANGES = ["gateio", "kucoin", "bitget", "bingx", "mexc", "huobi", "poloniex", "hitbtc"]

MIN_SPREAD_PERCENT = 0.005
FEE_PERCENT = 0.10

DEMO_PORTFOLIO = {
    "BTC": 0.013, "ETH": 0.42, "SOL": 11.6, "BNB": 1.63, "XRP": 730,
    "ADA": 4166, "AVAX": 108, "LINK": 113, "SUI": 1098, "HYPE": 23.5
}
DEMO_USDT_RESERVES = 10000

# ====================== КОНФИГУРАЦИЯ АДМИНА ======================
ADMIN_EMAILS = ["cb777899@gmail.com", "admin@arbitrage.com"]

def is_admin(email):
    return email in ADMIN_EMAILS

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
                balance REAL DEFAULT 0,
                total_profit REAL DEFAULT 0,
                trade_count INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                approved_at DATETIME,
                approved_by TEXT
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
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
        
        admin_email = "admin@arbitrage.com"
        admin_exists = conn.execute("SELECT id FROM users WHERE email = ?", (admin_email,)).fetchone()
        if not admin_exists:
            conn.execute('''
                INSERT INTO users (email, password_hash, full_name, registration_status, balance)
                VALUES (?, ?, ?, ?, ?)
            ''', (admin_email, "admin_hash", "Administrator", "approved", 0))

init_db()

# ====================== ФУНКЦИИ БАЗЫ ДАННЫХ ======================
def get_user_by_email(email):
    with get_db() as conn:
        return conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

def get_user_by_id(user_id):
    with get_db() as conn:
        return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

def create_user(email, password_hash, full_name, country, city, phone, wallet_address):
    with get_db() as conn:
        cursor = conn.execute('''
            INSERT INTO users (email, password_hash, full_name, country, city, phone, wallet_address, registration_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (email, password_hash, full_name, country, city, phone, wallet_address, 'pending'))
        return cursor.lastrowid

def approve_user(user_id, admin_email):
    with get_db() as conn:
        conn.execute('''
            UPDATE users SET registration_status = 'approved', approved_at = CURRENT_TIMESTAMP, approved_by = ?
            WHERE id = ?
        ''', (admin_email, user_id))

def reject_user(user_id):
    with get_db() as conn:
        conn.execute("UPDATE users SET registration_status = 'rejected' WHERE id = ?", (user_id,))

def get_pending_users():
    with get_db() as conn:
        return conn.execute("SELECT * FROM users WHERE registration_status = 'pending'").fetchall()

def get_all_users():
    with get_db() as conn:
        return conn.execute("SELECT id, email, full_name, country, city, registration_status, balance, total_profit, trade_count, created_at FROM users").fetchall()

def add_trade(user_id, asset, amount, profit, buy_exchange, sell_exchange):
    with get_db() as conn:
        conn.execute('''
            INSERT INTO trades (user_id, asset, amount, profit, buy_exchange, sell_exchange)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, asset, amount, profit, buy_exchange, sell_exchange))
        conn.execute('''
            UPDATE users SET total_profit = total_profit + ?, trade_count = trade_count + 1, balance = balance + ?
            WHERE id = ?
        ''', (profit, profit, user_id))

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
    with get_db() as conn:
        cursor = conn.execute('''
            INSERT INTO withdrawals (user_id, amount, wallet_address, status)
            VALUES (?, ?, ?, ?)
        ''', (user_id, amount, wallet_address, 'pending'))
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

def get_user_withdrawals(user_id):
    with get_db() as conn:
        return conn.execute('''
            SELECT * FROM withdrawals WHERE user_id = ? ORDER BY requested_at DESC
        ''', (user_id,)).fetchall()

def update_withdrawal_status(withdrawal_id, status, admin_email):
    with get_db() as conn:
        conn.execute('''
            UPDATE withdrawals SET status = ?, processed_at = CURRENT_TIMESTAMP, processed_by = ?
            WHERE id = ?
        ''', (status, admin_email, withdrawal_id))
        if status == 'completed':
            withdrawal = conn.execute("SELECT user_id, amount FROM withdrawals WHERE id = ?", (withdrawal_id,)).fetchone()
            conn.execute("UPDATE users SET balance = balance - ? WHERE id = ?", (withdrawal['amount'], withdrawal['user_id']))

def get_all_users_for_admin():
    with get_db() as conn:
        return conn.execute('''
            SELECT 
                id, email, full_name, country, city, phone,
                registration_status, balance, total_profit, trade_count,
                created_at, approved_at, approved_by
            FROM users 
            ORDER BY created_at DESC
        ''').fetchall()

def get_user_stats(user_id):
    with get_db() as conn:
        trades = conn.execute('''
            SELECT COUNT(*) as count, COALESCE(SUM(profit), 0) as total_profit
            FROM trades WHERE user_id = ?
        ''', (user_id,)).fetchone()
        withdrawals = conn.execute('''
            SELECT COALESCE(SUM(amount), 0) as total_withdrawn
            FROM withdrawals WHERE user_id = ? AND status = 'completed'
        ''', (user_id,)).fetchone()
        pending_withdrawals = conn.execute('''
            SELECT COALESCE(SUM(amount), 0) as total_pending
            FROM withdrawals WHERE user_id = ? AND status = 'pending'
        ''', (user_id,)).fetchone()
        return {
            'trade_count': trades['count'],
            'total_profit': trades['total_profit'],
            'total_withdrawn': withdrawals['total_withdrawn'],
            'pending_withdrawals': pending_withdrawals['total_pending']
        }

def update_user_status(user_id, status, admin_email):
    with get_db() as conn:
        if status == 'approved':
            conn.execute('''
                UPDATE users 
                SET registration_status = ?, approved_at = CURRENT_TIMESTAMP, approved_by = ?
                WHERE id = ?
            ''', (status, admin_email, user_id))
        else:
            conn.execute('''
                UPDATE users SET registration_status = ? WHERE id = ?
            ''', (status, user_id))

def update_user_balance(user_id, new_balance, admin_email):
    with get_db() as conn:
        conn.execute("UPDATE users SET balance = ? WHERE id = ?", (new_balance, user_id))

def delete_user(user_id, admin_email):
    with get_db() as conn:
        trades = conn.execute("SELECT COUNT(*) as count FROM trades WHERE user_id = ?", (user_id,)).fetchone()
        if trades['count'] == 0:
            conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
            return True
        return False

# ====================== ПОДКЛЮЧЕНИЕ К БИРЖАМ ======================
@st.cache_resource
def init_exchanges():
    exchanges = {}
    status = {}
    for ex_name in [MAIN_EXCHANGE] + AUX_EXCHANGES:
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

def find_all_arbitrage_opportunities(record=True):
    opportunities = []
    if not st.session_state.exchanges or MAIN_EXCHANGE not in st.session_state.exchanges:
        return opportunities
    
    main_prices = {}
    for asset in DEFAULT_ASSETS:
        price = get_price(st.session_state.exchanges[MAIN_EXCHANGE], asset)
        if price:
            main_prices[asset] = price
    
    now = datetime.now().isoformat()
    for asset in DEFAULT_ASSETS:
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
                    if net_spread > MIN_SPREAD_PERCENT and profit_usdt >= 0.20:
                        opp = {
                            'asset': asset,
                            'aux_exchange': aux_ex,
                            'main_price': main_price,
                            'aux_price': aux_price,
                            'spread_pct': round(spread_pct, 2),
                            'profit_usdt': profit_usdt,
                            'timestamp': now
                        }
                        opportunities.append(opp)
    return sorted(opportunities, key=lambda x: x['profit_usdt'], reverse=True)

def update_profit_stats(profit):
    today = datetime.now().strftime('%Y-%m-%d')
    week = datetime.now().strftime('%Y-%W')
    month = datetime.now().strftime('%Y-%m')
    if 'daily_profits' not in st.session_state:
        st.session_state.daily_profits = {}
    if 'weekly_profits' not in st.session_state:
        st.session_state.weekly_profits = {}
    if 'monthly_profits' not in st.session_state:
        st.session_state.monthly_profits = {}
    st.session_state.daily_profits[today] = st.session_state.daily_profits.get(today, 0) + profit
    st.session_state.weekly_profits[week] = st.session_state.weekly_profits.get(week, 0) + profit
    st.session_state.monthly_profits[month] = st.session_state.monthly_profits.get(month, 0) + profit

def compute_expected_return(capital_usdt, lookback_days=7):
    return capital_usdt * 0.008, 0.8, 10

# ====================== СЕССИЯ ======================
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'username' not in st.session_state:
    st.session_state.username = None
if 'email' not in st.session_state:
    st.session_state.email = None
if 'wallet_address' not in st.session_state:
    st.session_state.wallet_address = ''
if 'total_profit' not in st.session_state:
    st.session_state.total_profit = 0.0
if 'trade_count' not in st.session_state:
    st.session_state.trade_count = 0
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = DEMO_PORTFOLIO.copy()
if 'usdt_reserves' not in st.session_state:
    st.session_state.usdt_reserves = {ex: DEMO_USDT_RESERVES for ex in AUX_EXCHANGES}
if 'daily_profits' not in st.session_state:
    st.session_state.daily_profits = {}
if 'weekly_profits' not in st.session_state:
    st.session_state.weekly_profits = {}
if 'monthly_profits' not in st.session_state:
    st.session_state.monthly_profits = {}
if 'history' not in st.session_state:
    st.session_state.history = []
if 'exchanges' not in st.session_state:
    st.session_state.exchanges = None
if 'bot_running' not in st.session_state:
    st.session_state.bot_running = False
if 'trade_mode' not in st.session_state:
    st.session_state.trade_mode = "Демо"
if 'exchange_status' not in st.session_state:
    st.session_state.exchange_status = {}

# Инициализация бирж
if st.session_state.exchanges is None:
    with st.spinner("Подключение к биржам..."):
        st.session_state.exchanges, st.session_state.exchange_status = init_exchanges()

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
                        st.error("❌ Пользователь с таким email уже существует!")
                    else:
                        create_user(email, password, username, country, city, phone, wallet)
                        st.success("✅ Регистрация успешна! Ваша заявка отправлена администратору.")
                        st.info("📧 Вы получите уведомление, когда аккаунт будет активирован.")
                else:
                    st.error("❌ Заполните все поля или пароли не совпадают")
    
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
                        st.session_state.total_profit = user['total_profit']
                        st.session_state.trade_count = user['trade_count']
                        st.success(f"✅ Добро пожаловать, {st.session_state.username}!")
                        st.rerun()
                    elif user['registration_status'] == 'pending':
                        st.warning("⏳ Ваша заявка на одобрение ещё не рассмотрена.")
                    else:
                        st.error("❌ Ваша заявка отклонена. Свяжитесь с администратором.")
                else:
                    st.error("❌ Неверный email или пароль")
    
    st.stop()

# ====================== ОСНОВНОЙ ИНТЕРФЕЙС ======================
col_logo, col_status, col_logout = st.columns([3, 1, 1])
with col_logo:
    st.markdown('<h1 class="main-header">🚀 НАКОПИТЕЛЬНЫЙ АРБИТРАЖ PRO</h1>', unsafe_allow_html=True)
with col_status:
    if st.session_state.bot_running:
        st.markdown('<div style="text-align: center;"><span class="status-indicator status-running"></span> <b style="color: #00FF88;">РАБОТАЕТ</b></div>', unsafe_allow_html=True)
    else:
        st.markdown('<div style="text-align: center;"><span class="status-indicator status-stopped"></span> <b style="color: #FF4444;">ОСТАНОВЛЕН</b></div>', unsafe_allow_html=True)
with col_logout:
    if st.button("🚪 Выйти", key="logout"):
        st.session_state.logged_in = False
        st.rerun()

st.markdown(f'<div class="user-info">👤 {st.session_state.username} | 📧 {st.session_state.email}</div>', unsafe_allow_html=True)

connected = [ex.upper() for ex, status in st.session_state.exchange_status.items() if status == "connected"]
st.write(f"🔌 **Биржи:** {', '.join(connected[:8])}" + (f" +{len(connected)-8}" if len(connected) > 8 else ""))
st.write(f"🪙 **Токены:** {', '.join(DEFAULT_ASSETS)} (10 токенов)")
st.divider()

col1, col2 = st.columns(2)
col1.metric("💰 Общая прибыль", f"{st.session_state.total_profit:.2f} USDT")
col2.metric("📊 Сделок", st.session_state.trade_count)

c1, c2, c3, c4 = st.columns(4)
with c1:
    if st.button("▶ СТАРТ", use_container_width=True):
        st.session_state.bot_running = True
        st.rerun()
with c2:
    if st.button("⏸ ПАУЗА", use_container_width=True):
        st.session_state.bot_running = False
        st.rerun()
with c3:
    if st.button("⏹ СТОП", use_container_width=True):
        st.session_state.bot_running = False
        st.rerun()
with c4:
    st.session_state.trade_mode = st.selectbox("Режим", ["Демо", "Реальный"])

# ====================== ВКЛАДКИ ======================
show_admin_panel = st.session_state.get('logged_in') and is_admin(st.session_state.get('email', ''))

tabs_list = ["📊 Dashboard", "📈 Графики", "🔄 Арбитраж", "📊 Доходность", "📦 Портфель", "💰 Кошелёк", "📜 История"]
if show_admin_panel:
    tabs_list.append("👑 Админ-панель")

tabs = st.tabs(tabs_list)
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = tabs[:7]
if show_admin_panel:
    tab8 = tabs[7]

# TAB 1 - Dashboard
with tab1:
    st.subheader("📊 Статус сканирования токенов")
    st.write("### 🪙 Текущие цены на OKX")
    for i in range(0, len(DEFAULT_ASSETS), 5):
        cols = st.columns(5)
        for j, asset in enumerate(DEFAULT_ASSETS[i:i+5]):
            with cols[j]:
                price = get_price(st.session_state.exchanges[MAIN_EXCHANGE], asset) if st.session_state.exchanges and MAIN_EXCHANGE in st.session_state.exchanges else None
                if price:
                    st.markdown(f"<div class='token-card'><b>{asset}</b><br><span style='font-size: 18px; color: #00D4FF;'>${price:,.0f}</span></div>", unsafe_allow_html=True)
                else:
                    st.markdown(f"<div class='token-card'><b>{asset}</b><br>❌</div>", unsafe_allow_html=True)
    if st.session_state.bot_running:
        st.info(f"🟢 Бот сканирует **{len(DEFAULT_ASSETS)} токенов** на **{len(connected)} биржах** одновременно.")

# TAB 2 - Графики
with tab2:
    st.subheader("📈 Японские свечи")
    col_a, col_b = st.columns(2)
    selected_asset = col_a.selectbox("Актив", DEFAULT_ASSETS)
    selected_exchange = col_b.selectbox("Биржа", [MAIN_EXCHANGE] + AUX_EXCHANGES[:5])
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

# TAB 3 - Арбитраж
with tab3:
    st.subheader("🔍 Найденные арбитражные возможности")
    if st.button("🔄 Обновить", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    opportunities = find_all_arbitrage_opportunities()
    if opportunities:
        st.success(f"✅ Найдено {len(opportunities)} возможностей!")
        for idx, opp in enumerate(opportunities[:10]):
            unique_key = f"{opp['asset']}_{opp['aux_exchange']}_{idx}"
            st.info(f"🎯 {opp['asset']}: OKX ${opp['main_price']:,.0f} → {opp['aux_exchange'].upper()} ${opp['aux_price']:,.0f} | +{opp['profit_usdt']:.2f} USDT")
            if st.button(f"Исполнить {opp['asset']} на {opp['aux_exchange'].upper()}", key=unique_key):
                if st.session_state.trade_mode == "Демо":
                    profit = opp['profit_usdt']
                    st.session_state.total_profit += profit
                    st.session_state.trade_count += 1
                    update_profit_stats(profit)
                    if st.session_state.email:
                        user = get_user_by_email(st.session_state.email)
                        if user:
                            add_trade(user['id'], opp['asset'], 1000, profit, opp['aux_exchange'], MAIN_EXCHANGE)
                    trade_text = f"✅ {datetime.now().strftime('%H:%M:%S')} | {opp['asset']} | +{profit:.2f} USDT"
                    st.session_state.history.append(trade_text)
                    st.success(f"✅ Сделка исполнена! +{profit:.2f} USDT")
                    st.rerun()
    else:
        st.info("📊 Арбитражных возможностей не найдено.")

# TAB 4 - Доходность
with tab4:
    st.subheader("📊 Калькулятор ожидаемой доходности")
    capital = st.number_input("💵 Капитал для арбитража (USDT)", min_value=100.0, value=10000.0, step=1000.0)
    if st.button("Рассчитать", use_container_width=True):
        exp_profit, exp_return, avg_opps = compute_expected_return(capital)
        st.markdown(f"""
        <div class="profit-card">
            <b>📊 Ожидаемая дневная доходность:</b><br>
            💰 Прибыль в день: <b style="color: #00FF88;">${exp_profit:.2f}</b><br>
            📈 Доходность: <b style="color: #00FF88;">{exp_return:.2f}%</b> от капитала
        </div>
        """, unsafe_allow_html=True)

# TAB 5 - Портфель
with tab5:
    st.subheader("📦 Портфель токенов (OKX)")
    total = 0
    for asset in DEFAULT_ASSETS:
        amount = st.session_state.portfolio.get(asset, 0)
        price = get_price(st.session_state.exchanges[MAIN_EXCHANGE], asset) if st.session_state.exchanges and MAIN_EXCHANGE in st.session_state.exchanges else None
        value = amount * price if price else 0
        total += value
        st.write(f"{asset}: {amount:.6f} ≈ ${value:,.2f}")
    st.divider()
    st.metric("💰 Общая стоимость портфеля", f"${total:,.2f}")

# TAB 6 - Кошелёк
with tab6:
    st.subheader("💰 Резервы USDT на биржах")
    for ex in AUX_EXCHANGES[:5]:
        st.write(f"{ex.upper()}: {st.session_state.usdt_reserves.get(ex, DEMO_USDT_RESERVES):.0f} USDT")
    st.divider()
    wallet_input = st.text_input("Адрес кошелька", value=st.session_state.wallet_address)
    if st.button("💾 Сохранить"):
        st.session_state.wallet_address = wallet_input
        if st.session_state.email:
            user = get_user_by_email(st.session_state.email)
            if user:
                with get_db() as conn:
                    conn.execute("UPDATE users SET wallet_address = ? WHERE id = ?", (wallet_input, user['id']))
        st.success("Адрес сохранён!")
    withdraw = st.number_input("Сумма вывода (USDT)", min_value=10.0, step=10.0)
    if st.button("📤 Запросить вывод"):
        if st.session_state.wallet_address:
            if st.session_state.email:
                user = get_user_by_email(st.session_state.email)
                if user and user['balance'] >= withdraw:
                    create_withdrawal_request(user['id'], withdraw, st.session_state.wallet_address)
                    st.success(f"✅ Заявка на вывод {withdraw} USDT отправлена!")
                    st.rerun()
                else:
                    st.error("❌ Недостаточно средств!")
            else:
                st.error("❌ Ошибка: пользователь не найден")
        else:
            st.error("❌ Сначала сохраните адрес кошелька!")

# TAB 7 - История
with tab7:
    st.subheader("📜 История сделок")
    if st.session_state.history:
        for trade in reversed(st.session_state.history[-50:]):
            st.write(trade)
        if st.button("🗑 Очистить историю"):
            st.session_state.history = []
            st.rerun()
    else:
        st.info("Нет сделок")

# ====================== TAB 8: АДМИН-ПАНЕЛЬ ======================
if show_admin_panel:
    with tab8:
        st.subheader("👑 Админ-панель управления")
        
        admin_tab1, admin_tab2, admin_tab3, admin_tab4 = st.tabs(["👥 Участники", "📜 Все сделки", "💰 Заявки на вывод", "⚙ Настройки"])
        
        with admin_tab1:
            st.write("### 👥 Все участники платформы")
            all_users = get_all_users_for_admin()
            if all_users:
                users_data = []
                for user in all_users:
                    stats = get_user_stats(user['id'])
                    users_data.append({
                        "ID": user['id'],
                        "Email": user['email'],
                        "Имя": user['full_name'],
                        "Страна": user['country'],
                        "Город": user['city'],
                        "Статус": user['registration_status'],
                        "Баланс": f"${user['balance']:.2f}",
                        "Прибыль": f"${user['total_profit']:.2f}",
                        "Сделок": user['trade_count'],
                        "Выведено": f"${stats['total_withdrawn']:.2f}",
                        "В очереди": f"${stats['pending_withdrawals']:.2f}",
                        "Регистрация": user['created_at'][:10] if user['created_at'] else "",
                        "Одобрен": user['approved_at'][:10] if user['approved_at'] else "",
                        "Кто одобрил": user['approved_by'] or ""
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
                        st.write(f"**{user_data['email']}** — {user_data['full_name']}")
                        
                        col1_admin, col2_admin, col3_admin, col4_admin = st.columns(4)
                        col1_admin.metric("💰 Баланс", f"${user_data['balance']:.2f}")
                        col2_admin.metric("📊 Прибыль", f"${user_data['total_profit']                         col2_admin.metric("📊 Прибыль", f"${user_data['total_profit']:.2f}")
                        col3_admin.metric("🔄 Сделок", user_data['trade_count'])
                        status_color = "🟢" if user_data['registration_status'] == 'approved' else "🟡" if user_data['registration_status'] == 'pending' else "🔴"
                        col4_admin.metric("📝 Статус", f"{status_color} {user_data['registration_status']}")
                        
                        st.write("#### Действия")
                        action_col1, action_col2, action_col3, action_col4 = st.columns(4)
                        
                        with action_col1:
                            if user_data['registration_status'] == 'pending':
                                if st.button("✅ Одобрить", key=f"approve_{selected_user_id}", use_container_width=True):
                                    update_user_status(selected_user_id, 'approved', st.session_state.email)
                                    st.success(f"Пользователь {user_data['email']} одобрен!")
                                    st.rerun()
                            else:
                                st.button("✅ Одобрено", disabled=True, use_container_width=True)
                        
                        with action_col2:
                            if user_data['registration_status'] == 'pending':
                                if st.button("❌ Отклонить", key=f"reject_{selected_user_id}", use_container_width=True):
                                    update_user_status(selected_user_id, 'rejected', st.session_state.email)
                                    st.warning(f"Пользователь {user_data['email']} отклонён!")
                                    st.rerun()
                            else:
                                st.button("❌ Отклонить", disabled=True, use_container_width=True)
                        
                        with action_col3:
                            new_balance = st.number_input("Новый баланс", value=float(user_data['balance']), step=100.0, key=f"balance_{selected_user_id}")
                            if st.button("💾 Сохранить баланс", key=f"save_balance_{selected_user_id}", use_container_width=True):
                                update_user_balance(selected_user_id, new_balance, st.session_state.email)
                                st.success(f"Баланс пользователя {user_data['email']} обновлён!")
                                st.rerun()
                        
                        with action_col4:
                            if st.button("🗑 Удалить", key=f"delete_{selected_user_id}", use_container_width=True):
                                if delete_user(selected_user_id, st.session_state.email):
                                    st.success(f"Пользователь {user_data['email']} удалён!")
                                    st.rerun()
                                else:
                                    st.error("Нельзя удалить пользователя с историей сделок!")
            else:
                st.info("Нет зарегистрированных пользователей")
        
        with admin_tab2:
            st.write("### 📜 Все сделки всех участников")
            all_trades = get_all_trades(limit=200)
            if all_trades:
                trades_data = []
                for trade in all_trades:
                    trades_data.append({
                        "ID": trade['id'],
                        "Пользователь": trade['email'],
                        "Токен": trade['asset'],
                        "Сумма": f"${trade['amount']:.2f}",
                        "Прибыль": f"${trade['profit']:.2f}",
                        "Покупка": trade['buy_exchange'],
                        "Продажа": trade['sell_exchange'],
                        "Время": trade['trade_time']
                    })
                st.dataframe(pd.DataFrame(trades_data), use_container_width=True, hide_index=True)
            else:
                st.info("Нет совершённых сделок")
        
        with admin_tab3:
            st.write("### 💰 Заявки на вывод средств")
            st.info("📅 Вывод средств осуществляется по вторникам и пятницам.")
            
            pending_withdrawals = get_pending_withdrawals()
            if pending_withdrawals:
                withdrawals_data = []
                for w in pending_withdrawals:
                    withdrawals_data.append({
                        "ID": w['id'],
                        "Пользователь": w['email'],
                        "Сумма": f"${w['amount']:.2f}",
                        "Кошелёк": w['wallet_address'][:20] + "..." if len(w['wallet_address']) > 20 else w['wallet_address'],
                        "Дата заявки": w['requested_at']
                    })
                st.dataframe(pd.DataFrame(withdrawals_data), use_container_width=True, hide_index=True)
                
                st.write("#### Обработка заявок")
                for w in pending_withdrawals:
                    col1_w, col2_w, col3_w = st.columns([2, 1, 1])
                    col1_w.write(f"**{w['email']}** — {w['amount']} USDT")
                    if col2_w.button(f"✅ Выполнить", key=f"complete_{w['id']}", use_container_width=True):
                        update_withdrawal_status(w['id'], 'completed', st.session_state.email)
                        st.success(f"Вывод {w['amount']} USDT для {w['email']} выполнен!")
                        st.rerun()
                    if col3_w.button(f"🔴 Заблокировать", key=f"block_{w['id']}", use_container_width=True):
                        update_withdrawal_status(w['id'], 'blocked', st.session_state.email)
                        st.warning(f"Вывод {w['amount']} USDT для {w['email']} заблокирован!")
                        st.rerun()
            else:
                st.info("Нет заявок на вывод")
        
        with admin_tab4:
            st.write("### ⚙ Настройки платформы")
            st.info("Здесь будут глобальные настройки системы.")
            
            st.write("#### 📅 Дни вывода средств")
            withdrawal_days = st.multiselect(
                "Выберите дни для обработки выводов",
                ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"],
                default=["Вторник", "Пятница"]
            )
            if st.button("💾 Сохранить настройки выводов", use_container_width=True):
                st.success("Настройки сохранены!")
            
            st.write("#### 💸 Комиссии")
            col_fee1, col_fee2 = st.columns(2)
            with col_fee1:
                platform_fee = st.number_input("Комиссия платформы (%)", min_value=0.0, max_value=50.0, value=20.0, step=1.0)
            with col_fee2:
                withdrawal_fee = st.number_input("Комиссия за вывод USDT", min_value=0.0, max_value=10.0, value=0.5, step=0.1)
            
            if st.button("💾 Сохранить комиссии", use_container_width=True):
                st.success("Комиссии сохранены!")

# ====================== АВТОМАТИЧЕСКИЙ АРБИТРАЖ ======================
if st.session_state.bot_running and st.session_state.exchanges:
    time.sleep(8)
    opportunities = find_all_arbitrage_opportunities()
    if opportunities:
        best = opportunities[0]
        profit = best['profit_usdt']
        if profit >= 0.30:
            st.session_state.total_profit += profit
            st.session_state.trade_count += 1
            update_profit_stats(profit)
            
            if st.session_state.email:
                user = get_user_by_email(st.session_state.email)
                if user:
                    add_trade(user['id'], best['asset'], 1000, profit, best['aux_exchange'], MAIN_EXCHANGE)
            
            trade_text = f"✅ {datetime.now().strftime('%H:%M:%S')} | {best['asset']} | АВТО-АРБИТРАЖ | +{profit:.2f} USDT"
            st.session_state.history.append(trade_text)
            st.toast(f"🎯 {best['asset']} | +{profit:.2f} USDT", icon="💰")
            st.rerun()

st.caption(f"🚀 Сканируется {len(DEFAULT_ASSETS)} токенов на {len(connected)} биржах | Работает 24/7 | v2.0 с админ-панелью")
