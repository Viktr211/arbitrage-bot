
import streamlit as st
import time
import random
import json
from datetime import datetime, date

st.set_page_config(page_title="Arbitrage Bot PRO", layout="wide", page_icon="🚀")

# ====================== СТИЛЬ (только тёмная тема + уменьшенный шрифт) ======================
st.markdown("""
<style>
    .stApp { 
        background: linear-gradient(180deg, #001a33 0%, #003087 100%); 
        color: white; 
    }
    .main-header { 
        font-size: 26px; 
        font-weight: bold; 
        color: #00D4FF; 
        text-align: center; 
        margin-bottom: 8px;
    }
    .stMetric label { font-size: 14px !important; }
    .stMetric div[data-testid="stMetricValue"] { font-size: 22px !important; font-weight: bold; }
    .stButton>button { 
        border-radius: 30px; 
        height: 44px; 
        font-weight: bold; 
        font-size: 15px;
    }
    .stTabs [data-baseweb="tab-list"] button {
        font-size: 15.5px;
        font-weight: 600;
    }
    p, span, div, li {
        font-size: 15px !important;
    }
    h1, h2, h3 {
        font-size: 22px !important;
    }
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

st.markdown('<h1 class="main-header">🚀 ARBITRAGE BOT PRO</h1>', unsafe_allow_html=True)

# Режим Демо / Реальный
mode = st.radio("Выберите режим работы", ["Демо (Симуляция)", "Реальный"], horizontal=True)
st.session_state.mode = "Демо" if "Демо" in mode else "Реальный"

if st.session_state.mode == "Реальный":
    st.error("⚠️ Реальный режим использует настоящие деньги. Будьте очень осторожны!")

# Top Bar
col1, col2, col3 = st.columns([3, 2, 2])
with col1:
    st.metric("💰 Прибыль", f"{st.session_state.total_profit:.4f} USDT")
with col2:
    st.metric("📊 Сделок", st.session_state.trade_count)
with col3:
    status = "🟢 Работает" if st.session_state.bot_running else "🔴 Остановлен"
    st.metric("Статус", f"{status} — {st.session_state.mode}")

# Кнопки Регистрация и Вход
auth1, auth2 = st.columns(2)
with auth1:
    if st.button("👤 Регистрация", use_container_width=True):
        st.info("Регистрация будет доступна позже")
with auth2:
    if st.button("🔑 Вход", use_container_width=True):
        st.info("Вход будет доступен позже")

# Кнопки управления (капсулы)
c1, c2, c3 = st.columns(3)
if c1.button("▶ СТАРТ", type="primary", use_container_width=True):
    st.session_state.bot_running = True
    st.success(f"Бот запущен в {st.session_state.mode} режиме!")

if c2.button("⏸ ПАУЗА", use_container_width=True):
    st.session_state.bot_running = False
    st.warning("Бот на паузе")

if c3.button("⏹ СТОП", use_container_width=True):
    st.session_state.bot_running = False
    st.error("Бот остановлен")

# Вкладки
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 Dashboard", "📈 Графики", "📦 Активы", "📜 Текущие сделки", "📚 Архив по дням"])

with tab1:
    st.subheader("Главный дашборд")
    st.write(f"**Текущий режим:** {st.session_state.mode}")

with tab2:
    st.subheader("📈 Графики")
    selected = st.selectbox("Выберите токен", [a.get('asset', 'BTC') for a in ASSET_CONFIG])
    st.line_chart([random.randint(100, 600) for _ in range(30)], use_container_width=True)

with tab3:
    st.subheader("📦 Активы и цели")
    cols = st.columns(5)
    for i, asset in enumerate(ASSET_CONFIG):
        with cols[i % 5]:
            target = TARGET_ASSET_AMOUNT.get(asset.get('asset'), 0)
            st.metric(
                label=asset.get('asset'),
                value=f"Цель: {target}",
                delta=" "
            )

with tab4:
    st.subheader("📜 Текущие сделки")
    if st.session_state.history:
        for trade in reversed(st.session_state.history[-25:]):
            st.write(trade)
    else:
        st.info("Пока нет сделок. Запустите бота.")

with tab5:
    st.subheader("📚 Архив по дням")
    today = date.today().strftime("%Y-%m-%d")
    
    if st.button("Показать сделки за сегодня"):
        today_trades = [t for t in st.session_state.history if today in t]
        if today_trades:
            for t in today_trades:
                st.write(t)
        else:
            st.write("Сегодня сделок пока нет.")

    if st.button("Показать всю историю"):
        for trade in reversed(st.session_state.history):
            st.write(trade)

# ================== СИМУЛЯЦИЯ ==================
if st.session_state.bot_running:
    time.sleep(1.8)
    asset = random.choice([a.get('asset', 'BTC') for a in ASSET_CONFIG])
    profit = round(random.uniform(0.8, 8.5), 4)
    
    st.session_state.total_profit += profit
    st.session_state.trade_count += 1
    
    trade_text = f"✅ {datetime.now().strftime('%H:%M:%S')} | {asset}/USDT | +{profit} USDT"
    st.session_state.history.append(trade_text)
    
    st.rerun()

st.caption("Веб-версия 2.7 — уменьшен шрифт, только тёмная тема")