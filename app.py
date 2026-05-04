import streamlit as st
import time
import json
import ccxt
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import threading
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
DEFAULT_MIN_PROFIT_USDT = 0.005
DEFAULT_MIN_TRADE_USDT = 12.0
DEFAULT_MAX_TRADE_USDT = 30.0
DEFAULT_SCAN_INTERVAL = 10

# ---------- ФУНКЦИИ SUPABASE ----------
def get_user_by_email(email):
    res = supabase.table('users').select('*').eq('email', email).execute()
    return res.data[0] if res.data else None

def create_user(email, pwd_hash, full_name, country, city, phone, wallet):
    # Начальные данные: главный кошелёк = 0, на биржах всё 0
    data = {
        'email': email, 'password_hash': pwd_hash, 'full_name': full_name,
        'country': country, 'city': city, 'phone': phone, 'wallet_address': wallet,
        'registration_status': 'approved',
        'main_balance': 0.0,   # центральный кошелёк
        'total_profit': 0, 'trade_count': 0, 'total_admin_fee_paid': 0,
        'withdrawable_balance': 0,
        'demo_balances': json.dumps({ex: {"USDT": 0.0, "portfolio": {t: 0.0 for t in TOKENS}} for ex in EXCHANGES}),
        'demo_history': json.dumps([]),
        'demo_stats': json.dumps({})
    }
    res = supabase.table('users').insert(data).execute()
    return res.data[0]['id'] if res.data else None

def load_user_data(user_id):
    res = supabase.table('users').select('*').eq('id', user_id).execute()
    if res.data:
        user = res.data[0]
        return {
            'main_balance': user.get('main_balance', 0.0),
            'balances': json.loads(user.get('demo_balances', '{}')),
            'history': json.loads(user.get('demo_history', '[]')),
            'stats': json.loads(user.get('demo_stats', '{}')),
            'total_profit': user.get('total_profit', 0),
            'trade_count': user.get('trade_count', 0),
            'withdrawable_balance': user.get('withdrawable_balance', 0),
            'total_admin_fee_paid': user.get('total_admin_fee_paid', 0)
        }
    else:
        return None

