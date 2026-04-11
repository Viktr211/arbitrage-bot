
import streamlit as st
import time
import json
import pandas as pd
from datetime import datetime

# Импорт ccxt с обработкой ошибки
try:
    import ccxt
    CCXT_AVAILABLE = True
except ImportError:
    CCXT_AVAILABLE = False
    st.warning("⚠️ Библиотека ccxt не загружена, работаем в демо-режиме")

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
        "targets": {"BTC": 0.05, "ETH": 0.5, "BNB": 1.0, "SOL": 5.0},
        "exchanges": ["binance", "kucoin", "bybit"]
    }

ASSETS = config.get("assets", ["BTC", "ETH", "BNB", "SOL"])
TARGETS = config.get("targets", {"BTC": 0.05, "ETH": 0.5})
EXCHANGES = config.get("exchanges", ["binance", "kucoin", "bybit"])

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
if 'last_prices' not in st.session_state:
    st.session_state.last_prices = {}

# ==================== ФУНКЦИИ ПОЛУЧЕНИЯ ЦЕН ====================

@st.cache_data(ttl=30)
def get_binance_price(symbol):
    """Получает цену с Binance"""
    if not CCXT_AVAILABLE:
        return None
    try:
        exchange = ccxt.binance({'enableRateLimit': True})
        ticker = exchange.fetch_ticker(f"{symbol}/USDT")
        return ticker['last']
    except Exception as e:
        return None

@st.cache_data(ttl=30)
def get_all_prices(symbol):
    """Получает цены со всех бирж"""
    prices = {}
    if not CCXT_AVAILABLE:
        return prices
    
    for ex_name in EXCHANGES:
        try:
            exchange_class = getattr(ccxt, ex_name)
            exchange = exchange_class({'enableRateLimit': True})
            ticker = exchange.fetch_ticker(f"{symbol}/USDT")
            prices[ex_name] = ticker['last']
        except:
            prices[ex_name] = None
    return prices

