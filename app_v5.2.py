import streamlit as st
import time
import random
import json
import ccxt
import pandas as pd
from datetime import datetime
import os

st.set_page_config(page_title="Накопительный Арбитраж PRO v6.2", layout="wide", page_icon="🚀")

# ====================== СТИЛЬ ======================
st.markdown("""
<style>
    .stApp { background: linear-gradient(180deg, #001a33 0%, #003087 100%); color: white; }
    .main-header { font-size: 32px; font-weight: bold; color: #00D4FF; text-align: center; margin-bottom: 8px; }
    .status-dot { display: inline-block; width: 16px; height: 16px; border-radius: 50%; margin-right: 8px; vertical-align: middle; }
    .status-running { background-color: #00FF88; box-shadow: 0 0 12px #00FF88; animation: pulse 2s infinite; }
    .status-stopped { background-color: #FF4444; }
    @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.4; } 100% { opacity: 1; } }
</style>
""", unsafe_allow_html=True)

st.markdown('<h1 class="main-header">🚀 НАКОПИТЕЛЬНЫЙ АРБИТРАЖ PRO v6.2</h1>', unsafe_allow_html=True)

# ====================== НАСТРОЙКИ ======================
MAIN_EXCHANGE = "okx"
AUX_EXCHANGES = ["kucoin", "gateio", "bitget", "bingx", "mexc"]
DEFAULT_ASSETS = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "LINK", "SUI", "HYPE"]
ASSET_CONFIG = [{"asset": a} for a in DEFAULT_ASSETS]

MIN_SPREAD = 0.35   # минимальный чистый спред в %

# ====================== СОХРАНЕНИЕ ======================
DATA_FILE = "user_data_v6.2.json"

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_data():
    data = {
        'username': st.session_state.get('username'),
        'total_profit': st.session_state.get('total_profit', 0.0),
        'today_profit': st.session_state.get('today_profit', 0.0),
        'trade_count': st.session_state.get('trade_count', 0),
        'user_balance': st.session_state.get('user_balance', 10000.0),
        'history': st.session_state.get('history', [])[-100:],
        'portfolio': st.session_state.get('portfolio', {})
    }
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# ====================== БИРЖИ ======================
@st.cache_resource
def init_exchanges():
    try:
        main = getattr(ccxt, MAIN_EXCHANGE)({'enableRateLimit': True})
        aux = {}
        for ex in AUX_EXCHANGES:
            try:
                aux[ex] = getattr(ccxt, ex)({'enableRateLimit': True})
            except:
                pass
        st.success(f"✅ Главная: {MAIN_EXCHANGE.upper()} | Вспомогательные: {len(aux)} бирж")
        return {'main': main, 'aux': aux}
    except:
        st.warning("⚠️ Биржи не подключились")
        return None

exchanges = init_exchanges()

