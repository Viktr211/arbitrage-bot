import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import sys
import os
import hashlib
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from utils import (
    supabase,
    get_user_by_email,
    get_user_settings,
    set_auto_trade_enabled,
    get_available_tokens,
    get_config,
    set_config,
    get_latest_balances,
    get_logs,
    get_user_trades,
    get_price,
    get_real_balance,
    init_real_exchanges,
    get_trade_mode,
    set_trade_mode,
    get_demo_data,
    reset_demo_data,
    update_demo_balance,
    get_all_users,
    update_user_status,
    update_user_role,
    get_all_api_keys,
    save_api_key,
    EXCHANGES,
    TOKENS
)

st.set_page_config(page_title="Арбитражный бот HOVMEL", layout="wide", page_icon="🔄", initial_sidebar_state="collapsed")

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
    st.session_state.real_exchanges = None

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
                    st.session_state.real_exchanges = init_real_exchanges() if st.session_state.role == 'admin' else None
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
    mode = get_trade_mode(st.session_state.user_id)
    if mode == 'демо':
        st.markdown('<span class="status-running">🟢 ДЕМО РЕЖИМ</span>', unsafe_allow_html=True)
    else:
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
    col_start, col_stop, col_mode = st.columns(3)
    with col_start:
        if st.button("▶ СТАРТ АВТО-ТОРГОВЛИ", width='stretch'):
            set_auto_trade_enabled(st.session_state.user_id, True)
            st.rerun()
    with col_stop:
        if st.button("⏹ СТОП АВТО-ТОРГОВЛИ", width='stretch'):
            set_auto_trade_enabled(st.session_state.user_id, False)
            st.rerun()
    with col_mode:
        new_mode = st.radio("Режим", ["демо", "реальный"], horizontal=True, index=0 if get_trade_mode(st.session_state.user_id) == 'демо' else 1)
        if new_mode != get_trade_mode(st.session_state.user_id):
            set_trade_mode(st.session_state.user_id, new_mode)
            st.rerun()
else:
    st.info("🔒 Вы в режиме просмотра. Управление ботом недоступно.")

# Подключенные биржи
public_clients = {}
for ex in EXCHANGES:
    try:
        import ccxt
        public_clients[ex] = getattr(ccxt, ex)({'enableRateLimit': True, 'options': {'defaultType': 'spot'}})
        public_clients[ex].fetch_ticker("BTC/USDT")
    except:
        public_clients[ex] = None
connected = [ex.upper() for ex, cl in public_clients.items() if cl is not None]
st.success(f"🔌 Биржи для мониторинга: {', '.join(connected)}")

# ------------------- РАСЧЁТ КАПИТАЛА -------------------
mode = get_trade_mode(st.session_state.user_id)
total_usdt = 0.0
total_portfolio = 0.0

if mode == 'демо':
    demo_data = get_demo_data(st.session_state.user_id)
    if demo_data:
        for ex in EXCHANGES:
            total_usdt += demo_data['balances'].get(ex, {}).get('USDT', 0.0)
            for token, amt in demo_data['balances'].get(ex, {}).get('portfolio', {}).items():
                if amt > 0:
                    price = public_clients.get(ex).fetch_ticker(f"{token}/USDT")['last'] if public_clients.get(ex) else 0
                    total_portfolio += amt * price
    total_capital = total_usdt + total_portfolio
    st.info(f"🎮 **Демо-балансы** | USDT: {total_usdt:.2f} | Портфель: {total_portfolio:.2f} | Капитал: {total_capital:.2f}")