def get_price_demo(asset):
    """Демо-режим (случайные цены)"""
    base_prices = {"BTC": 40000, "ETH": 2500, "BNB": 600, "SOL": 150}
    base = base_prices.get(asset, 1000)
    variation = (hash(asset + str(int(time.time()) // 60)) % 1000) / 1000 * 0.05
    return round(base * (1 + variation), 2)

# ==================== ИНТЕРФЕЙС ====================

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

# Индикатор режима
if CCXT_AVAILABLE:
    st.success("✅ Режим: реальные цены с бирж")
else:
    st.warning("⚠️ Режим: демо-цены (ccxt не установлен)")

# Вкладки
tab1, tab2, tab3, tab4 = st.tabs(["📊 Dashboard", "📈 Цены по биржам", "📦 Активы", "📜 История"])

# TAB 1: Dashboard
with tab1:
    st.subheader("📊 Арбитражные возможности")
    
    for asset in ASSETS:
        st.write(f"**{asset}/USDT**")
        
        # Получаем цены
        if CCXT_AVAILABLE:
            prices = get_all_prices(asset)
            cols = st.columns(len(EXCHANGES) + 1)
            cols[0].write("Биржа:")
            for i, ex in enumerate(EXCHANGES):
                cols[i+1].write(f"**{ex.upper()}**")
            
            cols2 = st.columns(len(EXCHANGES) + 1)
            cols2[0].write("Цена:")
            for i, ex in enumerate(EXCHANGES):
                price = prices.get(ex)
                if price:
                    cols2[i+1].write(f"${price:,.2f}")
                else:
                    cols2[i+1].write("❌")
            
            # Поиск арбитража
            valid_prices = {k: v for k, v in prices.items() if v is not None}
            if len(valid_prices) >= 2:
                min_ex = min(valid_prices, key=valid_prices.get)
                max_ex = max(valid_prices, key=valid_prices.get)
                min_price = valid_prices[min_ex]
                max_price = valid_prices[max_ex]
                spread = (max_price - min_price) / min_price * 100
                if spread > 0.3:
                    st.info(f"🎯 Арбитраж: купить на **{min_ex.upper()}** (${min_price:,.2f}), продать на **{max_ex.upper()}** (${max_price:,.2f}) → +{spread:.2f}%")
                else:
                    st.caption(f"📊 Спред: {spread:.2f}% — нет выгодных возможностей")
        else:
            price = get_price_demo(asset)
            st.write(f"💰 Цена (демо): ${price:,.2f}")
        
        # Прогресс накопления
        target = TARGETS.get(asset, 0)
        current = st.session_state.balances.get(asset, 0)
        st.write(f"📦 Накоплено: {current:.6f} / {target}")
        st.progress(min(current/target, 1.0) if target > 0 else 0)
        st.divider()

# TAB 2: Цены по биржам
with tab2:
    st.subheader("📈 Сравнение цен на биржах")
    
    for asset in ASSETS:
        st.write(f"**{asset}/USDT**")
        if CCXT_AVAILABLE:
            prices = get_all_prices(asset)
            for ex in EXCHANGES:
                price = prices.get(ex)
                if price:
                    st.write(f"  {ex.upper()}: ${price:,.2f}")
                else:
                    st.write(f"  {ex.upper()}: ❌")
        else:
            price = get_price_demo(asset)
            st.write(f"  Демо-цена: ${price:,.2f}")
        st.divider()

# TAB 3: Активы
with tab3:
    st.subheader("📦 Активы и цели накопления")
    
    for asset in ASSETS:
        target = TARGETS.get(asset, 0)
        current = st.session_state.balances.get(asset, 0)
        col_a, col_b = st.columns([1, 3])
        col_a.metric(asset, f"{current:.6f}", f"цель: {target}")
        col_b.progress(min(current/target, 1.0) if target > 0 else 0)

# TAB 4: История
with tab4:
    st.subheader("📜 Последние сделки")
    if st.session_state.history:
        for trade in reversed(st.session_state.history[-25:]):
            st.write(trade)
    else:
        st.info("Пока нет сделок. Запустите бота.")

# ==================== ОСНОВНАЯ ЛОГИКА (СИМУЛЯЦИЯ СДЕЛОК) ====================

if st.session_state.bot_running:
    time.sleep(3)
    
    # Ищем арбитражную возможность (реальную или демо)
    trade_found = False
    trade_text = ""
    profit = 0
    
    if CCXT_AVAILABLE:
        for asset in ASSETS:
            prices = get_all_prices(asset)
            valid_prices = {k: v for k, v in prices.items() if v is not None}
            if len(valid_prices) >= 2:
                min_price = min(valid_prices.values())
                max_price = max(valid_prices.values())
                spread = (max_price - min_price) / min_price * 100
                if spread > 0.5:
                    profit = round(10 * (spread / 100), 4)
                    st.session_state.total_profit += profit
                    st.session_state.trade_count += 1
                    st.session_state.balances[asset] = st.session_state.balances.get(asset, 0) + 0.001
                    trade_text = f"✅ {datetime.now().strftime('%H:%M:%S')} | {asset} | Арбитраж | +{profit} USDT"
                    st.session_state.history.append(trade_text)
                    trade_found = True
                    break
    
    if not trade_found and not CCXT_AVAILABLE:
        # Демо-режим: случайные сделки
        profit = round(random.uniform(0.5, 3.0), 4)
        st.session_state.total_profit += profit
        st.session_state.trade_count += 1
        asset = random.choice(ASSETS)
        st.session_state.balances[asset] = st.session_state.balances.get(asset, 0) + 0.001
        trade_text = f"✅ {datetime.now().strftime('%H:%M:%S')} | {asset} | +{profit} USDT (демо)"
        st.session_state.history.append(trade_text)
        trade_found = True
    
    if trade_found:
        st.toast(f"🎯 Сделка! +{profit} USDT", icon="💰")
    
    st.rerun()

st.caption("🚀 Arbitrage Bot PRO — реальный поиск арбитража между биржами")
