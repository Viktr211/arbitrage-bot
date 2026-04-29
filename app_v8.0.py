import streamlit as st
import time
import random
import ccxt
from datetime import datetime

st.set_page_config(page_title="Накопительный Арбитраж PRO", layout="wide", page_icon="🚀")

# ====================== СТИЛЬ ======================
st.markdown("""
<style>
    .stApp { background: linear-gradient(180deg, #001a33 0%, #003087 100%) !important; color: white !important; }
    .main-header { font-size: 28px; font-weight: bold; color: #00D4FF; text-align: center; margin-bottom: 0; }
    .status-indicator { display: inline-block; width: 14px; height: 14px; border-radius: 50%; margin-right: 6px; }
    .status-running { background-color: #00FF88; box-shadow: 0 0 8px #00FF88; animation: pulse 1.5s infinite; }
    .status-stopped { background-color: #FF4444; box-shadow: 0 0 8px #FF4444; }
    @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.4; } 100% { opacity: 1; } }
</style>
""", unsafe_allow_html=True)

st.markdown('<h1 class="main-header">🚀 НАКОПИТЕЛЬНЫЙ АРБИТРАЖ PRO v8.1</h1>', unsafe_allow_html=True)

# ====================== КОНФИГУРАЦИЯ ======================
DEFAULT_ASSETS = ["BTC", "ETH", "SOL", "SUI", "TON", "XRP", "ADA"]
MAIN_EXCHANGE = "okx"
AUX_EXCHANGE = "kucoin"
MIN_TRADE_AMOUNT = 12.0

# ====================== СЕССИЯ ======================
for key, default in {
    'logged_in': True,
    'is_admin': True,
    'username': "Оганнес",
    'email': "cb777899@gmail.com",
    'bot_running': False,
    'total_profit': 0.0,
    'trade_count': 0,
    'history': [],
    'okx_balance': 125.0,
    'kucoin_balance': 125.0,
    'portfolio_okx': {asset: round(random.uniform(0.5, 5), 4) for asset in DEFAULT_ASSETS},
    'portfolio_kucoin': {asset: round(random.uniform(0.5, 5), 4) for asset in DEFAULT_ASSETS},
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
    except Exception as e:
        st.error(f"Ошибка подключения бирж: {e}")
        return None

if st.session_state.exchanges is None:
    with st.spinner("Подключение OKX и KuCoin..."):
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

        if kucoin_price < okx_price:
            spread_pct = (okx_price - kucoin_price) / kucoin_price * 100
            profit = (okx_price - kucoin_price) * 0.78

            if spread_pct > 0.15 and profit >= MIN_TRADE_AMOUNT:
                return {
                    'asset': asset,
                    'buy_exchange': 'kucoin',
                    'sell_exchange': 'okx',
                    'buy_price': kucoin_price,
                    'sell_price': okx_price,
                    'profit_usdt': round(profit, 2),
                    'spread_pct': round(spread_pct, 2)
                }
    return None

# ====================== ГЛАВНЫЙ ИНТЕРФЕЙС ======================
st.write(f"👤 **{st.session_state.username}**")

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
col1.metric("💰 Торговый баланс", f"{st.session_state.trade_balance:.2f} USDT")
col2.metric("🏦 Доступно для вывода", f"{st.session_state.withdrawable_balance:.2f} USDT")
col3.metric("💰 Общая прибыль", f"{st.session_state.total_profit:.2f} USDT")

# ====================== ВКЛАДКИ ======================
tabs = st.tabs(["📊 Dashboard", "🔄 Арбитраж", "📦 Портфель", "💰 Кошелёк", "📜 История"])

with tabs[0]:
    st.subheader("📊 Dashboard")
    st.metric("📊 Всего сделок", st.session_state.trade_count)

with tabs[1]:
    st.subheader("🔄 Арбитраж OKX ↔ KuCoin")
    if st.button("🔄 Проверить спреды"):
        st.rerun()
    
    opportunity = find_arbitrage_opportunity()
    if opportunity:
        st.success(f"🎯 Найдена возможность! +{opportunity['profit_usdt']:.2f} USDT")
        st.info(f"{opportunity['asset']} | Купить на KuCoin | Продать на OKX")
    else:
        st.info("Пока нет выгодных спредов (сканирование каждые 2.5 сек)")

with tabs[2]:
    st.subheader("📦 Портфель")
    st.write("**OKX портфель**")
    for asset, amount in st.session_state.portfolio_okx.items():
        st.write(f"{asset}: {amount:.4f}")
    st.write("**KuCoin портфель**")
    for asset, amount in st.session_state.portfolio_kucoin.items():
        st.write(f"{asset}: {amount:.4f}")

with tabs[3]:
    st.subheader("💰 Кошелёк")
    st.metric("OKX баланс", f"{st.session_state.okx_balance:.2f} USDT")
    st.metric("KuCoin баланс", f"{st.session_state.kucoin_balance:.2f} USDT")

with tabs[4]:
    st.subheader("📜 История сделок")
    if st.session_state.history:
        for trade in reversed(st.session_state.history[-15:]):
            st.write(trade)
    else:
        st.info("Сделок пока нет")

# ====================== РАБОТА БОТА ======================
if st.session_state.bot_running:
    time.sleep(2.5)
    
    opportunity = find_arbitrage_opportunity()
    
    if opportunity:
        profit = opportunity['profit_usdt']
        asset = opportunity['asset']
        
        st.session_state.total_profit += profit
        st.session_state.trade_count += 1
        st.session_state.history.append(
            f"✅ {datetime.now().strftime('%H:%M:%S')} | {asset} | KuCoin → OKX | +{profit:.2f} USDT"
        )
        
        st.toast(f"🎯 {asset} | +{profit:.2f} USDT", icon="💰")
        st.rerun()

st.caption("Тестовая версия v8.1 | OKX + KuCoin")
