import streamlit as st
import time
import random
import json
import ccxt
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime
import os
import threading

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
</style>
""", unsafe_allow_html=True)

# ====================== КОНФИГУРАЦИЯ ======================
DEFAULT_ASSETS = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "LINK", "SUI", "HYPE"]
MAIN_EXCHANGE = "okx"

# Вспомогательные биржи (10 бирж, без Binance и Bybit)
AUX_EXCHANGES = ["gateio", "kucoin", "bitget", "bingx", "mexc", "huobi", "poloniex", "hitbtc"]

# Параметры арбитража
MIN_SPREAD_PERCENT = 0.005
FEE_PERCENT = 0.10

# Демо-портфель (~1000 USDT)
DEMO_PORTFOLIO = {
    "BTC": 0.013, "ETH": 0.42, "SOL": 11.6, "BNB": 1.63, "XRP": 730,
    "ADA": 4166, "AVAX": 108, "LINK": 113, "SUI": 1098, "HYPE": 23.5
}
DEMO_USDT_RESERVES = 10000

# ====================== ФАЙЛЫ ======================
USER_DATA_FILE = "user_data_v8.json"
HISTORY_FILE = "history_v8.json"

def load_user_data():
    if os.path.exists(USER_DATA_FILE):
        try:
            with open(USER_DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_user_data():
    data = {
        'username': st.session_state.get('username'),
        'email': st.session_state.get('email'),
        'wallet_address': st.session_state.get('wallet_address', ''),
        'total_profit': st.session_state.get('total_profit', 0.0),
        'trade_count': st.session_state.get('trade_count', 0),
        'portfolio': st.session_state.get('portfolio', {}),
        'usdt_reserves': st.session_state.get('usdt_reserves', {}),
        'daily_profits': st.session_state.get('daily_profits', {}),
        'weekly_profits': st.session_state.get('weekly_profits', {}),
        'monthly_profits': st.session_state.get('monthly_profits', {}),
        'is_registered': True
    }
    with open(USER_DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return []
    return []

def save_history():
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(st.session_state.history[-500:], f, ensure_ascii=False, indent=4)

# ====================== СЕССИЯ ======================
saved_user = load_user_data()
saved_history = load_history()

for key, default in [
    ('logged_in', saved_user.get('logged_in', False)),
    ('username', saved_user.get('username', None)),
    ('email', saved_user.get('email', None)),
    ('wallet_address', saved_user.get('wallet_address', '')),
    ('total_profit', saved_user.get('total_profit', 0.0)),
    ('trade_count', saved_user.get('trade_count', 0)),
    ('portfolio', saved_user.get('portfolio', {asset: DEMO_PORTFOLIO.get(asset, 0.0) for asset in DEFAULT_ASSETS})),
    ('usdt_reserves', saved_user.get('usdt_reserves', {ex: DEMO_USDT_RESERVES for ex in AUX_EXCHANGES})),
    ('daily_profits', saved_user.get('daily_profits', {})),
    ('weekly_profits', saved_user.get('weekly_profits', {})),
    ('monthly_profits', saved_user.get('monthly_profits', {})),
    ('history', saved_history),
    ('exchanges', None),
    ('bot_running', False),
    ('trade_mode', "Демо"),
    ('exchange_status', {}),
    ('is_first_time', not saved_user.get('is_registered', False)),
    ('last_arbitrage_check', datetime.now())
]:
    if key not in st.session_state:
        st.session_state[key] = default

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

# ====================== ФУНКЦИИ ======================
@st.cache_data(ttl=5)
def get_price_cached(exchange, symbol):
    try:
        ticker = exchange.fetch_ticker(f"{symbol}/USDT")
        return ticker['last']
    except:
        return None

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

def find_arbitrage_opportunities():
    opportunities = []
    if not st.session_state.exchanges or MAIN_EXCHANGE not in st.session_state.exchanges:
        return opportunities
    
    for asset in DEFAULT_ASSETS:
        main_price = get_price(st.session_state.exchanges[MAIN_EXCHANGE], asset)
        if not main_price:
            continue
        
        for aux_ex in AUX_EXCHANGES:
            if aux_ex in st.session_state.exchanges and st.session_state.exchanges[aux_ex]:
                aux_price = get_price(st.session_state.exchanges[aux_ex], asset)
                if aux_price and aux_price < main_price:
                    spread_pct = (main_price - aux_price) / aux_price * 100
                    net_spread = spread_pct - FEE_PERCENT
                    profit_usdt = round((main_price - aux_price) - (main_price * 0.0008) - (aux_price * 0.0008), 2)
                    if net_spread > MIN_SPREAD_PERCENT and profit_usdt >= 0.20:
                        opportunities.append({
                            'asset': asset, 'aux_exchange': aux_ex,
                            'main_price': main_price, 'aux_price': aux_price,
                            'spread_pct': round(spread_pct, 2), 'profit_usdt': profit_usdt
                        })
    return sorted(opportunities, key=lambda x: x['profit_usdt'], reverse=True)

def update_profit_stats(profit):
    today = datetime.now().strftime('%Y-%m-%d')
    week = datetime.now().strftime('%Y-%W')
    month = datetime.now().strftime('%Y-%m')
    st.session_state.daily_profits[today] = st.session_state.daily_profits.get(today, 0) + profit
    st.session_state.weekly_profits[week] = st.session_state.weekly_profits.get(week, 0) + profit
    st.session_state.monthly_profits[month] = st.session_state.monthly_profits.get(month, 0) + profit

# ====================== ИНИЦИАЛИЗАЦИЯ БИРЖ ======================
if st.session_state.exchanges is None:
    with st.spinner("Подключение к биржам..."):
        st.session_state.exchanges, st.session_state.exchange_status = init_exchanges()

# ====================== РЕГИСТРАЦИЯ / ВХОД ======================
if not st.session_state.logged_in:
    st.markdown('<h1 class="main-header">🚀 НАКОПИТЕЛЬНЫЙ АРБИТРАЖ PRO</h1>', unsafe_allow_html=True)
    
    if not st.session_state.is_first_time:
        with st.form("login_form"):
            st.subheader("🔑 Вход в аккаунт")
            email = st.text_input("Email")
            password = st.text_input("Пароль", type="password")
            if st.form_submit_button("Войти", use_container_width=True):
                saved = load_user_data()
                if saved.get('email') == email:
                    for k in ['username', 'email', 'wallet_address', 'total_profit', 'trade_count', 'portfolio', 'usdt_reserves']:
                        if k in saved:
                            st.session_state[k] = saved[k]
                    st.session_state.logged_in = True
                    st.session_state.is_first_time = False
                    st.success(f"Добро пожаловать, {st.session_state.username}!")
                    st.rerun()
                else:
                    st.error("Неверный email или пароль")
    else:
        tab_reg, tab_login = st.tabs(["📝 Регистрация", "🔑 Вход"])
        with tab_reg:
            with st.form("register_form"):
                username = st.text_input("Имя пользователя")
                email = st.text_input("Email")
                wallet = st.text_input("Адрес кошелька")
                password = st.text_input("Пароль", type="password")
                confirm = st.text_input("Подтвердите пароль", type="password")
                if st.form_submit_button("Зарегистрироваться"):
                    if username and email and wallet and password and password == confirm:
                        st.session_state.logged_in = True
                        st.session_state.username = username
                        st.session_state.email = email
                        st.session_state.wallet_address = wallet
                        st.session_state.is_first_time = False
                        save_user_data()
                        st.success("Регистрация успешна!")
                        st.rerun()
                    else:
                        st.error("Заполните все поля")
        with tab_login:
            with st.form("login_form"):
                email = st.text_input("Email")
                password = st.text_input("Пароль", type="password")
                if st.form_submit_button("Войти"):
                    saved = load_user_data()
                    if saved.get('email') == email:
                        for k in ['username', 'email', 'wallet_address']:
                            if k in saved:
                                st.session_state[k] = saved[k]
                        st.session_state.logged_in = True
                        st.session_state.is_first_time = False
                        st.rerun()
                    else:
                        st.error("Неверный email")
    st.stop()

# ====================== ОСНОВНОЙ ИНТЕРФЕЙС ======================
col_logo, col_status = st.columns([4, 1])
with col_logo:
    st.markdown('<h1 class="main-header">🚀 НАКОПИТЕЛЬНЫЙ АРБИТРАЖ PRO</h1>', unsafe_allow_html=True)
with col_status:
    if st.session_state.bot_running:
        st.markdown('<div style="text-align: right;"><span class="status-indicator status-running"></span> <b style="color: #00FF88;">ПОИСК</b></div>', unsafe_allow_html=True)
    else:
        st.markdown('<div style="text-align: right;"><span class="status-indicator status-stopped"></span> <b style="color: #FF4444;">СТОП</b></div>', unsafe_allow_html=True)

st.markdown(f'<div class="user-info">👤 {st.session_state.username} | 📧 {st.session_state.email}</div>', unsafe_allow_html=True)

if st.button("🚪 Выйти"):
    st.session_state.logged_in = False
    st.rerun()

# Биржи
st.write("🔌 **Биржи:** " + ", ".join([f"✅ {ex.upper()}" if st.session_state.exchange_status.get(ex) == "connected" else f"❌ {ex.upper()}" for ex in [MAIN_EXCHANGE] + AUX_EXCHANGES[:6]]) + f" +{len(AUX_EXCHANGES)-6}")
st.divider()

col1, col2 = st.columns(2)
col1.metric("💰 Прибыль", f"{st.session_state.total_profit:.2f} USDT")
col2.metric("📊 Сделок", st.session_state.trade_count)

c1, c2, c3, c4 = st.columns(4)
if c1.button("▶ СТАРТ", use_container_width=True):
    st.session_state.bot_running = True
    st.rerun()
if c2.button("⏸ ПАУЗА", use_container_width=True):
    st.session_state.bot_running = False
    st.rerun()
if c3.button("⏹ СТОП", use_container_width=True):
    st.session_state.bot_running = False
    st.rerun()
st.session_state.trade_mode = c4.selectbox("Режим", ["Демо", "Реальный"])

# ====================== ВКЛАДКИ ======================
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["📊 Dashboard", "📈 Графики", "🔄 Арбитраж", "📦 Портфель", "💰 Кошелёк", "📜 История"])

# TAB 1
with tab1:
    st.subheader("📊 Текущие цены")
    for i in range(0, len(DEFAULT_ASSETS), 5):
        cols = st.columns(5)
        for j, asset in enumerate(DEFAULT_ASSETS[i:i+5]):
            with cols[j]:
                st.write(f"**{asset}**")
                if st.session_state.exchanges and MAIN_EXCHANGE in st.session_state.exchanges:
                    price = get_price(st.session_state.exchanges[MAIN_EXCHANGE], asset)
                    st.write(f"💰 ${price:,.0f}" if price else "❌")
    if st.session_state.bot_running:
        st.info("🟢 Бот ищет арбитраж на 10+ биржах")

# TAB 2
with tab2:
    st.subheader("📈 Японские свечи")
    col_a, col_b = st.columns(2)
    selected_asset = col_a.selectbox("Актив", DEFAULT_ASSETS)
    selected_exchange = col_b.selectbox("Биржа", [MAIN_EXCHANGE] + AUX_EXCHANGES[:5])
    if st.button("🔄 Обновить"):
        st.cache_data.clear()
    if st.session_state.exchanges and selected_exchange in st.session_state.exchanges:
        df = get_historical_ohlcv(st.session_state.exchanges[selected_exchange], selected_asset)
        if not df.empty:
            fig = go.Figure(data=[go.Candlestick(x=df['timestamp'], open=df['open'], high=df['high'], low=df['low'], close=df['close'])])
            fig.update_layout(template="plotly_dark", height=450, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(20,20,50,0.5)")
            st.plotly_chart(fig, use_container_width=True)

# TAB 3
with tab3:
    st.subheader("🔍 Арбитраж")
    if st.button("🔄 Поиск"):
        st.cache_data.clear()
    opportunities = find_arbitrage_opportunities()
    if opportunities:
        for opp in opportunities[:5]:
            st.info(f"🎯 {opp['asset']}: OKX ${opp['main_price']:,.0f} → {opp['aux_exchange'].upper()} ${opp['aux_price']:,.0f} | +{opp['profit_usdt']:.2f} USDT")
            if st.button(f"Исполнить {opp['asset']}", key=opp['asset']):
                profit = opp['profit_usdt']
                st.session_state.total_profit += profit
                st.session_state.trade_count += 1
                update_profit_stats(profit)
                st.session_state.history.append(f"✅ {datetime.now().strftime('%H:%M:%S')} | {opp['asset']} | +{profit:.2f} USDT")
                save_user_data()
                save_history()
                st.success(f"+{profit:.2f} USDT")
                st.rerun()
    else:
        st.info("Нет возможностей")

# TAB 4
with tab4:
    st.subheader("📦 Портфель")
    total = 0
    for asset in DEFAULT_ASSETS:
        amount = st.session_state.portfolio.get(asset, 0)
        if st.session_state.exchanges and MAIN_EXCHANGE in st.session_state.exchanges:
            price = get_price(st.session_state.exchanges[MAIN_EXCHANGE], asset)
            value = amount * price if price else 0
            total += value
            st.write(f"{asset}: {amount:.6f} ≈ ${value:,.2f}")
    st.metric("💰 Общая стоимость", f"${total:,.2f}")

# TAB 5
with tab5:
    st.subheader("💰 Кошелёк")
    for ex in AUX_EXCHANGES[:5]:
        st.write(f"{ex.upper()}: {st.session_state.usdt_reserves.get(ex, DEMO_USDT_RESERVES):.0f} USDT")
    st.divider()
    wallet_input = st.text_input("Адрес кошелька", value=st.session_state.wallet_address)
    if st.button("💾 Сохранить"):
        st.session_state.wallet_address = wallet_input
        save_user_data()
    withdraw = st.number_input("Сумма вывода", min_value=10.0, step=10.0)
    if st.button("📤 Вывести"):
        if st.session_state.wallet_address:
            st.success(f"Заявка на вывод {withdraw} USDT")

# TAB 6
with tab6:
    st.subheader("📜 История")
    for trade in reversed(st.session_state.history[-30:]):
        st.write(trade)
    if st.button("🗑 Очистить"):
        st.session_state.history = []
        save_history()
        st.rerun()

# ====================== АВТО-АРБИТРАЖ ======================
if st.session_state.bot_running and st.session_state.exchanges:
    time.sleep(5)
    opps = find_arbitrage_opportunities()
    if opps and opps[0]['profit_usdt'] >= 0.20:
        best = opps[0]
        profit = best['profit_usdt']
        st.session_state.total_profit += profit
        st.session_state.trade_count += 1
        update_profit_stats(profit)
        st.session_state.history.append(f"✅ {datetime.now().strftime('%H:%M:%S')} | {best['asset']} | АВТО | +{profit:.2f} USDT")
        save_user_data()
        save_history()
        st.toast(f"🎯 +{profit:.2f} USDT", icon="💰")
        st.rerun()

st.caption("🚀 10+ бирж | OKX (токены) | Остальные (USDT)")
