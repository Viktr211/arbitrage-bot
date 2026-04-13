import streamlit as st
import time
import random
import json
import ccxt
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
import os

st.set_page_config(page_title="Накопительный Арбитраж PRO", layout="wide", page_icon="🚀")

# ====================== СТИЛЬ ======================
st.markdown("""
<style>
    .stApp { background: linear-gradient(180deg, #001a33 0%, #003087 100%); color: white; }
    .main-header { font-size: 32px; font-weight: bold; color: #00D4FF; text-align: center; margin-bottom: 20px; }
    .stButton>button { border-radius: 30px; height: 48px; font-weight: bold; }
    .arbitrage-card { background: rgba(0,255,100,0.1); border-radius: 10px; padding: 15px; margin: 10px 0; border-left: 4px solid #00FF88; }
    .no-arbitrage { background: rgba(100,100,100,0.1); border-radius: 10px; padding: 15px; margin: 10px 0; }
</style>
""", unsafe_allow_html=True)

# ====================== КОНФИГУРАЦИЯ ======================
DEFAULT_ASSETS = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "LINK", "SUI", "HYPE"]
MAIN_EXCHANGE = "okx"
AUX_EXCHANGES = ["gateio", "kucoin"]

# Параметры арбитража
MIN_SPREAD_PERCENT = 0.03  # Уменьшил до 0.03% для более частых сделок
FEE_PERCENT = 0.15  # Комиссии 0.15%

# ====================== СЕССИЯ ======================
if 'username' not in st.session_state:
    st.session_state.username = "cb777899"
if 'exchanges' not in st.session_state:
    st.session_state.exchanges = None
if 'total_profit' not in st.session_state:
    st.session_state.total_profit = 0.0
if 'today_profit' not in st.session_state:
    st.session_state.today_profit = 0.0
if 'trade_count' not in st.session_state:
    st.session_state.trade_count = 0
if 'history' not in st.session_state:
    st.session_state.history = []
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = {asset: random.uniform(0.1, 0.5) for asset in DEFAULT_ASSETS}
if 'usdt_reserves' not in st.session_state:
    st.session_state.usdt_reserves = {ex: 10000 for ex in AUX_EXCHANGES}
if 'bot_running' not in st.session_state:
    st.session_state.bot_running = False
if 'trade_mode' not in st.session_state:
    st.session_state.trade_mode = "Демо"
if 'last_update' not in st.session_state:
    st.session_state.last_update = datetime.now()

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
        except Exception as e:
            st.warning(f"⚠️ {ex_name.upper()}: {str(e)[:50]}")
    return exchanges

if st.session_state.exchanges is None:
    with st.spinner("Подключение к биржам..."):
        st.session_state.exchanges = init_exchanges()

# ====================== ФУНКЦИИ ======================
def get_price(exchange, symbol):
    try:
        ticker = exchange.fetch_ticker(f"{symbol}/USDT")
        return ticker['last']
    except:
        return None

def find_all_arbitrage_opportunities():
    """Находит все арбитражные возможности"""
    opportunities = []
    
    for asset in DEFAULT_ASSETS:
        prices = {}
        for ex_name in [MAIN_EXCHANGE] + AUX_EXCHANGES:
            if ex_name in st.session_state.exchanges:
                price = get_price(st.session_state.exchanges[ex_name], asset)
                if price:
                    prices[ex_name] = price
        
        if len(prices) >= 2 and MAIN_EXCHANGE in prices:
            main_price = prices[MAIN_EXCHANGE]
            for aux_ex in AUX_EXCHANGES:
                if aux_ex in prices:
                    aux_price = prices[aux_ex]
                    if main_price > aux_price:
                        spread_pct = (main_price - aux_price) / aux_price * 100
                        net_spread = spread_pct - FEE_PERCENT
                        profit_usdt = round((main_price - aux_price) - (main_price * 0.001) - (aux_price * 0.001), 2)
                        
                        if net_spread > MIN_SPREAD_PERCENT:
                            opportunities.append({
                                'asset': asset,
                                'main_exchange': MAIN_EXCHANGE,
                                'aux_exchange': aux_ex,
                                'main_price': main_price,
                                'aux_price': aux_price,
                                'spread_pct': round(spread_pct, 2),
                                'net_spread': round(net_spread, 2),
                                'profit_usdt': profit_usdt
                            })
    
    return sorted(opportunities, key=lambda x: x['profit_usdt'], reverse=True)

# ====================== СТАТИСТИКА ======================
col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    st.metric("💰 Общая прибыль", f"{st.session_state.total_profit:.2f} USDT")
with col2:
    st.metric("📊 Сделок", st.session_state.trade_count)
with col3:
    st.metric("🏦 Главная биржа", MAIN_EXCHANGE.upper())
