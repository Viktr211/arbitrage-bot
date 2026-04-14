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
import threading
import numpy as np

st.set_page_config(page_title="Накопительный Арбитраж PRO", layout="wide", page_icon="🚀")

# ====================== СТИЛЬ ======================
st.markdown("""
<style>
    .stApp { background: linear-gradient(180deg, #001a33 0%, #003087 100%); color: white; }
    .main-header { font-size: 28px; font-weight: bold; color: #00D4FF; text-align: center; margin-bottom: 0; }
    .user-info { font-size: 14px; color: #aaaaff; margin-top: 5px; }
    .status-indicator { display: inline-block; width: 14px; height: 14px; border-radius: 50%; margin-right: 6px; }
    .status-running { background-color: #00FF88; box-shadow: 0 0 8px #00FF88; animation: pulse 1.5s infinite; }
    .status-stopped { background-color: #FF4444; box-shadow: 0 0 8px #FF4444; }
    @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.4; } 100% { opacity: 1; } }
    .stButton>button { border-radius: 30px; height: 42px; font-weight: bold; }
    .green-button button { background-color: #00AA44 !important; color: white !important; }
    .yellow-button button { background-color: #CC8800 !important; color: white !important; }
    .red-button button { background-color: #CC3333 !important; color: white !important; }
    .token-card { background: rgba(0,100,200,0.2); border-radius: 10px; padding: 8px; margin: 4px; text-align: center; }
    .profit-card { background: rgba(0,255,100,0.1); border-radius: 10px; padding: 15px; margin: 10px 0; border-left: 4px solid #00FF88; }
</style>
""", unsafe_allow_html=True)

# ====================== КОНФИГУРАЦИЯ ======================
DEFAULT_ASSETS = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "LINK", "SUI", "HYPE"]
MAIN_EXCHANGE = "okx"
AUX_EXCHANGES = ["gateio", "kucoin", "bitget", "bingx", "mexc", "huobi", "poloniex", "hitbtc"]

MIN_SPREAD_PERCENT = 0.005
FEE_PERCENT = 0.10

DEMO_PORTFOLIO = {
    "BTC": 0.013, "ETH": 0.42, "SOL": 11.6, "BNB": 1.63, "XRP": 730,
    "ADA": 4166, "AVAX": 108, "LINK": 113, "SUI": 1098, "HYPE": 23.5
}
DEMO_USDT_RESERVES = 10000

# ====================== ФАЙЛЫ ======================
USER_DATA_FILE = "user_data_v12.json"
HISTORY_FILE = "history_v12.json"
OPPORTUNITIES_FILE = "opportunities_history.json"

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
        'bot_running': st.session_state.get('bot_running', False),
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
        json.dump(st.session_state.history[-500:], f, ensure_ascii=False, indent=4)