else:
    # Реальные балансы из БД или напрямую
    if st.session_state.role == 'admin' and st.session_state.real_exchanges:
        for ex in EXCHANGES:
            exch = st.session_state.real_exchanges.get(ex)
            if exch:
                usdt = get_real_balance(exch, 'USDT')
                total_usdt += usdt
                for token in get_available_tokens():
                    amt = get_real_balance(exch, token)
                    if amt > 0:
                        price = get_price(exch, token)
                        if price:
                            total_portfolio += amt * price
        total_capital = total_usdt + total_portfolio
        st.info(f"💰 **Реальные балансы** | USDT: {total_usdt:.2f} | Портфель: {total_portfolio:.2f} | Капитал: {total_capital:.2f}")
    else:
        bal_data = get_latest_balances(st.session_state.user_id)
        if bal_data:
            df = pd.DataFrame(bal_data)
            df = df.sort_values('created_at').groupby(['exchange', 'asset']).last().reset_index()
            usdt_rows = df[df['asset'] == 'USDT']
            total_usdt = usdt_rows['total'].sum() if not usdt_rows.empty else 0.0
            token_rows = df[df['asset'] != 'USDT']
            total_portfolio = token_rows['usdt_value'].sum() if not token_rows.empty else 0.0
            total_capital = total_usdt + total_portfolio
            st.info(f"💰 **Реальные балансы** | USDT: {total_usdt:.2f} | Портфель: {total_portfolio:.2f} | Капитал: {total_capital:.2f}")
        else:
            st.info("⏳ Балансы загружаются...")
            total_capital = 0.0

col_a, col_b, col_c, col_d, col_e = st.columns(5)
col_a.metric("💰 USDT на биржах", f"{total_usdt:.2f}")
col_b.metric("📦 Портфель (токены)", f"{total_portfolio:.2f}")
col_c.metric("💎 Общий капитал", f"{total_capital:.2f}")

trades = get_user_trades(st.session_state.user_id, limit=1000)
total_profit = sum(t.get('profit', 0) for t in trades) if trades else 0.0
trade_count = len(trades) if trades else 0
col_d.metric("📈 Прибыль с запуска", f"{total_profit:.4f} USDT")
col_e.metric("📊 Сделок", trade_count)

# ------------------- НАСТРОЙКИ -------------------
with st.expander("⚙️ Настройки арбитража", expanded=False):
    settings = get_user_settings(st.session_state.user_id)
    if settings and st.session_state.role == 'admin':
        fee = st.number_input("Комиссия (%)", 0.0, 0.5, settings.get('fee', 0.2), 0.01, format="%.2f")
        min_profit = st.number_input("Мин. прибыль (USDT)", 0.001, 1.0, settings.get('min_profit', 0.03), 0.01, format="%.3f")
        min_trade = st.number_input("Минимальная сумма сделки (USDT)", 1.0, 1000.0, settings.get('min_trade', 8.0), 5.0)
        max_trade = st.number_input("Максимальная сумма сделки (USDT)", 1.0, 1000.0, settings.get('max_trade', 20.0), 10.0)
        scan_interval = st.number_input("Интервал сканирования (сек)", 10, 120, settings.get('scan_interval', 30), 5)
        use_orderbook = st.checkbox("Учитывать стакан", value=settings.get('use_orderbook', True))
        max_slippage = st.number_input("Макс. проскальзывание (%)", 0.05, 1.0, settings.get('max_slippage', 0.3), 0.05, format="%.2f")
        if st.button("💾 Сохранить настройки", width='stretch'):
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

