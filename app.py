import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import sys
import os
import hashlib
import ccxt

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from utils import (
    supabase,
    get_user_by_email,
    get_user_settings,
    set_auto_trade_enabled,
    get_available_tokens,
    get_latest_balances,
    get_logs,
    get_user_trades,
    get_config,
    set_config,
    init_real_exchanges,
    get_price,
    EXCHANGES
)

st.set_page_config(page_title="Арбитражный бот HOVMEL", layout="wide", page_icon="🔄", initial_sidebar_state="collapsed")

# ------------------- CSS -------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&display=swap');
.main-header h1 {
    font-family: 'Orbitron', sans-serif;
    font-size: 2.8rem;
    background: linear-gradient(135deg, #FFD700 0%, #FFA500 40%, #FF8C00 100%);
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
    text-align: center;
}
.hovmel-highlight { background: linear-gradient(120deg, #FFD700, #FF8C00); -webkit-background-clip: text; background-clip: text; color: transparent; font-weight: 900; }
.subtitle { text-align: center; color: #aaa; margin-top: -0.8rem; margin-bottom: 1.5rem; }
.status-running { color: #00FF88; font-weight: bold; }
.status-stopped { color: #FF4444; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# ------------------- СЕССИЯ -------------------
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_id = None
    st.session_state.email = None
    st.session_state.username = None
    st.session_state.wallet = ''
    st.session_state.role = 'viewer'

# ------------------- ЛОГИН / РЕГИСТРАЦИЯ -------------------
def login():
    st.markdown('<div class="main-header"><h1>Арбитражный бот <span class="hovmel-highlight">HOVMEL</span></h1></div><div class="subtitle">⚡ Автоматический поиск межбиржевого арбитража 24/7 ⚡</div>', unsafe_allow_html=True)
    tab1, tab2 = st.tabs(["Вход", "Регистрация"])
    with tab1:
        email = st.text_input("Email")
        pwd = st.text_input("Пароль", type="password")
        if st.button("Войти"):
            user = get_user_by_email(email)
            if user:
                pwd_hash = hashlib.sha256(pwd.encode()).hexdigest()
                if user['password_hash'] == pwd_hash and user['registration_status'] == 'approved':
                    st.session_state.logged_in = True
                    st.session_state.user_id = user['id']
                    st.session_state.email = user['email']
                    st.session_state.username = user['full_name']
                    st.session_state.wallet = user.get('wallet_address', '')
                    st.session_state.role = user.get('role', 'viewer')
                    st.rerun()
                else:
                    st.error("Неверные данные или аккаунт не одобрен")
            else:
                st.error("Пользователь не найден")
    with tab2:
        st.info("Регистрация через админа (закройте и обратитесь к администратору)")

if not st.session_state.logged_in:
    login()
    st.stop()

# ------------------- ОСНОВНОЙ ИНТЕРФЕЙС -------------------
st.markdown('<div class="main-header"><h1>Арбитражный бот <span class="hovmel-highlight">HOVMEL</span></h1></div><div class="subtitle">⚡ Автоматический поиск межбиржевого арбитража 24/7 ⚡</div>', unsafe_allow_html=True)

col1, col2, col3, col4 = st.columns([2,1,1,1])
with col1:
    st.markdown(f"👤 {st.session_state.username} | 📧 {st.session_state.email}")
with col2:
    st.markdown('<span class="status-stopped">🔴 РЕАЛЬНЫЙ РЕЖИМ</span>', unsafe_allow_html=True)
with col3:
    settings = get_user_settings(st.session_state.user_id)
    if settings and settings.get('auto_trade_enabled'):
        st.markdown('<span class="status-running">▶ АВТО-СДЕЛКИ АКТИВНЫ</span>', unsafe_allow_html=True)
    else:
        st.markdown('<span class="status-stopped">⏹ АВТО-СДЕЛКИ ОСТАНОВЛЕНЫ</span>', unsafe_allow_html=True)
with col4:
    if st.button("🚪 Выйти"):
        st.session_state.logged_in = False
        st.rerun()

# ------------------- УПРАВЛЕНИЕ (только для админа) -------------------
if st.session_state.role == 'admin':
    col_start, col_stop = st.columns(2)
    with col_start:
        if st.button("▶ СТАРТ АВТО-ТОРГОВЛИ", width='stretch'):
            set_auto_trade_enabled(st.session_state.user_id, True)
            st.rerun()
    with col_stop:
        if st.button("⏹ СТОП АВТО-ТОРГОВЛИ", width='stretch'):
            set_auto_trade_enabled(st.session_state.user_id, False)
            st.rerun()
else:
    st.info("🔒 Вы в режиме просмотра. Управление ботом недоступно.")

# ------------------- КАПИТАЛ И БАЛАНСЫ -------------------
balances = get_latest_balances(st.session_state.user_id)
total_usdt = 0.0
total_portfolio = 0.0
balance_by_exchange = {}

if balances:
    df_balances = pd.DataFrame(balances)
    # Группируем по биржам и активам
    for ex in EXCHANGES:
        ex_data = df_balances[df_balances['exchange'] == ex]
        if not ex_data.empty:
            usdt = ex_data[ex_data['asset'] == 'USDT']['usdt_value'].sum()
            tokens = ex_data[ex_data['asset'] != 'USDT']
            portfolio = tokens['usdt_value'].sum() if not tokens.empty else 0
            balance_by_exchange[ex] = {'USDT': usdt, 'portfolio': portfolio}
            total_usdt += usdt
            total_portfolio += portfolio

total_capital = total_usdt + total_portfolio

# Показываем балансы
if balance_by_exchange:
    info_text = " | ".join([f"{ex.upper()}: USDT {data['USDT']:.2f} | Портфель {data['portfolio']:.2f}" for ex, data in balance_by_exchange.items()])
    st.info(f"💰 **Реальные балансы** | USDT: {total_usdt:.2f} | Портфель: {total_portfolio:.2f} | Капитал: {total_capital:.2f}")
else:
    st.info("💰 Реальные балансы будут отображаться после первого сканирования worker'ом")

col_a, col_b, col_c, col_d, col_e = st.columns(5)
col_a.metric("💰 USDT на биржах", f"{total_usdt:.2f}")
col_b.metric("📦 Портфель (токены)", f"{total_portfolio:.2f}")
col_c.metric("💎 Общий капитал", f"{total_capital:.2f}")

# Прибыль и сделки
trades = get_user_trades(st.session_state.user_id, 1000)
total_profit = sum(t.get('profit', 0) for t in trades) if trades else 0
col_d.metric("📈 Прибыль с запуска", f"{total_profit:.4f} USDT")
col_e.metric("📊 Сделок", len(trades))

# ------------------- НАСТРОЙКИ (только для админа) -------------------
if st.session_state.role == 'admin':
    with st.expander("⚙️ Настройки арбитража", expanded=False):
        settings = get_user_settings(st.session_state.user_id)
        if settings:
            fee = st.number_input("Комиссия (%)", 0.0, 0.5, settings.get('fee', 0.2), 0.01, format="%.2f")
            min_profit = st.number_input("Мин. прибыль (USDT)", 0.001, 1.0, settings.get('min_profit', 0.03), 0.01, format="%.3f")
            min_trade = st.number_input("Минимальная сумма сделки (USDT)", 1.0, 1000.0, settings.get('min_trade', 8.0), 5.0)
            max_trade = st.number_input("Максимальная сумма сделки (USDT)", 1.0, 1000.0, settings.get('max_trade', 20.0), 10.0)
            scan_interval = st.number_input("Интервал сканирования (сек)", 10, 120, settings.get('scan_interval', 30), 5)
            use_orderbook = st.checkbox("Учитывать стакан", value=settings.get('use_orderbook', True))
            max_slippage = st.number_input("Макс. проскальзывание (%)", 0.05, 1.0, settings.get('max_slippage', 0.3), 0.05, format="%.2f")
            if st.button("💾 Сохранить настройки"):
                new_settings = {
                    'fee': fee,
                    'min_profit': min_profit,
                    'min_trade': min_trade,
                    'max_trade': max_trade,
                    'scan_interval': scan_interval,
                    'use_orderbook': use_orderbook,
                    'max_slippage': max_slippage,
                    'orderbook_depth': 20,
                    'reinvest_percent': 0,
                    'auto_trade_enabled': settings.get('auto_trade_enabled', False)
                }
                from utils import update_user_settings
                update_user_settings(st.session_state.user_id, new_settings)
                st.success("Настройки сохранены!")
else:
    with st.expander("⚙️ Настройки (только для администратора)", expanded=False):
        st.info("🔒 Для изменения настроек обратитесь к администратору.")

# ------------------- ЛОГ -------------------
with st.expander("📋 Лог авто-торговли", expanded=False):
    logs = get_logs(st.session_state.user_id, 50)
    if logs:
        for log in logs[::-1]:
            st.text(f"{log['created_at'][:19]} {log['message']}")
    else:
        st.info("Нет событий. Запустите авто-торговлю кнопкой СТАРТ.")

# ------------------- ВКЛАДКИ -------------------
show_admin = st.session_state.role == 'admin'
tabs_list = ["📊 Dashboard", "📈 Графики", "🔄 Арбитраж", "📊 Статистика", "💼 Балансы", "💰 Вывод", "📜 История", "👤 Кабинет", "💬 Чат"]
if show_admin:
    tabs_list.append("👑 Админ-панель")
tabs = st.tabs(tabs_list)

# ----- Dashboard -----
with tabs[0]:
    st.subheader("📊 Dashboard")
    st.write("Добро пожаловать в арбитражного бота **HOVMEL**.")
    st.write(f"Активные токены: {', '.join(get_available_tokens())}")
    st.write(f"Текущие настройки суммы сделки: от **{min_trade:.0f}** до **{max_trade:.0f}** USDT (общий лимит).")
    st.write(f"**Минимальная прибыль:** {min_profit:.2f} USDT.")
    st.success("✅ Реальный режим активен.")
    st.markdown("---")
    st.markdown("### 💹 Текущие цены токенов")
    # Показываем цены и спреды
    exchanges = init_real_exchanges()
    tokens = get_available_tokens()
    prices_data = {}
    for ex in EXCHANGES:
        if exchanges.get(ex):
            prices_data[ex] = {}
            for token in tokens:
                price = get_price(exchanges[ex], token)
                if price:
                    prices_data[ex][token] = price
    
    if prices_data:
        rows = []
        for token in tokens:
            row = {"Токен": token}
            for ex in EXCHANGES:
                if ex in prices_data and token in prices_data[ex]:
                    row[ex.upper()] = f"{prices_data[ex][token]:.8f}"
                else:
                    row[ex.upper()] = "—"
            if row.get("KUCOIN", "—") != "—" and row.get("OKX", "—") != "—":
                try:
                    diff = abs(float(row["KUCOIN"]) - float(row["OKX"])) / float(row["KUCOIN"]) * 100
                    row["Спред %"] = f"{diff:.2f}%"
                    row["Арбитраж"] = "✅" if diff > 0.15 else "❌"
                except:
                    row["Спред %"] = "—"
                    row["Арбитраж"] = "?"
            else:
                row["Спред %"] = "—"
                row["Арбитраж"] = "?"
            rows.append(row)
        df_prices = pd.DataFrame(rows)
        st.dataframe(df_prices, width='stretch', hide_index=True)
    else:
        st.info("⏳ Данные о ценах будут доступны после первого сканирования")

# ----- Графики -----
with tabs[1]:
    st.subheader("📈 Графики (японские свечи)")
    tokens = get_available_tokens()
    tok = st.selectbox("Выберите токен", tokens)
    timeframe = st.selectbox("Таймфрейм", ["1m", "5m", "15m", "1h", "4h", "1d"], index=3)
    exchange_for_chart = st.selectbox("Биржа", EXCHANGES, index=0)
    
    if tok and exchange_for_chart:
        exchange = init_real_exchanges().get(exchange_for_chart)
        if exchange:
            try:
                ohlcv = exchange.fetch_ohlcv(f"{tok}/USDT", timeframe=timeframe, limit=100)
                if ohlcv:
                    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                    fig = go.Figure(data=[go.Candlestick(
                        x=df['timestamp'],
                        open=df['open'],
                        high=df['high'],
                        low=df['low'],
                        close=df['close'],
                        name=f"{tok}/USDT"
                    )])
                    fig.update_layout(title=f"{tok}/USDT ({timeframe}) на {exchange_for_chart.upper()}", height=600)
                    st.plotly_chart(fig)
                else:
                    st.warning("Нет данных для отображения")
            except Exception as e:
                st.error(f"Ошибка получения данных: {str(e)}")
        else:
            st.error(f"Биржа {exchange_for_chart.upper()} не подключена")

# ----- Арбитраж (ручной) -----
with tabs[2]:
    st.subheader("🔄 Ручной поиск арбитража")
    st.info("Ручной поиск временно отключён в модульной версии. Worker сам находит сделки.")

# ----- Статистика -----
with tabs[3]:
    st.subheader("📊 Статистика")
    trades = get_user_trades(st.session_state.user_id, 1000)
    if trades:
        df = pd.DataFrame(trades)
        total_profit = df['profit'].sum()
        total_trades = len(df)
        col1, col2 = st.columns(2)
        col1.metric("📈 Общая прибыль", f"{total_profit:.4f} USDT")
        col2.metric("🔄 Количество сделок", total_trades)
        if total_trades > 0:
            avg = total_profit / total_trades
            st.metric("📊 Средняя прибыль на сделку", f"{avg:.4f} USDT")
        df_sorted = df.sort_values('trade_time')
        df_sorted['cumulative_profit'] = df_sorted['profit'].cumsum()
        fig = px.line(df_sorted, x='trade_time', y='cumulative_profit', title="Накопленная прибыль")
        st.plotly_chart(fig)
    else:
        st.info("Нет сделок для отображения")

# ----- Балансы -----
with tabs[4]:
    st.subheader("💼 Балансы и ручная торговля")
    balances = get_latest_balances(st.session_state.user_id)
    if balances:
        df_bal = pd.DataFrame(balances)
        for ex in EXCHANGES:
            with st.expander(f"{ex.upper()}"):
                ex_df = df_bal[df_bal['exchange'] == ex]
                if not ex_df.empty:
                    usdt = ex_df[ex_df['asset'] == 'USDT']['usdt_value'].sum()
                    st.write(f"**USDT:** {usdt:.2f}")
                    tokens = ex_df[ex_df['asset'] != 'USDT']
                    if not tokens.empty:
                        for _, row in tokens.iterrows():
                            st.write(f"{row['asset']}: {row['free']:.8f} ≈ {row['usdt_value']:.2f} USDT")
                else:
                    st.write("Нет данных")
    else:
        st.info("Балансы будут отображаться после получения данных от worker'а")

# ----- Вывод -----
with tabs[5]:
    st.subheader("💰 Вывод средств")
    st.info("Вывод средств временно отключён в модульной версии.")

# ----- История -----
with tabs[6]:
    st.subheader("📜 История сделок")
    trades = get_user_trades(st.session_state.user_id, 100)
    if trades:
        df = pd.DataFrame(trades)
        df_display = df[['trade_time', 'asset', 'amount', 'profit', 'buy_exchange', 'sell_exchange', 'mode']].copy()
        df_display['trade_time'] = pd.to_datetime(df_display['trade_time']).dt.strftime('%Y-%m-%d %H:%M')
        df_display['amount'] = df_display['amount'].apply(lambda x: f"{x:.8f}")
        df_display['profit'] = df_display['profit'].apply(lambda x: f"{x:.4f}")
        df_display.columns = ['Время', 'Актив', 'Количество', 'Прибыль (USDT)', 'Покупка', 'Продажа', 'Режим']
        st.dataframe(df_display, width='stretch')
    else:
        st.info("Нет сделок")

# ----- Кабинет -----
with tabs[7]:
    st.subheader("👤 Личный кабинет")
    st.write(f"**Имя:** {st.session_state.username}")
    st.write(f"**Email:** {st.session_state.email}")
    st.write(f"**Кошелёк:** {st.session_state.wallet}")

# ----- Чат -----
with tabs[8]:
    st.subheader("💬 Чат поддержки")
    st.info("Чат будет доступен после настройки.")

# ----- Админ-панель -----
if show_admin:
    with tabs[9]:
        st.subheader("👑 Административная панель")
        st.info("Здесь можно управлять пользователями, API-ключами и настройками.")