def save_user_data(user_id, data):
    supabase.table('users').update({
        'main_balance': data['main_balance'],
        'demo_balances': json.dumps(data['balances']),
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
        return None, f"Не хватает USDT на {buy_ex}"
    if token_sell < amount:
        return None, f"Не хватает {token} на {sell_ex}"

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

# ---------- ФОНОВОЙ ПОТОК ДЛЯ АВТО-ТОРГОВЛИ ----------
def background_arbitrage_loop():
    while True:
        try:
            if st.session_state.get('auto_trade_enabled', False):
                opp = find_best_opportunity(
                    st.session_state.fee_percent,
                    st.session_state.min_profit_usdt,
                    st.session_state.min_trade_usdt,
                    st.session_state.max_trade_usdt
                )
                if opp:
                    profit, error = execute_trade(opp)
                    if profit:
                        print(f"✅ Авто-сделка: +{profit:.2f} USDT")
                    elif error:
                        print(f"❌ Ошибка: {error}")
                time.sleep(st.session_state.scan_interval)
            else:
                time.sleep(5)
        except Exception as e:
            print(f"Ошибка в фоновом потоке: {e}")
            time.sleep(5)

if 'background_thread_started' not in st.session_state:
    threading.Thread(target=background_arbitrage_loop, daemon=True).start()
    st.session_state.background_thread_started = True

BOT_STATUS_FILE = "bot_status.json"
def save_bot_status(status):
    try:
        with open(BOT_STATUS_FILE,'w') as f:
            json.dump({'bot_running':status}, f)
    except: pass
def load_bot_status():
    try:
        with open(BOT_STATUS_FILE,'r') as f:
            return json.load(f).get('bot_running', False)
    except:
        return False

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
    st.session_state.bot_running = load_bot_status()
    st.session_state.fee_percent = DEFAULT_FEE_PERCENT
    st.session_state.min_profit_usdt = DEFAULT_MIN_PROFIT_USDT
    st.session_state.min_trade_usdt = DEFAULT_MIN_TRADE_USDT
    st.session_state.max_trade_usdt = DEFAULT_MAX_TRADE_USDT
    st.session_state.scan_interval = DEFAULT_SCAN_INTERVAL

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
col_logo, col_status, col_logout = st.columns([3,1,1])
with col_logo:
    st.markdown('<h1 class="main-header">🔄 Арбитражный бот | Центральный кошелёк</h1>', unsafe_allow_html=True)
with col_status:
    if st.session_state.auto_trade_enabled:
        st.markdown('<div><span class="status-indicator status-running"></span> <b>АВТО-СДЕЛКИ АКТИВНЫ</b></div>', unsafe_allow_html=True)
    else:
        st.markdown('<div><span class="status-indicator status-stopped"></span> <b>ОСТАНОВЛЕН</b></div>', unsafe_allow_html=True)
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

# Общая статистика
total_usdt_in_exchanges = sum(st.session_state.user_data['balances'].get(ex, {}).get('USDT', 0) for ex in EXCHANGES)
total_main = st.session_state.user_data['main_balance']
total_usdt = total_main + total_usdt_in_exchanges

total_portfolio = 0
for ex, balances in st.session_state.user_data['balances'].items():
    for token, amount in balances.get('portfolio', {}).items():
        price = get_price(st.session_state.exchanges.get(ex), token) if st.session_state.exchanges.get(ex) else None
        if price:
            total_portfolio += amount * price

col1, col2, col3 = st.columns(3)
col1.metric("💰 Центральный кошелёк", f"{total_main:.2f} USDT")
col2.metric("🏦 USDT на биржах", f"{total_usdt_in_exchanges:.2f} USDT")
col3.metric("📦 Портфель (токены)", f"{total_portfolio:.2f} USDT")

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
    # Режим пока не реализован, всегда Демо

# ----- НАСТРОЙКИ АРБИТРАЖА (в разворачиваемом блоке) -----
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

# ---------- ВКЛАДКИ ----------
show_admin = is_admin(st.session_state.email)
tabs_list = ["📊 Dashboard", "📈 Графики", "🔄 Арбитраж", "📊 Статистика", "📈 Доходность", "💼 Балансы", "💰 Вывод", "📜 История", "👤 Кабинет", "💬 Чат"]
if show_admin:
    tabs_list.append("👑 Админ-панель")
tabs = st.tabs(tabs_list)

# TAB 0: Dashboard (текущие цены)
with tabs[0]:
    st.subheader("📊 Текущие цены на биржах")
    tokens = get_available_tokens()
    for asset in tokens[:5]:
        st.write(f"**{asset}**")
        cols = st.columns(len(EXCHANGES))
        for i, ex in enumerate(EXCHANGES):
            price = get_price(st.session_state.exchanges.get(ex), asset) if st.session_state.exchanges.get(ex) else None
            with cols[i]:
                if price:
                    st.metric(ex.upper(), f"${price:.2f}")
                else:
                    st.metric(ex.upper(), "❌")
        st.divider()

# TAB 1: Графики (японские свечи)
with tabs[1]:
    st.subheader("📈 Японские свечи")
    col_a, col_b = st.columns(2)
    sel_asset = col_a.selectbox("Актив", get_available_tokens())
    sel_ex = col_b.selectbox("Биржа", EXCHANGES)
    if st.button("Обновить график") or True:
        if st.session_state.exchanges and sel_ex in st.session_state.exchanges:
            try:
                ohlcv = st.session_state.exchanges[sel_ex].fetch_ohlcv(f"{sel_asset}/USDT", '1h', 100)
                df = pd.DataFrame(ohlcv, columns=['timestamp','open','high','low','close','volume'])
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                fig = go.Figure(data=[go.Candlestick(x=df['timestamp'], open=df['open'], high=df['high'], low=df['low'], close=df['close'])])
                fig.update_layout(title=f"{sel_asset}/USDT на {sel_ex.upper()}", template="plotly_dark", height=500)
                st.plotly_chart(fig, use_container_width=True)
                st.metric("Текущая цена", f"${df['close'].iloc[-1]:,.2f}")
            except:
                st.warning("Нет данных для графика")

# TAB 2: Арбитраж (ручной поиск и исполнение)
with tabs[2]:
    st.subheader("🔍 Ручной арбитраж")
    if st.button("🎯 НАЙТИ И ИСПОЛНИТЬ ЛУЧШУЮ СДЕЛКУ", use_container_width=True):
        with st.spinner("Поиск..."):
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

# TAB 3: Статистика по токенам
with tabs[3]:
    st.subheader("📊 Статистика сделок по токенам")
    token_stats = {}
    total_profit_all = 0
    for trade in st.session_state.user_data['history']:
        if trade.startswith("✅"):
            try:
                parts = trade.split("|")
                if len(parts) >= 3:
                    token = parts[1].strip()
                    profit = float(parts[3].split("+")[1].split()[0])
                    token_stats.setdefault(token, {'trades': 0, 'profit': 0})
                    token_stats[token]['trades'] += 1
                    token_stats[token]['profit'] += profit
                    total_profit_all += profit
            except:
                pass
    if token_stats:
        data = [{"Токен": t, "Сделок": d['trades'], "Прибыль": f"{d['profit']:.2f}", "% общ.": f"{d['profit']/total_profit_all*100:.1f}%"} for t, d in sorted(token_stats.items(), key=lambda x: x[1]['profit'], reverse=True)]
        st.dataframe(pd.DataFrame(data), use_container_width=True, hide_index=True)
        fig = px.pie(pd.DataFrame([{"Токен": t, "Прибыль": d['profit']} for t, d in token_stats.items()]), values='Прибыль', names='Токен', title="Доля прибыли")
        fig.update_layout(template="plotly_dark", height=450)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Нет данных")

# TAB 4: Доходность по периодам
with tabs[4]:
    st.subheader("📈 Прибыль по периодам")
    stats = st.session_state.user_data['stats']
    if stats:
        days = {k: v for k, v in stats.items() if len(k) == 10 and '-' in k}
        weeks = {k: v for k, v in stats.items() if 'W' in k}
        months = {k: v for k, v in stats.items() if len(k) == 7 and '-' in k and 'W' not in k}
        years = {k: v for k, v in stats.items() if len(k) == 4}
        if days:
            df_days = pd.DataFrame([{"Дата": k, "Прибыль": v} for k, v in sorted(days.items())])
            fig = px.bar(df_days, x="Дата", y="Прибыль", title="Прибыль по дням")
            fig.update_layout(template="plotly_dark", height=400)
            st.plotly_chart(fig, use_container_width=True)
        if weeks:
            df_weeks = pd.DataFrame([{"Неделя": k, "Прибыль": v} for k, v in sorted(weeks.items())])
            fig = px.bar(df_weeks, x="Неделя", y="Прибыль", title="Прибыль по неделям")
            fig.update_layout(template="plotly_dark", height=400)
            st.plotly_chart(fig, use_container_width=True)
        if months:
            df_months = pd.DataFrame([{"Месяц": k, "Прибыль": v} for k, v in sorted(months.items())])
            fig = px.bar(df_months, x="Месяц", y="Прибыль", title="Прибыль по месяцам")
            fig.update_layout(template="plotly_dark", height=400)
            st.plotly_chart(fig, use_container_width=True)
        if years:
            st.write("**Итог по годам:**")
            for y, p in sorted(years.items()):
                st.metric(y, f"+{p:.2f} USDT")
    else:
        st.info("Нет статистики")

# TAB 5: Балансы (управление USDT и токенами)
with tabs[5]:
    st.subheader("💼 Управление средствами")
    st.info("Сначала пополните центральный кошелёк в личном кабинете, затем переводите USDT на биржи.")
    for ex in EXCHANGES:
        with st.expander(f"### {ex.upper()}"):
            bal = st.session_state.user_data['balances'].get(ex, {})
            usdt_ex = bal.get('USDT', 0)
            st.metric("USDT на бирже", f"{usdt_ex:.2f}")
            
            # Перевести USDT с центрального кошелька на биржу
            col1, col2 = st.columns(2)
            with col1:
                transfer_in = st.number_input(f"Перевести USDT с ЦК на {ex.upper()}", min_value=0.0, step=10.0, key=f"transfer_in_{ex}")
                if st.button(f"➡️ Перевести на биржу", key=f"btn_in_{ex}"):
                    if transfer_in > 0:
                        ok, msg = transfer_usdt_to_exchange(ex, transfer_in)
                        if ok:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)
            with col2:
                transfer_out = st.number_input(f"Вернуть USDT с {ex.upper()} в ЦК", min_value=0.0, step=10.0, key=f"transfer_out_{ex}")
                if st.button(f"⬅️ Вернуть в ЦК", key=f"btn_out_{ex}"):
                    if transfer_out > 0:
                        ok, msg = transfer_usdt_from_exchange(ex, transfer_out)
                        if ok:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)
            
            st.write("**Покупка токенов за USDT на этой бирже**")
            token_to_buy = st.selectbox(f"Токен", get_available_tokens(), key=f"token_{ex}")
            usdt_to_spend = st.number_input(f"Сумма USDT для покупки {token_to_buy}", min_value=0.0, step=10.0, key=f"spend_{ex}")
            if st.button(f"💰 Купить {token_to_buy}", key=f"buy_{ex}"):
                if usdt_to_spend > 0:
                    ok, msg = buy_token_with_usdt(ex, token_to_buy, usdt_to_spend)
                    if ok:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
            
            st.write("**Продажа токенов на этой бирже**")
            token_to_sell = st.selectbox(f"Токен для продажи", get_available_tokens(), key=f"sell_token_{ex}")
            amount_to_sell = st.number_input(f"Количество {token_to_sell} для продажи", min_value=0.0, step=0.01, key=f"sell_amt_{ex}", format="%.8f")
            if st.button(f"💰 Продать {token_to_sell}", key=f"sell_{ex}"):
                if amount_to_sell > 0:
                    ok, msg = sell_token_to_usdt(ex, token_to_sell, amount_to_sell)
                    if ok:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
            
            st.write("**Текущий портфель токенов:**")
            portfolio = bal.get('portfolio', {})
            for token, amount in portfolio.items():
                if amount > 0:
                    price = get_price(st.session_state.exchanges.get(ex), token) if st.session_state.exchanges.get(ex) else None
                    value = amount * price if price else 0
                    st.write(f"{token}: {amount:.8f} ≈ ${value:.2f}")
            st.divider()

