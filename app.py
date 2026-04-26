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

st.set_page_config(page_title="Накопительный Арбитраж PRO", layout="wide", page_icon="🚀", initial_sidebar_state="collapsed")

# ====================== ПОДКЛЮЧЕНИЕ К SUPABASE ======================
SUPABASE_URL = st.secrets.get("SUPABASE_URL")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("❌ Ошибка: не заданы переменные окружения SUPABASE_URL и SUPABASE_KEY. Добавьте их в Secrets в Streamlit Cloud.")
    st.stop()

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ====================== TELEGRAM ======================
TELEGRAM_BOT_TOKEN = st.secrets.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = st.secrets.get("TELEGRAM_CHAT_ID")

def send_telegram(message):
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
            requests.post(url, json=payload, timeout=5)
        except:
            pass

# ====================== СТИЛЬ ======================
st.markdown("""
<style>
    .stApp { background: linear-gradient(180deg, #001a33 0%, #003087 100%) !important; color: white !important; }
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
    .api-warning { background: #ffaa0022; border-left: 4px solid #FFAA00; padding: 10px; border-radius: 8px; margin: 10px 0; }
    .api-success { background: #00ff8822; border-left: 4px solid #00FF88; padding: 10px; border-radius: 8px; margin: 10px 0; }
</style>
""", unsafe_allow_html=True)

# ====================== КОНФИГУРАЦИЯ ======================
DEFAULT_ASSETS = ["ETH", "SOL", "LINK", "AAVE", "DOT", "ADA", "TON", "VET", "HBAR", "XTZ"]
PREFERRED_MAIN_EXCHANGE = "binance"
FALLBACK_MAIN_EXCHANGE = "okx"
AUX_EXCHANGES = ["gateio", "kucoin", "bybit", "mexc", "bitget", "bingx", "bitmart"]
ALL_EXCHANGES = [PREFERRED_MAIN_EXCHANGE, FALLBACK_MAIN_EXCHANGE] + AUX_EXCHANGES

# НИЗКИЕ ПОРОГИ ДЛЯ ТЕСТА (можно потом повысить)
MIN_SPREAD_PERCENT = 0.1      # 0.1% чистый спред
FEE_PERCENT = 0.1             # 0.1% комиссия тейкера
SLIPPAGE_PERCENT = 0.2        # 0.2% проскальзывание
MIN_24H_VOLUME_USDT = 100000  # 100k USDT
MAX_WITHDRAWAL_FEE_PERCENT = 20  # комиссия вывода до 20% от прибыли

ADMIN_COMMISSION = 0.22
REINVEST_SHARE = 0.50
FIXED_SHARE = 0.50
ADMIN_EMAILS = ["cb777899@gmail.com", "admin@arbitrage.com"]

def is_admin(email):
    return email in ADMIN_EMAILS

# ====================== ФУНКЦИИ РАБОТЫ С SUPABASE ======================
def get_user_by_email(email):
    result = supabase.table('users').select('*').eq('email', email).execute()
    return result.data[0] if result.data else None

def create_user(email, password_hash, full_name, country, city, phone, wallet_address):
    demo_reserves = get_demo_usdt_reserves()
    target_portfolio = get_target_portfolio()
    data = {
        'email': email,
        'password_hash': password_hash,
        'full_name': full_name,
        'country': country,
        'city': city,
        'phone': phone,
        'wallet_address': wallet_address,
        'registration_status': 'pending',
        'trade_balance': 1000,
        'portfolio': json.dumps(target_portfolio),
        'usdt_reserves': json.dumps(demo_reserves)
    }
    result = supabase.table('users').insert(data).execute()
    send_telegram(f"🆕 Новая регистрация!\n👤 {full_name}\n📧 {email}")
    return result.data[0]['id'] if result.data else None

def load_user_mode_data(user, mode):
    if mode == "Демо":
        return {
            'trade_balance': user.get('trade_balance', 1000),
            'withdrawable_balance': user.get('withdrawable_balance', 0),
            'total_profit': user.get('total_profit', 0),
            'trade_count': user.get('trade_count', 0),
            'total_admin_fee_paid': user.get('total_admin_fee_paid', 0),
            'last_withdrawal_date': user.get('last_withdrawal_date'),
            'portfolio': json.loads(user.get('portfolio', '{}')) if user.get('portfolio') else get_target_portfolio(),
            'usdt_reserves': json.loads(user.get('usdt_reserves', '{}')) if user.get('usdt_reserves') else get_demo_usdt_reserves(),
            'daily_profits': json.loads(user.get('demo_daily_profits', '{}')) if user.get('demo_daily_profits') else {},
            'weekly_profits': json.loads(user.get('demo_weekly_profits', '{}')) if user.get('demo_weekly_profits') else {},
            'monthly_profits': json.loads(user.get('demo_monthly_profits', '{}')) if user.get('demo_monthly_profits') else {},
            'history': json.loads(user.get('demo_history', '[]')) if user.get('demo_history') else []
        }
    else:
        return {
            'trade_balance': user.get('real_balance', 0),
            'withdrawable_balance': 0,
            'total_profit': user.get('real_total_profit', 0),
            'trade_count': user.get('real_trade_count', 0),
            'total_admin_fee_paid': 0,
            'last_withdrawal_date': None,
            'portfolio': json.loads(user.get('real_portfolio', '{}')) if user.get('real_portfolio') else {a: 0 for a in DEFAULT_ASSETS},
            'usdt_reserves': json.loads(user.get('real_usdt_reserves', '{}')) if user.get('real_usdt_reserves') else {},
            'daily_profits': json.loads(user.get('real_daily_profits', '{}')) if user.get('real_daily_profits') else {},
            'weekly_profits': json.loads(user.get('real_weekly_profits', '{}')) if user.get('real_weekly_profits') else {},
            'monthly_profits': json.loads(user.get('real_monthly_profits', '{}')) if user.get('real_monthly_profits') else {},
            'history': json.loads(user.get('real_history', '[]')) if user.get('real_history') else []
        }

def save_user_mode_data(user_id, mode, data):
    if mode == "Демо":
        update_data = {
            'trade_balance': data['trade_balance'],
            'withdrawable_balance': data['withdrawable_balance'],
            'total_profit': data['total_profit'],
            'trade_count': data['trade_count'],
            'total_admin_fee_paid': data['total_admin_fee_paid'],
            'last_withdrawal_date': data['last_withdrawal_date'],
            'portfolio': json.dumps(data['portfolio']),
            'usdt_reserves': json.dumps(data['usdt_reserves']),
            'demo_daily_profits': json.dumps(data['daily_profits']),
            'demo_weekly_profits': json.dumps(data['weekly_profits']),
            'demo_monthly_profits': json.dumps(data['monthly_profits']),
            'demo_history': json.dumps(data['history'][-500:])
        }
    else:
        update_data = {
            'real_balance': data['trade_balance'],
            'real_total_profit': data['total_profit'],
            'real_trade_count': data['trade_count'],
            'real_portfolio': json.dumps(data['portfolio']),
            'real_usdt_reserves': json.dumps(data['usdt_reserves']),
            'real_daily_profits': json.dumps(data['daily_profits']),
            'real_weekly_profits': json.dumps(data['weekly_profits']),
            'real_monthly_profits': json.dumps(data['monthly_profits']),
            'real_history': json.dumps(data['history'][-500:])
        }
    supabase.table('users').update(update_data).eq('id', user_id).execute()

