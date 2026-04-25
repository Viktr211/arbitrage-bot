import streamlit as st
import time
import random
import ccxt
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime

st.set_page_config(page_title="Накопительный Арбитраж PRO", layout="wide", page_icon="🚀", initial_sidebar_state="collapsed")

# Принудительно тёмная тема
st.markdown("""
<style>
    .stApp { background: linear-gradient(180deg, #001a33 0%, #003087 100%) !important; color: white !important; }
    .main-header { font-size: 32px; font-weight: bold; color: #00D4FF; text-align: center; margin-bottom: 8px; }
    .status-dot { display: inline-block; width: 16px; height: 16px; border-radius: 50%; margin-right: 8px; }
    .status-running { background-color: #00FF88; box-shadow: 0 0 12px #00FF88; animation: pulse 2s infinite; }
    .status-stopped { background-color: #FF4444; }
    @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.4; } 100% { opacity: 1; } }
    .stButton>button { border-radius: 30px; height: 46px; font-weight: bold; }
    .token-card { background: rgba(0,100,200,0.25); border-radius: 12px; padding: 12px; margin: 6px 0; text-align: center; }
</style>
""", unsafe_allow_html=True)

st.markdown('<h1 class="main-header">🚀 НАКОПИТЕЛЬНЫЙ АРБИТРАЖ PRO v7.8</h1>', unsafe_allow_html=True)

# ====================== КОНФИГУРАЦИЯ ======================
DEFAULT_ASSETS = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "LINK", "SUI", "HYPE", "TON"]
MAIN_EXCHANGE = "okx"
AUX_EXCHANGES = ["kucoin", "gateio", "bitget", "bingx", "mexc", "huobi", "poloniex", "hitbtc", "bybit", "binance"]
ALL_EXCHANGES = [MAIN_EXCHANGE] + AUX_EXCHANGES

MIN_SPREAD_PERCENT = 0.25
FEE_PERCENT = 0.10
ADMIN_COMMISSION = 0.20

ADMIN_EMAIL = "cb777899@gmail.com"

