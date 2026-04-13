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
import threading
import asyncio

st.set_page_config(page_title="Накопительный Арбитраж PRO", layout="wide", page_icon="🚀")

# ====================== СТИЛЬ ======================
st.markdown("""
<style>
    .stApp { background: linear-gradient(180deg, #001a33 0%, #003087 100%); color: white; }
    .main-header { font-size: 28px; font-weight: bold; color: #00D4FF; text-align: center; }
    .stButton>button { border-radius: 30px; height: 48px; font-weight: bold; }
    .success-card { background: rgba(0,255,100,0.1); border-radius: 10px; padding: 10px; margin: 5px 0; }
    .warning-card { background: rgba(255,100,0,0.1); border-radius: 10px; padding: 10px; margin: 5px 0; }
    .info-card { background: rgba(0,100,255,0.1); border-radius: 10px; padding: 10px; margin: 5px 0; }
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

# Главная биржа (где хранятся токены)
MAIN_EXCHANGE = "okx"
# Вспомогательные биржи (где хранятся USDT)
AUX_EXCHANGES = ["gateio", "kucoin"]

# ====================== СТАТИСТИКА ПЕРЕВОДОВ ======================
class TransferStats:
    def __init__(self):
        self.history = []
    
    def add_transfer(self, asset, from_exchange, to_exchange, amount, duration, success):
        self.history.append({
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'asset': asset,
            'from': from_exchange,
            'to': to_exchange,
            'amount': amount,
            'duration_sec': duration,
            'success': success
        })
        # Оставляем только последние 100 записей
        if len(self.history) > 100:
            self.history = self.history[-100:]
    
    def get_average_transfer_time(self, asset=None):
        transfers = [t for t in self.history if t['success']]
        if asset:
            transfers = [t for t in transfers if t['asset'] == asset]
        if not transfers:
            return 600  # 10 минут по умолчанию
        return sum(t['duration_sec'] for t in transfers) / len(transfers)
    
    def get_all_transfers(self):
        return self.history

transfer_stats = TransferStats()

# ====================== КЭШИРОВАНИЕ ======================
class PriceCache:
    def __init__(self, ttl=10):  # Уменьшил TTL для более быстрой реакции
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

price_cache = PriceCache(ttl=10)

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
DATA_FILE = "user_data_v3.json"
API_FILE = "api_keys_v3.json"

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
        'portfolio': st.session_state.get('portfolio', {}),  # Токены на главной бирже
        'usdt_reserves': st.session_state.get('usdt_reserves', {}),  # USDT на вспомогательных биржах
        'transfer_history': st.session_state.get('transfer_history', []),
        'pending_transfers': st.session_state.get('pending_transfers', [])
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
    
    # Все биржи (главная + вспомогательные)
    all_exchanges = [MAIN_EXCHANGE] + AUX_EXCHANGES
    
    for ex_name in all_exchanges:
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

# ====================== ФУНКЦИИ АРБИТРАЖА ======================
def get_price_with_cache(exchanges, symbol, exchange_name):
    """Получает цену с кэшированием для конкретной биржи"""
    cache_key = f"price_{exchange_name}_{symbol}"
    cached = price_cache.get(cache_key)
    if cached:
        return cached
    
    if exchanges and exchange_name in exchanges:
        try:
            ticker = exchanges[exchange_name].fetch_ticker(f"{symbol}/USDT")
            if ticker and ticker.get('last'):
                price_cache.set(cache_key, ticker['last'])
                return ticker['last']
        except:
            pass
    return None

def find_arbitrage_opportunity(exchanges, assets, main_exchange, aux_exchanges):
    """Ищет арбитражную возможность между главной и вспомогательными биржами"""
    opportunities = []
    
    for asset in assets:
        symbol = asset['asset']
        main_price = get_price_with_cache(exchanges, symbol, main_exchange)
        if not main_price:
            continue
        
        for aux_ex in aux_exchanges:
            aux_price = get_price_with_cache(exchanges, symbol, aux_ex)
            if not aux_price:
                continue
            
            # На главной дороже, на вспомогательной дешевле
            if main_price > aux_price:
                spread_pct = (main_price - aux_price) / aux_price * 100
                # Учитываем комиссии (тейкер ~0.1% на каждой бирже + вывод ~0.05%)
                total_fees_pct = 0.25  # 0.1% + 0.1% + 0.05%
                net_spread = spread_pct - total_fees_pct
                
                if net_spread > 0.1:  # Минимальная прибыль 0.1%
                    profit_usdt = (main_price - aux_price) - (main_price * 0.001) - (aux_price * 0.001)
                    opportunities.append({
                        'asset': symbol,
                        'main_exchange': main_exchange,
                        'aux_exchange': aux_ex,
                        'main_price': main_price,
                        'aux_price': aux_price,
                        'spread_pct': round(spread_pct, 2),
                        'net_spread': round(net_spread, 2),
                        'profit_usdt': round(profit_usdt, 2)
                    })
    
    # Сортируем по максимальной прибыли
    opportunities.sort(key=lambda x: x['profit_usdt'], reverse=True)
    return opportunities

def execute_arbitrage(exchanges, opportunity, amount_usdt):
    """Исполняет арбитражную сделку: продажа на главной + покупка на вспомогательной"""
    try:
        asset = opportunity['asset']
        main_ex = opportunity['main_exchange']
        aux_ex = opportunity['aux_exchange']
        main_price = opportunity['main_price']
        aux_price = opportunity['aux_price']
        
        # Рассчитываем количество токена
        amount_token = amount_usdt / aux_price
        
        # 1. Продажа на главной бирже
        sell_order = exchanges[main_ex].create_market_sell_order(f"{asset}/USDT", amount_token)
        
        # 2. Покупка на вспомогательной бирже
        buy_order = exchanges[aux_ex].create_market_buy_order(f"{asset}/USDT", amount_token)
        
        return {
            'success': True,
            'asset': asset,
            'amount_token': amount_token,
            'sell_price': main_price,
            'buy_price': aux_price,
            'sell_order': sell_order,
            'buy_order': buy_order
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}

def transfer_token_back(exchanges, asset, amount, from_exchange, to_exchange):
    """Переводит токен обратно на главную биржу"""
    try:
        start_time = time.time()
        
        # Получаем адрес депозита на главной бирже
        deposit_address = exchanges[to_exchange].fetch_deposit_address(asset)
        
        # Выводим с вспомогательной биржи
        withdrawal = exchanges[from_exchange].withdraw(asset, amount, deposit_address['address'])
        
        duration = time.time() - start_time
        
        transfer_stats.add_transfer(asset, from_exchange, to_exchange, amount, duration, True)
        
        return {
            'success': True,
            'duration': duration,
            'withdrawal_id': withdrawal.get('id', 'unknown')
        }
    except Exception as e:
        transfer_stats.add_transfer(asset, from_exchange, to_exchange, amount, 0, False)
        return {'success': False, 'error': str(e)}

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
    'usdt_reserves': {ex: 10000.0 for ex in AUX_EXCHANGES},  # По 10000 USDT на каждой вспомогательной бирже
    'transfer_history': [],
    'pending_transfers': [],
    'exchanges': None,
    'api_keys': {},
    'telegram_token': None,
    'telegram_chat_id': None
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

if os.path.exists(DATA_FILE):
    data = load_user_data()
    for key in ['total_profit', 'today_profit', 'trade_count', 'user_balance', 'history', 'portfolio', 'usdt_reserves', 'transfer_history', 'pending_transfers']:
        if key in data:
            st.session_state[key] = data[key]

st.session_state.api_keys = load_api_keys()

st.markdown('<h1 class="main-header">🚀 НАКОПИТЕЛЬНЫЙ АРБИТРАЖ PRO</h1>', unsafe_allow_html=True)

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
st.write(f"👤 **{st.session_state.username}**")

# Статистика
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("💰 Общая прибыль", f"{st.session_state.total_profit:.2f} USDT")
with col2:
    st.metric("📊 Сделок", st.session_state.trade_count)
with col3:
    st.metric("🏦 Главная биржа", MAIN_EXCHANGE.upper())
with col4:
    st.metric("🔄 Вспом. биржи", ", ".join([ex.upper() for ex in AUX_EXCHANGES]))

# Кнопки управления
c1, c2, c3 = st.columns(3)
if c1.button("▶ СТАРТ", type="primary", use_container_width=True):
    st.session_state.bot_running = True
if c2.button("⏸ ПАУЗА", use_container_width=True):
    st.session_state.bot_running = False
if c3.button("⏹ СТОП", use_container_width=True):
    st.session_state.bot_running = False

# ====================== ВКЛАДКИ ======================
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 Dashboard", "🔄 Активный арбитраж", "📦 Портфель", "📊 Статистика переводов", "📜 История"])

# TAB 1: Dashboard
with tab1:
    st.subheader("📊 Текущие цены")
    
    # Получаем цены со всех бирж
    if st.session_state.exchanges:
        for asset in ASSET_CONFIG:
            symbol = asset['asset']
            st.write(f"**{symbol}/USDT**")
            
            cols = st.columns(len([MAIN_EXCHANGE] + AUX_EXCHANGES))
            for i, ex in enumerate([MAIN_EXCHANGE] + AUX_EXCHANGES):
                price = get_price_with_cache(st.session_state.exchanges, symbol, ex)
                if price:
                    cols[i].metric(ex.upper(), f"${price:,.2f}")
                else:
                    cols[i].metric(ex.upper(), "❌")
            st.divider()

# TAB 2: Активный арбитраж
with tab2:
    st.subheader("🔄 Поиск арбитражных возможностей")
    
    if st.button("🔍 Найти возможности", use_container_width=True):
        price_cache.clear()
        opportunities = find_arbitrage_opportunity(
            st.session_state.exchanges, 
            ASSET_CONFIG, 
            MAIN_EXCHANGE, 
            AUX_EXCHANGES
        )
        
        if opportunities:
            st.success(f"✅ Найдено {len(opportunities)} возможностей!")
            for opp in opportunities[:10]:
                st.markdown(f"""
                <div class="success-card">
                    🎯 <b>{opp['asset']}</b><br>
                    📈 {opp['main_exchange'].upper()}: ${opp['main_price']:,.2f}<br>
                    📉 {opp['aux_exchange'].upper()}: ${opp['aux_price']:,.2f}<br>
                    💰 Спред: {opp['spread_pct']}% | Чистая прибыль: {opp['net_spread']}% (~${opp['profit_usdt']} на сделку)
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("Арбитражных возможностей не найдено. Попробуйте позже.")
    
    st.divider()
    st.subheader("⚡ Исполнение сделки")
    
    col_ex1, col_ex2, col_ex3 = st.columns(3)
    with col_ex1:
        selected_asset = st.selectbox("Актив", [a['asset'] for a in ASSET_CONFIG])
    with col_ex2:
        selected_amount = st.number_input("Сумма (USDT)", min_value=100.0, value=1000.0, step=100.0)
    with col_ex3:
        if st.button("🚀 Исполнить арбитраж", type="primary"):
            # Находим лучшую возможность для выбранного актива
            opportunities = find_arbitrage_opportunity(
                st.session_state.exchanges, 
                [{'asset': selected_asset}], 
                MAIN_EXCHANGE, 
                AUX_EXCHANGES
            )
            if opportunities:
                best = opportunities[0]
                st.info(f"Исполняем сделку по {selected_asset}: продажа на {best['main_exchange'].upper()} по ${best['main_price']:.2f}, покупка на {best['aux_exchange'].upper()} по ${best['aux_price']:.2f}")
                
                result = execute_arbitrage(st.session_state.exchanges, best, selected_amount)
                if result['success']:
                    profit = round(selected_amount * (best['net_spread'] / 100), 2)
                    st.session_state.total_profit += profit
                    st.session_state.today_profit += profit
                    st.session_state.trade_count += 1
                    
                    st.success(f"✅ Сделка исполнена! Прибыль: +{profit} USDT")
                    send_telegram_message(f"🎯 Арбитраж по {selected_asset}! Прибыль: +{profit} USDT")
                    
                    # Добавляем задачу на перевод токена
                    st.session_state.pending_transfers.append({
                        'asset': selected_asset,
                        'amount': selected_amount / best['aux_price'],
                        'from': best['aux_exchange'],
                        'to': MAIN_EXCHANGE,
                        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    })
                    save_user_data()
                    st.rerun()
                else:
                    st.error(f"❌ Ошибка: {result.get('error', 'Неизвестная ошибка')}")
            else:
                st.warning("Нет арбитражных возможностей для этого актива")

# TAB 3: Портфель
with tab3:
    st.subheader("📦 Портфель токенов (главная биржа)")
    
    for asset in ASSET_CONFIG:
        symbol = asset['asset']
        amount = st.session_state.portfolio.get(symbol, 0.0)
        price = get_price_with_cache(st.session_state.exchanges, symbol, MAIN_EXCHANGE)
        value = amount * price if price else 0
        col_a, col_b, col_c = st.columns(3)
        col_a.write(f"**{symbol}**")
        col_b.write(f"Количество: {amount:.6f}")
        col_c.write(f"Стоимость: ${value:,.2f}")
    
    st.divider()
    st.subheader("💰 Резервы USDT на вспомогательных биржах")
    
    for ex in AUX_EXCHANGES:
        reserve = st.session_state.usdt_reserves.get(ex, 0)
        st.write(f"**{ex.upper()}**: {reserve:.2f} USDT")
    
    st.divider()
    st.subheader("⏳ Ожидают перевода")
    
    if st.session_state.pending_transfers:
        for transfer in st.session_state.pending_transfers:
            st.info(f"🔄 {transfer['asset']}: {transfer['amount']:.6f} с {transfer['from'].upper()} на {transfer['to'].upper()}")
        
        if st.button("✅ Подтвердить завершение перевода"):
            for transfer in st.session_state.pending_transfers:
                st.session_state.portfolio[transfer['asset']] = st.session_state.portfolio.get(transfer['asset'], 0) + transfer['amount']
            st.session_state.pending_transfers = []
            save_user_data()
            st.success("Переводы подтверждены!")
            st.rerun()
    else:
        st.info("Нет ожидающих переводов")

# TAB 4: Статистика переводов
with tab4:
    st.subheader("📊 Статистика времени переводов")
    
    transfers = transfer_stats.get_all_transfers()
    if transfers:
        df = pd.DataFrame(transfers)
        st.dataframe(df, use_container_width=True)
        
        st.subheader("📈 Среднее время перевода")
        for asset in DEFAULT_ASSETS:
            avg_time = transfer_stats.get_average_transfer_time(asset)
            st.write(f"{asset}: {avg_time:.0f} секунд ({avg_time/60:.1f} минут)")
    else:
        st.info("Нет данных о переводах")

# TAB 5: История
with tab5:
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

# ====================== ИНИЦИАЛИЗАЦИЯ БИРЖ ======================
if st.session_state.exchanges is None:
    with st.spinner("Подключение к биржам..."):
        st.session_state.exchanges = init_exchanges(st.session_state.api_keys)

# ====================== ОСНОВНАЯ ЛОГИКА (ФОНОВЫЙ АРБИТРАЖ) ======================
if st.session_state.bot_running and st.session_state.exchanges:
    time.sleep(5)
    
    opportunities = find_arbitrage_opportunity(
        st.session_state.exchanges, 
        ASSET_CONFIG, 
        MAIN_EXCHANGE, 
        AUX_EXCHANGES
    )
    
    if opportunities:
        best = opportunities[0]
        trade_amount = 1000.0  # Фиксированная сумма на сделку
        
        result = execute_arbitrage(st.session_state.exchanges, best, trade_amount)
        if result['success']:
            profit = round(trade_amount * (best['net_spread'] / 100), 2)
            st.session_state.total_profit += profit
            st.session_state.today_profit += profit
            st.session_state.trade_count += 1
            
            # Уменьшаем резерв USDT на вспомогательной бирже
            st.session_state.usdt_reserves[best['aux_exchange']] = st.session_state.usdt_reserves.get(best['aux_exchange'], 10000) - trade_amount
            
            # Добавляем задачу на перевод
            st.session_state.pending_transfers.append({
                'asset': best['asset'],
                'amount': trade_amount / best['aux_price'],
                'from': best['aux_exchange'],
                'to': MAIN_EXCHANGE,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
            
            trade_text = f"✅ {datetime.now().strftime('%H:%M:%S')} | {best['asset']} | Арбитраж | +{profit} USDT | Куплен на {best['aux_exchange'].upper()} | Продан на {best['main_exchange'].upper()}"
            st.session_state.history.append(trade_text)
            
            send_telegram_message(f"🎯 АРБИТРАЖ! {best['asset']} | Прибыль: +{profit} USDT")
            save_user_data()
            st.toast(f"🎯 Арбитраж по {best['asset']}! +{profit} USDT", icon="💰")
            st.rerun()

st.caption("🚀 Накопительный арбитраж — токены растут в цене, а арбитраж приносит дополнительную прибыль")
