ModuleNotFoundError: This app has encountered an error. The original error message is redacted to prevent data leaks. Full error details have been recorded in the logs (if you're on Streamlit Cloud, click on 'Manage app' in the lower right of your app).
Traceback:
File "/mount/src/arbitrage-bot/app.py", line 9, in <module>
    import plotly.graph_objects as go
    .stMetric div[data-testid="stMetricValue"] { font-size: 22px !important; font-weight: bold; }
    .stButton>button { border-radius: 30px; height: 44px; font-weight: bold; font-size: 15px; }
    .stTabs [data-baseweb="tab-list"] button { font-size: 15.5px; font-weight: 600; }
</style>
""", unsafe_allow_html=True)

# Загрузка конфига
try:
    with open('config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)
except:
    config = {
        "asset_config": [{"asset": "BTC"}, {"asset": "ETH"}, {"asset": "BNB"}, {"asset": "SOL"}],
        "target_asset_amount": {"BTC": 0.05, "ETH": 0.5, "BNB": 1.0, "SOL": 5.0},
        "exchanges": ["binance", "kucoin", "bybit"]
    }

ASSET_CONFIG = config.get('asset_config', [{"asset": "BTC"}, {"asset": "ETH"}])
TARGET_ASSET_AMOUNT = config.get('target_asset_amount', {"BTC": 0.05, "ETH": 0.5})
EXCHANGES = config.get('exchanges', ["binance", "kucoin"])

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
if 'balances' not in st.session_state:
    st.session_state.balances = {asset['asset']: 0.0 for asset in ASSET_CONFIG}

# Функции арбитража
@st.cache_data(ttl=10)
def get_ticker_prices(symbol):
    prices = {}
    for exchange_name in EXCHANGES:
        try:
            exchange_class = getattr(ccxt, exchange_name)
            exchange = exchange_class({'enableRateLimit': True})
            ticker = exchange.fetch_ticker(symbol)
            prices[exchange_name] = {'bid': ticker['bid'], 'ask': ticker['ask'], 'last': ticker['last']}
        except:
            prices[exchange_name] = {'bid': None, 'ask': None, 'last': None}
    return prices

def find_arbitrage_opportunity(symbol, main_exchange='binance'):
    prices = get_ticker_prices(symbol)
    main_price = prices.get(main_exchange, {}).get('ask')
    if not main_price:
        return None
    opportunities = []
    for ex, data in prices.items():
        if ex == main_exchange:
            continue
        if data.get('ask') and data['ask'] < main_price:
            spread_pct = (main_price - data['ask']) / data['ask'] * 100
            if spread_pct > 0.3:
                opportunities.append({'exchange': ex, 'buy_price': data['ask'], 'sell_price': main_price, 'spread_pct': round(spread_pct, 2)})
    return max(opportunities, key=lambda x: x['spread_pct']) if opportunities else None

@st.cache_data(ttl=60)
def get_historical_prices(symbol, exchange='binance', limit=100):
    try:
        exchange_obj = getattr(ccxt, exchange)({'enableRateLimit': True})
        ohlcv = exchange_obj.fetch_ohlcv(symbol, timeframe='1h', limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except:
        return pd.DataFrame()

# Заголовок
st.markdown('<h1 class="main-header">🚀 ARBITRAGE BOT PRO</h1>', unsafe_allow_html=True)

# Верхняя панель
col1, col2, col3, col4 = st.columns([2, 2, 2, 3])
with col1:
    st.metric("💰 Общая прибыль", f"{st.session_state.total_profit:.4f} USDT")
with col2:
    st.metric("📊 Сделок", st.session_state.trade_count)
with col3:
    status = "🟢 Работает" if st.session_state.bot_running else "🔴 Остановлен"
    st.metric("Статус", f"{status}")
with col4:
    mode = st.radio("Режим", ["Демо (симуляция)", "Реальный (расчёт)"], horizontal=True, label_visibility="collapsed")
    st.session_state.mode = "Демо" if "Демо" in mode else "Реальный"

# Кнопки
c1, c2, c3 = st.columns(3)
if c1.button("▶ СТАРТ", type="primary", use_container_width=True):
    st.session_state.bot_running = True
    st.success("Бот запущен! Поиск арбитражных возможностей...")
if c2.button("⏸ ПАУЗА", use_container_width=True):
    st.session_state.bot_running = False
    st.warning("Бот на паузе")
if c3.button("⏹ СТОП", use_container_width=True):
    st.session_state.bot_running = False
    st.error("Бот остановлен")

# Вкладки
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 Dashboard", "📈 Графики", "📦 Активы", "📜 Текущие сделки", "📚 Архив по дням"])

# TAB 1: Dashboard
with tab1:
    st.subheader("📊 Дашборд арбитражных возможностей")
    for asset_config in ASSET_CONFIG:
        asset = asset_config['asset']
        symbol = f"{asset}/USDT"
        prices = get_ticker_prices(symbol)
        cols = st.columns(len(EXCHANGES) + 1)
        cols[0].write(f"**{asset}**")
        for i, ex in enumerate(EXCHANGES):
            price = prices.get(ex, {}).get('last')
            cols[i+1].metric(ex.upper(), f"${price:.2f}" if price else "❌")
        opportunity = find_arbitrage_opportunity(symbol)
        if opportunity:
            st.info(f"🎯 **{asset}**: Купить на {opportunity['exchange'].upper()} по ${opportunity['buy_price']:.2f}, продать на Binance по ${opportunity['sell_price']:.2f} → прибыль {opportunity['spread_pct']}%")
        else:
            st.caption(f"📊 {asset}: арбитражных возможностей не найдено")
        st.divider()

# TAB 2: Графики
with tab2:
    st.subheader("📈 Графики цен")
    selected_asset = st.selectbox("Выберите токен", [a['asset'] for a in ASSET_CONFIG])
    selected_exchange = st.selectbox("Выберите биржу", EXCHANGES)
    if selected_asset and selected_exchange:
        symbol = f"{selected_asset}/USDT"
        df = get_historical_prices(symbol, selected_exchange)
        if not df.empty:
            fig = go.Figure(data=[go.Candlestick(x=df['timestamp'], open=df['open'], high=df['high'], low=df['low'], close=df['close'])])
            fig.update_layout(title=f"{selected_asset}/USDT на {selected_exchange.upper()}", template="plotly_dark", height=500)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.error("Не удалось загрузить данные")

# TAB 3: Активы
with tab3:
    st.subheader("📦 Активы и цели накопления")
    cols = st.columns(len(ASSET_CONFIG))
    for i, asset_config in enumerate(ASSET_CONFIG):
        asset = asset_config['asset']
        target = TARGET_ASSET_AMOUNT.get(asset, 0)
        current = st.session_state.balances.get(asset, 0)
        with cols[i]:
            st.metric(label=asset, value=f"{current:.6f} / {target}", delta=f"{((current/target)-1)*100:.1f}%" if target > 0 else "0%")
            st.progress(min(current/target, 1.0) if target > 0 else 0)

# TAB 4: Текущие сделки
with tab4:
    st.subheader("📜 Последние сделки")
    if st.session_state.history:
        for trade in reversed(st.session_state.history[-25:]):
            st.write(trade)
    else:
        st.info("Пока нет сделок. Запустите бота.")

# TAB 5: Архив
with tab5:
    st.subheader("📚 Архив по дням")
    today = date.today().strftime("%Y-%m-%d")
    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("📅 Показать сделки за сегодня", use_container_width=True):
            today_trades = [t for t in st.session_state.history if today in t]
            for t in today_trades:
                st.write(t)
    with col_btn2:
        if st.button("📜 Показать всю историю", use_container_width=True):
            for trade in reversed(st.session_state.history):
                st.write(trade)

# Основная логика
if st.session_state.bot_running:
    time.sleep(3)
    for asset_config in ASSET_CONFIG:
        asset = asset_config['asset']
        symbol = f"{asset}/USDT"
        opportunity = find_arbitrage_opportunity(symbol)
        if opportunity:
            profit_pct = opportunity['spread_pct']
            trade_profit = round(10 * (profit_pct / 100), 4)
            if st.session_state.mode == "Демо":
                st.session_state.total_profit += trade_profit
                st.session_state.trade_count += 1
                st.session_state.balances[asset] = st.session_state.balances.get(asset, 0) + 0.001
                trade_text = f"✅ {datetime.now().strftime('%H:%M:%S')} | {asset} | Купить на {opportunity['exchange'].upper()} | Продать на Binance | +{trade_profit} USDT"
                st.session_state.history.append(trade_text)
                st.toast(f"🎯 Сделка по {asset}! Прибыль: +{trade_profit} USDT", icon="💰")
            else:
                st.warning(f"Реальный режим для {asset} требует настройки API ключей")
            st.rerun()

st.caption("🚀 Arbitrage Bot PRO v3.0 — реальный поиск арбитража между биржами")
