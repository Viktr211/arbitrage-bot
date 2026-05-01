import streamlit as st
import time
import json
import ccxt
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import hashlib
import base64
from supabase import create_client, Client
import requests
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="Накопительный арбитражный бот | АВТО", layout="wide", page_icon="🔄", initial_sidebar_state="collapsed")

# ---------- SUPABASE ----------
SUPABASE_URL = st.secrets.get("SUPABASE_URL")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY")
if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("❌ Нет SUPABASE_URL / SUPABASE_KEY в Secrets")
    st.stop()
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ---------- TELEGRAM ----------
TELEGRAM_BOT_TOKEN = st.secrets.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = st.secrets.get("TELEGRAM_CHAT_ID")
def send_telegram(msg):
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        try:
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                          json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"}, timeout=5)
        except:
            pass

# ---------- СТИЛИ ----------
st.markdown("""
<style>
    .stApp { background: linear-gradient(180deg, #001a33 0%, #003087 100%) !important; color: white; }
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
    .stTabs [data-baseweb="tab-list"] { flex-wrap: wrap !important; gap: 4px; }
    .api-warning { background: #ffaa0022; border-left: 4px solid #FFAA00; padding: 10px; border-radius: 8px; margin: 10px 0; }
    .api-success { background: #00ff8822; border-left: 4px solid #00FF88; padding: 10px; border-radius: 8px; margin: 10px 0; }
</style>
""", unsafe_allow_html=True)

# ---------- КОНСТАНТЫ ----------
EXCHANGES = ["kucoin", "hitbtc", "okx", "bingx", "bitget"]
DEFAULT_ASSETS = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "LINK", "SUI", "HYPE", "TON"]
DEFAULT_PORTFOLIO = {
    "BTC": 0.08, "ETH": 1.5, "SOL": 25.0, "BNB": 4.0, "XRP": 1800.0,
    "ADA": 4000.0, "AVAX": 40.0, "LINK": 70.0, "SUI": 400.0, "HYPE": 50.0, "TON": 80.0
}
DEMO_USDT_PER_EXCHANGE = 5000
ADMIN_COMMISSION = 0.22
REINVEST_SHARE = 0.50
FIXED_SHARE = 0.50
ADMIN_EMAILS = ["cb777899@gmail.com", "admin@arbitrage.com"]

DEFAULT_THRESHOLDS = {
    "min_spread_percent": 0.0005,
    "fee_percent": 0.1,
    "slippage_percent": 0.2,
    "min_24h_volume_usdt": 0,
    "max_withdrawal_fee_percent": 30
}

SCAN_INTERVAL = 3          # секунд между авто-проверками
MIN_AUTO_PROFIT = 0.01     # минимальная прибыль для авто-сделки

def is_admin(email):
    return email in ADMIN_EMAILS

# ---------- ВСЕ ФУНКЦИИ SUPABASE (полные, как в предыдущем коде) ----------
# Для краткости я их не повторяю, но вы вставите сюда свои функции 
# (get_user_by_email, create_user, load_demo_balances, save_demo_balances, ...,
# init_exchanges, get_price, find_all_arbitrage_opportunities, execute_trade).
# Убедитесь, что функции execute_trade и find_all_arbitrage_opportunities работают.

# ---------- СЕССИЯ ----------
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = None
    st.session_state.email = None
    st.session_state.wallet_address = ''
    st.session_state.exchanges = None
    st.session_state.auto_trade_enabled = False
    st.session_state.exchange_status = {}
    st.session_state.current_mode = "Демо"
    st.session_state.user_id = None
    st.session_state.api_keys = {}
    st.session_state.chat_unread = 0
    st.session_state.user_balances = {}
    st.session_state.user_history = []
    st.session_state.user_stats = {}
    st.session_state.total_profit = 0
    st.session_state.trade_count = 0
    st.session_state.total_admin_fee_paid = 0
    st.session_state.withdrawable_balance = 0
    st.session_state.last_withdrawal_date = None

if st.session_state.exchanges is None:
    with st.spinner("Подключение к биржам..."):
        st.session_state.exchanges, st.session_state.exchange_status = init_exchanges()
        st.session_state.api_keys = get_all_api_keys()

thresholds = get_thresholds()

