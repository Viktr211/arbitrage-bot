# arbitrage_bot_auto.py - Автоматический арбитражный бот
import streamlit as st
import time
import json
import ccxt
import pandas as pd
from datetime import datetime
import threading
from config import API_KEYS

st.set_page_config(page_title="Арбитражный бот (авто)", layout="wide", page_icon="🚀")

# ====================== НАСТРОЙКИ ======================
EXCHANGES = ["binance", "kucoin", "bybit", "okx", "gateio", "bitget", "bingx", "mexc", "hitbtc", "poloniex"]
TOKENS = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "LINK", "SUI", "HYPE"]

THRESHOLDS = {
    "min_profit_usdt": 0.5,      # минимальная прибыль для сделки (USDT)
    "trade_percent": 20,         # процент от USDT баланса на сделку
    "scan_interval": 5,          # секунд между сканированиями
}

# ====================== ИНИЦИАЛИЗАЦИЯ ======================
if 'bot_running' not in st.session_state:
    st.session_state.bot_running = False
if 'exchanges' not in st.session_state:
    st.session_state.exchanges = {}
if 'log' not in st.session_state:
    st.session_state.log = []
if 'stats' not in st.session_state:
    st.session_state.stats = {"total_profit": 0, "trades": 0}

def connect_exchanges():
    """Подключается ко всем биржам, у которых есть ключи"""
    connected = {}
    for ex_name in EXCHANGES:
        keys = API_KEYS.get(ex_name, {})
        api_key = keys.get("api_key", "")
        secret = keys.get("secret", "")
        if not api_key or not secret:
            continue
        try:
            ex_class = getattr(ccxt, ex_name)
            exchange = ex_class({
                'apiKey': api_key,
                'secret': secret,
                'enableRateLimit': True,
                'options': {'defaultType': 'spot'}
            })
            exchange.load_markets()
            connected[ex_name] = exchange
            st.session_state.log.append(f"✅ {ex_name} подключена")
        except Exception as e:
            st.session_state.log.append(f"❌ {ex_name}: {str(e)[:50]}")
    return connected

def get_balance(exchange, asset='USDT'):
    try:
        bal = exchange.fetch_balance()
        return bal[asset]['free'] if asset in bal else 0.0
    except:
        return 0.0

def get_ticker(exchange, symbol):
    try:
        ticker = exchange.fetch_ticker(symbol)
        return ticker['ask'], ticker['bid']
    except:
        return None, None

def find_opportunities():
    """Сканирует все пары бирж и находит лучшую возможность"""
    opportunities = []
    exchanges = st.session_state.exchanges
    if len(exchanges) < 2:
        return opportunities
    
    for buy_name, buy_ex in exchanges.items():
        for sell_name, sell_ex in exchanges.items():
            if buy_name == sell_name:
                continue
            usdt_balance = get_balance(buy_ex, 'USDT')
            if usdt_balance < 20:
                continue
            for token in TOKENS:
                symbol = f"{token}/USDT"
                ask, _ = get_ticker(buy_ex, symbol)
                _, bid = get_ticker(sell_ex, symbol)
                if not ask or not bid or bid <= ask:
                    continue
                spread_pct = (bid - ask) / ask * 100
                if spread_pct < 0.1:  # минимальный спред 0.1%
                    continue
                trade_usdt = usdt_balance * THRESHOLDS["trade_percent"] / 100
                if trade_usdt < 10:
                    trade_usdt = 10
                amount = trade_usdt / ask
                profit = (bid - ask) * amount
                # вычитаем комиссии (0.1% на покупку + 0.1% на продажу)
                fee_buy = ask * amount * 0.001
                fee_sell = bid * amount * 0.001
                net_profit = profit - fee_buy - fee_sell
                if net_profit > THRESHOLDS["min_profit_usdt"]:
                    opportunities.append({
                        'token': token,
                        'buy_ex': buy_name,
                        'sell_ex': sell_name,
                        'buy_price': ask,
                        'sell_price': bid,
                        'amount': amount,
                        'net_profit': net_profit
                    })
    opportunities.sort(key=lambda x: x['net_profit'], reverse=True)
    return opportunities