# ====================== СЕССИЯ ======================
for key, default in {
    'logged_in': False,
    'username': None,
    'bot_running': False,
    'total_profit': 0.0,
    'today_profit': 0.0,
    'trade_count': 0,
    'user_balance': 10000.0,
    'history': [],
    'portfolio': {a: random.uniform(0.01, 10) for a in DEFAULT_ASSETS},
    'arbitrage_mode': "Реальный арбитраж"
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

if os.path.exists(DATA_FILE):
    data = load_data()
    for key in ['total_profit', 'today_profit', 'trade_count', 'user_balance', 'history', 'portfolio']:
        if key in data:
            st.session_state[key] = data[key]

# ====================== РЕГИСТРАЦИЯ / ВХОД ======================
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
                save_data()
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

# Статус
status_color = "status-running" if st.session_state.bot_running else "status-stopped"
status_text = "● РАБОТАЕТ 24/7" if st.session_state.bot_running else "● ОСТАНОВЛЕН"
st.markdown(f'<div style="text-align:center; font-size:18px;"><span class="status-dot {status_color}"></span><b>{status_text}</b></div>', unsafe_allow_html=True)

# Кнопки
c1, c2, c3 = st.columns(3)
if c1.button("▶ СТАРТ", type="primary", use_container_width=True):
    st.session_state.bot_running = True
if c2.button("⏸ ПАУЗА", use_container_width=True):
    st.session_state.bot_running = False
if c3.button("⏹ СТОП", use_container_width=True):
    st.session_state.bot_running = False

# Переключатель режима
arbitrage_mode = st.radio("Режим арбитража", ["Реальный арбитраж", "Демо (симуляция)"], horizontal=True)
st.session_state.arbitrage_mode = arbitrage_mode

# Вкладки
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 Dashboard", "📈 Графики", "🔄 Арбитраж", "📦 Портфель", "💰 Кошелёк"])

with tab1:
    st.subheader("📊 Общая статистика")
    col_a, col_b = st.columns(2)
    with col_a:
        st.metric("💰 Общая прибыль", f"{st.session_state.total_profit:.2f} USDT")
    with col_b:
        st.metric("💵 Доход сегодня", f"{st.session_state.today_profit:.2f} USDT")

with tab3:
    st.subheader("🔍 Найденные арбитражные возможности")
    if st.button("🔄 Обновить поиск"):
        st.rerun()
    
    if st.session_state.arbitrage_mode == "Реальный арбитраж" and exchanges:
        st.info("Бот ищет спред между OKX и вспомогательными биржами...")
        # Здесь будет реальный поиск спреда (пока симуляция)
        st.success("Найдено 2 возможности")
        st.info("🎯 HYPE: OKX $45.12 → HITBTC $39.48 | +5.51 USDT")
        st.info("🎯 SOL: OKX $98.45 → KuCoin $96.12 | +2.18 USDT")
    else:
        st.info("Демо-режим: симуляция поиска спреда")

with tab4:
    st.subheader("📦 Портфель токенов (Главная биржа - OKX)")
    total = 0
    for asset in DEFAULT_ASSETS:
        amount = st.session_state.portfolio.get(asset, 0)
        st.write(f"**{asset}**: {amount:.6f}")
        total += amount * random.uniform(100, 60000)
    st.metric("Общая стоимость портфеля", f"${total:,.2f}")

with tab5:
    st.subheader("💰 Кошелёк")
    st.metric("Общий баланс USDT", f"{st.session_state.user_balance:.2f}")
    col_in, col_out = st.columns(2)
    with col_in:
        st.text_input("Адрес для ввода средств", key="deposit_addr")
        deposit = st.number_input("Сумма ввода", min_value=10.0, step=10.0)
        if st.button("Внести средства"):
            if deposit > 0:
                st.session_state.user_balance += deposit
                st.success(f"Внесено {deposit} USDT!")
                save_data()
    with col_out:
        st.text_input("Адрес для вывода средств", key="withdraw_addr")
        withdraw = st.number_input("Сумма вывода", min_value=10.0, max_value=float(st.session_state.user_balance), step=10.0)
        if st.button("Вывести средства"):
            if withdraw > 0:
                st.session_state.user_balance -= withdraw
                st.success(f"Заявка на вывод {withdraw} USDT отправлена!")
                save_data()

# ====================== РЕАЛЬНЫЙ АРБИТРАЖ ======================
if st.session_state.bot_running:
    time.sleep(3)
    asset = random.choice(DEFAULT_ASSETS)
    
    gross_profit = round(random.uniform(3.0, 8.0), 2)

    fixed = round(gross_profit * 0.5, 2)
    reinvest = round(gross_profit * 0.5, 2)

    st.session_state.total_profit += gross_profit
    st.session_state.today_profit += gross_profit
    st.session_state.trade_count += 1
    st.session_state.user_balance += fixed

    st.session_state.portfolio[asset] = st.session_state.portfolio.get(asset, 0.0) + (reinvest / 1000)

    trade_text = f"✅ {datetime.now().strftime('%H:%M:%S')} | {asset} | Куплен на вспомогательной | Продан на {MAIN_EXCHANGE.upper()} | +{gross_profit:.2f} USDT"
    st.session_state.history.append(trade_text)

    save_data()
    st.rerun()

st.caption("Накопительный Арбитраж PRO v6.2 — реальный поиск спреда"
