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

st.set_page_config(page_title="Арбитражный бот | Авто-сделки", layout="wide", page_icon="🔄", initial_sidebar_state="collapsed")

SUPABASE_URL = st.secrets.get("SUPABASE_URL")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY")
if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("❌ Нет SUPABASE_URL / SUPABASE_KEY в Secrets")
    st.stop()
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

TELEGRAM_BOT_TOKEN = st.secrets.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = st.secrets.get("TELEGRAM_CHAT_ID", "")
def send_telegram(msg):
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        try:
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                          json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"}, timeout=5)
        except:
            pass

st.markdown("""
<style>
    .stApp { background: linear-gradient(180deg, #001a33 0%, #003087 100%) !important; color: white; }
    .main-header { font-size: 28px; font-weight: bold; color: #00D4FF; text-align: center; margin-bottom: 0; }
    .user-info { font-size: 14px; color: #aaaaff; margin-top: 5px; }
    .status-indicator { display: inline-block; width: 14px; height: 14px; border-radius: 50%; margin-right: 6px; }
    .status-running { background-color: #00FF88; box-shadow: 0 0 8px #00FF88; animation: pulse 1.5s infinite; }
    .status-stopped { background-color: #FF4444; box-shadow: 0 0 8px #FF4444; }
    @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.4; } 100% { opacity: 1; } }
    .stButton>button { border-radius: 30px; height: 42px; font-weight: bold; }
    .green-button button { background-color: #00AA44 !important; color: white !important; }
    .yellow-button button { background-color: #CC8800 !important; color: white !important; }
    .red-button button { background-color: #CC3333 !important; color: white !important; }
    .token-card { background: rgba(0,100,200,0.2); border-radius: 10px; padding: 8px; margin: 4px; text-align: center; }
    .profit-card { background: rgba(0,255,100,0.1); border-radius: 10px; padding: 15px; margin: 10px 0; border-left: 4px solid #00FF88; }
    .stTabs [data-baseweb="tab-list"] { flex-wrap: wrap !important; gap: 4px; }
</style>
""", unsafe_allow_html=True)

EXCHANGES = ["kucoin", "okx", "hitbtc"]
DEFAULT_ASSETS = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "LINK", "SUI", "HYPE", "TON"]
ADMIN_EMAILS = ["cb777899@gmail.com", "admin@arbitrage.com"]

MIN_SPREAD_PERCENT = 0.001
FEE_PERCENT = 0.01
SLIPPAGE_PERCENT = 0.01
TRADE_PERCENT = 50
MIN_TRADE_USDT = 1.0          # снижено с 5 до 1
SCAN_INTERVAL = 5

def is_admin(email):
    return email in ADMIN_EMAILS

# ---------- ФУНКЦИИ SUPABASE (без изменений) ----------
def get_user_by_email(email):
    res = supabase.table('users').select('*').eq('email', email).execute()
    return res.data[0] if res.data else None

def create_user(email, pwd_hash, full_name, country, city, phone, wallet):
    empty_balances = {ex: {"USDT": 0.0, "portfolio": {asset: 0.0 for asset in DEFAULT_ASSETS}} for ex in EXCHANGES}
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
    send_telegram(f"🆕 Новый пользователь: {full_name} ({email})")
    return res.data[0]['id'] if res.data else None

def load_balances(user_id):
    res = supabase.table('users').select('demo_balances').eq('id', user_id).execute()
    if res.data and res.data[0].get('demo_balances'):
        return json.loads(res.data[0]['demo_balances'])
    else:
        return {ex: {"USDT": 0.0, "portfolio": {asset: 0.0 for asset in DEFAULT_ASSETS}} for ex in EXCHANGES}

def save_balances(user_id, balances):
    supabase.table('users').update({'demo_balances': json.dumps(balances)}).eq('id', user_id).execute()

def load_history(user_id):
    res = supabase.table('users').select('demo_history').eq('id', user_id).execute()
    if res.data and res.data[0].get('demo_history'):
        return json.loads(res.data[0]['demo_history'])
    return []

