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

st.set_page_config(page_title="Арбитраж PRO | Реальные сделки", layout="wide", page_icon="🚀", initial_sidebar_state="collapsed")

# ---------- SUPABASE ----------
SUPABASE_URL = st.secrets.get("SUPABASE_URL")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY")
if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("❌ Нет SUPABASE_URL / SUPABASE_KEY в Secrets")
    st.stop()
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ---------- TELEGRAM ----------
TELEGRAM_BOT_TOKEN = st.secrets.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = st.secrets.get("TELEGRAM_CHAT_ID")
def send_telegram(msg):
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        try:
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                          json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"}, timeout=5)
        except:
            pass

# ---------- СТИЛИ ----------
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

# ---------- КОНСТАНТЫ ----------
DEFAULT_ASSETS = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "LINK", "SUI", "HYPE", "TON"]
MAIN_EXCHANGE = "okx"
AUX_EXCHANGES = ["gateio", "kucoin", "bybit", "mexc", "bitget", "bingx", "bitmart"]
ALL_EXCHANGES = [MAIN_EXCHANGE] + AUX_EXCHANGES

MIN_SPREAD_PERCENT = 0.1
FEE_PERCENT = 0.1
SLIPPAGE_PERCENT = 0.2
MIN_24H_VOLUME_USDT = 200000
MAX_WITHDRAWAL_FEE_PERCENT = 15

ADMIN_COMMISSION = 0.22
REINVEST_SHARE = 0.50
FIXED_SHARE = 0.50
ADMIN_EMAILS = ["cb777899@gmail.com", "admin@arbitrage.com"]

# НАСТРОЙКИ РЕАЛЬНЫХ СДЕЛОК
REAL_TRADING = False        # Включить реальные ордера (требует API ключей)
ORDER_TYPE = 'limit'        # 'limit' или 'market'
SLIPPAGE_BPS = 0.2          # проскальзывание для рыночных ордеров
REBALANCE_THRESHOLD = 0.01  # 1% отклонение от цели
REBALANCE_HOUR = 2          # в 2:00 UTC

def is_admin(email):
    return email in ADMIN_EMAILS

# ---------- ФУНКЦИИ SUPABASE (без изменений, см. предыдущие версии) ----------
def get_user_by_email(email):
    res = supabase.table('users').select('*').eq('email', email).execute()
    return res.data[0] if res.data else None

def create_user(email, pwd_hash, full_name, country, city, phone, wallet):
    demo_reserves = get_demo_usdt_reserves()
    target_portfolio = get_target_portfolio()
    data = {
        'email': email, 'password_hash': pwd_hash, 'full_name': full_name,
        'country': country, 'city': city, 'phone': phone, 'wallet_address': wallet,
        'registration_status': 'pending', 'trade_balance': 1000,
        'portfolio': json.dumps(target_portfolio), 'usdt_reserves': json.dumps(demo_reserves)
    }
    res = supabase.table('users').insert(data).execute()
    send_telegram(f"🆕 Новый пользователь: {full_name} ({email})")
    return res.data[0]['id'] if res.data else None

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
            'trade_balance': data['trade_balance'], 'withdrawable_balance': data['withdrawable_balance'],
            'total_profit': data['total_profit'], 'trade_count': data['trade_count'],
            'total_admin_fee_paid': data['total_admin_fee_paid'], 'last_withdrawal_date': data['last_withdrawal_date'],
            'portfolio': json.dumps(data['portfolio']), 'usdt_reserves': json.dumps(data['usdt_reserves']),
            'demo_daily_profits': json.dumps(data['daily_profits']), 'demo_weekly_profits': json.dumps(data['weekly_profits']),
            'demo_monthly_profits': json.dumps(data['monthly_profits']), 'demo_history': json.dumps(data['history'][-500:])
        }
    else:
        update_data = {
            'real_balance': data['trade_balance'], 'real_total_profit': data['total_profit'],
            'real_trade_count': data['trade_count'], 'real_portfolio': json.dumps(data['portfolio']),
            'real_usdt_reserves': json.dumps(data['usdt_reserves']), 'real_daily_profits': json.dumps(data['daily_profits']),
            'real_weekly_profits': json.dumps(data['weekly_profits']), 'real_monthly_profits': json.dumps(data['monthly_profits']),
            'real_history': json.dumps(data['history'][-500:])
        }
    supabase.table('users').update(update_data).eq('id', user_id).execute()

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

def get_all_users_for_admin():
    return supabase.table('users').select('*').order('created_at', desc=True).execute().data

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