def execute_trade(opp):
    """Исполняет сделку"""
    buy_ex = st.session_state.exchanges[opp['buy_ex']]
    sell_ex = st.session_state.exchanges[opp['sell_ex']]
    symbol = f"{opp['token']}/USDT"
    try:
        # Покупка
        buy_order = buy_ex.create_limit_buy_order(symbol, opp['amount'], opp['buy_price'])
        if not buy_order or buy_order['status'] not in ['open', 'closed']:
            raise Exception("Ошибка покупки")
        # Продажа
        sell_order = sell_ex.create_limit_sell_order(symbol, opp['amount'], opp['sell_price'])
        if not sell_order or sell_order['status'] not in ['open', 'closed']:
            buy_ex.create_sell_order(symbol, opp['amount'], opp['buy_price'])
            raise Exception("Ошибка продажи")
        # Обновляем статистику
        st.session_state.stats['total_profit'] += opp['net_profit']
        st.session_state.stats['trades'] += 1
        log_msg = f"✅ {opp['token']}: {opp['buy_ex']}→{opp['sell_ex']} | Прибыль: {opp['net_profit']:.2f} USDT"
        st.session_state.log.append(f"[{datetime.now().strftime('%H:%M:%S')}] {log_msg}")
        return True
    except Exception as e:
        st.session_state.log.append(f"❌ Ошибка {opp['token']}: {e}")
        return False

def bot_loop():
    """Основной цикл бота (работает в фоне)"""
    log_msg = f"✅ Бот запущен. Сканирование каждые {THRESHOLDS['scan_interval']} сек."
    st.session_state.log.append(f"[{datetime.now().strftime('%H:%M:%S')}] {log_msg}")
    while st.session_state.bot_running:
        try:
            opportunities = find_opportunities()
            if opportunities:
                best = opportunities[0]
                execute_trade(best)
            time.sleep(THRESHOLDS['scan_interval'])
        except Exception as e:
            st.session_state.log.append(f"⚠️ Ошибка цикла: {e}")
            time.sleep(5)

# ====================== ИНТЕРФЕЙС STREAMLIT ======================
def main():
    st.title("🚀 Автоматический арбитражный бот")
    
    # Статус и кнопки
    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        if st.session_state.bot_running:
            st.success("🟢 БОТ РАБОТАЕТ")
        else:
            st.warning("🔴 БОТ ОСТАНОВЛЕН")
    with col2:
        if st.button("▶ СТАРТ"):
            if not st.session_state.exchanges:
                with st.spinner("Подключение к биржам..."):
                    st.session_state.exchanges = connect_exchanges()
            if st.session_state.exchanges:
                st.session_state.bot_running = True
                threading.Thread(target=bot_loop, daemon=True).start()
                st.rerun()
            else:
                st.error("Нет подключённых бирж. Проверьте API-ключи в config.py")
    with col3:
        if st.button("⏹ СТОП"):
            st.session_state.bot_running = False
            st.rerun()
    
    # Статистика
    st.subheader("📊 Статистика")
    col_a, col_b = st.columns(2)
    with col_a:
        st.metric("💰 Общая прибыль", f"{st.session_state.stats['total_profit']:.2f} USDT")
    with col_b:
        st.metric("📈 Всего сделок", st.session_state.stats['trades'])
    
    # Подключённые биржи
    st.subheader("🔌 Подключённые биржи")
    if st.session_state.exchanges:
        st.write(", ".join([ex.upper() for ex in st.session_state.exchanges.keys()]))
    else:
        st.info("Нет подключённых бирж. Добавьте API-ключи в config.py")
    
    # Лог
    st.subheader("📜 Лог событий")
    log_text = "\n".join(st.session_state.log[-30:])
    st.text_area("", log_text, height=300, label_visibility="collapsed")
    
    if st.button("🗑 Очистить лог"):
        st.session_state.log = []
        st.rerun()

if __name__ == "__main__":
    main()