def save_history(user_id, history):
    supabase.table('users').update({'demo_history': json.dumps(history[-500:])}).eq('id', user_id).execute()

def load_stats(user_id):
    res = supabase.table('users').select('demo_stats').eq('id', user_id).execute()
    if res.data and res.data[0].get('demo_stats'):
        return json.loads(res.data[0]['demo_stats'])
    return {}

def save_stats(user_id, stats):
    supabase.table('users').update({'demo_stats': json.dumps(stats)}).eq('id', user_id).execute()

def update_stats(user_id, profit):
    stats = load_stats(user_id)
    now = datetime.now()
    day_key = now.strftime("%Y-%m-%d")
    week_key = f"{now.year}-W{now.isocalendar()[1]}"
    month_key = now.strftime("%Y-%m")
    year_key = now.strftime("%Y")
    stats[day_key] = stats.get(day_key, 0) + profit
    stats[week_key] = stats.get(week_key, 0) + profit
    stats[month_key] = stats.get(month_key, 0) + profit
    stats[year_key] = stats.get(year_key, 0) + profit
    save_stats(user_id, stats)

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
    data = {
        'user_id': user_id, 'amount': amount, 'admin_fee': admin_fee,
        'user_receives': amount - admin_fee, 'wallet_address': wallet, 'status': 'pending'
    }
    supabase.table('withdrawals').insert(data).execute()

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
    return tokens if tokens else DEFAULT_ASSETS

def set_available_tokens(tokens):
    set_config('tokens', tokens)

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

@st.cache_resource
def init_exchanges():
    exchanges, status = {}, {}
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

# ---------- БАЛАНСЫ (с поддержкой уменьшения) ----------
def get_balance(exchange_name, asset):
    bal = st.session_state.user_balances.get(exchange_name, {})
    if asset == 'USDT':
        return bal.get('USDT', 0.0)
    else:
        return bal.get('portfolio', {}).get(asset, 0.0)

def update_balance(exchange_name, asset, delta):
    if exchange_name not in st.session_state.user_balances:
        st.session_state.user_balances[exchange_name] = {"USDT": 0.0, "portfolio": {a: 0.0 for a in DEFAULT_ASSETS}}
    if 'USDT' not in st.session_state.user_balances[exchange_name]:
        st.session_state.user_balances[exchange_name]['USDT'] = 0.0
    if 'portfolio' not in st.session_state.user_balances[exchange_name]:
        st.session_state.user_balances[exchange_name]['portfolio'] = {a: 0.0 for a in DEFAULT_ASSETS}
    if asset == 'USDT':
        st.session_state.user_balances[exchange_name]['USDT'] += delta
    else:
        if asset not in st.session_state.user_balances[exchange_name]['portfolio']:
            st.session_state.user_balances[exchange_name]['portfolio'][asset] = 0.0
        st.session_state.user_balances[exchange_name]['portfolio'][asset] += delta
    save_balances(st.session_state.user_id, st.session_state.user_balances)

# ---------- АРБИТРАЖ С ДЕТАЛЬНЫМ ЛОГИРОВАНИЕМ ----------
def find_opportunities():
    opportunities = []
    if not st.session_state.exchanges:
        return opportunities
    tokens = get_available_tokens()
    prices = {}
    for ex_name, ex in st.session_state.exchanges.items():
        prices[ex_name] = {}
        for asset in tokens:
            price = get_price(ex, asset)
            if price:
                prices[ex_name][asset] = price
    exchange_names = list(prices.keys())
    for buy_ex in exchange_names:
        for sell_ex in exchange_names:
            if buy_ex == sell_ex:
                continue
            for asset in tokens:
                if asset not in prices[buy_ex] or asset not in prices[sell_ex]:
                    continue
                buy_price = prices[buy_ex][asset]
                sell_price = prices[sell_ex][asset]
                if sell_price <= buy_price:
                    continue
                spread_pct = (sell_price - buy_price) / buy_price * 100
                net_spread = spread_pct - FEE_PERCENT - SLIPPAGE_PERCENT
                if net_spread <= MIN_SPREAD_PERCENT:
                    continue
                profit_before = sell_price - buy_price - (buy_price * (FEE_PERCENT/100) + sell_price * (FEE_PERCENT/100))
                if profit_before <= 0:
                    continue
                opportunities.append({
                    'asset': asset,
                    'buy_ex': buy_ex,
                    'sell_ex': sell_ex,
                    'buy_price': buy_price,
                    'sell_price': sell_price,
                    'profit': profit_before
                })
    opportunities.sort(key=lambda x: x['profit'], reverse=True)
    return opportunities