def get_target_portfolio():
    pf = get_config('portfolio')
    if not pf:
        pf = {"BTC": 0.013, "ETH": 0.42, "SOL": 11.6, "BNB": 1.63, "XRP": 730, "ADA": 4166, "AVAX": 108, "LINK": 113, "SUI": 1098, "HYPE": 23.5, "TON": 10.0}
        set_config('portfolio', pf)
    return pf

def set_available_tokens(tokens):
    set_config('tokens', tokens)

def set_target_portfolio(portfolio):
    set_config('portfolio', portfolio)

def get_demo_usdt_reserves():
    res = supabase.table('demo_usdt_reserves').select('exchange, amount').execute()
    return {row['exchange']: row['amount'] for row in res.data}

def update_demo_usdt_reserve(exchange, amount):
    supabase.table('demo_usdt_reserves').upsert({'exchange': exchange, 'amount': amount}).execute()

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

# ---------- ИНИЦИАЛИЗАЦИЯ БИРЖ ----------
@st.cache_resource
def init_exchanges():
    exchanges, status = {}, {}
    for ex_name in ALL_EXCHANGES:
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

def get_24h_volume(exchange, symbol):
    try:
        ticker = exchange.fetch_ticker(f"{symbol}/USDT")
        vol = ticker.get('quoteVolume')
        if vol is None:
            vol = ticker['last'] * ticker.get('baseVolume', 0)
        return vol
    except:
        return 0

def get_withdrawal_fee(exchange, asset):
    default_fees = {
        'gateio': 1.0, 'kucoin': 1.0, 'bybit': 1.0, 'bitget': 1.0,
        'bingx': 1.0, 'mexc': 1.0, 'bitmart': 1.0, 'okx': 0.5
    }
    high_fee_assets = ['BTC', 'ETH', 'BNB']
    if asset in high_fee_assets:
        return default_fees.get(exchange, 2.0) * 2
    return default_fees.get(exchange, 1.0)

# ---------- БАЛАНСЫ И ОРДЕРА (РЕАЛЬНЫЕ И ДЕМО) ----------
def get_balance(exchange, asset, mode='free'):
    if st.session_state.current_mode == "Демо" or not REAL_TRADING:
        if exchange.name == MAIN_EXCHANGE:
            return st.session_state.user_data.get('portfolio', {}).get(asset, 0.0)
        else:
            if asset == 'USDT':
                reserves = st.session_state.user_data.get('usdt_reserves', {})
                return reserves.get(exchange.name, 0.0)
            else:
                return 0.0
    else:
        try:
            balances = exchange.fetch_balance()
            return balances[asset]['free'] if asset in balances else 0.0
        except:
            return 0.0

def update_balance(exchange, asset, delta):
    if st.session_state.current_mode == "Демо" or not REAL_TRADING:
        if exchange.name == MAIN_EXCHANGE:
            port = st.session_state.user_data.get('portfolio', {})
            port[asset] = max(0.0, port.get(asset, 0.0) + delta)
            st.session_state.user_data['portfolio'] = port
        else:
            if asset == 'USDT':
                reserves = st.session_state.user_data.get('usdt_reserves', {})
                reserves[exchange.name] = max(0.0, reserves.get(exchange.name, 0.0) + delta)
                st.session_state.user_data['usdt_reserves'] = reserves
        save_user_mode_data(st.session_state.user_id, st.session_state.current_mode, st.session_state.user_data)
    else:
        pass

def place_order(exchange, symbol, side, amount, price=None):
    if st.session_state.current_mode == "Демо" or not REAL_TRADING:
        return (f"demo_{int(time.time())}", price or 0, amount, 0.0)
    try:
        if ORDER_TYPE == 'limit' and price:
            order = exchange.create_limit_order(symbol, side, amount, price)
            time.sleep(2)
            order = exchange.fetch_order(order['id'], symbol)
            if order['status'] == 'closed':
                exec_price = order['average'] or order['price']
                filled = order['filled']
                fee = order['fee']['cost'] if order['fee'] else 0.0
                return (order['id'], exec_price, filled, fee)
            else:
                exchange.cancel_order(order['id'], symbol)
                raise Exception("Ордер не исполнился")
        else:
            order = exchange.create_market_order(symbol, side, amount)
            time.sleep(1)
            order = exchange.fetch_order(order['id'], symbol)
            exec_price = order['average'] or order['price']
            filled = order['filled']
            fee = order['fee']['cost'] if order['fee'] else 0.0
            return (order['id'], exec_price, filled, fee)
    except Exception as e:
        st.error(f"Ошибка ордера на {exchange.name}: {e}")
        return (None, 0, 0, 0)