# TAB 6: Вывод средств (заявки на вывод с центрального кошелька)
with tabs[6]:
    st.subheader("💰 Вывод средств")
    st.write(f"**Доступно для вывода:** {st.session_state.user_data['withdrawable_balance']:.2f} USDT")
    weekday = datetime.now().strftime("%A")
    disabled = weekday not in ["Tuesday","Friday"]
    if disabled:
        st.warning("⏳ Вывод только по вторникам и пятницам")
    max_wd = st.session_state.user_data['withdrawable_balance']
    if max_wd >= 10:
        amt = st.number_input("Сумма вывода (USDT)", min_value=10.0, max_value=max_wd, step=10.0, disabled=disabled)
        if st.button("Запросить вывод", disabled=disabled) and amt and st.session_state.wallet_address:
            create_withdrawal_request(st.session_state.user_id, amt, st.session_state.wallet_address)
            st.session_state.user_data['withdrawable_balance'] -= amt
            save_user_data(st.session_state.user_id, st.session_state.user_data)
            st.success("Заявка отправлена")
            st.rerun()
    else:
        st.warning(f"Недостаточно средств (доступно {max_wd:.2f}, мин 10)")
    wallet_input = st.text_input("Адрес кошелька (USDT)", value=st.session_state.wallet_address)
    if st.button("Сохранить адрес"):
        st.session_state.wallet_address = wallet_input
        supabase.table('users').update({'wallet_address': wallet_input}).eq('email', st.session_state.email).execute()
        st.success("Сохранено")

