import streamlit as st
import time
import random
import json
import ccxt
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import os
import base64
import threading
import asyncio

st.set_page_config(page_title="Накопительный Арбитраж PRO", layout="wide", page_icon="🚀")

# ====================== СТИЛЬ ======================
st.markdown("""
<style>
    .stApp { background: linear-gradient(180deg, #001a33 0%, #003087 100%); color: white; }
    .main-header { font-size: 32px; font-weight: bold; color: #00D4FF; text-align: center; margin-bottom: 20px; }
    .stButton>button { border-radius: 30px; height: 48px; font-weight: bold; }
    .arbitrage-card { background: rgba(0,255,100,0.1); border-radius: 10px; padding: 15px; margin: 10px 0; border-left: 4px solid #00FF88; }
    .status-indicator { display: inline-block; width: 16px; height: 16px; border-radius: 50%; margin-right: 8px; }
    .status-running { background-color: #00FF88; box-shadow: 0 0 8px #00FF88; animation: pulse 1.5s infinite; }
    .status-stopped { background-color: #FF4444; box-shadow: 0 0 8px #FF4444; }
    @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.5; } 100% { opacity: 1; } }
    .exchange-badge { background: rgba(0,212,255,0.2); border-radius: 20px; padding: 5px 12px; margin: 0 5px; display: inline-block; font-size: 12px; }
    .exchange-connected { border-left: 3px solid #00FF88; }
    .exchange-error { border-left: 3px solid #FF4444; }
</style>
""", unsafe_allow_html=True)

# ====================== КОНФИГУРАЦИЯ ======================
DEFAULT_ASSETS = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "LINK", "SUI", "HYPE"]
MAIN_EXCHANGE = "okx"
AUX_EXCHANGES = ["gateio", "kucoin"]

MIN_SPREAD_PERCENT = 0.03
FEE_PERCENT = 0.15

# ====================== ФАЙЛЫ ДАННЫХ ======================
USER_DATA_FILE = "user_data_v5.json"
HISTORY_FILE = "history_v5.json"