def add_trade(user_id, mode, asset, amount, profit, buy_exchange, sell_exchange):
    data = {
        'user_id': user_id,
        'mode': mode,
        'asset': asset,
        'amount': amount,
        'profit': profit,
        'buy_exchange': buy_exchange,
        'sell_exchange': sell_exchange
    }
    supabase.table('trades').insert(data).execute()

def get_all_trades(limit=200):
    result = supabase.table('trades').select('*, users(email, full_name)').order('trade_time', desc=True).limit(limit).execute()
    return result.data

def create_withdrawal_request(user_id, amount, wallet_address):
    admin_fee = amount * ADMIN_COMMISSION
    user_receives = amount - admin_fee
    data = {
        'user_id': user_id,
        'amount': amount,
        'admin_fee': admin_fee,
        'user_receives': user_receives,
        'wallet_address': wallet_address,
        'status': 'pending'
    }
    result = supabase.table('withdrawals').insert(data).execute()
    send_telegram(f"💰 Заявка на вывод: {amount} USDT от пользователя")
    return result.data[0]['id'] if result.data else None

def get_pending_withdrawals():
    result = supabase.table('withdrawals').select('*, users(email, full_name)').eq('status', 'pending').order('requested_at').execute()
    return result.data

def update_withdrawal_status(withdrawal_id, status, admin_email):
    update_data = {'status': status, 'processed_at': datetime.now().isoformat(), 'processed_by': admin_email}
    supabase.table('withdrawals').update(update_data).eq('id', withdrawal_id).execute()
    if status == 'completed':
        withdrawal = supabase.table('withdrawals').select('user_id, amount, admin_fee').eq('id', withdrawal_id).execute()
        if withdrawal.data:
            user_id = withdrawal.data[0]['user_id']
            amount = withdrawal.data[0]['amount']
            admin_fee = withdrawal.data[0]['admin_fee']
            user = supabase.table('users').select('withdrawable_balance, total_admin_fee_paid').eq('id', user_id).execute()
            if user.data:
                new_balance = user.data[0]['withdrawable_balance'] - amount
                new_admin_fee_total = user.data[0]['total_admin_fee_paid'] + admin_fee
                supabase.table('users').update({'withdrawable_balance': new_balance, 'total_admin_fee_paid': new_admin_fee_total}).eq('id', user_id).execute()

def get_all_users_for_admin():
    result = supabase.table('users').select('id, email, full_name, country, city, phone, registration_status, trade_balance, withdrawable_balance, total_profit, trade_count, total_admin_fee_paid, created_at, approved_at, approved_by').order('created_at', desc=True).execute()
    return result.data

def update_user_status(user_id, status, admin_email):
    supabase.table('users').update({'registration_status': status, 'approved_at': datetime.now().isoformat(), 'approved_by': admin_email}).eq('id', user_id).execute()
    send_telegram(f"✅ Пользователь одобрен администратором")

def delete_user(user_id, admin_email):
    trades = supabase.table('trades').select('id').eq('user_id', user_id).execute()
    if len(trades.data) == 0:
        supabase.table('users').delete().eq('id', user_id).execute()
        return True
    return False

def get_all_api_keys():
    result = supabase.table('api_keys').select('exchange, api_key, secret_key').execute()
    return {row['exchange']: {'api_key': row['api_key'], 'secret_key': row['secret_key']} for row in result.data}

def save_api_key(exchange, api_key, secret_key, admin_email):
    encrypted_api = encrypt_api_key(api_key) if api_key else ""
    encrypted_secret = encrypt_api_key(secret_key) if secret_key else ""
    data = {
        'exchange': exchange,
        'api_key': encrypted_api,
        'secret_key': encrypted_secret,
        'updated_at': datetime.now().isoformat(),
        'updated_by': admin_email
    }
    supabase.table('api_keys').upsert(data, on_conflict='exchange').execute()

def get_config(key):
    result = supabase.table('config').select('value').eq('key', key).execute()
    if result.data:
        return json.loads(result.data[0]['value'])
    return None

def set_config(key, value):
    supabase.table('config').upsert({'key': key, 'value': json.dumps(value)}).execute()

def get_available_tokens():
    tokens = get_config('tokens')
    if not tokens:
        tokens = DEFAULT_ASSETS
        set_config('tokens', tokens)
    return tokens

def get_target_portfolio():
    pf = get_config('portfolio')
    if not pf:
        pf = {"ETH": 0.55, "SOL": 12.0, "LINK": 60.0, "AAVE": 5.5, "DOT": 80.0, "ADA": 2800.0, "TON": 25.0, "VET": 35000.0, "HBAR": 4000.0, "XTZ": 55.0}
        set_config('portfolio', pf)
    return pf

def set_available_tokens(tokens):
    set_config('tokens', tokens)

def set_target_portfolio(portfolio):
    set_config('portfolio', portfolio)

def get_demo_usdt_reserves():
    result = supabase.table('demo_usdt_reserves').select('exchange, amount').execute()
    return {row['exchange']: row['amount'] for row in result.data}

def update_demo_usdt_reserve(exchange, amount):
    supabase.table('demo_usdt_reserves').upsert({'exchange': exchange, 'amount': amount}).execute()

def get_messages(user_id=None, limit=50):
    if user_id:
        result = supabase.table('messages').select('*').eq('user_id', user_id).order('created_at', desc=True).limit(limit).execute()
    else:
        result = supabase.table('messages').select('*, users(full_name)').order('created_at', desc=True).limit(limit).execute()
    return result.data

def add_message(user_id, user_email, user_name, message, is_admin_reply=False, reply_to=None):
    data = {
        'user_id': user_id,
        'user_email': user_email,
        'user_name': user_name,
        'message': message,
        'is_admin_reply': is_admin_reply,
        'reply_to': reply_to
    }
    supabase.table('messages').insert(data).execute()
    send_telegram(f"📩 Новое сообщение от {user_name}: {message[:100]}...")

def mark_messages_read(user_id):
    supabase.table('messages').update({'is_read': True}).eq('user_id', user_id).eq('is_read', False).eq('is_admin_reply', True).execute()

def get_unread_count(user_id):
    result = supabase.table('messages').select('id', count='exact').eq('user_id', user_id).eq('is_read', False).eq('is_admin_reply', True).execute()
    return result.count or 0

# ====================== ШИФРОВАНИЕ ======================
ENCRYPTION_KEY = hashlib.sha256("arbitrage_secret_key_2024".encode()).digest()

def encrypt_api_key(key):
    if not key:
        return ""
    try:
        from cryptography.fernet import Fernet
        fernet = Fernet(base64.urlsafe_b64encode(ENCRYPTION_KEY[:32]))
        return fernet.encrypt(key.encode()).decode()
    except:
        return base64.b64encode(key.encode()).decode()

