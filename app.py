import streamlit as st
import time
import random
import json
from datetime import datetime

st.set_page_config(page_title="Arbitrage Bot PRO", layout="wide", page_icon="🚀")

st.markdown("""
<style>
    .stApp { background: linear-gradient(180deg, #001a33 0%, #003087 100%); color: white; }
    .main-header { font-size: 26px; font-weight: bold; color: #00D4FF; text-align: center; }
    .stButton>button { border-radius: 30px; height: 44px; font-weight: bold; }
    .stMetric label { font-size: 14px !important; }
    .stMetric div[data-testid="stMetricValue"] { font-size: 22px !important; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

st.markdown('<h1 class="main-header">🚀 ARBITRAGE BOT PRO</h1>', unsafe_allow_html=True)

# Загрузка конфига
try:
    with open('config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)
except:
    config = {
        "assets": ["BTC", "ETH", "BNB", "SOL"],
        "targets": {"BTC": 0.05, "ETH": 0.5, "BNB": 1.0, "SOL": 5.0}
    }

ASSETS = config.get("assets", ["BTC", "ETH", "BNB", "SOL"])
TARGETS = config.get("targets", {"BTC": 0.05, "ETH": 0.5})

# Сессия
if 'bot_running' not in st.session_state:
    st.session_state.bot_running = False
if 'total_profit' not in st.session_state:
    st.session_state.total_profit = 0.0
if 'trade_count' not in st.session_state:
    st.session_state.trade_count = 0
if 'history' not in st.session_state:
    st.session_state.history = []
if 'balances' not in st.session_state:
    st.session_state.balances = {asset: 0.0 for asset in ASSETS}

# Функция получения цены (симуляция для начала)
def get_price(asset):
    # Позже заменим на реальные цены с бирж
    return round(random.uniform(100, 50000), 2)

# Верхняя панель
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("💰 Общая прибыль", f"{st.session_state.total_profit:.4f} USDT")
with col2:
    st.metric("📊 Сделок", st.session_state.trade_count)
with col3:
    status = "🟢 Работает" if st.session_state.bot_running else "🔴 Остановлен"
    st.metric("Статус", status)

# Кнопки
c1, c2, c3 = st.columns(3)
if c1.button("▶ СТАРТ", type="primary", use_container_width=True):
    st.session_state.bot_running = True
if c2.button("⏸ ПАУЗА", use_container_width=True):
    st.session_state.bot_running = False
if c3.button("⏹ СТОП", use_container_width=True):
    st.session_state.bot_running = False

# Вкладки
tab1, tab2, tab3 = st.tabs(["📊 Dashboard", "📈 Цены", "📜 История"])

# TAB 1: Dashboard
with tab1:
    st.subheader("📊 Арбитражные возможности")
    for asset in ASSETS:
        price = get_price(asset)
        target = TARGETS.get(asset, 0)
        current = st.session_state.balances.get(asset, 0)
        col_a, col_b, col_c = st.columns([2, 1, 1])
        col_a.write(f"**{asset}/USDT**")
        col_b.write(f"💰 ${price:,.2f}")
        col_c.write(f"📦 {current:.6f} / {target}")
        st.progress(min(current/target, 1.0) if target > 0 else 0)
        st.divider()

# TAB 2: Цены
with tab2:
    st.subheader("📈 Текущие цены")
    for asset in ASSETS:
        price = get_price(asset)
        st.metric(asset, f"${price:,.2f}")

# TAB 3: История
with tab3:
    st.subheader("📜 Последние сделки")
    if st.session_state.history:
        for trade in reversed(st.session_state.history[-25:]):
            st.write(trade)
    else:
        st.info("Пока нет сделок. Запустите бота.")

# Основная логика
if st.session_state.bot_running:
    time.sleep(3)
    profit = round(random.uniform(0.5, 3.0), 4)
    st.session_state.total_profit += profit
    st.session_state.trade_count += 1
    asset = random.choice(ASSETS)
    st.session_state.balances[asset] = st.session_state.balances.get(asset, 0) + 0.001
    trade_text = f"✅ {datetime.now().strftime('%H:%M:%S')} | {asset}/USDT | +{profit} USDT"
    st.session_state.history.append(trade_text)
    st.rerun()

st.caption("🚀 Arbitrage Bot PRO — реальные цены будут добавлены в следующем обновлении")
