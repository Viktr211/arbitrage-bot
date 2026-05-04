import streamlit as st
import json
import ccxt
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
import hashlib
import base64
from supabase import create_client, Client
import requests

st.set_page_config(page_title="Простой арбитражный бот", layout="wide", page_icon="🔄", initial_sidebar_state="collapsed")

SUPABASE_URL = st.secrets.get("SUPABASE_URL")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY")
if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("❌ Нет SUPABASE_URL / SUPABASE_KEY в Secrets")
    st.stop()
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

EXCHANGES = ["kucoin", "okx", "hitbtc"]
TOKENS = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "LINK", "SUI", "HYPE", "TON"]
ADMIN_EMAILS = ["cb777899@gmail.com", "admin@arbitrage.com"]

def is_admin(email):
    return email in ADMIN_EMAILS

# ---------- НАСТРОЙКИ ----------
FEE_PERCENT = 0.1  # 0.1% комиссия тейкера
MIN_PROFIT_USDT = 0.05  # минимальная прибыль для сделки

# ---------- ФУНКЦИИ SUPABASE ----------
def get_user_by_email(email):
    res = supabase.table('users').select('*').eq('email', email).execute()
    return res.data[0] if res.data else None

def create_user(email, pwd_hash, full_name, country, city, phone, wallet):
    empty_balances = {
        ex: {"USDT": 0.0, "portfolio": {token: 0.0 for token in TOKENS}}
        for ex in EXCHANGES
    }
    data = {
        'email': email, 'password_hash': pwd_hash, 'full_name': full_name,
        'country': country, 'city': city, 'phone': phone, 'wallet_address': wallet,
        'registration_status': 'approved',
        'trade_balance': 0, 'withdrawable_balance': 0, 'total_profit': 0, 'trade_count': 0, 'total_admin_fee_paid': 0,
        'demo_balances': json.dumps(empty_balances),
        'demo_history': json.dumps([]),
        'demo_stats': json.dumps({})
    }
    res = supabase.table('users').insert(data).execute()
    return res.data[0]['id'] if res.data else None

def load_balances(user_id):
    res = supabase.table('users').select('demo_balances').eq('id', user_id).execute()
    if res.data and res.data[0].get('demo_balances'):
        return json.loads(res.data[0]['demo_balances'])
    else:
        return {ex: {"USDT": 0.0, "portfolio": {token: 0.0 for token in TOKENS}} for ex in EXCHANGES}

def save_balances(user_id, balances):
    supabase.table('users').update({'demo_balances': json.dumps(balances)}).eq('id', user_id).execute()

def load_history(user_id):
    res = supabase.table('users').select('demo_history').eq('id', user_id).execute()
    if res.data and res.data[0].get('demo_history'):
        return json.loads(res.data[0]['demo_history'])
    return []

def save_history(user_id, history):
    supabase.table('users').update({'demo_history': json.dumps(history[-500:])}).eq('id', user_id).execute()

def add_trade(user_id, mode, asset, amount, profit, buy_ex, sell_ex):
    supabase.table('trades').insert({
        'user_id': user_id, 'mode': mode, 'asset': asset,
        'amount': amount, 'profit': profit, 'buy_exchange': buy_ex, 'sell_exchange': sell_ex
    }).execute()

def get_config(key):
    res = supabase.table('config').select('value').eq('key', key).execute()
    return json.loads(res.data[0]['value']) if res.data else None

def set_config(key, value):
    supabase.table('config').upsert({'key': key, 'value': json.dumps(value)}).execute()

def get_available_tokens():
    tokens = get_config('tokens')
    return tokens if tokens else TOKENS

def get_messages(user_id=None, limit=50):
    if user_id:
        res = supabase.table('messages').select('*').eq('user_id', user_id).order('created_at', desc=True).limit(limit).execute()
    else:
        res = supabase.table('messages').select('*, users(full_name)').order('created_at', desc=True).limit(limit).execute()
    return res.data

def add_message(user_id, user_email, user_name, message, is_admin_reply=False, reply_to=None):
    supabase.table('messages').insert({
        'user_id': user_id, 'user_email': user_email, 'user_name': user_name,
        'message': message, 'is_admin_reply': is_admin_reply, 'reply_to': reply_to
    }).execute()

def mark_messages_read(user_id):
    supabase.table('messages').update({'is_read': True}).eq('user_id', user_id).eq('is_read', False).eq('is_admin_reply', True).execute()

def get_unread_count(user_id):
    res = supabase.table('messages').select('id', count='exact').eq('user_id', user_id).eq('is_read', False).eq('is_admin_reply', True).execute()
    return res.count or 0

