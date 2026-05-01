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
import threading
from supabase import create_client, Client
import requests

st.set_page_config(page_title="Накопительный арбитражный бот | АВТО", layout="wide", page_icon="🔄", initial_sidebar_state="collapsed")

SUPABASE_URL = st.secrets.get("SUPABASE_URL")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY")
if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("❌ Нет SUPABASE_URL / SUPABASE_KEY в Secrets")
    st.stop()
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

TELEGRAM_BOT_TOKEN = st.secrets.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = st.secrets.get("TELEGRAM_CHAT_ID")
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
    .api-warning { background: #ffaa0022; border-left: 4px solid #FFAA00; padding: 10px; border-radius: 8px; margin: 10px 0; }
    .api-success { background: #00ff8822; border-left: 4px solid #00FF88; padding: 10px; border-radius: 8px; margin: 10px 0; }
</style>
""", unsafe_allow_html=True)

EXCHANGES = ["kucoin", "hitbtc", "okx", "bingx", "bitget"]
DEFAULT_ASSETS = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "LINK", "SUI", "HYPE", "TON"]
DEFAULT_PORTFOLIO = {
    "BTC": 0.08, "ETH": 1.5, "SOL": 25.0, "BNB": 4.0, "XRP": 1800.0,
    "ADA": 4000.0, "AVAX": 40.0, "LINK": 70.0, "SUI": 400.0, "HYPE": 50.0, "TON": 80.0
}
DEMO_USDT_PER_EXCHANGE = 5000
ADMIN_COMMISSION = 0.22
REINVEST_SHARE = 0.50
FIXED_SHARE = 0.50
ADMIN_EMAILS = ["cb777899@gmail.com", "admin@arbitrage.com"]

DEFAULT_THRESHOLDS = {
    "min_spread_percent": 0.0005,
    "fee_percent": 0.1,
    "slippage_percent": 0.2,
    "min_24h_volume_usdt": 0,
    "max_withdrawal_fee_percent": 30
}

SCAN_INTERVAL = 3
MIN_AUTO_PROFIT = 0.01

def is_admin(email):
    return email in ADMIN_EMAILS

# ---------- ФУНКЦИИ SUPABASE ----------
def get_user_by_email(email):
    res = supabase.table('users').select('*').eq('email', email).execute()
    return res.data[0] if res.data else None

def create_user(email, pwd_hash, full_name, country, city, phone, wallet):
    initial_balances = {ex: {"USDT": DEMO_USDT_PER_EXCHANGE, "portfolio": DEFAULT_PORTFOLIO.copy()} for ex in EXCHANGES}
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
        balances = json.loads(res.data[0]['demo_balances'])
        for ex in EXCHANGES:
            if ex not in balances:
                balances[ex] = {"USDT": DEMO_USDT_PER_EXCHANGE, "portfolio": DEFAULT_PORTFOLIO.copy()}
        return balances
    else:
        return {ex: {"USDT": DEMO_USDT_PER_EXCHANGE, "portfolio": DEFAULT_PORTFOLIO.copy()} for ex in EXCHANGES}

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

def ensure_demo_balances(user_id):
    current = load_demo_balances(user_id)
    changed = False
    for ex in EXCHANGES:
        if ex not in current:
            current[ex] = {"USDT": DEMO_USDT_PER_EXCHANGE, "portfolio": DEFAULT_PORTFOLIO.copy()}
            changed = True
        else:
            if 'USDT' not in current[ex]:
                current[ex]['USDT'] = DEMO_USDT_PER_EXCHANGE
                changed = True
            if 'portfolio' not in current[ex]:
                current[ex]['portfolio'] = DEFAULT_PORTFOLIO.copy()
                changed = True
            for asset in DEFAULT_ASSETS:
                if asset not in current[ex]['portfolio']:
                    current[ex]['portfolio'][asset] = DEFAULT_PORTFOLIO.get(asset, 0)
                    changed = True
    if changed:
        save_demo_balances(user_id, current)
    return current

def get_all_users_for_admin():
    return supabase.table('users').select('*').order('created_at', desc=True).execute().data

def add_trade(user_id, mode, asset, amount, profit, buy_ex, sell_ex):
    supabase.table('trades').insert({
        'user_id': user_id, 'mode': mode, 'asset': asset,
        'amount': amount, 'profit': profit, 'buy_exchange': buy_ex, 'sell_exchange': sell_ex
    }).execute()

def get_all_trades(limit=200):
    res = supabase.table('trades').select('*, users(email, full_name)').order('trade_time', desc=True).limit(limit).execute()
    return res.data

def create_withdrawal_request(user_id, amount, wallet):
    admin_fee = amount * ADMIN_COMMISSION
    user_receives = amount - admin_fee
    data = {
        'user_id': user_id, 'amount': amount, 'admin_fee': admin_fee,
        'user_receives': user_receives, 'wallet_address': wallet, 'status': 'pending'
    }
    res = supabase.table('withdrawals').insert(data).execute()
    send_telegram(f"💰 Заявка на вывод {amount} USDT")
    return res.data[0]['id'] if res.data else None

def get_pending_withdrawals():
    res = supabase.table('withdrawals').select('*, users(email, full_name)').eq('status', 'pending').order('requested_at').execute()
    return res.data

def update_withdrawal_status(wid, status, admin_email):
    supabase.table('withdrawals').update({
        'status': status, 'processed_at': datetime.now().isoformat(), 'processed_by': admin_email
    }).eq('id', wid).execute()
    if status == 'completed':
        w = supabase.table('withdrawals').select('user_id, amount, admin_fee').eq('id', wid).execute()
        if w.data:
            uid = w.data[0]['user_id']; amt = w.data[0]['amount']; fee = w.data[0]['admin_fee']
            user = supabase.table('users').select('withdrawable_balance, total_admin_fee_paid').eq('id', uid).execute()
            if user.data:
                new_bal = user.data[0]['withdrawable_balance'] - amt
                new_fee = user.data[0]['total_admin_fee_paid'] + fee
                supabase.table('users').update({'withdrawable_balance': new_bal, 'total_admin_fee_paid': new_fee}).eq('id', uid).execute()

def update_user_status(uid, status, admin_email):
    supabase.table('users').update({
        'registration_status': status, 'approved_at': datetime.now().isoformat(), 'approved_by': admin_email
    }).eq('id', uid).execute()
    send_telegram(f"✅ Статус пользователя изменён на {status}")

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

def get_thresholds():
    th = get_config('thresholds')
    if th:
        return th
    else:
        set_config('thresholds', DEFAULT_THRESHOLDS)
        return DEFAULT_THRESHOLDS

def set_thresholds(thresholds):
    set_config('thresholds', thresholds)

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
    send_telegram(f"📩 Сообщение от {user_name}: {message[:100]}")

def mark_messages_read(user_id):
    supabase.table('messages').update({'is_read': True}).eq('user_id', user_id).eq('is_read', False).eq('is_admin_reply', True).execute()

def get_unread_count(user_id):
    res = supabase.table('messages').select('id', count='exact').eq('user_id', user_id).eq('is_read', False).eq('is_admin_reply', True).execute()
    return res.count or 0

def reset_demo_data(user_id):
    balances = {ex: {"USDT": DEMO_USDT_PER_EXCHANGE, "portfolio": DEFAULT_PORTFOLIO.copy()} for ex in EXCHANGES}
    supabase.table('users').update({
        'demo_balances': json.dumps(balances),
        'demo_history': json.dumps([]),
        'demo_stats': json.dumps({}),
        'total_profit': 0,
        'trade_count': 0,
        'withdrawable_balance': 0,
        'total_admin_fee_paid': 0
    }).eq('id', user_id).execute()
    send_telegram(f"🔄 Демо-данные пользователя {user_id} сброшены")

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
    exchanges = {}
    status = {}
    for ex_name in EXCHANGES:
        try:
            ex = getattr(ccxt, ex_name)({'enableRateLimit': True})
            ex.fetch_ticker('BTC/USDT')
            exchanges[ex_name] = ex
            status[ex_name] = "connected"
        except Exception as e:
            status[ex_name] = f"error: {str(e)[:30]}"
    return exchanges, status

@st.cache_data(ttl=2)
def get_cached_price(exchange_name, symbol):
    ex = st.session_state.exchanges.get(exchange_name)
    if not ex:
        return None
    try:
        ticker = ex.fetch_ticker(f"{symbol}/USDT")
        return ticker['last']
    except:
        return None

def get_price(exchange_name, symbol):
    return get_cached_price(exchange_name, symbol)

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
    return 0.0

def find_all_arbitrage_opportunities(exchanges, thresholds):
    opportunities = []
    tokens = get_available_tokens()
    prices = {}
    for ex_name in EXCHANGES:
        prices[ex_name] = {}
        for asset in tokens:
            price = get_price(ex_name, asset)
            if price:
                prices[ex_name][asset] = price
    for i, buy_ex in enumerate(EXCHANGES):
        for j, sell_ex in enumerate(EXCHANGES):
            if i == j: continue
            for asset in tokens:
                if asset not in prices[buy_ex] or asset not in prices[sell_ex]:
                    continue
                buy_price = prices[buy_ex][asset]
                sell_price = prices[sell_ex][asset]
                if sell_price <= buy_price:
                    continue
                spread_pct = (sell_price - buy_price) / buy_price * 100
                net_spread = spread_pct - thresholds['fee_percent'] - thresholds['slippage_percent']
                if net_spread <= thresholds['min_spread_percent']:
                    continue
                profit_before = sell_price - buy_price - (buy_price * thresholds['fee_percent']/100 + sell_price * thresholds['fee_percent']/100)
                if profit_before <= 0:
                    continue
                withdraw_fee = get_withdrawal_fee(buy_ex, asset)
                if withdraw_fee > profit_before * (thresholds['max_withdrawal_fee_percent'] / 100):
                    continue
                net_profit = profit_before - withdraw_fee
                if net_profit <= 0:
                    continue
                opportunities.append({
                    'asset': asset,
                    'buy_exchange': buy_ex,
                    'sell_exchange': sell_ex,
                    'buy_price': buy_price,
                    'sell_price': sell_price,
                    'spread_pct': round(spread_pct, 2),
                    'profit_usdt': round(profit_before, 2),
                    'withdrawal_fee': withdraw_fee,
                    'net_profit': round(net_profit, 2)
                })
    return sorted(opportunities, key=lambda x: x['net_profit'], reverse=True)

def get_historical_ohlcv(exchange, symbol, timeframe='1h', limit=100):
    try:
        ohlcv = exchange.fetch_ohlcv(f"{symbol}/USDT", timeframe, limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp','open','high','low','close','volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except:
        return pd.DataFrame()

# ---------- ИСПОЛНЕНИЕ СДЕЛКИ ----------
def execute_trade(opp, user_id, mode):
    profit = opp['net_profit']
    buy_ex = opp['buy_exchange']
    sell_ex = opp['sell_exchange']
    asset = opp['asset']
    if profit <= 0:
        return 0
    if mode == "Демо":
        if is_admin(st.session_state.email):
            st.session_state.total_profit += profit
            st.session_state.trade_count += 1
            if sell_ex in st.session_state.user_balances:
                st.session_state.user_balances[sell_ex]['USDT'] += profit
            else:
                st.session_state.user_balances[sell_ex] = {"USDT": DEMO_USDT_PER_EXCHANGE + profit, "portfolio": DEFAULT_PORTFOLIO.copy()}
        else:
            admin_fee = profit * ADMIN_COMMISSION
            net = profit - admin_fee
            reinvest = net * REINVEST_SHARE
            fixed = net * FIXED_SHARE
            st.session_state.total_profit += profit
            st.session_state.trade_count += 1
            st.session_state.withdrawable_balance += fixed
            st.session_state.total_admin_fee_paid += admin_fee
            if sell_ex in st.session_state.user_balances:
                st.session_state.user_balances[sell_ex]['USDT'] += reinvest
            else:
                st.session_state.user_balances[sell_ex] = {"USDT": DEMO_USDT_PER_EXCHANGE + reinvest, "portfolio": DEFAULT_PORTFOLIO.copy()}
        history_entry = f"✅ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | {asset} | {buy_ex}→{sell_ex} | +{profit:.2f} USDT"
        st.session_state.user_history.append(history_entry)
        save_demo_history(user_id, st.session_state.user_history)
        update_demo_stats(user_id, profit)
        save_demo_balances(user_id, st.session_state.user_balances)
        supabase.table('users').update({
            'total_profit': st.session_state.total_profit,
            'trade_count': st.session_state.trade_count,
            'withdrawable_balance': st.session_state.withdrawable_balance,
            'total_admin_fee_paid': st.session_state.total_admin_fee_paid,
            'demo_balances': json.dumps(st.session_state.user_balances),
            'demo_history': json.dumps(st.session_state.user_history[-500:]),
            'demo_stats': json.dumps(st.session_state.user_stats)
        }).eq('id', user_id).execute()
        add_trade(user_id, mode, asset, 1, profit, buy_ex, sell_ex)
        return profit
    return profit

# ---------- ФОНОВЫЙ ПОТОК ДЛЯ АВТО-СДЕЛОК ----------
def start_auto_trade():
    if 'auto_trade_thread' not in st.session_state or st.session_state.auto_trade_thread is None or not st.session_state.auto_trade_thread.is_alive():
        st.session_state.stop_auto_trade = False
        def worker():
            while not st.session_state.get('stop_auto_trade', False):
                try:
                    if 'auto_trade_log' not in st.session_state:
                        st.session_state.auto_trade_log = []
                    thresholds = get_thresholds()
                    opportunities = find_all_arbitrage_opportunities(st.session_state.exchanges, thresholds)
                    if opportunities:
                        best = opportunities[0]
                        if best['net_profit'] >= MIN_AUTO_PROFIT:
                            profit = execute_trade(best, st.session_state.user_id, st.session_state.current_mode)
                            if profit > 0:
                                msg = f"🤖 АВТОСДЕЛКА: {best['asset']} {best['buy_exchange']}→{best['sell_exchange']} +{profit:.2f} USDT"
                                st.session_state.auto_trade_log.append(f"{datetime.now().strftime('%H:%M:%S')} {msg}")
                                if len(st.session_state.auto_trade_log) > 50:
                                    st.session_state.auto_trade_log = st.session_state.auto_trade_log[-50:]
                                send_telegram(msg)
                    time.sleep(SCAN_INTERVAL)
                except Exception as e:
                    if 'auto_trade_log' in st.session_state:
                        st.session_state.auto_trade_log.append(f"{datetime.now().strftime('%H:%M:%S')} Ошибка: {e}")
                    time.sleep(5)
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        st.session_state.auto_trade_thread = thread

def stop_auto_trade():
    st.session_state.stop_auto_trade = True
    if 'auto_trade_thread' in st.session_state and st.session_state.auto_trade_thread:
        st.session_state.auto_trade_thread = None

# ---------- СЕССИЯ ----------
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = None
    st.session_state.email = None
    st.session_state.wallet_address = ''
    st.session_state.exchanges = None
    st.session_state.bot_running = False
    st.session_state.auto_trade_enabled = False
    st.session_state.stop_auto_trade = False
    st.session_state.exchange_status = {}
    st.session_state.current_mode = "Демо"
    st.session_state.user_id = None
    st.session_state.api_keys = {}
    st.session_state.chat_unread = 0
    st.session_state.viewed_user_id = None
    st.session_state.user_balances = {}
    st.session_state.user_history = []
    st.session_state.user_stats = {}
    st.session_state.total_profit = 0
    st.session_state.trade_count = 0
    st.session_state.total_admin_fee_paid = 0
    st.session_state.withdrawable_balance = 0
    st.session_state.last_withdrawal_date = None
    st.session_state.auto_trade_thread = None
    st.session_state.auto_trade_log = []

if st.session_state.exchanges is None:
    with st.spinner("Подключение к биржам..."):
        st.session_state.exchanges, st.session_state.exchange_status = init_exchanges()
        st.session_state.api_keys = get_all_api_keys()

thresholds = get_thresholds()

# ---------- РЕГИСТРАЦИЯ / ВХОД ----------
if not st.session_state.logged_in:
    st.markdown('<h1 class="main-header">🔄 Накопительный арбитражный бот | АВТО</h1>', unsafe_allow_html=True)
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
                    st.session_state.logged_in = True
                    st.session_state.username = user['full_name']
                    st.session_state.email = user['email']
                    st.session_state.wallet_address = user.get('wallet_address', '')
                    st.session_state.user_id = user['id']
                    st.session_state.user_balances = ensure_demo_balances(user['id'])
                    st.session_state.user_history = load_demo_history(user['id'])
                    st.session_state.user_stats = load_demo_stats(user['id'])
                    st.session_state.total_profit = user.get('total_profit', 0)
                    st.session_state.trade_count = user.get('trade_count', 0)
                    st.session_state.total_admin_fee_paid = user.get('total_admin_fee_paid', 0)
                    st.session_state.withdrawable_balance = user.get('withdrawable_balance', 0)
                    st.session_state.last_withdrawal_date = user.get('last_withdrawal_date')
                    st.session_state.chat_unread = get_unread_count(user['id'])
                    st.success(f"Добро пожаловать, {st.session_state.username}!")
                    st.rerun()
                else:
                    st.error("Неверный email или пароль")
    st.stop()

# ---------- ОСНОВНОЙ ИНТЕРФЕЙС ----------
col_logo, col_status, col_logout = st.columns([3, 1, 1])
with col_logo:
    st.markdown('<h1 class="main-header">🔄 Накопительный арбитражный бот | АВТО</h1>', unsafe_allow_html=True)
with col_status:
    if st.session_state.auto_trade_enabled:
        st.markdown('<div><span class="status-indicator status-running"></span> <b>АВТО-ТОРГОВЛЯ АКТИВНА</b></div>', unsafe_allow_html=True)
    else:
        st.markdown('<div><span class="status-indicator status-stopped"></span> <b>ОСТАНОВЛЕН</b></div>', unsafe_allow_html=True)
with col_logout:
    if st.button("🚪 Выйти"):
        save_demo_balances(st.session_state.user_id, st.session_state.user_balances)
        save_demo_history(st.session_state.user_id, st.session_state.user_history)
        st.session_state.logged_in = False
        if st.session_state.auto_trade_enabled:
            stop_auto_trade()
        st.rerun()

st.markdown(f'<div class="user-info">👤 {st.session_state.username} | 📧 {st.session_state.email}</div>', unsafe_allow_html=True)
connected = [ex.upper() for ex, sts in st.session_state.exchange_status.items() if "connected" in sts]
st.write(f"🔌 **Биржи:** {', '.join([ex.upper() for ex in EXCHANGES])}")
st.write(f"🪙 **Токены:** {', '.join(get_available_tokens())}")
st.divider()

total_usdt = sum(bal.get('USDT', 0) for bal in st.session_state.user_balances.values())
total_portfolio_value = 0
for ex, bal in st.session_state.user_balances.items():
    for asset, amount in bal.get('portfolio', {}).items():
        price = get_price(ex, asset)
        if price:
            total_portfolio_value += amount * price
col1, col2, col3 = st.columns(3)
col1.metric("💰 Всего USDT", f"{total_usdt:.2f}")
col2.metric("📦 Стоимость портфеля", f"{total_portfolio_value:.2f}")
col3.metric("📊 Всего сделок", st.session_state.trade_count)

c1, c2, c3, c4, c5 = st.columns(5)
with c1:
    st.markdown('<div class="green-button">', unsafe_allow_html=True)
    if st.button("▶ СТАРТ (авто)", use_container_width=True):
        if not st.session_state.exchanges:
            st.session_state.exchanges, _ = init_exchanges()
        if st.session_state.user_id:
            st.session_state.auto_trade_enabled = True
            start_auto_trade()
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)
with c2:
    st.markdown('<div class="yellow-button">', unsafe_allow_html=True)
    if st.button("⏸ ПАУЗА", use_container_width=True):
        st.session_state.auto_trade_enabled = False
        stop_auto_trade()
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)
with c3:
    st.markdown('<div class="red-button">', unsafe_allow_html=True)
    if st.button("⏹ СТОП", use_container_width=True):
        st.session_state.auto_trade_enabled = False
        stop_auto_trade()
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)
with c4:
    new_mode = st.selectbox("Режим", ["Демо", "Реальный"], index=0 if st.session_state.current_mode == "Демо" else 1)
    if new_mode != st.session_state.current_mode:
        st.session_state.current_mode = new_mode
        st.rerun()
with c5:
    if st.button("🧪 Тестовая сделка", use_container_width=True):
        opportunities = find_all_arbitrage_opportunities(st.session_state.exchanges, thresholds)
        if opportunities:
            best = opportunities[0]
            profit = execute_trade(best, st.session_state.user_id, st.session_state.current_mode)
            if profit > 0:
                st.success(f"Тестовая сделка исполнилась! +{profit:.2f} USDT")
                st.rerun()
            else:
                st.error(f"Не удалось исполнить: {best['net_profit']:.2f} USDT")
        else:
            st.warning("Нет возможностей")

if st.button("🔄 Обновить данные", use_container_width=True):
    st.session_state.user_balances = ensure_demo_balances(st.session_state.user_id)
    st.session_state.user_history = load_demo_history(st.session_state.user_id)
    st.session_state.user_stats = load_demo_stats(st.session_state.user_id)
    user_data = supabase.table('users').select('total_profit,trade_count,withdrawable_balance').eq('id', st.session_state.user_id).execute().data[0]
    st.session_state.total_profit = user_data['total_profit']
    st.session_state.trade_count = user_data['trade_count']
    st.session_state.withdrawable_balance = user_data['withdrawable_balance']
    st.rerun()

with st.expander("📋 Лог авто-сделок (последние события)"):
    if 'auto_trade_log' in st.session_state and st.session_state.auto_trade_log:
        for log in st.session_state.auto_trade_log[-30:]:
            st.text(log)
    else:
        st.info("Нет сообщений")

show_admin = is_admin(st.session_state.email)
tabs_list = ["📊 Dashboard", "📈 Графики", "🔄 Арбитраж", "📊 Статистика", "📈 Доходность по дням", "💼 Балансы", "💰 Вывод", "📜 История", "👤 Кабинет", "💬 Чат"]
if show_admin:
    tabs_list.append("👑 Админ-панель")
tabs = st.tabs(tabs_list)

# TAB 0: Dashboard
with tabs[0]:
    st.subheader("📊 Текущие цены на биржах")
    for asset in get_available_tokens()[:5]:
        st.write(f"**{asset}**")
        cols = st.columns(len(EXCHANGES))
        for i, ex in enumerate(EXCHANGES):
            price = get_price(ex, asset)
            with cols[i]:
                if price:
                    st.metric(ex.upper(), f"${price:.2f}")
                else:
                    st.metric(ex.upper(), "❌")
        st.divider()

# TAB 1: Графики
with tabs[1]:
    st.subheader("📈 Японские свечи")
    col_a, col_b = st.columns(2)
    sel_asset = col_a.selectbox("Актив", get_available_tokens())
    sel_ex = col_b.selectbox("Биржа", EXCHANGES)
    if st.button("Обновить график"):
        st.cache_data.clear()
        st.rerun()
    if st.session_state.exchanges and sel_ex in st.session_state.exchanges:
        df = get_historical_ohlcv(st.session_state.exchanges[sel_ex], sel_asset)
        if not df.empty:
            fig = go.Figure(data=[go.Candlestick(x=df['timestamp'], open=df['open'], high=df['high'], low=df['low'], close=df['close'])])
            fig.update_layout(title=f"{sel_asset}/USDT на {sel_ex.upper()}", template="plotly_dark", height=500)
            st.plotly_chart(fig, use_container_width=True)
            st.metric("Текущая цена", f"${df['close'].iloc[-1]:,.2f}")
        else:
            st.warning("Нет данных")

# TAB 2: Арбитраж
with tabs[2]:
    st.subheader("🔍 Арбитражные возможности (авто-торговля в фоне)")
    if st.button("🔄 Обновить", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    opps = find_all_arbitrage_opportunities(st.session_state.exchanges, thresholds)
    if opps:
        st.success(f"Найдено {len(opps)} возможностей")
        for idx, opp in enumerate(opps[:10]):
            key = f"{opp['asset']}_{opp['buy_exchange']}_{opp['sell_exchange']}_{idx}"
            st.info(f"🎯 {opp['asset']}: купить на {opp['buy_exchange'].upper()} ${opp['buy_price']:.2f} → продать на {opp['sell_exchange'].upper()} ${opp['sell_price']:.2f} | +{opp['profit_usdt']:.2f} USDT (чистая: {opp['net_profit']:.2f})")
            if st.button(f"Исполнить вручную {opp['asset']} {opp['buy_exchange']}→{opp['sell_exchange']}", key=key):
                profit = execute_trade(opp, st.session_state.user_id, st.session_state.current_mode)
                if profit > 0:
                    st.success(f"Сделка исполнена! +{profit:.2f} USDT")
                    st.rerun()
                else:
                    st.error("Ошибка исполнения")
    else:
        st.info("Арбитражных возможностей не найдено. Попробуйте снизить пороги в админ-панели.")

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
        data = [{"Токен": t, "Сделок": d['trades'], "Прибыль": f"{d['profit']:.2f}", "% общ.": f"{d['profit'] / total_profit_all * 100:.1f}%"} for t, d in sorted(token_stats.items(), key=lambda x: x[1]['profit'], reverse=True)]
        st.dataframe(pd.DataFrame(data), use_container_width=True, hide_index=True)
        fig = px.pie(pd.DataFrame([{"Токен": t, "Прибыль": d['profit']} for t, d in token_stats.items()]), values='Прибыль', names='Токен', title="Доля прибыли")
        fig.update_layout(template="plotly_dark", height=450)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Нет данных")

# TAB 4: Доходность по дням
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

# TAB 5: Балансы по биржам
with tabs[5]:
    st.subheader("💼 Балансы USDT и портфель по каждой бирже")
    for ex in EXCHANGES:
        with st.expander(f"### {ex.upper()}"):
            bal = st.session_state.user_balances.get(ex, {})
            usdt = bal.get('USDT', 0)
            st.metric("USDT", f"{usdt:.2f}")
            portfolio = bal.get('portfolio', {})
            st.write("**Портфель токенов:**")
            for asset, amount in portfolio.items():
                price = get_price(ex, asset)
                value = amount * price if price else 0
                st.write(f"{asset}: {amount:.6f} ≈ ${value:.2f}")
            add_usdt = st.number_input(f"Пополнить USDT на {ex.upper()}", min_value=0.0, step=100.0, key=f"add_{ex}")
            if st.button(f"➕ Добавить {add_usdt} USDT", key=f"btn_{ex}"):
                if add_usdt > 0:
                    st.session_state.user_balances[ex]['USDT'] += add_usdt
                    save_demo_balances(st.session_state.user_id, st.session_state.user_balances)
                    st.success(f"Добавлено {add_usdt} USDT на биржу {ex.upper()}")
                    st.rerun()

# TAB 6: Вывод
with tabs[6]:
    st.subheader("💰 Вывод средств")
    st.write(f"**Доступно для вывода:** {st.session_state.withdrawable_balance:.2f} USDT")
    weekday = datetime.now().strftime("%A")
    disabled = weekday not in ["Tuesday", "Friday"]
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
            save_demo_history(st.session_state.user_id, [])
            st.rerun()
    else:
        st.info("Нет сделок")

# TAB 8: Кабинет
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
        if first_ex not in st.session_state.user_balances:
            st.session_state.user_balances[first_ex] = {"USDT": DEMO_USDT_PER_EXCHANGE, "portfolio": DEFAULT_PORTFOLIO.copy()}
        st.session_state.user_balances[first_ex]['USDT'] += 1000
        save_demo_balances(st.session_state.user_id, st.session_state.user_balances)
        st.success("Добавлено 1000 USDT на биржу " + first_ex.upper())
        st.rerun()

# TAB 9: Чат
with tabs[9]:
    st.subheader("💬 Чат с поддержкой")
    if is_admin(st.session_state.email):
        msgs = get_messages(limit=100)
        for msg in msgs:
            uname = msg.get('user_name', 'Пользователь')
            uemail = msg.get('user_email', '')
            st.markdown(f"**{uname}** ({uemail}) - {msg['created_at'][:16]}")
            st.write(msg['message'])
            if not msg.get('is_admin_reply', False):
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
        a1, a2, a3, a4, a5, a6, a7 = st.tabs(["👥 Участники", "📊 Токены", "⚙ Пороги", "🔐 API ключи", "📜 Все сделки", "💰 Заявки", "🔄 Сброс демо"])
        with a1:
            users = get_all_users_for_admin()
            if users:
                df = pd.DataFrame([{
                    "Email": u['email'], "Имя": u['full_name'], "Статус": u['registration_status'],
                    "Прибыль": f"${u.get('total_profit', 0):.2f}", "Сделок": u.get('trade_count', 0)
                } for u in users])
                st.dataframe(df, use_container_width=True, hide_index=True)
                emails = {u['email']: u['id'] for u in users}
                sel = st.selectbox("Выберите пользователя для просмотра", list(emails.keys()))
                if sel:
                    if st.button(f"Смотреть страницу пользователя {sel}"):
                        st.session_state.viewed_user_id = emails[sel]
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
            st.write("### Настройка порогов")
            new_th = {}
            new_th['min_spread_percent'] = st.slider("Мин. чистый спред (%)", 0.0005, 0.5, thresholds['min_spread_percent'], 0.0005, format="%.4f")
            new_th['fee_percent'] = st.number_input("Комиссия тейкера (%)", 0.0, 0.5, thresholds['fee_percent'], 0.01, format="%.2f")
            new_th['slippage_percent'] = st.number_input("Проскальзывание (%)", 0.0, 1.0, thresholds['slippage_percent'], 0.05, format="%.2f")
            new_th['min_24h_volume_usdt'] = st.number_input("Мин. 24h объём (USDT)", 0, 1000000, thresholds['min_24h_volume_usdt'], 10000)
            new_th['max_withdrawal_fee_percent'] = st.number_input("Макс. комиссия вывода (% от прибыли)", 0, 100, thresholds['max_withdrawal_fee_percent'], 5)
            if st.button("Сохранить"):
                set_thresholds(new_th)
                st.success("Пороги обновлены. Перезагрузите страницу.")
                st.rerun()
        with a4:
            api_keys = get_all_api_keys()
            for ex in EXCHANGES:
                with st.expander(f"🔑 {ex.upper()}"):
                    cur = api_keys.get(ex, {})
                    cur_api = decrypt_api_key(cur.get('api_key', ''))
                    cur_sec = decrypt_api_key(cur.get('secret_key', ''))
                    new_api = st.text_input(f"API Key", value=cur_api, type="password", key=f"api_{ex}")
                    new_sec = st.text_input(f"Secret Key", value=cur_sec, type="password", key=f"sec_{ex}")
                    col1, col2 = st.columns(2)
                    if col1.button(f"Проверить {ex.upper()}", key=f"test_{ex}"):
                        if new_api and new_sec:
                            try:
                                ex_cls = getattr(ccxt, ex)
                                test_ex = ex_cls({'apiKey': new_api, 'secret': new_sec, 'enableRateLimit': True})
                                test_ex.fetch_balance()
                                st.success("Ключи действительны")
                            except Exception as e:
                                st.error(f"Ошибка: {str(e)[:100]}")
                    if col2.button(f"Сохранить {ex.upper()}", key=f"save_{ex}"):
                        save_api_key(ex, new_api, new_sec, st.session_state.email)
                        st.session_state.api_keys = get_all_api_keys()
                        st.success("Сохранено")
                        st.rerun()
        with a5:
            trades = get_all_trades(200)
            if trades:
                df = pd.DataFrame([{"Пользователь": t.get('users', {}).get('email', ''), "Токен": t['asset'], "Прибыль": f"${t['profit']:.2f}", "Время": t['trade_time']} for t in trades])
                st.dataframe(df, use_container_width=True, hide_index=True)
        with a6:
            pend = get_pending_withdrawals()
            for w in pend:
                st.write(f"{w.get('users', {}).get('email', '')} — {w['amount']} USDT (клиент получит {w['user_receives']:.2f})")
                if st.button(f"Выполнить", key=f"comp_{w['id']}"):
                    update_withdrawal_status(w['id'], 'completed', st.session_state.email)
                    st.rerun()
        with a7:
            st.warning("Сброс демо-данных пользователя")
            users_list = get_all_users_for_admin()
            user_options = {u['email']: u['id'] for u in users_list}
            sel_user = st.selectbox("Выберите пользователя", list(user_options.keys()))
            if st.button("Сбросить демо-данные"):
                uid = user_options[sel_user]
                reset_demo_data(uid)
                st.success(f"Данные {sel_user} сброшены")
                st.rerun()

st.caption(f"🚀 Сканируется {len(get_available_tokens())} токенов на {len(EXCHANGES)} биржах | Авто-интервал: {SCAN_INTERVAL} сек | Режим: {st.session_state.current_mode}")
