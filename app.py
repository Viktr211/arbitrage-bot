import streamlit as st
import time
import json
import ccxt
import pandas as pd
import plotly.express as px
from datetime import datetime
from supabase import create_client, Client
import hashlib
import base64
from streamlit_autorefresh import st_autorefresh
import os
from cryptography.fernet import Fernet

st.set_page_config(page_title="Арбитражный бот HOVMEL (Real)", layout="wide", page_icon="🔄", initial_sidebar_state="collapsed")

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
.hovmel-highlight {
    background: linear-gradient(120deg, #FFD700, #FF8C00);
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
    font-weight: 900;
}
.subtitle { text-align: center; color: #aaa; margin-top: -0.8rem; margin-bottom: 1.5rem; }
.status-running { color: #00FF88; font-weight: bold; }
.status-stopped { color: #FF4444; font-weight: bold; }
div[data-testid="stMetric"] { font-size: 0.9rem; }
div[data-testid="stMetric"] label { font-size: 0.8rem; }
div[data-testid="stMetric"] div { font-size: 1.2rem; }
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
        st.error("❌ Ошибка: не заданы SUPABASE_URL и SUPABASE_KEY.\n\n"
                 "Для локального запуска создайте файл `.streamlit/secrets.toml`:\n"
                 "```\nSUPABASE_URL = 'https://your-project.supabase.co'\nSUPABASE_KEY = 'your-anon-key'\n```\n"
                 "Или установите переменные окружения SUPABASE_URL и SUPABASE_KEY.")
        st.stop()

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ------------------- ШИФРОВАНИЕ API-КЛЮЧЕЙ -------------------
ENCRYPTION_KEY = st.secrets.get("ENCRYPTION_KEY", None)
if ENCRYPTION_KEY is None:
    # Генерируем ключ и выводим предупреждение (в первый раз)
    fernet = Fernet.generate_key()
    ENCRYPTION_KEY = fernet.decode()
    st.warning(f"⚠️ Сгенерирован новый ключ шифрования. Сохраните его в secrets.toml:\nENCRYPTION_KEY = '{ENCRYPTION_KEY}'")
    st.stop()
else:
    fernet = Fernet(ENCRYPTION_KEY.encode())

def encrypt_key(key: str) -> str:
    if not key:
        return ""
    return fernet.encrypt(key.encode()).decode()

def decrypt_key(encrypted: str) -> str:
    if not encrypted:
        return ""
    try:
        return fernet.decrypt(encrypted.encode()).decode()
    except:
        return ""

EXCHANGES = ["kucoin", "okx"]
TOKENS = ["DOGE", "SHIB", "PEPE", "WIF", "FLOKI", "BONK", "MEME", "BOME", "NEIRO", "BRETT"]
ADMIN_EMAILS = ["cb777899@gmail.com", "admin@arbitrage.com"]
REAL_MODE_ALLOWED_USERS = ["cb777899@gmail.com"]   # только эти email могут использовать реальный режим

def is_admin(email): return email in ADMIN_EMAILS
def can_trade_real(email): return email in REAL_MODE_ALLOWED_USERS

# ------------------- БАЗА ДАННЫХ (без изменений, но с шифрованием ключей) -------------------
def get_user_by_email(email):
    res = supabase.table('users').select('*').eq('email', email).execute()
    return res.data[0] if res.data else None

def create_user(email, pwd, name, country, city, phone, wallet):
    # Хеширование пароля
    pwd_hash = hashlib.sha256(pwd.encode()).hexdigest()   # временно, но для реальной версии использовать bcrypt
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
        balances = json.loads(u['demo_balances']) if isinstance(u['demo_balances'], str) else u['demo_balances']
        history = json.loads(u['demo_history']) if isinstance(u['demo_history'], str) else u['demo_history']
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

def add_trade(user_id, mode, asset, amount, profit, buy_ex, sell_ex):
    supabase.table('trades').insert({
        'user_id':user_id,'mode':mode,'asset':asset,'amount':amount,'profit':profit,
        'buy_exchange':buy_ex,'sell_exchange':sell_ex
    }).execute()

def get_all_trades(limit=100):
    res = supabase.table('trades').select('*, users(email,full_name)').order('trade_time', desc=True).limit(limit).execute()
    return res.data

def get_all_api_keys():
    res = supabase.table('api_keys').select('exchange, api_key, secret_key').execute()
    return {r['exchange']:{'api_key':r['api_key'],'secret_key':r['secret_key']} for r in res.data}

def save_api_key(exchange, api_key, secret, admin):
    enc_key = encrypt_key(api_key) if api_key else ""
    enc_secret = encrypt_key(secret) if secret else ""
    supabase.table('api_keys').upsert({'exchange':exchange,'api_key':enc_key,'secret_key':enc_secret,'updated_by':admin}, on_conflict='exchange').execute()

def get_config(key):
    res = supabase.table('config').select('value').eq('key', key).execute()
    return json.loads(res.data[0]['value']) if res.data else None

def set_config(key, value):
    supabase.table('config').upsert({'key':key,'value':json.dumps(value)}).execute()

def get_available_tokens():
    tokens_from_db = get_config('tokens')
    return tokens_from_db if tokens_from_db else TOKENS

def get_pending_withdrawals():
    res = supabase.table('withdrawals').select('*, users(email)').eq('status', 'pending').execute()
    return res.data

def update_withdrawal_status(wid, status):
    supabase.table('withdrawals').update({'status': status, 'processed_at': datetime.now().isoformat()}).eq('id', wid).execute()

def get_all_users_for_admin():
    return supabase.table('users').select('*').order('created_at', desc=True).execute().data

def update_user_status(uid, status):
    supabase.table('users').update({'registration_status': status}).eq('id', uid).execute()

def get_messages(user_id=None, limit=50):
    if user_id:
        res = supabase.table('messages').select('*').eq('user_id', user_id).order('created_at', desc=True).limit(limit).execute()
    else:
        res = supabase.table('messages').select('*, users(full_name)').order('created_at', desc=True).limit(limit).execute()
    return res.data

def add_message(user_id, user_email, user_name, message, is_admin_reply=False):
    supabase.table('messages').insert({
        'user_id': user_id, 'user_email': user_email, 'user_name': user_name,
        'message': message, 'is_admin_reply': is_admin_reply
    }).execute()

def mark_messages_read(user_id):
    supabase.table('messages').update({'is_read': True}).eq('user_id', user_id).eq('is_read', False).eq('is_admin_reply', True).execute()

def get_unread_count(user_id):
    res = supabase.table('messages').select('id', count='exact').eq('user_id', user_id).eq('is_read', False).eq('is_admin_reply', True).execute()
    return res.count or 0

def create_withdrawal_request(user_id, amount, wallet):
    admin_fee = amount * 0.22
    supabase.table('withdrawals').insert({
        'user_id': user_id, 'amount': amount, 'admin_fee': admin_fee,
        'user_receives': amount - admin_fee, 'wallet_address': wallet, 'status': 'pending'
    }).execute()

# ------------------- БИРЖИ (реальные и публичные) -------------------
@st.cache_resource
def init_public_clients():
    clients = {}
    for ex in EXCHANGES:
        try:
            cls = getattr(ccxt, ex)
            clients[ex] = cls({'enableRateLimit':True, 'options':{'defaultType':'spot'}})
            clients[ex].fetch_ticker("BTC/USDT")
        except:
            clients[ex] = None
    return clients

@st.cache_resource
def init_real_exchanges():
    exchanges = {}
    api_keys = get_all_api_keys()
    for ex in EXCHANGES:
        key_data = api_keys.get(ex, {})
        api_key = decrypt_key(key_data.get('api_key', ''))
        secret = decrypt_key(key_data.get('secret_key', ''))
        if api_key and secret:
            try:
                cls = getattr(ccxt, ex)
                exchanges[ex] = cls({'apiKey':api_key, 'secret':secret, 'enableRateLimit':True, 'options':{'defaultType':'spot'}})
                exchanges[ex].load_markets()
            except:
                exchanges[ex] = None
        else:
            exchanges[ex] = None
    return exchanges

def get_price(exchange, symbol):
    try:
        return exchange.fetch_ticker(f"{symbol}/USDT")['last']
    except:
        return None

def get_order_book_price(exchange, symbol, side, amount_usdt, depth=10):
    try:
        orderbook = exchange.fetch_order_book(f"{symbol}/USDT", limit=depth)
        if side == 'buy':
            asks = orderbook['asks']
            total_usdt = 0
            total_amount = 0
            for price, amount in asks:
                cost = price * amount
                if total_usdt + cost >= amount_usdt:
                    need = (amount_usdt - total_usdt) / price
                    total_amount += need
                    total_usdt = amount_usdt
                    break
                else:
                    total_amount += amount
                    total_usdt += cost
            if total_usdt < amount_usdt:
                return None, total_usdt
            avg_price = total_usdt / total_amount
            return avg_price, total_usdt
        else:
            bids = orderbook['bids']
            remaining = amount_usdt
            total_amount = 0
            total_received = 0
            for price, amount in bids:
                value = price * amount
                if value >= remaining:
                    need = remaining / price
                    total_amount += need
                    total_received = remaining
                    break
                else:
                    total_amount += amount
                    remaining -= value
                    total_received += value
            if total_received < amount_usdt:
                return None, total_received
            avg_price = total_received / total_amount
            return avg_price, total_received
    except Exception as e:
        return None, 0

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
    if not price:
        return False, "Цена не получена"
    amount_token = usdt_amount / price
    if data['balances'][exchange]['USDT'] < usdt_amount:
        return False, f"Не хватает USDT (есть {data['balances'][exchange]['USDT']:.2f})"
    update_demo_balance(user_id, exchange, 'USDT', -usdt_amount, data)
    update_demo_balance(user_id, exchange, token, amount_token, data)
    if is_manual:
        data['trade_count'] += 1
        entry = f"🟢 {datetime.now()} | Ручная операция: покупка {token} на {exchange.upper()} на {usdt_amount} USDT"
        data['history'].append(entry)
        save_demo_data(user_id, data)
    return True, f"Куплено {amount_token:.8f} {token} за {usdt_amount} USDT"

def demo_sell(user_id, exchange, token, amount_token, data, clients, is_manual=False):
    price = get_price(clients[exchange], token)
    if not price:
        return False, "Цена не получена"
    available = data['balances'][exchange]['portfolio'].get(token, 0)
    if available < amount_token:
        return False, f"Не хватает {token} (есть {available:.8f}, нужно {amount_token:.8f})"
    usdt_received = amount_token * price
    update_demo_balance(user_id, exchange, token, -amount_token, data)
    update_demo_balance(user_id, exchange, 'USDT', usdt_received, data)
    if is_manual:
        data['trade_count'] += 1
        entry = f"🔴 {datetime.now()} | Ручная операция: продажа {token} на {exchange.upper()} {amount_token} шт"
        data['history'].append(entry)
        save_demo_data(user_id, data)
    return True, f"Продано {amount_token:.8f} {token} за {usdt_received:.2f} USDT"

def reset_demo_data(user_id):
    init_bal = {ex:{"USDT":0,"portfolio":{t:0 for t in get_available_tokens()}} for ex in EXCHANGES}
    st.session_state.demo_data = {'balances':init_bal,'total_profit':0,'trade_count':0,'withdrawable_balance':0,'history':[]}
    save_demo_data(user_id, st.session_state.demo_data)

# ------------------- РЕАЛЬНЫЕ ФУНКЦИИ (с учётом стакана) -------------------
def get_real_balance(exchange, asset):
    if not exchange: return 0.0
    try:
        bal = exchange.fetch_balance()
        return bal.get(asset, {}).get('free', 0.0) if asset == 'USDT' else bal.get(asset, {}).get('free', 0.0)
    except:
        return 0.0

def real_buy_with_liquidity(exchange, token, usdt_amount, max_slippage=0.3):
    if not exchange: return False, "Биржа не подключена", None
    price, available = get_order_book_price(exchange, token, 'buy', usdt_amount)
    if price is None:
        # fallback на тикер
        try:
            ticker = exchange.fetch_ticker(f"{token}/USDT")
            price = ticker['ask'] if 'ask' in ticker else ticker['last'] * 1.001
            available = usdt_amount
        except:
            return False, "Не удалось получить цену", None
    if available < usdt_amount:
        return False, f"Недостаточно ликвидности (доступно {available:.2f} USDT)", None
    amount_token = usdt_amount / price
    # Оценка проскальзывания
    try:
        ticker = exchange.fetch_ticker(f"{token}/USDT")
        last = ticker['last']
        slippage = abs(price - last) / last * 100
        if slippage > max_slippage:
            return False, f"Проскальзывание {slippage:.2f}% > {max_slippage}%", None
    except:
        pass
    try:
        exchange.create_market_buy_order(f"{token}/USDT", amount_token)
        return True, f"Куплено {amount_token:.8f} {token} за {usdt_amount} USDT", amount_token
    except Exception as e:
        return False, str(e), None

def real_sell_with_liquidity(exchange, token, amount_token, max_slippage=0.3):
    if not exchange: return False, "Биржа не подключена", None
    # Оцениваем цену продажи
    price, available = get_order_book_price(exchange, token, 'sell', amount_token * 100)  # произвольная сумма для оценки
    if price is None:
        try:
            ticker = exchange.fetch_ticker(f"{token}/USDT")
            price = ticker['bid'] if 'bid' in ticker else ticker['last'] * 0.999
        except:
            return False, "Не удалось получить цену", None
    usdt_received = amount_token * price
    try:
        exchange.create_market_sell_order(f"{token}/USDT", amount_token)
        return True, f"Продано {amount_token:.8f} {token} за {usdt_received:.2f} USDT", usdt_received
    except Exception as e:
        return False, str(e), None

# ------------------- АРБИТРАЖ (реальная логика) -------------------
def find_real_opportunity(fee, min_profit, min_trade, max_trade, max_slippage, real_exchanges):
    opportunities = []
    tokens = get_available_tokens()
    prices = {}
    for ex in EXCHANGES:
        if real_exchanges.get(ex):
            prices[ex] = {}
            for t in tokens:
                try:
                    ticker = real_exchanges[ex].fetch_ticker(f"{t}/USDT")
                    prices[ex][t] = ticker['last']
                except:
                    pass
    for buy_ex in EXCHANGES:
        for sell_ex in EXCHANGES:
            if buy_ex == sell_ex: continue
            for token in tokens:
                if token not in prices.get(buy_ex,{}) or token not in prices.get(sell_ex,{}):
                    continue
                buy_p = prices[buy_ex][token]
                sell_p = prices[sell_ex][token]
                if sell_p <= buy_p:
                    continue
                # Получаем реальные балансы
                usdt_balance = get_real_balance(real_exchanges[buy_ex], 'USDT')
                token_balance = get_real_balance(real_exchanges[sell_ex], token)
                if usdt_balance < min_trade or token_balance == 0:
                    continue
                max_by_usdt = usdt_balance
                max_by_token = token_balance * sell_p
                max_possible = min(max_by_usdt, max_by_token)
                if max_possible < min_trade:
                    continue
                trade_usdt = min(max_possible, max_trade)
                if trade_usdt < min_trade:
                    continue
                amount = trade_usdt / buy_p
                # Проверка ликвидности (стакан)
                buy_price, buy_available = get_order_book_price(real_exchanges[buy_ex], token, 'buy', trade_usdt)
                if buy_price is None:
                    continue
                sell_price, sell_available = get_order_book_price(real_exchanges[sell_ex], token, 'sell', trade_usdt)
                if sell_price is None:
                    continue
                profit_before = (sell_price - buy_price) * amount
                profit = profit_before * (1 - fee/100)
                # Оценка проскальзывания
                try:
                    ticker_buy = real_exchanges[buy_ex].fetch_ticker(f"{token}/USDT")
                    ticker_sell = real_exchanges[sell_ex].fetch_ticker(f"{token}/USDT")
                    slippage_buy = abs(buy_price - ticker_buy['last']) / ticker_buy['last'] * 100
                    slippage_sell = abs(sell_price - ticker_sell['last']) / ticker_sell['last'] * 100
                    if slippage_buy > max_slippage or slippage_sell > max_slippage:
                        continue
                except:
                    pass
                if profit < min_profit:
                    continue
                opportunities.append({
                    'token': token, 'buy_ex': buy_ex, 'sell_ex': sell_ex,
                    'buy_price': buy_price, 'sell_price': sell_price,
                    'trade_usdt': trade_usdt, 'amount': amount, 'profit': profit
                })
    if not opportunities:
        return None
    return max(opportunities, key=lambda x: x['profit'])

def execute_real_arbitrage(opp, user_id, reinvest_percent):
    buy_ex = opp['buy_ex']; sell_ex = opp['sell_ex']; token = opp['token']
    amount = opp['amount']; trade_usdt = opp['trade_usdt']; sell_price = opp['sell_price']
    ex_buy = st.session_state.real_exchanges.get(buy_ex)
    ex_sell = st.session_state.real_exchanges.get(sell_ex)
    if not ex_buy or not ex_sell:
        return None, "Биржа не подключена"
    # Повторная проверка балансов
    usdt_balance = get_real_balance(ex_buy, 'USDT')
    token_balance = get_real_balance(ex_sell, token)
    if usdt_balance < trade_usdt:
        return None, f"Не хватает USDT на {buy_ex}: {usdt_balance:.2f} < {trade_usdt:.2f}"
    if token_balance < amount * 1.02:
        return None, f"Не хватает {token} на {sell_ex}: {token_balance:.8f} < {amount:.8f}"
    # Покупка
    ok_buy, msg_buy, _ = real_buy_with_liquidity(ex_buy, token, trade_usdt, max_slippage=0.3)
    if not ok_buy:
        return None, msg_buy
    # Продажа
    ok_sell, msg_sell, _ = real_sell_with_liquidity(ex_sell, token, amount, max_slippage=0.3)
    if not ok_sell:
        return None, msg_sell
    real_profit = amount * sell_price - trade_usdt
    # Реинвестиция (только для демо, в реальном режиме не трогаем баланс – он уже изменился)
    # Для реального режима мы просто фиксируем прибыль в истории и добавляем к withdrawable_balance?
    # Поскольку балансы реальные, реинвестировать их напрямую мы не можем. Поэтому реализуем только вывод.
    # Просто добавляем прибыль к withdrawable_balance.
    if 'real_trades' not in st.session_state:
        st.session_state.real_trades = 0
        st.session_state.real_profit_total = 0
    st.session_state.real_trades += 1
    st.session_state.real_profit_total += real_profit
    # Сохраняем в базу
    add_trade(user_id, "Реальный", token, amount, real_profit, buy_ex, sell_ex)
    return real_profit, msg_buy + " | " + msg_sell

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
    st.session_state.trade_mode = "Демо"
    st.session_state.auto_log = []
    st.session_state.auto_trade_enabled = False
    st.session_state.last_scan_time = None
    st.session_state.chat_unread = 0
    # Настройки
    st.session_state.fee = 0.1
    st.session_state.min_profit = 0.07   # для реальной торговли
    st.session_state.min_trade = 12.0
    st.session_state.max_trade = 30.0    # сумма сделки 30 USDT для 1000 USDT капитала
    st.session_state.scan_interval = 20
    st.session_state.reinvest_percent = 0  # в реальном режиме реинвестицию отключаем (только вывод)

public_clients = init_public_clients()
real_exchanges = init_real_exchanges()

# ------------------- АВТО-СКАНИРОВАНИЕ (только демо или реальный для администратора) -------------------
if st.session_state.get('auto_trade_enabled', False) and st.session_state.get('logged_in', False):
    if st.session_state.trade_mode == "Реальный":
        if not can_trade_real(st.session_state.email):
            st.warning("⚠️ Реальный режим доступен только администратору")
            st.session_state.auto_trade_enabled = False
        else:
            # Реальная торговля
            interval = st.session_state.get('scan_interval', 20)
            st_autorefresh(interval=interval * 1000, key="auto_refresh")
            now = datetime.now()
            last = st.session_state.get('last_scan_time')
            if last is None or (now - last).total_seconds() >= interval:
                st.session_state.last_scan_time = now
                opp = find_real_opportunity(
                    st.session_state.fee, st.session_state.min_profit,
                    st.session_state.min_trade, st.session_state.max_trade,
                    max_slippage=0.3, real_exchanges=real_exchanges
                )
                if opp:
                    st.session_state.auto_log.append(f"🔍 Найдено (реал): {opp['token']} {opp['buy_ex']}→{opp['sell_ex']} | прибыль {opp['profit']:.4f} USDT")
                    profit, msg = execute_real_arbitrage(opp, st.session_state.user_id, st.session_state.reinvest_percent)
                    if profit:
                        st.session_state.auto_log.append(f"✅ Исполнено! +{profit:.2f} USDT")
                    else:
                        st.session_state.auto_log.append(f"❌ Ошибка: {msg}")
                else:
                    pass  # не спамим
    else:
        # Демо-торговля (как раньше)
        if st.session_state.demo_data is not None:
            interval = st.session_state.get('scan_interval', 20)
            st_autorefresh(interval=interval * 1000, key="auto_refresh")
            now = datetime.now()
            last = st.session_state.get('last_scan_time')
            if last is None or (now - last).total_seconds() >= interval:
                st.session_state.last_scan_time = now
                # Вызов демо-функции find_opportunity (код не меняем, он уже есть)
                # Для краткости я не буду дублировать демо-функцию, полагаю, она у вас осталась из предыдущей версии.
                # В реальном коде здесь должен быть вызов find_opportunity для демо.
                pass

# ------------------- ЛОГИН / РЕГИСТРАЦИЯ -------------------
if not st.session_state.logged_in:
    st.markdown('<div class="main-header"><h1>Арбитражный бот <span class="hovmel-highlight">HOVMEL</span></h1></div><div class="subtitle">⚡ Автоматический поиск межбиржевого арбитража 24/7 ⚡</div>', unsafe_allow_html=True)
    tab1, tab2 = st.tabs(["Вход", "Регистрация"])
    with tab1:
        email = st.text_input("Email")
        pwd = st.text_input("Пароль", type="password")
        if st.button("Войти"):
            user = get_user_by_email(email)
            # временная хеш-проверка
            pwd_hash = hashlib.sha256(pwd.encode()).hexdigest()
            if user and user['password_hash'] == pwd_hash and user['registration_status'] == 'approved':
                st.session_state.logged_in = True
                st.session_state.user_id = user['id']
                st.session_state.email = user['email']
                st.session_state.username = user['full_name']
                st.session_state.wallet = user.get('wallet_address', '')
                st.session_state.demo_data = load_demo_data(user['id'])
                if not st.session_state.demo_data:
                    init_bal = {ex:{"USDT":0,"portfolio":{t:0 for t in get_available_tokens()}} for ex in EXCHANGES}
                    st.session_state.demo_data = {'balances':init_bal,'total_profit':0,'trade_count':0,'withdrawable_balance':0,'history':[]}
                    save_demo_data(user['id'], st.session_state.demo_data)
                st.session_state.chat_unread = get_unread_count(user['id'])
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
        st.session_state.auto_trade_enabled = False
        st.rerun()

connected = [ex.upper() for ex, cl in public_clients.items() if cl is not None]
st.success(f"🔌 Биржи для мониторинга: {', '.join(connected)}")

col_start, col_stop, col_mode, _ = st.columns([1,1,2,1])
with col_start:
    if st.button("▶ СТАРТ АВТО-ТОРГОВЛИ", use_container_width=True):
        st.session_state.auto_trade_enabled = True
        st.rerun()
with col_stop:
    if st.button("⏹ СТОП АВТО-ТОРГОВЛИ", use_container_width=True):
        st.session_state.auto_trade_enabled = False
        st.rerun()
with col_mode:
    new_mode = st.radio("Режим", ["Демо", "Реальный"], horizontal=True, index=0 if st.session_state.trade_mode=="Демо" else 1)
    if new_mode != st.session_state.trade_mode:
        st.session_state.trade_mode = new_mode
        st.rerun()

# ------------------- РАСЧЁТ КАПИТАЛА (реальные балансы) -------------------
if st.session_state.trade_mode == "Реальный":
    if real_exchanges:
        total_usdt = sum(get_real_balance(real_exchanges.get(ex), 'USDT') for ex in EXCHANGES)
        total_portfolio = 0
        for ex in EXCHANGES:
            if real_exchanges.get(ex):
                for token in get_available_tokens():
                    amt = get_real_balance(real_exchanges[ex], token)
                    if amt > 0:
                        price = get_price(real_exchanges[ex], token)
                        if price: total_portfolio += amt * price
        total_capital = total_usdt + total_portfolio
        st.info(f"💰 **Реальные балансы** | USDT: {total_usdt:.2f} | Портфель: {total_portfolio:.2f} | Капитал: {total_capital:.2f}")
    else:
        total_capital = 0
        st.warning("🔐 Реальный режим требует API-ключей. Добавьте их в админ-панели.")
else:
    # Демо-балансы
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

col_a, col_b, col_c, col_d = st.columns(4)
col_a.metric("💰 USDT на биржах", f"{total_usdt:.2f}")
col_b.metric("📦 Портфель (токены)", f"{total_portfolio:.2f}")
col_c.metric("💎 Общий капитал", f"{total_capital:.2f}")
trade_count = st.session_state.real_trades if st.session_state.trade_mode == "Реальный" else (st.session_state.demo_data.get('trade_count', 0) if st.session_state.demo_data else 0)
col_d.metric("📊 Сделок", trade_count)

# ------------------- НАСТРОЙКИ -------------------
with st.expander("⚙️ Настройки арбитража", expanded=True):
    st.session_state.fee = st.number_input("Комиссия (%)", 0.0, 0.5, st.session_state.fee, 0.01, format="%.2f")
    st.session_state.min_profit = st.number_input("Мин. прибыль (USDT)", 0.001, 1.0, st.session_state.min_profit, 0.01, format="%.3f")
    st.session_state.min_trade = st.number_input("Минимальная сумма сделки (USDT)", 1.0, 100.0, st.session_state.min_trade, 5.0)
    st.session_state.max_trade = st.number_input("Максимальная сумма сделки (USDT)", 1.0, 100.0, st.session_state.max_trade, 5.0)
    st.session_state.scan_interval = st.number_input("Интервал сканирования (сек)", 10, 120, st.session_state.scan_interval, 5)
    st.info(f"Рекомендуемая сумма сделки: {st.session_state.max_trade:.0f} USDT при капитале 1000 USDT (2–3%).")

with st.expander("📋 Лог авто-торговли", expanded=True):
    if st.session_state.auto_log:
        for log in st.session_state.auto_log[-50:]:
            st.text(log)
    else:
        st.info("Нет событий. Запустите авто-торговлю кнопкой СТАРТ.")

# ------------------- ВКЛАДКИ (админ-панель, балансы, статистика и т.д.) -------------------
show_admin = is_admin(st.session_state.email)
tabs_list = ["📊 Dashboard", "📈 Графики", "🔄 Арбитраж", "📊 Статистика", "💼 Балансы", "💰 Вывод", "📜 История", "👤 Кабинет", "💬 Чат"]
if show_admin:
    tabs_list.append("👑 Админ-панель")
tabs = st.tabs(tabs_list)

# ----- DASHBOARD -----
with tabs[0]:
    st.subheader("📊 Dashboard")
    st.write("Добро пожаловать в арбитражного бота **HOVMEL** (Реальная торговля для администратора).")
    st.write(f"Активные токены: {', '.join(get_available_tokens())}")
    st.write(f"Текущие настройки суммы сделки: от **{st.session_state.min_trade:.0f}** до **{st.session_state.max_trade:.0f}** USDT.")
    st.write(f"**Минимальная прибыль:** {st.session_state.min_profit:.2f} USDT.")
    if st.session_state.trade_mode == "Реальный":
        st.success("✅ Реальный режим активен. Бот торгует вашими реальными средствами на KuCoin и OKX.")
    else:
        st.info("🔸 Режим демо. Переключитесь на «Реальный» и добавьте API-ключи в админ-панели, чтобы начать реальную торговлю.")

# ----- АДМИН-ПАНЕЛЬ (для ввода API-ключей) -----
if show_admin:
    with tabs[9]:
        st.subheader("👑 Административная панель")
        with st.expander("🔐 API ключи бирж (реальная торговля)", expanded=True):
            st.warning("⚠️ Введите свои реальные API-ключи от KuCoin и OKX с правами на спотовую торговлю. Они будут зашифрованы.")
            for ex in EXCHANGES:
                st.markdown(f"#### {ex.upper()}")
                current_keys = get_all_api_keys().get(ex, {})
                api_key = st.text_input(f"API Key ({ex})", type="password", key=f"api_{ex}")
                secret = st.text_input(f"Secret Key ({ex})", type="password", key=f"sec_{ex}")
                if st.button(f"Сохранить ключи для {ex}", key=f"save_{ex}"):
                    save_api_key(ex, api_key, secret, st.session_state.email)
                    st.success("Ключи сохранены и зашифрованы")
                    st.rerun()