# ------------------- ЛОГ АВТО-ТОРГОВЛИ -------------------
with st.expander("📋 Лог авто-торговли", expanded=False):
    logs = get_logs(st.session_state.user_id, limit=50)
    if logs:
        for log in logs:
            st.text(f"{log['created_at'][:16]} | {log['message']}")
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
    settings = get_user_settings(st.session_state.user_id)
    if settings:
        st.write(f"Текущие настройки суммы сделки: от **{settings.get('min_trade', 8):.0f}** до **{settings.get('max_trade', 20):.0f}** USDT (общий лимит).")
        st.write(f"**Минимальная прибыль:** {settings.get('min_profit', 0.03):.2f} USDT.")
    st.markdown("---")
    st.markdown("### 💹 Текущие цены токенов")
    tokens = get_available_tokens()
    token_prices = []
    for token in tokens:
        row = {"Токен": token}
        for ex in EXCHANGES:
            if public_clients.get(ex):
                try:
                    price = public_clients[ex].fetch_ticker(f"{token}/USDT")['last']
                    row[ex.upper()] = f"{price:.8f}" if price else "—"
                except:
                    row[ex.upper()] = "—"
            else:
                row[ex.upper()] = "—"
        if row.get("KUCOIN", "—") != "—" and row.get("OKX", "—") != "—":
            try:
                diff = abs(float(row["KUCOIN"]) - float(row["OKX"])) / float(row["KUCOIN"]) * 100
                row["Спред %"] = f"{diff:.2f}%"
                is_profitable = diff > (settings.get('min_profit', 0.03) / (settings.get('min_trade', 8) / 100) + 0.1 if settings else 0.3)
                row["Арбитраж"] = "✅" if is_profitable else "❌"
            except:
                row["Спред %"] = "—"
                row["Арбитраж"] = "?"
        else:
            row["Спред %"] = "—"
            row["Арбитраж"] = "?"
        token_prices.append(row)
    if token_prices:
        df_prices = pd.DataFrame(token_prices)
        def highlight_profitable(row):
            if row.get("Арбитраж") == "✅":
                return ['background-color: #00FF88; color: black'] * len(row)
            return [''] * len(row)
        st.dataframe(df_prices.style.apply(highlight_profitable, axis=1), width='stretch', hide_index=True)
        st.caption("🟢 Зелёным выделены токены, спред по которым превышает минимальную прибыль с учётом комиссии.")

# ----- Графики -----
with tabs[1]:
    st.subheader("📈 Графики (японские свечи)")
    tok = st.selectbox("Выберите токен", get_available_tokens())
    timeframe = st.selectbox("Таймфрейм", ["1m", "5m", "15m", "1h", "4h", "1d"], index=3)
    exchange_for_chart = st.selectbox("Биржа", EXCHANGES, index=0)
    if tok and exchange_for_chart:
        exchange = public_clients.get(exchange_for_chart)
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
                    fig.update_layout(
                        title=f"{tok}/USDT ({timeframe}) на {exchange_for_chart.upper()}",
                        xaxis_title="Время",
                        yaxis_title="Цена (USDT)",
                        height=600
                    )
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
    if st.button("🔍 Найти лучшую возможность (с учётом текущих настроек)", width='stretch'):
        if st.session_state.role == 'admin' and st.session_state.real_exchanges:
            from utils import find_arbitrage_opportunity
            settings = get_user_settings(st.session_state.user_id)
            if settings:
                opp = find_arbitrage_opportunity(
                    settings.get('fee', 0.2),
                    settings.get('min_profit', 0.03),
                    settings.get('min_trade', 8.0),
                    settings.get('max_trade', 20.0),
                    settings.get('orderbook_depth', 20),
                    settings.get('use_orderbook', True),
                    st.session_state.real_exchanges,
                    settings.get('max_slippage', 0.3)
                )
                if opp:
                    st.success(f"Найдена возможность: {opp['token']}")
                    st.write(f"**Покупка:** {opp['buy_ex'].upper()} по {opp['buy_price']:.8f} USDT")
                    st.write(f"**Продажа:** {opp['sell_ex'].upper()} по {opp['sell_price']:.8f} USDT")
                    st.write(f"**Сумма сделки:** {opp['trade_usdt']:.2f} USDT")
                    st.write(f"**Прибыль:** {opp['profit']:.4f} USDT")
                    if st.button("✅ Выполнить сделку (реал/демо)", width='stretch'):
                        from utils import execute_arbitrage, get_trade_mode, get_demo_data
                        mode = get_trade_mode(st.session_state.user_id)
                        is_demo = (mode == 'демо')
                        demo_data = get_demo_data(st.session_state.user_id) if is_demo else None
                        profit, msg = execute_arbitrage(
                            opp, st.session_state.user_id, st.session_state.real_exchanges,
                            settings.get('reinvest_percent', 0),
                            settings.get('use_orderbook', True),
                            settings.get('orderbook_depth', 20),
                            settings.get('max_slippage', 0.3),
                            is_demo, demo_data
                        )
                        if profit:
                            st.success(f"Сделка выполнена! Прибыль: {profit:.2f} USDT")
                            st.rerun()
                        else:
                            st.error(f"Ошибка: {msg}")
                else:
                    st.warning("Арбитражных возможностей не найдено")
        else:
            st.error("Ручной поиск доступен только администратору")

