import streamlit as st
import time
import json
import ccxt
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import hashlib
import base64
from supabase import create_client, Client
import requests
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="Арбитражный бот | Центральный кошелёк", layout="wide", page_icon="🔄", initial_sidebar_state="collapsed")

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

# ---------- НАСТРОЙКИ АРБИТРАЖА ----------
DEFAULT_FEE_PERCENT = 0.1
DEFAULT_MIN_PROFIT_USDT = 0.001      # снизил для теста
DEFAULT_MIN_TRADE_USDT = 10.0        # снизил
DEFAULT_MAX_TRADE_USDT = 50.0        # увеличил
DEFAULT_SCAN_INTERVAL = 10

# ---------- ФУНКЦИИ SUPABASE ----------
def get_user_by_email(email):
    res = supabase.table('users').select('*').eq('email', email).execute()
    return res.data[0] if res.data else None

def create_user(email, pwd_hash, full_name, country, city, phone, wallet):
    initial_data = {
        'main_balance': 0.0,
        'exchanges': {ex: {"USDT": 0.0, "portfolio": {t: 0.0 for t in TOKENS}} for ex in EXCHANGES},
        'total_profit': 0,
        'trade_count': 0,
        'withdrawable_balance': 0,
        'total_admin_fee_paid': 0
    }
    data = {
        'email': email, 'password_hash': pwd_hash, 'full_name': full_name,
        'country': country, 'city': city, 'phone': phone, 'wallet_address': wallet,
        'registration_status': 'approved',
        'trade_balance': 0,
        'withdrawable_balance': 0,
        'total_profit': 0,
        'trade_count': 0,
        'total_admin_fee_paid': 0,
        'demo_balances': json.dumps(initial_data),
        'demo_history': json.dumps([]),
        'demo_stats': json.dumps({})
    }
    res = supabase.table('users').insert(data).execute()
    return res.data[0]['id'] if res.data else None

def load_user_data(user_id):
    res = supabase.table('users').select('demo_balances, demo_history, demo_stats, total_profit, trade_count, withdrawable_balance, total_admin_fee_paid').eq('id', user_id).execute()
    if res.data:
        user = res.data[0]
        balances = user.get('demo_balances', {})
        if isinstance(balances, str):
            balances = json.loads(balances)
        if not isinstance(balances, dict) or 'main_balance' not in balances:
            balances = {
                'main_balance': 0.0,
                'exchanges': {ex: {"USDT": 0.0, "portfolio": {t: 0.0 for t in TOKENS}} for ex in EXCHANGES},
                'total_profit': user.get('total_profit', 0),
                'trade_count': user.get('trade_count', 0),
                'withdrawable_balance': user.get('withdrawable_balance', 0),
                'total_admin_fee_paid': user.get('total_admin_fee_paid', 0)
            }
        return {
            'main_balance': balances.get('main_balance', 0.0),
            'balances': balances.get('exchanges', {ex: {"USDT": 0.0, "portfolio": {t: 0.0 for t in TOKENS}} for ex in EXCHANGES}),
            'history': json.loads(user.get('demo_history', '[]')) if isinstance(user.get('demo_history'), str) else user.get('demo_history', []),
            'stats': json.loads(user.get('demo_stats', '{}')) if isinstance(user.get('demo_stats'), str) else user.get('demo_stats', {}),
            'total_profit': balances.get('total_profit', user.get('total_profit', 0)),
            'trade_count': balances.get('trade_count', user.get('trade_count', 0)),
            'withdrawable_balance': balances.get('withdrawable_balance', user.get('withdrawable_balance', 0)),
            'total_admin_fee_paid': balances.get('total_admin_fee_paid', user.get('total_admin_fee_paid', 0))
        }
    return None

def save_user_data(user_id, data):
    balances = {
        'main_balance': data['main_balance'],
        'exchanges': data['balances'],
        'total_profit': data['total_profit'],
        'trade_count': data['trade_count'],
        'withdrawable_balance': data['withdrawable_balance'],
        'total_admin_fee_paid': data['total_admin_fee_paid']
    }
    supabase.table('users').update({
        'demo_balances': json.dumps(balances),
        'demo_history': json.dumps(data['history'][-500:]),
        'demo_stats': json.dumps(data['stats']),
        'total_profit': data['total_profit'],
        'trade_count': data['trade_count'],
        'withdrawable_balance': data['withdrawable_balance'],
        'total_admin_fee_paid': data['total_admin_fee_paid']
    }).eq('id', user_id).execute()