def execute_trade(opp, log_list):
    buy_ex = opp['buy_ex']
    sell_ex = opp['sell_ex']
    asset = opp['asset']
    buy_price = opp['buy_price']
    sell_price = opp['sell_price']

    usdt_buy = get_balance(buy_ex, 'USDT')
    token_sell = get_balance(sell_ex, asset)
    token_sell_value = token_sell * sell_price

    # Рассчитываем сумму сделки
    trade_usdt = min(usdt_buy * (TRADE_PERCENT / 100.0), token_sell_value * (TRADE_PERCENT / 100.0))
    log_list.append(f"🔄 {asset} {buy_ex}→{sell_ex}: USDT на {buy_ex}={usdt_buy:.2f}, токенов {asset} на {sell_ex}={token_sell:.6f} (стоимость {token_sell_value:.2f}), trade_usdt={trade_usdt:.2f}")

    if trade_usdt < MIN_TRADE_USDT:
        log_list.append(f"❌ {asset} {buy_ex}→{sell_ex}: сумма {trade_usdt:.2f} USDT < {MIN_TRADE_USDT}")
        return None
    amount = trade_usdt / buy_price
    buy_cost = amount * buy_price
    sell_proceeds = amount * sell_price

    if usdt_buy < buy_cost:
        log_list.append(f"❌ {asset}: не хватает USDT на {buy_ex} (нужно {buy_cost:.2f}, есть {usdt_buy:.2f})")
        return None
    if token_sell < amount:
        log_list.append(f"❌ {asset}: не хватает токенов на {sell_ex} (нужно {amount:.4f}, есть {token_sell:.4f})")
        return None

    # Исполняем сделку
    update_balance(buy_ex, 'USDT', -buy_cost)
    update_balance(buy_ex, asset, +amount)
    update_balance(sell_ex, asset, -amount)
    update_balance(sell_ex, 'USDT', +sell_proceeds)

    real_profit = sell_proceeds - buy_cost
    st.session_state.total_profit += real_profit
    st.session_state.trade_count += 1
    history_entry = f"✅ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | {asset} | {buy_ex}→{sell_ex} | {amount:.6f} {asset} | +{real_profit:.2f} USDT"
    st.session_state.user_history.append(history_entry)
    save_history(st.session_state.user_id, st.session_state.user_history)
    update_stats(st.session_state.user_id, real_profit)
    add_trade(st.session_state.user_id, st.session_state.current_mode, asset, amount, real_profit, buy_ex, sell_ex)
    supabase.table('users').update({
        'total_profit': st.session_state.total_profit,
        'trade_count': st.session_state.trade_count
    }).eq('id', st.session_state.user_id).execute()
    log_list.append(f"✅ {asset} {buy_ex}→{sell_ex} | {trade_usdt:.2f} USDT | +{real_profit:.2f} USDT")
    return real_profit

# ---------- ФОНОВОЙ ПОТОК ----------
def background_arbitrage_loop():
    while True:
        try:
            if st.session_state.get('bot_running', False):
                opps = find_opportunities()
                if opps:
                    best = opps[0]
                    st.session_state.auto_log.append(f"🔍 Найдено {len(opps)} возможностей, лучшая: {best['asset']} {best['buy_ex']}→{best['sell_ex']} прибыль {best['profit']:.4f} USDT")
                    if best['profit'] > 0:
                        execute_trade(best, st.session_state.auto_log)
                else:
                    st.session_state.auto_log.append("ℹ️ Нет арбитражных возможностей")
                time.sleep(SCAN_INTERVAL)
            else:
                time.sleep(5)
        except Exception as e:
            st.session_state.auto_log.append(f"⚠️ Ошибка в потоке: {e}")
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
    st.session_state.bot_running = load_bot_status()
    st.session_state.exchange_status = {}
    st.session_state.current_mode = "Демо"
    st.session_state.user_id = None
    st.session_state.api_keys = {}
    st.session_state.chat_unread = 0
    st.session_state.user_balances = {}
    st.session_state.user_history = []
    st.session_state.user_stats = {}
    st.session_state.total_profit = 0
    st.session_state.trade_count = 0
    st.session_state.total_admin_fee_paid = 0
    st.session_state.withdrawable_balance = 0
    st.session_state.auto_log = []

