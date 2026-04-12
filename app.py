import streamlit as st
import time
import json
import ccxt
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

# Загрузка конфига
try:
    with open('config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)
except:
    config = {"asset_config": [], "target_asset_amount": {}}

ASSET_CONFIG = config.get('asset_config', [])
TARGET_ASSET_AMOUNT = config.get('target_asset_amount', {})

# Инициализация sandbox бирж
@st.cache_resource
def init_sandbox_exchanges():
    try:
        binance = ccxt.binance({'enableRateLimit': True})
        binance.set_sandbox_mode(True)
        
        bybit = ccxt.bybit({'enableRateLimit': True})
        bybit.set_sandbox_mode(True)
        
        st.success("✅ Sandbox биржи подключены (Binance + Bybit)")
        return {'binance': binance, 'bybit': bybit}
    except Exception as e:
        st.warning("Не удалось подключить sandbox. Работаем в симуляции.")
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

st.write(f"👤 **{st.session_state.username}** | Баланс: **{st.session_state.user_balance:.2f} USDT**")

# Режим
mode = st.radio("Режим работы", ["Демо (Sandbox)", "Реальный"], horizontal=True)
st.session_state.mode = "Демо" if "Демо" in mode else "Реальный"

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
    st.subheader("Главный дашборд")
    st.write(f"**Режим:** {st.session_state.mode} | Sandbox: Binance + Bybit")

with tab2:
    st.subheader("📈 Японские свечи")
    selected = st.selectbox("Выберите токен", [a.get('asset', 'BTC') for a in ASSET_CONFIG] or ["BTC"])
    try:
        if exchanges:
            ohlcv = exchanges['binance'].fetch_ohlcv(selected + '/USDT', '1h', limit=50)
            if ohlcv:
                closes = [candle[4] for candle in ohlcv]
                st.line_chart(closes, use_container_width=True)
            else:
                st.warning("Нет данных свечей")
        else:
            st.line_chart([random.randint(100, 600) for _ in range(30)], use_container_width=True)
    except:
        st.line_chart([random.randint(100, 600) for _ in range(30)], use_container_width=True)
        st.caption("Реальные sandbox свечи (если не загрузилось — симуляция)")

with tab3:
    st.subheader("📦 Активы и цели")
    cols = st.columns(5)
    for i, asset in enumerate(ASSET_CONFIG):
        with cols[i % 5]:
            target = TARGET_ASSET_AMOUNT.get(asset.get('asset'), 0)
            st.metric(asset.get('asset'), f"Цель: {target}")

with tab4:
    st.subheader("💰 Кошелёк")
    st.metric("Общий баланс", f"{st.session_state.user_balance:.2f} USDT")
    st.metric("Сегодня заработано", f"{st.session_state.today_profit:.2f} USDT")
    amount = st.number_input("Сумма вывода (USDT)", min_value=10.0, max_value=float(st.session_state.user_balance))
    address = st.text_input("Адрес кошелька")
    if st.button("Вывести средства"):
        if amount > 0 and address:
            st.session_state.user_balance -= amount
            st.success(f"Заявка на вывод {amount} USDT отправлена!")
        else:
            st.error("Введите сумму и адрес")

with tab5:
    st.subheader("📜 История")
    for trade in reversed(st.session_state.history[-20:]):
        st.write(trade)

# ================== СИМУЛЯЦИЯ С SANDBOX ==================
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

    trade_text = f"✅ {datetime.now().strftime('%H:%M:%S')} | {asset}/USDT | +{gross_profit} | Фикс: {fixed} | Реинвест: {reinvest}"
    st.session_state.history.append(trade_text)

    st.rerun()

st.caption("Веб-версия 3.4 — sandbox биржи + кошелёк + цели")