with col4:
    st.metric("🔄 Бирж", f"{len(AUX_EXCHANGES)}")
with col5:
    status = "🟢 Работает" if st.session_state.bot_running else "🔴 Остановлен"
    st.metric("Бот", status)

# ====================== КНОПКИ ======================
c1, c2, c3, c4 = st.columns(4)
with c1:
    if st.button("▶ ЗАПУСТИТЬ", type="primary", use_container_width=True):
        st.session_state.bot_running = True
        st.rerun()
with c2:
    if st.button("⏸ ПАУЗА", use_container_width=True):
        st.session_state.bot_running = False
        st.rerun()
with c3:
    if st.button("⏹ СТОП", use_container_width=True):
        st.session_state.bot_running = False
        st.rerun()
with c4:
    mode = st.selectbox("Режим", ["Демо", "Реальный"], index=0)
    st.session_state.trade_mode = mode

# ====================== ВКЛАДКИ ======================
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 Арбитраж", "📈 Графики", "📦 Портфель", "💰 Кошелёк", "📜 История"])

# ====================== TAB 1: АРБИТРАЖ ======================
with tab1:
    st.subheader("🔍 Поиск арбитражных возможностей")
    
    if st.button("🔄 Обновить цены", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    
    # Текущие цены
    st.write("### 📊 Текущие цены")
    
    # Таблица цен
    price_data = []
    for asset in DEFAULT_ASSETS:
        row = {"Актив": asset}
        for ex_name in [MAIN_EXCHANGE] + AUX_EXCHANGES:
            if st.session_state.exchanges and ex_name in st.session_state.exchanges:
                price = get_price(st.session_state.exchanges[ex_name], asset)
                row[ex_name.upper()] = f"${price:,.2f}" if price else "❌"
            else:
                row[ex_name.upper()] = "❌"
        price_data.append(row)
    
    st.dataframe(pd.DataFrame(price_data), use_container_width=True, hide_index=True)
    
    # Поиск арбитража
    st.write("### 🎯 Арбитражные возможности")
    
    opportunities = find_all_arbitrage_opportunities()
    
    if opportunities:
        for opp in opportunities[:5]:
            st.markdown(f"""
            <div class="arbitrage-card">
                🎯 <b>{opp['asset']}/USDT</b><br>
                📈 Продать на <b>{opp['main_exchange'].upper()}</b>: ${opp['main_price']:,.2f}<br>
                📉 Купить на <b>{opp['aux_exchange'].upper()}</b>: ${opp['aux_price']:,.2f}<br>
                💰 Чистая прибыль: <b>+{opp['profit_usdt']:.2f} USDT</b> (спред {opp['spread_pct']}%, комиссии {FEE_PERCENT}%)<br>
                🔄 Доходность: {opp['net_spread']}%
            </div>
            """, unsafe_allow_html=True)
            
            if st.button(f"🚀 Исполнить {opp['asset']}", key=f"exec_{opp['asset']}"):
                if st.session_state.trade_mode == "Демо":
                    profit = opp['profit_usdt']
                    st.session_state.total_profit += profit
                    st.session_state.today_profit += profit
                    st.session_state.trade_count += 1
                    
                    trade_text = f"✅ {datetime.now().strftime('%H:%M:%S')} | {opp['asset']} | АРБИТРАЖ | +{profit:.2f} USDT | Продажа на {opp['main_exchange'].upper()} | Покупка на {opp['aux_exchange'].upper()}"
                    st.session_state.history.append(trade_text)
                    st.success(f"✅ Сделка исполнена! +{profit:.2f} USDT")
                    st.rerun()
                else:
                    st.warning("Реальный режим требует настройки API ключей")
    else:
        st.markdown("""
        <div class="no-arbitrage">
            📊 Арбитражных возможностей не найдено.<br>
            Текущие спреды слишком маленькие для получения прибыли после комиссий.
        </div>
        """, unsafe_allow_html=True)
        
        # Показываем ближайшие возможности
        st.write("### 📊 Ближайшие спреды")
        for asset in DEFAULT_ASSETS:
            prices = {}
            for ex_name in [MAIN_EXCHANGE] + AUX_EXCHANGES:
                if st.session_state.exchanges and ex_name in st.session_state.exchanges:
                    price = get_price(st.session_state.exchanges[ex_name], asset)
                    if price:
                        prices[ex_name] = price
            
            if len(prices) >= 2 and MAIN_EXCHANGE in prices:
                main_price = prices[MAIN_EXCHANGE]
                for aux_ex in AUX_EXCHANGES:
                    if aux_ex in prices:
                        aux_price = prices[aux_ex]
                        if main_price > aux_price:
                            spread = (main_price - aux_price) / aux_price * 100
                            st.write(f"**{asset}**: {main_price:.2f} vs {aux_price:.2f} → спред {spread:.3f}% (нужно >{MIN_SPREAD_PERCENT + FEE_PERCENT:.2f}%)")

# ====================== TAB 2: ГРАФИКИ ======================
with tab2:
    st.subheader("📈 Графики цен")
    selected_asset = st.selectbox("Выберите актив", DEFAULT_ASSETS)
    
    # Получаем исторические данные
    if st.session_state.exchanges and MAIN_EXCHANGE in st.session_state.exchanges:
        try:
            ohlcv = st.session_state.exchanges[MAIN_EXCHANGE].fetch_ohlcv(f"{selected_asset}/USDT", '1h', limit=50)
            if ohlcv:
                df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                
                fig = go.Figure(data=[go.Candlestick(
                    x=df['timestamp'],
                    open=df['open'],
                    high=df['high'],
                    low=df['low'],
                    close=df['close']
                )])
                fig.update_layout(title=f"{selected_asset}/USDT", template="plotly_dark", height=500)
                st.plotly_chart(fig, use_container_width=True)
        except:
            st.info("Не удалось загрузить график")

# ====================== TAB 3: ПОРТФЕЛЬ ======================
with tab3:
    st.subheader("📦 Портфель токенов (главная биржа)")
    
    for asset in DEFAULT_ASSETS:
        amount = st.session_state.portfolio.get(asset, 0)
        col1, col2 = st.columns(2)
        col1.write(f"**{asset}**")
        col2.write(f"{amount:.6f}")
    
    st.divider()
    st.subheader("💰 Резервы USDT")
    for ex in AUX_EXCHANGES:
        reserve = st.session_state.usdt_reserves.get(ex, 0)
        st.write(f"**{ex.upper()}**: {reserve:.2f} USDT")

# ====================== TAB 4: КОШЕЛЁК ======================
with tab4:
    st.subheader("💰 Управление средствами")
    
    col_in, col_out = st.columns(2)
    with col_in:
        deposit = st.number_input("Сумма ввода (USDT)", min_value=10.0, step=10.0)
        if st.button("💰 Внести"):
            st.session_state.usdt_reserves[AUX_EXCHANGES[0]] += deposit
            st.success(f"Внесено {deposit} USDT")
            st.rerun()
    
    with col_out:
        withdraw = st.number_input("Сумма вывода (USDT)", min_value=10.0, max_value=float(st.session_state.usdt_reserves.get(AUX_EXCHANGES[0], 0)), step=10.0)
        if st.button("📤 Вывести"):
            st.session_state.usdt_reserves[AUX_EXCHANGES[0]] -= withdraw
            st.success(f"Выведено {withdraw} USDT")
            st.rerun()

# ====================== TAB 5: ИСТОРИЯ ======================
with tab5:
    st.subheader("📜 История сделок")
    
    if st.session_state.history:
        for trade in reversed(st.session_state.history[-30:]):
            st.write(trade)
        
        if st.button("🗑 Очистить историю"):
            st.session_state.history = []
            st.rerun()
    else:
        st.info("Нет сделок. Нажмите 'Запустить' для автоматического поиска арбитража")

# ====================== АВТОМАТИЧЕСКИЙ АРБИТРАЖ ======================
if st.session_state.bot_running:
    time.sleep(5)
    
    opportunities = find_all_arbitrage_opportunities()
    
    if opportunities:
        best = opportunities[0]
        
        if st.session_state.trade_mode == "Демо":
            profit = best['profit_usdt']
            st.session_state.total_profit += profit
            st.session_state.today_profit += profit
            st.session_state.trade_count += 1
            
            # Уменьшаем резерв USDT на вспомогательной бирже
            st.session_state.usdt_reserves[best['aux_exchange']] = st.session_state.usdt_reserves.get(best['aux_exchange'], 10000) - 1000
            
            # Увеличиваем портфель на главной бирже (после перевода)
            st.session_state.portfolio[best['asset']] = st.session_state.portfolio.get(best['asset'], 0) + (1000 / best['aux_price'])
            
            trade_text = f"✅ {datetime.now().strftime('%H:%M:%S')} | {best['asset']} | АВТО-АРБИТРАЖ | +{profit:.2f} USDT | Куплен на {best['aux_exchange'].upper()} | Продан на {best['main_exchange'].upper()}"
            st.session_state.history.append(trade_text)
            st.toast(f"🎯 Авто-арбитраж по {best['asset']}! +{profit:.2f} USDT", icon="💰")
            st.rerun()
    else:
        # Небольшая задержка перед следующим поиском
        time.sleep(10)

st.caption("🚀 Накопительный арбитраж — автоматический поиск спредов между биржами")
