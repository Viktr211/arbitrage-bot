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

st.set_page_config(page_title="Накопительный Арбитраж PRO", layout="wide", page_icon="🚀")

# ====================== СТИЛЬ ======================
st.markdown("""
<style>
    .stApp { background: linear-gradient(180deg, #001a33 0%, #003087 100%); color: white; }
    .main-header { font-size: 32px; font-weight: bold; color: #00D4FF; text-align: center; margin-bottom: 20px; }
    .stButton>button { border-radius: 30px; height: 48px; font-weight: bold; }
    .arbitrage-card { background: rgba(0,255,100,0.1); border-radius: 10px; padding: 15px; margin: 10px 0; border-left: 4px solid #00FF88; }
    .profit-positive { color: #00FF88; font-weight: bold; }
    .profit-negative { color: #FF4444; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# ====================== КОНФИГУРАЦИЯ ======================
DEFAULT_ASSETS = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "LINK", "SUI", "HYPE"]
MAIN_EXCHANGE = "okx"
AUX_EXCHANGES = ["gateio", "kucoin"]

MIN_SPREAD_PERCENT = 0.03
FEE_PERCENT = 0.15

# ====================== ФАЙЛЫ ДАННЫХ ======================
USER_DATA_FILE = "user_data_v4.json"
HISTORY_FILE = "history_v4.json"

def load_user_data():
    if os.path.exists(USER_DATA_FILE):
        try:
            with open(USER_DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_user_data():
    data = {
        'username': st.session_state.get('username'),
        'email': st.session_state.get('email'),
        'total_profit': st.session_state.get('total_profit', 0.0),
        'trade_count': st.session_state.get('trade_count', 0),
        'portfolio': st.session_state.get('portfolio', {}),
        'usdt_reserves': st.session_state.get('usdt_reserves', {}),
        'daily_profits': st.session_state.get('daily_profits', {}),
        'weekly_profits': st.session_state.get('weekly_profits', {}),
        'monthly_profits': st.session_state.get('monthly_profits', {}),
        'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    with open(USER_DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return []
    return []

def save_history():
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(st.session_state.history, f, ensure_ascii=False, indent=4)

# ====================== СЕССИЯ (СОХРАНЯЕТСЯ ПРИ ОБНОВЛЕНИИ) ======================
# Загружаем сохранённые данные
saved_user = load_user_data()
saved_history = load_history()

# Инициализация сессии с сохранёнными данными
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = saved_user.get('logged_in', False)
if 'username' not in st.session_state:
    st.session_state.username = saved_user.get('username', None)
if 'email' not in st.session_state:
    st.session_state.email = saved_user.get('email', None)
if 'total_profit' not in st.session_state:
    st.session_state.total_profit = saved_user.get('total_profit', 0.0)
if 'trade_count' not in st.session_state:
    st.session_state.trade_count = saved_user.get('trade_count', 0)
if 'today_profit' not in st.session_state:
    st.session_state.today_profit = saved_user.get('today_profit', 0.0)
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = saved_user.get('portfolio', {asset: 0.0 for asset in DEFAULT_ASSETS})
if 'usdt_reserves' not in st.session_state:
    st.session_state.usdt_reserves = saved_user.get('usdt_reserves', {ex: 10000 for ex in AUX_EXCHANGES})
if 'daily_profits' not in st.session_state:
    st.session_state.daily_profits = saved_user.get('daily_profits', {})
if 'weekly_profits' not in st.session_state:
    st.session_state.weekly_profits = saved_user.get('weekly_profits', {})
if 'monthly_profits' not in st.session_state:
    st.session_state.monthly_profits = saved_user.get('monthly_profits', {})
if 'history' not in st.session_state:
    st.session_state.history = saved_history
if 'exchanges' not in st.session_state:
    st.session_state.exchanges = None
if 'bot_running' not in st.session_state:
    st.session_state.bot_running = False
if 'trade_mode' not in st.session_state:
    st.session_state.trade_mode = "Демо"
if 'last_update' not in st.session_state:
    st.session_state.last_update = datetime.now()

# Обновляем дневную статистику
today_str = datetime.now().strftime('%Y-%m-%d')
week_str = datetime.now().strftime('%Y-%W')
month_str = datetime.now().strftime('%Y-%m')

# ====================== ПОДКЛЮЧЕНИЕ К БИРЖАМ ======================
@st.cache_resource
def init_exchanges():
    exchanges = {}
    for ex_name in [MAIN_EXCHANGE] + AUX_EXCHANGES:
        try:
            exchange = getattr(ccxt, ex_name)({'enableRateLimit': True})
            exchange.fetch_ticker('BTC/USDT')
            exchanges[ex_name] = exchange
        except Exception as e:
            pass
    return exchanges

# ====================== ФУНКЦИИ ======================
def get_price(exchange, symbol):
    try:
        ticker = exchange.fetch_ticker(f"{symbol}/USDT")
        return ticker['last']
    except:
        return None

def find_all_arbitrage_opportunities():
    opportunities = []
    for asset in DEFAULT_ASSETS:
        prices = {}
        for ex_name in [MAIN_EXCHANGE] + AUX_EXCHANGES:
            if st.session_state.exchanges and ex_name in st.session_state.exchanges:
                price = get_price(st.session_state.exchanges[ex_name], asset)
                if price:
                    prices[ex_name] = price
        if len(prices) >= 2 and MAIN_EXCHANGE in prices:
            main_price = prices[MAIN_EXCHANGE]
            for aux_ex in AUX_EXCHANGES:
                if aux_ex in prices:
                    aux_price = prices[aux_ex]
                    if main_price > aux_price:
                        spread_pct = (main_price - aux_price) / aux_price * 100
                        net_spread = spread_pct - FEE_PERCENT
                        profit_usdt = round((main_price - aux_price) - (main_price * 0.001) - (aux_price * 0.001), 2)
                        if net_spread > MIN_SPREAD_PERCENT and profit_usdt >= 0.30:
                            opportunities.append({
                                'asset': asset,
                                'main_exchange': MAIN_EXCHANGE,
                                'aux_exchange': aux_ex,
                                'main_price': main_price,
                                'aux_price': aux_price,
                                'spread_pct': round(spread_pct, 2),
                                'net_spread': round(net_spread, 2),
                                'profit_usdt': profit_usdt
                            })
    return sorted(opportunities, key=lambda x: x['profit_usdt'], reverse=True)

def update_profit_stats(profit):
    """Обновляет статистику прибыли по дням, неделям, месяцам"""
    today = datetime.now().strftime('%Y-%m-%d')
    week = datetime.now().strftime('%Y-%W')
    month = datetime.now().strftime('%Y-%m')
    
    st.session_state.daily_profits[today] = st.session_state.daily_profits.get(today, 0) + profit
    st.session_state.weekly_profits[week] = st.session_state.weekly_profits.get(week, 0) + profit
    st.session_state.monthly_profits[month] = st.session_state.monthly_profits.get(month, 0) + profit
    st.session_state.today_profit = st.session_state.daily_profits.get(today, 0)

# ====================== РЕГИСТРАЦИЯ / ВХОД ======================
if not st.session_state.logged_in:
    st.markdown('<h1 class="main-header">🚀 НАКОПИТЕЛЬНЫЙ АРБИТРАЖ PRO</h1>', unsafe_allow_html=True)
    
    tab_reg, tab_login = st.tabs(["📝 Регистрация", "🔑 Вход"])
    
    with tab_reg:
        with st.form("register_form"):
            username = st.text_input("Имя пользователя")
            email = st.text_input("Email")
            password = st.text_input("Пароль", type="password")
            confirm = st.text_input("Подтвердите пароль", type="password")
            submitted = st.form_submit_button("Зарегистрироваться")
            
            if submitted:
                if username and email and password and password == confirm:
                    st.session_state.logged_in = True
                    st.session_state.username = username
                    st.session_state.email = email
                    st.session_state.portfolio = {asset: 0.0 for asset in DEFAULT_ASSETS}
                    st.session_state.usdt_reserves = {ex: 10000 for ex in AUX_EXCHANGES}
                    save_user_data()
                    st.success("Регистрация успешна!")
                    st.rerun()
                else:
                    st.error("Заполните все поля или пароли не совпадают")
    
    with tab_login:
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Пароль", type="password")
            submitted = st.form_submit_button("Войти")
            
            if submitted:
                saved = load_user_data()
                if saved.get('email') == email:
                    st.session_state.logged_in = True
                    st.session_state.username = saved.get('username', email.split('@')[0])
                    st.session_state.email = email
                    st.success(f"Добро пожаловать, {st.session_state.username}!")
                    st.rerun()
                else:
                    st.error("Неверный email или пароль")
    
    st.stop()

# ====================== ОСНОВНОЙ ИНТЕРФЕЙС ======================
st.markdown('<h1 class="main-header">🚀 НАКОПИТЕЛЬНЫЙ АРБИТРАЖ PRO</h1>', unsafe_allow_html=True)
st.write(f"👤 **{st.session_state.username}** | 📧 {st.session_state.email}")

# Инициализация бирж
if st.session_state.exchanges is None:
    with st.spinner("Подключение к биржам..."):
        st.session_state.exchanges = init_exchanges()

# Кнопка выхода
if st.button("🚪 Выйти", key="logout"):
    st.session_state.logged_in = False
    st.session_state.username = None
    st.session_state.email = None
    st.rerun()

# ====================== СТАТИСТИКА ======================
today_profit = st.session_state.daily_profits.get(datetime.now().strftime('%Y-%m-%d'), 0)
week_profit = st.session_state.weekly_profits.get(datetime.now().strftime('%Y-%W'), 0)
month_profit = st.session_state.monthly_profits.get(datetime.now().strftime('%Y-%m'), 0)

col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    st.metric("💰 Общая прибыль", f"{st.session_state.total_profit:.2f} USDT")
with col2:
    st.metric("📅 Сегодня", f"{today_profit:.2f} USDT", delta=f"{today_profit - st.session_state.daily_profits.get((datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d'), 0):+.2f}")
with col3:
    st.metric("📆 Эта неделя", f"{week_profit:.2f} USDT")
with col4:
    st.metric("📅 Этот месяц", f"{month_profit:.2f} USDT")
with col5:
    st.metric("📊 Сделок", st.session_state.trade_count)

# ====================== КНОПКИ УПРАВЛЕНИЯ ======================
c1, c2, c3, c4 = st.columns(4)
with c1:
    if st.button("▶ ЗАПУСТИТЬ", type="primary", use_container_width=True):
        st.session_state.bot_running = True
        st.rerun()
with c2:
    if st.button("⏸ ПАУЗА", use_container_width=True):
        st.session_state.bot_running = False
        st.rerun()
with c3:
    if st.button("⏹ СТОП", use_container_width=True):
        st.session_state.bot_running = False
        st.rerun()
with c4:
    mode = st.selectbox("Режим", ["Демо", "Реальный"], index=0)
    st.session_state.trade_mode = mode

# ====================== ВКЛАДКИ ======================
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["📊 Арбитраж", "📈 Графики", "📦 Портфель", "💰 Кошелёк", "📊 Статистика", "📜 История"])

# ====================== TAB 1: АРБИТРАЖ ======================
with tab1:
    st.subheader("🔍 Поиск арбитражных возможностей")
    
    if st.button("🔄 Обновить цены", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    
    opportunities = find_all_arbitrage_opportunities()
    
    if opportunities:
        for opp in opportunities[:5]:
            st.markdown(f"""
            <div class="arbitrage-card">
                🎯 <b>{opp['asset']}/USDT</b><br>
                📈 Продать на <b>{opp['main_exchange'].upper()}</b>: ${opp['main_price']:,.2f}<br>
                📉 Купить на <b>{opp['aux_exchange'].upper()}</b>: ${opp['aux_price']:,.2f}<br>
                💰 Прибыль: <b class="profit-positive">+{opp['profit_usdt']:.2f} USDT</b>
            </div>
            """, unsafe_allow_html=True)
            
            if st.button(f"🚀 Исполнить {opp['asset']}", key=f"exec_{opp['asset']}"):
                if st.session_state.trade_mode == "Демо":
                    profit = opp['profit_usdt']
                    st.session_state.total_profit += profit
                    st.session_state.trade_count += 1
                    update_profit_stats(profit)
                    
                    trade_text = f"✅ {datetime.now().strftime('%H:%M:%S')} | {opp['asset']} | АРБИТРАЖ | +{profit:.2f} USDT"
                    st.session_state.history.append(trade_text)
                    save_user_data()
                    save_history()
                    st.success(f"✅ Сделка исполнена! +{profit:.2f} USDT")
                    st.rerun()
    else:
        st.info("📊 Арбитражных возможностей не найдено")

# ====================== TAB 2: ГРАФИКИ ======================
with tab2:
    st.subheader("📈 Графики доходности")
    
    # График дневной прибыли
    if st.session_state.daily_profits:
        df_daily = pd.DataFrame(list(st.session_state.daily_profits.items()), columns=['Дата', 'Прибыль'])
        df_daily = df_daily.sort_values('Дата').tail(30)
        fig_daily = px.bar(df_daily, x='Дата', y='Прибыль', title="Дневная прибыль", color_discrete_sequence=['#00FF88'])
        fig_daily.update_layout(template="plotly_dark", height=400)
        st.plotly_chart(fig_daily, use_container_width=True)
    
    # График недельной прибыли
    if st.session_state.weekly_profits:
        df_weekly = pd.DataFrame(list(st.session_state.weekly_profits.items()), columns=['Неделя', 'Прибыль'])
        df_weekly = df_weekly.sort_values('Неделя')
        fig_weekly = px.bar(df_weekly, x='Неделя', y='Прибыль', title="Недельная прибыль", color_discrete_sequence=['#FF6B6B'])
        fig_weekly.update_layout(template="plotly_dark", height=400)
        st.plotly_chart(fig_weekly, use_container_width=True)
    
    # Накопленная прибыль
    if st.session_state.history:
        cumulative = []
        total = 0
        for trade in st.session_state.history:
            if "+" in trade:
                try:
                    profit = float(trade.split("+")[1].split()[0])
                    total += profit
                    cumulative.append(total)
                except:
                    pass
        if cumulative:
            fig_cum = px.line(y=cumulative, title="Накопленная прибыль", color_discrete_sequence=['#00D4FF'])
            fig_cum.update_layout(template="plotly_dark", height=400)
            st.plotly_chart(fig_cum, use_container_width=True)

# ====================== TAB 3: ПОРТФЕЛЬ ======================
with tab3:
    st.subheader("📦 Портфель токенов (главная биржа)")
    
    total_value = 0
    for asset in DEFAULT_ASSETS:
        amount = st.session_state.portfolio.get(asset, 0)
        if st.session_state.exchanges and MAIN_EXCHANGE in st.session_state.exchanges:
            price = get_price(st.session_state.exchanges[MAIN_EXCHANGE], asset)
            value = amount * price if price else 0
            total_value += value
            col1, col2, col3 = st.columns(3)
            col1.write(f"**{asset}**")
            col2.write(f"{amount:.6f}")
            col3.write(f"${value:,.2f}" if price else "—")
    
    st.divider()
    st.metric("💰 Общая стоимость портфеля", f"${total_value:,.2f}")

# ====================== TAB 4: КОШЕЛЁК ======================
with tab4:
    st.subheader("💰 Резервы USDT")
    for ex in AUX_EXCHANGES:
        reserve = st.session_state.usdt_reserves.get(ex, 0)
        st.write(f"**{ex.upper()}**: {reserve:.2f} USDT")
    
    st.divider()
    col_in, col_out = st.columns(2)
    with col_in:
        deposit = st.number_input("Сумма ввода (USDT)", min_value=10.0, step=10.0)
        if st.button("💰 Внести"):
            st.session_state.usdt_reserves[AUX_EXCHANGES[0]] += deposit
            save_user_data()
            st.success(f"Внесено {deposit} USDT")
            st.rerun()
    with col_out:
        withdraw = st.number_input("Сумма вывода (USDT)", min_value=10.0, max_value=float(st.session_state.usdt_reserves.get(AUX_EXCHANGES[0], 0)), step=10.0)
        if st.button("📤 Вывести"):
            st.session_state.usdt_reserves[AUX_EXCHANGES[0]] -= withdraw
            save_user_data()
            st.success(f"Выведено {withdraw} USDT")
            st.rerun()

# ====================== TAB 5: СТАТИСТИКА ======================
with tab5:
    st.subheader("📊 Детальная статистика")
    
    st.write("### 📅 Прибыль по дням")
    if st.session_state.daily_profits:
        df = pd.DataFrame(list(st.session_state.daily_profits.items()), columns=['Дата', 'Прибыль (USDT)'])
        st.dataframe(df.sort_values('Дата', ascending=False), use_container_width=True, hide_index=True)
    
    st.write("### 📆 Прибыль по неделям")
    if st.session_state.weekly_profits:
        df = pd.DataFrame(list(st.session_state.weekly_profits.items()), columns=['Неделя', 'Прибыль (USDT)'])
        st.dataframe(df.sort_values('Неделя', ascending=False), use_container_width=True, hide_index=True)
    
    st.write("### 📅 Прибыль по месяцам")
    if st.session_state.monthly_profits:
        df = pd.DataFrame(list(st.session_state.monthly_profits.items()), columns=['Месяц', 'Прибыль (USDT)'])
        st.dataframe(df.sort_values('Месяц', ascending=False), use_container_width=True, hide_index=True)

# ====================== TAB 6: ИСТОРИЯ ======================
with tab6:
    st.subheader("📜 История сделок")
    
    if st.session_state.history:
        for trade in reversed(st.session_state.history[-50:]):
            if "+" in trade:
                if "0.00" in trade:
                    st.write(trade)
                else:
                    st.success(trade)
            else:
                st.write(trade)
        
        if st.button("🗑 Очистить историю"):
            st.session_state.history = []
            save_history()
            st.rerun()
    else:
        st.info("Нет сделок")

# ====================== АВТОМАТИЧЕСКИЙ АРБИТРАЖ ======================
if st.session_state.bot_running and st.session_state.exchanges:
    time.sleep(5)
    
    opportunities = find_all_arbitrage_opportunities()
    profitable = [opp for opp in opportunities if opp['profit_usdt'] >= 0.50]
    
    if profitable:
        best = profitable[0]
        
        if st.session_state.trade_mode == "Демо":
            profit = best['profit_usdt']
            st.session_state.total_profit += profit
            st.session_state.trade_count += 1
            update_profit_stats(profit)
            
            trade_text = f"✅ {datetime.now().strftime('%H:%M:%S')} | {best['asset']} | АВТО-АРБИТРАЖ | +{profit:.2f} USDT"
            st.session_state.history.append(trade_text)
            save_user_data()
            save_history()
            st.toast(f"🎯 Авто-арбитраж по {best['asset']}! +{profit:.2f} USDT", icon="💰")
            st.rerun()
    else:
        time.sleep(10)

st.caption("🚀 Накопительный арбитраж — данные сохраняются при обновлении страницы")