def load_opportunities():
    if os.path.exists(OPPORTUNITIES_FILE):
        try:
            with open(OPPORTUNITIES_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return []
    return []

def save_opportunities(opps):
    if len(opps) > 10000:
        opps = opps[-10000:]
    with open(OPPORTUNITIES_FILE, 'w', encoding='utf-8') as f:
        json.dump(opps, f, ensure_ascii=False, indent=4)

# ====================== СЕССИЯ ======================
saved_user = load_user_data()
saved_history = load_history()
saved_opportunities = load_opportunities()

for key, default in [
    ('logged_in', saved_user.get('logged_in', False)),
    ('username', saved_user.get('username', None)),
    ('email', saved_user.get('email', None)),
    ('wallet_address', saved_user.get('wallet_address', '')),
    ('total_profit', saved_user.get('total_profit', 0.0)),
    ('trade_count', saved_user.get('trade_count', 0)),
    ('portfolio', saved_user.get('portfolio', {asset: DEMO_PORTFOLIO.get(asset, 0.0) for asset in DEFAULT_ASSETS})),
    ('usdt_reserves', saved_user.get('usdt_reserves', {ex: DEMO_USDT_RESERVES for ex in AUX_EXCHANGES})),
    ('daily_profits', saved_user.get('daily_profits', {})),
    ('weekly_profits', saved_user.get('weekly_profits', {})),
    ('monthly_profits', saved_user.get('monthly_profits', {})),
    ('history', saved_history),
    ('opportunities_history', saved_opportunities),
    ('exchanges', None),
    ('bot_running', saved_user.get('bot_running', False)),
    ('trade_mode', "Демо"),
    ('exchange_status', {}),
    ('is_first_time', not saved_user.get('is_registered', False))
]:
    if key not in st.session_state:
        st.session_state[key] = default

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
        except:
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

def find_all_arbitrage_opportunities(record=True):
    opportunities = []
    if not st.session_state.exchanges or MAIN_EXCHANGE not in st.session_state.exchanges:
        return opportunities
    
    main_prices = {}
    for asset in DEFAULT_ASSETS:
        price = get_price(st.session_state.exchanges[MAIN_EXCHANGE], asset)
        if price:
            main_prices[asset] = price
    
    now = datetime.now().isoformat()
    for asset in DEFAULT_ASSETS:
        if asset not in main_prices:
            continue
        main_price = main_prices[asset]
        for aux_ex in AUX_EXCHANGES:
            if aux_ex in st.session_state.exchanges and st.session_state.exchanges[aux_ex]:
                aux_price = get_price(st.session_state.exchanges[aux_ex], asset)
                if aux_price and aux_price < main_price:
                    spread_pct = (main_price - aux_price) / aux_price * 100
                    net_spread = spread_pct - FEE_PERCENT
                    profit_usdt = round((main_price - aux_price) - (main_price * 0.0008) - (aux_price * 0.0008), 2)
                    if net_spread > MIN_SPREAD_PERCENT and profit_usdt >= 0.20:
                        opp = {
                            'asset': asset,
                            'aux_exchange': aux_ex,
                            'main_price': main_price,
                            'aux_price': aux_price,
                            'spread_pct': round(spread_pct, 2),
                            'profit_usdt': profit_usdt,
                            'timestamp': now
                        }
                        opportunities.append(opp)
                        if record:
                            st.session_state.opportunities_history.append(opp)
    
    if record and opportunities:
        save_opportunities(st.session_state.opportunities_history)
    
    return sorted(opportunities, key=lambda x: x['profit_usdt'], reverse=True)

def update_profit_stats(profit):
    today = datetime.now().strftime('%Y-%m-%d')
    week = datetime.now().strftime('%Y-%W')
    month = datetime.now().strftime('%Y-%m')
    st.session_state.daily_profits[today] = st.session_state.daily_profits.get(today, 0) + profit
    st.session_state.weekly_profits[week] = st.session_state.weekly_profits.get(week, 0) + profit
    st.session_state.monthly_profits[month] = st.session_state.monthly_profits.get(month, 0) + profit

def compute_expected_return(capital_usdt, lookback_days=7):
    opps = st.session_state.opportunities_history
    if not opps:
        return None, None, None
    cutoff = datetime.now() - timedelta(days=lookback_days)
    recent = [o for o in opps if datetime.fromisoformat(o['timestamp']) > cutoff]
    if not recent:
        return None, None, None
    avg_profit_per_opp = np.mean([o['profit_usdt'] for o in recent])
    days = set(datetime.fromisoformat(o['timestamp']).date() for o in recent)
    if not days:
        return None, None, None
    total_opps = len(recent)
    avg_opps_per_day = total_opps / len(days)
    reference_capital = 80000.0
    scaling_factor = capital_usdt / reference_capital if reference_capital > 0 else 1
    expected_daily_profit = avg_profit_per_opp * avg_opps_per_day * scaling_factor
    expected_daily_return_pct = (expected_daily_profit / capital_usdt) * 100 if capital_usdt > 0 else 0
    return expected_daily_profit, expected_daily_return_pct, avg_opps_per_day

# ====================== ИНИЦИАЛИЗАЦИЯ БИРЖ ======================
if st.session_state.exchanges is None:
    with st.spinner("Подключение к биржам..."):
        st.session_state.exchanges, st.session_state.exchange_status = init_exchanges()

# ====================== РЕГИСТРАЦИЯ / ВХОД ======================
if not st.session_state.logged_in:
    st.markdown('<h1 class="main-header">🚀 НАКОПИТЕЛЬНЫЙ АРБИТРАЖ PRO</h1>', unsafe_allow_html=True)
    if not st.session_state.is_first_time:
        with st.form("login_form"):
            st.subheader("🔑 Вход в аккаунт")
            email = st.text_input("Email")
            password = st.text_input("Пароль", type="password")
            if st.form_submit_button("Войти", use_container_width=True):
                saved = load_user_data()
                if saved.get('email') == email:
                    for k in ['username', 'email', 'wallet_address', 'total_profit', 'trade_count', 'portfolio', 'usdt_reserves', 'daily_profits', 'weekly_profits', 'monthly_profits', 'history', 'bot_running']:
                        if k in saved:
                            st.session_state[k] = saved[k]
                    st.session_state.logged_in = True
                    st.session_state.is_first_time = False
                    st.success(f"Добро пожаловать, {st.session_state.username}!")
                    st.rerun()
                else:
                    st.error("Неверный email или пароль")
    else:
        tab_reg, tab_login = st.tabs(["📝 Регистрация", "🔑 Вход"])
        with tab_reg:
            with st.form("register_form"):
                username = st.text_input("Имя пользователя")
                email = st.text_input("Email")
                wallet = st.text_input("Адрес кошелька")
                password = st.text_input("Пароль", type="password")
                confirm = st.text_input("Подтвердите пароль", type="password")
                if st.form_submit_button("Зарегистрироваться"):
                    if username and email and wallet and password and password == confirm:
                        st.session_state.logged_in = True
                        st.session_state.username = username
                        st.session_state.email = email
                        st.session_state.wallet_address = wallet
                        st.session_state.is_first_time = False
                        save_user_data()
                        st.success("Регистрация успешна!")
                        st.rerun()
                    else:
                        st.error("Заполните все поля")
        with tab_login:
            with st.form("login_form"):
                email = st.text_input("Email")
                password = st.text_input("Пароль", type="password")
                if st.form_submit_button("Войти"):
                    saved = load_user_data()
                    if saved.get('email') == email:
                        for k in ['username', 'email', 'wallet_address']:
                            if k in saved:
                                st.session_state[k] = saved[k]
                        st.session_state.logged_in = True
                        st.session_state.is_first_time = False
                        st.rerun()
                    else:
                        st.error("Неверный email")
    st.stop()

# ====================== ОСНОВНОЙ ИНТЕРФЕЙС ======================
col_logo, col_status, col_logout = st.columns([3, 1, 1])
with col_logo:
    st.markdown('<h1 class="main-header">🚀 НАКОПИТЕЛЬНЫЙ АРБИТРАЖ PRO</h1>', unsafe_allow_html=True)
with col_status:
    if st.session_state.bot_running:
        st.markdown('<div style="text-align: center;"><span class="status-indicator status-running"></span> <b style="color: #00FF88;">РАБОТАЕТ</b></div>', unsafe_allow_html=True)
    else:
        st.markdown('<div style="text-align: center;"><span class="status-indicator status-stopped"></span> <b style="color: #FF4444;">ОСТАНОВЛЕН</b></div>', unsafe_allow_html=True)
with col_logout:
    if st.button("🚪 Выйти", key="logout"):
        st.session_state.bot_running = False
        st.session_state.logged_in = False
        save_user_data()
        st.rerun()

st.markdown(f'<div class="user-info">👤 {st.session_state.username} | 📧 {st.session_state.email}</div>', unsafe_allow_html=True)

connected = [ex.upper() for ex, status in st.session_state.exchange_status.items() if status == "connected"]
st.write(f"🔌 **Биржи:** {', '.join(connected[:8])}" + (f" +{len(connected)-8}" if len(connected) > 8 else ""))
st.write(f"🪙 **Токены:** {', '.join(DEFAULT_ASSETS)} (10 токенов)")
st.divider()

col1, col2 = st.columns(2)
col1.metric("💰 Общая прибыль", f"{st.session_state.total_profit:.2f} USDT")
col2.metric("📊 Сделок", st.session_state.trade_count)

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.markdown('<div class="green-button">', unsafe_allow_html=True)
    if st.button("▶ СТАРТ", use_container_width=True):
        st.session_state.bot_running = True
        save_user_data()
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)
with c2:
    st.markdown('<div class="yellow-button">', unsafe_allow_html=True)
    if st.button("⏸ ПАУЗА", use_container_width=True):
        st.session_state.bot_running = False
        save_user_data()
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)
with c3:
    st.markdown('<div class="red-button">', unsafe_allow_html=True)
    if st.button("⏹ СТОП", use_container_width=True):
        st.session_state.bot_running = False
        save_user_data()
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)
with c4:
    st.session_state.trade_mode = st.selectbox("Режим", ["Демо", "Реальный"])