# ---------- РЕГИСТРАЦИЯ / ВХОД ----------
if not st.session_state.logged_in:
    st.markdown('<h1 class="main-header">🔄 Накопительный арбитражный бот | АВТО</h1>', unsafe_allow_html=True)
    tab_reg, tab_login = st.tabs(["📝 Регистрация","🔑 Вход"])
    with tab_reg:
        with st.form("register_form"):
            username = st.text_input("Имя")
            email = st.text_input("Email")
            country = st.text_input("Страна")
            city = st.text_input("Город")
            phone = st.text_input("Телефон")
            wallet = st.text_input("Адрес USDT")
            pwd = st.text_input("Пароль", type="password")
            pwd2 = st.text_input("Повтор пароля", type="password")
            if st.form_submit_button("Зарегистрироваться", use_container_width=True):
                if username and email and wallet and pwd and pwd == pwd2:
                    if get_user_by_email(email):
                        st.error("Email уже существует")
                    else:
                        create_user(email, pwd, username, country, city, phone, wallet)
                        st.success("Регистрация успешна! Теперь вы можете войти.")
                else:
                    st.error("Заполните все поля или пароли не совпадают")
    with tab_login:
        with st.form("login_form"):
            email = st.text_input("Email")
            pwd = st.text_input("Пароль", type="password")
            if st.form_submit_button("Войти", use_container_width=True):
                user = get_user_by_email(email)
                if user and user['password_hash'] == pwd:
                    st.session_state.logged_in = True
                    st.session_state.username = user['full_name']
                    st.session_state.email = user['email']
                    st.session_state.wallet_address = user.get('wallet_address', '')
                    st.session_state.user_id = user['id']
                    st.session_state.user_balances = ensure_demo_balances(user['id'])
                    st.session_state.user_history = load_demo_history(user['id'])
                    st.session_state.user_stats = load_demo_stats(user['id'])
                    st.session_state.total_profit = user.get('total_profit', 0)
                    st.session_state.trade_count = user.get('trade_count', 0)
                    st.session_state.total_admin_fee_paid = user.get('total_admin_fee_paid', 0)
                    st.session_state.withdrawable_balance = user.get('withdrawable_balance', 0)
                    st.session_state.last_withdrawal_date = user.get('last_withdrawal_date')
                    st.session_state.chat_unread = get_unread_count(user['id'])
                    st.success(f"Добро пожаловать, {st.session_state.username}!")
                    st.rerun()
                else:
                    st.error("Неверный email или пароль")
    st.stop()

# ---------- АВТО-СДЕЛКИ (при каждом автообновлении) ----------
if st.session_state.auto_trade_enabled:
    # Автообновление каждые SCAN_INTERVAL секунд
    st_autorefresh(interval=SCAN_INTERVAL * 1000, key="auto_refresh")
    # Выполняем лучшую сделку
    if st.session_state.exchanges and st.session_state.user_id:
        opportunities = find_all_arbitrage_opportunities(st.session_state.exchanges, thresholds)
        if opportunities:
            best = opportunities[0]
            if best['net_profit'] >= MIN_AUTO_PROFIT:
                profit = execute_trade(best, st.session_state.user_id, st.session_state.current_mode)
                if profit > 0:
                    # Запись в лог (в session_state)
                    if 'auto_trade_log' not in st.session_state:
                        st.session_state.auto_trade_log = []
                    st.session_state.auto_trade_log.append(f"{datetime.now().strftime('%H:%M:%S')} {best['asset']} {best['buy_exchange']}→{best['sell_exchange']} +{profit:.2f}")
                    # Обновляем данные в session_state (они уже обновлены внутри execute_trade, но перечитаем из БД)
                    st.session_state.user_balances = ensure_demo_balances(st.session_state.user_id)
                    st.session_state.user_history = load_demo_history(st.session_state.user_id)
                    user_data = supabase.table('users').select('total_profit,trade_count,withdrawable_balance').eq('id', st.session_state.user_id).execute().data[0]
                    st.session_state.total_profit = user_data['total_profit']
                    st.session_state.trade_count = user_data['trade_count']
                    send_telegram(f"🤖 {best['asset']} {best['buy_exchange']}→{best['sell_exchange']} +{profit:.2f} USDT")

# ---------- ОСНОВНОЙ ИНТЕРФЕЙС ----------
col_logo, col_status, col_logout = st.columns([3, 1, 1])
with col_logo:
    st.markdown('<h1 class="main-header">🔄 Накопительный арбитражный бот | АВТО</h1>', unsafe_allow_html=True)
with col_status:
    if st.session_state.auto_trade_enabled:
        st.markdown('<div><span class="status-indicator status-running"></span> <b>АВТО-ТОРГОВЛЯ АКТИВНА</b></div>', unsafe_allow_html=True)
    else:
        st.markdown('<div><span class="status-indicator status-stopped"></span> <b>ОСТАНОВЛЕН</b></div>', unsafe_allow_html=True)
with col_logout:
    if st.button("🚪 Выйти"):
        save_demo_balances(st.session_state.user_id, st.session_state.user_balances)
        save_demo_history(st.session_state.user_id, st.session_state.user_history)
        st.session_state.logged_in = False
        st.rerun()

