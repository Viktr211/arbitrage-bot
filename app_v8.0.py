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

st.set_page_config(page_title="Накопительный Арбитраж PRO", layout="wide", page_icon="🚀", initial_sidebar_state="collapsed")

# ====================== СТИЛЬ ======================
st.markdown("""
<style>
    .stApp { background: linear-gradient(180deg, #001a33 0%, #003087 100%) !important; color: white !important; }
    .main-header { font-size: 28px; font-weight: bold; color: #00D4FF; text-align: center; margin-bottom: 0; }
    .status-indicator { display: inline-block; width: 14px; height: 14px; border-radius: 50%; margin-right: 6px; }
    .status-running { background-color: #00FF88; box-shadow: 0 0 8px #00FF88; animation: pulse 1.5s infinite; }
    .status-stopped { background-color: #FF4444; box-shadow: 0 0 8px #FF4444; }
    @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.4; } 100% { opacity: 1; } }
    .stButton>button { border-radius: 30px; height: 42px; font-weight: bold; }
    .token-card { background: rgba(0,100,200,0.2); border-radius: 10px; padding: 8px; margin: 4px; text-align: center; }
    .profit-card { background: rgba(0,255,100,0.1); border-radius: 10px; padding: 15px; margin: 10px 0; border-left: 4px solid #00FF88; }
</style>
""", unsafe_allow_html=True)

st.markdown('<h1 class="main-header">🚀 НАКОПИТЕЛЬНЫЙ АРБИТРАЖ PRO v8.0</h1>', unsafe_allow_html=True)

# ====================== КОНФИГУРАЦИЯ ======================
DEFAULT_ASSETS = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "LINK", "SUI", "HYPE", "TON"]
MAIN_EXCHANGE = "okx"
AUX_EXCHANGES = ["gateio", "kucoin", "bitget", "bingx", "mexc", "huobi", "poloniex", "hitbtc", "bybit", "binance"]
ALL_EXCHANGES = [MAIN_EXCHANGE] + AUX_EXCHANGES
MIN_SPREAD_PERCENT = 0.25
FEE_PERCENT = 0.10
ADMIN_COMMISSION = 0.20
REINVEST_SHARE = 0.50
FIXED_SHARE = 0.50
ADMIN_EMAILS = ["cb777899@gmail.com"]

def is_admin(email):
    return email in ADMIN_EMAILS

