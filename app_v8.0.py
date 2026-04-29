import streamlit as st
import time
import random
import ccxt
from datetime import datetime

st.set_page_config(page_title="Накопительный Арбитраж PRO - Тест", layout="wide", page_icon="🚀")

st.markdown("""
<style>
    .stApp { background: linear-gradient(180deg, #001a33 0%, #003087 100%) !important; color: white !important; }
    .main-header { font-size: 30px; font-weight: bold; color: #00D4FF; text-align: center; margin-bottom: 10px; }
    .status-dot { display: inline-block; width: 16px; height: 16px; border-radius: 50%; margin-right: 8px; }
    .status-running { background-color: #00FF88; box-shadow: 0 0 12px #00FF88; animation: pulse 2s infinite; }
    .status-stopped { background-color: #FF4444; }
    @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.4; } 100% { opacity: 1; } }
</style>
""", unsafe_allow_html=True)

st.markdown('<h1 class="main-header">🚀 НАКОПИТЕЛЬНЫЙ АРБИТРАЖ PRO - Тест v8.1</h1>', unsafe_allow_html=True)
st.caption("OKX + KuCoin | 500 USDT | Мин. сделка 12 USDT | Сканирование 2.5 сек")

# ====================== КОНФИГУРАЦИЯ ======================
DEFAULT_ASSETS = ["BTC", "ETH", "SOL", "BNB", "XRP", "SUI", "TON", "HYPE"]
MIN_TRADE_AMOUNT = 12.0   # минимальная сумма сделки в USDT

# ====================== СЕССИЯ ======================
for key, default in {
    'logged_in': True,           # для теста сразу считаем авторизованным
    'bot_running': False,
    'total_profit': 0.0,
    'trade_count': 0,
    'history': [],
    'okx_balance': 125.0,        # USDT на OKX
    'kucoin_balance': 125.0,     # USDT на KuCoin
    'portfolio_okx': {asset: 2.0 for asset in DEFAULT_ASSETS},
    'portfolio_kucoin': {asset: 2.0 for asset in DEFAULT_ASSETS},
    'exchanges': None
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

# ====================== ПОДКЛЮЧЕНИЕ БИРЖ ======================
@st.cache_resource
def init_exchanges():
    exchanges = {}
    try:
        exchanges['okx'] = ccxt.okx({'enableRateLimit': True})
        exchanges['kucoin'] = ccxt.kucoin({'enableRateLimit': True})
        # Для теста можно включить sandbox, если нужно
        # exchanges['kucoin'].set_sandbox_mode(True)
    except:
        st.error("Ошибка подключения бирж")
    return exchanges

if st.session_state.exchanges is None:
    st.session_state.exchanges = init_exchanges()

def get_price(exchange, symbol):
    try:
        return exchange.fetch_ticker(f"{symbol}/USDT")['last']
    except:
        return None

# ====================== АРБИТРАЖ ======================
def find_arbitrage_opportunity():
    for asset in DEFAULT_ASSETS:
        okx_price = get_price(st.session_state.exchanges['okx'], asset)
        kucoin_price = get_price(st.session_state.exchanges['kucoin'], asset)
        
        if not okx_price or not kucoin_price:
            continue
            
        # Покупаем на дешёвой, продаём на дорогой
        if kucoin_price < okx_price:
            spread = (okx_price - kucoin_price) / kucoin_price * 100
            profit = (okx_price - kucoin_price) * 0.8   # после приблизительных комиссий
            
            if spread > 0.35 and profit > MIN_TRADE_AMOUNT:
                return {
                    'asset': asset,
                    'buy_exchange': 'kucoin',
                    'sell_exchange': 'okx',
                    'buy_price': kucoin_price,
                    'sell_price': okx_price,
                    'profit_usdt': round(profit, 2),
                    'spread': round(spread, 2)
                }
    return None

# ====================== ГЛАВНЫЙ ИНТЕРФЕЙС ======================
st.write(f"**OKX баланс:** {st.session_state.okx_balance:.2f} USDT | **KuCoin баланс:** {st.session_state.kucoin_balance:.2f} USDT")

# Статус
status_color = "status-running" if st.session_state.bot_running else "status-stopped"
status_text = "● РАБОТАЕТ 24/7" if st.session_state.bot_running else "● ОСТАНОВЛЕН"
st.markdown(f'<div style="text-align:center; font-size:18px;"><span class="status-dot {status_color}"></span><b>{status_text}</b></div>', unsafe_allow_html=True)

c1, c2, c3 = st.columns(3)
if c1.button("▶ СТАРТ", type="primary", use_container_width=True):
    st.session_state.bot_running = True
if c2.button("⏸ ПАУЗА", use_container_width=True):
    st.session_state.bot_running = False
if c3.button("⏹ СТОП", use_container_width=True):
    st.session_state.bot_running = False

# ====================== РАБОТА БОТА ======================
if st.session_state.bot_running:
    time.sleep(2.5)   # сканирование каждые 2.5 секунды
    
    opportunity = find_arbitrage_opportunity()
    
    if opportunity:
        profit = opportunity['profit_usdt']
        asset = opportunity['asset']
        
        # Симулируем исполнение
        st.session_state.total_profit += profit
        st.session_state.trade_count += 1
        st.session_state.history.append(
            f"✅ {datetime.now().strftime('%H:%M:%S')} | {asset} | Куплено на {opportunity['buy_exchange'].upper()} | "
            f"Продано на {opportunity['sell_exchange'].upper()} | +{profit:.2f} USDT"
        )
        
        st.toast(f"🎯 {asset} | +{profit:.2f} USDT", icon="💰")
        st.rerun()

# ====================== ИНФОРМАЦИЯ ======================
st.subheader("📊 Текущие результаты теста")
st.metric("💰 Общая прибыль", f"{st.session_state.total_profit:.2f} USDT")
st.metric("📊 Количество сделок", st.session_state.trade_count)

if st.session_state.history:
    st.subheader("📜 Последние сделки")
    for trade in reversed(st.session_state.history[-15:]):
        st.write(trade)

st.caption("Тестовая версия v8.1 | OKX + KuCoin | Мин. сделка 12 USDT | Сканирование 2.5 сек")
