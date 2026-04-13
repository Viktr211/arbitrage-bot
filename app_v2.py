import streamlit as st
import time
import random
import json
import ccxt
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime
import os
import base64
import requests
from collections import deque

st.set_page_config(page_title="Arbitrage Bot PRO v2", layout="wide", page_icon="🚀")

# ====================== СТИЛЬ ======================
st.markdown("""
<style>
    .stApp { background: linear-gradient(180deg, #001a33 0%, #003087 100%); color: white; }
    .main-header { font-size: 28px; font-weight: bold; color: #00D4FF; text-align: center; }
    .stButton>button { border-radius: 30px; height: 48px; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# ====================== КОНФИГУРАЦИЯ ======================
DEFAULT_ASSETS = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "LINK", "SUI", "HYPE"]
DEFAULT_TARGETS = {
    "BTC": 0.5, "ETH": 2.0, "SOL": 50.0, "BNB": 20.0,
    "XRP": 10000.0, "ADA": 5000.0, "AVAX": 100.0,
    "LINK": 300.0, "SUI": 800.0, "HYPE": 400.0
}
ASSET_CONFIG = [{"asset": a} for a in DEFAULT_ASSETS]
EXCHANGE_LIST = ["okx", "gateio", "kucoin"]

# ====================== КЭШИРОВАНИЕ ======================
class PriceCache:
    def __init__(self, ttl=30):
        self.cache = {}
        self.ttl = ttl
        self.timestamps = {}
    
    def get(self, key):
        if key in self.cache:
            if time.time() - self.timestamps[key] < self.ttl:
                return self.cache[key]
        return None
    
    def set(self, key, value):
        self.cache[key] = value
        self.timestamps[key] = time.time()
    
    def clear(self):
        self.cache.clear()
        self.timestamps.clear()

price_cache = PriceCache(ttl=30)

# ====================== TELEGRAM ======================
def send_telegram_message(message):
    if st.session_state.get('telegram_token') and st.session_state.get('telegram_chat_id'):
        try:
            url = f"https://api.telegram.org/bot{st.session_state.telegram_token}/sendMessage"
            payload = {"chat_id": st.session_state.telegram_chat_id, "text": message, "parse_mode": "HTML"}
            requests.post(url, json=payload, timeout=5)
        except Exception as e:
            print(f"Telegram ошибка: {e}")

# ====================== СОХРАНЕНИЕ ДАННЫХ ======================
DATA_FILE = "user_data_v2.json"
API_FILE = "api_keys_v2.json"

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
        'user_balance': st.session_state.get('user_balance', 1000.0),
        'history': st.session_state.get('history', [])[-500:],
        'portfolio': st.session_state.get('portfolio', {}),
        'real_trades': st.session_state.get('real_trades', 0),
        'open_positions': st.session_state.get('open_positions', []),
        'stop_loss': st.session_state.get('stop_loss', 2.0),
        'take_profit': st.session_state.get('take_profit', 5.0)
    }
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def load_api_keys():
    if os.path.exists(API_FILE):
        try:
            with open(API_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_api_keys(keys):
    with open(API_FILE, 'w', encoding='utf-8') as f:
        json.dump(keys, f, ensure_ascii=False, indent=4)

# ====================== ПОДКЛЮЧЕНИЕ К БИРЖАМ ======================
@st.cache_resource
def init_exchanges(api_keys=None):
    exchanges = {}
    
    for ex_name in EXCHANGE_LIST:
        try:
            config = {
                'enableRateLimit': True,
                'options': {'defaultType': 'spot'}
            }
            
            if api_keys and ex_name in api_keys:
                keys = api_keys[ex_name]
                if keys.get('api_key') and keys.get('secret'):
                    config['apiKey'] = keys['api_key']
                    config['secret'] = keys['secret']
                    st.success(f"✅ {ex_name.upper()} — подключена (с API ключами)")
                else:
                    st.info(f"📊 {ex_name.upper()} — только чтение")
            else:
                st.info(f"📊 {ex_name.upper()} — только чтение")
            
            exchange_class = getattr(ccxt, ex_name)
            exchange = exchange_class(config)
            ticker = exchange.fetch_ticker('BTC/USDT')
            if ticker and ticker.get('last'):
                exchanges[ex_name] = exchange
        except Exception as e:
            st.warning(f"⚠️ {ex_name.upper()}: {str(e)[:50]}")
    
    return exchanges if exchanges else None

# ====================== ФУНКЦИИ ======================
def check_stop_loss_take_profit(entry_price, current_price):
    profit_pct = (current_price - entry_price) / entry_price * 100
    sl = st.session_state.get('stop_loss', 2.0)
    tp = st.session_state.get('take_profit', 5.0)
    
    if profit_pct <= -sl:
        return "stop_loss", profit_pct
    elif profit_pct >= tp:
        return "take_profit", profit_pct
    return None, profit_pct

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
    
    return fig

def get_real_candles(exchanges, symbol, exchange_name="okx"):
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
    return simulated_data, "Симуляция"

def get_price_with_cache(exchanges, symbol):
    cache_key = f"price_{symbol}"
    cached = price_cache.get(cache_key)
    if cached:
        return cached, "кэш"
    
    if exchanges:
        for ex_name in EXCHANGE_LIST:
            if ex_name in exchanges:
                try:
                    ticker = exchanges[ex_name].fetch_ticker(f"{symbol}/USDT")
                    if ticker and ticker.get('last'):
                        price_cache.set(cache_key, ticker['last'])
                        return ticker['last'], ex_name.upper()
                except:
                    continue
    return random.uniform(100, 60000), "симуляция"

# ====================== СЕССИЯ ======================
for key, default in {
    'logged_in': False,
    'username': None,
    'bot_running': False,
    'trade_mode': "Демо",
    'data_mode': "Реальные данные с бирж",
    'total_profit': 0.0,
    'today_profit': 0.0,
    'trade_count': 0,
    'user_balance': 1000.0,
    'history': [],
    'portfolio': {a: 0.0 for a in DEFAULT_ASSETS},
    'real_trades': 0,
    'exchanges': None,
    'api_keys': {},
    'open_positions': [],
    'stop_loss': 2.0,
    'take_profit': 5.0,
    'telegram_token': None,
    'telegram_chat_id': None
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

if os.path.exists(DATA_FILE):
    data = load_user_data()
    for key in ['total_profit', 'today_profit', 'trade_count', 'user_balance', 'history', 'portfolio', 'real_trades', 'open_positions', 'stop_loss', 'take_profit']:
        if key in data:
            st.session_state[key] = data[key]

st.session_state.api_keys = load_api_keys()

st.markdown('<h1 class="main-header">🚀 ARBITRAGE BOT PRO v2</h1>', unsafe_allow_html=True)

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

# Настройки Telegram
with st.expander("⚙️ Настройки уведомлений Telegram", expanded=False):
    tele_token = st.text_input("Telegram Bot Token", type="password", key="tele_token_input")
    tele_chat = st.text_input("Telegram Chat ID", key="tele_chat_input")
    if st.button("💾 Сохранить Telegram"):
        st.session_state.telegram_token = tele_token
        st.session_state.telegram_chat_id = tele_chat
        st.success("Настройки сохранены!")
        send_telegram_message("✅ Бот подключён к Telegram уведомлениям")

# Настройки рисков
with st.expander("🛡️ Настройки рисков", expanded=False):
    col_risk1, col_risk2 = st.columns(2)
    with col_risk1:
        new_sl = st.number_input("Стоп-лосс (%)", min_value=0.5, max_value=20.0, value=float(st.session_state.stop_loss), step=0.5)
    with col_risk2:
        new_tp = st.number_input("Тейк-профит (%)", min_value=1.0, max_value=50.0, value=float(st.session_state.take_profit), step=1.0)
    
    if st.button("💾 Применить настройки рисков"):
        st.session_state.stop_loss = new_sl
        st.session_state.take_profit = new_tp
        st.success(f"✅ Стоп-лосс: {new_sl}%, Тейк-профит: {new_tp}%")

# Режимы работы
col_mode1, col_mode2 = st.columns(2)
with col_mode1:
    trade_mode = st.radio("Режим торговли", ["Демо (симуляция)", "Реальный (API ключи)"], horizontal=True)
    st.session_state.trade_mode = "Демо" if "Демо" in trade_mode else "Реальный"

with col_mode2:
    data_mode = st.radio("Режим данных", ["Реальные данные с бирж", "Демо (симуляция)"], horizontal=True)
    st.session_state.data_mode = data_mode

# API ключи для реального режима
if st.session_state.trade_mode == "Реальный":
    with st.expander("🔐 API ключи", expanded=False):
        new_api_keys = {}
        for ex_name in EXCHANGE_LIST:
            st.subheader(f"{ex_name.upper()}")
            current_keys = st.session_state.api_keys.get(ex_name, {})
            api_key = st.text_input(f"API Key ({ex_name})", value=current_keys.get('api_key', ''), type="password", key=f"api_key_{ex_name}")
            secret = st.text_input(f"Secret Key ({ex_name})", value=current_keys.get('secret', ''), type="password", key=f"secret_{ex_name}")
            if api_key and secret:
                new_api_keys[ex_name] = {'api_key': api_key, 'secret': secret}
        
        if st.button("💾 Сохранить API ключи"):
            save_api_keys(new_api_keys)
            st.session_state.api_keys = new_api_keys
            st.success("API ключи сохранены!")
            st.rerun()

# Инициализация бирж
st.session_state.exchanges = init_exchanges(st.session_state.api_keys if st.session_state.trade_mode == "Реальный" else None)

# Статистика
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("💰 Общая прибыль", f"{st.session_state.total_profit:.4f} USDT")
with col2:
    st.metric("💵 Сегодня", f"{st.session_state.today_profit:.2f} USDT")
with col3:
    st.metric("📊 Сделок", f"{st.session_state.trade_count} ({st.session_state.real_trades} реал.)")
with col4:
    st.metric("🛡️ Риски", f"SL:{st.session_state.stop_loss}% / TP:{st.session_state.take_profit}%")

# Кнопки управления
c1, c2, c3 = st.columns(3)
if c1.button("▶ СТАРТ", type="primary", use_container_width=True):
    st.session_state.bot_running = True
    send_telegram_message(f"🚀 Бот запущен пользователем {st.session_state.username}")
if c2.button("⏸ ПАУЗА", use_container_width=True):
    st.session_state.bot_running = False
if c3.button("⏹ СТОП", use_container_width=True):
    st.session_state.bot_running = False
    st.session_state.open_positions = []

# ====================== ВКЛАДКИ ======================
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["📊 Dashboard", "📈 Японские свечи", "📦 Активы", "💰 Кошелёк", "🛡️ Риски", "📜 История"])

# TAB 1
with tab1:
    st.subheader("📊 Портфель и Котировки")
    table_data = []
    for asset in ASSET_CONFIG:
        symbol = asset['asset']
        price, source = get_price_with_cache(st.session_state.exchanges, symbol)
        amount = st.session_state.portfolio.get(symbol, 0.0)
        value = amount * price
        table_data.append({"Токен": symbol, "Цена": f"${price:,.2f}", "Количество": f"{amount:.6f}", "Стоимость": f"${value:,.2f}", "Источник": source})
    st.dataframe(pd.DataFrame(table_data), use_container_width=True, hide_index=True)

# TAB 2
with tab2:
    st.subheader("📈 Японские свечи")
    col_a, col_b = st.columns(2)
    with col_a:
        selected_asset = st.selectbox("Выберите токен", [a['asset'] for a in ASSET_CONFIG])
    with col_b:
        available = list(st.session_state.exchanges.keys()) if st.session_state.exchanges else []
        selected_exchange = st.selectbox("Выберите биржу", available if available else ["okx"])
    
    if st.button("🔄 Обновить график"):
        price_cache.clear()
        st.cache_data.clear()
    
    if st.session_state.data_mode == "Реальные данные с бирж" and st.session_state.exchanges:
        ohlcv, source = get_real_candles(st.session_state.exchanges, selected_asset, selected_exchange)
        if ohlcv:
            fig = create_candlestick_chart(ohlcv, selected_asset, source)
            if fig:
                st.plotly_chart(fig, use_container_width=True)
        else:
            ohlcv_sim, source_sim = get_simulated_candles(selected_asset)
            fig = create_candlestick_chart(ohlcv_sim, selected_asset, source_sim)
            if fig:
                st.plotly_chart(fig, use_container_width=True)
    else:
        ohlcv_sim, source_sim = get_simulated_candles(selected_asset)
        fig = create_candlestick_chart(ohlcv_sim, selected_asset, source_sim)
        if fig:
            st.plotly_chart(fig, use_container_width=True)

# TAB 3
with tab3:
    st.subheader("📦 Активы и цели")
    cols = st.columns(5)
    for i, asset in enumerate(ASSET_CONFIG):
        with cols[i % 5]:
            name = asset['asset']
            current = DEFAULT_TARGETS.get(name, 0)
            new_target = st.number_input(f"Цель {name}", min_value=0.0, value=float(current), step=0.01, key=f"target_{name}")
            st.metric(name, f"Цель: {new_target}")

# TAB 4
with tab4:
    st.subheader("💰 Кошелёк")
    st.metric("Общий баланс", f"{st.session_state.user_balance:.2f} USDT")
    col_in, col_out = st.columns(2)
    with col_in:
        deposit = st.number_input("Сумма ввода", min_value=10.0, step=10.0, key="deposit")
        if st.button("💰 Внести"):
            st.session_state.user_balance += deposit
            save_user_data()
            st.rerun()
    with col_out:
        withdraw = st.number_input("Сумма вывода", min_value=10.0, max_value=float(st.session_state.user_balance), step=10.0, key="withdraw")
        address = st.text_input("Адрес кошелька", key="addr")
        if st.button("📤 Вывести"):
            st.session_state.user_balance -= withdraw
            save_user_data()
            st.rerun()

# TAB 5
with tab5:
    st.subheader("🛡️ Открытые позиции")
    if st.session_state.open_positions:
        positions_to_remove = []
        for idx, pos in enumerate(st.session_state.open_positions):
            current_price, _ = get_price_with_cache(st.session_state.exchanges, pos['asset'])
            action, profit_pct = check_stop_loss_take_profit(pos['entry_price'], current_price)
            
            col_pos1, col_pos2, col_pos3, col_pos4 = st.columns(4)
            col_pos1.write(f"**{pos['asset']}**")
            col_pos2.write(f"Вход: ${pos['entry_price']:.2f}")
            col_pos3.write(f"Текущая: ${current_price:.2f} ({profit_pct:.2f}%)")
            if col_pos4.button(f"Закрыть", key=f"close_{pos['asset']}_{idx}"):
                positions_to_remove.append(pos)
                st.rerun()
            
            if action == "stop_loss":
                st.warning(f"⚠️ СТОП-ЛОСС по {pos['asset']}! Убыток: {abs(profit_pct):.2f}%")
                positions_to_remove.append(pos)
                send_telegram_message(f"🔴 СТОП-ЛОСС по {pos['asset']}! Убыток: {abs(profit_pct):.2f}%")
                st.rerun()
            elif action == "take_profit":
                st.success(f"✅ ТЕЙК-ПРОФИТ по {pos['asset']}! Прибыль: {profit_pct:.2f}%")
                positions_to_remove.append(pos)
                send_telegram_message(f"🟢 ТЕЙК-ПРОФИТ по {pos['asset']}! Прибыль: {profit_pct:.2f}%")
                st.rerun()
        
        for pos in positions_to_remove:
            if pos in st.session_state.open_positions:
                st.session_state.open_positions.remove(pos)
    else:
        st.info("Нет открытых позиций")

# TAB 6
with tab6:
    st.subheader("📜 История сделок")
    if st.session_state.history:
        for trade in reversed(st.session_state.history[-30:]):
            st.write(trade)
        if st.button("🗑 Очистить историю"):
            st.session_state.history = []
            save_user_data()
            st.rerun()
    else:
        st.info("Нет сделок")

# ====================== ОСНОВНАЯ ЛОГИКА ======================
if st.session_state.bot_running:
    time.sleep(3)
    asset = random.choice([a['asset'] for a in ASSET_CONFIG])
    price, source = get_price_with_cache(st.session_state.exchanges, asset)
    gross_profit = round(price * random.uniform(0.0005, 0.002), 2)
    
    fixed = round(gross_profit * 0.5, 2)
    reinvest = round(gross_profit * 0.5, 2)
    
    st.session_state.total_profit += gross_profit
    st.session_state.today_profit += gross_profit
    st.session_state.trade_count += 1
    st.session_state.user_balance += reinvest
    st.session_state.portfolio[asset] = st.session_state.portfolio.get(asset, 0.0) + (reinvest / 500)
    
    st.session_state.open_positions.append({
        'asset': asset,
        'entry_price': price,
        'entry_time': datetime.now().strftime('%H:%M:%S'),
        'amount': reinvest / price
    })
    
    trade_text = f"✅ {datetime.now().strftime('%H:%M:%S')} | {asset} | +{gross_profit:.2f} USDT | Фикс: {fixed:.2f} | Реинвест: {reinvest:.2f}"
    st.session_state.history.append(trade_text)
    
    send_telegram_message(f"🎯 Новая сделка!\nАктив: {asset}\nПрибыль: +{gross_profit} USDT")
    
    save_user_data()
    st.toast(f"🎯 Сделка по {asset}! +{gross_profit} USDT", icon="💰")
    st.rerun()

st.caption("🚀 Arbitrage Bot PRO v2 — кэш, стоп-лосс, тейк-профит, Telegram")