ENCRYPTION_KEY = hashlib.sha256("arbitrage_secret_key_2024".encode()).digest()
def encrypt_api_key(key):
    if not key: return ""
    try:
        from cryptography.fernet import Fernet
        fernet = Fernet(base64.urlsafe_b64encode(ENCRYPTION_KEY[:32]))
        return fernet.encrypt(key.encode()).decode()
    except:
        return base64.b64encode(key.encode()).decode()
def decrypt_api_key(encrypted):
    if not encrypted: return ""
    try:
        from cryptography.fernet import Fernet
        fernet = Fernet(base64.urlsafe_b64encode(ENCRYPTION_KEY[:32]))
        return fernet.decrypt(encrypted.encode()).decode()
    except:
        try:
            return base64.b64decode(encrypted).decode()
        except:
            return ""

# ---------- ПОДКЛЮЧЕНИЕ К БИРЖАМ ----------
@st.cache_resource
def init_exchanges():
    exchanges = {}
    status = {}
    for ex_name in EXCHANGES:
        try:
            ex = getattr(ccxt, ex_name)({'enableRateLimit': True})
            ex.fetch_ticker('BTC/USDT')
            exchanges[ex_name] = ex
            status[ex_name] = "connected"
        except:
            status[ex_name] = "error"
    return exchanges, status

def get_price(exchange, symbol):
    try:
        ticker = exchange.fetch_ticker(f"{symbol}/USDT")
        return ticker['last']
    except:
        return None

# ---------- БАЛАНСЫ ----------
def get_balance(exchange_name, asset):
    bal = st.session_state.user_balances.get(exchange_name, {})
    if asset == 'USDT':
        return bal.get('USDT', 0.0)
    else:
        return bal.get('portfolio', {}).get(asset, 0.0)

def update_balance(exchange_name, asset, delta):
    if exchange_name not in st.session_state.user_balances:
        st.session_state.user_balances[exchange_name] = {"USDT": 0.0, "portfolio": {t: 0.0 for t in TOKENS}}
    if 'USDT' not in st.session_state.user_balances[exchange_name]:
        st.session_state.user_balances[exchange_name]['USDT'] = 0.0
    if 'portfolio' not in st.session_state.user_balances[exchange_name]:
        st.session_state.user_balances[exchange_name]['portfolio'] = {t: 0.0 for t in TOKENS}
    if asset == 'USDT':
        st.session_state.user_balances[exchange_name]['USDT'] += delta
    else:
        if asset not in st.session_state.user_balances[exchange_name]['portfolio']:
            st.session_state.user_balances[exchange_name]['portfolio'][asset] = 0.0
        st.session_state.user_balances[exchange_name]['portfolio'][asset] += delta
    save_balances(st.session_state.user_id, st.session_state.user_balances)

def buy_token_with_usdt(exchange_name, token, usdt_amount):
    """Покупает токен на указанную сумму USDT по текущему курсу"""
    ex = st.session_state.exchanges.get(exchange_name)
    if not ex:
        return False, "Биржа не подключена"
    price = get_price(ex, token)
    if not price:
        return False, "Не удалось получить цену"
    amount = usdt_amount / price
    usdt_current = get_balance(exchange_name, 'USDT')
    if usdt_current < usdt_amount:
        return False, f"Недостаточно USDT (есть {usdt_current:.2f})"
    update_balance(exchange_name, 'USDT', -usdt_amount)
    update_balance(exchange_name, token, amount)
    return True, f"Куплено {amount:.8f} {token} за {usdt_amount} USDT по цене {price:.2f}"

# ---------- АРБИТРАЖ ----------
def find_best_opportunity():
    opportunities = []
    if not st.session_state.exchanges:
        return None
    tokens = get_available_tokens()
    prices = {}
    for ex_name, ex in st.session_state.exchanges.items():
        prices[ex_name] = {}
        for token in tokens:
            price = get_price(ex, token)
            if price:
                prices[ex_name][token] = price
    exchange_names = list(prices.keys())
    for buy_ex in exchange_names:
        for sell_ex in exchange_names:
            if buy_ex == sell_ex:
                continue
            for token in tokens:
                if token not in prices[buy_ex] or token not in prices[sell_ex]:
                    continue
                buy_price = prices[buy_ex][token]
                sell_price = prices[sell_ex][token]
                if sell_price <= buy_price:
                    continue
                # Проверяем, хватает ли средств
                usdt_buy = get_balance(buy_ex, 'USDT')
                token_sell = get_balance(sell_ex, token)
                if usdt_buy < 10 or token_sell < 0.001:
                    continue
                # Максимальная сумма сделки (мин. из доступных USDT и стоимости токенов)
                max_trade_usdt = min(usdt_buy, token_sell * sell_price)
                if max_trade_usdt < 10:
                    continue
                # Прибыль до комиссий
                profit_before = (sell_price - buy_price) * (max_trade_usdt / buy_price)
                fee = profit_before * (FEE_PERCENT / 100)
                profit_after = profit_before - fee
                if profit_after < MIN_PROFIT_USDT:
                    continue
                opportunities.append({
                    'token': token,
                    'buy_ex': buy_ex,
                    'sell_ex': sell_ex,
                    'buy_price': buy_price,
                    'sell_price': sell_price,
                    'trade_usdt': max_trade_usdt,
                    'amount': max_trade_usdt / buy_price,
                    'profit': profit_after
                })
    if not opportunities:
        return None
    return max(opportunities, key=lambda x: x['profit'])

