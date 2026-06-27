import streamlit as st
import os
import hashlib
from supabase import create_client

st.set_page_config(page_title="Arbitrage Bot", layout="wide")

# ------------------- SUPABASE -------------------
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ------------------- ФУНКЦИИ -------------------
def get_user_by_email(email):
    res = supabase.table('users').select('*').eq('email', email).execute()
    return res.data[0] if res.data else None

def load_settings(user_id):
    res = supabase.table('user_settings').select('*').eq('user_id', user_id).execute()
    if res.data:
        return res.data[0]
    return None

def save_settings(user_id, settings):
    supabase.table('user_settings').upsert(settings, on_conflict='user_id').execute()

# ------------------- СЕССИЯ (СОХРАНЕНИЕ В URL) -------------------
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_id = None
    st.session_state.email = None
    st.session_state.auto_trade_enabled = False

# Восстановление сессии из URL
if 'email' in st.query_params:
    email = st.query_params['email']
    user = get_user_by_email(email)
    if user:
        st.session_state.logged_in = True
        st.session_state.user_id = user['id']
        st.session_state.email = email
        # Загружаем настройки
        settings = load_settings(st.session_state.user_id)
        if settings:
            st.session_state.auto_trade_enabled = settings.get('auto_trade_enabled', False)

# Если уже вошли, но email не в URL — добавляем
if st.session_state.logged_in and st.session_state.email:
    if 'email' not in st.query_params:
        st.query_params.email = st.session_state.email

# ------------------- СТРАНИЦА ВХОДА -------------------
if not st.session_state.logged_in:
    st.title("Вход в бот")
    email = st.text_input("Email")
    pwd = st.text_input("Пароль", type="password")
    if st.button("Войти"):
        user = get_user_by_email(email)
        if user and user['password_hash'] == hashlib.sha256(pwd.encode()).hexdigest():
            st.session_state.logged_in = True
            st.session_state.user_id = user['id']
            st.session_state.email = email
            st.query_params.email = email
            # Загружаем настройки
            settings = load_settings(st.session_state.user_id)
            if settings:
                st.session_state.auto_trade_enabled = settings.get('auto_trade_enabled', False)
            st.rerun()
        else:
            st.error("Неверный email или пароль")
    st.stop()

# ------------------- ОСНОВНОЙ ИНТЕРФЕЙС -------------------
st.title("Арбитражный бот HOVMEL")
st.write(f"👤 {st.session_state.email}")

# Статус авто-сделок
if st.session_state.auto_trade_enabled:
    st.success("▶ АВТО-СДЕЛКИ АКТИВНЫ")
else:
    st.warning("⏹ АВТО-СДЕЛКИ ОСТАНОВЛЕНЫ")

# Кнопки управления
col1, col2, col3 = st.columns(3)
with col1:
    if st.button("▶ СТАРТ АВТО-ТОРГОВЛИ"):
        st.session_state.auto_trade_enabled = True
        # Сохраняем только те поля, которые есть в таблице
        save_settings(st.session_state.user_id, {
            'user_id': st.session_state.user_id,
            'auto_trade_enabled': True,
            'fee': 0.1,
            'min_profit': 0.07,
            'min_trade': 12.0,
            'max_trade': 100.0,
            'scan_interval': 20,
            'reinvest_percent': 0,
            'use_orderbook': True,
            'orderbook_depth': 10
        })
        st.rerun()

with col2:
    if st.button("⏹ СТОП АВТО-ТОРГОВЛИ"):
        st.session_state.auto_trade_enabled = False
        save_settings(st.session_state.user_id, {
            'user_id': st.session_state.user_id,
            'auto_trade_enabled': False
        })
        st.rerun()

with col3:
    if st.button("🚪 Выйти"):
        st.session_state.logged_in = False
        st.session_state.auto_trade_enabled = False
        st.query_params.clear()
        st.rerun()

# Показываем текущие настройки
st.subheader("⚙️ Настройки")
settings = load_settings(st.session_state.user_id)
if settings:
    st.write(f"Комиссия: {settings.get('fee', 0.1)}%")
    st.write(f"Мин. прибыль: {settings.get('min_profit', 0.07)} USDT")
    st.write(f"Интервал сканирования: {settings.get('scan_interval', 20)} сек")
else:
    st.info("Настройки не найдены. Нажмите СТАРТ для создания.")
