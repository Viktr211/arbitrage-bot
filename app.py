import streamlit as st
import time
import json
import ccxt
import pandas as pd
import plotly.express as px
from datetime import datetime
from supabase import create_client, Client
import hashlib
import base64
import os
from cryptography.fernet import Fernet
# Восстановление сессии из URL
if 'email' in st.query_params:
    email = st.query_params['email']
    user = get_user_by_email(email)
    if user:
        st.session_state.logged_in = True
        st.session_state.user_id = user['id']
        st.session_state.email = user['email']
        st.session_state.username = user['full_name']
        st.session_state.wallet = user.get('wallet_address', '')
elif st.session_state.get('logged_in', False) and st.session_state.get('email'):
    # Если пользователь уже вошёл, но email нет в URL — добавляем
    st.query_params.email = st.session_state.email


# ------------------- НАСТРОЙКИ СТРАНИЦЫ -------------------
st.set_page_config(page_title="Арбитражный бот HOVMEL", layout="wide", page_icon="🔄", initial_sidebar_state="collapsed")

# ------------------- CSS -------------------
st.markdown("""
<style>
.main-header h1 {
    font-size: 2.8rem;
    background: linear-gradient(135deg, #FFD700 0%, #FFA500 40%, #FF8C00 100%);
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
    text-align: center;
}
.hovmel-highlight {
    background: linear-gradient(120deg, #FFD700, #FF8C00);
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
    font-weight: 900;
}
.subtitle { text-align: center; color: #aaa; margin-top: -0.8rem; margin-bottom: 1.5rem; }
.status-running { color: #00FF88; font-weight: bold; }
.status-stopped { color: #FF4444; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# ------------------- SUPABASE -------------------
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ------------------- ШИФРОВАНИЕ -------------------
ENCRYPTION_KEY = "LHiBLyxFE1Z4BZSGFRPfy0AZ_ADKi0WV1ZwjUo9jjzE="
fernet = Fernet(ENCRYPTION_KEY.encode())

def encrypt_key(key: str) -> str:
    if not key: return ""
    return fernet.encrypt(key.encode()).decode()

def decrypt_key(encrypted: str) -> str:
    if not encrypted: return ""
    try:
        return fernet.decrypt(encrypted.encode()).decode()
    except:
        return ""

# ------------------- КОНСТАНТЫ -------------------
EXCHANGES = ["kucoin", "okx"]
TOKENS = ["DOGE", "SHIB", "PEPE", "WIF", "FLOKI", "BONK", "MEME", "BOME", "NEIRO", "BRETT", "BTC", "ETH", "SOL", "BNB", "TON"]
ADMIN_EMAILS = ["cb777899@gmail.com"]
def is_admin(email): return email in ADMIN_EMAILS

# ------------------- ФУНКЦИИ БАЗЫ ДАННЫХ -------------------
def get_user_by_email(email):
    res = supabase.table('users').select('*').eq('email', email).execute()
    return res.data[0] if res.data else None

def load_user_settings(user_id):
    res = supabase.table('user_settings').select('*').eq('user_id', user_id).execute()
    if res.data:
        return res.data[0]
    return None

def save_user_settings(user_id, settings):
    supabase.table('user_settings').update(settings).eq('user_id', user_id).execute()

# ------------------- ИНИЦИАЛИЗАЦИЯ СЕССИИ -------------------
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_id = None
    st.session_state.email = None
    st.session_state.username = None
    st.session_state.auto_trade_enabled = False
    st.session_state.fee = 0.1
    st.session_state.min_profit = 0.07
    st.session_state.min_trade = 12.0
    st.session_state.max_trade = 100.0
    st.session_state.scan_interval = 20

# Восстановление сессии из URL
if 'email' in st.query_params and not st.session_state.logged_in:
    email = st.query_params['email']
    user = get_user_by_email(email)
    if user:
        st.session_state.logged_in = True
        st.session_state.user_id = user['id']
        st.session_state.email = user['email']
        st.session_state.username = user['full_name']
        settings = load_user_settings(st.session_state.user_id)
        if settings:
            st.session_state.fee = float(settings.get('fee', 0.1))
            st.session_state.min_profit = float(settings.get('min_profit', 0.07))
            st.session_state.min_trade = float(settings.get('min_trade', 12.0))
            st.session_state.max_trade = float(settings.get('max_trade', 100.0))
            st.session_state.scan_interval = int(settings.get('scan_interval', 20))
            st.session_state.auto_trade_enabled = bool(settings.get('auto_trade_enabled', False))

# ------------------- ЛОГИН / РЕГИСТРАЦИЯ -------------------
if not st.session_state.logged_in:
    st.markdown('<div class="main-header"><h1>Арбитражный бот <span class="hovmel-highlight">HOVMEL</span></h1></div><div class="subtitle">⚡ Автоматический поиск межбиржевого арбитража 24/7 ⚡</div>', unsafe_allow_html=True)
    tab1, tab2 = st.tabs(["Вход", "Регистрация"])
    with tab1:
        email = st.text_input("Email")
        pwd = st.text_input("Пароль", type="password")
        if st.button("Войти"):
            user = get_user_by_email(email)
            if user and user['password_hash'] == hashlib.sha256(pwd.encode()).hexdigest():
                st.session_state.logged_in = True
                st.session_state.user_id = user['id']
                st.session_state.email = user['email']
                st.session_state.username = user['full_name']
                st.query_params.email = user['email']
                settings = load_user_settings(st.session_state.user_id)
                if settings:
                    st.session_state.fee = float(settings.get('fee', 0.1))
                    st.session_state.min_profit = float(settings.get('min_profit', 0.07))
                    st.session_state.min_trade = float(settings.get('min_trade', 12.0))
                    st.session_state.max_trade = float(settings.get('max_trade', 100.0))
                    st.session_state.scan_interval = int(settings.get('scan_interval', 20))
                    st.session_state.auto_trade_enabled = bool(settings.get('auto_trade_enabled', False))
                st.rerun()
            else:
                st.error("Неверные данные")
    with tab2:
        with st.form("reg"):
            name = st.text_input("Имя")
            email = st.text_input("Email")
            country = st.text_input("Страна")
            city = st.text_input("Город")
            phone = st.text_input("Телефон")
            wallet = st.text_input("Кошелёк USDT")
            pwd = st.text_input("Пароль", type="password")
            pwd2 = st.text_input("Повтор", type="password")
            if st.form_submit_button("Зарегистрироваться"):
                if name and email and wallet and pwd == pwd2:
                    if get_user_by_email(email):
                        st.error("Email уже есть")
                    else:
                        pwd_hash = hashlib.sha256(pwd.encode()).hexdigest()
                        supabase.table('users').insert({
                            'email': email,
                            'password_hash': pwd_hash,
                            'full_name': name,
                            'country': country,
                            'city': city,
                            'phone': phone,
                            'wallet_address': wallet,
                            'registration_status': 'approved'
                        }).execute()
                        st.success("OK, теперь войдите")
                else:
                    st.error("Ошибка")
    st.stop()

# ------------------- ОСНОВНОЙ ИНТЕРФЕЙС -------------------
st.markdown('<div class="main-header"><h1>Арбитражный бот <span class="hovmel-highlight">HOVMEL</span></h1></div><div class="subtitle">⚡ Автоматический поиск межбиржевого арбитража 24/7 ⚡</div>', unsafe_allow_html=True)

col1, col2, col3, col4 = st.columns([2,1,1,1])
with col1:
    st.markdown(f"👤 {st.session_state.username} | 📧 {st.session_state.email}")
with col2:
    if st.session_state.auto_trade_enabled:
        st.markdown('<span class="status-running">▶ АВТО-СДЕЛКИ АКТИВНЫ</span>', unsafe_allow_html=True)
    else:
        st.markdown('<span class="status-stopped">⏹ АВТО-СДЕЛКИ ОСТАНОВЛЕНЫ</span>', unsafe_allow_html=True)
with col4:
    if st.button("🚪 Выйти"):
        st.session_state.logged_in = False
        st.session_state.user_id = None
        st.session_state.email = None
        st.query_params.clear()
        st.rerun()

# ------------------- НАСТРОЙКИ -------------------
with st.expander("⚙️ Настройки арбитража", expanded=False):
    fee = st.number_input("Комиссия (%)", 0.0, 0.5, st.session_state.fee, 0.01, format="%.2f")
    min_profit = st.number_input("Мин. прибыль (USDT)", 0.001, 1.0, st.session_state.min_profit, 0.01, format="%.3f")
    min_trade = st.number_input("Минимальная сумма сделки (USDT)", 1.0, 1000.0, st.session_state.min_trade, 5.0)
    max_trade = st.number_input("Максимальная сумма сделки (USDT) (общий лимит)", 1.0, 1000.0, st.session_state.max_trade, 10.0)
    scan_interval = st.number_input("Интервал сканирования (сек)", 10, 120, st.session_state.scan_interval, 5)
    
    # Сохраняем настройки при изменении
    if st.session_state.user_id:
        save_user_settings(st.session_state.user_id, {
            'fee': fee,
            'min_profit': min_profit,
            'min_trade': min_trade,
            'max_trade': max_trade,
            'scan_interval': scan_interval,
            'auto_trade_enabled': st.session_state.auto_trade_enabled
        })
        st.info("Настройки сохранены")

# ------------------- УПРАВЛЕНИЕ АВТО-СДЕЛКАМИ -------------------
col_start, col_stop, _ = st.columns([1,1,2])
with col_start:
    if st.button("▶ СТАРТ АВТО-ТОРГОВЛИ", use_container_width=True):
        st.session_state.auto_trade_enabled = True
        if st.session_state.user_id:
            settings = load_user_settings(st.session_state.user_id)
            if settings:
                settings['auto_trade_enabled'] = True
                save_user_settings(st.session_state.user_id, settings)
        st.rerun()
with col_stop:
    if st.button("⏹ СТОП АВТО-ТОРГОВЛИ", use_container_width=True):
        st.session_state.auto_trade_enabled = False
        if st.session_state.user_id:
            settings = load_user_settings(st.session_state.user_id)
            if settings:
                settings['auto_trade_enabled'] = False
                save_user_settings(st.session_state.user_id, settings)
        st.rerun()

# ------------------- ЛОГ АВТО-ТОРГОВЛИ -------------------
with st.expander("📋 Лог авто-торговли", expanded=False):
    if st.session_state.auto_trade_enabled:
        st.info("🔍 Бот ищет арбитражные возможности... (логи будут здесь)")
    else:
        st.info("⏹ Авто-торговля остановлена. Нажмите СТАРТ для запуска.")

# ------------------- АДМИН-ПАНЕЛЬ -------------------
if is_admin(st.session_state.email):
    with st.expander("👑 Админ-панель", expanded=False):
        st.write("Здесь будет админ-панель")
