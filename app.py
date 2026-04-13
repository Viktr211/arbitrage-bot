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
import io

st.set_page_config(page_title="Arbitrage Bot PRO", layout="wide", page_icon="🚀")

# ====================== СТИЛЬ ======================
st.markdown("""
<style>
    .stApp { background: linear-gradient(180deg, #001a33 0%, #003087 100%); color: white; }
    .main-header { font-size: 28px; font-weight: bold; color: #00D4FF; text-align: center; }
    .stButton>button { border-radius: 30px; height: 48px; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# ====================== ТОКЕНЫ И ЦЕЛИ ======================
DEFAULT_ASSETS = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "LINK", "SUI", "HYPE"]
DEFAULT_TARGETS = {
    "BTC": 0.5, "ETH": 2.0, "SOL": 50.0, "BNB": 20.0,
    "XRP": 10000.0, "ADA": 5000.0, "AVAX": 100.0,
    "LINK": 300.0, "SUI": 800.0, "HYPE": 400.0
}
ASSET_CONFIG = [{"asset": a} for a in DEFAULT_ASSETS]

# ====================== БИРЖИ (только работающие) ======================
# Поменяем порядок: OKX и Gate.io первые, они работают
EXCHANGE_LIST = ["okx", "gateio", "kucoin"]  # Binance и Bybit убраны

# ====================== СОХРАНЕНИЕ ДАННЫХ ======================
DATA_FILE = "user_data.json"

def load_user_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_user_data():
    data = {
        'username': st.session_state.get('username'),
        'total_profit': st.session_state.get('total_profit', 0.0),
        'today_profit': st.session_state.get('today_profit', 0.0),
        'trade_count': st.session_state.get('trade_count', 0),
        'fixed_profit': st.session_state.get('fixed_profit', 0.0),
        'user_balance': st.session_state.get('user_balance', 1000.0),
        'history': st.session_state.get('history', [])[-500:],
        'portfolio': st.session_state.get('portfolio', {}),
        'daily_profits': st.session_state.get('daily_profits', {}),
        'weekly_profits': st.session_state.get('weekly_profits', {})
    }
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# ====================== ПОДКЛЮЧЕНИЕ К БИРЖАМ (ТОЛЬКО РАБОТАЮЩИЕ) ======================
@st.cache_resource
def init_exchanges():
    exchanges = {}
    
    for ex_name in EXCHANGE_LIST:
        try:
            exchange_class = getattr(ccxt, ex_name)
            exchange = exchange_class({
                'enableRateLimit': True,
                'options': {'defaultType': 'spot'}
            })
            # Проверяем подключение (короткий таймаут)
            ticker = exchange.fetch_ticker('BTC/USDT')
            if ticker and ticker.get('last'):
                exchanges[ex_name] = exchange
                st.success(f"✅ {ex_name.upper()} — подключена")
            else:
                st.warning(f"⚠️ {ex_name.upper()}: нет данных")
        except Exception as e:
            st.warning(f"⚠️ {ex_name.upper()}: {str(e)[:50]}")
    
    if not exchanges:
        st.error("❌ Ни одна биржа не подключена. Работаем в демо-режиме.")
    
    return exchanges if exchanges else None

exchanges = init_exchanges()

# ====================== ФУНКЦИИ ДЛЯ СВЕЧЕЙ ======================
def create_candlestick_chart(ohlcv_data, symbol, source):
    if not ohlcv_data or len(ohlcv_data) == 0:
        return None
    
    df = pd.DataFrame(ohlcv_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    
    fig = go.Figure(data=[go.Candlestick(
        x=df['timestamp'],
        open=df['open'],
        high=df['high'],
        low=df['low'],
        close=df['close'],
        name='Японские свечи'
    )])
    
    fig.update_layout(
        title=f"{symbol}/USDT — {source}",
        xaxis_title="Время",
        yaxis_title="Цена (USDT)",
        template="plotly_dark",
        height=500,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(20,20,50,0.5)",
        font=dict(color="white")
    )
    
    fig.update_xaxes(gridcolor="rgba(100,100,150,0.3)")
    fig.update_yaxes(gridcolor="rgba(100,100,150,0.3)")
    
    return fig

def get_real_candles(symbol, exchange_name="okx"):
    if not exchanges or exchange_name not in exchanges:
        return None, None
    try:
        ohlcv = exchanges[exchange_name].fetch_ohlcv(f"{symbol}/USDT", '1h', limit=60)
        if ohlcv and len(ohlcv) > 0:
            return ohlcv, f"{exchange_name.upper()} (реальные данные)"
    except:
        pass
    return None, None

def get_simulated_candles(symbol):
    simulated_data = []
    base_price = random.uniform(100, 50000)
    for i in range(60):
        open_price = base_price + random.uniform(-500, 500)
        close_price = open_price + random.uniform(-300, 300)
        high_price = max(open_price, close_price) + random.uniform(0, 200)
        low_price = min(open_price, close_price) - random.uniform(0, 200)
        simulated_data.append([i, open_price, high_price, low_price, close_price, 0])
        base_price = close_price
    return simulated_data, "Симуляция (нет доступа к биржам)"

def get_price(symbol, mode):
    if mode == "Реальные данные" and exchanges:
        for ex_name in EXCHANGE_LIST:
            if ex_name in exchanges:
                try:
                    ticker = exchanges[ex_name].fetch_ticker(f"{symbol}/USDT")
                    if ticker and ticker.get('last'):
                        return ticker['last'], ex_name.upper()
                except:
                    continue
        return random.uniform(100, 60000), "Симуляция"
    else:
        return random.uniform(100, 60000), "Демо-режим"

# ====================== ФУНКЦИИ ДЛЯ ЭКСПОРТА ======================
def get_csv_download_link(df, filename):
    csv = df.to_csv(index=False)
    b64 = base64.b64encode(csv.encode()).decode()
    href = f'<a href="data:file/csv;base64,{b64}" download="{filename}" style="color: #00FF88;">📥 Скачать {filename}</a>'
    return href

# ====================== СЕССИЯ ======================
for key, default in {
    'logged_in': False,
    'username': None,
    'bot_running': False,
    'mode': "Реальные данные",
    'total_profit': 0.0,
    'today_profit': 0.0,
    'trade_count': 0,
    'fixed_profit': 0.0,
    'user_balance': 1000.0,
    'history': [],
    'portfolio': {a: 0.0 for a in DEFAULT_ASSETS},
    'daily_profits': {},
    'weekly_profits': {}
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

if os.path.exists(DATA_FILE):
    data = load_user_data()
    for key in ['total_profit', 'today_profit', 'trade_count', 'fixed_profit', 'user_balance', 'history', 'portfolio', 'daily_profits', 'weekly_profits']:
        if key in data:
            st.session_state[key] = data[key]

st.markdown('<h1 class="main-header">🚀 ARBITRAGE BOT PRO</h1>', unsafe_allow_html=True)

# ====================== РЕГИСТРАЦИЯ / ВХОД ======================
if not st.session_state.logged_in:
    tab_reg, tab_login = st.tabs(["📝 Регистрация", "🔑 Вход"])
    with tab_reg:
        username = st.text_input("Имя пользователя", key="reg_user")
        email = st.text_input("Email", key="reg_email")
        if st.button("Зарегистрироваться"):
            if username and email:
                st.session_state.logged_in = True
                st.session_state.username = username
                st.success("Регистрация успешна!")
                save_user_data()
                st.rerun()
    with tab_login:
        email = st.text_input("Email", key="login_email")
        if st.button("Войти"):
            if email:
                st.session_state.logged_in = True
                st.session_state.username = email.split('@')[0]
                st.success(f"Добро пожаловать, {st.session_state.username}!")
                st.rerun()
    st.stop()

# ====================== ОСНОВНОЙ ИНТЕРФЕЙС ======================
st.write(f"👤 **{st.session_state.username}** | Баланс: **{st.session_state.user_balance:.2f} USDT**")

mode = st.radio("Режим работы", ["Реальные данные", "Демо (симуляция)"], horizontal=True, index=0)
st.session_state.mode = mode

if st.session_state.mode == "Реальные данные":
    if exchanges:
        working_exchanges = ", ".join([ex.upper() for ex in exchanges.keys()])
        st.success(f"✅ Режим: реальные цены и свечи с бирж: {working_exchanges}")
    else:
        st.warning("⚠️ Биржи не подключены, работаем в демо-режиме")
        st.session_state.mode = "Демо (симуляция)"
else:
    st.info("🔮 Демо-режим: симуляция цен и свечей")

col1, col2, col3 = st.columns([3, 2, 2])
with col1:
    st.metric("💰 Общая прибыль", f"{st.session_state.total_profit:.4f} USDT")
with col2:
    st.metric("💵 Сегодня", f"{st.session_state.today_profit:.2f} USDT")
with col3:
    st.metric("📊 Сделок", st.session_state.trade_count)

c1, c2, c3 = st.columns(3)
if c1.button("▶ СТАРТ", type="primary", use_container_width=True):
    st.session_state.bot_running = True
if c2.button("⏸ ПАУЗА", use_container_width=True):
    st.session_state.bot_running = False
if c3.button("⏹ СТОП", use_container_width=True):
    st.session_state.bot_running = False

# ====================== ВКЛАДКИ ======================
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["📊 Dashboard", "📈 Японские свечи", "📦 Активы", "💰 Кошелёк", "📈 Доходность", "📜 История"])

# ====================== TAB 1: DASHBOARD ======================
with tab1:
    st.subheader("📊 Портфель и Котировки")
    data = []
    for asset in ASSET_CONFIG:
        symbol = asset['asset']
        price, source = get_price(symbol, st.session_state.mode)
        amount = st.session_state.portfolio.get(symbol, 0.0)
        value = amount * price
        data.append({"Токен": symbol, "Цена": f"${price:,.2f}", "Количество": f"{amount:.6f}", "Стоимость": f"${value:,.2f}", "Источник": source})
    st.dataframe(pd.DataFrame(data), use_container_width=True, hide_index=True)

# ====================== TAB 2: ЯПОНСКИЕ СВЕЧИ ======================
with tab2:
    st.subheader("📈 Японские свечи")
    col_a, col_b = st.columns(2)
    with col_a:
        selected_asset = st.selectbox("Выберите токен", [a['asset'] for a in ASSET_CONFIG])
    with col_b:
        # Только доступные биржи
        available_exchanges = list(exchanges.keys()) if exchanges else []
        if available_exchanges:
            selected_exchange = st.selectbox("Выберите биржу", available_exchanges)
        else:
            selected_exchange = None
            st.warning("Нет доступных бирж")
    
    if st.button("🔄 Обновить график", use_container_width=True):
        st.cache_data.clear()
    
    if st.session_state.mode == "Реальные данные" and selected_exchange:
        ohlcv, source = get_real_candles(selected_asset, selected_exchange)
        if ohlcv:
            fig = create_candlestick_chart(ohlcv, selected_asset, source)
            if fig:
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning(f"Не удалось получить данные с {selected_exchange.upper()}. Показываем симуляцию.")
            ohlcv_sim, source_sim = get_simulated_candles(selected_asset)
            fig = create_candlestick_chart(ohlcv_sim, selected_asset, source_sim)
            if fig:
                st.plotly_chart(fig, use_container_width=True)
    else:
        ohlcv_sim, source_sim = get_simulated_candles(selected_asset)
        fig = create_candlestick_chart(ohlcv_sim, selected_asset, source_sim)
        if fig:
            st.plotly_chart(fig, use_container_width=True)

# ====================== TAB 3: АКТИВЫ ======================
with tab3:
    st.subheader("📦 Активы и цели (редактирование)")
    cols = st.columns(5)
    for i, asset in enumerate(ASSET_CONFIG):
        with cols[i % 5]:
            name = asset['asset']
            current = DEFAULT_TARGETS.get(name, 0)
            new_target = st.number_input(f"Цель {name}", min_value=0.0, value=float(current), step=0.01, key=f"target_{name}")
            st.metric(name, f"Цель: {new_target}")

# ====================== TAB 4: КОШЕЛЁК ======================
with tab4:
    st.subheader("💰 Кошелёк")
    st.metric("Общий баланс USDT", f"{st.session_state.user_balance:.2f}")
    st.metric("Сегодня заработано", f"{st.session_state.today_profit:.2f} USDT")
    col_in, col_out = st.columns(2)
    with col_in:
        deposit = st.number_input("Сумма ввода (USDT)", min_value=10.0, step=10.0, key="deposit")
        if st.button("💰 Внести средства"):
            if deposit > 0:
                st.session_state.user_balance += deposit
                st.success(f"Внесено {deposit} USDT!")
                save_user_data()
                st.rerun()
    with col_out:
        withdraw = st.number_input("Сумма вывода (USDT)", min_value=10.0, max_value=float(st.session_state.user_balance), step=10.0, key="withdraw")
        address = st.text_input("Адрес кошелька", key="addr")
        if st.button("📤 Вывести средства"):
            if withdraw > 0 and address:
                st.session_state.user_balance -= withdraw
                st.success(f"Заявка на вывод {withdraw} USDT отправлена")
                save_user_data()
                st.rerun()

# ====================== TAB 5: ДОХОДНОСТЬ ======================
with tab5:
    st.subheader("📈 Графики доходности")
    
    if st.session_state.history:
        history_data = []
        for trade in st.session_state.history:
            if "✅" in trade and "+" in trade:
                try:
                    parts = trade.split("|")
                    time_str = parts[0].replace("✅", "").strip()
                    asset = parts[1].strip() if len(parts) > 1 else "Unknown"
                    profit_str = parts[2].split("+")[1].split()[0] if len(parts) > 2 else "0"
                    profit = float(profit_str)
                    date = datetime.now().strftime("%Y-%m-%d")
                    week = datetime.now().strftime("%Y-%W")
                    history_data.append({"datetime": time_str, "date": date, "week": week, "asset": asset, "profit": profit})
                except:
                    pass
        
        if history_data:
            df = pd.DataFrame(history_data)
            
            st.subheader("📊 Дневная доходность")
            daily_df = df.groupby('date')['profit'].sum().reset_index()
            daily_df.columns = ['Дата', 'Прибыль (USDT)']
            fig_daily = px.bar(daily_df, x='Дата', y='Прибыль (USDT)', title="Доходность по дням", color_discrete_sequence=['#00FF88'])
            fig_daily.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(20,20,50,0.5)")
            st.plotly_chart(fig_daily, use_container_width=True)
            
            st.subheader("📊 Накопленная прибыль")
            df['cumulative'] = df['profit'].cumsum()
            fig_cum = px.line(df, x='datetime', y='cumulative', title="Накопленная прибыль", color_discrete_sequence=['#00D4FF'])
            fig_cum.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(20,20,50,0.5)")
            st.plotly_chart(fig_cum, use_container_width=True)
            
            st.subheader("📊 Доходность по активам")
            asset_df = df.groupby('asset')['profit'].sum().reset_index()
            asset_df.columns = ['Актив', 'Прибыль (USDT)']
            fig_asset = px.pie(asset_df, values='Прибыль (USDT)', names='Актив', title="Распределение прибыли по активам")
            fig_asset.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(20,20,50,0.5)")
            st.plotly_chart(fig_asset, use_container_width=True)
        else:
            st.info("Недостаточно данных для построения графиков.")
    else:
        st.info("Нет данных о сделках. Запустите бота.")

# ====================== TAB 6: ИСТОРИЯ ======================
with tab6:
    st.subheader("📜 История сделок")
    
    if st.session_state.history:
        history_df = pd.DataFrame([{"Время": trade.split("|")[0].replace("✅", "").strip(), "Сделка": trade} for trade in st.session_state.history])
        st.dataframe(history_df, use_container_width=True, hide_index=True)
        
        st.subheader("📥 Экспорт истории")
        if st.button("📄 Экспорт в CSV", use_container_width=True):
            csv_data = history_df.to_csv(index=False)
            b64 = base64.b64encode(csv_data.encode()).decode()
            href = f'<a href="data:file/csv;base64,{b64}" download="history_{datetime.now().strftime("%Y%m%d")}.csv" style="color: #00FF88;">📥 Нажмите для скачивания CSV</a>'
            st.markdown(href, unsafe_allow_html=True)
        
        if st.button("🗑 Очистить историю", use_container_width=True):
            st.session_state.history = []
            save_user_data()
            st.rerun()
    else:
        st.info("Пока нет сделок. Запустите бота.")

# ====================== ОСНОВНАЯ ЛОГИКА ======================
if st.session_state.bot_running:
    time.sleep(2)
    asset = random.choice([a['asset'] for a in ASSET_CONFIG])
    
    if st.session_state.mode == "Реальные данные" and exchanges:
        try:
            price, _ = get_price(asset, st.session_state.mode)
            gross_profit = round(price * random.uniform(0.0005, 0.002), 4)
        except:
            gross_profit = round(random.uniform(0.3, 1.5), 4)
    else:
        gross_profit = round(random.uniform(0.3, 1.5), 4)

    fixed = round(gross_profit * 0.5, 4)
    reinvest = round(gross_profit * 0.5, 4)

    st.session_state.total_profit += gross_profit
    st.session_state.today_profit += gross_profit
    st.session_state.fixed_profit += fixed
    st.session_state.trade_count += 1
    st.session_state.user_balance += reinvest
    st.session_state.portfolio[asset] = st.session_state.portfolio.get(asset, 0.0) + (reinvest / 500)

    source_text = "реальные данные" if st.session_state.mode == "Реальные данные" else "демо"
    trade_text = f"✅ {datetime.now().strftime('%H:%M:%S')} | {asset} | +{gross_profit:.4f} USDT ({source_text}) | Фикс: {fixed:.4f} | Реинвест: {reinvest:.4f}"
    st.session_state.history.append(trade_text)

    save_user_data()
    st.toast(f"🎯 Сделка по {asset}! +{gross_profit} USDT", icon="💰")
    st.rerun()

st.caption("🚀 Arbitrage Bot PRO — работающие биржи: OKX, Gate.io, KuCoin")
