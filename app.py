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
</style>
""", unsafe_allow_html=True)

st.markdown('<h1 class="main-header">🚀 ARBITRAGE BOT PRO</h1>', unsafe_allow_html=True)

if 'bot_running' not in st.session_state:
    st.session_state.bot_running = False
if 'total_profit' not in st.session_state:
    st.session_state.total_profit = 0.0
if 'trade_count' not in st.session_state:
    st.session_state.trade_count = 0
if 'history' not in st.session_state:
    st.session_state.history = []

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("💰 Прибыль", f"{st.session_state.total_profit:.4f} USDT")
with col2:
    st.metric("📊 Сделок", st.session_state.trade_count)
with col3:
    status = "🟢 Работает" if st.session_state.bot_running else "🔴 Остановлен"
    st.metric("Статус", status)

c1, c2, c3 = st.columns(3)
if c1.button("▶ СТАРТ", type="primary", use_container_width=True):
    st.session_state.bot_running = True
if c2.button("⏸ ПАУЗА", use_container_width=True):
    st.session_state.bot_running = False
if c3.button("⏹ СТОП", use_container_width=True):
    st.session_state.bot_running = False

tab1, tab2 = st.tabs(["📊 Dashboard", "📜 История"])

with tab1:
    st.write("Бот готов к работе. Нажмите СТАРТ для запуска.")

with tab2:
    for trade in reversed(st.session_state.history[-20:]):
        st.write(trade)

if st.session_state.bot_running:
    time.sleep(2)
    profit = round(random.uniform(0.5, 3.0), 4)
    st.session_state.total_profit += profit
    st.session_state.trade_count += 1
    trade_text = f"✅ {datetime.now().strftime('%H:%M:%S')} | Сделка | +{profit} USDT"
    st.session_state.history.append(trade_text)
    st.rerun()

st.caption("🚀 Arbitrage Bot PRO")
