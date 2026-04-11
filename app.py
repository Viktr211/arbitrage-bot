import streamlit as st
import time
import json
import random
import requests
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime

st.set_page_config(page_title="Arbitrage Bot PRO", layout="wide", page_icon="🚀")

# ==================== КРАСИВЫЙ CSS ====================
st.markdown("""
<style>
    .stApp { background: linear-gradient(135deg, #0a0a2a 0%, #1a1a4a 50%, #0a0a2a 100%); color: white; }
    .main-header { font-size: 42px; font-weight: bold; background: linear-gradient(90deg, #00D4FF, #FF6B6B); -webkit-background-clip: text; -webkit-text-fill-color: transparent; text-align: center; margin-bottom: 20px; }
    .sub-header { font-size: 20px; color: #8888FF; text-align: center; margin-bottom: 30px; }
    .stButton>button { border-radius: 30px; height: 48px; font-weight: bold; font-size: 16px; transition: all 0.3s; }
    .stButton>button:hover { transform: scale(1.02); }
    .stMetric label { font-size: 14px !important; color: #aaaaff !important; }
    .stMetric div[data-testid="stMetricValue"] { font-size: 28px !important; font-weight: bold; color: #00FF88 !important; }
    .register-form { background: rgba(20,20,50,0.8); backdrop-filter: blur(10px); padding: 30px; border-radius: 20px; border: 1px solid rgba(0,212,255,0.3); }
    .token-card { background: rgba(30,30,70,0.6); border-radius: 15px; padding: 15px; margin: 5px; text-align: center; transition: all 0.3s; }
    .token-card:hover { transform: translateY(-5px); background: rgba(50,50,100,0.8); }
    .profit-positive { color: #00FF88; font-weight: bold; }
    .profit-negative { color: #FF4444; font-weight: bold; }
    .sidebar-box { background: rgba(20,20,50,0.8); border-radius: 15px; padding: 20px; margin: 10px 0; }
</style>
""", unsafe_allow_html=True)

# ==================== ЗАГРУЗКА КОНФИГА ====================
def load_config():
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {
            "assets": ["BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOT", "AVAX", "MATIC", "LINK"],
            "targets": {"BTC": 0.05, "ETH": 0.5, "BNB": 1.0, "SOL": 5.0, "XRP": 100, "ADA": 200, "DOT": 10, "AVAX": 5, "MATIC": 100, "LINK": 10},
            "exchanges": ["binance", "kucoin", "bybit", "okx", "gateio", "huobi", "bitget", "bingx", "mexc", "bitfinex"]
        }

def save_config(config):
    with open('config.json', 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=4)

def load_users():
    try:
        with open('users.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def save_users(users):
    with open('users.json', 'w', encoding='utf-8') as f:
        json.dump(users, f, indent=4)

config = load_config()
ASSETS = config.get("assets", ["BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOT", "AVAX", "MATIC", "LINK"])
TARGETS = config.get("targets", {})
EXCHANGES = config.get("exchanges", ["binance", "kucoin", "bybit"])

# ==================== СЕССИЯ ====================
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'username' not in st.session_state:
    st.session_state.username = None
if 'wallet' not in st.session_state:
    st.session_state.wallet = None
if 'user_balance' not in st.session_state:
    st.session_state.user_balance = 1000.0
if 'user_withdrawals' not in st.session_state:
    st.session_state.user_withdrawals = []
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
if 'price_history' not in st.session_state:
    st.session_state.price_history = {asset: [] for asset in ASSETS}
if 'targets' not in st.session_state:
    st.session_state.targets = TARGETS.copy()

# ==================== ФУНКЦИИ ПОЛУЧЕНИЯ ЦЕН ====================

@st.cache_data(ttl=30)
def get_binance_price(symbol):
    try:
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}USDT"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return float(response.json()['price'])
        return None
    except:
        return None

@st.cache_data(ttl=30)
def get_kucoin_price(symbol):
    try:
        url = f"https://api.kucoin.com/api/v1/market/orderbook/level1?symbol={symbol}-USDT"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return float(response.json()['data']['price'])
        return None
    except:
        return None

@st.cache_data(ttl=30)
def get_bybit_price(symbol):
    try:
        url = f"https://api.bybit.com/v5/market/tickers?category=spot&symbol={symbol}USDT"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return float(response.json()['result']['list'][0]['lastPrice'])
        return None
    except:
        return None

@st.cache_data(ttl=30)
def get_okx_price(symbol):
    try:
        url = f"https://www.okx.com/api/v5/market/ticker?instId={symbol}-USDT"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return float(response.json()['data'][0]['last'])
        return None
    except:
        return None