def add_trade(user_id, mode, asset, amount, profit, buy_ex, sell_ex):
    supabase.table('trades').insert({
        'user_id': user_id, 'mode': mode, 'asset': asset,
        'amount': amount, 'profit': profit, 'buy_exchange': buy_ex, 'sell_exchange': sell_ex
    }).execute()

def get_all_trades(limit=200):
    res = supabase.table('trades').select('*, users(email, full_name)').order('trade_time', desc=True).limit(limit).execute()
    return res.data

def create_withdrawal_request(user_id, amount, wallet):
    admin_fee = amount * 0.22
    supabase.table('withdrawals').insert({
        'user_id': user_id, 'amount': amount, 'admin_fee': admin_fee,
        'user_receives': amount - admin_fee, 'wallet_address': wallet, 'status': 'pending'
    }).execute()

def get_pending_withdrawals():
    res = supabase.table('withdrawals').select('*, users(email, full_name)').eq('status', 'pending').execute()
    return res.data

def update_withdrawal_status(wid, status, admin_email):
    supabase.table('withdrawals').update({
        'status': status, 'processed_at': datetime.now().isoformat(), 'processed_by': admin_email
    }).eq('id', wid).execute()

def get_all_users_for_admin():
    return supabase.table('users').select('*').order('created_at', desc=True).execute().data

def update_user_status(uid, status, admin_email):
    supabase.table('users').update({
        'registration_status': status, 'approved_at': datetime.now().isoformat(), 'approved_by': admin_email
    }).eq('id', uid).execute()

def get_all_api_keys():
    res = supabase.table('api_keys').select('exchange, api_key, secret_key').execute()
    return {row['exchange']: {'api_key': row['api_key'], 'secret_key': row['secret_key']} for row in res.data}

def save_api_key(exchange, api_key, secret_key, admin_email):
    enc_api = encrypt_api_key(api_key) if api_key else ""
    enc_secret = encrypt_api_key(secret_key) if secret_key else ""
    supabase.table('api_keys').upsert({
        'exchange': exchange, 'api_key': enc_api, 'secret_key': enc_secret,
        'updated_at': datetime.now().isoformat(), 'updated_by': admin_email
    }, on_conflict='exchange').execute()

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

# ---------- БАЛАНСЫ ПОЛЬЗОВАТЕЛЯ ----------
def get_balance(exchange_name, asset):
    bal = st.session_state.user_data['balances'].get(exchange_name, {})
    if asset == 'USDT':
        return bal.get('USDT', 0.0)
    else:
        return bal.get('portfolio', {}).get(asset, 0.0)

def update_balance(exchange_name, asset, delta):
    if exchange_name not in st.session_state.user_data['balances']:
        st.session_state.user_data['balances'][exchange_name] = {"USDT": 0.0, "portfolio": {t: 0.0 for t in TOKENS}}
    if 'USDT' not in st.session_state.user_data['balances'][exchange_name]:
        st.session_state.user_data['balances'][exchange_name]['USDT'] = 0.0
    if 'portfolio' not in st.session_state.user_data['balances'][exchange_name]:
        st.session_state.user_data['balances'][exchange_name]['portfolio'] = {t: 0.0 for t in TOKENS}
    if asset == 'USDT':
        st.session_state.user_data['balances'][exchange_name]['USDT'] += delta
    else:
        if asset not in st.session_state.user_data['balances'][exchange_name]['portfolio']:
            st.session_state.user_data['balances'][exchange_name]['portfolio'][asset] = 0.0
        st.session_state.user_data['balances'][exchange_name]['portfolio'][asset] += delta
    save_user_data(st.session_state.user_id, st.session_state.user_data)

def transfer_usdt_to_exchange(exchange_name, amount):
    if st.session_state.user_data['main_balance'] >= amount:
        st.session_state.user_data['main_balance'] -= amount
        update_balance(exchange_name, 'USDT', amount)
        return True, f"Переведено {amount} USDT на {exchange_name.upper()}"
    else:
        return False, f"Недостаточно средств в центральном кошельке (доступно {st.session_state.user_data['main_balance']:.2f})"

def transfer_usdt_from_exchange(exchange_name, amount):
    usdt_ex = get_balance(exchange_name, 'USDT')
    if usdt_ex >= amount:
        update_balance(exchange_name, 'USDT', -amount)
        st.session_state.user_data['main_balance'] += amount
        return True, f"Возвращено {amount} USDT с {exchange_name.upper()} в центральный кошелёк"
    else:
        return False, f"Недостаточно USDT на {exchange_name.upper()} (доступно {usdt_ex:.2f})"