def execute_arbitrage_trade(opp):
    asset = opp['asset']
    amount = 1.0
    aux_ex = opp['aux_exchange']
    main_ex = st.session_state.exchanges[MAIN_EXCHANGE]
    aux_ex_obj = st.session_state.exchanges[aux_ex]

    main_balance = get_balance(main_ex, asset)
    if main_balance < amount:
        st.warning(f"Недостаточно {asset} на OKX (есть {main_balance})")
        return None
    aux_usdt = get_balance(aux_ex_obj, 'USDT')
    buy_cost = opp['aux_price'] * amount
    if aux_usdt < buy_cost:
        st.warning(f"Недостаточно USDT на {aux_ex} (нужно {buy_cost:.2f})")
        return None

    sell_price = opp['main_price']
    buy_price = opp['aux_price']
    slippage_factor = 1 - (SLIPPAGE_BPS / 10000)
    if ORDER_TYPE == 'limit':
        sell_limit = sell_price
        buy_limit = buy_price
    else:
        sell_limit = None
        buy_limit = None

    with st.spinner(f"Исполнение: продажа {amount} {asset} на OKX по {sell_price:.2f}, покупка на {aux_ex} по {buy_price:.2f}"):
        sell_oid, exec_sell, filled_sell, fee_sell = place_order(main_ex, f"{asset}/USDT", 'sell', amount, sell_limit)
        if sell_oid is None or filled_sell < amount * 0.99:
            st.error("Продажа не удалась")
            return None
        buy_oid, exec_buy, filled_buy, fee_buy = place_order(aux_ex_obj, f"{asset}/USDT", 'buy', amount, buy_limit)
        if buy_oid is None or filled_buy < amount * 0.99:
            place_order(main_ex, f"{asset}/USDT", 'buy', filled_sell, exec_sell)
            return None

    profit_usdt = (exec_sell * amount - fee_sell) - (exec_buy * amount + fee_buy)
    if profit_usdt <= 0:
        st.warning(f"Прибыль {profit_usdt:.4f} USDT, откат")
        place_order(main_ex, f"{asset}/USDT", 'buy', amount, exec_sell)
        place_order(aux_ex_obj, f"{asset}/USDT", 'sell', amount, exec_buy)
        return None

    update_balance(main_ex, asset, -amount)
    update_balance(main_ex, 'USDT', profit_usdt)
    update_balance(aux_ex_obj, 'USDT', -(exec_buy * amount + fee_buy))
    st.session_state.user_data['trade_count'] += 1
    st.session_state.user_data['total_profit'] += profit_usdt
    st.session_state.user_data['history'].append(
        f"✅ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | {asset} | "
        f"Продажа OKX {exec_sell:.2f} | Покупка {aux_ex} {exec_buy:.2f} | +{profit_usdt:.2f} USDT"
    )
    send_telegram(f"💹 Сделка: {asset} +{profit_usdt:.2f} USDT")
    return profit_usdt

def get_cheapest_withdrawal_network(exchange, asset):
    if asset == 'USDT':
        networks = {
            'trc20': 1.0,
            'bep20': 0.8,
            'sol': 0.2 if exchange.name in ['bybit','gateio','kucoin'] else 999,
            'erc20': 8.0
        }
        best = min(networks.items(), key=lambda x: x[1])
        return best[0], best[1]
    else:
        return None, 999

def withdraw_to_main(exchange, asset, amount):
    if st.session_state.current_mode == "Демо" or not REAL_TRADING:
        update_balance(exchange, asset, -amount)
        update_balance(st.session_state.exchanges[MAIN_EXCHANGE], asset, amount)
        return True
    network, fee = get_cheapest_withdrawal_network(exchange, asset)
    if fee > 999:
        st.error(f"Нет сети для вывода {asset} с {exchange.name}")
        return False
    try:
        if hasattr(exchange, 'withdraw'):
            exchange.withdraw(asset, amount, st.session_state.wallet_address, params={'network': network})
            update_balance(exchange, asset, -amount)
            return True
        else:
            st.warning(f"Вывод с {exchange.name} не поддерживается")
            return False
    except Exception as e:
        st.error(f"Ошибка вывода: {e}")
        return False

def rebalance_portfolio():
    st.info("🔄 Запуск ежесуточного ребалланса...")
    target = get_target_portfolio()
    current = st.session_state.user_data.get('portfolio', {})
    for aux_name in AUX_EXCHANGES:
        if aux_name not in st.session_state.exchanges:
            continue
        aux_ex = st.session_state.exchanges[aux_name]
        for asset, target_amt in target.items():
            balance = get_balance(aux_ex, asset)
            if balance > 0.001 and balance > target_amt * REBALANCE_THRESHOLD:
                st.info(f"Переводим {balance:.6f} {asset} с {aux_name} на OKX")
                if withdraw_to_main(aux_ex, asset, balance):
                    new_amt = current.get(asset, 0) + balance
                    current[asset] = new_amt
                    st.session_state.user_data['portfolio'] = current
                    save_user_mode_data(st.session_state.user_id, st.session_state.current_mode, st.session_state.user_data)
    st.success("Ребалланс завершён")