def get_all_prices(symbol):
    prices = {}
    b_price = get_binance_price(symbol)
    if b_price:
        prices['binance'] = b_price
    k_price = get_kucoin_price(symbol)
    if k_price:
        prices['kucoin'] = k_price
    by_price = get_bybit_price(symbol)
    if by_price:
        prices['bybit'] = by_price
    return prices

# ==================== ФУНКЦИЯ ДЛЯ ЯПОНСКИХ СВЕЧЕЙ ====================

def create_candlestick_chart(df, title):
    """Создаёт японские свечи из данных"""
    if df.empty:
        return None
    
    fig = go.Figure(data=[go.Candlestick(
        x=df['time'],
        open=df['open'],
        high=df['high'],
        low=df['low'],
        close=df['close'],
        name='Японские свечи'
    )])
    
    fig.update_layout(
        title=title,
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

# ==================== РЕГИСТРАЦИЯ И ВХОД ====================

if not st.session_state.logged_in:
    col_left, col_center, col_right = st.columns([1, 2, 1])
    with col_center:
        st.markdown('<h1 class="main-header">🚀 ARBITRAGE BOT PRO</h1>', unsafe_allow_html=True)
        st.markdown('<p class="sub-header">Автоматический накопительный арбитраж с фиксацией прибыли в USDT</p>', unsafe_allow_html=True)
        
        # Рисунок японские свечи
        fig = go.Figure()
        fig.add_trace(go.Candlestick(
            x=['2024-01-01', '2024-01-02', '2024-01-03', '2024-01-04', '2024-01-05'],
            open=[100, 110, 105, 115, 120],
            high=[115, 115, 112, 120, 125],
            low=[95, 105, 100, 110, 115],
            close=[110, 105, 115, 120, 122]
        ))
        fig.update_layout(height=250, template="plotly_dark", showlegend=False, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        fig.update_xaxis(visible=False)
        fig.update_yaxis(visible=False)
        st.plotly_chart(fig, use_container_width=True)
        
        st.divider()
        
        tab_login, tab_register = st.tabs(["🔑 Вход", "📝 Регистрация"])
        
        with tab_login:
            with st.form("login_form"):
                email = st.text_input("Эл. почта")
                password = st.text_input("Пароль", type="password")
                submitted = st.form_submit_button("Войти", use_container_width=True)
                
                if submitted:
                    users = load_users()
                    if email in users and users[email].get('password') == password:
                        st.session_state.logged_in = True
                        st.session_state.username = users[email].get('name', email)
                        st.session_state.wallet = users[email].get('wallet', '')
                        st.success(f"Добро пожаловать, {users[email].get('name', email)}!")
                        st.rerun()
                    else:
                        st.error("❌ Неверный email или пароль!")
        
        with tab_register:
            with st.form("register_form"):
                st.markdown('<div class="register-form">', unsafe_allow_html=True)
                full_name = st.text_input("ФИО")
                country = st.text_input("Страна")
                city = st.text_input("Город")
                email = st.text_input("Эл. почта")
                wallet = st.text_input("Кошелёк (USDT или другой адрес)")
                password = st.text_input("Пароль", type="password")
                confirm_password = st.text_input("Подтвердите пароль", type="password")
                submitted = st.form_submit_button("Зарегистрироваться", use_container_width=True)
                st.markdown('</div>', unsafe_allow_html=True)
                
                if submitted:
                    if not all([full_name, country, city, email, wallet]):
                        st.error("❌ Заполните все поля!")
                    elif len(password) < 4:
                        st.error("❌ Пароль должен быть не менее 4 символов!")
                    elif password != confirm_password:
                        st.error("❌ Пароли не совпадают!")
                    else:
                        users = load_users()
                        if email in users:
                            st.error("❌ Пользователь с таким email уже существует!")
                        else:
                            users[email] = {
                                'name': full_name, 'country': country, 'city': city,
                                'wallet': wallet, 'password': password,
                                'registered_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                'balance': 1000.0, 'withdrawals': []
                            }
                            save_users(users)
                            st.success("✅ Регистрация успешна! Теперь войдите.")
                            st.rerun()
    
    st.stop()

# ==================== ОСНОВНОЙ ИНТЕРФЕЙС ====================

# Верхняя панель
st.markdown('<h1 class="main-header">🚀 ARBITRAGE BOT PRO</h1>', unsafe_allow_html=True)

col0a, col0b, col0c, col0d, col0e = st.columns([2, 2, 2, 2, 1])
with col0a:
    st.write(f"👤 **{st.session_state.username}**")
with col0b:
    st.write(f"💳 **Кошелёк:** {st.session_state.wallet[:20]}..." if len(st.session_state.wallet) > 20 else f"💳 **Кошелёк:** {st.session_state.wallet}")
with col0c:
    st.write(f"📅 **Старт:** {datetime.now().strftime('%d.%m.%Y %H:%M')}")
with col0d:
    st.metric("💰 Баланс", f"{st.session_state.user_balance:.2f} USDT")
with col0e:
    if st.button("🚪 Выйти"):
        st.session_state.logged_in = False
        st.rerun()

st.divider()

# Статистика
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("💰 Общая прибыль", f"{st.session_state.total_profit:.4f} USDT")
with col2:
    st.metric("📊 Сделок", st.session_state.trade_count)
with col3:
    status = "🟢 Работает" if st.session_state.bot_running else "🔴 Остановлен"
    st.metric("Статус", status)

# Кнопки управления
c1, c2, c3 = st.columns(3)
if c1.button("▶ СТАРТ", type="primary", use_container_width=True):
    st.session_state.bot_running = True
if c2.button("⏸ ПАУЗА", use_container_width=True):
    st.session_state.bot_running = False
if c3.button("⏹ СТОП", use_container_width=True):
    st.session_state.bot_running = False

st.success("✅ Режим: реальные цены с бирж")

# ==================== ВКЛАДКИ ====================
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["📊 Dashboard", "📈 Графики", "📦 Активы", "💰 Личный кабинет", "⚙ Настройка целей", "📜 История"])

# ==================== TAB 1: DASHBOARD ====================
with tab1:
    st.subheader("📊 Арбитражные возможности")
    
    # Токены в виде карточек
    cols = st.columns(5)
    for i, asset in enumerate(ASSETS[:10]):
        with cols[i % 5]:
            prices = get_all_prices(asset)
            price = list(prices.values())[0] if prices else 0
            st.markdown(f"""
            <div class="token-card">
                <h3>{asset}</h3>
                <p>${price:,.2f}</p>
            </div>
            """, unsafe_allow_html=True)
    
    st.divider()
    
    for asset in ASSETS:
        with st.expander(f"📊 {asset}/USDT", expanded=False):
            prices = get_all_prices(asset)
            if prices:
                cols = st.columns(len(prices))
                for i, (ex, price) in enumerate(prices.items()):
                    with cols[i]:
                        st.metric(ex.upper(), f"${price:,.2f}")
                
                if len(prices) >= 2:
                    min_ex = min(prices, key=prices.get)
                    max_ex = max(prices, key=prices.get)
                    spread = (prices[max_ex] - prices[min_ex]) / prices[min_ex] * 100
                    if spread > 0.3:
                        st.info(f"🎯 Арбитраж: купить на **{min_ex.upper()}** (${prices[min_ex]:,.2f}), продать на **{max_ex.upper()}** (${prices[max_ex]:,.2f}) → +{spread:.2f}%")
            else:
                st.warning("Нет данных")

# ==================== TAB 2: ГРАФИКИ (ЯПОНСКИЕ СВЕЧИ) ====================
with tab2:
    st.subheader("📈 Японские свечи — графики цен")
    
    selected_asset = st.selectbox("Выберите актив", ASSETS)
    
    # Генерируем демо-данные для свечей (в реальном времени будут из API)
    df_candles = pd.DataFrame({
        'time': pd.date_range(end=datetime.now(), periods=30, freq='H'),
        'open': [random.uniform(100, 50000) for _ in range(30)],
        'high': [random.uniform(100, 50000) for _ in range(30)],
        'low': [random.uniform(100, 50000) for _ in range(30)],
        'close': [random.uniform(100, 50000) for _ in range(30)]
    })
    
    fig = create_candlestick_chart(df_candles, f"{selected_asset}/USDT — График")
    if fig:
        st.plotly_chart(fig, use_container_width=True)
    
    st.divider()
    st.subheader("📊 Все активы")
    asset_cols = st.columns(5)
    for i, asset in enumerate(ASSETS):
        with asset_cols[i % 5]:
            if st.button(f"📈 {asset}", use_container_width=True):
                st.session_state.selected_chart_asset = asset
                st.rerun()

# ==================== TAB 3: АКТИВЫ ====================
with tab3:
    st.subheader("📦 Активы и цели накопления")
    
    for asset in ASSETS:
        target = st.session_state.targets.get(asset, 0)
        current = st.session_state.balances.get(asset, 0)
        col_a, col_b = st.columns([1, 3])
        col_a.metric(asset, f"{current:.6f}", f"цель: {target}")
        if target > 0:
            col_b.progress(min(current/target, 1.0))

# ==================== TAB 4: ЛИЧНЫЙ КАБИНЕТ ====================
with tab4:
    st.subheader("💰 Личный кабинет")
    
    col_w1, col_w2 = st.columns(2)
    with col_w1:
        st.markdown('<div class="sidebar-box">', unsafe_allow_html=True)
        st.subheader("💳 Баланс и средства")
        st.metric("Доступно средств", f"{st.session_state.user_balance:.2f} USDT")
        st.metric("Заработано ботом", f"{st.session_state.total_profit:.4f} USDT")
        st.metric("Всего сделок", st.session_state.trade_count)
        st.markdown('</div>', unsafe_allow_html=True)
    
    with col_w2:
        st.markdown('<div class="sidebar-box">', unsafe_allow_html=True)
        st.subheader("💸 Вывод средств")
        withdraw_amount = st.number_input("Сумма вывода (USDT)", min_value=1.0, max_value=float(st.session_state.user_balance), step=10.0)
        withdraw_address = st.text_input("Адрес кошелька для вывода", placeholder="Введите USDT адрес")
        if st.button("📤 Запросить вывод", use_container_width=True):
            if withdraw_amount > 0 and withdraw_address:
                st.session_state.user_balance -= withdraw_amount
                st.session_state.user_withdrawals.append({
                    'amount': withdraw_amount,
                    'address': withdraw_address,
                    'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'status': 'pending'
                })
                st.success(f"✅ Заявка на вывод {withdraw_amount} USDT отправлена!")
                st.rerun()
            else:
                st.error("❌ Введите сумму и адрес кошелька!")
        st.markdown('</div>', unsafe_allow_html=True)
    
    st.divider()
    st.subheader("📜 История выводов")
    if st.session_state.user_withdrawals:
        for w in reversed(st.session_state.user_withdrawals[-10:]):
            st.write(f"📤 {w['date']} — {w['amount']} USDT на {w['address'][:20]}... — {w['status']}")
    else:
        st.info("Нет запросов на вывод")

# ==================== TAB 5: НАСТРОЙКА ЦЕЛЕЙ ====================
with tab5:
    st.subheader("⚙ Настройка целей накопления")
    
    new_targets = {}
    cols = st.columns(5)
    for i, asset in enumerate(ASSETS):
        with cols[i % 5]:
            current_target = st.session_state.targets.get(asset, 0)
            new_target = st.number_input(f"{asset}", min_value=0.0, max_value=1000.0, value=float(current_target), step=0.1, key=f"target_{asset}")
            new_targets[asset] = new_target
    
    if st.button("💾 Сохранить цели", type="primary", use_container_width=True):
        st.session_state.targets = new_targets
        config['targets'] = new_targets
        save_config(config)
        st.success("✅ Цели сохранены!")

# ==================== TAB 6: ИСТОРИЯ ====================
with tab6:
    st.subheader("📜 История сделок")
    if st.session_state.history:
        for trade in reversed(st.session_state.history[-50:]):
            st.write(trade)
        if st.button("🗑 Очистить историю"):
            st.session_state.history = []
            st.rerun()
    else:
        st.info("Пока нет сделок. Запустите бота.")

# ==================== ОСНОВНАЯ ЛОГИКА ====================

if st.session_state.bot_running:
    time.sleep(5)
    
    for asset in ASSETS:
        prices = get_all_prices(asset)
        if len(prices) >= 2:
            min_price = min(prices.values())
            max_price = max(prices.values())
            spread = (max_price - min_price) / min_price * 100
            
            if spread > 0.5:
                profit = round(10 * (spread / 100), 4)
                st.session_state.total_profit += profit
                st.session_state.user_balance += profit
                st.session_state.trade_count += 1
                st.session_state.balances[asset] = st.session_state.balances.get(asset, 0) + 0.001
                
                min_ex = min(prices, key=prices.get)
                max_ex = max(prices, key=prices.get)
                
                trade_text = f"✅ {datetime.now().strftime('%H:%M:%S')} | {asset} | Купить на {min_ex.upper()} | Продать на {max_ex.upper()} | +{profit} USDT"
                st.session_state.history.append(trade_text)
                
                # Сохраняем в users.json баланс пользователя
                users = load_users()
                for email, data in users.items():
                    if data.get('name') == st.session_state.username:
                        users[email]['balance'] = st.session_state.user_balance
                        save_users(users)
                        break
                break
    
    st.rerun()

st.caption("🚀 Arbitrage Bot PRO — реальные цены, японские свечи, 10 токенов, 10 бирж, личный кабинет")