# ----- Статистика -----
with tabs[3]:
    st.subheader("📊 Статистика")
    trades = get_user_trades(st.session_state.user_id, limit=1000)
    if trades:
        df = pd.DataFrame(trades)
        total_profit = df['profit'].sum()
        total_trades = len(df)
        col1, col2, col3 = st.columns(3)
        col1.metric("📈 Общая прибыль", f"{total_profit:.4f} USDT")
        col2.metric("🔄 Количество сделок", total_trades)
        col3.metric("💰 Доступно для вывода", "0.00 USDT")
        if total_trades > 0:
            avg = total_profit / total_trades
            st.metric("📊 Средняя прибыль на сделку", f"{avg:.4f} USDT")
        df = df.sort_values('trade_time')
        df['cumulative_profit'] = df['profit'].cumsum()
        fig = px.line(df, x='trade_time', y='cumulative_profit', title="Накопленная прибыль")
        st.plotly_chart(fig)
    else:
        st.info("Нет сделок для отображения.")

# ----- Балансы -----
with tabs[4]:
    st.subheader("💼 Балансы")
    mode = get_trade_mode(st.session_state.user_id)
    if mode == 'демо':
        demo_data = get_demo_data(st.session_state.user_id)
        if demo_data:
            for ex in EXCHANGES:
                with st.expander(f"{ex.upper()}"):
                    bal = demo_data['balances'].get(ex, {})
                    st.write(f"**USDT:** {bal.get('USDT', 0):.2f}")
                    for token, amt in bal.get('portfolio', {}).items():
                        if amt > 0:
                            price = public_clients.get(ex).fetch_ticker(f"{token}/USDT")['last'] if public_clients.get(ex) else 0
                            st.write(f"{token}: {amt:.8f} ≈ {amt * price:.2f} USDT")
        else:
            st.info("Демо-данные не загружены")
    else:
        if st.session_state.role == 'admin' and st.session_state.real_exchanges:
            for ex in EXCHANGES:
                exch = st.session_state.real_exchanges.get(ex)
                if exch:
                    with st.expander(f"{ex.upper()}"):
                        bal = exch.fetch_balance()
                        usdt = bal.get('USDT', {}).get('free', 0.0)
                        st.write(f"**USDT:** {usdt:.2f}")
                        for token in get_available_tokens():
                            amt = bal.get(token, {}).get('free', 0.0)
                            if amt > 0:
                                price = get_price(exch, token)
                                if price:
                                    st.write(f"{token}: {amt:.8f} ≈ {amt * price:.2f} USDT")
        else:
            bal_data = get_latest_balances(st.session_state.user_id)
            if bal_data:
                df = pd.DataFrame(bal_data)
                df = df.sort_values('created_at').groupby(['exchange', 'asset']).last().reset_index()
                for ex in EXCHANGES:
                    with st.expander(f"{ex.upper()}"):
                        ex_data = df[df['exchange'] == ex]
                        if not ex_data.empty:
                            for _, row in ex_data.iterrows():
                                if row['asset'] == 'USDT':
                                    st.write(f"**USDT:** {row['total']:.2f}")
                                else:
                                    st.write(f"{row['asset']}: {row['free']:.8f} ≈ {row['usdt_value']:.2f} USDT")
            else:
                st.info("Нет данных по балансам. Ожидайте первого сканирования worker'ом.")

