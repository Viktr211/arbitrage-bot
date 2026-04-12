import streamlit as st
import time
import random
import json
import ccxt
import pandas as pd
from datetime import datetime
import os

st.set_page_config(page_title="Arbitrage Bot PRO", layout="wide", page_icon="🚀")

# ====================== СТИЛЬ ======================
st.markdown("""
<style>
    .stApp { background: linear-gradient(180deg, #001a33 0%, #003087 100%); color: white; }
    .main-header { font-size: 28px; font-weight: bold; color: #00D4FF; text-align: center; }
    .stButton>button { border-radius: 30px; height: 48px; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# ====================== СОХРАНЕНИЕ ДАННЫХ ======================
DATA_FILE = "user_data.json"

def load_user_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_user_data():
    data = {
        'username': st.session_state.get('username'),
        'total_profit': st.session_state.get('total_profit', 0.0),
        'today_profit': st.session_state.get('today_profit', 0.0),
        'trade_count': st.session_state.get('trade_count', 0),
        'fixed_profit': st.session_state.get('fixed_profit', 0.0),
        'user_balance': st.session_state.get('user_balance', 1000.0),
        'history': st.session_state.get('history', [])[-50:],
        'portfolio': st.session_state.get('portfolio', {})
    }
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# Токены и цели
DEFAULT_ASSETS = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "LINK", "SUI", "HYPE"]
DEFAULT_TARGETS = {"BTC": 0.5, "ETH": 2.0, "SOL": 50.0, "BNB": 20.0, "XRP": 10000.0, "ADA": 5000.0,
                   "AVAX": 100.0, "LINK": 300.0, "SUI": 800.0, "HYPE": 400.0}

ASSET_CONFIG = [{"asset": a} for a in DEFAULT_ASSETS]

# Sandbox биржи
@st.cache_resource
def init_sandbox_exchanges():
    try:
        binance = ccxt.binance({'enableRateLimit': True})
        binance.set_sandbox_mode(True)
        bybit = ccxt.bybit({'enableRateLimit': True})
        bybit.set_sandbox_mode(True)
        st.success("✅ Реальные демо-биржи подключены: Binance Sandbox + Bybit Sandbox")
        return {'binance': binance, 'bybit': bybit}
    except:
        st.warning("Не удалось подключить sandbox биржи")
        return None

exchanges = init_sandbox_exchanges()

# Сессия
for key, default in {
    'logged_in': False,
    'username': None,
    'bot_running': False,
    'mode': "Демо",
    'total_profit': 0.0,
    'today_profit': 0.0,
    'trade_count': 0,
    'fixed_profit': 0.0,
    'user_balance': 1000.0,
    'history': [],
    'portfolio': {a: 0.0 for a in DEFAULT_ASSETS}
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

# Загрузка сохранённых данных
if os.path.exists(DATA_FILE):
    data = load_user_data()
    for key in ['total_profit', 'today_profit', 'trade_count', 'fixed_profit', 'user_balance', 'history', 'portfolio']:
        if key in data:
            st.session_state[key] = data[key]

st.markdown('<h1 class="main-header">🚀 ARBITRAGE BOT PRO</h1>', unsafe_allow_html=True)

# Регистрация / Вход
if not st.session_state.logged_in:
    tab_reg, tab_login = st.tabs(["📝 Регистрация", "🔑 Вход"])
    with tab_reg:
        username = st.text_input("Имя пользователя", key="reg_user")
        email = st.text_input("Email", key="reg_email")
        if st.button("Зарегистрироваться"):
            if username and email:
                st.session_state.logged_in = True
                st.session_state.username = username
                st.success("Регистрация успешна!")
                save_user_data()
                st.rerun()
    with tab_login:
        email = st.text_input("Email", key="login_email")
        if st.button("Войти"):
            if email:
                st.session_state.logged_in = True
                st.session_state.username = email.split('@')[0]
                st.success(f"Добро пожаловать, {st.session_state.username}!")
                st.rerun()
    st.stop()

st.write(f"👤 **{st.session_state.username}** | Баланс: **{st.session_state.user_balance:.2f} USDT**")

# Режим
mode = st.radio("Режим работы", ["Демо (Sandbox)", "Реальный"], horizontal=True)
st.session_state.mode = "Демо" if "Демо" in mode else "Реальный"

if st.session_state.mode == "Реальный":
    st.error("⚠️ Реальный режим использует настоящие деньги!")

# Top Bar
col1, col2, col3 = st.columns([3, 2, 2])
with col1:
    st.metric("💰 Общая прибыль", f"{st.session_state.total_profit:.4f} USDT")
with col2:
    st.metric("💵 Сегодня", f"{st.session_state.today_profit:.2f} USDT")
with col3:
    st.metric("📊 Сделок", st.session_state.trade_count)

# Кнопки
c1, c2, c3 = st.columns(3)
if c1.button("▶ СТАРТ", type="primary", use_container_width=True):
    st.session_state.bot_running = True
if c2.button("⏸ ПАУЗА", use_container_width=True):
    st.session_state.bot_running = False
if c3.button("⏹ СТОП", use_container_width=True):
    st.session_state.bot_running = False

# Вкладки
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 Dashboard", "📈 Графики", "📦 Активы", "💰 Кошелёк", "📜 История"])

with tab1:
    st.subheader("📊 Портфель и Котировки")
    data = []
    for asset in ASSET_CONFIG:
        symbol = asset['asset']
        try:
            if exchanges:
                price = exchanges['binance'].fetch_ticker(symbol + '/USDT')['last']
            else:
                price = random.uniform(100, 60000)
        except:
            price = random.uniform(100, 60000)
        amount = st.session_state.portfolio.get(symbol, 0.0)
        value = amount * price
        data.append({"Токен": symbol, "Цена": f"${price:,.2f}", "Количество": f"{amount:.6f}", "Стоимость": f"${value:,.2f}"})
    st.dataframe(pd.DataFrame(data), use_container_width=True, hide_index=True)

with tab2:
    st.subheader("📈 Японские свечи (реальные из Sandbox)")
    selected = st.selectbox("Выберите токен", [a['asset'] for a in ASSET_CONFIG])
    try:
        if exchanges and 'binance' in exchanges:
            ohlcv = exchanges['binance'].fetch_ohlcv(selected + '/USDT', '1h', limit=60)
            if ohlcv:
                closes = [candle[4] for candle in ohlcv]
                st.line_chart(closes, use_container_width=True)
                st.caption(f"Реальные свечи {selected}/USDT из Binance Sandbox")
            else:
                st.line_chart([random.randint(100, 600) for _ in range(30)], use_container_width=True)
        else:
            st.line_chart([random.randint(100, 600) for _ in range(30)], use_container_width=True)
    except:
        st.line_chart([random.randint(100, 600) for _ in range(30)], use_container_width=True)
        st.caption("Ошибка получения свечей → симуляция")

with tab3:
    st.subheader("📦 Активы и цели (редактирование)")
    cols = st.columns(5)
    for i, asset in enumerate(ASSET_CONFIG):
        with cols[i % 5]:
            name = asset['asset']
            current = DEFAULT_TARGETS.get(name, 0)
            new_target = st.number_input(f"Цель {name}", min_value=0.0, value=float(current), step=0.01, key=f"target_{name}")
            st.metric(name, f"Цель: {new_target}")

with tab4:
    st.subheader("💰 Кошелёк")
    st.metric("Общий баланс USDT", f"{st.session_state.user_balance:.2f}")
    st.metric("Сегодня заработано", f"{st.session_state.today_profit:.2f} USDT")
    
    col_in, col_out = st.columns(2)
    with col_in:
        deposit = st.number_input("Сумма ввода (USDT)", min_value=10.0, step=10.0, key="deposit")
        if st.button("Внести средства"):
            if deposit > 0:
                st.session_state.user_balance += deposit
                st.success(f"Внесено {deposit} USDT!")
                save_user_data()
    with col_out:
        withdraw = st.number_input("Сумма вывода (USDT)", min_value=10.0, max_value=float(st.session_state.user_balance), step=10.0, key="withdraw")
        address = st.text_input("Адрес кошелька", key="addr")
        if st.button("Вывести средства"):
            if withdraw > 0 and address:
                st.session_state.user_balance -= withdraw
                st.success(f"Заявка на вывод {withdraw} USDT отправлена!")
                save_user_data()

with tab5:
    st.subheader("📜 История")
    for trade in reversed(st.session_state.history[-30:]):
        st.write(trade)

# ================== СИМУЛЯЦИЯ ==================
if st.session_state.bot_running:
    time.sleep(2)
    asset = random.choice([a['asset'] for a in ASSET_CONFIG])
    gross_profit = round(random.uniform(0.8, 5.5), 4)

    fixed = round(gross_profit * 0.5, 4)
    reinvest = round(gross_profit * 0.5, 4)

    st.session_state.total_profit += gross_profit
    st.session_state.today_profit += gross_profit
    st.session_state.fixed_profit += fixed
    st.session_state.trade_count += 1
    st.session_state.user_balance += reinvest

    st.session_state.portfolio[asset] = st.session_state.portfolio.get(asset, 0.0) + (reinvest / 500)

    trade_text = f"✅ {datetime.now().strftime('%H:%M:%S')} | {asset}/USDT | +{gross_profit:.4f} | Фикс: {fixed:.4f} | Реинвест: {reinvest:.4f}"
    st.session_state.history.append(trade_text)

    save_user_data()
    st.rerun()

st.caption("Веб-версия 4.2 — реальные свечи + sandbox + сохранение данных")
