import streamlit as st
import time
import json
import ccxt
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime
import threading
import hashlib
import base64
from supabase import create_client, Client

st.set_page_config(
    page_title="Арбитражный бот HOVMEL",
    page_icon="🔄",
    layout="wide",
    initial_sidebar_state="collapsed"
)

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
    text-shadow: 0 0 15px rgba(255,215,0,0.5);
    text-align: center;
}
.hovmel-highlight {
    background: linear-gradient(120deg, #FFD700, #FF8C00);
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
    font-weight: 900;
}
.subtitle {
    text-align: center;
    color: #aaa;
    margin-top: -0.8rem;
    margin-bottom: 1.5rem;
}
.status-indicator {
    display: inline-block;
    width: 12px;
    height: 12px;
    border-radius: 50%;
    margin-right: 6px;
}
.status-running { background-color: #00FF88; box-shadow: 0 0 8px #00FF88; }
.status-stopped { background-color: #FF4444; box-shadow: 0 0 8px #FF4444; }
</style>
""", unsafe_allow_html=True)

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

DEFAULT_FEE_PERCENT = 0.1
DEFAULT_MIN_PROFIT_USDT = 0.01   # <-- Уменьшил, чтобы арбитраж находился
DEFAULT_MIN_TRADE_USDT = 12.0
DEFAULT_MAX_TRADE_USDT = 15.0
DEFAULT_SCAN_INTERVAL = 10

# ---------- ФУНКЦИИ SUPABASE (без изменений) ----------
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

# ---------- ПУБЛИЧНЫЕ КЛИЕНТЫ ----------
@st.cache_resource
def init_public_clients():
    clients = {}
    status = {}
    for ex_name in EXCHANGES:
        try:
            exchange_class = getattr(ccxt, ex_name)
            ex = exchange_class({'enableRateLimit': True, 'options': {'defaultType': 'spot'}})
            ex.fetch_ticker("BTC/USDT")
            clients[ex_name] = ex
            status[ex_name] = "ok"
        except Exception as e:
            status[ex_name] = f"error: {str(e)[:50]}"
    return clients, status

@st.cache_resource
def init_real_exchanges():
    exchanges = {}
    status = {}
    api_keys = get_all_api_keys()
    for ex_name in EXCHANGES:
        try:
            api_data = api_keys.get(ex_name, {})
            api_key = decrypt_api_key(api_data.get('api_key', ''))
            secret_key = decrypt_api_key(api_data.get('secret_key', ''))
            if not api_key or not secret_key:
                status[ex_name] = "no_api"
                continue
            exchange_class = getattr(ccxt, ex_name)
            ex = exchange_class({'apiKey': api_key, 'secret': secret_key, 'enableRateLimit': True, 'options': {'defaultType': 'spot'}})
            ex.load_markets()
            status[ex_name] = "connected"
            exchanges[ex_name] = ex
        except Exception as e:
            status[ex_name] = f"error: {str(e)[:50]}"
    return exchanges, status

def get_price(exchange, symbol):
    try:
        ticker = exchange.fetch_ticker(f"{symbol}/USDT")
        return ticker['last']
    except:
        return None

# ---------- ДЕМО-ФУНКЦИИ ----------
def get_demo_balance(exchange_name, asset):
    bal = st.session_state.user_data['balances'].get(exchange_name, {})
    if asset == 'USDT':
        return bal.get('USDT', 0.0)
    else:
        return bal.get('portfolio', {}).get(asset, 0.0)

def update_demo_balance(exchange_name, asset, delta):
    if exchange_name not in st.session_state.user_data['balances']:
        st.session_state.user_data['balances'][exchange_name] = {"USDT": 0.0, "portfolio": {t: 0.0 for t in TOKENS}}
    if asset == 'USDT':
        st.session_state.user_data['balances'][exchange_name]['USDT'] += delta
    else:
        if asset not in st.session_state.user_data['balances'][exchange_name]['portfolio']:
            st.session_state.user_data['balances'][exchange_name]['portfolio'][asset] = 0.0
        st.session_state.user_data['balances'][exchange_name]['portfolio'][asset] += delta
    save_user_data(st.session_state.user_id, st.session_state.user_data)

def execute_demo_buy(exchange_name, token, usdt_amount):
    price = get_price(st.session_state.public_clients.get(exchange_name), token)
    if not price:
        return False, "Не удалось получить цену", None
    amount_token = usdt_amount / price
    usdt_current = get_demo_balance(exchange_name, 'USDT')
    if usdt_current < usdt_amount:
        return False, f"Недостаточно USDT (есть {usdt_current:.2f})", None
    update_demo_balance(exchange_name, 'USDT', -usdt_amount)
    update_demo_balance(exchange_name, token, amount_token)
    return True, f"Куплено {amount_token:.8f} {token} за {usdt_amount:.2f} USDT", None

def execute_demo_sell(exchange_name, token, amount_token):
    price = get_price(st.session_state.public_clients.get(exchange_name), token)
    if not price:
        return False, "Не удалось получить цену", None
    token_current = get_demo_balance(exchange_name, token)
    if token_current < amount_token:
        return False, f"Недостаточно {token} (есть {token_current:.8f})", None
    usdt_received = amount_token * price
    update_demo_balance(exchange_name, token, -amount_token)
    update_demo_balance(exchange_name, 'USDT', usdt_received)
    return True, f"Продано {amount_token:.8f} {token} за {usdt_received:.2f} USDT", None

# ---------- РЕАЛЬНЫЕ ФУНКЦИИ ----------
def get_real_balance(exchange, asset):
    try:
        balance = exchange.fetch_balance()
        if asset == 'USDT':
            return balance.get('USDT', {}).get('free', 0.0)
        else:
            return balance.get(asset, {}).get('free', 0.0)
    except:
        return 0.0

def get_real_balances_all():
    balances = {}
    for ex_name, ex in st.session_state.real_exchanges.items():
        try:
            balance = ex.fetch_balance()
            balances[ex_name] = {
                'USDT': balance.get('USDT', {}).get('free', 0.0),
                'portfolio': {}
            }
            for token in get_available_tokens():
                balances[ex_name]['portfolio'][token] = balance.get(token, {}).get('free', 0.0)
        except Exception:
            balances[ex_name] = {'USDT': 0.0, 'portfolio': {t: 0.0 for t in TOKENS}}
    return balances

def update_real_balance_in_db(user_id):
    real_balances = get_real_balances_all()
    st.session_state.user_data['balances'] = real_balances
    save_user_data(user_id, st.session_state.user_data)
    return real_balances

def execute_real_buy(exchange_name, token, usdt_amount):
    ex = st.session_state.real_exchanges.get(exchange_name)
    if not ex:
        return False, "Биржа не подключена", None
    try:
        ticker = ex.fetch_ticker(f"{token}/USDT")
        price = ticker['last']
        amount = usdt_amount / price
        order = ex.create_market_buy_order(f"{token}/USDT", amount)
        update_real_balance_in_db(st.session_state.user_id)
        return True, f"Куплено {amount:.8f} {token} за {usdt_amount:.2f} USDT", order
    except Exception as e:
        return False, f"Ошибка: {str(e)}", None

def execute_real_sell(exchange_name, token, amount_token):
    ex = st.session_state.real_exchanges.get(exchange_name)
    if not ex:
        return False, "Биржа не подключена", None
    try:
        ticker = ex.fetch_ticker(f"{token}/USDT")
        price = ticker['last']
        order = ex.create_market_sell_order(f"{token}/USDT", amount_token)
        update_real_balance_in_db(st.session_state.user_id)
        usdt_received = amount_token * price
        return True, f"Продано {amount_token:.8f} {token} за {usdt_received:.2f} USDT", order
    except Exception as e:
        return False, f"Ошибка: {str(e)}", None

# ---------- АРБИТРАЖ ----------
def find_best_opportunity(mode, fee_percent, min_profit_usdt, min_trade_usdt, max_trade_usdt):
    opportunities = []
    if not st.session_state.public_clients:
        return None
    tokens = get_available_tokens()
    prices = {}
    for ex_name, ex in st.session_state.public_clients.items():
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
                if mode == "Реальный":
                    if buy_ex not in st.session_state.real_exchanges or sell_ex not in st.session_state.real_exchanges:
                        continue
                    usdt_on_buy = get_real_balance(st.session_state.real_exchanges[buy_ex], 'USDT')
                    token_on_sell = get_real_balance(st.session_state.real_exchanges[sell_ex], token)
                else:
                    usdt_on_buy = get_demo_balance(buy_ex, 'USDT')
                    token_on_sell = get_demo_balance(sell_ex, token)
                max_by_usdt = usdt_on_buy
                max_by_token = token_on_sell * sell_price
                max_possible = min(max_by_usdt, max_by_token)
                if max_possible < min_trade_usdt:
                    continue
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
                    'token': token, 'buy_ex': buy_ex, 'sell_ex': sell_ex,
                    'buy_price': buy_price, 'sell_price': sell_price,
                    'trade_usdt': trade_usdt, 'amount': amount,
                    'profit': profit_after, 'usdt_available': usdt_on_buy,
                    'token_available': token_on_sell
                })
    if not opportunities:
        return None
    return max(opportunities, key=lambda x: x['profit'])

def execute_trade(mode, opp):
    buy_ex = opp['buy_ex']; sell_ex = opp['sell_ex']
    token = opp['token']; amount = opp['amount']
    trade_usdt = opp['trade_usdt']; sell_price = opp['sell_price']
    if mode == "Реальный":
        success_buy, msg_buy, _ = execute_real_buy(buy_ex, token, trade_usdt)
        if not success_buy:
            return None, f"Ошибка покупки: {msg_buy}"
        success_sell, msg_sell, _ = execute_real_sell(sell_ex, token, amount)
        if not success_sell:
            return None, f"Ошибка продажи: {msg_sell}"
    else:
        success_buy, msg_buy, _ = execute_demo_buy(buy_ex, token, trade_usdt)
        if not success_buy:
            return None, f"Ошибка покупки: {msg_buy}"
        success_sell, msg_sell, _ = execute_demo_sell(sell_ex, token, amount)
        if not success_sell:
            return None, f"Ошибка продажи: {msg_sell}"
    usdt_received = amount * sell_price
    real_profit = usdt_received - trade_usdt
    st.session_state.user_data['total_profit'] += real_profit
    st.session_state.user_data['trade_count'] += 1
    entry = f"✅ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | {token} | {buy_ex}→{sell_ex} | {amount:.8f} | +{real_profit:.2f} USDT | {mode}"
    st.session_state.user_data['history'].append(entry)
    save_user_data(st.session_state.user_id, st.session_state.user_data)
    add_trade(st.session_state.user_id, mode, token, amount, real_profit, buy_ex, sell_ex)
    return real_profit, None

# ---------- ФОНОВЫЙ ПОТОК (исправлен) ----------
def background_arbitrage_loop():
    while True:
        try:
            # Принудительно считываем состояние
            auto = st.session_state.get('auto_trade_enabled', False)
            mode = st.session_state.get('trade_mode', "Демо")
            fee = st.session_state.get('fee_percent', DEFAULT_FEE_PERCENT)
            min_profit = st.session_state.get('min_profit_usdt', DEFAULT_MIN_PROFIT_USDT)
            min_trade = st.session_state.get('min_trade_usdt', DEFAULT_MIN_TRADE_USDT)
            max_trade = st.session_state.get('max_trade_usdt', DEFAULT_MAX_TRADE_USDT)
            
            if auto:
                if 'auto_log' not in st.session_state:
                    st.session_state.auto_log = []
                opp = find_best_opportunity(mode, fee, min_profit, min_trade, max_trade)
                if opp:
                    st.session_state.auto_log.append(
                        f"🔍 {mode} | {opp['token']} {opp['buy_ex']}→{opp['sell_ex']} | "
                        f"прибыль {opp['profit']:.4f} USDT | сумма {opp['trade_usdt']:.2f} USDT"
                    )
                    profit, error = execute_trade(mode, opp)
                    if profit:
                        st.session_state.auto_log.append(f"✅ {mode} сделка: +{profit:.2f} USDT")
                    elif error:
                        st.session_state.auto_log.append(f"❌ {mode} ошибка: {error}")
                # else: не спамим лог
                time.sleep(st.session_state.get('scan_interval', DEFAULT_SCAN_INTERVAL))
            else:
                time.sleep(5)
        except Exception as e:
            if 'auto_log' in st.session_state:
                st.session_state.auto_log.append(f"⚠️ Ошибка фона: {e}")
            time.sleep(5)

# ---------- ИНИЦИАЛИЗАЦИЯ СЕССИИ ----------
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = None
    st.session_state.email = None
    st.session_state.wallet_address = ''
    st.session_state.public_clients = None
    st.session_state.real_exchanges = None
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
    st.session_state.trade_mode = "Демо"

if st.session_state.public_clients is None:
    with st.spinner("Подключение к биржам для получения цен..."):
        st.session_state.public_clients, pub_status = init_public_clients()
        st.session_state.exchange_status = pub_status

if st.session_state.real_exchanges is None and st.session_state.trade_mode == "Реальный":
    with st.spinner("Подключение реальных бирж с API..."):
        st.session_state.real_exchanges, real_status = init_real_exchanges()
        for ex, sts in real_status.items():
            st.session_state.exchange_status[ex] = sts

if 'background_thread_started' not in st.session_state:
    threading.Thread(target=background_arbitrage_loop, daemon=True).start()
    st.session_state.background_thread_started = True
    st.session_state.auto_log = []

# ---------- ХЕДЕР ----------
st.markdown('<div class="main-header"><h1>Арбитражный бот <span class="hovmel-highlight">HOVMEL</span></h1></div><div class="subtitle">⚡ Автоматический поиск межбиржевого арбитража ⚡</div>', unsafe_allow_html=True)

# ---------- ЛОГИН/РЕГИСТРАЦИЯ ----------
if not st.session_state.logged_in:
    tab_reg, tab_login = st.tabs(["📝 Регистрация", "🔑 Вход"])
    with tab_reg:
        with st.form("register_form"):
            username = st.text_input("Имя")
            email = st.text_input("Email")
            country = st.text_input("Страна")
            city = st.text_input("Город")
            phone = st.text_input("Телефон")
            wallet = st.text_input("Адрес USDT (TRC20)")
            pwd = st.text_input("Пароль", type="password")
            pwd2 = st.text_input("Повтор пароля", type="password")
            if st.form_submit_button("Зарегистрироваться", use_container_width=True):
                if username and email and wallet and pwd and pwd == pwd2:
                    if get_user_by_email(email):
                        st.error("Email уже существует")
                    else:
                        create_user(email, pwd, username, country, city, phone, wallet)
                        st.success("Регистрация успешна! Теперь войдите.")
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
                        st.rerun()
                    else:
                        st.error("Доступ запрещён")
                else:
                    st.error("Неверный email или пароль")
    st.stop()

if st.session_state.user_id and st.session_state.user_data:
    save_user_data(st.session_state.user_id, st.session_state.user_data)

# ---------- ВЕРХНЯЯ ПАНЕЛЬ ----------
col_logo, col_status, col_mode, col_logout = st.columns([2, 1, 1, 1])
with col_logo:
    st.markdown(f"👤 {st.session_state.username} | 📧 {st.session_state.email}")
with col_status:
    if st.session_state.auto_trade_enabled:
        st.markdown('<span class="status-indicator status-running"></span> **АВТО-СДЕЛКИ АКТИВНЫ**', unsafe_allow_html=True)
    else:
        st.markdown('<span class="status-indicator status-stopped"></span> **АВТО-СДЕЛКИ ОСТАНОВЛЕНЫ**', unsafe_allow_html=True)
with col_mode:
    mode_color = "green" if st.session_state.trade_mode == "Реальный" else "orange"
    st.markdown(f'🎯 **{st.session_state.trade_mode} режим**', unsafe_allow_html=True)
with col_logout:
    if st.button("🚪 Выйти"):
        st.session_state.logged_in = False
        st.session_state.auto_trade_enabled = False
        st.rerun()

connected_pub = [ex.upper() for ex, sts in st.session_state.exchange_status.items() if sts == "ok"]
if connected_pub:
    st.success(f"🔌 Биржи для мониторинга цен: {', '.join(connected_pub)}")
else:
    st.error("Нет подключения ни к одной бирже для получения цен")
st.divider()

# ---------- ДЕМО-ПОПОЛНЕНИЕ ----------
if st.session_state.trade_mode == "Демо":
    with st.expander("💰 Пополнение демо-балансов"):
        col1, col2, col3 = st.columns(3)
        with col1:
            demo_exchange = st.selectbox("Биржа", EXCHANGES, key="demo_ex")
        with col2:
            asset_type = st.selectbox("Актив", ["USDT"] + get_available_tokens(), key="demo_asset")
        with col3:
            amount_demo = st.number_input("Количество", min_value=0.0, step=10.0, key="demo_amount")
        if st.button("➕ Пополнить демо-баланс"):
            if amount_demo > 0:
                update_demo_balance(demo_exchange, asset_type, amount_demo)
                st.success(f"Добавлено {amount_demo} {asset_type} на {demo_exchange.upper()}")
                st.rerun()
        st.info("💡 Вы можете добавить USDT или любые токены для тестирования арбитража.")

# ---------- РАСЧЁТ ОБЩИХ БАЛАНСОВ ----------
def compute_total_capital():
    if st.session_state.trade_mode == "Реальный" and st.session_state.real_exchanges:
        balances = get_real_balances_all()
    else:
        balances = st.session_state.user_data['balances']
    total_usdt = sum(balances.get(ex, {}).get('USDT', 0) for ex in EXCHANGES)
    total_portfolio = 0
    for ex, bal in balances.items():
        for token, amt in bal.get('portfolio', {}).items():
            if amt > 0 and st.session_state.public_clients.get(ex):
                price = get_price(st.session_state.public_clients[ex], token)
                if price:
                    total_portfolio += amt * price
    return total_usdt, total_portfolio, total_usdt + total_portfolio

total_usdt, total_portfolio, total_capital = compute_total_capital()

if st.session_state.trade_mode == "Реальный" and st.session_state.real_exchanges:
    st.info(f"💰 **Реальные балансы** | USDT: {total_usdt:.2f} | Портфель: {total_portfolio:.2f} | Капитал: {total_capital:.2f}")
    if st.button("🔄 Обновить реальные балансы"):
        update_real_balance_in_db(st.session_state.user_id)
        st.rerun()
else:
    st.info(f"🎮 **Демо-балансы** | USDT: {total_usdt:.2f} | Портфель: {total_portfolio:.2f} | Капитал: {total_capital:.2f}")

col1, col2, col3, col4 = st.columns(4)
col1.metric("💰 USDT на биржах", f"{total_usdt:.2f}")
col2.metric("📦 Портфель (токены)", f"{total_portfolio:.2f}")
col3.metric("💎 Общий капитал", f"{total_capital:.2f}")
col4.metric("📊 Сделок", st.session_state.user_data['trade_count'])

c1, c2, c3, c4 = st.columns(4)
with c1:
    if st.button("▶ СТАРТ АВТО", use_container_width=True):
        st.session_state.auto_trade_enabled = True
        st.rerun()
with c2:
    if st.button("⏹ СТОП АВТО", use_container_width=True):
        st.session_state.auto_trade_enabled = False
        st.rerun()
with c3:
    if st.button("🔄 Обновить интерфейс", use_container_width=True):
        st.rerun()
with c4:
    new_mode = st.selectbox("Режим торговли", ["Демо", "Реальный"], index=0 if st.session_state.trade_mode == "Демо" else 1)
    if new_mode != st.session_state.trade_mode:
        st.session_state.trade_mode = new_mode
        if new_mode == "Реальный" and st.session_state.real_exchanges is None:
            with st.spinner("Подключение реальных бирж..."):
                st.session_state.real_exchanges, _ = init_real_exchanges()
        st.rerun()

with st.expander("⚙️ Настройки арбитража"):
    st.session_state.fee_percent = st.number_input("Комиссия (%)", 0.0, 0.5, st.session_state.fee_percent, 0.01, format="%.2f")
    st.session_state.min_profit_usdt = st.number_input("Мин. прибыль (USDT)", 0.001, 10.0, st.session_state.min_profit_usdt, 0.01, format="%.3f")
    st.session_state.min_trade_usdt = st.number_input("Мин. сумма сделки (USDT)", 10.0, 15.0, st.session_state.min_trade_usdt, 1.0)
    st.session_state.max_trade_usdt = st.number_input("Макс. сумма сделки (USDT)", 12.0, 15.0, st.session_state.max_trade_usdt, 1.0)
    st.session_state.scan_interval = st.number_input("Интервал (сек)", 5, 60, st.session_state.scan_interval, 5)
    st.info("💡 Сумма сделки автоматически ограничивается 12-15 USDT в зависимости от доступных средств.")

with st.expander("📋 Лог авто-торговли"):
    if st.session_state.auto_log:
        for log in st.session_state.auto_log[-20:]:
            st.text(log)
    else:
        st.info("Нет событий. Запустите авто-торговлю.")

# ---------- ВКЛАДКИ ----------
show_admin = is_admin(st.session_state.email)
tabs_list = ["📊 Dashboard", "📈 Графики", "🔄 Арбитраж", "📊 Статистика", "📈 Доходность", "💼 Балансы", "💰 Вывод", "📜 История", "👤 Кабинет", "💬 Чат"]
if show_admin:
    tabs_list.append("👑 Админ-панель")
tabs = st.tabs(tabs_list)

# ---------- DASHBOARD ----------
with tabs[0]:
    st.subheader("📊 Dashboard")
    st.write("Добро пожаловать в арбитражного бота **HOVMEL**.")
    st.write("Используйте раздел «Балансы» для ручной покупки/продажи токенов.")

# ---------- ГРАФИКИ ----------
with tabs[1]:
    st.subheader("📈 Графики цен")
    token_choice = st.selectbox("Выберите токен", get_available_tokens())
    if token_choice:
        data = []
        for ex_name, ex in st.session_state.public_clients.items():
            price = get_price(ex, token_choice)
            if price:
                data.append({'Биржа': ex_name.upper(), 'Цена (USDT)': price})
        if data:
            df = pd.DataFrame(data)
            fig = px.bar(df, x='Биржа', y='Цена (USDT)', title=f"Цена {token_choice}/USDT", color='Биржа')
            st.plotly_chart(fig, use_container_width=True)

# ---------- АРБИТРАЖ ----------
with tabs[2]:
    st.subheader("🔄 Ручной поиск арбитража")
    if st.button("🔍 Найти лучшую возможность"):
        opp = find_best_opportunity(st.session_state.trade_mode, st.session_state.fee_percent,
                                    st.session_state.min_profit_usdt, st.session_state.min_trade_usdt,
                                    st.session_state.max_trade_usdt)
        if opp:
            st.success(f"Найдена возможность: {opp['token']}")
            st.write(f"Покупка: {opp['buy_ex'].upper()} по {opp['buy_price']:.2f} USDT")
            st.write(f"Продажа: {opp['sell_ex'].upper()} по {opp['sell_price']:.2f} USDT")
            st.write(f"Сумма сделки: {opp['trade_usdt']:.2f} USDT")
            st.write(f"Прибыль: {opp['profit']:.4f} USDT")
            if st.button("Выполнить сделку"):
                profit, err = execute_trade(st.session_state.trade_mode, opp)
                if profit:
                    st.success(f"Сделка выполнена! Прибыль: {profit:.2f} USDT")
                    st.rerun()
                else:
                    st.error(f"Ошибка: {err}")
        else:
            st.warning("Арбитражных возможностей не найдено")

# ---------- СТАТИСТИКА ----------
with tabs[3]:
    st.subheader("📊 Статистика")
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Общая прибыль", f"{st.session_state.user_data['total_profit']:.2f} USDT")
        st.metric("Количество сделок", st.session_state.user_data['trade_count'])
    with col2:
        avg_profit = st.session_state.user_data['total_profit'] / st.session_state.user_data['trade_count'] if st.session_state.user_data['trade_count'] > 0 else 0
        st.metric("Средняя прибыль на сделку", f"{avg_profit:.2f} USDT")
    trades = get_all_trades(100)
    if trades:
        df_trades = pd.DataFrame(trades)
        df_trades['trade_time'] = pd.to_datetime(df_trades['trade_time'])
        df_trades = df_trades.sort_values('trade_time')
        df_trades['cumulative_profit'] = df_trades['profit'].cumsum()
        fig = px.line(df_trades, x='trade_time', y='cumulative_profit', title="Накопленная прибыль")
        st.plotly_chart(fig, use_container_width=True)

# ---------- ДОХОДНОСТЬ ----------
with tabs[4]:
    st.subheader("📈 Доходность")
    if st.session_state.user_data['trade_count'] > 0:
        total_invested = total_capital - st.session_state.user_data['total_profit']
        if total_invested > 0:
            roi = (st.session_state.user_data['total_profit'] / total_invested) * 100
            st.metric("ROI", f"{roi:.2f}%")
        st.metric("Абсолютная прибыль", f"{st.session_state.user_data['total_profit']:.2f} USDT")
    else:
        st.info("Нет данных о сделках")

# ---------- БАЛАНСЫ c ручной торговлей ----------
with tabs[5]:
    st.subheader("💼 Балансы и ручная торговля")
    if st.session_state.trade_mode == "Реальный" and st.session_state.real_exchanges:
        balances = get_real_balances_all()
    else:
        balances = st.session_state.user_data['balances']
    for ex in EXCHANGES:
        if ex in balances:
            with st.expander(f"{ex.upper()}"):
                usdt = balances[ex].get('USDT', 0)
                st.write(f"**USDT:** {usdt:.2f}")
                portfolio = balances[ex].get('portfolio', {})
                st.write("**Токены:**")
                for token, amount in portfolio.items():
                    if amount > 0:
                        price = get_price(st.session_state.public_clients.get(ex), token) if st.session_state.public_clients.get(ex) else None
                        value = amount * price if price else 0
                        st.write(f"  {token}: {amount:.8f} ≈ {value:.2f} USDT")
                st.markdown("---")
                # Ручная покупка
                col_buy1, col_buy2, col_buy3 = st.columns(3)
                with col_buy1:
                    token_buy = st.selectbox("Токен для покупки", get_available_tokens(), key=f"buy_token_{ex}")
                with col_buy2:
                    usdt_amount = st.number_input("Сумма в USDT", min_value=1.0, step=10.0, key=f"buy_usdt_{ex}")
                with col_buy3:
                    if st.button(f"Купить {token_buy} за USDT", key=f"buy_btn_{ex}"):
                        if st.session_state.trade_mode == "Реальный":
                            ok, msg, _ = execute_real_buy(ex, token_buy, usdt_amount)
                        else:
                            ok, msg, _ = execute_demo_buy(ex, token_buy, usdt_amount)
                        if ok:
                            st.session_state.user_data['trade_count'] += 1
                            entry = f"🟢 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Ручная покупка {token_buy} на {ex.upper()} на {usdt_amount} USDT"
                            st.session_state.user_data['history'].append(entry)
                            save_user_data(st.session_state.user_id, st.session_state.user_data)
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)
                # Ручная продажа
                col_sell1, col_sell2, col_sell3 = st.columns(3)
                with col_sell1:
                    token_sell = st.selectbox("Токен для продажи", get_available_tokens(), key=f"sell_token_{ex}")
                with col_sell2:
                    token_amount = st.number_input("Количество токенов", min_value=0.000001, step=0.001, format="%.6f", key=f"sell_amount_{ex}")
                with col_sell3:
                    if st.button(f"Продать {token_sell}", key=f"sell_btn_{ex}"):
                        if st.session_state.trade_mode == "Реальный":
                            ok, msg, _ = execute_real_sell(ex, token_sell, token_amount)
                        else:
                            ok, msg, _ = execute_demo_sell(ex, token_sell, token_amount)
                        if ok:
                            st.session_state.user_data['trade_count'] += 1
                            entry = f"🔴 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Ручная продажа {token_sell} на {ex.upper()} {token_amount:.6f} шт"
                            st.session_state.user_data['history'].append(entry)
                            save_user_data(st.session_state.user_id, st.session_state.user_data)
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)
    if st.session_state.trade_mode == "Реальный":
        st.divider()
        if st.button("🔄 Обновить реальные балансы", use_container_width=True):
            update_real_balance_in_db(st.session_state.user_id)
            st.rerun()

# ---------- ВЫВОД ----------
with tabs[6]:
    st.subheader("💰 Вывод средств")
    st.info("Вывод возможен только после одобрения администратором (комиссия 22%).")
    withdrawable = st.session_state.user_data.get('withdrawable_balance', 0.0)
    if not isinstance(withdrawable, (int, float)):
        withdrawable = 0.0
    st.write(f"Доступно для вывода: **{withdrawable:.2f} USDT**")
    amount = st.number_input("Сумма вывода (USDT)", min_value=1.0, max_value=max(1.0, withdrawable), step=10.0)
    wallet = st.text_input("Адрес USDT (TRC20)", value=st.session_state.wallet_address)
    if st.button("Запросить вывод"):
        if amount > 0 and wallet:
            create_withdrawal_request(st.session_state.user_id, amount, wallet)
            st.success("Заявка на вывод отправлена администратору!")
        else:
            st.error("Введите корректную сумму и адрес")

# ---------- ИСТОРИЯ ----------
with tabs[7]:
    st.subheader("📜 История сделок")
    history = st.session_state.user_data['history'][-50:]
    if history:
        for h in reversed(history):
            st.text(h)
    else:
        st.info("Сделок пока нет")

# ---------- КАБИНЕТ (с общим капиталом) ----------
with tabs[8]:
    st.subheader("👤 Личный кабинет")
    col1, col2 = st.columns(2)
    with col1:
        st.write(f"**Имя:** {st.session_state.username}")
        st.write(f"**Email:** {st.session_state.email}")
        st.write(f"**Кошелёк:** {st.session_state.wallet_address}")
    with col2:
        st.write(f"**Всего сделок:** {st.session_state.user_data['trade_count']}")
        st.write(f"**Общая прибыль:** {st.session_state.user_data['total_profit']:.2f} USDT")
        st.write(f"**💎 Общий капитал (USDT):** {total_capital:.2f}")

# ---------- ЧАТ ----------
with tabs[9]:
    st.subheader("💬 Чат поддержки")
    if st.session_state.chat_unread > 0:
        st.info(f"📬 У вас {st.session_state.chat_unread} непрочитанных сообщений от администратора")
    messages = get_messages(st.session_state.user_id, 50)
    for msg in reversed(messages):
        if msg['is_admin_reply']:
            st.markdown(f"**🛡️ Админ:** {msg['message']}  \n*{msg['created_at'][:16]}*")
        else:
            st.markdown(f"**👤 {msg['user_name']}:** {msg['message']}  \n*{msg['created_at'][:16]}*")
    with st.form("chat_form"):
        new_msg = st.text_area("Ваше сообщение")
        if st.form_submit_button("Отправить"):
            if new_msg:
                add_message(st.session_state.user_id, st.session_state.email, st.session_state.username, new_msg, False)
                st.rerun()
    mark_messages_read(st.session_state.user_id)
    st.session_state.chat_unread = 0

# ---------- АДМИН-ПАНЕЛЬ ----------
if show_admin:
    with tabs[10]:
        st.subheader("👑 Административная панель")
        admin_tabs = st.tabs(["Пользователи", "API ключи", "Выводы", "Конфиг", "Сообщения"])
        with admin_tabs[0]:
            st.markdown("#### Управление пользователями")
            users = get_all_users_for_admin()
            for user in users:
                with st.expander(f"{user['email']} - {user['full_name']}"):
                    st.write(f"Статус: {user['registration_status']}")
                    st.write(f"Баланс для вывода: {user.get('withdrawable_balance', 0)} USDT")
                    st.write(f"Сделок: {user.get('trade_count', 0)}")
                    new_status = st.selectbox("Изменить статус", ["approved", "blocked"], key=f"status_{user['id']}")
                    if st.button("Обновить", key=f"update_{user['id']}"):
                        update_user_status(user['id'], new_status, st.session_state.email)
                        st.rerun()
        with admin_tabs[1]:
            st.markdown("#### API ключи бирж")
            for ex in EXCHANGES:
                with st.expander(f"{ex.upper()}"):
                    api_key = st.text_input(f"API Key ({ex})", type="password", key=f"api_{ex}")
                    secret = st.text_input(f"Secret Key ({ex})", type="password", key=f"secret_{ex}")
                    if st.button(f"Сохранить {ex}", key=f"save_{ex}"):
                        save_api_key(ex, api_key, secret, st.session_state.email)
                        st.success(f"Ключи для {ex} сохранены")
                        st.session_state.real_exchanges = None
                        st.rerun()
        with admin_tabs[2]:
            st.markdown("#### Заявки на вывод")
            withdrawals = get_pending_withdrawals()
            for w in withdrawals:
                with st.expander(f"{w['users']['email']} - {w['amount']} USDT"):
                    st.write(f"Сумма: {w['amount']} USDT, комиссия 22%: {w['admin_fee']:.2f}, к получению: {w['user_receives']:.2f}")
                    st.write(f"Кошелёк: {w['wallet_address']}")
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button("✅ Одобрить", key=f"approve_{w['id']}"):
                            update_withdrawal_status(w['id'], 'approved', st.session_state.email)
                            st.rerun()
                    with col2:
                        if st.button("❌ Отклонить", key=f"reject_{w['id']}"):
                            update_withdrawal_status(w['id'], 'rejected', st.session_state.email)
                            st.rerun()
        with admin_tabs[3]:
            st.markdown("#### Конфигурация токенов")
            current_tokens = get_available_tokens()
            tokens_input = st.text_area("Список токенов (через запятую)", value=", ".join(current_tokens))
            if st.button("Сохранить токены"):
                new_tokens = [t.strip().upper() for t in tokens_input.split(",") if t.strip()]
                if new_tokens:
                    set_config('tokens', new_tokens)
                    st.success("Список токенов обновлён")
                    st.rerun()
        with admin_tabs[4]:
            st.markdown("#### Сообщения пользователей")
            all_messages = get_messages(limit=100)
            for msg in all_messages:
                if not msg['is_admin_reply']:
                    st.markdown(f"**{msg['user_name']}** ({msg['user_email']}): {msg['message']}  \n*{msg['created_at'][:16]}*")
                    reply = st.text_area("Ответ", key=f"reply_{msg['id']}")
                    if st.button("Отправить ответ", key=f"send_{msg['id']}"):
                        add_message(msg['user_id'], msg['user_email'], "Admin", reply, True, msg['id'])
                        st.rerun()
                    st.divider()