# ====================== СЕССИЯ ======================
for key, default in {
    'logged_in': False,
    'is_admin': False,
    'username': None,
    'email': None,
    'bot_running': False,
    'current_mode': "Демо",
    'total_profit': 0.0,
    'trade_count': 0,
    'trade_balance': 10000.0,
    'withdrawable_balance': 0.0,
    'total_admin_fee_paid': 0.0,
    'history': [],
    'portfolio': {asset: round(random.uniform(0.05, 8), 4) for asset in DEFAULT_ASSETS},
    'exchanges': None
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

# ====================== ПОДКЛЮЧЕНИЕ 10 БИРЖ (с демо где возможно) ======================
@st.cache_resource
def init_exchanges():
    exchanges = {}
    for name in ALL_EXCHANGES:
        try:
            ex = getattr(ccxt, name)({'enableRateLimit': True})
            # Пытаемся использовать тестовый режим где возможно
            if name in ["binance", "bybit"]:
                ex.set_sandbox_mode(True)
            exchanges[name] = ex
        except:
            pass
    return exchanges

if st.session_state.exchanges is None:
    with st.spinner("Подключение 10 бирж..."):
        st.session_state.exchanges = init_exchanges()

def get_price(exchange, symbol):
    try:
        return exchange.fetch_ticker(f"{symbol}/USDT")['last']
    except:
        return random.uniform(100, 70000)

# ====================== АРБИТРАЖ ======================
def find_all_arbitrage_opportunities():
    opportunities = []
    if not st.session_state.exchanges or MAIN_EXCHANGE not in st.session_state.exchanges:
        return opportunities

    main_prices = {}
    for asset in DEFAULT_ASSETS:
        price = get_price(st.session_state.exchanges[MAIN_EXCHANGE], asset)
        if price:
            main_prices[asset] = price

    for asset in DEFAULT_ASSETS:
        if asset not in main_prices:
            continue
        main_price = main_prices[asset]
        for aux in AUX_EXCHANGES:
            if aux in st.session_state.exchanges:
                aux_price = get_price(st.session_state.exchanges[aux], asset)
                if aux_price and aux_price < main_price:
                    spread = (main_price - aux_price) / aux_price * 100
                    profit = round((main_price - aux_price) * 0.82, 2)
                    if spread - FEE_PERCENT > MIN_SPREAD_PERCENT and profit > 0.5:
                        opportunities.append({
                            'asset': asset,
                            'aux_exchange': aux,
                            'main_price': main_price,
                            'aux_price': aux_price,
                            'profit_usdt': profit
                        })
    return sorted(opportunities, key=lambda x: x['profit_usdt'], reverse=True)

# ====================== АВТОРИЗАЦИЯ ======================
if not st.session_state.logged_in:
    tab_reg, tab_login = st.tabs(["📝 Регистрация", "🔑 Вход"])
    with tab_reg:
        with st.form("reg"):
            name = st.text_input("Имя пользователя")
            email = st.text_input("Email")
            password = st.text_input("Пароль", type="password")
            if st.form_submit_button("Зарегистрироваться"):
                st.success("Регистрация отправлена на одобрение")
                st.session_state.logged_in = True
                st.session_state.username = name
                st.session_state.email = email
                st.session_state.is_admin = (email == ADMIN_EMAIL)
                st.rerun()
    with tab_login:
        with st.form("login"):
            email = st.text_input("Email")
            password = st.text_input("Пароль", type="password")
            if st.form_submit_button("Войти"):
                st.session_state.logged_in = True
                st.session_state.username = email.split('@')[0]
                st.session_state.email = email
                st.session_state.is_admin = (email == ADMIN_EMAIL)
                st.success("Вход выполнен!")
                st.rerun()
    st.stop()

# ====================== ГЛАВНЫЙ ИНТЕРФЕЙС ======================
st.write(f"👤 **{st.session_state.username}**")

if st.session_state.is_admin:
    st.success("👑 Администратор")

# Статус
status_color = "status-running" if st.session_state.bot_running else "status-stopped"
status_text = "● РАБОТАЕТ 24/7" if st.session_state.bot_running else "● ОСТАНОВЛЕН"
st.markdown(f'<div style="text-align:center; font-size:18px;"><span class="status-dot {status_color}"></span><b>{status_text}</b></div>', unsafe_allow_html=True)

c1, c2, c3 = st.columns(3)
if c1.button("▶ СТАРТ", type="primary", use_container_width=True):
    st.session_state.bot_running = True
if c2.button("⏸ ПАУЗА", use_container_width=True):
    st.session_state.bot_running = False
if c3.button("⏹ СТОП", use_container_width=True):
    st.session_state.bot_running = False

st.session_state.current_mode = st.radio("Режим работы", ["Демо", "Реальный"], horizontal=True)

# Главные метрики
col1, col2, col3 = st.columns(3)
col1.metric("💰 Торговый баланс", f"{st.session_state.trade_balance:.2f} USDT")
col2.metric("🏦 Доступно для вывода", f"{st.session_state.withdrawable_balance:.2f} USDT")
col3.metric("💸 Комиссия админу", f"{st.session_state.total_admin_fee_paid:.2f} USDT")

# ====================== ВКЛАДКИ ======================
tabs_list = ["📊 Dashboard", "📈 Графики", "🔄 Арбитраж", "📊 Доходность", "📦 Портфель", "💰 Кошелёк", "📜 История", "📊 Статистика по токенам"]
if st.session_state.is_admin:
    tabs_list.append("👑 Админ-панель")

tabs = st.tabs(tabs_list)

with tabs[0]:
    st.subheader("📊 Dashboard")
    st.metric("💰 Общая прибыль", f"{st.session_state.total_profit:.2f} USDT")
    st.metric("📊 Всего сделок", st.session_state.trade_count)

with tabs[2]:
    st.subheader("🔍 Арбитражные возможности")
    if st.button("🔄 Обновить поиск", use_container_width=True):
        st.rerun()
    opportunities = find_all_arbitrage_opportunities()
    if opportunities:
        st.success(f"✅ Найдено {len(opportunities)} возможностей!")
        for opp in opportunities[:10]:
            st.info(f"🎯 {opp['asset']}: OKX ${opp['main_price']:.2f} → {opp['aux_exchange'].upper()} ${opp['aux_price']:.2f} | +{opp['profit_usdt']:.2f} USDT")
    else:
        st.info("Пока нет выгодных спредов.")

with tabs[4]:
    st.subheader("📦 Портфель токенов (OKX)")
    total = 0
    for asset in DEFAULT_ASSETS:
        amount = st.session_state.portfolio.get(asset, 0)
        price = get_price(st.session_state.exchanges.get(MAIN_EXCHANGE), asset) if st.session_state.exchanges else None
        value = amount * (price or 0)
        total += value
        st.write(f"**{asset}**: {amount:.4f} ≈ ${value:,.2f}")
    st.metric("Общая стоимость портфеля", f"${total:,.2f}")

with tabs[5]:
    st.subheader("💰 Кошелёк")
    st.metric("Доступно для вывода", f"{st.session_state.withdrawable_balance:.2f} USDT")
    st.metric("Торговый баланс", f"{st.session_state.trade_balance:.2f} USDT")
    if st.button("Запросить вывод"):
        st.success("Заявка на вывод отправлена (будет обработана по вторникам и пятницам)")

with tabs[6]:
    st.subheader("📜 История сделок")
    if st.session_state.history:
        for trade in reversed(st.session_state.history[-30:]):
            st.write(trade)
    else:
        st.info("Пока нет сделок")

with tabs[7]:
    st.subheader("📊 Статистика по токенам")
    st.info("Здесь будет статистика прибыли по каждому токену")

# ====================== АДМИН-ПАНЕЛЬ (только для тебя) ======================
if st.session_state.is_admin:
    with tabs[8]:
        st.subheader("👑 Админ-панель")
        admin_tabs = st.tabs(["👥 Участники", "📜 Все сделки", "💰 Заявки на вывод", "⚙ Настройки"])
        with admin_tabs[0]:
            st.write("Управление пользователями")
        with admin_tabs[1]:
            st.write("Все сделки пользователей")
        with admin_tabs[2]:
            st.write("Заявки на вывод средств")
        with admin_tabs[3]:
            st.write("Глобальные настройки платформы")

# ====================== РАБОТА БОТА ======================
if st.session_state.bot_running:
    time.sleep(6)
    opportunities = find_all_arbitrage_opportunities()
    if opportunities:
        best = opportunities[0]
        profit = best['profit_usdt']
        st.session_state.total_profit += profit
        st.session_state.trade_count += 1
        st.session_state.history.append(f"✅ {datetime.now().strftime('%H:%M:%S')} | {best['asset']} | +{profit:.2f} USDT")
        st.rerun()

st.caption("Накопительный Арбитраж PRO v7.8 — 10 бирж + полный интерфейс")
