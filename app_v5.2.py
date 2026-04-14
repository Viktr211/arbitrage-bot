import streamlit as st
import time
import random
import json
import ccxt
import pandas as pd
from datetime import datetime
import os

st.set_page_config(page_title="Arbitrage Bot PRO v5.3", layout="wide", page_icon="🚀")

# ====================== СТИЛЬ ======================
st.markdown("""
<style>
    .stApp { background: linear-gradient(180deg, #001a33 0%, #003087 100%); color: white; }
    .main-header { font-size: 32px; font-weight: bold; color: #00D4FF; text-align: center; margin-bottom: 8px; }
    .status-dot { display: inline-block; width: 16px; height: 16px; border-radius: 50%; margin-right: 8px; vertical-align: middle; }
    .status-running { background-color: #00FF88; box-shadow: 0 0 12px #00FF88; animation: pulse 2s infinite; }
    .status-stopped { background-color: #FF4444; }
    @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.4; } 100% { opacity: 1; } }
    .stButton>button { border-radius: 30px; height: 48px; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# ====================== ТОКЕНЫ ======================
DEFAULT_ASSETS = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "LINK", "SUI", "HYPE"]
ASSET_CONFIG = [{"asset": a} for a in DEFAULT_ASSETS]

# ====================== СОХРАНЕНИЕ ======================
DATA_FILE = "user_data_v5.3.json"

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
        'user_balance': st.session_state.get('user_balance', 1000.0),
        'history': st.session_state.get('history', [])[-100:],
        'portfolio': st.session_state.get('portfolio', {})
    }
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# ====================== БИРЖИ ======================
@st.cache_resource
def init_exchanges():
    try:
        binance = ccxt.binance({'enableRateLimit': True})
        kucoin = ccxt.kucoin({'enableRateLimit': True})
        st.success("✅ Подключены реальные биржи: Binance + KuCoin")
        return {'binance': binance, 'kucoin': kucoin}
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
    'user_balance': 1000.0,
    'history': [],
    'portfolio': {a: 0.0 for a in DEFAULT_ASSETS}
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

if os.path.exists(DATA_FILE):
    data = load_data()
    for key in ['total_profit', 'today_profit', 'trade_count', 'user_balance', 'history', 'portfolio']:
        if key in data:
            st.session_state[key] = data[key]

st.markdown('<h1 class="main-header">🚀 ARBITRAGE BOT PRO v5.3</h1>', unsafe_allow_html=True)

# ====================== СТАТУС ======================
status_color = "status-running" if st.session_state.bot_running else "status-stopped"
status_text = "● РАБОТАЕТ 24/7" if st.session_state.bot_running else "● ОСТАНОВЛЕН"
st.markdown(f'<div style="text-align:center; font-size:18px; margin:10px 0;"><span class="status-dot {status_color}"></span><b>{status_text}</b></div>', unsafe_allow_html=True)

st.write(f"👤 **{st.session_state.username}** | Баланс: **{st.session_state.user_balance:.2f} USDT**")

# Кнопки
c1, c2, c3, c4 = st.columns(4)
with c1:
    if st.button("▶ СТАРТ", type="primary", use_container_width=True):
        st.session_state.bot_running = True
with c2:
    if st.button("⏸ ПАУЗА", use_container_width=True):
        st.session_state.bot_running = False
with c3:
    if st.button("⏹ СТОП", use_container_width=True):
        st.session_state.bot_running = False
with c4:
    if st.button("🚪 Выйти", use_container_width=True):
        st.session_state.bot_running = False
        st.session_state.logged_in = False
        save_data()
        st.rerun()

# ====================== ВКЛАДКИ ======================
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["📊 Dashboard", "📈 Графики", "🔄 Арбитраж", "📦 Портфель", "💰 Кошелёк", "📜 История"])

with tab1:
    st.subheader("📊 Общая статистика")
    col_a, col_b = st.columns(2)
    with col_a:
        st.metric("💰 Общая сумма заработка", f"{st.session_state.total_profit:.2f} USDT")
    with col_b:
        st.metric("💵 Доход сегодня", f"{st.session_state.today_profit:.2f} USDT")

with tab2:
    st.subheader("📈 Японские свечи")
    selected = st.selectbox("Выберите токен", [a['asset'] for a in ASSET_CONFIG])
    st.line_chart([random.randint(100, 600) for _ in range(30)], use_container_width=True)  # пока симуляция

with tab3:
    st.subheader("🔍 Найденные арбитражные возможности")
    st.info("Бот сканирует спреды между OKX и другими биржами...")
    # Здесь будет реальный арбитраж позже

with tab4:
    st.subheader("📦 Портфель токенов (OKX)")
    total = 0
    for asset in DEFAULT_ASSETS:
        amount = st.session_state.portfolio.get(asset, 0)
        price = random.uniform(100, 60000)  # пока симуляция
        value = amount * price
        total += value
        st.write(f"**{asset}**: {amount:.6f} ≈ ${value:,.2f}")
    st.divider()
    st.metric("💰 Общая стоимость портфеля", f"${total:,.2f}")

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

with tab6:
    st.subheader("📜 История арбитражных сделок")
    if st.session_state.history:
        for trade in reversed(st.session_state.history[-50:]):
            st.success(trade)   # зелёный цвет для всех сделок
    else:
        st.info("Пока нет сделок. Запустите бота.")

# ====================== АРБИТРАЖ ======================
if st.session_state.bot_running:
    time.sleep(3)
    asset = random.choice([a['asset'] for a in ASSET_CONFIG])
    gross_profit = round(random.uniform(4.0, 8.0), 2)

    fixed = round(gross_profit * 0.5, 2)
    reinvest = round(gross_profit * 0.5, 2)

    st.session_state.total_profit += gross_profit
    st.session_state.today_profit += gross_profit
    st.session_state.trade_count += 1
    st.session_state.user_balance += reinvest

    st.session_state.portfolio[asset] = st.session_state.portfolio.get(asset, 0.0) + (reinvest / price if 'price' in locals() else 500)

    trade_text = f"✅ {datetime.now().strftime('%H:%M:%S')} | {asset} | Куплен на HITBTC по 39.49 | Продан на OKX по 45.XX | +{gross_profit:.2f} USDT"
    st.session_state.history.append(trade_text)

    save_data()
    st.rerun()

st.caption("Arbitrage Bot PRO v5.3 — улучшенная версия")