def decrypt_api_key(encrypted):
    if not encrypted:
        return ""
    try:
        from cryptography.fernet import Fernet
        fernet = Fernet(base64.urlsafe_b64encode(ENCRYPTION_KEY[:32]))
        return fernet.decrypt(encrypted.encode()).decode()
    except:
        try:
            return base64.b64decode(encrypted).decode()
        except:
            return ""

# ====================== ПОДКЛЮЧЕНИЕ К БИРЖАМ ======================
@st.cache_resource
def init_exchanges():
    exchanges = {}
    status = {}
    for ex_name in ALL_EXCHANGES:
        try:
            exchange = getattr(ccxt, ex_name)({'enableRateLimit': True})
            exchange.fetch_ticker('BTC/USDT')
            exchanges[ex_name] = exchange
            status[ex_name] = "connected"
        except:
            status[ex_name] = "error"
    # Определяем основную биржу (сначала пробуем Binance, если нет - OKX)
    if PREFERRED_MAIN_EXCHANGE in exchanges:
        st.session_state.main_exchange = PREFERRED_MAIN_EXCHANGE
    elif FALLBACK_MAIN_EXCHANGE in exchanges:
        st.session_state.main_exchange = FALLBACK_MAIN_EXCHANGE
    else:
        st.session_state.main_exchange = None
    return exchanges, status

def get_price(exchange, symbol):
    try:
        ticker = exchange.fetch_ticker(f"{symbol}/USDT")
        return ticker['last']
    except:
        return None

def get_24h_volume(exchange, symbol):
    try:
        ticker = exchange.fetch_ticker(f"{symbol}/USDT")
        vol = ticker.get('quoteVolume')
        if vol is None:
            vol = ticker['last'] * ticker.get('baseVolume', 0)
        return vol
    except:
        return 0

def get_withdrawal_fee(exchange_name, asset):
    default_fees = {
        'binance': 0.5, 'okx': 0.5, 'gateio': 1.0, 'kucoin': 1.0, 'bybit': 1.0,
        'bitget': 1.0, 'bingx': 1.0, 'mexc': 1.0, 'bitmart': 1.0
    }
    high_fee_assets = ['ETH', 'LINK', 'AAVE']
    if asset in high_fee_assets:
        return default_fees.get(exchange_name, 2.0) * 2
    return default_fees.get(exchange_name, 1.0)

def find_all_arbitrage_opportunities():
    opportunities = []
    if not st.session_state.exchanges or st.session_state.main_exchange not in st.session_state.exchanges:
        return opportunities
    tokens = get_available_tokens()
    main_prices = {}
    main_volumes = {}
    for asset in tokens:
        price = get_price(st.session_state.exchanges[st.session_state.main_exchange], asset)
        if price:
            main_prices[asset] = price
            main_volumes[asset] = get_24h_volume(st.session_state.exchanges[st.session_state.main_exchange], asset)
    for asset in tokens:
        if asset not in main_prices:
            continue
        if main_volumes.get(asset, 0) < MIN_24H_VOLUME_USDT:
            continue
        main_price = main_prices[asset]
        for aux_ex in AUX_EXCHANGES:
            if aux_ex not in st.session_state.exchanges or not st.session_state.exchanges[aux_ex]:
                continue
            aux_price = get_price(st.session_state.exchanges[aux_ex], asset)
            if aux_price and aux_price < main_price:
                spread_pct = (main_price - aux_price) / aux_price * 100
                net_spread = spread_pct - FEE_PERCENT - SLIPPAGE_PERCENT
                if net_spread <= MIN_SPREAD_PERCENT:
                    continue
                profit_before = main_price - aux_price - (main_price * (FEE_PERCENT/100) + aux_price * (FEE_PERCENT/100))
                if profit_before <= 0:
                    continue
                withdraw_fee = get_withdrawal_fee(aux_ex, asset)
                if withdraw_fee > profit_before * (MAX_WITHDRAWAL_FEE_PERCENT / 100):
                    continue
                net_profit = profit_before - withdraw_fee
                if net_profit <= 0:
                    continue
                opportunities.append({
                    'asset': asset,
                    'aux_exchange': aux_ex,
                    'main_price': main_price,
                    'aux_price': aux_price,
                    'spread_pct': round(spread_pct, 2),
                    'profit_usdt': round(profit_before, 2),
                    'withdrawal_fee': withdraw_fee,
                    'net_profit_after_withdrawal': round(net_profit, 2)
                })
    return sorted(opportunities, key=lambda x: x['net_profit_after_withdrawal'], reverse=True)