st.markdown(f'<div class="user-info">👤 {st.session_state.username} | 📧 {st.session_state.email}</div>', unsafe_allow_html=True)
connected = [ex.upper() for ex, sts in st.session_state.exchange_status.items() if "connected" in sts]
st.write(f"🔌 **Биржи:** {', '.join([ex.upper() for ex in EXCHANGES])}")
st.write(f"🪙 **Токены:** {', '.join(get_available_tokens())}")
st.divider()

total_usdt = sum(bal.get('USDT', 0) for bal in st.session_state.user_balances.values())
total_portfolio_value = 0
for ex, bal in st.session_state.user_balances.items():
    for asset, amount in bal.get('portfolio', {}).items():
        price = get_price(ex, asset)
        if price:
            total_portfolio_value += amount * price
col1, col2, col3 = st.columns(3)
col1.metric("💰 Всего USDT", f"{total_usdt:.2f}")
col2.metric("📦 Стоимость портфеля", f"{total_portfolio_value:.2f}")
col3.metric("📊 Всего сделок", st.session_state.trade_count)

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.markdown('<div class="green-button">', unsafe_allow_html=True)
    if st.button("▶ СТАРТ (авто)", use_container_width=True):
        st.session_state.auto_trade_enabled = True
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)
with c2:
    st.markdown('<div class="yellow-button">', unsafe_allow_html=True)
    if st.button("⏸ ПАУЗА (авто)", use_container_width=True):
        st.session_state.auto_trade_enabled = False
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)
with c3:
    st.markdown('<div class="red-button">', unsafe_allow_html=True)
    if st.button("⏹ СТОП", use_container_width=True):
        st.session_state.auto_trade_enabled = False
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)
with c4:
    new_mode = st.selectbox("Режим", ["Демо", "Реальный"], index=0 if st.session_state.current_mode == "Демо" else 1)
    if new_mode != st.session_state.current_mode:
        st.session_state.current_mode = new_mode
        st.rerun()

if st.button("🔄 Обновить данные", use_container_width=True):
    st.session_state.user_balances = ensure_demo_balances(st.session_state.user_id)
    st.session_state.user_history = load_demo_history(st.session_state.user_id)
    st.session_state.user_stats = load_demo_stats(st.session_state.user_id)
    user_data = supabase.table('users').select('total_profit,trade_count,withdrawable_balance').eq('id', st.session_state.user_id).execute().data[0]
    st.session_state.total_profit = user_data['total_profit']
    st.session_state.trade_count = user_data['trade_count']
    st.session_state.withdrawable_balance = user_data['withdrawable_balance']
    st.rerun()

with st.expander("📋 Лог авто-сделок (последние события)"):
    if 'auto_trade_log' in st.session_state and st.session_state.auto_trade_log:
        for log in st.session_state.auto_trade_log[-30:]:
            st.text(log)
    else:
        st.info("Нет сообщений")

show_admin = is_admin(st.session_state.email)
tabs_list = ["📊 Dashboard", "📈 Графики", "🔄 Арбитраж", "📊 Статистика", "📈 Доходность по дням", "💼 Балансы", "💰 Вывод", "📜 История", "👤 Кабинет", "💬 Чат"]
if show_admin:
    tabs_list.append("👑 Админ-панель")
tabs = st.tabs(tabs_list)

# ---------- ВЫ МОЖЕТЕ ВСТАВИТЬ СВОИ ВКЛАДКИ (они не изменились) ----------
# Для краткости я приведу только пример вкладки Арбитраж (упрощённой, без ручных кнопок)
with tabs[2]:
    st.subheader("🔍 Арбитражные возможности (авто-торговля активна)")
    opps = find_all_arbitrage_opportunities(st.session_state.exchanges, thresholds)
    if opps:
        st.success(f"Найдено {len(opps)} возможностей")
        for opp in opps[:10]:
            st.info(f"🎯 {opp['asset']}: купить на {opp['buy_exchange'].upper()} ${opp['buy_price']:.2f} → продать на {opp['sell_exchange'].upper()} ${opp['sell_price']:.2f} | +{opp['profit_usdt']:.2f} USDT (чистая: {opp['net_profit']:.2f})")
    else:
        st.info("Арбитражных возможностей не найдено.")

# Остальные вкладки (Dashboard, Графики, Статистика, Доходность, Балансы, Вывод, История, Кабинет, Чат, Админка) оставляем как в предыдущем коде.
# В целях экономии места я их здесь не повторяю, но вы вставляете свои рабочие копии.

st.caption(f"🚀 Сканируется {len(get_available_tokens())} токенов на {len(EXCHANGES)} биржах | Авто-интервал: {SCAN_INTERVAL} сек | Режим: {st.session_state.current_mode}")