def buy_token_with_usdt(exchange_name, token, usdt_amount):
    ex = st.session_state.exchanges.get(exchange_name)
    if not ex:
        return False, "Биржа не подключена"
    price = get_price(ex, token)
    if not price:
        return False, "Не удалось получить цену"
    amount_token = usdt_amount / price
    usdt_current = get_balance(exchange_name, 'USDT')
    if usdt_current < usdt_amount:
        return False, f"Недостаточно USDT на бирже (есть {usdt_current:.2f})"
    update_balance(exchange_name, 'USDT', -usdt_amount)
    update_balance(exchange_name, token, amount_token)
    return True, f"Куплено {amount_token:.8f} {token} за {usdt_amount} USDT по цене {price:.2f}"

def sell_token_to_usdt(exchange_name, token, amount_token):
    ex = st.session_state.exchanges.get(exchange_name)
    if not ex:
        return False, "Биржа не подключена"
    price = get_price(ex, token)
    if not price:
        return False, "Не удалось получить цену"
    token_current = get_balance(exchange_name, token)
    if token_current < amount_token:
        return False, f"Недостаточно {token} на бирже (есть {token_current:.8f})"
    usdt_received = amount_token * price
    update_balance(exchange_name, token, -amount_token)
    update_balance(exchange_name, 'USDT', usdt_received)
    return True, f"Продано {amount_token:.8f} {token} за {usdt_received:.2f} USDT по цене {price:.2f}"