def schedule_rebalance():
    now = datetime.utcnow()
    next_run = now.replace(hour=REBALANCE_HOUR, minute=0, second=0, microsecond=0)
    if now >= next_run:
        next_run += timedelta(days=1)
    delay = (next_run - now).total_seconds()
    threading.Timer(delay, rebalance_portfolio_and_reschedule).start()

def rebalance_portfolio_and_reschedule():
    rebalance_portfolio()
    schedule_rebalance()

# ---------- ОСНОВНЫЕ ФУНКЦИИ БОТА ----------
def find_all_arbitrage_opportunities():
    opps = []
    if not st.session_state.exchanges or MAIN_EXCHANGE not in st.session_state.exchanges:
        return opps
    tokens = get_available_tokens()
    main_prices, main_volumes = {}, {}
    for asset in tokens:
        price = get_price(st.session_state.exchanges[MAIN_EXCHANGE], asset)
        if price:
            main_prices[asset] = price
            main_volumes[asset] = get_24h_volume(st.session_state.exchanges[MAIN_EXCHANGE], asset)
    for asset in tokens:
        if asset not in main_prices or main_volumes.get(asset,0) < MIN_24H_VOLUME_USDT:
            continue
        main_price = main_prices[asset]
        for aux_ex in AUX_EXCHANGES:
            if aux_ex not in st.session_state.exchanges:
                continue
            aux_price = get_price(st.session_state.exchanges[aux_ex], asset)
            if aux_price and aux_price < main_price:
                spread_pct = (main_price - aux_price) / aux_price * 100
                net_spread = spread_pct - FEE_PERCENT - SLIPPAGE_PERCENT
                if net_spread <= MIN_SPREAD_PERCENT:
                    continue
                profit_before = main_price - aux_price - (main_price * (FEE_PERCENT/100) + aux_price*(FEE_PERCENT/100))
                if profit_before <= 0:
                    continue
                w_fee = get_withdrawal_fee(aux_ex, asset)
                if w_fee > profit_before * (MAX_WITHDRAWAL_FEE_PERCENT/100):
                    continue
                net_profit = profit_before - w_fee
                if net_profit <= 0:
                    continue
                opps.append({
                    'asset': asset, 'aux_exchange': aux_ex,
                    'main_price': main_price, 'aux_price': aux_price,
                    'spread_pct': round(spread_pct,2),
                    'profit_usdt': round(profit_before,2),
                    'withdrawal_fee': w_fee,
                    'net_profit_after_withdrawal': round(net_profit,2)
                })
    return sorted(opps, key=lambda x: x['net_profit_after_withdrawal'], reverse=True)