# TAB 7: История сделок
with tabs[7]:
    st.subheader("📜 История сделок")
    if st.session_state.user_data['history']:
        for trade in reversed(st.session_state.user_data['history'][-50:]):
            st.write(trade)
        if st.button("Очистить историю"):
            st.session_state.user_data['history'] = []
            save_user_data(st.session_state.user_id, st.session_state.user_data)
            st.rerun()
    else:
        st.info("Нет сделок")

# TAB 8: Личный кабинет (пополнение центрального кошелька)
with tabs[8]:
    st.subheader("👤 Личный кабинет")
    st.write(f"**Имя:** {st.session_state.username}")
    st.write(f"**Email:** {st.session_state.email}")
    st.write(f"**Кошелёк для вывода:** {st.session_state.wallet_address if st.session_state.wallet_address else 'не указан'}")
    st.divider()
    colb1, colb2 = st.columns(2)
    colb1.metric("Центральный кошелёк (USDT)", f"{st.session_state.user_data['main_balance']:.2f}")
    colb2.metric("Прибыль (USDT)", f"{st.session_state.user_data['total_profit']:.2f}")
    st.divider()
    st.subheader("💰 Пополнение центрального кошелька")
    add_main = st.number_input("Сумма пополнения (USDT)", min_value=10.0, step=10.0)
    if st.button("Пополнить центральный кошелёк"):
        if add_main > 0:
            st.session_state.user_data['main_balance'] += add_main
            save_user_data(st.session_state.user_id, st.session_state.user_data)
            st.success(f"Центральный кошелёк пополнен на {add_main} USDT")
            st.rerun()
    st.info("После пополнения переводите USDT на биржи через вкладку «Балансы» и покупайте токены.")