def execute_trade(opp):
    buy_ex = opp['buy_ex']
    sell_ex = opp['sell_ex']
    token = opp['token']
    buy_price = opp['buy_price']
    sell_price = opp['sell_price']
    amount = opp['amount']
    trade_usdt = opp['trade_usdt']
    expected_profit = opp['profit']

    # Проверяем ещё раз балансы
    usdt_buy = get_balance(buy_ex, 'USDT')
    token_sell = get_balance(sell_ex, token)
    if usdt_buy < trade_usdt:
        return None, f"Не хватает USDT на {buy_ex}"
    if token_sell < amount:
        return None, f"Не хватает {token} на {sell_ex}"

    # Исполняем
    update_balance(buy_ex, 'USDT', -trade_usdt)
    update_balance(buy_ex, token, amount)
    update_balance(sell_ex, token, -amount)
    update_balance(sell_ex, 'USDT', amount * sell_price)

    real_profit = amount * sell_price - trade_usdt
    st.session_state.total_profit += real_profit
    st.session_state.trade_count += 1
    entry = f"✅ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | {token} | {buy_ex}→{sell_ex} | {amount:.8f} | +{real_profit:.2f} USDT"
    st.session_state.user_history.append(entry)
    save_history(st.session_state.user_id, st.session_state.user_history)
    add_trade(st.session_state.user_id, "Демо", token, amount, real_profit, buy_ex, sell_ex)
    supabase.table('users').update({
        'total_profit': st.session_state.total_profit,
        'trade_count': st.session_state.trade_count
    }).eq('id', st.session_state.user_id).execute()
    return real_profit, None

# ---------- СЕССИЯ ----------
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = None
    st.session_state.email = None
    st.session_state.wallet_address = ''
    st.session_state.exchanges = None
    st.session_state.exchange_status = {}
    st.session_state.user_id = None
    st.session_state.user_balances = {}
    st.session_state.user_history = []
    st.session_state.total_profit = 0
    st.session_state.trade_count = 0
    st.session_state.chat_unread = 0
    st.session_state.msg = ""

if st.session_state.exchanges is None:
    with st.spinner("Подключение к биржам..."):
        st.session_state.exchanges, st.session_state.exchange_status = init_exchanges()

if not st.session_state.logged_in:
    st.markdown('<h1 class="main-header">🔄 Простой арбитражный бот</h1>', unsafe_allow_html=True)
    tab_reg, tab_login = st.tabs(["📝 Регистрация","🔑 Вход"])
    with tab_reg:
        with st.form("register_form"):
            username = st.text_input("Имя")
            email = st.text_input("Email")
            country = st.text_input("Страна")
            city = st.text_input("Город")
            phone = st.text_input("Телефон")
            wallet = st.text_input("Адрес USDT")
            pwd = st.text_input("Пароль", type="password")
            pwd2 = st.text_input("Повтор пароля", type="password")
            if st.form_submit_button("Зарегистрироваться", use_container_width=True):
                if username and email and wallet and pwd and pwd == pwd2:
                    if get_user_by_email(email):
                        st.error("Email уже существует")
                    else:
                        create_user(email, pwd, username, country, city, phone, wallet)
                        st.success("Регистрация успешна! Теперь вы можете войти.")
                else:
                    st.error("Заполните все поля или пароли не совпадают")
    with tab_login:
        with st.form("login_form"):
            email = st.text_input("Email")
            pwd = st.text_input("Пароль", type="password")
            if st.form_submit_button("Войти", use_container_width=True):
                user = get_user_by_email(email)
                if user and user['password_hash'] == pwd:
                    if user['registration_status'] == 'approved':
                        st.session_state.logged_in = True
                        st.session_state.username = user['full_name']
                        st.session_state.email = user['email']
                        st.session_state.wallet_address = user.get('wallet_address', '')
                        st.session_state.user_id = user['id']
                        st.session_state.user_balances = load_balances(user['id'])
                        st.session_state.user_history = load_history(user['id'])
                        st.session_state.total_profit = user.get('total_profit', 0)
                        st.session_state.trade_count = user.get('trade_count', 0)
                        st.session_state.chat_unread = get_unread_count(user['id'])
                        st.success(f"Добро пожаловать, {st.session_state.username}!")
                        st.rerun()
                    else:
                        st.error("Доступ запрещён")
                else:
                    st.error("Неверный email или пароль")
    st.stop()

