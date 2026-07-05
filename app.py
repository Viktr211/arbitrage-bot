import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import sys
import os
import hashlib  # <-- ДОБАВЬ ЭТУ СТРОКУ
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from utils import (
    supabase,
    get_user_by_email,
    get_user_settings,
    set_auto_trade_enabled,
    get_available_tokens,
    get_config,
    set_config
)
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from utils import (
    supabase,
    get_user_by_email,
    get_user_settings,
    set_auto_trade_enabled,
    get_available_tokens,
    get_config,
    set_config
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
    # Проверяем статус из БД
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

# ------------------- БАЛАНСЫ (читаем из БД или отображаем заглушку) -------------------
# Здесь можно добавить чтение балансов из БД, если они там сохраняются.
# Пока просто покажем метрики.
st.info("💰 Реальные балансы будут отображаться после первого сканирования worker'ом")

# ------------------- ВКЛАДКИ -------------------
show_admin = st.session_state.role == 'admin'
tabs_list = ["📊 Dashboard", "📈 Графики", "📊 Статистика", "💼 Балансы", "📜 История", "👤 Кабинет"]
if show_admin:
    tabs_list.append("👑 Админ-панель")
tabs = st.tabs(tabs_list)

# ----- Dashboard -----
with tabs[0]:
    st.subheader("📊 Dashboard")
    st.write("Добро пожаловать в арбитражного бота **HOVMEL**.")
    st.write(f"Активные токены: {', '.join(get_available_tokens())}")
    st.write("Статус: ожидание данных от worker'а...")

# ----- Графики -----
with tabs[1]:
    st.subheader("📈 Графики (японские свечи)")
    st.info("Графики будут доступны после накопления данных.")

# ----- Статистика -----
with tabs[2]:
    st.subheader("📊 Статистика")
    # Загружаем сделки из БД
    trades = supabase.table('trades').select('*').eq('user_id', st.session_state.user_id).order('trade_time', desc=True).limit(100).execute().data
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
        # График накопленной прибыли
        df_sorted = df.sort_values('trade_time')
        df_sorted['cumulative_profit'] = df_sorted['profit'].cumsum()
        fig = px.line(df_sorted, x='trade_time', y='cumulative_profit', title="Накопленная прибыль")
        st.plotly_chart(fig)
    else:
        st.info("Нет сделок для отображения.")

# ----- Балансы -----
with tabs[3]:
    st.subheader("💼 Балансы")
    st.info("Балансы будут отображаться после получения данных от worker'а")

# ----- История -----
with tabs[4]:
    st.subheader("📜 История сделок")
    trades = supabase.table('trades').select('*').eq('user_id', st.session_state.user_id).order('trade_time', desc=True).limit(100).execute().data
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
with tabs[5]:
    st.subheader("👤 Личный кабинет")
    st.write(f"**Имя:** {st.session_state.username}")
    st.write(f"**Email:** {st.session_state.email}")
    st.write(f"**Кошелёк:** {st.session_state.wallet}")

# ----- Админ-панель -----
if show_admin:
    with tabs[6]:
        st.subheader("👑 Административная панель")
        st.info("Здесь можно управлять пользователями, API-ключами и настройками.")
        # Можно добавить редактирование настроек пользователя
        settings = get_user_settings(st.session_state.user_id)
        if settings:
            with st.expander("Настройки пользователя"):
                fee = st.number_input("Комиссия (%)", 0.0, 0.5, settings.get('fee', 0.2), 0.01, format="%.2f")
                min_profit = st.number_input("Мин. прибыль (USDT)", 0.001, 1.0, settings.get('min_profit', 0.03), 0.01, format="%.3f")
                min_trade = st.number_input("Минимальная сумма сделки (USDT)", 1.0, 1000.0, settings.get('min_trade', 8.0), 5.0)
                max_trade = st.number_input("Максимальная сумма сделки (USDT)", 1.0, 1000.0, settings.get('max_trade', 20.0), 10.0)
                scan_interval = st.number_input("Интервал сканирования (сек)", 10, 120, settings.get('scan_interval', 30), 5)
                use_orderbook = st.checkbox("Учитывать стакан", value=settings.get('use_orderbook', True))
                max_slippage = st.number_input("Макс. проскальзывание (%)", 0.05, 1.0, settings.get('max_slippage', 0.3), 0.05, format="%.2f")
                if st.button("Сохранить настройки"):
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
                    # Обновляем в БД (сделаем функцию в utils)
                    from utils import update_user_settings
                    update_user_settings(st.session_state.user_id, new_settings)
                    st.success("Настройки сохранены!")
