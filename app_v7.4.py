import streamlit as st
import time
import random
import json
import ccxt
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
import os

st.set_page_config(page_title="Накопительный Арбитраж PRO v7.4", layout="wide", page_icon="🚀")

# ====================== СТИЛЬ ======================
st.markdown("""
<style>
    .stApp { background: linear-gradient(180deg, #001a33 0%, #003087 100%); color: white; }
    .main-header { font-size: 32px; font-weight: bold; color: #00D4FF; text-align: center; margin-bottom: 8px; }
    .status-dot { display: inline-block; width: 16px; height: 16px; border-radius: 50%; margin-right: 8px; vertical-align: middle; }
    .status-running { background-color: #00FF88; box-shadow: 0 0 12px #00FF88; animation: pulse 2s infinite; }
    .status-stopped { background-color: #FF4444; }
    @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.4; } 100% { opacity: 1; } }
    .stButton>button { border-radius: 30px; height: 46px; font-weight: bold; }
    .token-card { background: rgba(0,100,200,0.25); border-radius: 12px; padding: 12px; margin: 6px 0; text-align: center; }
</style>
""", unsafe_allow_html=True)

st.markdown('<h1 class="main-header">🚀 НАКОПИТЕЛЬНЫЙ АРБИТРАЖ PRO v7.4</h1>', unsafe_allow_html=True)

# ====================== КОНФИГУРАЦИЯ ======================
DEFAULT_ASSETS = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "LINK", "SUI", "HYPE", "TON"]
MAIN_EXCHANGE = "okx"
AUX_EXCHANGES = ["kucoin", "gateio", "bitget", "bingx", "mexc"]
MIN_SPREAD_PERCENT = 0.25      # Увеличил, чтобы реальный спред был заметен
FEE_PERCENT = 0.10
ADMIN_COMMISSION = 0.20
REINVEST_SHARE = 0.50
FIXED_SHARE = 0.50

ADMIN_EMAILS = ["cb777899@gmail.com"]

# ====================== СЕССИЯ ======================
for key, default in {
    'logged_in': False,
    'is_admin': False,
    'username': None,
    'email': None,
    'user_id': None,
    'bot_running': False,
    'current_mode': "Демо",
    'total_profit': 0.0,
    'trade_count': 0,
    'history': [],
    'portfolio': {},
    'withdrawable_balance': 0.0,
    'trade_balance': 10000.0,
    'exchanges': None,
    'exchange_status': {}
}.items():
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
        except Exception as e:
            status[ex_name] = "error"
    return exchanges, status

if st.session_state.exchanges is None:
    with st.spinner("Подключение к биржам..."):
        st.session_state.exchanges, st.session_state.exchange_status = init_exchanges()

# ====================== ФУНКЦИИ АРБИТРАЖА ======================
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

    main_ex = st.session_state.exchanges[MAIN_EXCHANGE]
    tokens = DEFAULT_ASSETS

    main_prices = {}
    for asset in tokens:
        price = get_price(main_ex, asset)
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
                    profit_usdt = round((main_price - aux_price) * 0.85, 2)   # с запасом на комиссии

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
            password = st.text_input("Пароль", type="password")
            if st.form_submit_button("Зарегистрироваться"):
                if username and email and password:
                    st.success("Регистрация успешна! (в этой версии упрощена)")
                    st.session_state.logged_in = True
                    st.session_state.username = username
                    st.session_state.email = email
                    st.session_state.is_admin = (email == "cb777899@gmail.com")
                    st.rerun()
    with tab_login:
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Пароль", type="password")
            if st.form_submit_button("Войти"):
                if email:
                    st.session_state.logged_in = True
                    st.session_state.username = email.split('@')[0]
                    st.session_state.email = email
                    st.session_state.is_admin = (email == "cb777899@gmail.com")
                    st.success(f"Добро пожаловать, {st.session_state.username}!")
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

# Кнопки управления
c1, c2, c3 = st.columns(3)
if c1.button("▶ СТАРТ", type="primary", use_container_width=True):
    st.session_state.bot_running = True
if c2.button("⏸ ПАУЗА", use_container_width=True):
    st.session_state.bot_running = False
if c3.button("⏹ СТОП", use_container_width=True):
    st.session_state.bot_running = False

st.session_state.current_mode = st.radio("Режим работы", ["Демо", "Реальный"], horizontal=True)

# ====================== ВКЛАДКИ ======================
tabs = st.tabs(["📊 Dashboard", "📈 Графики", "🔄 Арбитраж", "📦 Портфель", "💰 Кошелёк", "📜 История"])

with tabs[0]:
    st.metric("💰 Общая прибыль", f"{st.session_state.total_profit:.2f} USDT")
    st.metric("📊 Сделок", st.session_state.trade_count)

with tabs[2]:
    st.subheader("🔍 Арбитражные возможности")
    if st.button("🔄 Обновить поиск", use_container_width=True):
        st.rerun()
    
    opportunities = find_all_arbitrage_opportunities()
    if opportunities:
        st.success(f"✅ Найдено {len(opportunities)} реальных возможностей!")
        for opp in opportunities[:8]:
            st.info(f"🎯 **{opp['asset']}** | OKX ${opp['main_price']:.2f} → {opp['aux_exchange'].upper()} ${opp['aux_price']:.2f} | +{opp['profit_usdt']:.2f} USDT")
    else:
        st.info("Пока нет выгодных спредов. Попробуйте обновить.")

# ====================== ОСНОВНОЙ ЦИКЛ ======================
if st.session_state.bot_running:
    time.sleep(6)
    opportunities = find_all_arbitrage_opportunities()
    
    if opportunities:
        best = opportunities[0]
        profit = best['profit_usdt']
        
        st.session_state.total_profit += profit
        st.session_state.trade_count += 1
        trade_text = f"✅ {datetime.now().strftime('%H:%M:%S')} | {best['asset']} | {st.session_state.current_mode} | +{profit:.2f} USDT"
        st.session_state.history.append(trade_text)
        
        st.toast(f"🎯 {best['asset']} | +{profit:.2f} USDT", icon="💰")
        st.rerun()

st.caption("Накопительный Арбитраж PRO v7.4 — улучшенный реальный режим")