if st.session_state.exchanges is None:
    with st.spinner("Подключение к биржам..."):
        st.session_state.exchanges, st.session_state.exchange_status = init_exchanges()
        st.session_state.api_keys = get_all_api_keys()

# ---------- РЕГИСТРАЦИЯ / ВХОД ----------
if not st.session_state.logged_in:
    st.markdown('<h1 class="main-header">🔄 Арбитражный бот | Авто-сделки</h1>', unsafe_allow_html=True)
    tab_reg, tab_login = st.tabs(["📝 Регистрация","🔑 Вход"])
    with tab_reg:
        with st.form("register_form"):
            username = st.text_input("Имя")
            email = st.text_input("Email")
            country = st.text_input("Страна")
            city = st.text_input("Город")
            phone = st.text_input("Телефон")
            wallet = st.text_input("Адрес USDT")
            pwd = st.text_input("Пароль",type="password")
            pwd2 = st.text_input("Повтор пароля",type="password")
            if st.form_submit_button("Зарегистрироваться", use_container_width=True):
                if username and email and wallet and pwd and pwd==pwd2:
                    if get_user_by_email(email):
                        st.error("Email уже существует")
                    else:
                        create_user(email,pwd,username,country,city,phone,wallet)
                        st.success("Регистрация успешна! Теперь вы можете войти.")
                else:
                    st.error("Заполните все поля или пароли не совпадают")
    with tab_login:
        with st.form("login_form"):
            email = st.text_input("Email")
            pwd = st.text_input("Пароль",type="password")
            if st.form_submit_button("Войти", use_container_width=True):
                user = get_user_by_email(email)
                if user and user['password_hash'] == pwd:
                    if user['registration_status'] == 'approved':
                        st.session_state.logged_in = True
                        st.session_state.username = user['full_name']
                        st.session_state.email = user['email']
                        st.session_state.wallet_address = user.get('wallet_address','')
                        st.session_state.user_id = user['id']
                        st.session_state.user_balances = load_balances(user['id'])
                        st.session_state.user_history = load_history(user['id'])
                        st.session_state.user_stats = load_stats(user['id'])
                        st.session_state.total_profit = user.get('total_profit', 0)
                        st.session_state.trade_count = user.get('trade_count', 0)
                        st.session_state.total_admin_fee_paid = user.get('total_admin_fee_paid', 0)
                        st.session_state.withdrawable_balance = user.get('withdrawable_balance', 0)
                        st.session_state.chat_unread = get_unread_count(user['id'])
                        st.success(f"Добро пожаловать, {st.session_state.username}!")
                        st.rerun()
                    else:
                        st.error("Доступ запрещён")
                else:
                    st.error("Неверный email или пароль")
    st.stop()

# ---------- ОСНОВНОЙ ИНТЕРФЕЙС ----------
if st.session_state.user_id:
    save_balances(st.session_state.user_id, st.session_state.user_balances)

col_logo, col_status, col_logout = st.columns([3,1,1])
with col_logo:
    st.markdown('<h1 class="main-header">🔄 Арбитражный бот | Авто-сделки</h1>', unsafe_allow_html=True)
with col_status:
    if st.session_state.bot_running:
        st.markdown('<div><span class="status-indicator status-running"></span> <b>АВТО-СДЕЛКИ АКТИВНЫ</b></div>', unsafe_allow_html=True)
    else:
        st.markdown('<div><span class="status-indicator status-stopped"></span> <b>ОСТАНОВЛЕН</b></div>', unsafe_allow_html=True)
