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

st.set_page_config(page_title="Арбитраж PRO | Финальная версия", layout="wide", page_icon="🚀", initial_sidebar_state="collapsed")

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
</style>
""", unsafe_allow_html=True)

# ---------- НАСТРОЙКИ ----------
EXCHANGES = ["kucoin", "okx", "hitbtc"]
DEFAULT_ASSETS = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "LINK", "SUI", "HYPE", "TON"]

DEMO_USDT_PER_EXCHANGE = 125.0
# НОВЫЙ ПОРТФЕЛЬ — стоимость каждого токена ~125 USDT при текущих ценах
INITIAL_PORTFOLIO = {
    "BTC": 0.0016,   # ~125 USDT
    "ETH": 0.054,    # ~125 USDT
    "SOL": 1.48,     # ~125 USDT
    "BNB": 0.20,     # ~125 USDT
    "XRP": 89.0,     # ~125 USDT
    "ADA": 500.0,    # ~125 USDT
    "AVAX": 1.35,    # ~125 USDT
    "LINK": 1.35,    # ~125 USDT
    "SUI": 135.0,    # ~125 USDT
    "HYPE": 3.07,    # ~125 USDT
    "TON": 94.0      # ~125 USDT
}

ADMIN_EMAILS = ["cb777899@gmail.com", "admin@arbitrage.com"]

MIN_SPREAD_PERCENT = 0.001
FEE_PERCENT = 0.01
SLIPPAGE_PERCENT = 0.01
TRADE_PERCENT = 50          # 50% от доступных средств
MIN_TRADE_USDT = 5.0
SCAN_INTERVAL = 5

def is_admin(email):
    return email in ADMIN_EMAILS

# ---------- ФУНКЦИИ ДЛЯ СБРОСА БАЛАНСОВ ----------
def reset_demo_balances_to_target(user_id):
    target_balances = {ex: {"USDT": DEMO_USDT_PER_EXCHANGE, "portfolio": INITIAL_PORTFOLIO.copy()} for ex in EXCHANGES}
    supabase.table('users').update({
        'demo_balances': json.dumps(target_balances),
        'demo_history': json.dumps([]),
        'demo_stats': json.dumps({}),
        'total_profit': 0,
        'trade_count': 0,
        'withdrawable_balance': 0,
        'total_admin_fee_paid': 0
    }).eq('id', user_id).execute()
    return target_balances

# ---------- SUPABASE ФУНКЦИИ ----------
def get_user_by_email(email):
    res = supabase.table('users').select('*').eq('email', email).execute()
    return res.data[0] if res.data else None

def create_user(email, pwd_hash, full_name, country, city, phone, wallet):
    initial_balances = {ex: {"USDT": DEMO_USDT_PER_EXCHANGE, "portfolio": INITIAL_PORTFOLIO.copy()} for ex in EXCHANGES}
    data = {
        'email': email, 'password_hash': pwd_hash, 'full_name': full_name,
        'country': country, 'city': city, 'phone': phone, 'wallet_address': wallet,
        'registration_status': 'approved',
        'trade_balance': 0, 'withdrawable_balance': 0, 'total_profit': 0, 'trade_count': 0, 'total_admin_fee_paid': 0,
        'demo_balances': json.dumps(initial_balances),
        'demo_history': json.dumps([]),
        'demo_stats': json.dumps({})
    }
    res = supabase.table('users').insert(data).execute()
    send_telegram(f"🆕 Новый пользователь: {full_name} ({email})")
    return res.data[0]['id'] if res.data else None

def load_demo_balances(user_id):
    res = supabase.table('users').select('demo_balances').eq('id', user_id).execute()
    if res.data and res.data[0].get('demo_balances'):
        return json.loads(res.data[0]['demo_balances'])
    else:
        return {ex: {"USDT": DEMO_USDT_PER_EXCHANGE, "portfolio": INITIAL_PORTFOLIO.copy()} for ex in EXCHANGES}

def save_demo_balances(user_id, balances):
    supabase.table('users').update({'demo_balances': json.dumps(balances)}).eq('id', user_id).execute()

def load_demo_history(user_id):
    res = supabase.table('users').select('demo_history').eq('id', user_id).execute()
    if res.data and res.data[0].get('demo_history'):
        return json.loads(res.data[0]['demo_history'])
    return []

def save_demo_history(user_id, history):
    supabase.table('users').update({'demo_history': json.dumps(history[-500:])}).eq('id', user_id).execute()

def load_demo_stats(user_id):
    res = supabase.table('users').select('demo_stats').eq('id', user_id).execute()
    if res.data and res.data[0].get('demo_stats'):
        return json.loads(res.data[0]['demo_stats'])
    return {}

def save_demo_stats(user_id, stats):
    supabase.table('users').update({'demo_stats': json.dumps(stats)}).eq('id', user_id).execute()

def update_demo_stats(user_id, profit):
    stats = load_demo_stats(user_id)
    now = datetime.now()
    day_key = now.strftime("%Y-%m-%d")
    week_key = f"{now.year}-W{now.isocalendar()[1]}"
    month_key = now.strftime("%Y-%m")
    year_key = now.strftime("%Y")
    stats[day_key] = stats.get(day_key, 0) + profit
    stats[week_key] = stats.get(week_key, 0) + profit
    stats[month_key] = stats.get(month_key, 0) + profit
    stats[year_key] = stats.get(year_key, 0) + profit
    save_demo_stats(user_id, stats)

def add_trade(user_id, mode, asset, amount, profit, buy_ex, sell_ex):
    supabase.table('trades').insert({
        'user_id': user_id, 'mode': mode, 'asset': asset,
        'amount': amount, 'profit': profit, 'buy_exchange': buy_ex, 'sell_exchange': sell_ex
    }).execute()

def create_withdrawal_request(user_id, amount, wallet):
    admin_fee = amount * 0.22
    supabase.table('withdrawals').insert({
        'user_id': user_id, 'amount': amount, 'admin_fee': admin_fee,
        'user_receives': amount - admin_fee, 'wallet_address': wallet, 'status': 'pending'
    }).execute()

def get_all_users_for_admin():
    return supabase.table('users').select('*').order('created_at', desc=True).execute().data

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

# ---------- ШИФРОВАНИЕ ----------
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

# ---------- ДЕМО-БАЛАНСЫ ----------
def get_balance(exchange_name, asset):
    if asset == 'USDT':
        return st.session_state.user_data.get('usdt_reserves', {}).get(exchange_name, 0.0)
    else:
        return st.session_state.user_data.get('portfolio', {}).get(asset, 0.0)

def update_balance(exchange_name, asset, delta):
    if asset == 'USDT':
        reserves = st.session_state.user_data.get('usdt_reserves', {})
        reserves[exchange_name] = reserves.get(exchange_name, 0.0) + delta
        st.session_state.user_data['usdt_reserves'] = reserves
    else:
        port = st.session_state.user_data.get('portfolio', {})
        port[asset] = port.get(asset, 0.0) + delta
        st.session_state.user_data['portfolio'] = port
    save_user_mode_data(st.session_state.user_id, st.session_state.current_mode, st.session_state.user_data)

def save_user_mode_data(user_id, mode, data):
    if mode == "Демо":
        update_data = {
            'demo_balances': json.dumps({
                'usdt_reserves': data.get('usdt_reserves', {}),
                'portfolio': data.get('portfolio', {})
            }),
            'demo_history': json.dumps(data['history'][-500:]),
            'demo_stats': json.dumps(data.get('stats', {})),
            'total_profit': data['total_profit'],
            'trade_count': data['trade_count'],
            'withdrawable_balance': data['withdrawable_balance'],
            'total_admin_fee_paid': data['total_admin_fee_paid']
        }
        supabase.table('users').update(update_data).eq('id', user_id).execute()
    else:
        pass

def load_user_mode_data(user, mode):
    if mode == "Демо":
        bal = json.loads(user.get('demo_balances', '{}')) if user.get('demo_balances') else {}
        return {
            'trade_balance': 0,
            'withdrawable_balance': user.get('withdrawable_balance', 0),
            'total_profit': user.get('total_profit', 0),
            'trade_count': user.get('trade_count', 0),
            'total_admin_fee_paid': user.get('total_admin_fee_paid', 0),
            'portfolio': bal.get('portfolio', INITIAL_PORTFOLIO),
            'usdt_reserves': bal.get('usdt_reserves', {ex: DEMO_USDT_PER_EXCHANGE for ex in EXCHANGES}),
            'history': json.loads(user.get('demo_history', '[]')),
            'stats': json.loads(user.get('demo_stats', '{}'))
        }
    else:
        return {}

# ---------- АРБИТРАЖ ----------
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

    trade_usdt = min(usdt_buy * (TRADE_PERCENT / 100.0), token_sell_value * (TRADE_PERCENT / 100.0))
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
    st.session_state.user_data['total_profit'] += real_profit
    st.session_state.user_data['trade_count'] += 1
    history_entry = f"✅ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | {asset} | {buy_ex}→{sell_ex} | {amount:.6f} {asset} | +{real_profit:.2f} USDT"
    st.session_state.user_data['history'].append(history_entry)
    save_user_mode_data(st.session_state.user_id, st.session_state.current_mode, st.session_state.user_data)
    update_demo_stats(st.session_state.user_id, real_profit)
    add_trade(st.session_state.user_id, st.session_state.current_mode, asset, amount, real_profit, buy_ex, sell_ex)
    log_list.append(f"✅ {asset} {buy_ex}→{sell_ex} | {trade_usdt:.2f} USDT | +{real_profit:.2f} USDT")
    return real_profit

# ---------- ФОНОВЫЙ ПОТОК ----------
def background_arbitrage_loop():
    while True:
        try:
            if st.session_state.get('bot_running', False):
                opps = find_opportunities()
                if opps:
                    best = opps[0]
                    if best['profit'] > 0:
                        execute_trade(best, st.session_state.auto_log)
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
    st.session_state.user_data = {}
    st.session_state.user_id = None
    st.session_state.api_keys = {}
    st.session_state.chat_unread = 0
    st.session_state.auto_log = []

if st.session_state.exchanges is None:
    with st.spinner("Подключение к биржам..."):
        st.session_state.exchanges, st.session_state.exchange_status = init_exchanges()
        st.session_state.api_keys = get_all_api_keys()

# ---------- РЕГИСТРАЦИЯ / ВХОД ----------
if not st.session_state.logged_in:
    st.markdown('<h1 class="main-header">🚀 АРБИТРАЖ PRO | Финальная версия</h1>', unsafe_allow_html=True)
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
                        st.session_state.user_data = load_user_mode_data(user,"Демо")
                        st.session_state.chat_unread = get_unread_count(user['id'])
                        st.success(f"Добро пожаловать, {st.session_state.username}!")
                        st.rerun()
                    else:
                        st.error("Доступ запрещён")
                else:
                    st.error("Неверный email или пароль")
    st.stop()

# ---------- ОСНОВНОЙ ИНТЕРФЕЙС ----------
if st.session_state.user_id and st.session_state.user_data:
    save_user_mode_data(st.session_state.user_id, st.session_state.current_mode, st.session_state.user_data)

col_logo, col_status, col_logout = st.columns([3,1,1])
with col_logo:
    st.markdown('<h1 class="main-header">🚀 АРБИТРАЖ PRO | Финальная версия</h1>', unsafe_allow_html=True)
with col_status:
    if st.session_state.bot_running:
        st.markdown('<div><span class="status-indicator status-running"></span> <b>АВТО-ТОРГОВЛЯ АКТИВНА</b></div>', unsafe_allow_html=True)
    else:
        st.markdown('<div><span class="status-indicator status-stopped"></span> <b>ОСТАНОВЛЕН</b></div>', unsafe_allow_html=True)
with col_logout:
    if st.button("🚪 Выйти"):
        save_user_mode_data(st.session_state.user_id, st.session_state.current_mode, st.session_state.user_data)
        st.session_state.logged_in = False
        st.session_state.bot_running = False
        save_bot_status(False)
        st.rerun()

st.markdown(f'<div class="user-info">👤 {st.session_state.username} | 📧 {st.session_state.email}</div>', unsafe_allow_html=True)
connected = [ex.upper() for ex,sts in st.session_state.exchange_status.items() if sts=="connected"]
st.write(f"🔌 **Биржи:** {', '.join(connected)}")
st.write(f"🪙 **Токены:** {', '.join(get_available_tokens())}")
st.divider()

total_usdt = sum(st.session_state.user_data.get('usdt_reserves',{}).values())
total_portfolio = 0
for asset, amount in st.session_state.user_data.get('portfolio', {}).items():
    if st.session_state.exchanges:
        first_ex = list(st.session_state.exchanges.keys())[0]
        price = get_price(st.session_state.exchanges[first_ex], asset)
        if price:
            total_portfolio += amount * price
col1,col2,col3 = st.columns(3)
col1.metric("💰 Всего USDT", f"{total_usdt:.2f}")
col2.metric("📦 Стоимость портфеля", f"{total_portfolio:.2f}")
col3.metric("📊 Всего сделок", st.session_state.user_data.get('trade_count',0))

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
    new_mode = st.selectbox("Режим",["Демо","Реальный"], index=0 if st.session_state.current_mode=="Демо" else 1)
    if new_mode != st.session_state.current_mode:
        save_user_mode_data(st.session_state.user_id, st.session_state.current_mode, st.session_state.user_data)
        st.session_state.current_mode = "Демо"
        st.rerun()

if st.button("🔄 Обновить данные", use_container_width=True):
    st.rerun()

with st.expander("📋 Лог авто-торговли (последние 20 событий)"):
    if st.session_state.auto_log:
        for log in st.session_state.auto_log[-20:]:
            st.text(log)
    else:
        st.info("Нет событий. Запустите бота (СТАРТ).")

# ---------- АДМИН-ПАНЕЛЬ ----------
if is_admin(st.session_state.email):
    st.divider()
    st.subheader("👑 Админ-панель")
    if st.button("🔄 Сбросить мои балансы до 125 USDT + портфель (очистит историю)"):
        reset_demo_balances_to_target(st.session_state.user_id)
        st.success("Балансы сброшены! Перезагрузите страницу (нажмите 'R' или F5).")
        st.rerun()

st.caption(f"🚀 Сканируется {len(get_available_tokens())} токенов на {len(connected)} биржах | Интервал: {SCAN_INTERVAL} сек | Режим: {st.session_state.current_mode}")