def get_historical_ohlcv(exchange, symbol, timeframe='1h', limit=100):
    try:
        ohlcv = exchange.fetch_ohlcv(f"{symbol}/USDT", timeframe, limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except:
        return pd.DataFrame()

# ====================== ФОНОВЫЙ ПОТОК ======================
background_running = True
def background_arbitrage_loop():
    while True:
        try:
            if st.session_state.get('bot_running', False):
                time.sleep(10)
            else:
                time.sleep(5)
        except:
            time.sleep(5)
if 'background_thread_started' not in st.session_state:
    background_thread = threading.Thread(target=background_arbitrage_loop, daemon=True)
    background_thread.start()
    st.session_state.background_thread_started = True

BOT_STATUS_FILE = "bot_status.json"
def save_bot_status(status):
    try:
        with open(BOT_STATUS_FILE, 'w') as f:
            json.dump({'bot_running': status}, f)
    except:
        pass
def load_bot_status():
    try:
        with open(BOT_STATUS_FILE, 'r') as f:
            data = json.load(f)
            return data.get('bot_running', False)
    except:
        return False

query_params = st.query_params
if query_params.get("ping") == "true":
    st.write("ok")
    st.stop()

# ====================== СЕССИЯ ======================
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'username' not in st.session_state:
    st.session_state.username = None
if 'email' not in st.session_state:
    st.session_state.email = None
if 'wallet_address' not in st.session_state:
    st.session_state.wallet_address = ''
if 'exchanges' not in st.session_state:
    st.session_state.exchanges = None
if 'bot_running' not in st.session_state:
    st.session_state.bot_running = load_bot_status()
if 'exchange_status' not in st.session_state:
    st.session_state.exchange_status = {}
if 'current_mode' not in st.session_state:
    st.session_state.current_mode = "Демо"
if 'user_data' not in st.session_state:
    st.session_state.user_data = {}
if 'user_id' not in st.session_state:
    st.session_state.user_id = None
if 'api_keys' not in st.session_state:
    st.session_state.api_keys = {}
if 'show_api_warning' not in st.session_state:
    st.session_state.show_api_warning = False
if 'chat_unread' not in st.session_state:
    st.session_state.chat_unread = 0
if 'main_exchange' not in st.session_state:
    st.session_state.main_exchange = None

if st.session_state.exchanges is None:
    with st.spinner("Подключение к биржам..."):
        st.session_state.exchanges, st.session_state.exchange_status = init_exchanges()
        st.session_state.api_keys = get_all_api_keys()

if st.session_state.main_exchange is None:
    st.error("❌ Не удалось подключиться ни к Binance, ни к OKX. Проверьте интернет и доступность бирж.")
    st.stop()

# ====================== РЕГИСТРАЦИЯ / ВХОД ======================
if not st.session_state.logged_in:
    st.markdown('<h1 class="main-header">🚀 НАКОПИТЕЛЬНЫЙ АРБИТРАЖ PRO</h1>', unsafe_allow_html=True)
    tab_reg, tab_login = st.tabs(["📝 Регистрация", "🔑 Вход"])
    with tab_reg:
        with st.form("register_form"):
            username = st.text_input("Имя пользователя")
            email = st.text_input("Email")
            country = st.text_input("Страна")
            city = st.text_input("Город")
            phone = st.text_input("Телефон")
            wallet = st.text_input("Адрес кошелька (USDT)")
            password = st.text_input("Пароль", type="password")
            confirm = st.text_input("Подтвердите пароль", type="password")
            submitted = st.form_submit_button("Зарегистрироваться", use_container_width=True)
            if submitted:
                if username and email and wallet and password and password == confirm:
                    existing_user = get_user_by_email(email)
                    if existing_user:
                        st.error("Пользователь с таким email уже существует!")
                    else:
                        create_user(email, password, username, country, city, phone, wallet)
                        st.success("Регистрация успешна! Ваша заявка отправлена администратору.")
                else:
                    st.error("Заполните все поля или пароли не совпадают")
    with tab_login:
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Пароль", type="password")
            submitted = st.form_submit_button("Войти", use_container_width=True)
            if submitted:
                user = get_user_by_email(email)
                if user and user['password_hash'] == password:
                    if user['registration_status'] == 'approved':
                        st.session_state.logged_in = True
                        st.session_state.username = user['full_name']
                        st.session_state.email = user['email']
                        st.session_state.wallet_address = user.get('wallet_address', '')
                        st.session_state.user_id = user['id']
                        st.session_state.user_data = load_user_mode_data(user, "Демо")
                        st.session_state.chat_unread = get_unread_count(user['id'])
                        st.success(f"Добро пожаловать, {st.session_state.username}!")
                        st.rerun()
                    elif user['registration_status'] == 'pending':
                        st.warning("Ваша заявка на одобрение ещё не рассмотрена.")
                    else:
                        st.error("Ваша заявка отклонена. Свяжитесь с администратором.")
                else:
                    st.error("Неверный email или пароль")
    st.stop()

# ====================== ОСНОВНОЙ ИНТЕРФЕЙС ======================
if st.session_state.user_id and st.session_state.user_data:
    save_user_mode_data(st.session_state.user_id, st.session_state.current_mode, st.session_state.user_data)

col_logo, col_status, col_logout = st.columns([3, 1, 1])
with col_logo:
    st.markdown('<h1 class="main-header">🚀 НАКОПИТЕЛЬНЫЙ АРБИТРАЖ PRO</h1>', unsafe_allow_html=True)
with col_status:
    if st.session_state.bot_running:
        st.markdown('<div style="text-align: center;"><span class="status-indicator status-running"></span> <b style="color: #00FF88;">РАБОТАЕТ 24/7</b></div>', unsafe_allow_html=True)
    else:
        st.markdown('<div style="text-align: center;"><span class="status-indicator status-stopped"></span> <b style="color: #FF4444;">ОСТАНОВЛЕН</b></div>', unsafe_allow_html=True)
with col_logout:
    if st.button("🚪 Выйти", key="logout"):
        if st.session_state.user_id and st.session_state.user_data:
            save_user_mode_data(st.session_state.user_id, st.session_state.current_mode, st.session_state.user_data)
        st.session_state.logged_in = False
        st.session_state.bot_running = False
        save_bot_status(False)
        st.rerun()

st.markdown(f'<div class="user-info">👤 {st.session_state.username} | 📧 {st.session_state.email}</div>', unsafe_allow_html=True)

connected = [ex.upper() for ex, status in st.session_state.exchange_status.items() if status == "connected"]
st.write(f"🔌 **Биржи:** {', '.join(connected[:8])}" + (f" +{len(connected)-8}" if len(connected) > 8 else ""))
st.write(f"🪙 **Токены:** {', '.join(get_available_tokens())} ({len(get_available_tokens())} токенов)")
st.divider()

col1, col2, col3 = st.columns(3)
col1.metric("💰 Торговый баланс", f"{st.session_state.user_data.get('trade_balance', 0):.2f} USDT")
col2.metric("🏦 Доступно для вывода", f"{st.session_state.user_data.get('withdrawable_balance', 0):.2f} USDT")
col3.metric("📊 Всего сделок", st.session_state.user_data.get('trade_count', 0))
if is_admin(st.session_state.email):
    st.metric("💸 Всего комиссий админу", f"{st.session_state.user_data.get('total_admin_fee_paid', 0):.2f} USDT")

if not is_admin(st.session_state.email):
    unread = get_unread_count(st.session_state.user_id)
    if unread > 0:
        st.info(f"💬 У вас {unread} непрочитанных сообщений в чате поддержки!")

# Цветные кнопки управления
c1, c2, c3, c4 = st.columns(4)
with c1:
    st.markdown('<div class="green-button">', unsafe_allow_html=True)
    if st.button("▶ СТАРТ", use_container_width=True):
        st.session_state.bot_running = True
        save_bot_status(True)
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)
with c2:
    st.markdown('<div class="yellow-button">', unsafe_allow_html=True)
    if st.button("⏸ ПАУЗА", use_container_width=True):
        st.session_state.bot_running = False
        save_bot_status(False)
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)
with c3:
    st.markdown('<div class="red-button">', unsafe_allow_html=True)
    if st.button("⏹ СТОП", use_container_width=True):
        st.session_state.bot_running = False
        save_bot_status(False)
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)
with c4:
    new_mode = st.selectbox("Режим", ["Демо", "Реальный"], index=0 if st.session_state.current_mode == "Демо" else 1)
    if new_mode != st.session_state.current_mode:
        if st.session_state.user_id and st.session_state.user_data:
            save_user_mode_data(st.session_state.user_id, st.session_state.current_mode, st.session_state.user_data)
        if new_mode == "Реальный":
            has_keys = any(st.session_state.api_keys.get(ex, {}).get('api_key') for ex in ALL_EXCHANGES)
            if not has_keys:
                st.warning("⚠️ Для реального режима необходимо подключить API ключи бирж.")
                st.session_state.current_mode = "Демо"
                st.rerun()
        user = get_user_by_email(st.session_state.email)
        if user:
            st.session_state.user_data = load_user_mode_data(user, new_mode)
            st.session_state.current_mode = new_mode
            st.rerun()

if st.session_state.current_mode == "Реальный":
    has_keys = any(st.session_state.api_keys.get(ex, {}).get('api_key') for ex in ALL_EXCHANGES)
    if has_keys:
        st.markdown('<div class="api-success">✅ Реальный режим активен.</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="api-warning">⚠️ РЕАЛЬНЫЙ РЕЖИМ: API ключи не подключены.</div>', unsafe_allow_html=True)

# ====================== ВКЛАДКИ ======================
show_admin_panel = st.session_state.get('logged_in') and is_admin(st.session_state.get('email', ''))
tabs_list = ["📊 Dashboard", "📈 Графики", "🔄 Арбитраж", "📊 Доходность", "📊 Статистика по токенам", "📦 Портфель", "💰 Кошелёк", "📜 История", "👤 Личный кабинет", "💬 Чат"]
if show_admin_panel:
    tabs_list.append("👑 Админ-панель")
