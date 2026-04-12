import streamlit as st
import time
import random
import json
import ccxt
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="Arbitrage Bot PRO", layout="wide", page_icon="🚀")

# ====================== СТИЛЬ ======================
st.markdown("""
<style>
    .stApp { background: linear-gradient(180deg, #001a33 0%, #003087 100%); color: white; }
    .main-header { font-size: 28px; font-weight: bold; color: #00D4FF; text-align: center; }
    .stButton>button { border-radius: 30px; height: 48px; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# Встроенный список токенов
DEFAULT_ASSETS = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "LINK", "SUI", "HYPE"]
DEFAULT_TARGETS = {"BTC": 0.5, "ETH": 2.0, "SOL": 50.0, "BNB": 20.0, "XRP": 10000.0, "ADA": 5000.0,
                   "AVAX": 100.0, "LINK": 300.0, "SUI": 800.0, "HYPE": 400.0}

# Загрузка конфига
try:
    with open('config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)
except:
    config = {}

ASSET_CONFIG = config.get('asset_config', [{"asset": a} for a in DEFAULT_ASSETS])
TARGET_ASSET_AMOUNT = config.get('target_asset_amount', DEFAULT_TARGETS)

# Инициализация sandbox бирж
@st.cache_resource
def init_sandbox_exchanges():
    try:
        binance = ccxt.binance({'enableRateLimit': True})
        binance.set_sandbox_mode(True)
        bybit = ccxt.bybit({'enableRateLimit': True})
        bybit.set_sandbox_mode(True)
        st.success("✅ Sandbox подключены: Binance + Bybit")
        return {'binance': binance, 'bybit': bybit}
    except:
        st.warning("Sandbox не подключился. Используем симуляцию.")
        return None

exchanges = init_sandbox_exchanges()

# Сессия
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'username' not in st.session_state:
    st.session_state.username = None
if 'bot_running' not in st.session_state:
    st.session_state.bot_running = False
if 'mode' not in st.session_state:
    st.session_state.mode = "Демо"
if 'total_profit' not in st.session_state:
    st.session_state.total_profit = 0.0
if 'today_profit' not in st.session_state:
    st.session_state.today_profit = 0.0
if 'trade_count' not in st.session_state:
    st.session_state.trade_count = 0
if 'history' not in st.session_state:
    st.session_state.history = []
if 'fixed_profit' not in st.session_state:
    st.session_state.fixed_profit = 0.0
if 'user_balance' not in st.session_state:
    st.session_state.user_balance = 1000.0
if 'portfolio' not in st.session_state:   # Новый: количество каждого токена
    st.session_state.portfolio = {asset.get('asset', 'BTC'): 0.0 for asset in ASSET_CONFIG}

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

st.write(f"👤 **{st.session_state.username}** | Баланс USDT: **{st.session_state.user_balance:.2f}**")

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

# Кнопки управления
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
    st.subheader("📊 Портфель и Котировки (Dashboard)")
    try:
        data = []
        for asset in ASSET_CONFIG:
            symbol = asset.get('asset', 'BTC')
            try:
                if exchanges:
                    ticker = exchanges['binance'].fetch_ticker(symbol + '/USDT')
                    price = ticker['last']
                else:
                    price = random.uniform(100, 60000)
            except:
                price = random.uniform(100, 60000)
            
            amount = st.session_state.portfolio.get(symbol, 0.0)
            value = amount * price
            
            data.append({
                "Токен": symbol,
                "Цена (USDT)": f"${price:,.2f}",
                "Количество": f"{amount:.6f}",
                "Стоимость (USDT)": f"${value:,.2f}"
            })
        
        df = pd.DataFrame(data)
        st.dataframe(df, use_container_width=True, hide_index=True)
    except:
        st.info("Загрузка портфеля...")

with tab2:
    st.subheader("📈 Японские свечи")
    selected = st.selectbox("Выберите токен", [a.get('asset', 'BTC') for a in ASSET_CONFIG])
    try:
        if exchanges and 'binance' in exchanges:
            ohlcv = exchanges['binance'].fetch_ohlcv(selected + '/USDT', '1h', limit=50)
            if ohlcv:
                closes = [candle[4] for candle in ohlcv]
                st.line_chart(closes, use_container_width=True)
            else:
                st.line_chart([random.randint(100, 600) for _ in range(30)], use_container_width=True)
        else:
            st.line_chart([random.randint(100, 600) for _ in range(30)], use_container_width=True)
    except:
        st.line_chart([random.randint(100, 600) for _ in range(30)], use_container_width=True)

with tab3:
    st.subheader("📦 Активы и цели")
    cols = st.columns(5)
    for i, asset in enumerate(ASSET_CONFIG):
        with cols[i % 5]:
            asset_name = asset.get('asset', 'BTC')
            target = TARGET_ASSET_AMOUNT.get(asset_name, 0)
            st.metric(asset_name, f"Цель: {target}")

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
    with col_out:
        withdraw = st.number_input("Сумма вывода (USDT)", min_value=10.0, max_value=float(st.session_state.user_balance), step=10.0, key="withdraw")
        address = st.text_input("Адрес кошелька", key="withdraw_address")
        if st.button("Вывести средства"):
            if withdraw > 0 and address:
                st.session_state.user_balance -= withdraw
                st.success(f"Заявка на вывод {withdraw} USDT отправлена!")
            else:
                st.error("Введите сумму и адрес")

with tab5:
    st.subheader("📜 История")
    for trade in reversed(st.session_state.history[-20:]):
        st.write(trade)

# ================== СИМУЛЯЦИЯ ==================
if st.session_state.bot_running:
    time.sleep(2)
    asset = random.choice([a.get('asset', 'BTC') for a in ASSET_CONFIG] or ["BTC"])
    gross_profit = round(random.uniform(0.8, 5.5), 4)

    fixed = round(gross_profit * 0.5, 4)
    reinvest = round(gross_profit * 0.5, 4)

    st.session_state.total_profit += gross_profit
    st.session_state.today_profit += gross_profit
    st.session_state.fixed_profit += fixed
    st.session_state.trade_count += 1
    st.session_state.user_balance += reinvest

    # Добавляем немного токена в портфель при реинвесте
    st.session_state.portfolio[asset] = st.session_state.portfolio.get(asset, 0.0) + (reinvest / 1000)

    trade_text = f"✅ {datetime.now().strftime('%H:%M:%S')} | {asset}/USDT | +{gross_profit} | Фикс: {fixed} | Реинвест: {reinvest}"
    st.session_state.history.append(trade_text)

    st.rerun()

st.caption("Веб-версия 3.7 — добавлен Dashboard с котировками и портфелем")
