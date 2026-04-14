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

st.set_page_config(page_title="Накопительный Арбитраж PRO", layout="wide", page_icon="🚀")

# ====================== СТИЛЬ ======================
st.markdown("""
<style>
    .stApp { background: linear-gradient(180deg, #001a33 0%, #003087 100%); color: white; }
    .main-header { font-size: 28px; font-weight: bold; color: #00D4FF; text-align: center; margin-bottom: 0; }
    .header-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
    .user-info { font-size: 14px; color: #aaaaff; margin-top: 5px; }
    .status-indicator { display: inline-block; width: 14px; height: 14px; border-radius: 50%; margin-right: 6px; }
    .status-running { background-color: #00FF88; box-shadow: 0 0 8px #00FF88; animation: pulse 1.5s infinite; }
    .status-stopped { background-color: #FF4444; box-shadow: 0 0 8px #FF4444; }
    @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.4; } 100% { opacity: 1; } }
    .exchange-badge { background: rgba(0,212,255,0.2); border-radius: 20px; padding: 3px 10px; margin: 0 3px; display: inline-block; font-size: 11px; }
    .stButton>button { border-radius: 30px; height: 42px; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# ====================== КОНФИГУРАЦИЯ ======================
DEFAULT_ASSETS = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "LINK", "SUI", "HYPE"]

# Главная биржа (где хранятся токены)
MAIN_EXCHANGE = "okx"

# ВСПОМОГАТЕЛЬНЫЕ БИРЖИ (10 бирж, без Binance и Bybit)
AUX_EXCHANGES = [
    "gateio", "kucoin", "okx", "bitget", "bingx",
    "mexc", "huobi", "gate", "poloniex", "hitbtc"
]

# Убираем дубликаты и удаляем OKX из вспомогательных (если там)
AUX_EXCHANGES = list(set([ex for ex in AUX_EXCHANGES if ex != MAIN_EXCHANGE]))

# Параметры арбитража
MIN_SPREAD_PERCENT = 0.005  # Уменьшен до 0.005% для более частых сделок
FEE_PERCENT = 0.10

# Демо-портфель (токены на главной бирже эквивалент 1000 USDT)
DEMO_PORTFOLIO = {
    "BTC": 0.013, "ETH": 0.42, "SOL": 11.6, "BNB": 1.63, "XRP": 730,
    "ADA": 4166, "AVAX": 108, "LINK": 113, "SUI": 1098, "HYPE": 23.5
}

# Демо-резервы USDT на каждой вспомогательной бирже (по 10000 USDT)
DEMO_USDT_RESERVES = 10000

# ====================== ФАЙЛЫ ДАННЫХ ======================
USER_DATA_FILE = "user_data_v7.json"
HISTORY_FILE = "history_v7.json"

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
        'wallet_address': st.session_state.get('wallet_address', ''),
        'total_profit': st.session_state.get('total_profit', 0.0),
        'trade_count': st.session_state.get('trade_count', 0),
        'portfolio': st.session_state.get('portfolio', {}),
        'usdt_reserves': st.session_state.get('usdt_reserves', {}),
        'daily_profits': st.session_state.get('daily_profits', {}),
        'weekly_profits': st.session_state.get('weekly_profits', {}),
        'monthly_profits': st.session_state.get('monthly_profits', {}),
        'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'is_registered': True
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
if 'wallet_address' not in st.session_state:
    st.session_state.wallet_address = saved_user.get('wallet_address', '')
if 'total_profit' not in st.session_state:
    st.session_state.total_profit = saved_user.get('total_profit', 0.0)
if 'trade_count' not in st.session_state:
    st.session_state.trade_count = saved_user.get('trade_count', 0)
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = saved_user.get('portfolio', {asset: DEMO_PORTFOLIO.get(asset, 0.0) for asset in DEFAULT_ASSETS})
if 'usdt_reserves' not in st.session_state:
    reserves = {ex: DEMO_USDT_RESERVES for ex in AUX_EXCHANGES}
    reserves[MAIN_EXCHANGE] = 0
    st.session_state.usdt_reserves = saved_user.get('usdt_reserves', reserves)
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
if 'is_first_time' not in st.session_state:
    st.session_state.is_first_time = not saved_user.get('is_registered', False)

# ====================== ПОДКЛЮЧЕНИЕ К БИРЖАМ ======================
@st.cache_resource
def init_exchanges():
    exchanges = {}
    status = {}
    all_exchanges = [MAIN_EXCHANGE] + AUX_EXCHANGES
    for ex_name in all_exchanges:
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
    try:
        ohlcv = exchange.fetch_ohlcv(f"{symbol}/USDT", timeframe, limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except:
        return pd.DataFrame()

def find_all_arbitrage_opportunities():
    """Ищет арбитраж между главной и всеми вспомогательными биржами"""
    opportunities = []
    
    for asset in DEFAULT_ASSETS:
        # Получаем цену на главной бирже
        main_price = None
        if st.session_state.exchanges and MAIN_EXCHANGE in st.session_state.exchanges:
            main_price = get_price(st.session_state.exchanges[MAIN_EXCHANGE], asset)
        
        if not main_price:
            continue
        
        # Проверяем все вспомогательные биржи
        for aux_ex in AUX_EXCHANGES:
            if aux_ex in st.session_state.exchanges and st.session_state.exchanges[aux_ex]:
                aux_price = get_price(st.session_state.exchanges[aux_ex], asset)
                if aux_price:
                    # Если на вспомогательной бирже цена ДЕШЕВЛЕ
                    if aux_price < main_price:
                        spread_pct = (main_price - aux_price) / aux_price * 100
                        net_spread = spread_pct - FEE_PERCENT
                        profit_usdt = round((main_price - aux_price) - (main_price * 0.0008) - (aux_price * 0.0008), 2)
                        
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

def update_profit_stats(profit):
    today = datetime.now().strftime('%Y-%m-%d')
    week = datetime.now().strftime('%Y-%W')
    month = datetime.now().strftime('%Y-%m')
    
    st.session_state.daily_profits[today] = st.session_state.daily_profits.get(today, 0) + profit
    st.session_state.weekly_profits[week] = st.session_state.weekly_profits.get(week, 0) + profit
    st.session_state.monthly_profits[month] = st.session_state.monthly_profits.get(month, 0) + profit

# ====================== РЕГИСТРАЦИЯ / ВХОД ======================
# Показываем регистрацию только при первом входе
if not st.session_state.logged_in:
    st.markdown('<h1 class="main-header">🚀 НАКОПИТЕЛЬНЫЙ АРБИТРАЖ PRO</h1>', unsafe_allow_html=True)
    
    # Если уже регистрировался раньше — показываем только вход
    if not st.session_state.is_first_time:
        with st.form("login_form"):
            st.subheader("🔑 Вход в аккаунт")
            email = st.text_input("Email")
            password = st.text_input("Пароль", type="password")
            submitted = st.form_submit_button("Войти", use_container_width=True)
            
            if submitted:
                saved = load_user_data()
                if saved.get('email') == email:
                    st.session_state.logged_in = True
                    st.session_state.username = saved.get('username', email.split('@')[0])
                    st.session_state.email = email
                    st.session_state.wallet_address = saved.get('wallet_address', '')
                    st.success(f"Добро пожаловать, {st.session_state.username}!")
                    st.rerun()
                else:
                    st.error("Неверный email или пароль")
    else:
        # Первый раз — показываем регистрацию и вход
        tab_reg, tab_login = st.tabs(["📝 Регистрация", "🔑 Вход"])
        
        with tab_reg:
            with st.form("register_form"):
                username = st.text_input("Имя пользователя")
                email = st.text_input("Email")
                wallet = st.text_input("Адрес кошелька (USDT TRC20 / ERC20)")
                password = st.text_input("Пароль", type="password")
                confirm = st.text_input("Подтвердите пароль", type="password")
                submitted = st.form_submit_button("Зарегистрироваться", use_container_width=True)
                
                if submitted:
                    if username and email and wallet and password and password == confirm:
                        st.session_state.logged_in = True
                        st.session_state.username = username
                        st.session_state.email = email
                        st.session_state.wallet_address = wallet
                        st.session_state.is_first_time = False
                        st.session_state.portfolio = {asset: DEMO_PORTFOLIO.get(asset, 0.0) for asset in DEFAULT_ASSETS}
                        st.session_state.usdt_reserves = {ex: DEMO_USDT_RESERVES for ex in AUX_EXCHANGES}
                        save_user_data()
                        st.success("Регистрация успешна!")
                        st.rerun()
                    else:
                        st.error("Заполните все поля или пароли не совпадают")
        
        with tab_login:
            with st.form("login_form"):
                email = st.text_input("Email")
                password = st.text_input("Пароль", type="password")
                submitted = st.form_submit_button("Войти", use_container_width=True)
                
                if submitted:
                    saved = load_user_data()
                    if saved.get('email') == email:
                        st.session_state.logged_in = True
                        st.session_state.username = saved.get('username', email.split('@')[0])
                        st.session_state.email = email
                        st.session_state.wallet_address = saved.get('wallet_address', '')
                        st.session_state.is_first_time = False
                        st.success(f"Добро пожаловать, {st.session_state.username}!")
                        st.rerun()
                    else:
                        st.error("Неверный email или пароль")
    
    st.stop()

# ====================== ИНИЦИАЛИЗАЦИЯ БИРЖ ======================
if st.session_state.exchanges is None:
    with st.spinner("Подключение к 10+ биржам..."):
        st.session_state.exchanges, st.session_state.exchange_status = init_exchanges()

# ====================== ВЕРХНЯЯ ПАНЕЛЬ ======================
col_logo, col_status = st.columns([4, 1])
with col_logo:
    st.markdown('<h1 class="main-header">🚀 НАКОПИТЕЛЬНЫЙ АРБИТРАЖ PRO</h1>', unsafe_allow_html=True)
with col_status:
    if st.session_state.bot_running:
        st.markdown('<div style="text-align: right; margin-top: 10px;"><span class="status-indicator status-running"></span> <b style="color: #00FF88;">ПОИСК АРБИТРАЖА</b></div>', unsafe_allow_html=True)
    else:
        st.markdown('<div style="text-align: right; margin-top: 10px;"><span class="status-indicator status-stopped"></span> <b style="color: #FF4444;">ОСТАНОВЛЕН</b></div>', unsafe_allow_html=True)

# Информация о пользователе (без адреса на главной)
st.markdown(f'<div class="user-info">👤 {st.session_state.username} | 📧 {st.session_state.email}</div>', unsafe_allow_html=True)

# Кнопка выхода
if st.button("🚪 Выйти", key="logout"):
    st.session_state.logged_in = False
    st.rerun()

# Отображение подключенных бирж (компактно)
st.write("### 🔌 Подключенные биржи")
all_exchanges = [MAIN_EXCHANGE] + AUX_EXCHANGES
ex_cols = st.columns(min(len(all_exchanges), 8))
for i, ex in enumerate(all_exchanges[:8]):
    status = st.session_state.exchange_status.get(ex, "error")
    icon = "✅" if status == "connected" else "❌"
    color = "#00FF88" if status == "connected" else "#FF4444"
    ex_cols[i].markdown(f'<span style="color: {color}; font-size: 12px;">{icon} {ex.upper()}</span>', unsafe_allow_html=True)

if len(all_exchanges) > 8:
    st.write(f"+ ещё {len(all_exchanges)-8} бирж")

st.divider()

# ====================== СТАТИСТИКА ======================
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
    
    # Две строки по 5 токенов
    for i in range(0, len(DEFAULT_ASSETS), 5):
        row_assets = DEFAULT_ASSETS[i:i+5]
        cols = st.columns(5)
        for j, asset in enumerate(row_assets):
            with cols[j]:
                st.markdown(f"**{asset}**")
                if st.session_state.exchanges and MAIN_EXCHANGE in st.session_state.exchanges:
                    price = get_price(st.session_state.exchanges[MAIN_EXCHANGE], asset)
                    if price:
                        st.markdown(f'<span style="font-size: 14px;">💰 ${price:,.0f}</span>', unsafe_allow_html=True)
                    else:
                        st.markdown('<span style="font-size: 12px;">❌</span>', unsafe_allow_html=True)
                st.divider()
    
    if st.session_state.bot_running:
        st.info("🟢 Бот работает в фоновом режиме 24/7. Поиск арбитражных возможностей на 10+ биржах...")
    else:
        st.warning("🔴 Бот остановлен. Нажмите 'ЗАПУСТИТЬ' для начала работы.")

# ====================== TAB 2: ГРАФИКИ ======================
with tab2:
    st.subheader("📈 Японские свечи")
    
    col_a, col_b = st.columns(2)
    with col_a:
        selected_asset = st.selectbox("Выберите актив", DEFAULT_ASSETS, key="chart_asset")
    with col_b:
        selected_exchange = st.selectbox("Выберите биржу", [MAIN_EXCHANGE] + AUX_EXCHANGES[:5], key="chart_exchange")
    
    if st.button("🔄 Обновить график", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    
    if st.session_state.exchanges and selected_exchange in st.session_state.exchanges:
        try:
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
                    template="plotly_dark",
                    height=450,
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(20,20,50,0.5)"
                )
                st.plotly_chart(fig, use_container_width=True)
                current_price = df['close'].iloc[-1]
                st.metric("Текущая цена", f"${current_price:,.2f}")
            else:
                st.info("Не удалось загрузить данные для графика")
        except Exception as e:
            st.info(f"Ошибка: {str(e)[:80]}")
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
        st.success(f"✅ Найдено {len(opportunities)} возможностей!")
        for opp in opportunities[:10]:
            st.markdown(f"""
            <div style="background: rgba(0,255,100,0.1); border-radius: 10px; padding: 10px; margin: 8px 0; border-left: 3px solid #00FF88;">
                🎯 <b>{opp['asset']}/USDT</b> | {opp['main_exchange'].upper()} → {opp['aux_exchange'].upper()}<br>
                📈 ${opp['main_price']:,.2f} → ${opp['aux_price']:,.2f}<br>
                💰 <b style="color: #00FF88;">+{opp['profit_usdt']:.2f} USDT</b> (спред {opp['spread_pct']}%)
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
        st.info("📊 Арбитражных возможностей не найдено. Бот продолжает поиск...")

# ====================== TAB 4: ПОРТФЕЛЬ ======================
with tab4:
    st.subheader("📦 Портфель токенов (главная биржа OKX)")
    
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
    st.caption("🎯 Цель: накопление токенов для долгосрочного роста")

# ====================== TAB 5: КОШЕЛЁК ======================
with tab5:
    st.subheader("💰 Резервы USDT на вспомогательных биржах")
    
    # Показываем первые 5 бирж
    for ex in AUX_EXCHANGES[:5]:
        reserve = st.session_state.usdt_reserves.get(ex, DEMO_USDT_RESERVES)
        st.write(f"**{ex.upper()}**: {reserve:.2f} USDT")
    
    if len(AUX_EXCHANGES) > 5:
        st.write(f"+ ещё {len(AUX_EXCHANGES)-5} бирж по {DEMO_USDT_RESERVES} USDT")
    
    st.divider()
    st.subheader("💳 Мой кошелёк для вывода")
    
    wallet_input = st.text_input("Адрес кошелька (USDT TRC20 / ERC20)", value=st.session_state.wallet_address)
    if st.button("💾 Сохранить адрес кошелька"):
        st.session_state.wallet_address = wallet_input
        save_user_data()
        st.success("Адрес сохранён!")
    
    st.divider()
    st.subheader("📤 Вывод средств")
    col_in, col_out = st.columns(2)
    with col_in:
        deposit = st.number_input("Сумма ввода (USDT)", min_value=10.0, step=10.0)
        if st.button("💰 Внести на биржу"):
            st.session_state.usdt_reserves[AUX_EXCHANGES[0]] = st.session_state.usdt_reserves.get(AUX_EXCHANGES[0], DEMO_USDT_RESERVES) + deposit
            save_user_data()
            st.success(f"Внесено {deposit} USDT")
            st.rerun()
    with col_out:
        withdraw = st.number_input("Сумма вывода (USDT)", min_value=10.0, max_value=float(st.session_state.usdt_reserves.get(AUX_EXCHANGES[0], DEMO_USDT_RESERVES)), step=10.0)
        if st.button("📤 Вывести на кошелёк"):
            if st.session_state.wallet_address:
                st.session_state.usdt_reserves[AUX_EXCHANGES[0]] -= withdraw
                save_user_data()
                st.success(f"✅ Заявка на вывод {withdraw} USDT отправлена!")
                st.rerun()
            else:
                st.error("Сначала сохраните адрес кошелька!")

# ====================== TAB 6: СТАТИСТИКА ======================
with tab6:
    st.subheader("📊 Детальная статистика")
    
    if st.session_state.daily_profits:
        df = pd.DataFrame(list(st.session_state.daily_profits.items()), columns=['Дата', 'Прибыль (USDT)'])
        st.dataframe(df.sort_values('Дата', ascending=False), use_container_width=True, hide_index=True)
        
        df_daily = df.sort_values('Дата').tail(30)
        fig_daily = px.bar(df_daily, x='Дата', y='Прибыль (USDT)', title="Дневная прибыль", color_discrete_sequence=['#00FF88'])
        fig_daily.update_layout(template="plotly_dark", height=400)
        st.plotly_chart(fig_daily, use_container_width=True)
    else:
        st.info("Нет данных о прибыли")

# ====================== TAB 7: ИСТОРИЯ ======================
with tab7:
    st.subheader("📜 История сделок")
    
    if st.session_state.history:
        for trade in reversed(st.session_state.history[-50:]):
            if "+" in trade and "0.00" not in trade:
                st.success(trade)
            else:
                st.write(trade)
        
        if st.button("🗑 Очистить историю"):
            st.session_state.history = []
            save_history()
            st.rerun()
    else:
        st.info("Нет сделок")

# ====================== АВТОМАТИЧЕСКИЙ АРБИТРАЖ ======================
if st.session_state.bot_running and st.session_state.exchanges:
    time.sleep(3)
    
    opportunities = find_all_arbitrage_opportunities()
    
    if opportunities:
        best = opportunities[0]
        
        if st.session_state.trade_mode == "Демо":
            profit = best['profit_usdt']
            if profit >= 0.20:
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
        time.sleep(5)

st.caption("🚀 Накопительный арбитраж — поиск на 10+ биржах, токены на OKX, USDT на вспомогательных биржах")
