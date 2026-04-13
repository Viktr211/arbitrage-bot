import streamlit as st
import time
import random
import json
import ccxt
import pandas as pd
from datetime import datetime
import os

st.set_page_config(page_title="Накопительный Арбитраж", layout="wide", page_icon="🚀")

st.markdown("""
<style>
    .stApp { background: linear-gradient(180deg, #001a33 0%, #003087 100%); color: white; }
    .main-header { font-size: 28px; font-weight: bold; color: #00D4FF; text-align: center; }
    .stButton>button { border-radius: 30px; height: 48px; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# ====================== КОНФИГУРАЦИЯ ======================
DEFAULT_ASSETS = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "LINK", "SUI", "HYPE"]
MAIN_EXCHANGE = "okx"
AUX_EXCHANGES = ["gateio", "kucoin"]

# ====================== СЕССИЯ ======================
if 'username' not in st.session_state:
    st.session_state.username = "cb777899"
if 'exchanges' not in st.session_state:
    st.session_state.exchanges = None
if 'total_profit' not in st.session_state:
    st.session_state.total_profit = 0.0
if 'trade_count' not in st.session_state:
    st.session_state.trade_count = 0
if 'history' not in st.session_state:
    st.session_state.history = []

st.markdown('<h1 class="main-header">🚀 НАКОПИТЕЛЬНЫЙ АРБИТРАЖ PRO</h1>', unsafe_allow_html=True)
st.write(f"👤 **{st.session_state.username}**")

# ====================== ПОДКЛЮЧЕНИЕ К БИРЖАМ ======================
@st.cache_resource
def init_exchanges():
    exchanges = {}
    for ex_name in [MAIN_EXCHANGE] + AUX_EXCHANGES:
        try:
            exchange = getattr(ccxt, ex_name)({'enableRateLimit': True})
            exchange.fetch_ticker('BTC/USDT')
            exchanges[ex_name] = exchange
            st.success(f"✅ {ex_name.upper()} — подключена")
        except Exception as e:
            st.warning(f"⚠️ {ex_name.upper()}: {str(e)[:50]}")
    return exchanges

# Инициализируем биржи
if st.session_state.exchanges is None:
    with st.spinner("Подключение к биржам..."):
        st.session_state.exchanges = init_exchanges()

# ====================== ФУНКЦИИ ПОЛУЧЕНИЯ ЦЕН ======================
# Без кэширования, чтобы избежать ошибок с нехэшируемыми объектами
def get_price(exchange, symbol):
    try:
        ticker = exchange.fetch_ticker(f"{symbol}/USDT")
        return ticker['last']
    except:
        return None

# ====================== СТАТИСТИКА ======================
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("💰 Общая прибыль", f"{st.session_state.total_profit:.2f} USDT")
with col2:
    st.metric("📊 Сделок", st.session_state.trade_count)
with col3:
    st.metric("🏦 Главная биржа", MAIN_EXCHANGE.upper())
with col4:
    st.metric("🔄 Вспом. биржи", ", ".join([ex.upper() for ex in AUX_EXCHANGES]))

# ====================== КНОПКИ ======================
c1, c2, c3 = st.columns(3)
with c1:
    demo_mode = st.checkbox("🎮 Демо-режим (симуляция)", value=True)
with c2:
    if st.button("🔄 Найти арбитраж", type="primary", use_container_width=True):
        st.cache_data.clear()
with c3:
    if st.button("🎯 Тестовая сделка", use_container_width=True):
        if demo_mode:
            profit = round(random.uniform(0.5, 3.0), 2)
            st.session_state.total_profit += profit
            st.session_state.trade_count += 1
            trade_text = f"✅ {datetime.now().strftime('%H:%M:%S')} | ТЕСТОВАЯ | +{profit} USDT"
            st.session_state.history.append(trade_text)
            st.success(f"✅ Тестовая сделка! +{profit} USDT")
            st.rerun()
        else:
            st.warning("Включите демо-режим для тестовой сделки")

# ====================== ТАБЛИЦА ЦЕН И АРБИТРАЖ ======================
st.subheader("📊 Текущие цены и арбитражные возможности")

# Проверяем, что биржи подключены
if st.session_state.exchanges:
    for asset in DEFAULT_ASSETS:
        st.write(f"**{asset}/USDT**")
        
        # Получаем цены со всех бирж
        prices = {}
        cols = st.columns(len([MAIN_EXCHANGE] + AUX_EXCHANGES) + 1)
        cols[0].write("Биржа")
        
        # Заголовки
        for i, ex_name in enumerate([MAIN_EXCHANGE] + AUX_EXCHANGES):
            cols[i+1].write(f"**{ex_name.upper()}**")
        
        # Цены
        price_cols = st.columns(len([MAIN_EXCHANGE] + AUX_EXCHANGES) + 1)
        price_cols[0].write("Цена")
        
        for i, ex_name in enumerate([MAIN_EXCHANGE] + AUX_EXCHANGES):
            if ex_name in st.session_state.exchanges:
                price = get_price(st.session_state.exchanges[ex_name], asset)
                if price:
                    prices[ex_name] = price
                    price_cols[i+1].write(f"${price:,.2f}")
                else:
                    price_cols[i+1].write("❌")
        
        # Поиск арбитража
        if len(prices) >= 2 and MAIN_EXCHANGE in prices:
            main_price = prices[MAIN_EXCHANGE]
            best_opportunity = None
            best_spread = 0
            
            for aux_ex in AUX_EXCHANGES:
                if aux_ex in prices and prices[aux_ex]:
                    aux_price = prices[aux_ex]
                    if main_price > aux_price:
                        spread = (main_price - aux_price) / aux_price * 100
                        if spread > best_spread:
                            best_spread = spread
                            best_opportunity = (aux_ex, aux_price, spread)
            
            if best_opportunity and best_spread > 0.05:
                aux_ex, aux_price, spread = best_opportunity
                profit = round((main_price - aux_price) - (main_price * 0.001) - (aux_price * 0.001), 2)
                st.info(f"🎯 **АРБИТРАЖ!** {asset}: продать на {MAIN_EXCHANGE.upper()} (${main_price:.2f}), купить на {aux_ex.upper()} (${aux_price:.2f}) → +{profit:.2f} USDT (спред {spread:.2f}%)")
            else:
                st.caption(f"📊 Нет выгодного арбитража для {asset} (максимальный спред: {best_spread:.2f}%)")
        
        st.divider()
else:
    st.error("❌ Биржи не подключены. Проверьте интернет-соединение.")

# ====================== ИСТОРИЯ ======================
with st.expander("📜 История сделок"):
    if st.session_state.history:
        for trade in reversed(st.session_state.history[-20:]):
            st.write(trade)
        if st.button("🗑 Очистить историю"):
            st.session_state.history = []
            st.rerun()
    else:
        st.info("Нет сделок. Нажмите 'Тестовая сделка' для проверки.")

st.caption("🚀 Накопительный арбитраж — токены растут в цене, а арбитраж приносит дополнительную прибыль")