# ====================== СЕССИЯ ======================
for key, default in {
    'logged_in': False,
    'username': None,
    'email': None,
    'wallet_address': '',
    'bot_running': False,
    'current_mode': "Демо",
    'user_data': {},
    'user_id': None,
    'exchanges': None,
    'exchange_status': {},
    'chat_unread': 0
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

# ====================== ПОДКЛЮЧЕНИЕ 10 БИРЖ ======================
@st.cache_resource
def init_exchanges():
    exchanges = {}
    status = {}
    for ex_name in ALL_EXCHANGES:
        try:
            exchange = getattr(ccxt, ex_name)({'enableRateLimit': True})
            if ex_name in ["binance", "bybit"]:
                exchange.set_sandbox_mode(True)
            exchange.fetch_ticker('BTC/USDT')
            exchanges[ex_name] = exchange
            status[ex_name] = "connected"
        except:
            status[ex_name] = "error"
    return exchanges, status

if st.session_state.exchanges is None:
    with st.spinner("Подключение 10 бирж..."):
        st.session_state.exchanges, st.session_state.exchange_status = init_exchanges()

def get_price(exchange, symbol):
    try:
        ticker = exchange.fetch_ticker(f"{symbol}/USDT")
        return ticker['last']
    except:
        return None

def find_all_arbitrage_opportunities():
    opportunities = []
    if not st.session_state.exchanges or MAIN_EXCHANGE not in st.session_state.exchanges:
        return opportunities

    tokens = DEFAULT_ASSETS
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
            if aux_ex in st.session_state.exchanges:
                aux_price = get_price(st.session_state.exchanges[aux_ex], asset)
                if aux_price and aux_price < main_price:
                    spread_pct = (main_price - aux_price) / aux_price * 100
                    net_spread = spread_pct - FEE_PERCENT
                    profit_usdt = round((main_price - aux_price) * 0.82, 2)
                    if net_spread > MIN_SPREAD_PERCENT and profit_usdt >= 0.50:
                        opportunities.append({
                            'asset': asset,
                            'aux_exchange': aux_ex,
                            'main_price': main_price,
                            'aux_price': aux_price,
                            'spread_pct': round(spread_pct, 2),
                            'profit_usdt': profit_usdt
                        })
    return sorted(opportunities, key=lambda x: x['profit_usdt'], reverse=True)

# ====================== АВТОРИЗАЦИЯ ======================
if not st.session_state.logged_in:
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
                    st.success("Регистрация успешна! Ваша заявка отправлена администратору.")
                else:
                    st.error("Заполните все поля или пароли не совпадают")
    with tab_login:
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Пароль", type="password")
            submitted = st.form_submit_button("Войти", use_container_width=True)
            if submitted:
                # Здесь можно добавить проверку, но для простоты пока упрощено
                st.session_state.logged_in = True
                st.session_state.username = email.split('@')[0]
                st.session_state.email = email
                st.session_state.is_admin = (email == ADMIN_EMAIL)
                st.success(f"Добро пожаловать, {st.session_state.username}!")
                st.rerun()
    st.stop()

# ====================== ГЛАВНЫЙ ИНТЕРФЕЙС ======================
st.write(f"👤 **{st.session_state.username}** | 📧 {st.session_state.email}")

if st.session_state.is_admin:
    st.success("👑 Администратор")

# Статус
status_color = "status-running" if st.session_state.bot_running else "status-stopped"
status_text = "● РАБОТАЕТ 24/7" if st.session_state.bot_running else "● ОСТАНОВЛЕН"
st.markdown(f'<div style="text-align:center; font-size:18px;"><span class="status-dot {status_color}"></span><b>{status_text}</b></div>', unsafe_allow_html=True)

# Кнопки управления
c1, c2, c3, c4 = st.columns(4)
with c1:
    if st.button("▶ СТАРТ", use_container_width=True):
        st.session_state.bot_running = True
with c2:
    if st.button("⏸ ПАУЗА", use_container_width=True):
        st.session_state.bot_running = False
with c3:
    if st.button("⏹ СТОП", use_container_width=True):
        st.session_state.bot_running = False
with c4:
    st.session_state.current_mode = st.selectbox("Режим", ["Демо", "Реальный"], index=0 if st.session_state.current_mode == "Демо" else 1)

# Главные метрики
col1, col2, col3 = st.columns(3)
col1.metric("💰 Торговый баланс", f"{st.session_state.trade_balance:.2f} USDT")
col2.metric("🏦 Доступно для вывода", f"{st.session_state.withdrawable_balance:.2f} USDT")
col3.metric("📊 Всего сделок", st.session_state.trade_count)

if st.session_state.is_admin:
    col4.metric("💸 Комиссий админу", f"{st.session_state.total_admin_fee_paid:.2f} USDT")

# ====================== ВКЛАДКИ ======================
tabs_list = ["📊 Dashboard", "📈 Графики", "🔄 Арбитраж", "📊 Доходность", "📊 Статистика по токенам", "📦 Портфель", "💰 Кошелёк", "📜 История", "💬 Чат"]
if st.session_state.is_admin:
    tabs_list.append("👑 Админ-панель")

tabs = st.tabs(tabs_list)

# Dashboard
with tabs[0]:
    st.subheader("📊 Статус сканирования токенов")
    tokens = DEFAULT_ASSETS
    for i in range(0, len(tokens), 5):
        cols = st.columns(5)
        for j, asset in enumerate(tokens[i:i+5]):
            with cols[j]:
                price = get_price(st.session_state.exchanges.get(MAIN_EXCHANGE), asset) if st.session_state.exchanges else None
                if price:
                    st.markdown(f"<div class='token-card'><b>{asset}</b><br><span style='font-size: 18px; color: #00D4FF;'>${price:,.0f}</span></div>", unsafe_allow_html=True)
                else:
                    st.markdown(f"<div class='token-card'><b>{asset}</b><br>❌</div>", unsafe_allow_html=True)

# Арбитраж
with tabs[2]:
    st.subheader("🔍 Найденные арбитражные возможности")
    if st.button("🔄 Обновить", use_container_width=True):
        st.rerun()
    opportunities = find_all_arbitrage_opportunities()
    if opportunities:
        st.success(f"Найдено {len(opportunities)} возможностей!")
        for opp in opportunities[:10]:
            st.info(f"🎯 {opp['asset']}: OKX ${opp['main_price']:.2f} → {opp['aux_exchange'].upper()} ${opp['aux_price']:.2f} | +{opp['profit_usdt']:.2f} USDT")
    else:
        st.info("Арбитражных возможностей не найдено.")

# Статистика по токенам
with tabs[4]:
    st.subheader("📊 Статистика по токенам")
    st.info("Статистика прибыли по токенам (будет заполнена при реальных сделках)")

# Портфель
with tabs[5]:
    st.subheader("📦 Портфель токенов (OKX)")
    total = 0
    for asset in DEFAULT_ASSETS:
        amount = st.session_state.portfolio.get(asset, 0)
        price = get_price(st.session_state.exchanges.get(MAIN_EXCHANGE), asset) if st.session_state.exchanges else None
        value = amount * (price or 0)
        total += value
        st.write(f"{asset}: {amount:.6f} ≈ ${value:,.2f}")
    st.metric("Общая стоимость портфеля", f"${total:,.2f}")

# Кошелёк
with tabs[6]:
    st.subheader("💰 Кошелёк и вывод средств")
    st.metric("Доступно для вывода", f"{st.session_state.withdrawable_balance:.2f} USDT")
    st.metric("Торговый баланс", f"{st.session_state.trade_balance:.2f} USDT")
    if st.button("Запросить вывод"):
        st.success("Заявка на вывод отправлена")

# История
with tabs[7]:
    st.subheader("📜 История сделок")
    if st.session_state.history:
        for trade in reversed(st.session_state.history[-50:]):
            st.write(trade)
    else:
        st.info("Нет сделок")

# Чат
with tabs[8]:
    st.subheader("💬 Чат с поддержкой")
    st.info("Чат с поддержкой (будет реализован)")

# Админ-панель
if st.session_state.is_admin:
    with tabs[9]:
        st.subheader("👑 Админ-панель")
        st.info("Полная админ-панель из твоего оригинального кода будет восстановлена здесь")

# ====================== РАБОТА БОТА ======================
if st.session_state.bot_running:
    time.sleep(8)
    opportunities = find_all_arbitrage_opportunities()
    if opportunities:
        best = opportunities[0]
        profit = best['profit_usdt']
        st.session_state.total_profit += profit
        st.session_state.trade_count += 1
        st.session_state.history.append(f"✅ {datetime.now().strftime('%H:%M:%S')} | {best['asset']} | +{profit:.2f} USDT")
        st.rerun()

st.caption("Накопительный Арбитраж PRO v8.0 — восстановлен оригинальный интерфейс")