# ----- Вывод -----
with tabs[5]:
    st.subheader("💰 Вывод средств")
    st.info("Вывод доступен только для демо-режима (комиссия 22%).")
    mode = get_trade_mode(st.session_state.user_id)
    if mode == 'демо':
        demo_data = get_demo_data(st.session_state.user_id)
        withdrawable = demo_data.get('withdrawable_balance', 0) if demo_data else 0
        st.write(f"Доступно для вывода: **{withdrawable:.2f} USDT**")
        amount = st.number_input("Сумма вывода (USDT)", min_value=1.0, max_value=max(1.0, withdrawable), step=10.0)
        wallet = st.text_input("Адрес USDT (TRC20)", value=st.session_state.wallet)
        if st.button("Запросить вывод", width='stretch'):
            st.warning("Вывод из демо-режима не поддерживается (только симуляция).")
    else:
        st.warning("Вывод доступен только в демо-режиме.")

# ----- История -----
with tabs[6]:
    st.subheader("📜 История сделок")
    trades = get_user_trades(st.session_state.user_id, limit=100)
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
    col1, col2 = st.columns(2)
    with col1:
        st.write(f"**Имя:** {st.session_state.username}")
        st.write(f"**Email:** {st.session_state.email}")
        st.write(f"**Кошелёк:** {st.session_state.wallet}")
    with col2:
        st.write(f"**Всего сделок:** {trade_count}")
        st.write(f"**Общая прибыль:** {total_profit:.4f} USDT")
        st.write(f"**Общий капитал:** {total_capital:.2f} USDT")

# ----- Чат -----
with tabs[8]:
    st.subheader("💬 Чат поддержки")
    st.info("Чат будет доступен в следующей версии")

# ----- Админ-панель -----
if show_admin:
    with tabs[9]:
        st.subheader("👑 Административная панель")
        admin_tabs = st.tabs(["Пользователи", "API ключи", "Конфигурация токенов"])
        
        with admin_tabs[0]:
            st.markdown("#### Управление пользователями")
            users = get_all_users()
            for user in users:
                with st.expander(f"{user['email']} - {user['full_name']}"):
                    st.write(f"Статус: {user['registration_status']}")
                    st.write(f"Роль: {user.get('role', 'viewer')}")
                    st.write(f"Сделок: {user.get('trade_count', 0)}")
                    new_status = st.selectbox("Изменить статус", ["approved", "blocked"], key=f"status_{user['id']}")
                    new_role = st.selectbox("Изменить роль", ["viewer", "admin"], index=0 if user.get('role', 'viewer') == 'viewer' else 1, key=f"role_{user['id']}")
                    if st.button("Обновить", key=f"update_{user['id']}"):
                        update_user_status(user['id'], new_status)
                        update_user_role(user['id'], new_role)
                        st.rerun()
        
        with admin_tabs[1]:
            st.markdown("#### API ключи бирж")
            st.warning("⚠️ Введите свои реальные API-ключи с правами на спотовую торговлю.")
            for ex in EXCHANGES:
                with st.expander(f"{ex.upper()}"):
                    api_key = st.text_input(f"API Key ({ex})", type="password", value="", key=f"api_{ex}")
                    secret = st.text_input(f"Secret Key ({ex})", type="password", value="", key=f"sec_{ex}")
                    passphrase = st.text_input(f"Passphrase ({ex})", type="password", value="", key=f"pass_{ex}")
                    if st.button(f"Сохранить {ex}", key=f"save_{ex}"):
                        if api_key and secret and passphrase:
                            save_api_key(ex, api_key, secret, passphrase, st.session_state.email)
                            st.success(f"Ключи для {ex} сохранены")
                            st.session_state.real_exchanges = init_real_exchanges()
                            st.rerun()
                        else:
                            st.error(f"Для {ex} необходимо заполнить все поля.")
        
        with admin_tabs[2]:
            st.markdown("#### Конфигурация токенов")
            current_tokens = get_available_tokens()
            tokens_input = st.text_area("Список токенов (через запятую)", value=", ".join(current_tokens))
            if st.button("Сохранить токены", width='stretch'):
                new_tokens = [t.strip().upper() for t in tokens_input.split(",") if t.strip()]
                if new_tokens:
                    set_config('tokens', new_tokens)
                    st.success("Список токенов обновлён")
                    st.rerun()