# Сохраняем данные
if st.session_state.user_id:
    save_balances(st.session_state.user_id, st.session_state.user_balances)

# ---------- ИНТЕРФЕЙС ----------
st.title("🔄 Простой арбитражный бот")
col1, col2, col3 = st.columns(3)
col1.metric("💰 Всего USDT", f"{sum(bal.get('USDT',0) for bal in st.session_state.user_balances.values()):.2f}")
col2.metric("📦 Стоимость портфеля", "—")
col3.metric("📊 Сделок", st.session_state.trade_count)

# ----- Вкладка 1: Балансы (пополнение USDT и покупка токенов) -----
st.subheader("💼 Балансы и пополнение")
for ex in EXCHANGES:
    with st.expander(f"### {ex.upper()}"):
        bal = st.session_state.user_balances.get(ex, {})
        usdt = bal.get('USDT', 0)
        st.metric("USDT", f"{usdt:.2f}")
        
        # Пополнение USDT
        col1, col2 = st.columns(2)
        with col1:
            add_usdt = st.number_input(f"Добавить USDT на {ex.upper()}", min_value=0.0, step=10.0, key=f"add_usdt_{ex}")
            if st.button(f"➕ Добавить USDT", key=f"btn_usdt_{ex}"):
                if add_usdt > 0:
                    update_balance(ex, 'USDT', add_usdt)
                    st.success(f"Добавлено {add_usdt} USDT")
                    st.rerun()
        
        # Покупка токенов за USDT (автоматический перевод по курсу)
        st.write("**Купить токены (автоматически по курсу)**")
        token_to_buy = st.selectbox(f"Токен", get_available_tokens(), key=f"token_{ex}")
        usdt_to_spend = st.number_input(f"Сумма USDT для покупки {token_to_buy}", min_value=0.0, step=10.0, key=f"spend_{ex}")
        if st.button(f"💰 Купить {token_to_buy}", key=f"buy_{ex}"):
            if usdt_to_spend > 0:
                success, msg = buy_token_with_usdt(ex, token_to_buy, usdt_to_spend)
                if success:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)
        
        # Текущий портфель
        st.write("**Текущий портфель:**")
        portfolio = bal.get('portfolio', {})
        for token, amount in portfolio.items():
            if amount > 0:
                price = get_price(st.session_state.exchanges.get(ex), token) if st.session_state.exchanges.get(ex) else None
                value = amount * price if price else 0
                st.write(f"{token}: {amount:.8f} ≈ ${value:.2f}")

# ----- Вкладка 2: Арбитраж -----
st.subheader("🔍 Арбитраж")
if st.button("🎯 НАЙТИ И ИСПОЛНИТЬ ЛУЧШУЮ СДЕЛКУ", use_container_width=True):
    with st.spinner("Поиск лучшей возможности..."):
        best = find_best_opportunity()
        if best:
            st.info(f"📊 Найдена сделка: купить {best['token']} на {best['buy_ex'].upper()} за {best['buy_price']:.2f}, продать на {best['sell_ex'].upper()} за {best['sell_price']:.2f} | Ожидаемая прибыль: {best['profit']:.2f} USDT")
            profit, error = execute_trade(best)
            if profit:
                st.success(f"✅ Сделка исполнена! Прибыль: +{profit:.2f} USDT")
                st.rerun()
            else:
                st.error(f"❌ Ошибка: {error}")
        else:
            st.warning("Арбитражных возможностей не найдено. Проверьте балансы USDT и токенов.")

# ----- История -----
st.subheader("📜 История сделок")
if st.session_state.user_history:
    for trade in reversed(st.session_state.user_history[-20:]):
        st.text(trade)
else:
    st.info("Нет сделок")

# ----- Чат -----
with st.expander("💬 Сообщения поддержке"):
    if is_admin(st.session_state.email):
        msgs = get_messages(limit=50)
        for msg in msgs:
            st.markdown(f"**{msg.get('user_name','Пользователь')}** ({msg.get('user_email','')}) - {msg['created_at'][:16]}")
            st.write(msg['message'])
            if not msg.get('is_admin_reply', False):
                reply = st.text_input("Ответ", key=f"rep_{msg['id']}")
                if st.button("Отправить", key=f"send_{msg['id']}") and reply:
                    add_message(msg['user_id'], msg['user_email'], msg['user_name'], reply, is_admin_reply=True, reply_to=msg['id'])
                    st.success("Ответ отправлен")
                    st.rerun()
            st.divider()
    else:
        user_msg = st.text_area("Ваше сообщение")
        if st.button("Отправить сообщение"):
            if user_msg:
                add_message(st.session_state.user_id, st.session_state.email, st.session_state.username, user_msg)
                st.success("Сообщение отправлено")
                st.rerun()