def get_historical_ohlcv(exchange, symbol, timeframe='1h', limit=100):
    try:
        ohlcv = exchange.fetch_ohlcv(f"{symbol}/USDT", timeframe, limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp','open','high','low','close','volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except:
        return pd.DataFrame()

# ---------- ФОНОВЫЙ ПОТОК ----------
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

if st.session_state.exchanges is None:
    with st.spinner("Подключение к биржам..."):
        st.session_state.exchanges, st.session_state.exchange_status = init_exchanges()
        st.session_state.api_keys = get_all_api_keys()

# ---------- РЕГИСТРАЦИЯ / ВХОД ----------
if not st.session_state.logged_in:
    st.markdown('<h1 class="main-header">🚀 АРБИТРАЖ PRO | РЕАЛЬНЫЕ СДЕЛКИ</h1>', unsafe_allow_html=True)
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
                        st.success("Регистрация успешна! Ожидайте одобрения.")
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
                    elif user['registration_status'] == 'pending':
                        st.warning("Заявка на одобрение")
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
    st.markdown('<h1 class="main-header">🚀 АРБИТРАЖ PRO | РЕАЛЬНЫЕ СДЕЛКИ</h1>', unsafe_allow_html=True)
with col_status:
    if st.session_state.bot_running:
        st.markdown('<div><span class="status-indicator status-running"></span> <b>РАБОТАЕТ 24/7</b></div>', unsafe_allow_html=True)
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
st.write(f"🔌 **Биржи:** {', '.join(connected[:8])}" + (f" +{len(connected)-8}" if len(connected)>8 else ""))
st.write(f"🪙 **Токены:** {', '.join(get_available_tokens())}")
st.divider()

col1,col2,col3 = st.columns(3)
col1.metric("💰 Торговый баланс", f"{st.session_state.user_data.get('trade_balance',0):.2f} USDT")
col2.metric("🏦 Доступно для вывода", f"{st.session_state.user_data.get('withdrawable_balance',0):.2f} USDT")
col3.metric("📊 Всего сделок", st.session_state.user_data.get('trade_count',0))

c1,c2,c3,c4 = st.columns(4)
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
    new_mode = st.selectbox("Режим",["Демо","Реальный"], index=0 if st.session_state.current_mode=="Демо" else 1)
    if new_mode != st.session_state.current_mode:
        save_user_mode_data(st.session_state.user_id, st.session_state.current_mode, st.session_state.user_data)
        if new_mode == "Реальный":
            has_keys = any(st.session_state.api_keys.get(ex,{}).get('api_key') for ex in ALL_EXCHANGES)
            if not has_keys:
                st.warning("⚠️ Для реального режима нужны API ключи")
                st.session_state.current_mode = "Демо"
                st.rerun()
        user = get_user_by_email(st.session_state.email)
        if user:
            st.session_state.user_data = load_user_mode_data(user, new_mode)
            st.session_state.current_mode = new_mode
            st.rerun()

if st.session_state.current_mode == "Реальный":
    has_keys = any(st.session_state.api_keys.get(ex,{}).get('api_key') for ex in ALL_EXCHANGES)
    if has_keys and REAL_TRADING:
        st.markdown('<div class="api-success">✅ Реальный режим активен (реальные ордера)</div>', unsafe_allow_html=True)
    elif has_keys and not REAL_TRADING:
        st.markdown('<div class="api-warning">⚠️ Реальный режим: API есть, но REAL_TRADING=False (только симуляция)</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="api-warning">⚠️ РЕАЛЬНЫЙ РЕЖИМ: API ключи не подключены</div>', unsafe_allow_html=True)

# ---------- ВКЛАДКИ ----------
show_admin = is_admin(st.session_state.email)
tabs_list = ["📊 Dashboard","📈 Графики","🔄 Арбитраж","📊 Доходность","📊 Статистика","📦 Портфель","💰 Кошелёк","📜 История","👤 Кабинет","💬 Чат"]
if show_admin:
    tabs_list.append("👑 Админ-панель")
tabs = st.tabs(tabs_list)

# TAB 0: Dashboard
with tabs[0]:
    st.subheader("📊 Статус сканирования")
    tokens = get_available_tokens()
    for i in range(0,len(tokens),5):
        cols = st.columns(5)
        for j,asset in enumerate(tokens[i:i+5]):
            with cols[j]:
                price = get_price(st.session_state.exchanges[MAIN_EXCHANGE], asset) if st.session_state.exchanges else None
                if price:
                    st.markdown(f"<div class='token-card'><b>{asset}</b><br><span style='font-size:18px;color:#00D4FF;'>${price:,.0f}</span></div>", unsafe_allow_html=True)
                else:
                    st.markdown(f"<div class='token-card'><b>{asset}</b><br>❌</div>", unsafe_allow_html=True)
    if st.session_state.bot_running:
        st.info(f"🟢 Бот сканирует **{len(tokens)}** токенов на **{len(connected)}** биржах")

# TAB 1: Графики
with tabs[1]:
    st.subheader("📈 Японские свечи")
    col_a, col_b = st.columns(2)
    sel_asset = col_a.selectbox("Актив", get_available_tokens())
    sel_ex = col_b.selectbox("Биржа", ALL_EXCHANGES[:5])
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
    st.subheader("🔍 Арбитражные возможности")
    if st.button("🔄 Обновить", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    opps = find_all_arbitrage_opportunities()
    if opps:
        st.success(f"Найдено {len(opps)} возможностей")
        for idx,opp in enumerate(opps[:10]):
            key = f"{opp['asset']}_{opp['aux_exchange']}_{idx}"
            st.info(f"🎯 {opp['asset']}: OKX ${opp['main_price']:,.0f} → {opp['aux_exchange'].upper()} ${opp['aux_price']:,.0f} | +{opp['profit_usdt']:.2f} USDT (чистая: {opp['net_profit_after_withdrawal']:.2f})")
            if st.button(f"Исполнить {opp['asset']} на {opp['aux_exchange'].upper()}", key=key):
                if st.session_state.current_mode == "Реальный" and REAL_TRADING:
                    profit = execute_arbitrage_trade(opp)
                    if profit:
                        st.success(f"Сделка исполнена! +{profit:.2f} USDT")
                        st.rerun()
                else:
                    profit = opp['net_profit_after_withdrawal']
                    if is_admin(st.session_state.email):
                        st.session_state.user_data['trade_balance'] += profit
                        st.session_state.user_data['total_profit'] += profit
                        st.session_state.user_data['trade_count'] += 1
                        st.session_state.user_data['history'].append(f"✅ {datetime.now().strftime('%H:%M:%S')} | {opp['asset']} | +{profit:.2f} USDT")
                        add_trade(st.session_state.user_id, st.session_state.current_mode, opp['asset'], 1000, profit, opp['aux_exchange'], MAIN_EXCHANGE)
                        save_user_mode_data(st.session_state.user_id, st.session_state.current_mode, st.session_state.user_data)
                        st.success(f"Сделка (демо) +{profit:.2f} USDT")
                        st.rerun()
                    else:
                        admin_fee = profit * ADMIN_COMMISSION
                        net = profit - admin_fee
                        reinvest = net * REINVEST_SHARE
                        fixed = net * FIXED_SHARE
                        st.session_state.user_data['trade_balance'] += reinvest
                        st.session_state.user_data['withdrawable_balance'] += fixed
                        st.session_state.user_data['total_profit'] += profit
                        st.session_state.user_data['trade_count'] += 1
                        st.session_state.user_data['total_admin_fee_paid'] += admin_fee
                        st.session_state.user_data['history'].append(f"✅ {datetime.now().strftime('%H:%M:%S')} | {opp['asset']} | +{profit:.2f} USDT")
                        add_trade(st.session_state.user_id, st.session_state.current_mode, opp['asset'], 1000, profit, opp['aux_exchange'], MAIN_EXCHANGE)
                        save_user_mode_data(st.session_state.user_id, st.session_state.current_mode, st.session_state.user_data)
                        st.success(f"Демо-сделка +{profit:.2f} USDT")
                        st.rerun()
    else:
        st.info("Арбитражных возможностей не найдено")

# TAB 3: Доходность
with tabs[3]:
    st.subheader("Калькулятор доходности")
    capital = st.number_input("Капитал (USDT)", min_value=100.0, value=10000.0, step=1000.0)
    if st.button("Рассчитать", use_container_width=True):
        exp_profit = capital * 0.008
        st.markdown(f"<div class='profit-card'><b>Ожидаемая дневная доходность:</b><br>Прибыль в день: <b style='color:#00FF88;'>${exp_profit:.2f}</b><br>Доходность: 0.8%</div>", unsafe_allow_html=True)

# TAB 4: Статистика по токенам
with tabs[4]:
    st.subheader("📊 Статистика по токенам")
    token_stats = {}
    total_profit_all = 0
    for trade in st.session_state.user_data.get('history',[]):
        if trade.startswith("✅"):
            try:
                parts = trade.split("|")
                if len(parts)>=3:
                    token = parts[1].strip()
                    profit = None
                    for part in parts:
                        if "+" in part and "USDT" in part:
                            profit = float(part.split("+")[1].split()[0])
                            break
                    if profit:
                        token_stats.setdefault(token,{'trades':0,'profit':0})
                        token_stats[token]['trades']+=1
                        token_stats[token]['profit']+=profit
                        total_profit_all+=profit
            except: pass
    if token_stats:
        data = [{"Токен":t,"Сделок":d['trades'],"Прибыль":f"{d['profit']:.2f}","% общ.":f"{d['profit']/total_profit_all*100:.1f}%"} for t,d in sorted(token_stats.items(), key=lambda x:x[1]['profit'], reverse=True)]
        st.dataframe(pd.DataFrame(data), use_container_width=True, hide_index=True)
        fig = px.pie(pd.DataFrame([{"Токен":t,"Прибыль":d['profit']} for t,d in token_stats.items()]), values='Прибыль', names='Токен', title="Доля прибыли")
        fig.update_layout(template="plotly_dark", height=450)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Нет данных")

# TAB 5: Портфель
with tabs[5]:
    st.subheader("📦 Портфель токенов (OKX)")
    total = 0
    portfolio = st.session_state.user_data.get('portfolio', get_target_portfolio())
    for asset, amount in portfolio.items():
        price = get_price(st.session_state.exchanges[MAIN_EXCHANGE], asset) if st.session_state.exchanges else None
        value = amount * price if price else 0
        total += value
        st.write(f"{asset}: {amount:.6f} ≈ ${value:,.2f}")
    st.metric("💰 Общая стоимость портфеля", f"${total:,.2f}")

# TAB 6: Кошелёк
with tabs[6]:
    st.subheader("💰 Кошелёк и вывод")
    st.write(f"**Доступно для вывода:** {st.session_state.user_data.get('withdrawable_balance',0):.2f} USDT")
    st.write(f"**Торговый баланс:** {st.session_state.user_data.get('trade_balance',0):.2f} USDT")
    st.write(f"**Всего комиссий:** {st.session_state.user_data.get('total_admin_fee_paid',0):.2f} USDT")
    weekday = datetime.now().strftime("%A")
    disabled = weekday not in ["Tuesday","Friday"]
    if disabled:
        st.warning("⏳ Вывод только по вторникам и пятницам")
    max_wd = st.session_state.user_data.get('withdrawable_balance',0)
    if max_wd >= 10:
        amt = st.number_input("Сумма вывода", min_value=10.0, max_value=max_wd, step=10.0, disabled=disabled)
        if st.button("Запросить вывод", disabled=disabled) and amt and st.session_state.wallet_address:
            create_withdrawal_request(st.session_state.user_id, amt, st.session_state.wallet_address)
            st.session_state.user_data['withdrawable_balance'] -= amt
            save_user_mode_data(st.session_state.user_id, st.session_state.current_mode, st.session_state.user_data)
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
    if st.session_state.user_data.get('history'):
        for trade in reversed(st.session_state.user_data['history'][-50:]):
            st.write(trade)
        if st.button("Очистить историю"):
            st.session_state.user_data['history'] = []
            save_user_mode_data(st.session_state.user_id, st.session_state.current_mode, st.session_state.user_data)
            st.rerun()
    else:
        st.info("Нет сделок")

# TAB 8: Личный кабинет
with tabs[8]:
    st.subheader("👤 Личный кабинет")
    st.write(f"**Имя:** {st.session_state.username}")
    st.write(f"**Email:** {st.session_state.email}")
    st.write(f"**Кошелёк:** {st.session_state.wallet_address if st.session_state.wallet_address else 'не указан'}")
    colb1,colb2 = st.columns(2)
    colb1.metric("Торговый баланс", f"{st.session_state.user_data.get('trade_balance',0):.2f} USDT")
    colb2.metric("Доступно для вывода", f"{st.session_state.user_data.get('withdrawable_balance',0):.2f} USDT")
    st.divider()
    st.metric("Общая прибыль", f"{st.session_state.user_data.get('total_profit',0):.2f} USDT")
    st.metric("Сделок", st.session_state.user_data.get('trade_count',0))
    st.divider()
    dep = st.number_input("Пополнить (USDT)", min_value=10.0, step=10.0)
    if st.button("Пополнить"):
        st.session_state.user_data['trade_balance'] += dep
        save_user_mode_data(st.session_state.user_id, st.session_state.current_mode, st.session_state.user_data)
        st.success(f"Пополнено {dep} USDT")
        st.rerun()
    wd = st.number_input("Вывести (USDT)", min_value=10.0, step=10.0)
    if st.button("Запросить вывод (личный кабинет)") and wd <= st.session_state.user_data.get('withdrawable_balance',0) and st.session_state.wallet_address:
        create_withdrawal_request(st.session_state.user_id, wd, st.session_state.wallet_address)
        st.success("Заявка отправлена")
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

# ---------- АДМИН-ПАНЕЛЬ ----------
if show_admin:
    with tabs[-1]:
        st.subheader("👑 Админ-панель")
        a1,a2,a3,a4,a5,a6,a7 = st.tabs(["👥 Участники","📊 Токены","🔐 API ключи","📜 Все сделки","💰 Заявки","⚙ Демо-резервы","🎛 Реальная торговля"])
        with a1:
            users = get_all_users_for_admin()
            if users:
                df = pd.DataFrame([{
                    "Email":u['email'], "Имя":u['full_name'], "Статус":u['registration_status'],
                    "Баланс":f"${u.get('trade_balance',0):.2f}", "Вывод":f"${u.get('withdrawable_balance',0):.2f}",
                    "Прибыль":f"${u.get('total_profit',0):.2f}", "Сделок":u.get('trade_count',0)
                } for u in users])
                st.dataframe(df, use_container_width=True, hide_index=True)
                emails = {u['email']:u['id'] for u in users}
                sel = st.selectbox("Пользователь", list(emails.keys()))
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
            st.divider()
            st.write("Целевой портфель")
            curr_pf = get_target_portfolio()
            new_pf = {}
            cols = st.columns(3)
            for i,tok in enumerate(cur_tokens):
                with cols[i%3]:
                    new_pf[tok] = st.number_input(tok, value=float(curr_pf.get(tok,0)), step=0.01, format="%.4f")
            if st.button("Сохранить портфель"):
                set_target_portfolio(new_pf)
                st.success("Сохранено")
        with a3:
            api_keys = get_all_api_keys()
            for ex in ALL_EXCHANGES:
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
            cur_res = get_demo_usdt_reserves()
            new_res = {}
            cols = st.columns(3)
            for i,ex in enumerate(AUX_EXCHANGES):
                with cols[i%3]:
                    new_res[ex] = st.number_input(f"{ex.upper()} USDT", value=float(cur_res.get(ex,10000)), step=500.0)
            if st.button("Сохранить резервы"):
                for ex,amt in new_res.items():
                    update_demo_usdt_reserve(ex,amt)
                st.success("Сохранено")
        with a7:
            st.warning("⚠️ Включение реальных сделок требует рабочих API-ключей и USDT/tokenов на биржах!")
            new_real = st.checkbox("Включить реальное исполнение (REAL_TRADING)", value=REAL_TRADING)
            if new_real != REAL_TRADING:
                REAL_TRADING = new_real
                st.experimental_rerun()
            ord_type = st.selectbox("Тип ордеров", ['limit','market'], index=0 if ORDER_TYPE=='limit' else 1)
            if ord_type != ORDER_TYPE:
                ORDER_TYPE = ord_type
            if st.button("Проверить балансы всех бирж (режим реальный)"):
                for ex_name, ex in st.session_state.exchanges.items():
                    if st.session_state.current_mode == "Реальный" and REAL_TRADING:
                        try:
                            bal = ex.fetch_balance()
                            usdt = bal['USDT']['free'] if 'USDT' in bal else 0
                            st.write(f"**{ex_name.upper()}** USDT: {usdt:.2f}")
                        except:
                            st.write(f"**{ex_name.upper()}** ошибка")
                    else:
                        st.write(f"**{ex_name.upper()}** (демо) USDT: {get_balance(ex, 'USDT'):.2f}")
            if st.button("Запустить ребалланс вручную"):
                rebalance_portfolio()

# ---------- АВТОМАТИЧЕСКИЙ АРБИТРАЖ ----------
if st.session_state.bot_running and st.session_state.exchanges:
    time.sleep(8)
    opps = find_all_arbitrage_opportunities()
    if opps:
        best = opps[0]
        profit = best['net_profit_after_withdrawal']
        if profit >= 0.08:
            if st.session_state.current_mode == "Реальный" and REAL_TRADING:
                executed = execute_arbitrage_trade(best)
                if executed:
                    st.toast(f"🎯 Реальная сделка {best['asset']} +{executed:.2f} USDT", icon="💰")
                    st.rerun()
            else:
                if is_admin(st.session_state.email):
                    st.session_state.user_data['trade_balance'] += profit
                    st.session_state.user_data['total_profit'] += profit
                    st.session_state.user_data['trade_count'] += 1
                    st.session_state.user_data['history'].append(f"✅ {datetime.now().strftime('%H:%M:%S')} | {best['asset']} | АВТО | +{profit:.2f} USDT")
                    add_trade(st.session_state.user_id, st.session_state.current_mode, best['asset'], 1000, profit, best['aux_exchange'], MAIN_EXCHANGE)
                    save_user_mode_data(st.session_state.user_id, st.session_state.current_mode, st.session_state.user_data)
                    st.toast(f"🎯 {best['asset']} +{profit:.2f} USDT (демо)", icon="💰")
                    send_telegram(f"🤖 Авто-сделка (админ): {best['asset']} +{profit:.2f} USDT")
                    st.rerun()
                else:
                    admin_fee = profit * ADMIN_COMMISSION
                    net = profit - admin_fee
                    reinvest = net * REINVEST_SHARE
                    fixed = net * FIXED_SHARE
                    st.session_state.user_data['trade_balance'] += reinvest
                    st.session_state.user_data['withdrawable_balance'] += fixed
                    st.session_state.user_data['total_profit'] += profit
                    st.session_state.user_data['trade_count'] += 1
                    st.session_state.user_data['total_admin_fee_paid'] += admin_fee
                    st.session_state.user_data['history'].append(f"✅ {datetime.now().strftime('%H:%M:%S')} | {best['asset']} | АВТО | +{profit:.2f} USDT")
                    add_trade(st.session_state.user_id, st.session_state.current_mode, best['asset'], 1000, profit, best['aux_exchange'], MAIN_EXCHANGE)
                    save_user_mode_data(st.session_state.user_id, st.session_state.current_mode, st.session_state.user_data)
                    st.toast(f"🎯 {best['asset']} +{profit:.2f} USDT (демо)", icon="💰")
                    send_telegram(f"🤖 Авто-сделка: {best['asset']} +{profit:.2f} USDT")
                    st.rerun()

# ---------- ЗАПУСК РЕБАЛЛАНСА ----------
if 'rebalance_scheduled' not in st.session_state:
    schedule_rebalance()
    st.session_state.rebalance_scheduled = True

st.caption(f"🚀 Сканируется {len(get_available_tokens())} токенов | Режим: {st.session_state.current_mode} | Реальные сделки: {'ВКЛ' if REAL_TRADING else 'ВЫКЛ'}")
