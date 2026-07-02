import streamlit as st
import time
import json
import ccxt
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from supabase import create_client, Client
import hashlib
import base64
import os
from cryptography.fernet import Fernet

# Пытаемся импортировать автообновление
try:
    from streamlit_autorefresh import st_autorefresh
    AUTOREFRESH_AVAILABLE = True
except ImportError:
    AUTOREFRESH_AVAILABLE = False
    st_autorefresh = None

st.set_page_config(page_title="Арбитражный бот HOVMEL", layout="wide", page_icon="🔄", initial_sidebar_state="collapsed")

# ------------------- CSS -------------------
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
    text-align: center;
}
.hovmel-highlight { background: linear-gradient(120deg, #FFD700, #FF8C00); -webkit-background-clip: text; background-clip: text; color: transparent; font-weight: 900; }
.subtitle { text-align: center; color: #aaa; margin-top: -0.8rem; margin-bottom: 1.5rem; }
.status-running { color: #00FF88; font-weight: bold; }
.status-stopped { color: #FF4444; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# ------------------- SUPABASE -------------------
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
except Exception:
    SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
    SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
    if not SUPABASE_URL or not SUPABASE_KEY:
        st.error("❌ Ошибка: не заданы SUPABASE_URL и SUPABASE_KEY.")
        st.stop()

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

EXCHANGES = ["kucoin", "okx"]
TOKENS = ["DOGE", "SHIB", "PEPE", "WIF", "FLOKI", "BONK", "MEME", "BOME", "SOL", "NEIRO", "BRETT"]

TOKEN_MAX_TRADE = {
    "BTC": 300, "ETH": 250, "SOL": 200, "BNB": 200, "TON": 150,
    "DOGE": 100, "SHIB": 100, "PEPE": 50, "WIF": 50, "FLOKI": 50,
    "BONK": 50, "MEME": 50, "BOME": 50, "NEIRO": 50, "BRETT": 50
}

ADMIN_EMAILS = ["cb777899@gmail.com"]
REAL_MODE_ALLOWED_USERS = ["cb777899@gmail.com"]

def is_admin(email): return email in ADMIN_EMAILS
def can_trade_real(email): return email in REAL_MODE_ALLOWED_USERS

# ------------------- КЭШИРОВАНИЕ -------------------
@st.cache_data(ttl=10)
def get_cached_user_settings(user_id):
    try:
        res = supabase.table('user_settings').select('*').eq('user_id', user_id).execute()
        if res.data:
            return res.data[0]
    except:
        pass
    return None

@st.cache_data(ttl=10)
def get_user_trades(user_id, mode=None, limit=100):
    try:
        query = supabase.table('trades').select('*').eq('user_id', user_id)
        if mode is not None:
            query = query.eq('mode', mode)
        res = query.order('trade_time', desc=True).limit(limit).execute()
        return res.data
    except:
        return []

@st.cache_data(ttl=10)
def get_cached_trades(limit=100):
    return supabase.table('trades').select('*, users(email,full_name)').order('trade_time', desc=True).limit(limit).execute().data

@st.cache_data(ttl=15)
def get_cached_messages(user_id=None, limit=50):
    query = supabase.table('messages').select('*, users(full_name)').order('created_at', desc=True).limit(limit)
    if user_id is not None:
        query = query.eq('user_id', user_id)
    return query.execute().data

@st.cache_data(ttl=15)
def get_cached_withdrawals():
    return supabase.table('withdrawals').select('*, users(email)').eq('status', 'pending').execute().data

@st.cache_data(ttl=30)
def get_cached_users():
    return supabase.table('users').select('*').order('created_at', desc=True).execute().data

# ------------------- БАЗА ДАННЫХ -------------------
def get_user_by_email(email):
    res = supabase.table('users').select('*').eq('email', email).execute()
    return res.data[0] if res.data else None

def create_user(email, pwd, name, country, city, phone, wallet):
    pwd_hash = hashlib.sha256(pwd.encode()).hexdigest()
    initial = {'main_balance':0, 'exchanges':{ex:{"USDT":0,"portfolio":{t:0 for t in TOKENS}} for ex in EXCHANGES},
               'total_profit':0,'trade_count':0,'withdrawable_balance':0,'total_admin_fee_paid':0}
    supabase.table('users').insert({
        'email':email,'password_hash':pwd_hash,'full_name':name,'country':country,'city':city,
        'phone':phone,'wallet_address':wallet,'registration_status':'approved',
        'demo_balances':json.dumps(initial),'demo_history':'[]','demo_stats':'{}'
    }).execute()

def load_demo_data(user_id):
    res = supabase.table('users').select('demo_balances, demo_history, total_profit, trade_count, withdrawable_balance').eq('id', user_id).execute()
    if res.data:
        u = res.data[0]
        try:
            balances = json.loads(u['demo_balances']) if isinstance(u['demo_balances'], str) else u['demo_balances']
            if not isinstance(balances, dict): balances = {}
        except: balances = {}
        try:
            history = json.loads(u['demo_history']) if isinstance(u['demo_history'], str) else u['demo_history']
            if not isinstance(history, list): history = []
        except: history = []
        return {
            'balances': balances.get('exchanges', {ex:{"USDT":0,"portfolio":{t:0 for t in TOKENS}} for ex in EXCHANGES}),
            'total_profit': u.get('total_profit',0),
            'trade_count': u.get('trade_count',0),
            'withdrawable_balance': u.get('withdrawable_balance',0),
            'history': history
        }
    return None

def save_demo_data(user_id, data):
    to_save = {'main_balance':0,'exchanges':data['balances'],'total_profit':data['total_profit'],
               'trade_count':data['trade_count'],'withdrawable_balance':data['withdrawable_balance'],'total_admin_fee_paid':0}
    supabase.table('users').update({
        'demo_balances':json.dumps(to_save),
        'demo_history':json.dumps(data['history']),
        'total_profit':data['total_profit'],
        'trade_count':data['trade_count'],
        'withdrawable_balance':data['withdrawable_balance']
    }).eq('id', user_id).execute()
    st.cache_data.clear()

def add_trade(user_id, mode, asset, amount, profit, buy_ex, sell_ex):
    print(f"🔵 ВХОД В add_trade: user_id={user_id}, mode={mode}, asset={asset}, amount={amount}, profit={profit}")
    try:
        result = supabase.table('trades').insert({
            'user_id':user_id,'mode':mode,'asset':asset,'amount':amount,'profit':profit,
            'buy_exchange':buy_ex,'sell_exchange':sell_ex
        }).execute()
        print(f"✅ СДЕЛКА СОХРАНЕНА: {asset} {amount} {profit} {mode}")
        st.cache_data.clear()
        return True
    except Exception as e:
        print(f"❌ ОШИБКА СОХРАНЕНИЯ СДЕЛКИ: {e}")
        return False

# ------------------- API КЛЮЧИ -------------------
def get_all_api_keys():
    res = supabase.table('api_keys').select('exchange, api_key, secret_key, passphrase').execute()
    result = {}
    for row in res.data:
        result[row['exchange']] = {
            'api_key': row.get('api_key', ''),
            'secret_key': row.get('secret_key', ''),
            'passphrase': row.get('passphrase', '')
        }
    return result

def save_api_key(exchange, api_key, secret, passphrase, admin):
    enc_key = encrypt_key(api_key) if api_key else ""
    enc_secret = encrypt_key(secret) if secret else ""
    enc_passphrase = encrypt_key(passphrase) if passphrase else ""
    supabase.table('api_keys').upsert({
        'exchange': exchange,
        'api_key': enc_key,
        'secret_key': enc_secret,
        'passphrase': enc_passphrase,
        'updated_at': datetime.now().isoformat(),
        'updated_by': admin
    }, on_conflict='exchange').execute()
    st.cache_data.clear()

def get_config(key):
    res = supabase.table('config').select('value').eq('key', key).execute()
    return json.loads(res.data[0]['value']) if res.data else None

def set_config(key, value):
    supabase.table('config').upsert({'key':key,'value':json.dumps(value)}).execute()

def get_available_tokens():
    tokens_from_db = get_config('tokens')
    return tokens_from_db if tokens_from_db else TOKENS

def update_withdrawal_status(wid, status):
    supabase.table('withdrawals').update({'status': status, 'processed_at': datetime.now().isoformat()}).eq('id', wid).execute()
    st.cache_data.clear()

def update_user_status(uid, status):
    supabase.table('users').update({'registration_status': status}).eq('id', uid).execute()
    st.cache_data.clear()

def add_message(user_id, user_email, user_name, message, is_admin_reply=False):
    supabase.table('messages').insert({
        'user_id': user_id, 'user_email': user_email, 'user_name': user_name,
        'message': message, 'is_admin_reply': is_admin_reply
    }).execute()
    st.cache_data.clear()

def mark_messages_read(user_id):
    supabase.table('messages').update({'is_read': True}).eq('user_id', user_id).eq('is_read', False).eq('is_admin_reply', True).execute()
    st.cache_data.clear()

def get_unread_count(user_id):
    res = supabase.table('messages').select('id', count='exact').eq('user_id', user_id).eq('is_read', False).eq('is_admin_reply', True).execute()
    return res.count or 0

def create_withdrawal_request(user_id, amount, wallet):
    admin_fee = amount * 0.22
    supabase.table('withdrawals').insert({
        'user_id': user_id, 'amount': amount, 'admin_fee': admin_fee,
        'user_receives': amount - admin_fee, 'wallet_address': wallet, 'status': 'pending'
    }).execute()
    st.cache_data.clear()

# ------------------- НАСТРОЙКИ ПОЛЬЗОВАТЕЛЯ -------------------
def load_user_settings(user_id):
    res = supabase.table('user_settings').select('*').eq('user_id', user_id).execute()
    if res.data:
        return res.data[0]
    default = {
        'user_id': user_id,
        'fee': 0.2,
        'min_profit': 0.07,
        'min_trade': 8.0,
        'max_trade': 20.0,
        'scan_interval': 30,
        'reinvest_percent': 0,
        'use_orderbook': True,
        'max_slippage': 0.3,
        'orderbook_depth': 20,
        'auto_trade_enabled': False
    }
    try:
        supabase.table('user_settings').upsert(default, on_conflict='user_id').execute()
        st.cache_data.clear()
    except: pass
    return default

def save_user_settings(user_id, settings):
    try:
        supabase.table('user_settings').update(settings).eq('user_id', user_id).execute()
        st.cache_data.clear()
    except: pass

# ------------------- БИРЖИ -------------------
@st.cache_resource
def init_public_clients():
    clients = {}
    for ex in EXCHANGES:
        try:
            cls = getattr(ccxt, ex)
            clients[ex] = cls({'enableRateLimit':True, 'options':{'defaultType':'spot'}})
            clients[ex].fetch_ticker("BTC/USDT")
        except: clients[ex] = None
    return clients

@st.cache_resource
def init_real_exchanges():
    exchanges = {}
    api_keys = get_all_api_keys()
    for ex in EXCHANGES:
        key_data = api_keys.get(ex, {})
        api_key = decrypt_key(key_data.get('api_key', ''))
        secret = decrypt_key(key_data.get('secret_key', ''))
        passphrase = decrypt_key(key_data.get('passphrase', ''))
        if api_key and secret:
            try:
                cls = getattr(ccxt, ex)
                exchanges[ex] = cls({
                    'apiKey': api_key,
                    'secret': secret,
                    'password': passphrase,
                    'enableRateLimit': True,
                    'options': {'defaultType': 'spot'}
                })
                exchanges[ex].load_markets()
            except:
                exchanges[ex] = None
        else:
            exchanges[ex] = None
    return exchanges

def get_price(exchange, symbol):
    try:
        ticker = exchange.fetch_ticker(f"{symbol}/USDT")
        return ticker['last']
    except: return None

def get_order_book_price(exchange, symbol, side, amount_usdt, depth=20):
    try:
        orderbook = exchange.fetch_order_book(f"{symbol}/USDT", limit=depth)
        if side == 'buy':
            asks = orderbook['asks']
            if not asks: return None, 0, "Нет данных в стакане (asks)"
            total_usdt = 0; total_amount = 0
            for price, amount in asks:
                cost = price * amount
                if total_usdt + cost >= amount_usdt:
                    need = (amount_usdt - total_usdt) / price
                    total_amount += need; total_usdt = amount_usdt
                    break
                else:
                    total_amount += amount; total_usdt += cost
            if total_usdt < amount_usdt:
                # Возвращаем то, что есть
                avg_price = total_usdt / total_amount if total_amount > 0 else None
                return avg_price, total_usdt, f"Доступно только {total_usdt:.2f} USDT"
            avg_price = total_usdt / total_amount
            return avg_price, total_usdt, None
        else:  # sell
            bids = orderbook['bids']
            if not bids: return None, 0, "Нет данных в стакане (bids)"
            remaining = amount_usdt; total_amount = 0; total_received = 0
            for price, amount in bids:
                value = price * amount
                if value >= remaining:
                    need = remaining / price
                    total_amount += need; total_received = remaining
                    break
                else:
                    total_amount += amount; remaining -= value; total_received += value
            if total_received < amount_usdt:
                avg_price = total_received / total_amount if total_amount > 0 else None
                return avg_price, total_received, f"Доступно только {total_received:.2f} USDT"
            avg_price = total_received / total_amount
            return avg_price, total_received, None
    except Exception as e:
        return None, 0, f"Ошибка получения стакана: {str(e)}"

def get_market_price_with_liquidity(exchange, symbol, side, amount_usdt, depth=20, max_slippage=0.3):
    price, available, err = get_order_book_price(exchange, symbol, side, amount_usdt, depth)
    if price is not None:
        try:
            ticker = exchange.fetch_ticker(f"{symbol}/USDT")
            last = ticker['last']
            slippage = abs(price - last) / last * 100
            if slippage > max_slippage:
                return None, 0, f"Проскальзывание {slippage:.2f}% > {max_slippage}%"
        except: pass
        return price, available, None
    else:
        try:
            ticker = exchange.fetch_ticker(f"{symbol}/USDT")
            if side == 'buy':
                price = ticker['ask'] if 'ask' in ticker else ticker['last'] * 1.001
            else:
                price = ticker['bid'] if 'bid' in ticker else ticker['last'] * 0.999
            return price, amount_usdt, err
        except Exception as e:
            return None, 0, f"Ошибка получения цены: {str(e)}"

# ------------------- ДЕМО-ФУНКЦИИ -------------------
def update_demo_balance(user_id, exchange, asset, delta, data):
    if exchange not in data['balances']:
        data['balances'][exchange] = {'USDT':0.0, 'portfolio':{t:0.0 for t in get_available_tokens()}}
    if asset == 'USDT':
        data['balances'][exchange]['USDT'] += delta
    else:
        if asset not in data['balances'][exchange]['portfolio']:
            data['balances'][exchange]['portfolio'][asset] = 0.0
        data['balances'][exchange]['portfolio'][asset] += delta
    save_demo_data(user_id, data)

def demo_buy(user_id, exchange, token, usdt_amount, data, clients, is_manual=False):
    price = get_price(clients[exchange], token)
    if not price: return False, "Цена не получена"
    amount_token = usdt_amount / price
    if data['balances'][exchange]['USDT'] < usdt_amount:
        return False, f"Не хватает USDT (есть {data['balances'][exchange]['USDT']:.2f})"
    update_demo_balance(user_id, exchange, 'USDT', -usdt_amount, data)
    update_demo_balance(user_id, exchange, token, amount_token, data)
    if is_manual:
        entry = f"🟢 {datetime.now()} | Ручная операция: покупка {token} на {exchange.upper()} на {usdt_amount} USDT"
        data['history'].append(entry)
        save_demo_data(user_id, data)
    return True, f"Куплено {amount_token:.8f} {token} за {usdt_amount} USDT"

def demo_sell(user_id, exchange, token, usdt_amount, data, clients, is_manual=False):
    price = get_price(clients[exchange], token)
    if not price: return False, "Цена не получена"
    amount_token = usdt_amount / price
    available = data['balances'][exchange]['portfolio'].get(token, 0)
    if available < amount_token:
        return False, f"Не хватает {token} (есть {available:.8f}, нужно {amount_token:.8f})"
    usdt_received = amount_token * price
    update_demo_balance(user_id, exchange, token, -amount_token, data)
    update_demo_balance(user_id, exchange, 'USDT', usdt_received, data)
    if is_manual:
        entry = f"🔴 {datetime.now()} | Ручная операция: продажа {token} на {exchange.upper()} на {usdt_amount} USDT (продано {amount_token:.8f})"
        data['history'].append(entry)
        save_demo_data(user_id, data)
    return True, f"Продано {amount_token:.8f} {token} за {usdt_received:.2f} USDT"

def reset_demo_data(user_id):
    init_bal = {ex:{"USDT":0,"portfolio":{t:0 for t in get_available_tokens()}} for ex in EXCHANGES}
    st.session_state.demo_data = {'balances':init_bal,'total_profit':0,'trade_count':0,'withdrawable_balance':0,'history':[]}
    save_demo_data(user_id, st.session_state.demo_data)

# ------------------- РЕАЛЬНЫЕ ФУНКЦИИ (исправлены) -------------------
def get_real_balance(exchange, asset):
    if not exchange: return 0.0
    try:
        bal = exchange.fetch_balance()
        if asset == 'USDT':
            return bal.get('USDT', {}).get('free', 0.0)
        else:
            return bal.get(asset, {}).get('free', 0.0)
    except: return 0.0

def real_buy_with_liquidity(exchange, token, usdt_amount, max_slippage=0.3, depth=20, use_orderbook=True):
    if not exchange: return False, "Биржа не подключена", None, None
    if use_orderbook:
        price, available, err = get_market_price_with_liquidity(exchange, token, 'buy', usdt_amount, depth, max_slippage)
        if price is None:
            return False, err, None, None
        if available < usdt_amount:
            usdt_amount = available  # уменьшаем сумму до доступной
        amount_token = usdt_amount / price
    else:
        price = get_price(exchange, token)
        if not price: return False, "Не удалось получить цену", None, None
        amount_token = usdt_amount / price
    try:
        order = exchange.create_market_buy_order(f"{token}/USDT", amount_token)
        filled = order.get('filled', amount_token)
        cost = order.get('cost', usdt_amount)
        if filled is None or cost is None or filled == 0:
            return False, "Не удалось получить данные об исполнении", None, None
        real_price = cost / filled
        print(f"✅ РЕАЛЬНАЯ ПОКУПКА: {filled:.8f} {token} по средней цене {real_price:.8f} USDT на {exchange.name}")
        return True, f"Куплено {filled:.8f} {token} по {real_price:.8f}", filled, real_price
    except Exception as e:
        print(f"❌ ОШИБКА ПОКУПКИ: {e}")
        return False, str(e), None, None

def real_sell_with_liquidity(exchange, token, usdt_amount, max_slippage=0.3, depth=20, use_orderbook=True):
    if not exchange: return False, "Биржа не подключена", None, None
    if use_orderbook:
        price, available, err = get_market_price_with_liquidity(exchange, token, 'sell', usdt_amount, depth, max_slippage)
        if price is None:
            return False, err, None, None
        if available < usdt_amount:
            usdt_amount = available
        amount_token = usdt_amount / price
    else:
        price = get_price(exchange, token)
        if not price: return False, "Не удалось получить цену", None, None
        amount_token = usdt_amount / price
    try:
        order = exchange.create_market_sell_order(f"{token}/USDT", amount_token)
        filled = order.get('filled', amount_token)
        cost = order.get('cost', usdt_amount)
        if filled is None or cost is None or filled == 0:
            return False, "Не удалось получить данные об исполнении", None, None
        real_price = cost / filled
        print(f"✅ РЕАЛЬНАЯ ПРОДАЖА: {filled:.8f} {token} по средней цене {real_price:.8f} USDT на {exchange.name}")
        return True, f"Продано {filled:.8f} {token} по {real_price:.8f}", filled, real_price
    except Exception as e:
        print(f"❌ ОШИБКА ПРОДАЖИ: {e}")
        return False, str(e), None, None

# ------------------- АРБИТРАЖНЫЕ ФУНКЦИИ (исправлены) -------------------
def find_demo_opportunity(fee, min_profit, min_trade, max_trade, depth, use_orderbook, demo_data, public_clients, max_slippage=0.3):
    opportunities = []
    tokens = get_available_tokens()
    prices = {}
    for ex in EXCHANGES:
        if public_clients.get(ex):
            prices[ex] = {}
            for t in tokens:
                p = get_price(public_clients[ex], t)
                if p: prices[ex][t] = p
    for buy_ex in EXCHANGES:
        for sell_ex in EXCHANGES:
            if buy_ex == sell_ex: continue
            for token in tokens:
                if token not in prices.get(buy_ex,{}) or token not in prices.get(sell_ex,{}): continue
                buy_p = prices[buy_ex][token]
                sell_p = prices[sell_ex][token]
                if sell_p <= buy_p: continue
                usdt = demo_data['balances'].get(buy_ex, {}).get('USDT', 0)
                token_amt = demo_data['balances'].get(sell_ex, {}).get('portfolio', {}).get(token, 0)
                if usdt < min_trade: continue
                max_by_usdt = usdt
                max_by_token = token_amt * sell_p
                max_possible = min(max_by_usdt, max_by_token)
                if max_possible < min_trade: continue
                token_max = TOKEN_MAX_TRADE.get(token, max_trade)
                trade_usdt = min(max_possible, token_max)
                if trade_usdt < min_trade: continue
                amount = trade_usdt / buy_p
                required_token = amount * 1.02
                if required_token > token_amt:
                    max_sell_usdt = token_amt * sell_p * 0.98
                    trade_usdt = min(trade_usdt, max_sell_usdt, token_max)
                    if trade_usdt < min_trade: continue
                    amount = trade_usdt / buy_p
                if use_orderbook:
                    buy_price, buy_available, err1 = get_market_price_with_liquidity(public_clients[buy_ex], token, 'buy', trade_usdt, depth, max_slippage)
                    if buy_price is None: continue
                    sell_price, sell_available, err2 = get_market_price_with_liquidity(public_clients[sell_ex], token, 'sell', trade_usdt, depth, max_slippage)
                    if sell_price is None: continue
                else:
                    buy_price = buy_p
                    sell_price = sell_p
                profit_before = (sell_price - buy_price) * amount
                profit = profit_before * (1 - fee/100)
                if profit < min_profit: continue
                opportunities.append({
                    'token':token, 'buy_ex':buy_ex, 'sell_ex':sell_ex,
                    'buy_price':buy_price, 'sell_price':sell_price,
                    'trade_usdt':trade_usdt, 'amount':amount, 'profit':profit
                })
    if not opportunities: return None
    return max(opportunities, key=lambda x: x['profit'])

def execute_demo_arbitrage(opp, user_id, demo_data, public_clients, reinvest_percent, use_orderbook=True, depth=20, max_slippage=0.3):
    buy_ex = opp['buy_ex']; sell_ex = opp['sell_ex']; token = opp['token']
    amount = opp['amount']; trade_usdt = opp['trade_usdt']; sell_price = opp['sell_price']
    if not demo_data: return None, "Демо-данные не загружены"
    usdt_balance = demo_data['balances'].get(buy_ex, {}).get('USDT', 0)
    token_balance = demo_data['balances'].get(sell_ex, {}).get('portfolio', {}).get(token, 0)
    token_max = TOKEN_MAX_TRADE.get(token, st.session_state.max_trade)
    if usdt_balance < trade_usdt:
        trade_usdt = min(trade_usdt, usdt_balance, token_max)
        if trade_usdt < st.session_state.min_trade:
            return None, f"Не хватает USDT на {buy_ex}: {usdt_balance:.2f} < {trade_usdt:.2f}"
        amount = trade_usdt / opp['buy_price']
    if token_balance < amount * 1.02:
        max_sell_usdt = token_balance * sell_price * 0.98
        trade_usdt = min(trade_usdt, max_sell_usdt, token_max)
        if trade_usdt < st.session_state.min_trade:
            return None, f"Не хватает {token} на {sell_ex}: нужно {amount:.8f}, доступно {token_balance:.8f}"
        amount = trade_usdt / opp['buy_price']
        profit_before = (sell_price - opp['buy_price']) * amount
        real_profit = profit_before * (1 - st.session_state.fee/100)
    else:
        real_profit = amount * sell_price - trade_usdt
    ok_buy, msg_buy = demo_buy(user_id, buy_ex, token, trade_usdt, demo_data, public_clients, is_manual=False)
    if not ok_buy: return None, msg_buy
    ok_sell, msg_sell = demo_sell(user_id, sell_ex, token, amount * sell_price, demo_data, public_clients, is_manual=False)
    if not ok_sell: return None, msg_sell
    reinvest_amount = real_profit * reinvest_percent / 100
    withdrawable_amount = real_profit - reinvest_amount
    if reinvest_amount > 0: update_demo_balance(user_id, sell_ex, 'USDT', reinvest_amount, demo_data)
    if withdrawable_amount > 0: demo_data['withdrawable_balance'] += withdrawable_amount
    demo_data['total_profit'] += real_profit
    demo_data['trade_count'] += 1
    entry = f"✅ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | {token} | {buy_ex}→{sell_ex} | {amount:.8f} | +{real_profit:.2f} USDT | Реинвест {reinvest_percent}%"
    demo_data['history'].append(entry)
    save_demo_data(user_id, demo_data)
    add_trade(user_id, "Демо", token, amount, real_profit, buy_ex, sell_ex)
    st.toast(f"💰 Демо-сделка: +{real_profit:.2f} USDT", icon="🎉")
    return real_profit, entry

# ==================== РЕАЛЬНЫЙ АРБИТРАЖ (ПЕРЕРАБОТАН) ====================
def find_real_opportunity(fee, min_profit, min_trade, max_trade, depth, use_orderbook, real_exchanges, max_slippage=0.3):
    if not real_exchanges or not any(real_exchanges.values()):
        return None
    opportunities = []
    tokens = get_available_tokens()
    prices = {}
    balances = {}
    for ex in EXCHANGES:
        exch = real_exchanges.get(ex)
        if exch:
            prices[ex] = {}
            for t in tokens:
                p = get_price(exch, t)
                if p: prices[ex][t] = p
            balances[ex] = {
                'USDT': get_real_balance(exch, 'USDT'),
                'portfolio': {t: get_real_balance(exch, t) for t in tokens}
            }
        else:
            prices[ex] = {}
            balances[ex] = {'USDT': 0, 'portfolio': {t: 0 for t in tokens}}
    
    now = datetime.now()
    last_trade_info = st.session_state.get('last_trade_info', {})
    
    for buy_ex in EXCHANGES:
        for sell_ex in EXCHANGES:
            if buy_ex == sell_ex: continue
            for token in tokens:
                # Защита от обратных сделок
                if token in last_trade_info:
                    last_dir = last_trade_info[token].get('direction')
                    last_time = last_trade_info[token].get('timestamp')
                    if last_time and (now - last_time).seconds < 300:
                        if last_dir and (buy_ex, sell_ex) != last_dir:
                            continue
                
                if token not in prices.get(buy_ex,{}) or token not in prices.get(sell_ex,{}): continue
                buy_p = prices[buy_ex][token]
                sell_p = prices[sell_ex][token]
                if sell_p <= buy_p: continue
                usdt = balances.get(buy_ex, {}).get('USDT', 0)
                token_amt = balances.get(sell_ex, {}).get('portfolio', {}).get(token, 0)
                if usdt < min_trade: continue
                max_by_usdt = usdt
                max_by_token = token_amt * sell_p
                max_possible = min(max_by_usdt, max_by_token)
                if max_possible < min_trade: continue
                token_max = TOKEN_MAX_TRADE.get(token, max_trade)
                trade_usdt = min(max_possible, token_max)
                if trade_usdt < min_trade: continue
                amount = trade_usdt / buy_p
                required_token = amount * 1.02
                if required_token > token_amt:
                    max_sell_usdt = token_amt * sell_p * 0.98
                    trade_usdt = min(trade_usdt, max_sell_usdt, token_max)
                    if trade_usdt < min_trade: continue
                    amount = trade_usdt / buy_p
                # Получаем реальные цены с учётом стакана
                if use_orderbook:
                    buy_price, buy_available, err1 = get_market_price_with_liquidity(real_exchanges[buy_ex], token, 'buy', trade_usdt, depth, max_slippage)
                    if buy_price is None:
                        if buy_available and buy_available > min_trade:
                            trade_usdt = min(trade_usdt, buy_available)
                            buy_price, _, _ = get_market_price_with_liquidity(real_exchanges[buy_ex], token, 'buy', trade_usdt, depth, max_slippage)
                            if buy_price is None:
                                continue
                        else:
                            continue
                    sell_price, sell_available, err2 = get_market_price_with_liquidity(real_exchanges[sell_ex], token, 'sell', trade_usdt, depth, max_slippage)
                    if sell_price is None:
                        if sell_available and sell_available > min_trade:
                            trade_usdt = min(trade_usdt, sell_available)
                            sell_price, _, _ = get_market_price_with_liquidity(real_exchanges[sell_ex], token, 'sell', trade_usdt, depth, max_slippage)
                            if sell_price is None:
                                continue
                        else:
                            continue
                else:
                    buy_price = buy_p
                    sell_price = sell_p
                amount = trade_usdt / buy_price
                profit_before = (sell_price - buy_price) * amount
                total_fee = 0.002
                profit = profit_before * (1 - total_fee) - 0.005
                if profit < min_profit: continue
                opportunities.append({
                    'token':token, 'buy_ex':buy_ex, 'sell_ex':sell_ex,
                    'buy_price':buy_price, 'sell_price':sell_price,
                    'trade_usdt':trade_usdt, 'amount':amount, 'profit':profit
                })
    if not opportunities: return None
    return max(opportunities, key=lambda x: x['profit'])

def execute_real_arbitrage(opp, user_id, real_exchanges, reinvest_percent, use_orderbook=True, depth=20, max_slippage=0.3):
    print(f"🚀 НАЧАЛО РЕАЛЬНОЙ СДЕЛКИ для {opp['token']}")
    
    buy_ex = opp['buy_ex']; sell_ex = opp['sell_ex']; token = opp['token']
    amount = opp['amount']; trade_usdt = opp['trade_usdt']; sell_price = opp['sell_price']
    
    if not real_exchanges or not any(real_exchanges.values()):
        print("❌ Реальные биржи не подключены")
        return None, "Реальные биржи не подключены"
    
    exch_buy = real_exchanges.get(buy_ex)
    exch_sell = real_exchanges.get(sell_ex)
    if not exch_buy or not exch_sell:
        print(f"❌ Одна из бирж не подключена: buy={buy_ex}, sell={sell_ex}")
        return None, "Одна из бирж не подключена"
    
    usdt_balance = get_real_balance(exch_buy, 'USDT')
    token_balance = get_real_balance(exch_sell, token)
    print(f"📊 Балансы: USDT на {buy_ex}={usdt_balance:.2f}, {token} на {sell_ex}={token_balance:.8f}")
    
    if usdt_balance < trade_usdt:
        trade_usdt = min(trade_usdt, usdt_balance)
        if trade_usdt < st.session_state.min_trade:
            msg = f"Не хватает USDT на {buy_ex}: {usdt_balance:.2f} < {trade_usdt:.2f}"
            print(f"❌ {msg}")
            return None, msg
        amount = trade_usdt / opp['buy_price']
        print(f"📊 Скорректирована сумма сделки: {trade_usdt:.2f} USDT, {amount:.8f} {token}")
    
    if token_balance < amount * 1.02:
        max_sell_usdt = token_balance * opp['sell_price'] * 0.98
        trade_usdt = min(trade_usdt, max_sell_usdt)
        if trade_usdt < st.session_state.min_trade:
            msg = f"Не хватает {token} на {sell_ex}: нужно {amount:.8f}, доступно {token_balance:.8f}"
            print(f"❌ {msg}")
            return None, msg
        amount = trade_usdt / opp['buy_price']
        print(f"📊 Скорректирована сумма сделки (токен): {trade_usdt:.2f} USDT, {amount:.8f} {token}")
    
    print(f"🔄 Покупка {amount:.8f} {token} на {buy_ex} за {trade_usdt:.2f} USDT")
    ok_buy, msg_buy, filled_buy, real_buy_price = real_buy_with_liquidity(exch_buy, token, trade_usdt, max_slippage, depth, use_orderbook)
    if not ok_buy:
        print(f"❌ Ошибка покупки: {msg_buy}")
        return None, msg_buy
    print(f"✅ Покупка выполнена по {real_buy_price:.8f}, количество {filled_buy:.8f}")
    
    if filled_buy is None or real_buy_price is None:
        return None, "Не удалось получить данные о покупке"
    
    sell_usdt = filled_buy * real_buy_price
    print(f"🔄 Продажа {filled_buy:.8f} {token} на {sell_ex} на сумму {sell_usdt:.2f} USDT")
    ok_sell, msg_sell, filled_sell, real_sell_price = real_sell_with_liquidity(exch_sell, token, sell_usdt, max_slippage, depth, use_orderbook)
    if not ok_sell:
        print(f"❌ Ошибка продажи: {msg_sell}")
        return None, msg_sell
    print(f"✅ Продажа выполнена по {real_sell_price:.8f}, количество {filled_sell:.8f}")
    
    if filled_sell is None or real_sell_price is None:
        return None, "Не удалось получить данные о продаже"
    
    real_profit_final = (real_sell_price - real_buy_price) * filled_sell
    total_turnover = trade_usdt + sell_usdt
    real_profit_final -= total_turnover * 0.002
    real_profit_final -= 0.005
    
    if real_profit_final < 0.005:
        print(f"❌ Реальная прибыль {real_profit_final:.4f} меньше нуля, сделка убыточна")
        return None, f"Убыток {real_profit_final:.4f} USDT"
    
    st.session_state.real_trades += 1
    st.session_state.real_profit_total += real_profit_final
    print(f"📊 Сделка #{st.session_state.real_trades}, реальная прибыль: {real_profit_final:.4f} USDT")
    
    print(f"💾 Попытка сохранить сделку: {token}, {filled_sell:.8f}, {real_profit_final:.4f}, {buy_ex}->{sell_ex}")
    success = add_trade(user_id, "Реальный", token, filled_sell, real_profit_final, buy_ex, sell_ex)
    if success:
        print(f"✅ СДЕЛКА УСПЕШНО СОХРАНЕНА")
    else:
        print(f"❌ НЕ УДАЛОСЬ СОХРАНИТЬ СДЕЛКУ")
    
    if 'last_trade_info' not in st.session_state:
        st.session_state.last_trade_info = {}
    st.session_state.last_trade_info[token] = {
        'direction': (buy_ex, sell_ex),
        'timestamp': datetime.now()
    }
    
    st.toast(f"💰 Реальная сделка: +{real_profit_final:.2f} USDT", icon="🎉")
    return real_profit_final, f"Сделка выполнена! Реальная прибыль: {real_profit_final:.2f} USDT"

# ------------------- СЕССИЯ -------------------
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_id = None
    st.session_state.email = None
    st.session_state.username = None
    st.session_state.wallet = ''
    st.session_state.demo_data = None
    st.session_state.real_trades = 0
    st.session_state.real_profit_total = 0
    st.session_state.trade_mode = "Реальный"
    st.session_state.auto_log = []
    st.session_state.auto_trade_enabled = False
    st.session_state.last_scan_time = None
    st.session_state.chat_unread = 0
    st.session_state.fee = 0.2
    st.session_state.min_profit = 0.07
    st.session_state.min_trade = 8.0
    st.session_state.max_trade = 20.0
    st.session_state.scan_interval = 30
    st.session_state.reinvest_percent = 0
    st.session_state.use_orderbook = True
    st.session_state.max_slippage = 0.3
    st.session_state.orderbook_depth = 20
    st.session_state.real_exchanges = None
    st.session_state.last_trade_info = {}

if 'email' in st.query_params:
    email = st.query_params['email']
    user = get_user_by_email(email)
    if user:
        st.session_state.logged_in = True
        st.session_state.user_id = user['id']
        st.session_state.email = user['email']
        st.session_state.username = user['full_name']
        st.session_state.wallet = user.get('wallet_address', '')
        demo = load_demo_data(st.session_state.user_id)
        if demo: st.session_state.demo_data = demo
        else:
            init_bal = {ex:{"USDT":0,"portfolio":{t:0 for t in get_available_tokens()}} for ex in EXCHANGES}
            st.session_state.demo_data = {'balances':init_bal,'total_profit':0,'trade_count':0,'withdrawable_balance':0,'history':[]}
            save_demo_data(st.session_state.user_id, st.session_state.demo_data)
        settings = load_user_settings(st.session_state.user_id)
        st.session_state.fee = settings.get('fee', 0.2)
        st.session_state.min_profit = settings.get('min_profit', 0.07)
        st.session_state.min_trade = settings.get('min_trade', 8.0)
        st.session_state.max_trade = settings.get('max_trade', 20.0)
        st.session_state.scan_interval = settings.get('scan_interval', 30)
        st.session_state.reinvest_percent = settings.get('reinvest_percent', 0)
        st.session_state.use_orderbook = settings.get('use_orderbook', True)
        st.session_state.max_slippage = settings.get('max_slippage', 0.3)
        st.session_state.orderbook_depth = settings.get('orderbook_depth', 20)
        st.session_state.auto_trade_enabled = settings.get('auto_trade_enabled', False)
        st.session_state.real_exchanges = init_real_exchanges()
        st.session_state.chat_unread = get_unread_count(st.session_state.user_id)

if st.session_state.logged_in and st.session_state.email:
    st.query_params.email = st.session_state.email

public_clients = init_public_clients()
if st.session_state.real_exchanges is None:
    st.session_state.real_exchanges = init_real_exchanges()

admin_user = get_user_by_email("cb777899@gmail.com")

# ------------------- АВТО-СКАНИРОВАНИЕ -------------------
if st.session_state.get('auto_trade_enabled', False):
    if st.session_state.trade_mode == "Реальный":
        if st.session_state.real_exchanges and any(st.session_state.real_exchanges.values()):
            if AUTOREFRESH_AVAILABLE:
                interval = st.session_state.get('scan_interval', 30)
                st_autorefresh(interval=interval * 1000, key="auto_refresh")
            now = datetime.now()
            last = st.session_state.get('last_scan_time')
            if last is None or (now - last).total_seconds() >= st.session_state.get('scan_interval', 30):
                st.session_state.last_scan_time = now
                opp = find_real_opportunity(
                    st.session_state.fee, st.session_state.min_profit,
                    st.session_state.min_trade, st.session_state.max_trade,
                    st.session_state.orderbook_depth, st.session_state.use_orderbook,
                    st.session_state.real_exchanges,
                    st.session_state.max_slippage
                )
                if opp:
                    st.session_state.auto_log.append(f"🔍 Найдено (реал): {opp['token']} {opp['buy_ex']}→{opp['sell_ex']} | прибыль {opp['profit']:.4f} USDT")
                    user_id = st.session_state.user_id if st.session_state.logged_in else (admin_user['id'] if admin_user else None)
                    if user_id:
                        profit, msg = execute_real_arbitrage(
                            opp, user_id, st.session_state.real_exchanges,
                            st.session_state.reinvest_percent,
                            st.session_state.use_orderbook, st.session_state.orderbook_depth,
                            st.session_state.max_slippage
                        )
                        if profit:
                            st.session_state.auto_log.append(f"✅ Исполнено! +{profit:.2f} USDT")
                        else:
                            st.session_state.auto_log.append(f"❌ Ошибка: {msg}")
                else:
                    st.session_state.auto_log.append("⏳ Сканирование завершено, возможностей не найдено")
        else:
            st.warning("🔐 Реальный режим требует корректных API-ключей. Проверьте их в админ-панели.")
    else:
        if st.session_state.demo_data is not None:
            if AUTOREFRESH_AVAILABLE:
                interval = st.session_state.get('scan_interval', 30)
                st_autorefresh(interval=interval * 1000, key="auto_refresh")
            now = datetime.now()
            last = st.session_state.get('last_scan_time')
            if last is None or (now - last).total_seconds() >= st.session_state.get('scan_interval', 30):
                st.session_state.last_scan_time = now
                opp = find_demo_opportunity(
                    st.session_state.fee, st.session_state.min_profit,
                    st.session_state.min_trade, st.session_state.max_trade,
                    st.session_state.orderbook_depth, st.session_state.use_orderbook,
                    st.session_state.demo_data, public_clients,
                    st.session_state.max_slippage
                )
                if opp:
                    st.session_state.auto_log.append(f"🔍 Найдено (демо): {opp['token']} {opp['buy_ex']}→{opp['sell_ex']} | прибыль {opp['profit']:.4f} USDT")
                    user_id = st.session_state.user_id if st.session_state.logged_in else (admin_user['id'] if admin_user else None)
                    if user_id:
                        profit, msg = execute_demo_arbitrage(
                            opp, user_id, st.session_state.demo_data,
                            public_clients, st.session_state.reinvest_percent,
                            st.session_state.use_orderbook, st.session_state.orderbook_depth,
                            st.session_state.max_slippage
                        )
                        if profit:
                            st.session_state.auto_log.append(f"✅ Исполнено! +{profit:.2f} USDT")
                        else:
                            st.session_state.auto_log.append(f"❌ Ошибка: {msg}")
                else:
                    st.session_state.auto_log.append("⏳ Сканирование завершено, возможностей не найдено")

# ------------------- ЛОГИН / РЕГИСТРАЦИЯ -------------------
if not st.session_state.logged_in:
    st.markdown('<div class="main-header"><h1>Арбитражный бот <span class="hovmel-highlight">HOVMEL</span></h1></div><div class="subtitle">⚡ Автоматический поиск межбиржевого арбитража 24/7 ⚡</div>', unsafe_allow_html=True)
    tab1, tab2 = st.tabs(["Вход", "Регистрация"])
    with tab1:
        email = st.text_input("Email")
        pwd = st.text_input("Пароль", type="password")
        if st.button("Войти"):
            user = get_user_by_email(email)
            pwd_hash = hashlib.sha256(pwd.encode()).hexdigest()
            if user and user['password_hash'] == pwd_hash and user['registration_status'] == 'approved':
                st.session_state.logged_in = True
                st.session_state.user_id = user['id']
                st.session_state.email = user['email']
                st.session_state.username = user['full_name']
                st.session_state.wallet = user.get('wallet_address', '')
                st.query_params.email = user['email']
                demo = load_demo_data(st.session_state.user_id)
                if demo: st.session_state.demo_data = demo
                else:
                    init_bal = {ex:{"USDT":0,"portfolio":{t:0 for t in get_available_tokens()}} for ex in EXCHANGES}
                    st.session_state.demo_data = {'balances':init_bal,'total_profit':0,'trade_count':0,'withdrawable_balance':0,'history':[]}
                    save_demo_data(st.session_state.user_id, st.session_state.demo_data)
                settings = load_user_settings(st.session_state.user_id)
                st.session_state.fee = settings.get('fee', 0.2)
                st.session_state.min_profit = settings.get('min_profit', 0.07)
                st.session_state.min_trade = settings.get('min_trade', 8.0)
                st.session_state.max_trade = settings.get('max_trade', 20.0)
                st.session_state.scan_interval = settings.get('scan_interval', 30)
                st.session_state.reinvest_percent = settings.get('reinvest_percent', 0)
                st.session_state.use_orderbook = settings.get('use_orderbook', True)
                st.session_state.max_slippage = settings.get('max_slippage', 0.3)
                st.session_state.orderbook_depth = settings.get('orderbook_depth', 20)
                st.session_state.auto_trade_enabled = settings.get('auto_trade_enabled', False)
                st.session_state.real_exchanges = init_real_exchanges()
                st.session_state.chat_unread = get_unread_count(st.session_state.user_id)
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
                        create_user(email, pwd, name, country, city, phone, wallet)
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
    if st.session_state.trade_mode == "Демо":
        st.markdown('<span class="status-running">🟢 ДЕМО РЕЖИМ</span>', unsafe_allow_html=True)
    else:
        st.markdown('<span class="status-stopped">🔴 РЕАЛЬНЫЙ РЕЖИМ</span>', unsafe_allow_html=True)
with col3:
    if st.session_state.auto_trade_enabled:
        st.markdown('<span class="status-running">▶ АВТО-СДЕЛКИ АКТИВНЫ</span>', unsafe_allow_html=True)
    else:
        st.markdown('<span class="status-stopped">⏹ АВТО-СДЕЛКИ ОСТАНОВЛЕНЫ</span>', unsafe_allow_html=True)
with col4:
    if st.button("🚪 Выйти"):
        st.session_state.logged_in = False
        st.query_params.clear()
        st.rerun()

connected = [ex.upper() for ex, cl in public_clients.items() if cl is not None]
st.success(f"🔌 Биржи для мониторинга: {', '.join(connected)}")

col_start, col_stop, col_mode, _ = st.columns([1,1,2,1])
with col_start:
    if st.button("▶ СТАРТ АВТО-ТОРГОВЛИ", use_container_width=True):
        st.session_state.auto_trade_enabled = True
        target_user_id = st.session_state.user_id if st.session_state.logged_in else (admin_user['id'] if admin_user else None)
        if target_user_id:
            settings = load_user_settings(target_user_id)
            settings['auto_trade_enabled'] = True
            save_user_settings(target_user_id, settings)
        if st.session_state.trade_mode == "Реальный":
            st.session_state.real_exchanges = init_real_exchanges()
        st.rerun()
with col_stop:
    if st.button("⏹ СТОП АВТО-ТОРГОВЛИ", use_container_width=True):
        st.session_state.auto_trade_enabled = False
        target_user_id = st.session_state.user_id if st.session_state.logged_in else (admin_user['id'] if admin_user else None)
        if target_user_id:
            settings = load_user_settings(target_user_id)
            settings['auto_trade_enabled'] = False
            save_user_settings(target_user_id, settings)
        st.rerun()
with col_mode:
    new_mode = st.radio("Режим", ["Демо", "Реальный"], horizontal=True, index=0 if st.session_state.trade_mode=="Демо" else 1)
    if new_mode != st.session_state.trade_mode:
        st.session_state.trade_mode = new_mode
        if new_mode == "Реальный":
            st.session_state.real_exchanges = init_real_exchanges()
        else:
            st.session_state.real_exchanges = None
        st.rerun()

# ------------------- РАСЧЁТ КАПИТАЛА -------------------
if st.session_state.trade_mode == "Реальный":
    if st.session_state.real_exchanges and any(st.session_state.real_exchanges.values()):
        total_usdt = sum(get_real_balance(st.session_state.real_exchanges.get(ex), 'USDT') for ex in EXCHANGES if st.session_state.real_exchanges.get(ex))
        total_portfolio = 0
        for ex in EXCHANGES:
            exch = st.session_state.real_exchanges.get(ex)
            if exch:
                for token in get_available_tokens():
                    amt = get_real_balance(exch, token)
                    if amt > 0:
                        price = get_price(exch, token)
                        if price: total_portfolio += amt * price
        total_capital = total_usdt + total_portfolio
        st.info(f"💰 **Реальные балансы** | USDT: {total_usdt:.2f} | Портфель: {total_portfolio:.2f} | Капитал: {total_capital:.2f}")
    else:
        total_usdt = 0.0
        total_portfolio = 0.0
        total_capital = 0.0
        st.warning("🔐 Реальный режим требует корректных API-ключей. Проверьте их в админ-панели.")
else:
    if st.session_state.demo_data and 'balances' in st.session_state.demo_data:
        balances = st.session_state.demo_data['balances']
    else:
        balances = {ex: {"USDT": 0, "portfolio": {t: 0 for t in get_available_tokens()}} for ex in EXCHANGES}
    total_usdt = sum(balances.get(ex, {}).get('USDT',0) for ex in EXCHANGES)
    total_portfolio = 0
    for ex in EXCHANGES:
        for token, amt in balances.get(ex, {}).get('portfolio',{}).items():
            if amt>0 and public_clients[ex]:
                price = get_price(public_clients[ex], token)
                if price: total_portfolio += amt * price
    total_capital = total_usdt + total_portfolio
    st.info(f"🎮 **Демо-балансы** | USDT: {total_usdt:.2f} | Портфель: {total_portfolio:.2f} | Капитал: {total_capital:.2f}")

col_a, col_b, col_c, col_d, col_e = st.columns(5)
col_a.metric("💰 USDT на биржах", f"{total_usdt:.2f}")
col_b.metric("📦 Портфель (токены)", f"{total_portfolio:.2f}")
col_c.metric("💎 Общий капитал", f"{total_capital:.2f}")

user_id_stats = st.session_state.user_id if st.session_state.logged_in else (admin_user['id'] if admin_user else None)
if user_id_stats:
    trades_current_mode = get_user_trades(user_id_stats, mode=st.session_state.trade_mode, limit=1000)
    total_profit_current = sum(t.get('profit', 0) for t in trades_current_mode)
else:
    total_profit_current = 0.0
col_d.metric("📈 Прибыль с запуска", f"{total_profit_current:.4f} USDT")

current_mode = st.session_state.trade_mode
if user_id_stats:
    user_trades_count = get_user_trades(user_id_stats, mode=current_mode, limit=1000)
    trade_count = len(user_trades_count)
else:
    trade_count = 0
col_e.metric("📊 Сделок", trade_count)

# ------------------- НАСТРОЙКИ -------------------
with st.expander("⚙️ Настройки арбитража", expanded=False):
    fee = st.number_input("Комиссия (%)", 0.0, 0.5, st.session_state.fee, 0.01, format="%.2f")
    min_profit = st.number_input("Мин. прибыль (USDT)", 0.001, 1.0, st.session_state.min_profit, 0.01, format="%.3f")
    min_trade = st.number_input("Минимальная сумма сделки (USDT)", 1.0, 1000.0, st.session_state.min_trade, 5.0)
    max_trade = st.number_input("Максимальная сумма сделки (USDT) (общий лимит)", 1.0, 1000.0, st.session_state.max_trade, 10.0)
    scan_interval = st.number_input("Интервал сканирования (сек)", 10, 120, st.session_state.scan_interval, 5)
    reinvest_percent = st.slider("Процент реинвестиции (только демо)", 0, 100, st.session_state.reinvest_percent, 5)
    
    use_orderbook = st.checkbox("Учитывать стакан ордеров (order book)", value=st.session_state.use_orderbook)
    if use_orderbook:
        max_slippage = st.number_input("Максимальное проскальзывание (%)", 0.05, 1.0, st.session_state.max_slippage, 0.05, format="%.2f")
        depth = st.number_input("Глубина стакана (уровней)", 5, 50, st.session_state.orderbook_depth, 5)
    else:
        max_slippage = st.session_state.max_slippage
        depth = st.session_state.orderbook_depth

    if st.button("💾 Сохранить настройки"):
        target_user_id = st.session_state.user_id if st.session_state.logged_in else (admin_user['id'] if admin_user else None)
        if target_user_id:
            save_user_settings(target_user_id, {
                'fee': fee,
                'min_profit': min_profit,
                'min_trade': min_trade,
                'max_trade': max_trade,
                'scan_interval': scan_interval,
                'reinvest_percent': reinvest_percent,
                'use_orderbook': use_orderbook,
                'max_slippage': max_slippage,
                'orderbook_depth': depth,
                'auto_trade_enabled': st.session_state.auto_trade_enabled
            })
            st.success("Настройки сохранены!")
        else:
            st.error("Пользователь не авторизован")

    st.info(f"Настройки сохранены. Учёт стакана: {'включён' if use_orderbook else 'выключен'}.")

with st.expander("📋 Лог авто-торговли", expanded=False):
    if st.session_state.auto_log:
        for log in st.session_state.auto_log[-50:]:
            st.text(log)
    else:
        st.info("Нет событий. Запустите авто-торговлю кнопкой СТАРТ.")

# ------------------- ВКЛАДКИ (сокращённо, чтобы уместить) -------------------
show_admin = is_admin(st.session_state.email) if st.session_state.logged_in else is_admin("cb777899@gmail.com")
tabs_list = ["📊 Dashboard", "📈 Графики", "🔄 Арбитраж", "📊 Статистика", "💼 Балансы", "💰 Вывод", "📜 История", "👤 Кабинет", "💬 Чат"]
if show_admin:
    tabs_list.append("👑 Админ-панель")
tabs = st.tabs(tabs_list)

# ----- Dashboard -----
with tabs[0]:
    st.subheader("📊 Dashboard")
    st.write("Добро пожаловать в арбитражного бота **HOVMEL**.")
    st.write(f"Активные токены: {', '.join(get_available_tokens())}")
    st.write(f"Текущие настройки суммы сделки: от **{st.session_state.min_trade:.0f}** до **{st.session_state.max_trade:.0f}** USDT (общий лимит).")
    st.write(f"**Минимальная прибыль:** {st.session_state.min_profit:.2f} USDT.")
    if st.session_state.trade_mode == "Реальный":
        st.success("✅ Реальный режим активен.")
    else:
        st.info("🔸 Режим демо.")
    st.markdown("---")
    st.markdown("### 💹 Текущие цены токенов")
    spread_threshold = st.session_state.min_profit / (st.session_state.min_trade / 100) if st.session_state.min_trade > 0 else 0.3
    spread_threshold += 0.1
    token_prices = []
    for token in get_available_tokens():
        row = {"Токен": token}
        for ex in EXCHANGES:
            if public_clients[ex]:
                price = get_price(public_clients[ex], token)
                row[ex.upper()] = f"{price:.8f}" if price else "—"
            else:
                row[ex.upper()] = "—"
        if row.get("KUCOIN", "—") != "—" and row.get("OKX", "—") != "—":
            try:
                diff = abs(float(row["KUCOIN"]) - float(row["OKX"])) / float(row["KUCOIN"]) * 100
                row["Спред %"] = f"{diff:.2f}%"
                is_profitable = diff > spread_threshold
                row["Арбитраж"] = "✅" if is_profitable else "❌"
            except:
                row["Спред %"] = "—"
                row["Арбитраж"] = "?"
        else:
            row["Спред %"] = "—"
            row["Арбитраж"] = "?"
        token_prices.append(row)
    df_prices = pd.DataFrame(token_prices)
    def highlight_profitable(row):
        if row.get("Арбитраж") == "✅":
            return ['background-color: #00FF88; color: black'] * len(row)
        else:
            return [''] * len(row)
    st.dataframe(df_prices.style.apply(highlight_profitable, axis=1), width='stretch', hide_index=True)
    st.caption("🟢 Зелёным выделены токены, спред по которым превышает минимальную прибыль с учётом комиссии.")

# ----- Графики (японские свечи) -----
with tabs[1]:
    st.subheader("📈 Графики (японские свечи)")
    col1, col2 = st.columns(2)
    with col1:
        tok = st.selectbox("Выберите токен", get_available_tokens())
    with col2:
        timeframe = st.selectbox("Таймфрейм", ["1m", "5m", "15m", "1h", "4h", "1d"], index=3)
    exchange_for_chart = st.selectbox("Биржа", EXCHANGES, index=0)
    
    if tok and exchange_for_chart:
        exchange = public_clients.get(exchange_for_chart)
        if exchange:
            try:
                ohlcv = exchange.fetch_ohlcv(f"{tok}/USDT", timeframe=timeframe, limit=100)
                if ohlcv:
                    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                    fig = go.Figure(data=[go.Candlestick(
                        x=df['timestamp'],
                        open=df['open'],
                        high=df['high'],
                        low=df['low'],
                        close=df['close'],
                        name=f"{tok}/USDT"
                    )])
                    fig.update_layout(
                        title=f"{tok}/USDT ({timeframe}) на {exchange_for_chart.upper()}",
                        xaxis_title="Время",
                        yaxis_title="Цена (USDT)",
                        height=600
                    )
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.warning("Нет данных для отображения")
            except Exception as e:
                st.error(f"Ошибка получения данных: {str(e)}")
        else:
            st.error(f"Биржа {exchange_for_chart.upper()} не подключена")

# ----- Арбитраж (ручной) -----
with tabs[2]:
    st.subheader("🔄 Ручной поиск арбитража")
    if st.button("🔍 Найти лучшую возможность (с учётом текущих настроек)"):
        if st.session_state.trade_mode == "Реальный":
            if not st.session_state.real_exchanges or not any(st.session_state.real_exchanges.values()):
                st.error("Реальные биржи не подключены. Проверьте API-ключи.")
            else:
                opp = find_real_opportunity(
                    st.session_state.fee, st.session_state.min_profit,
                    st.session_state.min_trade, st.session_state.max_trade,
                    st.session_state.orderbook_depth, st.session_state.use_orderbook,
                    st.session_state.real_exchanges,
                    st.session_state.max_slippage
                )
                if opp:
                    st.success(f"Найдена возможность: {opp['token']}")
                    st.write(f"**Покупка:** {opp['buy_ex'].upper()} по {opp['buy_price']:.8f} USDT")
                    st.write(f"**Продажа:** {opp['sell_ex'].upper()} по {opp['sell_price']:.8f} USDT")
                    st.write(f"**Сумма сделки:** {opp['trade_usdt']:.2f} USDT")
                    st.write(f"**Прибыль:** {opp['profit']:.4f} USDT")
                    if st.button("✅ Выполнить сделку (реал)"):
                        user_id = st.session_state.user_id if st.session_state.logged_in else (admin_user['id'] if admin_user else None)
                        if user_id:
                            profit, msg = execute_real_arbitrage(
                                opp, user_id, st.session_state.real_exchanges,
                                st.session_state.reinvest_percent,
                                st.session_state.use_orderbook, st.session_state.orderbook_depth,
                                st.session_state.max_slippage
                            )
                            if profit:
                                st.success(f"Сделка выполнена! Прибыль: {profit:.2f} USDT. {msg}")
                                st.rerun()
                            else:
                                st.error(f"Ошибка: {msg}")
                        else:
                            st.error("Пользователь не найден")
                else:
                    st.warning("Арбитражных возможностей не найдено")
        else:
            if not st.session_state.demo_data:
                st.error("Данные демо-счёта не загружены.")
            else:
                opp = find_demo_opportunity(
                    st.session_state.fee, st.session_state.min_profit,
                    st.session_state.min_trade, st.session_state.max_trade,
                    st.session_state.orderbook_depth, st.session_state.use_orderbook,
                    st.session_state.demo_data, public_clients,
                    st.session_state.max_slippage
                )
                if opp:
                    st.success(f"Найдена возможность: {opp['token']}")
                    st.write(f"**Покупка:** {opp['buy_ex'].upper()} по {opp['buy_price']:.8f} USDT")
                    st.write(f"**Продажа:** {opp['sell_ex'].upper()} по {opp['sell_price']:.8f} USDT")
                    st.write(f"**Сумма сделки:** {opp['trade_usdt']:.2f} USDT")
                    st.write(f"**Прибыль:** {opp['profit']:.4f} USDT")
                    if st.button("✅ Выполнить сделку (демо)"):
                        user_id = st.session_state.user_id if st.session_state.logged_in else (admin_user['id'] if admin_user else None)
                        if user_id:
                            profit, msg = execute_demo_arbitrage(
                                opp, user_id, st.session_state.demo_data,
                                public_clients, st.session_state.reinvest_percent,
                                st.session_state.use_orderbook, st.session_state.orderbook_depth,
                                st.session_state.max_slippage
                            )
                            if profit:
                                st.success(f"Сделка выполнена! Прибыль: {profit:.2f} USDT. {msg}")
                                st.rerun()
                            else:
                                st.error(f"Ошибка: {msg}")
                        else:
                            st.error("Пользователь не найден")
                else:
                    st.warning("Арбитражных возможностей не найдено")

# ----- Статистика (раздельно) -----
with tabs[3]:
    st.subheader("📊 Статистика")
    current_mode = st.session_state.trade_mode
    user_id_stats = st.session_state.user_id if st.session_state.logged_in else (admin_user['id'] if admin_user else None)
    if user_id_stats:
        mode_trades = get_user_trades(user_id_stats, mode=current_mode, limit=1000)
        total_profit = sum(t.get('profit', 0) for t in mode_trades)
        total_trades = len(mode_trades)
    else:
        total_profit = 0.0
        total_trades = 0
    
    if current_mode == "Демо":
        withdrawable = st.session_state.demo_data.get('withdrawable_balance', 0) if st.session_state.demo_data else 0
        st.info("📊 Статистика для **ДЕМО-режима**")
    else:
        withdrawable = 0
        st.info("📊 Статистика для **РЕАЛЬНОГО** режима")
    
    col1, col2, col3 = st.columns(3)
    col1.metric("📈 Общая прибыль", f"{total_profit:.4f} USDT")
    col2.metric("🔄 Количество сделок", total_trades)
    col3.metric("💰 Доступно для вывода", f"{withdrawable:.2f} USDT")
    
    if total_trades > 0:
        avg = total_profit / total_trades
        st.metric("📊 Средняя прибыль на сделку", f"{avg:.4f} USDT")
    
    if mode_trades:
        df_trades = pd.DataFrame(mode_trades)
        df_trades['trade_time'] = pd.to_datetime(df_trades['trade_time'])
        df_trades = df_trades.sort_values('trade_time')
        df_trades['cumulative_profit'] = df_trades['profit'].cumsum()
        fig = px.line(df_trades, x='trade_time', y='cumulative_profit', title=f"Накопленная прибыль ({current_mode} режим)")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Нет сделок для отображения графика.")

# ----- Балансы и ручная торговля -----
with tabs[4]:
    st.subheader("💼 Балансы и ручная торговля")
    if st.session_state.trade_mode == "Демо" and st.session_state.demo_data:
        st.markdown(f"**💰 Доступно для вывода (от реинвестиции):** {st.session_state.demo_data.get('withdrawable_balance',0):.2f} USDT")
        st.markdown("---")
        st.markdown("### 💰 Пополнение демо-балансов")
        col1, col2, col3 = st.columns(3)
        with col1:
            demo_exchange = st.selectbox("Биржа", EXCHANGES, key="demo_ex")
        with col2:
            asset_type = st.selectbox("Актив", ["USDT"] + get_available_tokens(), key="demo_asset")
        with col3:
            amount_add = st.number_input("Количество", min_value=0.0, step=10.0, key="demo_amount")
        if st.button("➕ Добавить на демо-счёт"):
            if amount_add > 0 and st.session_state.demo_data:
                update_demo_balance(st.session_state.user_id, demo_exchange, asset_type, amount_add, st.session_state.demo_data)
                st.success(f"Добавлено {amount_add} {asset_type} на {demo_exchange.upper()}")
                st.rerun()
        st.markdown("---")
        st.markdown("### ⚠️ Сброс демо-данных")
        if st.button("🧹 ПОЛНЫЙ СБРОС", use_container_width=True):
            reset_demo_data(st.session_state.user_id)
            st.success("Демо-данные сброшены!")
            st.rerun()
        st.warning("Это действие удалит все ваши демо-балансы, историю и статистику. Необратимо!")
        st.markdown("---")
    
    if st.session_state.trade_mode == "Реальный":
        if st.session_state.real_exchanges and any(st.session_state.real_exchanges.values()):
            balances = {}
            for ex in EXCHANGES:
                if st.session_state.real_exchanges.get(ex):
                    usdt = get_real_balance(st.session_state.real_exchanges[ex], 'USDT')
                    port = {t: get_real_balance(st.session_state.real_exchanges[ex], t) for t in get_available_tokens()}
                    balances[ex] = {'USDT': usdt, 'portfolio': port}
                else:
                    balances[ex] = {'USDT': 0, 'portfolio': {t: 0 for t in TOKENS}}
        else:
            balances = {ex: {'USDT': 0, 'portfolio': {t: 0 for t in TOKENS}} for ex in EXCHANGES}
            st.warning("Реальные биржи не подключены. Добавьте API-ключи в админ-панели.")
    else:
        if st.session_state.demo_data and 'balances' in st.session_state.demo_data:
            balances = st.session_state.demo_data['balances']
        else:
            balances = {ex: {'USDT': 0, 'portfolio': {t: 0 for t in TOKENS}} for ex in EXCHANGES}
    
    for ex in EXCHANGES:
        with st.expander(f"{ex.upper()}"):
            if ex in balances:
                st.write(f"**USDT:** {balances[ex].get('USDT', 0):.2f}")
                port = balances[ex].get('portfolio', {})
                for token, amt in port.items():
                    if amt > 0:
                        price = get_price(public_clients.get(ex), token) if public_clients.get(ex) else None
                        val = amt * price if price else 0
                        st.write(f"{token}: {amt:.8f} ≈ {val:.2f} USDT")
            else:
                st.write(f"**USDT:** 0.00")
                st.write(f"**Токены:** нет данных")
            st.markdown("---")
            colA, colB = st.columns(2)
            with colA:
                token_buy = st.selectbox("Купить", get_available_tokens(), key=f"buy_{ex}")
                usdt_buy = st.number_input("Сумма в USDT (покупка)", min_value=1.0, value=15.0, step=10.0, key=f"usdt_buy_{ex}")
                if st.button(f"Купить {token_buy}", key=f"btn_buy_{ex}"):
                    if st.session_state.trade_mode == "Реальный":
                        if st.session_state.real_exchanges.get(ex):
                            ok, msg, _, _ = real_buy_with_liquidity(
                                st.session_state.real_exchanges[ex], token_buy, usdt_buy,
                                st.session_state.max_slippage, st.session_state.orderbook_depth,
                                st.session_state.use_orderbook
                            )
                        else:
                            ok, msg = False, "Биржа не подключена"
                    else:
                        if not st.session_state.demo_data:
                            st.error("Нет демо-данных")
                        else:
                            client = public_clients.get(ex)
                            if client is None:
                                st.error(f"Биржа {ex.upper()} не подключена для получения цен")
                            else:
                                ok, msg = demo_buy(st.session_state.user_id, ex, token_buy, usdt_buy, st.session_state.demo_data, public_clients, is_manual=True)
                    if ok:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
            with colB:
                token_sell = st.selectbox("Продать", get_available_tokens(), key=f"sell_{ex}")
                usdt_sell = st.number_input("Сумма в USDT (продажа)", min_value=1.0, value=15.0, step=10.0, key=f"usdt_sell_{ex}")
                if st.button(f"Продать {token_sell} на {usdt_sell} USDT", key=f"btn_sell_{ex}"):
                    if st.session_state.trade_mode == "Реальный":
                        if st.session_state.real_exchanges.get(ex):
                            ok, msg, _, _ = real_sell_with_liquidity(
                                st.session_state.real_exchanges[ex], token_sell, usdt_sell,
                                st.session_state.max_slippage, st.session_state.orderbook_depth,
                                st.session_state.use_orderbook
                            )
                        else:
                            ok, msg = False, "Биржа не подключена"
                    else:
                        if not st.session_state.demo_data:
                            st.error("Нет демо-данных")
                        else:
                            client = public_clients.get(ex)
                            if client is None:
                                st.error(f"Биржа {ex.upper()} не подключена для получения цен")
                            else:
                                ok, msg = demo_sell(st.session_state.user_id, ex, token_sell, usdt_sell, st.session_state.demo_data, public_clients, is_manual=True)
                    if ok:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)

# ----- Вывод -----
with tabs[5]:
    st.subheader("💰 Вывод средств")
    st.info("Вывод возможен только после одобрения администратором (комиссия 22%).")
    if st.session_state.trade_mode == "Реальный":
        withdrawable = 0.0
    else:
        withdrawable = st.session_state.demo_data.get('withdrawable_balance', 0.0) if st.session_state.demo_data else 0.0
    st.write(f"Доступно для вывода: **{withdrawable:.2f} USDT**")
    amount = st.number_input("Сумма вывода (USDT)", min_value=1.0, max_value=max(1.0, withdrawable), step=10.0)
    wallet = st.text_input("Адрес USDT (TRC20)", value=st.session_state.wallet)
    if st.button("Запросить вывод"):
        if amount > 0 and wallet and withdrawable >= amount:
            create_withdrawal_request(st.session_state.user_id, amount, wallet)
            st.success("Заявка на вывод отправлена администратору!")
        else:
            st.error("Введите корректную сумму и адрес")

# ----- История (раздельно) -----
with tabs[6]:
    st.subheader("📜 История сделок")
    current_mode = st.session_state.trade_mode
    user_id_hist = st.session_state.user_id if st.session_state.logged_in else (admin_user['id'] if admin_user else None)
    if user_id_hist:
        trades = get_user_trades(user_id_hist, mode=current_mode, limit=100)
    else:
        trades = []
    if trades:
        df = pd.DataFrame(trades)
        df_display = df[['trade_time', 'asset', 'amount', 'profit', 'buy_exchange', 'sell_exchange', 'mode']].copy()
        df_display['trade_time'] = pd.to_datetime(df_display['trade_time']).dt.strftime('%Y-%m-%d %H:%M')
        df_display['amount'] = df_display['amount'].apply(lambda x: f"{x:.8f}")
        df_display['profit'] = df_display['profit'].apply(lambda x: f"{x:.4f}")
        df_display.columns = ['Время', 'Актив', 'Количество', 'Прибыль (USDT)', 'Покупка', 'Продажа', 'Режим']
        st.dataframe(df_display, width='stretch')
    else:
        st.info(f"Нет сделок в {current_mode} режиме.")

# ----- Кабинет -----
with tabs[7]:
    st.subheader("👤 Личный кабинет")
    col1, col2 = st.columns(2)
    with col1:
        st.write(f"**Имя:** {st.session_state.username if st.session_state.logged_in else 'Гость'}")
        st.write(f"**Email:** {st.session_state.email if st.session_state.logged_in else 'Не авторизован'}")
        st.write(f"**Кошелёк:** {st.session_state.wallet if st.session_state.logged_in else '—'}")
    with col2:
        user_id_cab = st.session_state.user_id if st.session_state.logged_in else (admin_user['id'] if admin_user else None)
        if user_id_cab:
            all_trades = get_user_trades(user_id_cab, limit=1000)
            total_profit_all = sum(t.get('profit',0) for t in all_trades)
            total_trades_all = len(all_trades)
        else:
            total_profit_all = 0.0
            total_trades_all = 0
        st.write(f"**Всего сделок (все режимы):** {total_trades_all}")
        st.write(f"**Общая прибыль (все режимы):** {total_profit_all:.4f} USDT")
        st.write(f"**Общий капитал:** {total_capital:.2f} USDT")

# ----- Чат -----
with tabs[8]:
    st.subheader("💬 Чат поддержки")
    if st.session_state.chat_unread > 0:
        st.info(f"📬 У вас {st.session_state.chat_unread} непрочитанных сообщений от администратора")
    messages = get_cached_messages(st.session_state.user_id, 50)
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

# ----- Админ-панель -----
if show_admin:
    with tabs[9]:
        st.subheader("👑 Административная панель")
        admin_tabs = st.tabs(["Пользователи", "API ключи", "Выводы", "Конфиг", "Сообщения"])
        
        with admin_tabs[0]:
            st.markdown("#### Управление пользователями")
            users = get_cached_users()
            for user in users:
                with st.expander(f"{user['email']} - {user['full_name']}"):
                    st.write(f"Статус: {user['registration_status']}")
                    st.write(f"Сделок: {user.get('trade_count', 0)}")
                    new_status = st.selectbox("Изменить статус", ["approved", "blocked"], key=f"status_{user['id']}")
                    if st.button("Обновить", key=f"update_{user['id']}"):
                        update_user_status(user['id'], new_status)
                        st.rerun()
        
        with admin_tabs[1]:
            st.markdown("#### API ключи бирж")
            st.warning("⚠️ Введите свои реальные API-ключи от KuCoin и OKX с правами на спотовую торговлю. Они будут зашифрованы. Для KuCoin и OKX обязательно укажите Passphrase.")
            for ex in EXCHANGES:
                with st.expander(f"{ex.upper()}"):
                    api_key = st.text_input(f"API Key ({ex})", type="password", value="", key=f"api_{ex}")
                    secret = st.text_input(f"Secret Key ({ex})", type="password", value="", key=f"sec_{ex}")
                    passphrase = st.text_input(f"Passphrase ({ex})", type="password", value="", key=f"pass_{ex}")
                    if st.button(f"Сохранить {ex}", key=f"save_{ex}"):
                        if api_key and secret and passphrase:
                            save_api_key(ex, api_key, secret, passphrase, st.session_state.email)
                            st.success(f"Ключи для {ex} сохранены и зашифрованы")
                            st.session_state.real_exchanges = init_real_exchanges()
                            st.rerun()
                        else:
                            st.error(f"Для {ex} необходимо заполнить все поля: API Key, Secret Key и Passphrase.")
        
        with admin_tabs[2]:
            st.markdown("#### Заявки на вывод")
            withdrawals = get_cached_withdrawals()
            for w in withdrawals:
                with st.expander(f"{w['users']['email']} - {w['amount']} USDT"):
                    st.write(f"Сумма: {w['amount']} USDT, комиссия 22%: {w['admin_fee']:.2f}, к получению: {w['user_receives']:.2f}")
                    st.write(f"Кошелёк: {w['wallet_address']}")
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button("✅ Одобрить", key=f"approve_{w['id']}"):
                            update_withdrawal_status(w['id'], 'approved')
                            st.rerun()
                    with col2:
                        if st.button("❌ Отклонить", key=f"reject_{w['id']}"):
                            update_withdrawal_status(w['id'], 'rejected')
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
            all_messages = get_cached_messages(None, 100)
            for msg in all_messages:
                if not msg['is_admin_reply']:
                    st.markdown(f"**{msg['user_name']}** ({msg['user_email']}): {msg['message']}  \n*{msg['created_at'][:16]}*")
                    reply = st.text_area("Ответ", key=f"reply_{msg['id']}")
                    if st.button("Отправить ответ", key=f"send_{msg['id']}"):
                        add_message(msg['user_id'], msg['user_email'], "Admin", reply, True)
                        st.rerun()
                    st.divider()
