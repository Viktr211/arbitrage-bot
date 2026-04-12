import streamlit as st
import time
import random
import json
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

# Загрузка конфига с защитой
try:
    with open('config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)
except:
    config = {
        "asset_config": [
            {"asset": "BTC"}, {"asset": "ETH"}, {"asset": "SOL"}, {"asset": "BNB"},
            {"asset": "XRP"}, {"asset": "ADA"}, {"asset": "AVAX"}, {"asset": "LINK"}
        ],
        "target_asset_amount": {"BTC": 0.5, "ETH": 2.0, "SOL": 50.0, "BNB": 20.0}
    }

ASSET_CONFIG = config.get('asset_config', [])
TARGET_ASSET_AMOUNT = config.get('target_asset_amount', {})

# Сессия
if 'bot_running' not in st.session_state:
    st.session_state.bot_running = False
if 'mode' not in st.session_state:
    st.session_state.mode = "Демо"
if 'total_profit' not in st.session_state:
    st.session_state.total_profit = 0.0
if 'trade_count' not in st.session_state:
    st.session_state.trade_count = 0
if 'history' not in st.session_state:
    st.session_state.history = []
if 'fixed_profit' not in st.session_state:
    st.session_state.fixed_profit = 0.0

st.markdown('<h1 class="main-header">🚀 ARBITRAGE BOT PRO</h1>', unsafe_allow_html=True)

# Режим
mode = st.radio("Режим работы", ["Демо (Симуляция)", "Реальный"], horizontal=True)
st.session_state.mode = "Демо" if "Демо" in mode else "Реальный"

if st.session_state.mode == "Реальный":
    st.error("⚠️ Реальный режим использует настоящие деньги!")

# Top Bar
col1, col2, col3 = st.columns([3, 2, 2])
with col1:
    st.metric("💰 Прибыль всего", f"{st.session_state.total_profit:.4f} USDT")
with col2:
    st.metric("📊 Сделок", st.session_state.trade_count)
with col3:
    st.metric("💵 Фиксировано", f"{st.session_state.fixed_profit:.2f} USDT")

# Кнопки управления
c1, c2, c3 = st.columns(3)
if c1.button("▶ СТАРТ", type="primary", use_container_width=True):
    st.session_state.bot_running = True
    st.success("Бот запущен!")
if c2.button("⏸ ПАУЗА", use_container_width=True):
    st.session_state.bot_running = False
    st.warning("Бот на паузе")
if c3.button("⏹ СТОП", use_container_width=True):
    st.session_state.bot_running = False
    st.error("Бот остановлен")

# Вкладки
tab1, tab2, tab3, tab4 = st.tabs(["📊 Dashboard", "📈 Графики", "📦 Активы", "📜 История"])

with tab1:
    st.subheader("Главный дашборд")
    st.write(f"**Режим:** {st.session_state.mode}")

with tab2:
    st.subheader("📈 Графики")
    selected = st.selectbox("Выберите токен", [a.get('asset', 'BTC') for a in ASSET_CONFIG] or ["BTC"])
    st.line_chart([random.randint(100, 600) for _ in range(30)], use_container_width=True)

with tab3:
    st.subheader("📦 Активы и цели")
    cols = st.columns(5)
    for i, asset in enumerate(ASSET_CONFIG):
        with cols[i % 5]:
            target = TARGET_ASSET_AMOUNT.get(asset.get('asset'), 0)
            st.metric(asset.get('asset'), f"Цель: {target}")

with tab4:
    st.subheader("📜 История")
    if st.session_state.history:
        for trade in reversed(st.session_state.history[-20:]):
            st.write(trade)
    else:
        st.info("Пока нет сделок. Запустите бота.")

# ================== СИМУЛЯЦИЯ С 50/50 ==================
if st.session_state.bot_running:
    time.sleep(1.8)
    asset_list = [a.get('asset', 'BTC') for a in ASSET_CONFIG]
    if not asset_list:
        asset_list = ["BTC"]
    asset = random.choice(asset_list)
    gross_profit = round(random.uniform(0.8, 5.5), 4)

    fixed = round(gross_profit * 0.5, 4)
    reinvest = round(gross_profit * 0.5, 4)

    st.session_state.total_profit += gross_profit
    st.session_state.fixed_profit += fixed
    st.session_state.trade_count += 1

    trade_text = f"✅ {datetime.now().strftime('%H:%M:%S')} | {asset}/USDT | +{gross_profit} | Фикс: {fixed} | Реинвест: {reinvest}"
    st.session_state.history.append(trade_text)

    st.rerun()

st.caption("Веб-версия 2.8 — 50/50 механизм")
