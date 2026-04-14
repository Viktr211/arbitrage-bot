import streamlit as st
import time
import random
import json
import ccxt
import pandas as pd
from datetime import datetime
import os

st.set_page_config(page_title="Накопительный Арбитраж PRO v6.0", layout="wide", page_icon="🚀")

# ====================== СТИЛЬ ======================
st.markdown("""
<style>
    .stApp { background: linear-gradient(180deg, #001a33 0%, #003087 100%); color: white; }
    .main-header { font-size: 34px; font-weight: bold; color: #00D4FF; text-align: center; margin-bottom: 8px; }
    .status-dot { display: inline-block; width: 16px; height: 16px; border-radius: 50%; margin-right: 8px; vertical-align: middle; }
    .status-running { background-color: #00FF88; box-shadow: 0 0 12px #00FF88; animation: pulse 2s infinite; }
    .status-stopped { background-color: #FF4444; }
    @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.4; } 100% { opacity: 1; } }
</style>
""", unsafe_allow_html=True)

st.markdown('<h1 class="main-header">🚀 НАКОПИТЕЛЬНЫЙ АРБИТРАЖ PRO v6.0</h1>', unsafe_allow_html=True)

# ====================== НАСТРОЙКИ ======================
MAIN_EXCHANGE = "okx"                    # Главная биржа (храним токены)
AUX_EXCHANGES = ["kucoin", "gateio", "bitget", "bingx", "mexc", "huobi"]
MIN_SPREAD = 0.35                        # Минимальный чистый спред в %
FEE_PERCENT = 0.10                       # Примерные комиссии

DEFAULT_ASSETS = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "LINK", "SUI", "HYPE"]
ASSET_CONFIG = [{"asset": a} for a in DEFAULT_ASSETS]

# ====================== СОХРАНЕНИЕ ======================
DATA_FILE = "user_data_v6.0.json"

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
        aux = {ex: getattr(ccxt, ex)({'enableRateLimit': True}) for ex in AUX_EXCHANGES}
        st.success(f"✅ Главная биржа: {MAIN_EXCHANGE.upper()} | Вспомогательные: {', '.join(AUX_EXCHANGES[:5])}...")
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
    'portfolio': {a: random.uniform(0.01, 10) for a in DEFAULT_ASSETS}
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

if os.path.exists(DATA_FILE):
    data = load_data()
    for key in ['total_profit', 'today_profit', 'trade_count', 'user_balance', 'history', 'portfolio']:
        if key in data:
            st.session_state[key] = data[key]

# ====================== ИНТЕРФЕЙС ======================
if not st.session_state.logged_in:
    # (регистрация/вход оставляем как было)
    st.stop()

st.write(f"👤 **{st.session_state.username}** | Баланс USDT: **{st.session_state.user_balance:.2f}**")

# Статус
status = "🟢 РАБОТАЕТ 24/7" if st.session_state.bot_running else "🔴 ОСТАНОВЛЕН"
st.markdown(f"### {status}", unsafe_allow_html=True)

c1, c2, c3 = st.columns(3)
if c1.button("▶ СТАРТ", type="primary", use_container_width=True):
    st.session_state.bot_running = True
if c2.button("⏸ ПАУЗА", use_container_width=True):
    st.session_state.bot_running = False
if c3.button("⏹ СТОП", use_container_width=True):
    st.session_state.bot_running = False

tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 Dashboard", "📈 Графики", "🔄 Арбитраж", "📦 Портфель", "📜 История"])

with tab1:
    st.subheader("📊 Общая статистика")
    col_a, col_b = st.columns(2)
    with col_a:
        st.metric("💰 Общая прибыль", f"{st.session_state.total_profit:.2f} USDT")
    with col_b:
        st.metric("💵 Доход сегодня", f"{st.session_state.today_profit:.2f} USDT")

with tab3:
    st.subheader("🔄 Арбитраж в реальном времени")
    st.info("Бот ищет спред между главной биржей и вспомогательными...")

with tab4:
    st.subheader("📦 Портфель токенов (Главная биржа)")
    total = 0
    for asset in DEFAULT_ASSETS:
        amount = st.session_state.portfolio.get(asset, 0)
        st.write(f"**{asset}**: {amount:.6f}")
        total += amount * random.uniform(100, 60000)  # временно
    st.metric("Общая стоимость портфеля", f"${total:,.2f}")

with tab5:
    st.subheader("📜 История")
    for trade in reversed(st.session_state.history[-30:]):
        st.write(trade)

# ====================== ОСНОВНАЯ ЛОГИКА ======================
if st.session_state.bot_running:
    time.sleep(3)
    asset = random.choice(DEFAULT_ASSETS)

    # Симуляция реального арбитража
    main_price = random.uniform(100, 60000)
    aux_price = main_price * (1 - random.uniform(0.006, 0.018))   # спред 0.6–1.8%
    gross_profit = round((main_price - aux_price) * 0.4, 2)       # чистая прибыль после комиссий

    fixed = round(gross_profit * 0.5, 2)
    reinvest = round(gross_profit * 0.5, 2)

    st.session_state.total_profit += gross_profit
    st.session_state.today_profit += gross_profit
    st.session_state.trade_count += 1
    st.session_state.user_balance += fixed

    # Портфель токенов почти не меняется (только небольшое увеличение)
    st.session_state.portfolio[asset] = st.session_state.portfolio.get(asset, 0.0) + (reinvest / main_price * 0.1)

    trade_text = f"✅ {datetime.now().strftime('%H:%M:%S')} | {asset} | Продан на {MAIN_EXCHANGE.upper()} по ${main_price:,.2f} | Куплен на вспомогательной по ${aux_price:,.2f} | +{gross_profit:.2f} USDT"
    st.session_state.history.append(trade_text)

    save_data()
    st.rerun()

st.caption("Накопительный Арбитраж PRO v6.0 — портфель токенов сохраняется")