tabs = st.tabs(tabs_list)

# ---------- TAB 0: Dashboard ----------
with tabs[0]:
    st.subheader("📊 Статус сканирования токенов")
    st.write("### 🪙 Текущие цены на основной бирже")
    tokens = get_available_tokens()
    for i in range(0, len(tokens), 5):
        cols = st.columns(5)
        for j, asset in enumerate(tokens[i:i+5]):
            with cols[j]:
                price = get_price(st.session_state.exchanges[st.session_state.main_exchange], asset) if st.session_state.exchanges else None
                if price:
                    st.markdown(f"<div class='token-card'><b>{asset}</b><br><span style='font-size: 18px; color: #00D4FF;'>${price:,.0f}</span></div>", unsafe_allow_html=True)
                else:
                    st.markdown(f"<div class='token-card'><b>{asset}</b><br>❌</div>", unsafe_allow_html=True)
    if st.session_state.bot_running:
        st.info(f"🟢 Бот сканирует **{len(tokens)} токенов** на **{len(connected)} биржах** одновременно. Работает 24/7.")

# ---------- TAB 1: Графики ----------
with tabs[1]:
    st.subheader("📈 Японские свечи")
    col_a, col_b = st.columns(2)
    selected_asset = col_a.selectbox("Актив", get_available_tokens())
    selected_exchange = col_b.selectbox("Биржа", ALL_EXCHANGES[:5])
    if st.button("🔄 Обновить график", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    if st.session_state.exchanges and selected_exchange in st.session_state.exchanges:
        try:
            df = get_historical_ohlcv(st.session_state.exchanges[selected_exchange], selected_asset)
            if not df.empty:
                fig = go.Figure(data=[go.Candlestick(x=df['timestamp'], open=df['open'], high=df['high'], low=df['low'], close=df['close'])])
                fig.update_layout(title=f"{selected_asset}/USDT на {selected_exchange.upper()}", template="plotly_dark", height=500)
                st.plotly_chart(fig, use_container_width=True)
                st.metric("Текущая цена", f"${df['close'].iloc[-1]:,.2f}")
            else:
                st.warning("Нет данных для графика")
        except Exception as e:
            st.warning(f"Ошибка: {str(e)[:80]}")
    else:
        st.warning("Биржа не подключена")

# ---------- TAB 2: Арбитраж ----------
with tabs[2]:
    st.subheader("🔍 Найденные арбитражные возможности")
    if st.button("🔄 Обновить", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    opportunities = find_all_arbitrage_opportunities()
    if opportunities:
        st.success(f"Найдено {len(opportunities)} возможностей!")
        for idx, opp in enumerate(opportunities[:10]):
            unique_key = f"{opp['asset']}_{opp['aux_exchange']}_{idx}"
            st.info(f"🎯 {opp['asset']}: {st.session_state.main_exchange.upper()} ${opp['main_price']:,.0f} → {opp['aux_exchange'].upper()} ${opp['aux_price']:,.0f} | +{opp['profit_usdt']:.2f} USDT (чистая: {opp['net_profit_after_withdrawal']:.2f})")
            if st.button(f"Исполнить {opp['asset']} на {opp['aux_exchange'].upper()}", key=unique_key):
                profit = opp['net_profit_after_withdrawal']
                if is_admin(st.session_state.email):
                    st.session_state.user_data['trade_balance'] += profit
                    st.session_state.user_data['total_profit'] += profit
                    st.session_state.user_data['trade_count'] += 1
                    st.session_state.user_data['history'].append(f"✅ {datetime.now().strftime('%H:%M:%S')} | {opp['asset']} | +{profit:.2f} USDT")
                    if st.session_state.user_id:
                        add_trade(st.session_state.user_id, st.session_state.current_mode, opp['asset'], 1000, profit, opp['aux_exchange'], st.session_state.main_exchange)
                        save_user_mode_data(st.session_state.user_id, st.session_state.current_mode, st.session_state.user_data)
                    st.success(f"Сделка исполнена! +{profit:.2f} USDT")
                    send_telegram(f"💹 Сделка (админ): {opp['asset']} +{profit:.2f} USDT")
                    st.rerun()
                else:
                    admin_fee = profit * ADMIN_COMMISSION
                    net_profit = profit - admin_fee
                    reinvest_amount = net_profit * REINVEST_SHARE
                    fixed_amount = net_profit * FIXED_SHARE
                    st.session_state.user_data['trade_balance'] += reinvest_amount
                    st.session_state.user_data['withdrawable_balance'] += fixed_amount
                    st.session_state.user_data['total_profit'] += profit
                    st.session_state.user_data['trade_count'] += 1
                    st.session_state.user_data['total_admin_fee_paid'] += admin_fee
                    st.session_state.user_data['history'].append(f"✅ {datetime.now().strftime('%H:%M:%S')} | {opp['asset']} | +{profit:.2f} USDT")
                    if st.session_state.user_id:
                        add_trade(st.session_state.user_id, st.session_state.current_mode, opp['asset'], 1000, profit, opp['aux_exchange'], st.session_state.main_exchange)
                        save_user_mode_data(st.session_state.user_id, st.session_state.current_mode, st.session_state.user_data)
                    st.success(f"Сделка исполнена! +{profit:.2f} USDT (админу {admin_fee:.2f}, реинвест {reinvest_amount:.2f}, вывод {fixed_amount:.2f})")
                    send_telegram(f"💹 Сделка: {opp['asset']} +{profit:.2f} USDT")
                    st.rerun()
    else:
        st.info("Арбитражных возможностей не найдено. Попробуйте снизить пороги в админ-панели или подождать волатильности.")

# ---------- TAB 3: Доходность ----------
with tabs[3]:
    st.subheader("Калькулятор ожидаемой доходности")
    capital = st.number_input("Капитал для арбитража (USDT)", min_value=100.0, value=10000.0, step=1000.0)
    if st.button("Рассчитать", use_container_width=True):
        exp_profit = capital * 0.008
        exp_return = 0.8
        st.markdown(f"""
        <div class="profit-card">
            <b>Ожидаемая дневная доходность:</b><br>
            Прибыль в день: <b style="color: #00FF88;">${exp_profit:.2f}</b><br>
            Доходность: <b style="color: #00FF88;">{exp_return:.2f}%</b> от капитала
        </div>
        """, unsafe_allow_html=True)

# ---------- TAB 4: Статистика по токенам ----------
with tabs[4]:
    st.subheader("📊 Статистика арбитражных сделок по токенам")
    token_stats = {}
    total_profit_all = 0
    total_trades_all = 0
    for trade in st.session_state.user_data.get('history', []):
        if trade.startswith("✅"):
            try:
                parts = trade.split("|")
                if len(parts) >= 3:
                    token = parts[1].strip()
                    profit = None
                    for part in parts:
                        if "+" in part and "USDT" in part:
                            profit_str = part.split("+")[1].split()[0]
                            profit = float(profit_str)
                            break
                    if profit is not None:
                        token_stats.setdefault(token, {'trades': 0, 'profit': 0})
                        token_stats[token]['trades'] += 1
                        token_stats[token]['profit'] += profit
                        total_profit_all += profit
                        total_trades_all += 1
            except:
                pass
    if token_stats:
        stats_data = []
        for token, data in sorted(token_stats.items(), key=lambda x: x[1]['profit'], reverse=True):
            profit_pct = (data['profit'] / total_profit_all * 100) if total_profit_all > 0 else 0
            stats_data.append({"Токен": token, "Сделок": data['trades'], "Прибыль (USDT)": f"{data['profit']:.2f}", "% от общей прибыли": f"{profit_pct:.1f}%"})
        st.dataframe(pd.DataFrame(stats_data), use_container_width=True, hide_index=True)
        fig_data = [{"Токен": t, "Прибыль": d['profit']} for t, d in token_stats.items()]
        df_fig = pd.DataFrame(fig_data)
        if not df_fig.empty:
            fig = px.pie(df_fig, values='Прибыль', names='Токен', title="Доля прибыли по токенам")
            fig.update_layout(template="plotly_dark", height=450)
            st.plotly_chart(fig, use_container_width=True)
            fig2 = px.bar(df_fig, x='Токен', y='Прибыль', title="Прибыль по токенам (USDT)", color='Токен')
            fig2.update_layout(template="plotly_dark", height=450)
            st.plotly_chart(fig2, use_container_width=True)
        st.caption(f"📊 Всего сделок: {total_trades_all} | Общая прибыль: ${total_profit_all:.2f}")
    else:
        st.info("Нет данных о сделках.")

# ---------- TAB 5: Портфель ----------
with tabs[5]:
    st.subheader("📦 Портфель токенов")
    total = 0
    portfolio = st.session_state.user_data.get('portfolio', get_target_portfolio())
    for asset, amount in portfolio.items():
        price = get_price(st.session_state.exchanges[st.session_state.main_exchange], asset) if st.session_state.exchanges else None
        value = amount * price if price else 0
        total += value
        st.write(f"{asset}: {amount:.6f} ≈ ${value:,.2f}")
    st.divider()
    st.metric("💰 Общая стоимость портфеля", f"${total:,.2f}")

# ---------- TAB 6: Кошелёк ----------
with tabs[6]:
    st.subheader("💰 Кошелёк и вывод средств")
    st.write(f"**Доступно для вывода:** {st.session_state.user_data.get('withdrawable_balance', 0):.2f} USDT")
    st.write(f"**Торговый баланс:** {st.session_state.user_data.get('trade_balance', 0):.2f} USDT")
    st.write(f"**Всего комиссий уплачено:** {st.session_state.user_data.get('total_admin_fee_paid', 0):.2f} USDT")
    current_weekday = datetime.now().strftime("%A")
    allowed_days = ["Tuesday", "Friday"]
    if current_weekday not in allowed_days:
        st.warning("⏳ Вывод средств возможен только по вторникам и пятницам.")
        withdraw_disabled = True
    else:
        withdraw_disabled = False
    max_withdraw = st.session_state.user_data.get('withdrawable_balance', 0)
    if max_withdraw >= 10.0:
        withdraw_amount = st.number_input("Сумма вывода (USDT)", min_value=10.0, max_value=max_withdraw, step=10.0, disabled=withdraw_disabled)
        if st.button("📤 Запросить вывод", disabled=withdraw_disabled):
            if withdraw_amount > 0 and st.session_state.wallet_address:
                admin_fee = withdraw_amount * ADMIN_COMMISSION
                user_receives = withdraw_amount - admin_fee
                st.info(f"💰 Сумма: {withdraw_amount} USDT | Комиссия: {admin_fee:.2f} | Вы получите: {user_receives:.2f}")
                if st.button("✅ Подтвердить вывод"):
                    create_withdrawal_request(st.session_state.user_id, withdraw_amount, st.session_state.wallet_address)
                    st.session_state.user_data['withdrawable_balance'] -= withdraw_amount
                    save_user_mode_data(st.session_state.user_id, st.session_state.current_mode, st.session_state.user_data)
                    st.success(f"Заявка отправлена! Комиссия {admin_fee:.2f} USDT, вы получите {user_receives:.2f} USDT.")
                    st.rerun()
            elif not st.session_state.wallet_address:
                st.error("Сначала сохраните адрес кошелька!")
            else:
                st.error("Введите сумму больше 0")
    else:
        st.warning(f"Недостаточно средств. Доступно: {max_withdraw:.2f} USDT (мин. 10)")
    st.divider()
    wallet_input = st.text_input("Адрес кошелька (USDT)", value=st.session_state.wallet_address)
    if st.button("💾 Сохранить адрес"):
        st.session_state.wallet_address = wallet_input
        if st.session_state.email:
            supabase.table('users').update({'wallet_address': wallet_input}).eq('email', st.session_state.email).execute()
        st.success("Адрес сохранён!")

# ---------- TAB 7: История ----------
with tabs[7]:
    st.subheader("📜 История сделок")
    if st.session_state.user_data.get('history'):
        for trade in reversed(st.session_state.user_data['history'][-50:]):
            st.write(trade)
        if st.button("🗑 Очистить историю"):
            st.session_state.user_data['history'] = []
            if st.session_state.user_id:
                save_user_mode_data(st.session_state.user_id, st.session_state.current_mode, st.session_state.user_data)
            st.rerun()
    else:
        st.info("Нет сделок")

# ---------- TAB 8: Личный кабинет ----------
with tabs[8]:
    st.subheader("👤 Личный кабинет")
    st.write(f"**Имя:** {st.session_state.username}")
    st.write(f"**Email:** {st.session_state.email}")
    st.write(f"**Кошелёк для вывода:** {st.session_state.wallet_address if st.session_state.wallet_address else 'не указан'}")
    st.divider()
    col_bal1, col_bal2 = st.columns(2)
    with col_bal1:
        st.metric("💰 Торговый баланс", f"{st.session_state.user_data.get('trade_balance', 0):.2f} USDT")
    with col_bal2:
        st.metric("🏦 Доступно для вывода", f"{st.session_state.user_data.get('withdrawable_balance', 0):.2f} USDT")
    st.divider()
    st.write("### 📊 Ваша статистика")
    col_stat1, col_stat2, col_stat3 = st.columns(3)
    with col_stat1:
        st.metric("📈 Общая прибыль", f"{st.session_state.user_data.get('total_profit', 0):.2f} USDT")
    with col_stat2:
        st.metric("📊 Сделок", st.session_state.user_data.get('trade_count', 0))
    with col_stat3:
        st.metric("💸 Комиссий уплачено", f"{st.session_state.user_data.get('total_admin_fee_paid', 0):.2f} USDT")
    st.divider()
    st.write("### 📦 Ваши токены (топ-5)")
    portfolio = st.session_state.user_data.get('portfolio', {})
    if portfolio:
        top_tokens = list(portfolio.items())[:5]
        for token, amount in top_tokens:
            price = get_price(st.session_state.exchanges[st.session_state.main_exchange], token) if st.session_state.exchanges else None
            value = amount * price if price else 0
            st.write(f"**{token}:** {amount:.6f} ≈ ${value:,.2f}")
    else:
        st.write("Нет данных")
    st.divider()
    st.write("### 💳 Управление средствами")
    deposit_amount = st.number_input("Сумма пополнения (USDT)", min_value=10.0, step=10.0, key="deposit_lk")
    if st.button("💰 Пополнить", key="deposit_btn"):
        st.session_state.user_data['trade_balance'] += deposit_amount
        save_user_mode_data(st.session_state.user_id, st.session_state.current_mode, st.session_state.user_data)
        st.success(f"✅ Баланс пополнен на {deposit_amount} USDT!")
        st.rerun()
    withdraw_amount_lk = st.number_input("Сумма вывода (USDT)", min_value=10.0, step=10.0, key="withdraw_lk")
    if st.button("📤 Запросить вывод", key="withdraw_btn"):
        if withdraw_amount_lk <= st.session_state.user_data.get('withdrawable_balance', 0):
            if st.session_state.wallet_address:
                create_withdrawal_request(st.session_state.user_id, withdraw_amount_lk, st.session_state.wallet_address)
                st.success(f"Заявка на вывод {withdraw_amount_lk} USDT отправлена!")
                st.rerun()
            else:
                st.error("Сначала сохраните адрес кошелька!")
        else:
            st.error("Недостаточно средств для вывода!")
    st.info("💡 Пополнение доступно только в демо-режиме. В реальном режиме средства вносятся напрямую на биржу.")

# ---------- TAB 9: Чат ----------
with tabs[9]:
    st.subheader("💬 Чат с поддержкой")
    if is_admin(st.session_state.email):
        st.write("### Сообщения от пользователей")
        messages = get_messages(limit=100)
        if messages:
            for msg in messages:
                user_name = msg.get('user_name', 'Пользователь')
                user_email = msg.get('user_email', '')
                with st.container():
                    st.markdown(f"**{user_name}** ({user_email}) - {msg['created_at'][:16]}")
                    st.write(msg['message'])
                    if not msg.get('is_admin_reply', False):
                        reply_text = st.text_input(f"Ответ для {user_name}", key=f"reply_{msg['id']}")
                        if st.button(f"Отправить ответ", key=f"send_{msg['id']}"):
                            if reply_text:
                                add_message(msg['user_id'], user_email, user_name, reply_text, is_admin_reply=True, reply_to=msg['id'])
                                st.success("Ответ отправлен!")
                                send_telegram(f"📨 Администратор ответил {user_name}: {reply_text[:50]}...")
                                st.rerun()
                    st.divider()
        else:
            st.info("Нет сообщений.")
        with st.expander("📢 Отправить сообщение всем пользователям"):
            broadcast = st.text_area("Текст объявления")
            if st.button("Отправить всем"):
                if broadcast:
                    all_users = get_all_users_for_admin()
                    for u in all_users:
                        add_message(u['id'], u['email'], u['full_name'], f"[ОБЪЯВЛЕНИЕ] {broadcast}", is_admin_reply=True)
                    st.success("Объявление отправлено всем пользователям!")
                    send_telegram(f"📢 Объявление отправлено всем пользователям: {broadcast[:100]}")
                    st.rerun()
    else:
        st.write("### Напишите нам")
        user_message = st.text_area("Ваше сообщение")
        if st.button("Отправить сообщение"):
            if user_message:
                add_message(st.session_state.user_id, st.session_state.email, st.session_state.username, user_message)
                st.success("Сообщение отправлено! Администратор ответит в ближайшее время.")
                st.rerun()
        st.divider()
        st.write("### История ваших обращений")
        user_messages = get_messages(user_id=st.session_state.user_id, limit=30)
        if user_messages:
            for msg in user_messages:
                if msg.get('is_admin_reply'):
                    st.info(f"📢 **Администратор:** {msg['message']} _( {msg['created_at'][:16]} )_")
                else:
                    st.write(f"📤 **Вы:** {msg['message']} _( {msg['created_at'][:16]} )_")
        else:
            st.info("У вас пока нет обращений.")
        mark_messages_read(st.session_state.user_id)
        st.session_state.chat_unread = 0

# ---------- АДМИН-ПАНЕЛЬ ----------
if show_admin_panel:
    with tabs[-1]:
        st.subheader("👑 Админ-панель")
        admin_tab1, admin_tab2, admin_tab3, admin_tab4, admin_tab5, admin_tab6 = st.tabs(["👥 Участники", "📊 Токены", "🔐 API ключи", "📜 Все сделки", "💰 Заявки на вывод", "⚙ Демо-резервы"])
        # Участники
        with admin_tab1:
            st.write("### Все участники")
            all_users = get_all_users_for_admin()
            if all_users:
                users_data = []
                for user in all_users:
                    users_data.append({
                        "ID": user['id'], "Email": user['email'], "Имя": user['full_name'],
                        "Страна": user.get('country', ''), "Город": user.get('city', ''), "Статус": user['registration_status'],
                        "Торговый баланс": f"${user.get('trade_balance', 0):.2f}",
                        "Доступно для вывода": f"${user.get('withdrawable_balance', 0):.2f}",
                        "Общая прибыль": f"${user.get('total_profit', 0):.2f}",
                        "Сделок": user.get('trade_count', 0), "Комиссий админу": f"${user.get('total_admin_fee_paid', 0):.2f}",
                        "Регистрация": user['created_at'][:10] if user.get('created_at') else ""
                    })
                st.dataframe(pd.DataFrame(users_data), use_container_width=True, hide_index=True)
                st.write("### Управление статусами")
                all_users_list = list(all_users)
                user_emails = {u['email']: u['id'] for u in all_users_list}
                selected_user_email = st.selectbox("Выберите пользователя", list(user_emails.keys()))
                if selected_user_email:
                    selected_id = user_emails[selected_user_email]
                    user = supabase.table('users').select('*').eq('id', selected_id).execute()
                    if user.data:
                        user_data = user.data[0]
                        st.write(f"**Текущий статус:** {user_data['registration_status']}")
                        if user_data['registration_status'] == 'pending':
                            if st.button("✅ Одобрить этого пользователя"):
                                update_user_status(selected_id, 'approved', st.session_state.email)
                                st.success(f"Пользователь {selected_user_email} одобрен!")
                                st.rerun()
                        elif user_data['registration_status'] == 'approved':
                            if st.button("🔴 Заблокировать (установить статус rejected)"):
                                update_user_status(selected_id, 'rejected', st.session_state.email)
                                st.warning(f"Пользователь {selected_user_email} заблокирован.")
                                st.rerun()
            else:
                st.info("Нет пользователей")
        # Токены
        with admin_tab2:
            st.write("### Управление токенами")
            current_tokens = get_available_tokens()
            tokens_input = st.text_input("Список токенов через запятую", value=", ".join(current_tokens))
            if st.button("Сохранить список токенов"):
                new_tokens = [t.strip().upper() for t in tokens_input.split(",") if t.strip()]
                if new_tokens:
                    set_available_tokens(new_tokens)
                    st.success("Список токенов обновлён!")
                    st.rerun()
                else:
                    st.error("Введите хотя бы один токен")
            st.divider()
            st.write("### Целевые количества в портфеле")
            current_portfolio = get_target_portfolio()
            new_portfolio = {}
            cols = st.columns(3)
            for i, token in enumerate(current_tokens):
                with cols[i % 3]:
                    new_portfolio[token] = st.number_input(f"{token} (шт.)", value=float(current_portfolio.get(token, 0.0)), step=0.01, format="%.4f", key=f"admin_token_{token}")
            if st.button("Сохранить портфель"):
                set_target_portfolio(new_portfolio)
                st.success("Цели обновлены!")
        # API ключи
        with admin_tab3:
            st.write("### API ключи")
            api_keys = get_all_api_keys()
            for ex in ALL_EXCHANGES:
                with st.expander(f"🔑 {ex.upper()}", expanded=False):
                    current = api_keys.get(ex, {})
                    current_api = decrypt_api_key(current.get('api_key', ''))
                    current_secret = decrypt_api_key(current.get('secret_key', ''))
                    new_api = st.text_input(f"API Key ({ex.upper()})", value=current_api, type="password", key=f"api_{ex}")
                    new_secret = st.text_input(f"Secret Key ({ex.upper()})", value=current_secret, type="password", key=f"secret_{ex}")
                    col1, col2 = st.columns(2)
                    if col1.button(f"🔍 Проверить {ex.upper()}", key=f"test_{ex}"):
                        if new_api and new_secret:
                            try:
                                ex_class = getattr(ccxt, ex)
                                test_ex = ex_class({'apiKey': new_api, 'secret': new_secret, 'enableRateLimit': True})
                                test_ex.fetch_balance()
                                st.success("✅ Ключи действительны")
                            except Exception as e:
                                st.error(f"❌ Ошибка: {str(e)[:100]}")
                        else:
                            st.warning("Введите ключи")
                    if col2.button(f"💾 Сохранить {ex.upper()}", key=f"save_{ex}"):
                        save_api_key(ex, new_api, new_secret, st.session_state.email)
                        st.session_state.api_keys = get_all_api_keys()
                        st.success(f"Ключи {ex.upper()} сохранены!")
                        st.rerun()
        # Все сделки
        with admin_tab4:
            st.write("### Все сделки")
            all_trades = get_all_trades(limit=200)
            if all_trades:
                trades_data = [{"ID": t['id'], "Пользователь": t.get('users', {}).get('email', 'unknown'), "Токен": t['asset'], "Прибыль": f"${t['profit']:.2f}", "Время": t['trade_time']} for t in all_trades]
                st.dataframe(pd.DataFrame(trades_data), use_container_width=True, hide_index=True)
            else:
                st.info("Нет сделок")
        # Заявки на вывод
        with admin_tab5:
            st.write("### Заявки на вывод")
            pending = get_pending_withdrawals()
            if pending:
                for w in pending:
                    st.write(f"**{w.get('users', {}).get('email', 'unknown')}** — {w['amount']} USDT (комиссия {w['admin_fee']:.2f}, клиент получит {w['user_receives']:.2f})")
                    if st.button(f"✅ Выполнить", key=f"complete_{w['id']}"):
                        update_withdrawal_status(w['id'], 'completed', st.session_state.email)
                        st.success(f"Вывод {w['amount']} USDT выполнен!")
                        st.rerun()
            else:
                st.info("Нет заявок")
        # Демо-резервы
        with admin_tab6:
            st.write("### Настройка начальных резервов USDT для демо-режима")
            st.info("Эти значения будут использоваться при создании новых пользователей в демо-режиме.")
            current_reserves = get_demo_usdt_reserves()
            new_reserves = {}
            cols = st.columns(3)
            for i, ex in enumerate(AUX_EXCHANGES):
                with cols[i % 3]:
                    current_val = current_reserves.get(ex, 10000)
                    new_val = st.number_input(f"{ex.upper()} (USDT)", value=float(current_val), step=500.0, key=f"reserve_{ex}")
                    new_reserves[ex] = new_val
            if st.button("💾 Сохранить резервы"):
                for ex, amt in new_reserves.items():
                    update_demo_usdt_reserve(ex, amt)
                st.success("Настройки резервов сохранены! Новые пользователи будут получать указанные суммы USDT.")
                st.rerun()

# ====================== АВТОМАТИЧЕСКИЙ АРБИТРАЖ ======================
if st.session_state.bot_running and st.session_state.exchanges:
    time.sleep(8)
    opportunities = find_all_arbitrage_opportunities()
    if opportunities:
        best = opportunities[0]
        profit = best['net_profit_after_withdrawal']
        if profit >= 0.08:
            if is_admin(st.session_state.email):
                st.session_state.user_data['trade_balance'] += profit
                st.session_state.user_data['total_profit'] += profit
                st.session_state.user_data['trade_count'] += 1
                st.session_state.user_data['history'].append(f"✅ {datetime.now().strftime('%H:%M:%S')} | {best['asset']} | АВТО | +{profit:.2f} USDT")
                if st.session_state.user_id:
                    add_trade(st.session_state.user_id, st.session_state.current_mode, best['asset'], 1000, profit, best['aux_exchange'], st.session_state.main_exchange)
                    save_user_mode_data(st.session_state.user_id, st.session_state.current_mode, st.session_state.user_data)
                st.toast(f"🎯 {best['asset']} +{profit:.2f} USDT", icon="💰")
                send_telegram(f"🤖 Авто-сделка (админ): {best['asset']} +{profit:.2f} USDT")
                st.rerun()
            else:
                admin_fee = profit * ADMIN_COMMISSION
                net_profit = profit - admin_fee
                reinvest_amount = net_profit * REINVEST_SHARE
                fixed_amount = net_profit * FIXED_SHARE
                st.session_state.user_data['trade_balance'] += reinvest_amount
                st.session_state.user_data['withdrawable_balance'] += fixed_amount
                st.session_state.user_data['total_profit'] += profit
                st.session_state.user_data['trade_count'] += 1
                st.session_state.user_data['total_admin_fee_paid'] += admin_fee
                st.session_state.user_data['history'].append(f"✅ {datetime.now().strftime('%H:%M:%S')} | {best['asset']} | АВТО | +{profit:.2f} USDT")
                if st.session_state.user_id:
                    add_trade(st.session_state.user_id, st.session_state.current_mode, best['asset'], 1000, profit, best['aux_exchange'], st.session_state.main_exchange)
                    save_user_mode_data(st.session_state.user_id, st.session_state.current_mode, st.session_state.user_data)
                st.toast(f"🎯 {best['asset']} +{profit:.2f} USDT (реинвест {reinvest_amount:.2f}, вывод {fixed_amount:.2f})", icon="💰")
                send_telegram(f"🤖 Авто-сделка: {best['asset']} +{profit:.2f} USDT")
                st.rerun()

st.caption(f"🚀 Сканируется {len(get_available_tokens())} токенов на {len(connected)} биржах | Режим: {st.session_state.current_mode} | Основная биржа: {st.session_state.main_exchange.upper()} | Фильтры: ликвидность >{MIN_24H_VOLUME_USDT/1000}k USDT, проскальзывание {SLIPPAGE_PERCENT}%, комиссия вывода <{MAX_WITHDRAWAL_FEE_PERCENT}% от прибыли")