with col_logout:
    if st.button("🚪 Выйти"):
        save_balances(st.session_state.user_id, st.session_state.user_balances)
        save_history(st.session_state.user_id, st.session_state.user_history)
        st.session_state.logged_in = False
        st.session_state.bot_running = False
        save_bot_status(False)
        st.rerun()

st.markdown(f'<div class="user-info">👤 {st.session_state.username} | 📧 {st.session_state.email}</div>', unsafe_allow_html=True)
connected = [ex.upper() for ex,sts in st.session_state.exchange_status.items() if sts=="connected"]
st.write(f"🔌 **Биржи:** {', '.join(connected)}")
st.write(f"🪙 **Токены:** {', '.join(get_available_tokens())}")
st.divider()

total_usdt = sum(st.session_state.user_balances.get(ex, {}).get('USDT', 0) for ex in EXCHANGES)
total_portfolio = 0
for ex, balances in st.session_state.user_balances.items():
    for asset, amount in balances.get('portfolio', {}).items():
        price = get_price(st.session_state.exchanges.get(ex), asset) if st.session_state.exchanges.get(ex) else None
        if price:
            total_portfolio += amount * price
col1,col2,col3 = st.columns(3)
col1.metric("💰 Всего USDT", f"{total_usdt:.2f}")
col2.metric("📦 Стоимость портфеля", f"{total_portfolio:.2f}")
col3.metric("📊 Всего сделок", st.session_state.trade_count)

c1,c2,c3 = st.columns(3)
with c1:
    st.markdown('<div class="green-button">', unsafe_allow_html=True)
    if st.button("▶ СТАРТ", use_container_width=True):
        st.session_state.bot_running = True
        save_bot_status(True)
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)
with c2:
    st.markdown('<div class="red-button">', unsafe_allow_html=True)
    if st.button("⏹ СТОП", use_container_width=True):
        st.session_state.bot_running = False
        save_bot_status(False)
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)
with c3:
    new_mode = st.selectbox("Режим",["Демо","Реальный"], index=0)
    st.session_state.current_mode = "Демо"

if st.button("🔄 Обновить данные", use_container_width=True):
    st.rerun()

with st.expander("📋 Лог авто-торговли (последние 20 событий, сохраняется между сессиями)"):
    if st.session_state.auto_log:
        for log in st.session_state.auto_log[-20:]:
            st.text(log)
    else:
        st.info("Нет событий. Запустите бота (СТАРТ).")

show_admin = is_admin(st.session_state.email)
tabs_list = ["📊 Dashboard", "📈 Графики", "🔄 Арбитраж", "📊 Статистика", "📈 Доходность", "💼 Балансы", "💰 Вывод", "📜 История", "👤 Кабинет", "💬 Чат"]
if show_admin:
    tabs_list.append("👑 Админ-панель")
tabs = st.tabs(tabs_list)

# TAB 0: Dashboard
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
    if st.session_state.bot_running:
        st.info(f"🟢 Бот сканирует **{len(tokens)}** токенов на **{len(connected)}** биржах")

# TAB 1: Графики (упрощён)
with tabs[1]:
    st.subheader("📈 Японские свечи")
    col_a, col_b = st.columns(2)
    sel_asset = col_a.selectbox("Актив", get_available_tokens())
    sel_ex = col_b.selectbox("Биржа", EXCHANGES)
    if st.button("Обновить график"):
        st.cache_data.clear()
        st.rerun()
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
            st.warning("Нет данных")