# TAB 9: Чат
with tabs[9]:
    st.subheader("💬 Чат с поддержкой")
    if is_admin(st.session_state.email):
        msgs = get_messages(limit=100)
        for msg in msgs:
            uname = msg.get('user_name','Пользователь')
            uemail = msg.get('user_email','')
            st.markdown(f"**{uname}** ({uemail}) - {msg['created_at'][:16]}")
            st.write(msg['message'])
            if not msg.get('is_admin_reply',False):
                reply = st.text_input(f"Ответ", key=f"rep_{msg['id']}")
                if st.button("Отправить", key=f"send_{msg['id']}") and reply:
                    add_message(msg['user_id'], uemail, uname, reply, is_admin_reply=True, reply_to=msg['id'])
                    st.success("Ответ отправлен")
                    st.rerun()
            st.divider()
        with st.expander("📢 Объявление всем"):
            broadcast = st.text_area("Текст")
            if st.button("Отправить всем") and broadcast:
                for u in get_all_users_for_admin():
                    add_message(u['id'], u['email'], u['full_name'], f"[ОБЪЯВЛЕНИЕ] {broadcast}", is_admin_reply=True)
                st.success("Отправлено всем")
    else:
        user_msg = st.text_area("Ваше сообщение")
        if st.button("Отправить") and user_msg:
            add_message(st.session_state.user_id, st.session_state.email, st.session_state.username, user_msg)
            st.success("Сообщение отправлено")
            st.rerun()
        st.divider()
        st.write("История обращений")
        for msg in get_messages(user_id=st.session_state.user_id, limit=30):
            if msg.get('is_admin_reply'):
                st.info(f"📢 **Администратор:** {msg['message']} _({msg['created_at'][:16]})_")
            else:
                st.write(f"📤 **Вы:** {msg['message']} _({msg['created_at'][:16]})_")
        mark_messages_read(st.session_state.user_id)
        st.session_state.chat_unread = 0

