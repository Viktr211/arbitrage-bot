import streamlit as st
import time
import random
import ccxt
from datetime import datetime

st.set_page_config(page_title="Накопительный Арбитраж PRO - Тест", layout="wide", page_icon="🚀")

# ====================== СТИЛЬ ======================
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

st.markdown('<h1 class="main-header">🚀 НАКОПИТЕЛЬНЫЙ АРБИТРАЖ PRO - Тест v8.2</h1>', unsafe_allow_html=True)
st.caption("OKX + KuCoin | 500 USDT | Мин. сделка 12 USDT | Сканирование 2.5 сек")

# ====================== СЕССИЯ ======================
for key, default in {
    'bot_running': False,
    'total_profit': 0.0,
    'trade_count': 0,
    'history': [],
    'okx_balance': 125.0,
    'kucoin_balance': 125.0,
    'portfolio_okx': {asset: 2.0 for asset in ["BTC", "ETH", "SOL", "SUI", "TON"]},
    'portfolio_kucoin': {asset: 2.0 for asset in ["BTC", "ETH", "SOL", "SUI", "TON"]},
    'exchanges': None
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

# ====================== ПОДКЛЮЧЕНИЕ БИРЖ ======================
@st.cache_resource
def init_exchanges():
    try:
        okx = ccxt.okx({'enableRateLimit': True})
        kucoin = ccxt.kucoin({'enableRateLimit': True})
        return {'okx': okx, 'kucoin': kucoin}
    except:
        st.error("Ошибка подключения бирж")
        return None

if st.session_state.exchanges is None:
    st.session_state.exchanges = init_exchanges()

def get_price(exchange, symbol):
    try:
        return exchange.fetch_ticker(f"{symbol}/USDT")['last']
    except:
        return None

# ====================== АРБИТРАЖ ======================
def find_arbitrage_opportunity():
    assets = ["BTC", "ETH", "SOL", "SUI", "TON"]
    for asset in assets:
        okx_price = get_price(st.session_state.exchanges['okx'], asset)
        kucoin_price = get_price(st.session_state.exchanges['kucoin'], asset)
        
        if not okx_price or not kucoin_price:
            continue
            
        if kucoin_price < okx_price * 0.996:   # спред больше 0.4%
            spread = (okx_price - kucoin_price) / kucoin_price * 100
            profit = (okx_price - kucoin_price) * 0.8   # после комиссий
            
            if profit >= 12.0:
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

# ====================== ИНТЕРФЕЙС ======================
st.write(f"**OKX:** {st.session_state.okx_balance:.2f} USDT | **KuCoin:** {st.session_state.kucoin_balance:.2f} USDT")

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

# Главные метрики
col1, col2, col3 = st.columns(3)
col1.metric("💰 Общая прибыль", f"{st.session_state.total_profit:.2f} USDT")
col2.metric("📊 Сделок", st.session_state.trade_count)
col3.metric("Мин. сделка", "12 USDT")

# Арбитраж
st.subheader("🔄 Арбитраж OKX ↔ KuCoin")
if st.button("🔄 Проверить спреды сейчас"):
    st.rerun()

opportunity = find_arbitrage_opportunity()
if opportunity:
    st.success(f"🎯 Найдена возможность! +{opportunity['profit_usdt']:.2f} USDT")
    st.info(f"{opportunity['asset']} | Купить на {opportunity['buy_exchange'].upper()} по ${opportunity['buy_price']:.2f} | Продать на {opportunity['sell_exchange'].upper()} по ${opportunity['sell_price']:.2f}")
else:
    st.info("Пока нет выгодных спредов (проверка каждые 2.5 сек)")

# История
st.subheader("📜 Последние сделки")
if st.session_state.history:
    for trade in reversed(st.session_state.history[-10:]):
        st.write(trade)
else:
    st.info("Сделок пока нет")

# ====================== РАБОТА БОТА ======================
if st.session_state.bot_running:
    time.sleep(2.5)   # сканирование каждые 2.5 секунды
    
    opportunity = find_arbitrage_opportunity()
    
    if opportunity:
        profit = opportunity['profit_usdt']
        asset = opportunity['asset']
        
        st.session_state.total_profit += profit
        st.session_state.trade_count += 1
        st.session_state.history.append(
            f"✅ {datetime.now().strftime('%H:%M:%S')} | {asset} | {opportunity['buy_exchange'].upper()} → {opportunity['sell_exchange'].upper()} | +{profit:.2f} USDT"
        )
        
        st.toast(f"🎯 Сделка по {asset} | +{profit:.2f} USDT", icon="💰")
        st.rerun()

st.caption("Тестовая версия v8.2 | OKX + KuCoin | Мин. сделка 12 USDT")