# TAB 2: Арбитраж
with tabs[2]:
    st.subheader("🔍 Арбитражные возможности")
    if st.button("🔄 Обновить", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    opps = find_opportunities()
    if opps:
        st.success(f"Найдено {len(opps)} возможностей")
        for opp in opps[:10]:
            st.info(f"🎯 {opp['asset']}: купить на {opp['buy_ex'].upper()} ${opp['buy_price']:.2f} → продать на {opp['sell_ex'].upper()} ${opp['sell_price']:.2f} | чистая прибыль: {opp['profit']:.4f} USDT")
    else:
        st.info("Арбитражных возможностей не найдено")

# TAB 3: Статистика по токенам
with tabs[3]:
    st.subheader("📊 Статистика сделок по токенам")
    token_stats = {}
    total_profit_all = 0
    for trade in st.session_state.user_history:
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

# TAB 4: Доходность
with tabs[4]:
    st.subheader("📈 Прибыль по периодам")
    stats = st.session_state.user_stats
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

# TAB 5: Балансы (с возможностью добавлять и вычитать)
with tabs[5]:
    st.subheader("💼 Управление балансами по биржам")
    st.info("Здесь вы можете вручную добавлять или вычитать USDT и токены на каждой бирже.")
    for ex in EXCHANGES:
        with st.expander(f"### {ex.upper()}"):
            bal = st.session_state.user_balances.get(ex, {})
            usdt = bal.get('USDT', 0.0)
            st.metric("USDT", f"{usdt:.2f}")
            portfolio = bal.get('portfolio', {})
            st.write("**Текущий портфель токенов:**")
            for asset, amount in portfolio.items():
                price = get_price(st.session_state.exchanges.get(ex), asset) if st.session_state.exchanges.get(ex) else None
                value = amount * price if price else 0
                st.write(f"{asset}: {amount:.6f} ≈ ${value:.2f}")
            # Управление USDT
            st.write("**Изменить USDT:**")
            col_usdt1, col_usdt2, col_usdt3 = st.columns([2,1,1])
            with col_usdt1:
                usdt_amount = st.number_input(f"Сумма USDT", min_value=0.0, step=10.0, key=f"usdt_amt_{ex}", format="%.2f")
            with col_usdt2:
                if st.button(f"➕ Добавить USDT", key=f"add_usdt_{ex}"):
                    if usdt_amount > 0:
                        update_balance(ex, 'USDT', usdt_amount)
                        st.success(f"Добавлено {usdt_amount} USDT на биржу {ex.upper()}")
                        st.rerun()
            with col_usdt3:
                if st.button(f"➖ Вычесть USDT", key=f"sub_usdt_{ex}"):
                    if usdt_amount > 0 and usdt >= usdt_amount:
                        update_balance(ex, 'USDT', -usdt_amount)
                        st.success(f"Вычтено {usdt_amount} USDT с биржи {ex.upper()}")
                        st.rerun()
                    elif usdt_amount > 0 and usdt < usdt_amount:
                        st.error(f"Недостаточно USDT на бирже {ex.upper()} (доступно {usdt:.2f})")
            # Управление токенами
            st.write("**Изменить токены:**")
            cols = st.columns(3)
            for i, asset in enumerate(get_available_tokens()):
                with cols[i % 3]:
                    current_amount = portfolio.get(asset, 0.0)
                    st.write(f"**{asset}:** {current_amount:.6f}")
                    amount = st.number_input(f"Количество {asset}", min_value=0.0, step=0.01, key=f"amt_{ex}_{asset}", format="%.6f")
                    col_add, col_sub = st.columns(2)
                    with col_add:
                        if st.button(f"➕ Добавить", key=f"add_{ex}_{asset}"):
                            if amount > 0:
                                update_balance(ex, asset, amount)
                                st.success(f"Добавлено {amount} {asset} на биржу {ex.upper()}")
                                st.rerun()
                    with col_sub:
                        if st.button(f"➖ Вычесть", key=f"sub_{ex}_{asset}"):
                            if amount > 0 and current_amount >= amount:
                                update_balance(ex, asset, -amount)
                                st.success(f"Вычтено {amount} {asset} с биржи {ex.upper()}")
                                st.rerun()
                            elif amount > 0 and current_amount < amount:
                                st.error(f"Недостаточно {asset} на бирже {ex.upper()} (доступно {current_amount:.6f})")
            st.divider()

# TAB 6: Вывод
with tabs[6]:
    st.subheader("💰 Вывод средств")
    st.write(f"**Доступно для вывода:** {st.session_state.withdrawable_balance:.2f} USDT")
    weekday = datetime.now().strftime("%A")
    disabled = weekday not in ["Tuesday","Friday"]
    if disabled:
        st.warning("⏳ Вывод только по вторникам и пятницам")
    max_wd = st.session_state.withdrawable_balance
    if max_wd >= 10:
        amt = st.number_input("Сумма вывода (USDT)", min_value=10.0, max_value=max_wd, step=10.0, disabled=disabled)
        if st.button("Запросить вывод", disabled=disabled) and amt and st.session_state.wallet_address:
            create_withdrawal_request(st.session_state.user_id, amt, st.session_state.wallet_address)
            st.session_state.withdrawable_balance -= amt
            supabase.table('users').update({'withdrawable_balance': st.session_state.withdrawable_balance}).eq('id', st.session_state.user_id).execute()
            st.success("Заявка отправлена")
            st.rerun()
    else:
        st.warning(f"Недостаточно средств (доступно {max_wd:.2f}, мин 10)")
    wallet_input = st.text_input("Адрес кошелька (USDT)", value=st.session_state.wallet_address)
    if st.button("Сохранить адрес"):
        st.session_state.wallet_address = wallet_input
        supabase.table('users').update({'wallet_address': wallet_input}).eq('email', st.session_state.email).execute()
        st.success("Сохранено")

# TAB 7: История
with tabs[7]:
    st.subheader("📜 История сделок")
    if st.session_state.user_history:
        for trade in reversed(st.session_state.user_history[-50:]):
            st.write(trade)
        if st.button("Очистить историю"):
            st.session_state.user_history = []
            save_history(st.session_state.user_id, [])
            st.rerun()
    else:
        st.info("Нет сделок")

# TAB 8: Личный кабинет
with tabs[8]:
    st.subheader("👤 Личный кабинет")
    st.write(f"**Имя:** {st.session_state.username}")
    st.write(f"**Email:** {st.session_state.email}")
    st.write(f"**Кошелёк:** {st.session_state.wallet_address if st.session_state.wallet_address else 'не указан'}")
    st.divider()
    colb1, colb2 = st.columns(2)
    colb1.metric("Общая прибыль (USDT)", f"{st.session_state.total_profit:.2f}")
    colb2.metric("Всего сделок", st.session_state.trade_count)
    st.divider()
    if st.button("Пополнить демо-счёт (добавить 1000 USDT на первую биржу)"):
        first_ex = EXCHANGES[0]
        update_balance(first_ex, 'USDT', 1000)
        st.success(f"Добавлено 1000 USDT на биржу {first_ex.upper()}")
        st.rerun()

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

if show_admin:
    with tabs[-1]:
        st.subheader("👑 Админ-панель")
        a1,a2,a3,a4,a5,a6 = st.tabs(["👥 Участники","📊 Токены","🔐 API ключи","📜 Все сделки","💰 Заявки","⚙ Настройки"])
        with a1:
            users = get_all_users_for_admin()
            if users:
                df = pd.DataFrame([{
                    "Email":u['email'], "Имя":u['full_name'], "Статус":u['registration_status'],
                    "Прибыль":f"${u.get('total_profit',0):.2f}", "Сделок":u.get('trade_count',0)
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
            st.write("Настройки арбитража")
            new_min_trade = st.number_input("Минимальная сумма сделки (USDT)", min_value=0.5, value=MIN_TRADE_USDT, step=0.5)
            new_trade_percent = st.slider("Процент от баланса для сделки (%)", 10, 100, TRADE_PERCENT, 5)
            if st.button("Сохранить настройки"):
                # Здесь можно сохранить в config
                st.session_state.temp_min_trade = new_min_trade
                st.session_state.temp_trade_percent = new_trade_percent
                st.success("Настройки сохранены (требуется перезапуск бота)")
                st.rerun()

st.caption(f"🚀 Сканируется {len(get_available_tokens())} токенов на {len(connected)} биржах | Интервал: {SCAN_INTERVAL} сек | Режим: {st.session_state.current_mode}")