# ====================== ВКЛАДКИ ======================
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(["📊 Dashboard", "📈 Графики", "🔄 Арбитраж", "📊 Доходность", "📦 Портфель", "💰 Кошелёк", "📜 История"])

# TAB 1 - Dashboard
with tab1:
    st.subheader("📊 Статус сканирования токенов")
    st.write("### 🪙 Текущие цены на OKX")
    for i in range(0, len(DEFAULT_ASSETS), 5):
        cols = st.columns(5)
        for j, asset in enumerate(DEFAULT_ASSETS[i:i+5]):
            with cols[j]:
                price = get_price(st.session_state.exchanges[MAIN_EXCHANGE], asset) if st.session_state.exchanges and MAIN_EXCHANGE in st.session_state.exchanges else None
                if price:
                    st.markdown(f"<div class='token-card'><b>{asset}</b><br><span style='font-size: 18px; color: #00D4FF;'>${price:,.0f}</span></div>", unsafe_allow_html=True)
                else:
                    st.markdown(f"<div class='token-card'><b>{asset}</b><br>❌</div>", unsafe_allow_html=True)
    st.divider()
    st.write("### 🔍 Активные биржи")
    active = [ex for ex in AUX_EXCHANGES if ex.upper() in [x.upper() for x in connected]]
    for i, ex in enumerate(active[:8]):
        if i % 4 == 0:
            cols = st.columns(4)
        with cols[i % 4]:
            st.markdown(f"<div class='token-card'>✅ {ex.upper()}<br><span style='font-size: 11px;'>USDT: {DEMO_USDT_RESERVES:.0f}</span></div>", unsafe_allow_html=True)
    if st.session_state.bot_running:
        st.info(f"🟢 Бот сканирует **{len(DEFAULT_ASSETS)} токенов** на **{len(connected)} биржах** одновременно. Последнее обновление: {datetime.now().strftime('%H:%M:%S')}")
    else:
        st.warning("🔴 Бот остановлен. Нажмите СТАРТ для начала сканирования.")