# ---------- АРБИТРАЖ ----------
def find_best_opportunity(fee_percent, min_profit_usdt, min_trade_usdt, max_trade_usdt):
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
                usdt_buy = get_balance(buy_ex, 'USDT')
                token_sell = get_balance(sell_ex, token)
                if usdt_buy < min_trade_usdt or token_sell < 0.0001:
                    continue
                max_possible = min(usdt_buy, token_sell * sell_price)
                trade_usdt = min(max_possible, max_trade_usdt)
                if trade_usdt < min_trade_usdt:
                    continue
                amount = trade_usdt / buy_price
                profit_before = (sell_price - buy_price) * amount
                fee = profit_before * (fee_percent / 100)
                profit_after = profit_before - fee
                if profit_after < min_profit_usdt:
                    continue
                opportunities.append({
                    'token': token,
                    'buy_ex': buy_ex,
                    'sell_ex': sell_ex,
                    'buy_price': buy_price,
                    'sell_price': sell_price,
                    'trade_usdt': trade_usdt,
                    'amount': amount,
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

    usdt_buy = get_balance(buy_ex, 'USDT')
    token_sell = get_balance(sell_ex, token)
    if usdt_buy < trade_usdt:
        return None, f"Не хватает USDT на {buy_ex} (нужно {trade_usdt:.2f}, есть {usdt_buy:.2f})"
    if token_sell < amount:
        return None, f"Не хватает {token} на {sell_ex} (нужно {amount:.8f}, есть {token_sell:.8f})"

    update_balance(buy_ex, 'USDT', -trade_usdt)
    update_balance(buy_ex, token, amount)
    update_balance(sell_ex, token, -amount)
    update_balance(sell_ex, 'USDT', amount * sell_price)

    real_profit = amount * sell_price - trade_usdt
    st.session_state.user_data['total_profit'] += real_profit
    st.session_state.user_data['trade_count'] += 1
    entry = f"✅ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | {token} | {buy_ex}→{sell_ex} | {amount:.8f} | +{real_profit:.2f} USDT"
    st.session_state.user_data['history'].append(entry)
    save_user_data(st.session_state.user_id, st.session_state.user_data)
    add_trade(st.session_state.user_id, "Демо", token, amount, real_profit, buy_ex, sell_ex)
    return real_profit, None

# ---------- АВТО-СДЕЛКИ (через автообновление) ----------
def auto_trade():
    if not st.session_state.auto_trade_enabled:
        return
    with st.spinner("🔍 Поиск арбитражных возможностей..."):
        best = find_best_opportunity(
            st.session_state.fee_percent,
            st.session_state.min_profit_usdt,
            st.session_state.min_trade_usdt,
            st.session_state.max_trade_usdt
        )
        if best:
            st.session_state.auto_log.append(f"🎯 Найдена сделка: {best['token']} {best['buy_ex']}→{best['sell_ex']} прибыль {best['profit']:.4f} USDT")
            profit, error = execute_trade(best)
            if profit:
                st.session_state.auto_log.append(f"✅ Авто-сделка исполнена! +{profit:.2f} USDT")
            else:
                st.session_state.auto_log.append(f"❌ Ошибка: {error}")
        else:
            st.session_state.auto_log.append("ℹ️ Нет подходящих возможностей")

# ---------- СЕССИЯ ----------
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = None
    st.session_state.email = None
    st.session_state.wallet_address = ''
    st.session_state.exchanges = None
    st.session_state.exchange_status = {}
    st.session_state.user_id = None
    st.session_state.user_data = None
    st.session_state.chat_unread = 0
    st.session_state.auto_trade_enabled = False
    st.session_state.fee_percent = DEFAULT_FEE_PERCENT
    st.session_state.min_profit_usdt = DEFAULT_MIN_PROFIT_USDT
    st.session_state.min_trade_usdt = DEFAULT_MIN_TRADE_USDT
    st.session_state.max_trade_usdt = DEFAULT_MAX_TRADE_USDT
    st.session_state.scan_interval = DEFAULT_SCAN_INTERVAL
    st.session_state.auto_log = []

if st.session_state.exchanges is None:
    with st.spinner("Подключение к биржам..."):
        st.session_state.exchanges, st.session_state.exchange_status = init_exchanges()
        st.session_state.api_keys = get_all_api_keys()

# ---------- РЕГИСТРАЦИЯ / ВХОД ----------
if not st.session_state.logged_in:
    st.markdown('<h1 class="main-header">🔄 Арбитражный бот | Центральный кошелёк</h1>', unsafe_allow_html=True)
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
                        st.session_state.user_data = load_user_data(user['id'])
                        if st.session_state.user_data is None:
                            st.error("Не удалось загрузить данные пользователя")
                            st.stop()
                        st.session_state.chat_unread = get_unread_count(user['id'])
                        st.success(f"Добро пожаловать, {st.session_state.username}!")
                        st.rerun()
                    else:
                        st.error("Доступ запрещён")
                else:
                    st.error("Неверный email или пароль")
    st.stop()

# Сохраняем данные при каждом изменении
if st.session_state.user_id and st.session_state.user_data:
    save_user_data(st.session_state.user_id, st.session_state.user_data)

# ---------- ОСНОВНОЙ ИНТЕРФЕЙС ----------
col_logo, col_status, col_logout = st.columns([3, 1, 1])
with col_logo:
    st.markdown('<h1 class="main-header">🔄 Арбитражный бот | Центральный кошелёк</h1>', unsafe_allow_html=True)
with col_status:
    if st.session_state.auto_trade_enabled:
        st.markdown('<div style="text-align: center;"><span class="status-indicator status-running"></span> <b style="color: #00FF88;">АВТО-СДЕЛКИ АКТИВНЫ</b></div>', unsafe_allow_html=True)
    else:
        st.markdown('<div style="text-align: center;"><span class="status-indicator status-stopped"></span> <b style="color: #FF4444;">АВТО-СДЕЛКИ ОСТАНОВЛЕНЫ</b></div>', unsafe_allow_html=True)
with col_logout:
    if st.button("🚪 Выйти"):
        st.session_state.logged_in = False
        st.session_state.auto_trade_enabled = False
        st.rerun()

st.markdown(f'<div class="user-info">👤 {st.session_state.username} | 📧 {st.session_state.email}</div>', unsafe_allow_html=True)
connected = [ex.upper() for ex,sts in st.session_state.exchange_status.items() if sts=="connected"]
st.write(f"🔌 **Биржи:** {', '.join(connected)}")
st.write(f"🪙 **Токены:** {', '.join(get_available_tokens())}")
st.divider()

total_usdt_in_exchanges = sum(st.session_state.user_data['balances'].get(ex, {}).get('USDT', 0) for ex in EXCHANGES)
total_main = st.session_state.user_data['main_balance']
total_portfolio = 0
for ex, balances in st.session_state.user_data['balances'].items():
    for token, amount in balances.get('portfolio', {}).items():
        price = get_price(st.session_state.exchanges.get(ex), token) if st.session_state.exchanges.get(ex) else None
        if price:
            total_portfolio += amount * price

col1, col2, col3, col4 = st.columns(4)
col1.metric("💰 Центральный кошелёк", f"{total_main:.2f} USDT")
col2.metric("🏦 USDT на биржах", f"{total_usdt_in_exchanges:.2f} USDT")
col3.metric("📦 Портфель (токены)", f"{total_portfolio:.2f} USDT")
col4.metric("📊 Сделок", st.session_state.user_data['trade_count'])

c1, c2, c3, c4 = st.columns(4)
with c1:
    if st.button("▶ СТАРТ АВТО-ТОРГОВЛИ", use_container_width=True):
        st.session_state.auto_trade_enabled = True
        st.rerun()
with c2:
    if st.button("⏹ СТОП АВТО-ТОРГОВЛИ", use_container_width=True):
        st.session_state.auto_trade_enabled = False
        st.rerun()
with c3:
    if st.button("🔄 Ручное обновление", use_container_width=True):
        st.rerun()
with c4:
    new_mode = st.selectbox("Режим",["Демо","Реальный"], index=0)

# ----- АВТО-СДЕЛКИ (выполняются при обновлении страницы) -----
if st.session_state.auto_trade_enabled:
    st_autorefresh(interval=st.session_state.scan_interval * 1000, key="auto_refresh")
    auto_trade()

# ----- НАСТРОЙКИ АРБИТРАЖА -----
with st.expander("⚙️ Настройки арбитража"):
    new_fee = st.number_input("Комиссия тейкера (%)", min_value=0.0, max_value=0.5, value=st.session_state.fee_percent, step=0.01, format="%.2f")
    new_min_profit = st.number_input("Минимальная прибыль (USDT)", min_value=0.001, value=st.session_state.min_profit_usdt, step=0.01, format="%.3f")
    new_min_trade = st.number_input("Минимальная сумма сделки (USDT)", min_value=1.0, value=st.session_state.min_trade_usdt, step=5.0)
    new_max_trade = st.number_input("Максимальная сумма сделки (USDT)", min_value=1.0, value=st.session_state.max_trade_usdt, step=10.0)
    new_interval = st.number_input("Интервал авто-сканирования (сек)", min_value=5, max_value=60, value=st.session_state.scan_interval, step=5)
    if st.button("Сохранить настройки"):
        st.session_state.fee_percent = new_fee
        st.session_state.min_profit_usdt = new_min_profit
        st.session_state.min_trade_usdt = new_min_trade
        st.session_state.max_trade_usdt = new_max_trade
        st.session_state.scan_interval = new_interval
        st.success("Настройки сохранены")

# ----- Лог авто-торговли -----
with st.expander("📋 Лог авто-торговли (последние 20 событий)"):
    if st.session_state.auto_log:
        for log in st.session_state.auto_log[-20:]:
            st.text(log)
    else:
        st.info("Нет событий. Запустите авто-торговлю.")

# ---------- ВКЛАДКИ (остальные – как в предыдущей версии, но для краткости я приведу только ключевые) ----------
show_admin = is_admin(st.session_state.email)
tabs_list = ["📊 Dashboard", "📈 Графики", "🔄 Арбитраж", "📊 Статистика", "📈 Доходность", "💼 Балансы", "💰 Вывод", "📜 История", "👤 Кабинет", "💬 Чат"]
if show_admin:
    tabs_list.append("👑 Админ-панель")
tabs = st.tabs(tabs_list)

# Только основная вкладка Арбитраж (ручной) – остальные я опускаю для краткости, они идентичны предыдущему коду
with tabs[2]:
    st.subheader("🔍 Ручной арбитраж")
    if st.button("🎯 НАЙТИ И ИСПОЛНИТЬ ЛУЧШУЮ СДЕЛКУ", use_container_width=True):
        with st.spinner("Поиск и исполнение..."):
            best = find_best_opportunity(
                st.session_state.fee_percent,
                st.session_state.min_profit_usdt,
                st.session_state.min_trade_usdt,
                st.session_state.max_trade_usdt
            )
            if best:
                st.info(f"📊 Найдена сделка: купить {best['token']} на {best['buy_ex'].upper()} за {best['buy_price']:.2f}, продать на {best['sell_ex'].upper()} за {best['sell_price']:.2f} | Ожидаемая прибыль: {best['profit']:.4f} USDT")
                profit, error = execute_trade(best)
                if profit:
                    st.success(f"✅ Сделка исполнена! Прибыль: +{profit:.2f} USDT")
                    st.rerun()
                else:
                    st.error(f"❌ Ошибка: {error}")
            else:
                st.warning("Арбитражных возможностей не найдено")

# Остальные вкладки (Dashboard, Графики, Статистика, Доходность, Балансы, Вывод, История, Кабинет, Чат, Админ-панель) – они полностью аналогичны коду из предыдущего сообщения, просто скопируйте их оттуда.

st.caption(f"🚀 Настройки: комиссия {st.session_state.fee_percent}%, мин. прибыль {st.session_state.min_profit_usdt} USDT, мин. сделка {st.session_state.min_trade_usdt} USDT, макс. сделка {st.session_state.max_trade_usdt} USDT | Авто-интервал {st.session_state.scan_interval} сек")