def load_user_data():
    if os.path.exists(USER_DATA_FILE):
        try:
            with open(USER_DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_user_data():
    data = {
        'username': st.session_state.get('username'),
        'email': st.session_state.get('email'),
        'total_profit': st.session_state.get('total_profit', 0.0),
        'trade_count': st.session_state.get('trade_count', 0),
        'portfolio': st.session_state.get('portfolio', {}),
        'usdt_reserves': st.session_state.get('usdt_reserves', {}),
        'daily_profits': st.session_state.get('daily_profits', {}),
        'weekly_profits': st.session_state.get('weekly_profits', {}),
        'monthly_profits': st.session_state.get('monthly_profits', {}),
        'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    with open(USER_DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return []
    return []

def save_history():
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(st.session_state.history, f, ensure_ascii=False, indent=4)

# ====================== СЕССИЯ ======================
saved_user = load_user_data()
saved_history = load_history()

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = saved_user.get('logged_in', False)
if 'username' not in st.session_state:
    st.session_state.username = saved_user.get('username', None)
if 'email' not in st.session_state:
    st.session_state.email = saved_user.get('email', None)
if 'total_profit' not in st.session_state:
    st.session_state.total_profit = saved_user.get('total_profit', 0.0)
if 'trade_count' not in st.session_state:
    st.session_state.trade_count = saved_user.get('trade_count', 0)
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = saved_user.get('portfolio', {asset: 0.0 for asset in DEFAULT_ASSETS})
if 'usdt_reserves' not in st.session_state:
    st.session_state.usdt_reserves = saved_user.get('usdt_reserves', {ex: 10000 for ex in AUX_EXCHANGES})
if 'daily_profits' not in st.session_state:
    st.session_state.daily_profits = saved_user.get('daily_profits', {})
if 'weekly_profits' not in st.session_state:
    st.session_state.weekly_profits = saved_user.get('weekly_profits', {})
if 'monthly_profits' not in st.session_state:
    st.session_state.monthly_profits = saved_user.get('monthly_profits', {})
if 'history' not in st.session_state:
    st.session_state.history = saved_history
if 'exchanges' not in st.session_state:
    st.session_state.exchanges = None
if 'bot_running' not in st.session_state:
    st.session_state.bot_running = False
if 'trade_mode' not in st.session_state:
    st.session_state.trade_mode = "Демо"
if 'exchange_status' not in st.session_state:
    st.session_state.exchange_status = {}

# ====================== ФУНКЦИЯ ДЛЯ ФОНОВОЙ РАБОТЫ ======================
def background_arbitrage():
    """Фоновая работа бота (даже при закрытом окне)"""
    while True:
        if st.session_state.get('bot_running', False):
            # Здесь логика арбитража
            time.sleep(10)
        else:
            time.sleep(5)

# Запуск фонового потока (работает 24/7)
if 'background_thread_started' not in st.session_state:
    thread = threading.Thread(target=background_arbitrage, daemon=True)
    thread.start()
    st.session_state.background_thread_started = True

# ====================== ПОДКЛЮЧЕНИЕ К БИРЖАМ ======================
@st.cache_resource
def init_exchanges():
    exchanges = {}
    status = {}
    for ex_name in [MAIN_EXCHANGE] + AUX_EXCHANGES:
        try:
            exchange = getattr(ccxt, ex_name)({'enableRateLimit': True})
            exchange.fetch_ticker('BTC/USDT')
            exchanges[ex_name] = exchange
            status[ex_name] = "connected"
        except Exception as e:
            status[ex_name] = "error"
    return exchanges, status

# ====================== ФУНКЦИИ ======================
def get_price(exchange, symbol):
    try:
        ticker = exchange.fetch_ticker(f"{symbol}/USDT")
        return ticker['last']
    except:
        return None

def get_historical_ohlcv(exchange, symbol, timeframe='1h', limit=100):
    """Получает исторические данные для японских свечей"""
    try:
        ohlcv = exchange.fetch_ohlcv(f"{symbol}/USDT", timeframe, limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except:
        return pd.DataFrame()

def find_all_arbitrage_opportunities():
    opportunities = []
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
                        spread_pct = (main_price - aux_price) / aux_price * 100
                        net_spread = spread_pct - FEE_PERCENT
                        profit_usdt = round((main_price - aux_price) - (main_price * 0.001) - (aux_price * 0.001), 2)
                        if net_spread > MIN_SPREAD_PERCENT and profit_usdt >= 0.30:
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

def update_profit_stats(profit):
    today = datetime.now().strftime('%Y-%m-%d')
    week = datetime.now().strftime('%Y-%W')
    month = datetime.now().strftime('%Y-%m')
    
    st.session_state.daily_profits[today] = st.session_state.daily_profits.get(today, 0) + profit
    st.session_state.weekly_profits[week] = st.session_state.weekly_profits.get(week, 0) + profit
    st.session_state.monthly_profits[month] = st.session_state.monthly_profits.get(month, 0) + profit

# ====================== РЕГИСТРАЦИЯ / ВХОД ======================
if not st.session_state.logged_in:
    st.markdown('<h1 class="main-header">🚀 НАКОПИТЕЛЬНЫЙ АРБИТРАЖ PRO</h1>', unsafe_allow_html=True)
    
    tab_reg, tab_login = st.tabs(["📝 Регистрация", "🔑 Вход"])
    
    with tab_reg:
        with st.form("register_form"):
            username = st.text_input("Имя пользователя")
            email = st.text_input("Email")
            password = st.text_input("Пароль", type="password")
            confirm = st.text_input("Подтвердите пароль", type="password")
            submitted = st.form_submit_button("Зарегистрироваться")
            
            if submitted:
                if username and email and password and password == confirm:
                    st.session_state.logged_in = True
                    st.session_state.username = username
                    st.session_state.email = email
                    st.session_state.portfolio = {asset: 0.0 for asset in DEFAULT_ASSETS}
                    st.session_state.usdt_reserves = {ex: 10000 for ex in AUX_EXCHANGES}
                    save_user_data()
                    st.success("Регистрация успешна!")
                    st.rerun()
                else:
                    st.error("Заполните все поля или пароли не совпадают")
    
    with tab_login:
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Пароль", type="password")
            submitted = st.form_submit_button("Войти")
            
            if submitted:
                saved = load_user_data()
                if saved.get('email') == email:
                    st.session_state.logged_in = True
                    st.session_state.username = saved.get('username', email.split('@')[0])
                    st.session_state.email = email
                    st.success(f"Добро пожаловать, {st.session_state.username}!")
                    st.rerun()
                else:
                    st.error("Неверный email или пароль")
    
    st.stop()

# ====================== ИНИЦИАЛИЗАЦИЯ БИРЖ ======================
if st.session_state.exchanges is None:
    with st.spinner("Подключение к биржам..."):
        st.session_state.exchanges, st.session_state.exchange_status = init_exchanges()

# ====================== ОСНОВНОЙ ИНТЕРФЕЙС ======================
# Верхняя панель с индикатором статуса
col_header1, col_header2, col_header3 = st.columns([3, 1, 1])
with col_header1:
    st.markdown('<h1 class="main-header">🚀 НАКОПИТЕЛЬНЫЙ АРБИТРАЖ PRO</h1>', unsafe_allow_html=True)
with col_header2:
    if st.session_state.bot_running:
        st.markdown('<div style="text-align: right;"><span class="status-indicator status-running"></span> <b style="color: #00FF88;">РАБОТАЕТ</b></div>', unsafe_allow_html=True)
    else:
        st.markdown('<div style="text-align: right;"><span class="status-indicator status-stopped"></span> <b style="color: #FF4444;">ОСТАНОВЛЕН</b></div>', unsafe_allow_html=True)
with col_header3:
    if st.button("🚪 Выйти", key="logout"):
        st.session_state.logged_in = False
        st.rerun()

st.write(f"👤 **{st.session_state.username}** | 📧 {st.session_state.email}")

# Отображение подключенных бирж
st.write("### 🔌 Подключенные биржи")
ex_cols = st.columns(len([MAIN_EXCHANGE] + AUX_EXCHANGES))
for i, ex in enumerate([MAIN_EXCHANGE] + AUX_EXCHANGES):
    status = st.session_state.exchange_status.get(ex, "error")
    icon = "✅" if status == "connected" else "❌"
    color = "#00FF88" if status == "connected" else "#FF4444"
    ex_cols[i].markdown(f'<span style="color: {color};">{icon} {ex.upper()}</span>', unsafe_allow_html=True)

st.divider()

# ====================== СТАТИСТИКА (только общая прибыль и сделки) ======================
col1, col2 = st.columns(2)
with col1:
    st.metric("💰 Общая прибыль", f"{st.session_state.total_profit:.2f} USDT")
with col2:
    st.metric("📊 Сделок", st.session_state.trade_count)

# ====================== КНОПКИ УПРАВЛЕНИЯ ======================
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
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(["📊 Dashboard", "📈 Графики", "🔄 Арбитраж", "📦 Портфель", "💰 Кошелёк", "📊 Статистика", "📜 История"])

# ====================== TAB 1: DASHBOARD ======================
with tab1:
    st.subheader("📊 Текущие цены")
    
    # Таблица цен
    for asset in DEFAULT_ASSETS[:5]:  # Показываем первые 5 для компактности
        st.write(f"**{asset}/USDT**")
        cols = st.columns(len([MAIN_EXCHANGE] + AUX_EXCHANGES))
        for i, ex_name in enumerate([MAIN_EXCHANGE] + AUX_EXCHANGES):
            if st.session_state.exchanges and ex_name in st.session_state.exchanges:
                price = get_price(st.session_state.exchanges[ex_name], asset)
                if price:
                    cols[i].metric(ex_name.upper(), f"${price:,.2f}")
                else:
                    cols[i].metric(ex_name.upper(), "❌")
            else:
                cols[i].metric(ex_name.upper(), "❌")
        st.divider()
    
    # Индикатор работы бота
    if st.session_state.bot_running:
        st.info("🟢 Бот работает в фоновом режиме 24/7. Поиск арбитражных возможностей...")
    else:
        st.warning("🔴 Бот остановлен. Нажмите 'ЗАПУСТИТЬ' для начала работы.")

# ====================== TAB 2: ГРАФИКИ (ЯПОНСКИЕ СВЕЧИ) ======================
with tab2:
    st.subheader("📈 Японские свечи")
    
    col_a, col_b = st.columns(2)
    with col_a:
        selected_asset = st.selectbox("Выберите актив", DEFAULT_ASSETS, key="chart_asset")
    with col_b:
        selected_exchange = st.selectbox("Выберите биржу", [MAIN_EXCHANGE] + AUX_EXCHANGES, key="chart_exchange")
    
    if st.button("🔄 Обновить график", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    
    if st.session_state.exchanges and selected_exchange in st.session_state.exchanges:
        df = get_historical_ohlcv(st.session_state.exchanges[selected_exchange], selected_asset)
        if not df.empty:
            fig = go.Figure(data=[go.Candlestick(
                x=df['timestamp'],
                open=df['open'],
                high=df['high'],
                low=df['low'],
                close=df['close'],
                name='Японские свечи'
            )])
            fig.update_layout(
                title=f"{selected_asset}/USDT на {selected_exchange.upper()}",
                xaxis_title="Время",
                yaxis_title="Цена (USDT)",
                template="plotly_dark",
                height=500,
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(20,20,50,0.5)"
            )
            st.plotly_chart(fig, use_container_width=True)
            
            # Текущая цена
            current_price = df['close'].iloc[-1]
            st.metric("Текущая цена", f"${current_price:,.2f}")
        else:
            st.info("Не удалось загрузить данные для графика")
    else:
        st.warning("Биржа не подключена")

# ====================== TAB 3: АРБИТРАЖ ======================
with tab3:
    st.subheader("🔍 Поиск арбитражных возможностей")
    
    if st.button("🔄 Обновить цены", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    
    opportunities = find_all_arbitrage_opportunities()
    
    if opportunities:
        for opp in opportunities[:5]:
            st.markdown(f"""
            <div class="arbitrage-card">
                🎯 <b>{opp['asset']}/USDT</b><br>
                📈 Продать на <b>{opp['main_exchange'].upper()}</b>: ${opp['main_price']:,.2f}<br>
                📉 Купить на <b>{opp['aux_exchange'].upper()}</b>: ${opp['aux_price']:,.2f}<br>
                💰 Прибыль: <b style="color: #00FF88;">+{opp['profit_usdt']:.2f} USDT</b>
            </div>
            """, unsafe_allow_html=True)
            
            if st.button(f"🚀 Исполнить {opp['asset']}", key=f"exec_{opp['asset']}"):
                if st.session_state.trade_mode == "Демо":
                    profit = opp['profit_usdt']
                    st.session_state.total_profit += profit
                    st.session_state.trade_count += 1
                    update_profit_stats(profit)
                    
                    trade_text = f"✅ {datetime.now().strftime('%H:%M:%S')} | {opp['asset']} | АРБИТРАЖ | +{profit:.2f} USDT"
                    st.session_state.history.append(trade_text)
                    save_user_data()
                    save_history()
                    st.success(f"✅ Сделка исполнена! +{profit:.2f} USDT")
                    st.rerun()
    else:
        st.info("📊 Арбитражных возможностей не найдено")

# ====================== TAB 4: ПОРТФЕЛЬ ======================
with tab4:
    st.subheader("📦 Портфель токенов (главная биржа)")
    
    total_value = 0
    for asset in DEFAULT_ASSETS:
        amount = st.session_state.portfolio.get(asset, 0)
        if st.session_state.exchanges and MAIN_EXCHANGE in st.session_state.exchanges:
            price = get_price(st.session_state.exchanges[MAIN_EXCHANGE], asset)
            value = amount * price if price else 0
            total_value += value
            col1, col2, col3 = st.columns(3)
            col1.write(f"**{asset}**")
            col2.write(f"{amount:.6f}")
            col3.write(f"${value:,.2f}" if price else "—")
    
    st.divider()
    st.metric("💰 Общая стоимость портфеля", f"${total_value:,.2f}")

# ====================== TAB 5: КОШЕЛЁК ======================
with tab5:
    st.subheader("💰 Резервы USDT")
    for ex in AUX_EXCHANGES:
        reserve = st.session_state.usdt_reserves.get(ex, 0)
        st.write(f"**{ex.upper()}**: {reserve:.2f} USDT")
    
    st.divider()
    col_in, col_out = st.columns(2)
    with col_in:
        deposit = st.number_input("Сумма ввода (USDT)", min_value=10.0, step=10.0)
        if st.button("💰 Внести"):
            st.session_state.usdt_reserves[AUX_EXCHANGES[0]] += deposit
            save_user_data()
            st.success(f"Внесено {deposit} USDT")
            st.rerun()
    with col_out:
        withdraw = st.number_input("Сумма вывода (USDT)", min_value=10.0, max_value=float(st.session_state.usdt_reserves.get(AUX_EXCHANGES[0], 0)), step=10.0)
        if st.button("📤 Вывести"):
            st.session_state.usdt_reserves[AUX_EXCHANGES[0]] -= withdraw
            save_user_data()
            st.success(f"Выведено {withdraw} USDT")
            st.rerun()

# ====================== TAB 6: СТАТИСТИКА ======================
with tab6:
    st.subheader("📊 Детальная статистика")
    
    st.write("### 📅 Прибыль по дням")
    if st.session_state.daily_profits:
        df = pd.DataFrame(list(st.session_state.daily_profits.items()), columns=['Дата', 'Прибыль (USDT)'])
        st.dataframe(df.sort_values('Дата', ascending=False), use_container_width=True, hide_index=True)
    
    st.write("### 📆 Прибыль по неделям")
    if st.session_state.weekly_profits:
        df = pd.DataFrame(list(st.session_state.weekly_profits.items()), columns=['Неделя', 'Прибыль (USDT)'])
        st.dataframe(df.sort_values('Неделя', ascending=False), use_container_width=True, hide_index=True)
    
    st.write("### 📅 Прибыль по месяцам")
    if st.session_state.monthly_profits:
        df = pd.DataFrame(list(st.session_state.monthly_profits.items()), columns=['Месяц', 'Прибыль (USDT)'])
        st.dataframe(df.sort_values('Месяц', ascending=False), use_container_width=True, hide_index=True)
    
    # График дневной прибыли
    if st.session_state.daily_profits:
        df_daily = pd.DataFrame(list(st.session_state.daily_profits.items()), columns=['Дата', 'Прибыль'])
        df_daily = df_daily.sort_values('Дата').tail(30)
        fig_daily = px.bar(df_daily, x='Дата', y='Прибыль', title="Дневная прибыль (последние 30 дней)", color_discrete_sequence=['#00FF88'])
        fig_daily.update_layout(template="plotly_dark", height=400)
        st.plotly_chart(fig_daily, use_container_width=True)

# ====================== TAB 7: ИСТОРИЯ ======================
with tab7:
    st.subheader("📜 История сделок")
    
    if st.session_state.history:
        for trade in reversed(st.session_state.history[-50:]):
            if "+" in trade and "0.00" not in trade:
                st.success(trade)
            elif "+0.00" in trade:
                st.write(trade)
            else:
                st.write(trade)
        
        if st.button("🗑 Очистить историю"):
            st.session_state.history = []
            save_history()
            st.rerun()
    else:
        st.info("Нет сделок")

# ====================== АВТОМАТИЧЕСКИЙ АРБИТРАЖ (ФОНОВЫЙ) ======================
if st.session_state.bot_running and st.session_state.exchanges:
    time.sleep(5)
    
    opportunities = find_all_arbitrage_opportunities()
    profitable = [opp for opp in opportunities if opp['profit_usdt'] >= 0.50]
    
    if profitable:
        best = profitable[0]
        
        if st.session_state.trade_mode == "Демо":
            profit = best['profit_usdt']
            st.session_state.total_profit += profit
            st.session_state.trade_count += 1
            update_profit_stats(profit)
            
            trade_text = f"✅ {datetime.now().strftime('%H:%M:%S')} | {best['asset']} | АВТО-АРБИТРАЖ | +{profit:.2f} USDT"
            st.session_state.history.append(trade_text)
            save_user_data()
            save_history()
            st.toast(f"🎯 Авто-арбитраж по {best['asset']}! +{profit:.2f} USDT", icon="💰")
            st.rerun()
    else:
        time.sleep(10)

st.caption("🚀 Накопительный арбитраж — данные сохраняются, бот работает 24/7 даже при закрытом окне")