# TAB 2 - Графики
with tab2:
    st.subheader("📈 Японские свечи")
    col_a, col_b = st.columns(2)
    selected_asset = col_a.selectbox("Актив", DEFAULT_ASSETS)
    selected_exchange = col_b.selectbox("Биржа", [MAIN_EXCHANGE] + AUX_EXCHANGES[:5])
    if st.button("🔄 Обновить график", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    if st.session_state.exchanges and selected_exchange in st.session_state.exchanges:
        try:
            df = get_historical_ohlcv(st.session_state.exchanges[selected_exchange], selected_asset)
            if not df.empty:
                fig = go.Figure(data=[go.Candlestick(x=df['timestamp'], open=df['open'], high=df['high'], low=df['low'], close=df['close'])])
                fig.update_layout(title=f"{selected_asset}/USDT на {selected_exchange.upper()}", template="plotly_dark", height=500)
                st.plotly_chart(fig, use_container_width=True)
                st.metric("Текущая цена", f"${df['close'].iloc[-1]:,.2f}")
            else:
                st.warning("Нет данных для графика")
        except Exception as e:
            st.warning(f"Ошибка: {str(e)[:80]}")
    else:
        st.warning("Биржа не подключена")

# TAB 3 - Арбитраж (ИСПРАВЛЕНА ОШИБКА DUPLICATE KEY)
with tab3:
    st.subheader("🔍 Найденные арбитражные возможности")
    if st.button("🔄 Обновить", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    opportunities = find_all_arbitrage_opportunities(record=True)
    if opportunities:
        st.success(f"✅ Найдено {len(opportunities)} возможностей на {len(set([opp['asset'] for opp in opportunities]))} токенах!")
        for idx, opp in enumerate(opportunities[:10]):
            # Уникальный ключ: asset + биржа + индекс
            unique_key = f"{opp['asset']}_{opp['aux_exchange']}_{idx}"
            st.info(f"🎯 {opp['asset']}: OKX ${opp['main_price']:,.0f} → {opp['aux_exchange'].upper()} ${opp['aux_price']:,.0f} | +{opp['profit_usdt']:.2f} USDT")
            if st.button(f"Исполнить {opp['asset']} на {opp['aux_exchange'].upper()}", key=unique_key):
                if st.session_state.trade_mode == "Демо":
                    profit = opp['profit_usdt']
                    st.session_state.total_profit += profit
                    st.session_state.trade_count += 1
                    update_profit_stats(profit)
                    trade_text = f"✅ {datetime.now().strftime('%H:%M:%S')} | {opp['asset']} | Куплен на {opp['aux_exchange'].upper()} по ${opp['aux_price']:.2f} | Продан на OKX по ${opp['main_price']:.2f} | +{profit:.2f} USDT"
                    st.session_state.history.append(trade_text)
                    save_user_data()
                    save_history()
                    st.success(f"✅ Сделка исполнена! +{profit:.2f} USDT")
                    st.rerun()
    else:
        st.info("📊 Арбитражных возможностей не найдено. Бот сканирует все токены и биржи...")

# TAB 4 - Доходность
with tab4:
    st.subheader("📊 Калькулятор ожидаемой доходности")
    st.markdown("На основе исторических арбитражных возможностей (последние 7 дней) бот рассчитывает потенциальный доход.")
    if not st.session_state.opportunities_history:
        with st.spinner("Сбор данных об арбитражных возможностях..."):
            find_all_arbitrage_opportunities(record=True)
    opps = st.session_state.opportunities_history
    if opps:
        df_opps = pd.DataFrame(opps)
        df_opps['timestamp'] = pd.to_datetime(df_opps['timestamp'])
        df_opps['date'] = df_opps['timestamp'].dt.date
        st.write("### 📈 Статистика найденных возможностей за всё время")
        col_a, col_b, col_c = st.columns(3)
        col_a.metric("Всего возможностей", len(df_opps))
        col_b.metric("Средняя прибыль на сделку", f"${df_opps['profit_usdt'].mean():.2f}")
        col_c.metric("Максимальная прибыль", f"${df_opps['profit_usdt'].max():.2f}")
        daily_counts = df_opps.groupby('date').size().reset_index(name='count')
        fig_counts = px.bar(daily_counts, x='date', y='count', title="Количество возможностей по дням", color_discrete_sequence=['#00FF88'])
        fig_counts.update_layout(template="plotly_dark", height=400)
        st.plotly_chart(fig_counts, use_container_width=True)
        asset_counts = df_opps['asset'].value_counts().reset_index()
        asset_counts.columns = ['Актив', 'Количество']
        fig_assets = px.bar(asset_counts, x='Актив', y='Количество', title="Возможности по активам", color_discrete_sequence=['#00D4FF'])
        fig_assets.update_layout(template="plotly_dark", height=400)
        st.plotly_chart(fig_assets, use_container_width=True)
        st.divider()
        st.write("### 💰 Калькулятор ожидаемого дохода")
        st.info("Введите сумму USDT, которую вы планируете использовать для арбитража.")
        capital = st.number_input("💵 Капитал для арбитража (USDT)", min_value=100.0, value=10000.0, step=1000.0)
        lookback = st.selectbox("Период анализа", [3, 7, 14, 30], index=1, format_func=lambda x: f"{x} дней")
        if st.button("Рассчитать ожидаемую доходность", use_container_width=True):
            exp_profit, exp_return_pct, avg_opps_per_day = compute_expected_return(capital, lookback_days=lookback)
            if exp_profit is not None:
                st.markdown(f"""
                <div class="profit-card">
                    <b>📊 Ожидаемая дневная доходность (на основе последних {lookback} дней):</b><br>
                    💰 Прибыль в день: <b style="color: #00FF88;">${exp_profit:.2f}</b><br>
                    📈 Доходность: <b style="color: #00FF88;">{exp_return_pct:.2f}%</b> от капитала<br>
                    🔄 Количество сделок в день (оценка): <b>{avg_opps_per_day:.1f}</b>
                </div>
                """, unsafe_allow_html=True)
                st.caption("⚠️ *Расчёт основан на исторических спредах и не гарантирует будущих результатов.*")
            else:
                st.warning(f"Недостаточно данных за последние {lookback} дней.")
    else:
        st.info("Пока нет накопленных данных об арбитражных возможностях. Запустите бота и подождите некоторое время.")
        if st.button("Принудительно запустить сканирование"):
            find_all_arbitrage_opportunities(record=True)
            st.rerun()

# TAB 5 - Портфель
with tab5:
    st.subheader("📦 Портфель токенов (OKX)")
    total = 0
    for asset in DEFAULT_ASSETS:
        amount = st.session_state.portfolio.get(asset, 0)
        if st.session_state.exchanges and MAIN_EXCHANGE in st.session_state.exchanges:
            price = get_price(st.session_state.exchanges[MAIN_EXCHANGE], asset)
            value = amount * price if price else 0
            total += value
            st.write(f"{asset}: {amount:.6f} ≈ ${value:,.2f}")
    st.divider()
    st.metric("💰 Общая стоимость портфеля", f"${total:,.2f}")

# TAB 6 - Кошелёк
with tab6:
    st.subheader("💰 Резервы USDT на биржах")
    for ex in AUX_EXCHANGES[:5]:
        st.write(f"{ex.upper()}: {st.session_state.usdt_reserves.get(ex, DEMO_USDT_RESERVES):.0f} USDT")
    st.divider()
    wallet_input = st.text_input("Адрес кошелька", value=st.session_state.wallet_address)
    if st.button("💾 Сохранить"):
        st.session_state.wallet_address = wallet_input
        save_user_data()
        st.success("Адрес сохранён!")
    withdraw = st.number_input("Сумма вывода", min_value=10.0, step=10.0)
    if st.button("📤 Вывести"):
        if st.session_state.wallet_address:
            st.success(f"Заявка на вывод {withdraw} USDT отправлена")

# TAB 7 - История
with tab7:
    st.subheader("📜 История арбитражных сделок")
    if st.session_state.history:
        for trade in reversed(st.session_state.history[-50:]):
            if "✅" in trade:
                st.success(trade)
            else:
                st.write(trade)
        if st.button("🗑 Очистить историю"):
            st.session_state.history = []
            save_history()
            st.rerun()
    else:
        st.info("Нет совершённых сделок")

# ====================== АВТОМАТИЧЕСКИЙ АРБИТРАЖ ======================
if st.session_state.bot_running and st.session_state.exchanges:
    time.sleep(8)
    opportunities = find_all_arbitrage_opportunities(record=True)
    if opportunities:
        best = opportunities[0]
        profit = best['profit_usdt']
        if profit >= 0.30:
            st.session_state.total_profit += profit
            st.session_state.trade_count += 1
            update_profit_stats(profit)
            trade_text = f"✅ {datetime.now().strftime('%H:%M:%S')} | {best['asset']} | Куплен на {best['aux_exchange'].upper()} по ${best['aux_price']:.2f} | Продан на OKX по ${best['main_price']:.2f} | +{profit:.2f} USDT"
            st.session_state.history.append(trade_text)
            save_user_data()
            save_history()
            st.toast(f"🎯 {best['asset']} | +{profit:.2f} USDT", icon="💰")
            st.rerun()

st.caption(f"🚀 Сканируется {len(DEFAULT_ASSETS)} токенов на {len(connected)} биржах | Работает 24/7")
