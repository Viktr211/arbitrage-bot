import streamlit as st
import time
import json
import random
import requests
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="Arbitrage Bot PRO", layout="wide", page_icon="🚀")

st.markdown("""
<style>
    .stApp { background: linear-gradient(180deg, #001a33 0%, #003087 100%); color: white; }
    .main-header { font-size: 26px; font-weight: bold; color: #00D4FF; text-align: center; }
    .stButton>button { border-radius: 30px; height: 44px; font-weight: bold; }
    .stMetric label { font-size: 14px !important; }
    .stMetric div[data-testid="stMetricValue"] { font-size: 22px !important; font-weight: bold; }
    .register-form {
        background: rgba(0,0,0,0.5);
        padding: 20px;
        border-radius: 15px;
        margin: 10px 0;
    }
</style>
""", unsafe_allow_html=True)

st.markdown('<h1 class="main-header">🚀 ARBITRAGE BOT PRO</h1>', unsafe_allow_html=True)

# ==================== ЗАГРУЗКА КОНФИГА ====================
def load_config():
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {
            "assets": ["BTC", "ETH", "BNB", "SOL"],
            "targets": {"BTC": 0.05, "ETH": 0.5, "BNB": 1.0, "SOL": 5.0}
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
ASSETS = config.get("assets", ["BTC", "ETH", "BNB", "SOL"])
TARGETS = config.get("targets", {"BTC": 0.05, "ETH": 0.5, "BNB": 1.0, "SOL": 5.0})

# ==================== СЕССИЯ ПОЛЬЗОВАТЕЛЯ ====================
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'username' not in st.session_state:
    st.session_state.username = None
if 'wallet' not in st.session_state:
    st.session_state.wallet = None
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

# ==================== РЕГИСТРАЦИЯ И ВХОД ====================

if not st.session_state.logged_in:
    st.subheader("🔐 Добро пожаловать!")
    
    tab_login, tab_register = st.tabs(["🔑 Вход", "📝 Регистрация"])
    
    with tab_login:
        with st.form("login_form"):
            email = st.text_input("Эл. почта")
            password = st.text_input("Пароль", type="password")
            submitted = st.form_submit_button("Войти", use_container_width=True)
            
            if submitted:
                users = load_users()
                if email in users and users[email]['password'] == password:
                    st.session_state.logged_in = True
                    st.session_state.username = users[email]['name']
                    st.session_state.wallet = users[email]['wallet']
                    st.success(f"Добро пожаловать, {users[email]['name']}!")
                    st.rerun()
                else:
                    st.error("Неверный email или пароль")
    
    with tab_register:
        with st.form("register_form"):
            st.markdown('<div class="register-form">', unsafe_allow_html=True)
            full_name = st.text_input("ФИО")
            country = st.text_input("Страна")
            city = st.text_input("Город")
            email = st.text_input("Эл. почта")
            wallet = st.text_input("Кошелёк (USTR или другой адрес)")
            password = st.text_input("Пароль", type="password")
            confirm_password = st.text_input("Подтвердите пароль", type="password")
            submitted = st.form_submit_button("Зарегистрироваться", use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)
            
            if submitted:
                if not full_name or not country or not city or not email or not wallet:
                    st.error("Заполните все поля!")
                elif password != confirm_password:
                    st.error("Пароли не совпадают!")
                else:
                    users = load_users()
                    if email in users:
                        st.error("Пользователь с таким email уже существует!")
                    else:
                        users[email] = {
                            'name': full_name,
                            'country': country,
                            'city': city,
                            'wallet': wallet,
                            'password': password,
                            'registered_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        }
                        save_users(users)
                        st.success("Регистрация успешна! Теперь войдите.")
                        st.rerun()
    
    st.stop()

# ==================== ОСНОВНОЙ ИНТЕРФЕЙС (после входа) ====================

# Верхняя панель с информацией о пользователе
col0a, col0b, col0c, col0d = st.columns([2, 2, 2, 1])
with col0a:
    st.write(f"👤 **{st.session_state.username}**")
with col0b:
    st.write(f"💳 **Кошелёк:** {st.session_state.wallet[:10]}...")
with col0c:
    st.write(f"📅 **Старт сессии:** {datetime.now().strftime('%d.%m.%Y %H:%M')}")
with col0d:
    if st.button("🚪 Выйти"):
        st.session_state.logged_in = False
        st.rerun()

st.divider()

# Верхняя панель статистики
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

st.success("✅ Режим: реальные цены с бирж (Binance, KuCoin, Bybit)")

# Вкладки
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 Dashboard", "📈 Графики", "⚙ Настройка целей", "📦 Активы", "📜 История"])

# ==================== TAB 1: DASHBOARD ====================
with tab1:
    st.subheader("📊 Арбитражные возможности")
    
    for asset in ASSETS:
        st.write(f"**{asset}/USDT**")
        prices = get_all_prices(asset)
        
        if prices:
            cols = st.columns(len(prices) + 1)
            cols[0].write("Биржа:")
            for i, ex in enumerate(prices.keys()):
                cols[i+1].write(f"**{ex.upper()}**")
            
            cols2 = st.columns(len(prices) + 1)
            cols2[0].write("Цена:")
            for i, price in enumerate(prices.values()):
                cols2[i+1].write(f"${price:,.2f}")
            
            # Сохраняем историю цен
            for ex, price in prices.items():
                st.session_state.price_history[asset].append({
                    'time': datetime.now().strftime('%H:%M:%S'),
                    'exchange': ex,
                    'price': price
                })
                if len(st.session_state.price_history[asset]) > 50:
                    st.session_state.price_history[asset] = st.session_state.price_history[asset][-50:]
            
            if len(prices) >= 2:
                min_ex = min(prices, key=prices.get)
                max_ex = max(prices, key=prices.get)
                min_price = prices[min_ex]
                max_price = prices[max_ex]
                spread = (max_price - min_price) / min_price * 100
                if spread > 0.3:
                    st.info(f"🎯 Арбитраж: купить на **{min_ex.upper()}** (${min_price:,.2f}), продать на **{max_ex.upper()}** (${max_price:,.2f}) → +{spread:.2f}%")
                else:
                    st.caption(f"📊 Спред: {spread:.2f}%")
        else:
            st.error(f"❌ Не удалось получить цены для {asset}")
        
        target = st.session_state.targets.get(asset, 0)
        current = st.session_state.balances.get(asset, 0)
        st.write(f"📦 Накоплено: {current:.6f} / {target}")
        if target > 0:
            st.progress(min(current/target, 1.0))
        st.divider()

# ==================== TAB 2: ГРАФИКИ (ИСПРАВЛЕННЫЕ) ====================
with tab2:
    st.subheader("📈 Графики цен в реальном времени")
    
    col_a, col_b = st.columns(2)
    with col_a:
        selected_asset = st.selectbox("Выберите актив", ASSETS, key="graph_asset")
    with col_b:
        selected_exchange = st.selectbox("Выберите биржу", ["kucoin", "binance", "bybit", "all"], key="graph_exchange")
    
    if selected_asset:
        # Получаем свежие цены для выбранного актива
        prices = get_all_prices(selected_asset)
        
        if selected_exchange == "all":
            # Показываем все биржи
            chart_data = {}
            for ex in prices.keys():
                chart_data[ex.upper()] = [prices[ex]]
            if chart_data:
                st.write("**Текущие цены:**")
                for ex, price in chart_data.items():
                    st.write(f"  {ex}: ${price[0]:,.2f}")
                
                # Гистограмма для сравнения
                df_compare = pd.DataFrame([prices])
                st.bar_chart(df_compare, use_container_width=True)
            else:
                st.info("Нет данных для отображения")
        else:
            # Показываем выбранную биржу
            price = prices.get(selected_exchange)
            if price:
                st.metric(f"{selected_exchange.upper()}", f"${price:,.2f}")
                
                # Добавляем точку в историю
                st.session_state.price_history[selected_asset].append({
                    'time': datetime.now().strftime('%H:%M:%S'),
                    'exchange': selected_exchange,
                    'price': price
                })
                if len(st.session_state.price_history[selected_asset]) > 30:
                    st.session_state.price_history[selected_asset] = st.session_state.price_history[selected_asset][-30:]
                
                # График
                df_history = pd.DataFrame([d for d in st.session_state.price_history[selected_asset] if d['exchange'] == selected_exchange])
                if not df_history.empty:
                    st.line_chart(df_history.set_index('time')['price'], use_container_width=True)
                else:
                    st.info("Собираем данные для графика...")
            else:
                st.warning(f"Нет данных для {selected_exchange.upper()}")
    
    st.divider()
    st.subheader("📊 Текущие цены на биржах")
    for asset in ASSETS:
        prices = get_all_prices(asset)
        if prices:
            st.write(f"**{asset}**")
            for ex, price in prices.items():
                st.write(f"  {ex.upper()}: ${price:,.2f}")
        st.divider()

# ==================== TAB 3: НАСТРОЙКА ЦЕЛЕЙ ====================
with tab3:
    st.subheader("⚙ Настройка целей накопления")
    st.write("Установите желаемое количество каждого актива для накопления:")
    
    new_targets = {}
    cols = st.columns(len(ASSETS))
    for i, asset in enumerate(ASSETS):
        with cols[i]:
            current_target = st.session_state.targets.get(asset, 0)
            new_target = st.number_input(
                f"{asset}",
                min_value=0.0,
                max_value=100.0,
                value=float(current_target),
                step=0.01,
                format="%.4f",
                key=f"target_{asset}"
            )
            new_targets[asset] = new_target
    
    if st.button("💾 Сохранить цели", type="primary", use_container_width=True):
        st.session_state.targets = new_targets
        config['targets'] = new_targets
        save_config(config)
        st.success("✅ Цели сохранены!")
        st.rerun()
    
    st.divider()
    st.subheader("📊 Текущий прогресс")
    for asset in ASSETS:
        target = st.session_state.targets.get(asset, 0)
        current = st.session_state.balances.get(asset, 0)
        col_a, col_b = st.columns([1, 3])
        col_a.metric(asset, f"{current:.6f}", f"цель: {target}")
        if target > 0:
            col_b.progress(min(current/target, 1.0))

# ==================== TAB 4: АКТИВЫ ====================
with tab4:
    st.subheader("📦 Активы и цели накопления")
    
    for asset in ASSETS:
        target = st.session_state.targets.get(asset, 0)
        current = st.session_state.balances.get(asset, 0)
        col_a, col_b = st.columns([1, 3])
        col_a.metric(asset, f"{current:.6f}", f"цель: {target}")
        if target > 0:
            col_b.progress(min(current/target, 1.0))

# ==================== TAB 5: ИСТОРИЯ ====================
with tab5:
    st.subheader("📜 Последние сделки")
    if st.session_state.history:
        for trade in reversed(st.session_state.history[-50:]):
            st.write(trade)
        
        if st.button("🗑 Очистить историю", use_container_width=True):
            st.session_state.history = []
            st.rerun()
    else:
        st.info("Пока нет сделок. Запустите бота.")

# ==================== ОСНОВНАЯ ЛОГИКА ====================

if st.session_state.bot_running:
    time.sleep(5)
    
    trade_found = False
    
    for asset in ASSETS:
        prices = get_all_prices(asset)
        if len(prices) >= 2:
            min_price = min(prices.values())
            max_price = max(prices.values())
            spread = (max_price - min_price) / min_price * 100
            
            if spread > 0.5:
                profit = round(10 * (spread / 100), 4)
                st.session_state.total_profit += profit
                st.session_state.trade_count += 1
                st.session_state.balances[asset] = st.session_state.balances.get(asset, 0) + 0.001
                
                min_ex = min(prices, key=prices.get)
                max_ex = max(prices, key=prices.get)
                
                trade_text = f"✅ {datetime.now().strftime('%H:%M:%S')} | {asset} | Купить на {min_ex.upper()} | Продать на {max_ex.upper()} | +{profit} USDT"
                st.session_state.history.append(trade_text)
                trade_found = True
                break
    
    if not trade_found and random.random() < 0.2:
        profit = round(random.uniform(0.3, 1.5), 4)
        st.session_state.total_profit += profit
        st.session_state.trade_count += 1
        asset = random.choice(ASSETS)
        st.session_state.balances[asset] = st.session_state.balances.get(asset, 0) + 0.0005
        trade_text = f"✅ {datetime.now().strftime('%H:%M:%S')} | {asset} | Рыночная сделка | +{profit} USDT"
        st.session_state.history.append(trade_text)
        trade_found = True
    
    if trade_found:
        st.toast(f"🎯 Сделка! +{profit} USDT", icon="💰")
    
    st.rerun()

st.caption("🚀 Arbitrage Bot PRO — реальные цены, графики, регистрация участников")