# ---------- АДМИН-ПАНЕЛЬ ----------
if show_admin:
    with tabs[-1]:
        st.subheader("👑 Админ-панель")
        a1,a2,a3,a4,a5,a6 = st.tabs(["👥 Участники","📊 Токены","🔐 API ключи","📜 Все сделки","💰 Заявки","⚙ Сброс"])
        with a1:
            users = get_all_users_for_admin()
            if users:
                df = pd.DataFrame([{
                    "Email":u['email'], "Имя":u['full_name'], "Статус":u['registration_status'],
                    "Баланс ЦК":f"${u.get('main_balance',0):.2f}", "Прибыль":f"${u.get('total_profit',0):.2f}",
                    "Сделок":u.get('trade_count',0)
                } for u in users])
                st.dataframe(df, use_container_width=True, hide_index=True)
                emails = {u['email']:u['id'] for u in users}
                sel = st.selectbox("Выберите пользователя", list(emails.keys()))
                if sel:
                    uid = emails[sel]
                    u = supabase.table('users').select('registration_status').eq('id',uid).execute().data[0]
                    if u['registration_status'] == 'pending':
                        if st.button("✅ Одобрить"):
                            update_user_status(uid,'approved',st.session_state.email)
                            st.rerun()
                    elif u['registration_status'] == 'approved':
                        if st.button("🔴 Заблокировать"):
                            update_user_status(uid,'rejected',st.session_state.email)
                            st.rerun()
        with a2:
            cur_tokens = get_available_tokens()
            new_tokens = st.text_input("Список токенов через запятую", value=", ".join(cur_tokens))
            if st.button("Сохранить токены"):
                tlist = [t.strip().upper() for t in new_tokens.split(",") if t.strip()]
                if tlist:
                    set_available_tokens(tlist)
                    st.rerun()
        with a3:
            api_keys = get_all_api_keys()
            for ex in EXCHANGES:
                with st.expander(f"🔑 {ex.upper()}"):
                    cur = api_keys.get(ex,{})
                    cur_api = decrypt_api_key(cur.get('api_key',''))
                    cur_sec = decrypt_api_key(cur.get('secret_key',''))
                    new_api = st.text_input(f"API Key", value=cur_api, type="password", key=f"api_{ex}")
                    new_sec = st.text_input(f"Secret Key", value=cur_sec, type="password", key=f"sec_{ex}")
                    col1,col2 = st.columns(2)
                    if col1.button(f"Проверить {ex.upper()}", key=f"test_{ex}"):
                        if new_api and new_sec:
                            try:
                                ex_cls = getattr(ccxt, ex)
                                test_ex = ex_cls({'apiKey':new_api, 'secret':new_sec, 'enableRateLimit':True})
                                test_ex.fetch_balance()
                                st.success("Ключи действительны")
                            except Exception as e:
                                st.error(f"Ошибка: {str(e)[:100]}")
                    if col2.button(f"Сохранить {ex.upper()}", key=f"save_{ex}"):
                        save_api_key(ex,new_api,new_sec,st.session_state.email)
                        st.session_state.api_keys = get_all_api_keys()
                        st.success("Сохранено")
                        st.rerun()
        with a4:
            trades = get_all_trades(200)
            if trades:
                df = pd.DataFrame([{"Пользователь":t.get('users',{}).get('email',''), "Токен":t['asset'], "Прибыль":f"${t['profit']:.2f}", "Время":t['trade_time']} for t in trades])
                st.dataframe(df, use_container_width=True, hide_index=True)
        with a5:
            pend = get_pending_withdrawals()
            for w in pend:
                st.write(f"{w.get('users',{}).get('email','')} — {w['amount']} USDT (клиент получит {w['user_receives']:.2f})")
                if st.button(f"Выполнить", key=f"comp_{w['id']}"):
                    update_withdrawal_status(w['id'], 'completed', st.session_state.email)
                    st.rerun()
        with a6:
            if st.button("🔄 Сбросить данные текущего пользователя (обнулить всё)"):
                st.session_state.user_data['main_balance'] = 0.0
                st.session_state.user_data['balances'] = {ex: {"USDT": 0.0, "portfolio": {t: 0.0 for t in TOKENS}} for ex in EXCHANGES}
                st.session_state.user_data['history'] = []
                st.session_state.user_data['stats'] = {}
                st.session_state.user_data['total_profit'] = 0
                st.session_state.user_data['trade_count'] = 0
                st.session_state.user_data['withdrawable_balance'] = 0
                st.session_state.user_data['total_admin_fee_paid'] = 0
                save_user_data(st.session_state.user_id, st.session_state.user_data)
                st.success("Данные сброшены")
                st.rerun()

st.caption(f"🚀 Настройки: комиссия {st.session_state.fee_percent}%, мин. прибыль {st.session_state.min_profit_usdt} USDT, мин. сделка {st.session_state.min_trade_usdt} USDT, макс. сделка {st.session_state.max_trade_usdt} USDT | Авто-интервал {st.session_state.scan_interval} сек")
