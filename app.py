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
</style>
""", unsafe_allow_html=True)

# ------------------- SUPABASE -------------------
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

EXCHANGES = ["kucoin", "okx", "hitbtc"]
TOKENS = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "LINK", "SUI", "HYPE", "TON"]
ADMIN_EMAILS = ["cb777899@gmail.com", "admin@arbitrage.com"]

def is_admin(email): return email in ADMIN_EMAILS

# ------------------- ФУНКЦИИ БД -------------------
def get_user_by_email(email):
    res = supabase.table('users').select('*').eq('email', email).execute()
    return res.data[0] if res.data else None

def create_user(email, pwd, name, country, city, phone, wallet):
    initial = {'main_balance':0, 'exchanges':{ex:{"USDT":0,"portfolio":{t:0 for t in TOKENS}} for ex in EXCHANGES},
               'total_profit':0,'trade_count':0,'withdrawable_balance':0,'total_admin_fee_paid':0}
    supabase.table('users').insert({
        'email':email,'password_hash':pwd,'full_name':name,'country':country,'city':city,
        'phone':phone,'wallet_address':wallet,'registration_status':'approved',
        'demo_balances':json.dumps(initial),'demo_history':'[]','demo_stats':'{}'
    }).execute()

def load_demo_data(user_id):
    res = supabase.table('users').select('demo_balances, demo_history, total_profit, trade_count').eq('id', user_id).execute()
    if res.data:
        u = res.data[0]
        balances = json.loads(u['demo_balances']) if isinstance(u['demo_balances'], str) else u['demo_balances']
        history = json.loads(u['demo_history']) if isinstance(u['demo_history'], str) else u['demo_history']
        return {
            'balances': balances.get('exchanges', {ex:{"USDT":0,"portfolio":{t:0 for t in TOKENS}} for ex in EXCHANGES}),
            'total_profit': u.get('total_profit',0),
            'trade_count': u.get('trade_count',0),
            'history': history
        }
    return None

def save_demo_data(user_id, data):
    to_save = {'main_balance':0,'exchanges':data['balances'],'total_profit':data['total_profit'],
               'trade_count':data['trade_count'],'withdrawable_balance':0,'total_admin_fee_paid':0}
    supabase.table('users').update({
        'demo_balances':json.dumps(to_save),
        'demo_history':json.dumps(data['history'][-500:]),
        'total_profit':data['total_profit'],
        'trade_count':data['trade_count']
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
    enc_key = base64.b64encode(api_key.encode()).decode() if api_key else ""
    enc_secret = base64.b64encode(secret.encode()).decode() if secret else ""
    supabase.table('api_keys').upsert({'exchange':exchange,'api_key':enc_key,'secret_key':enc_secret,'updated_by':admin}, on_conflict='exchange').execute()

def get_config(key):
    res = supabase.table('config').select('value').eq('key', key).execute()
    return json.loads(res.data[0]['value']) if res.data else None

def set_config(key, value):
    supabase.table('config').upsert({'key':key,'value':json.dumps(value)}).execute()

def get_available_tokens():
    return get_config('tokens') or TOKENS

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

# ------------------- БИРЖИ -------------------
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
        api_key = base64.b64decode(key_data.get('api_key','')).decode() if key_data.get('api_key') else None
        secret = base64.b64decode(key_data.get('secret_key','')).decode() if key_data.get('secret_key') else None
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

# ------------------- ДЕМО-ФУНКЦИИ -------------------
def update_demo_balance(user_id, exchange, asset, delta, data):
    if exchange not in data['balances']:
        data['balances'][exchange] = {'USDT':0.0, 'portfolio':{t:0.0 for t in TOKENS}}
    if asset == 'USDT':
        data['balances'][exchange]['USDT'] += delta
    else:
        if asset not in data['balances'][exchange]['portfolio']:
            data['balances'][exchange]['portfolio'][asset] = 0.0
        data['balances'][exchange]['portfolio'][asset] += delta
    save_demo_data(user_id, data)

def demo_buy(user_id, exchange, token, usdt_amount, data, clients):
    price = get_price(clients[exchange], token)
    if not price:
        return False, "Цена не получена"
    amount_token = usdt_amount / price
    if data['balances'][exchange]['USDT'] < usdt_amount:
        return False, f"Не хватает USDT (есть {data['balances'][exchange]['USDT']:.2f})"
    update_demo_balance(user_id, exchange, 'USDT', -usdt_amount, data)
    update_demo_balance(user_id, exchange, token, amount_token, data)
    return True, f"Куплено {amount_token:.8f} {token} за {usdt_amount} USDT"

def demo_sell(user_id, exchange, token, amount_token, data, clients):
    price = get_price(clients[exchange], token)
    if not price:
        return False, "Цена не получена"
    available = data['balances'][exchange]['portfolio'].get(token, 0)
    if available < amount_token:
        return False, f"Не хватает {token} (есть {available:.8f}, нужно {amount_token:.8f})"
    usdt_received = amount_token * price
    update_demo_balance(user_id, exchange, token, -amount_token, data)
    update_demo_balance(user_id, exchange, 'USDT', usdt_received, data)
    return True, f"Продано {amount_token:.8f} {token} за {usdt_received:.2f} USDT"

def reset_demo_data(user_id):
    init_bal = {ex:{"USDT":0,"portfolio":{t:0 for t in TOKENS}} for ex in EXCHANGES}
    st.session_state.demo_data = {'balances':init_bal,'total_profit':0,'trade_count':0,'history':[]}
    save_demo_data(user_id, st.session_state.demo_data)

# ------------------- РЕАЛЬНЫЕ ФУНКЦИИ -------------------
def get_real_balance(exchange, asset):
    if not exchange: return 0.0
    try:
        bal = exchange.fetch_balance()
        return bal.get(asset, {}).get('free', 0.0) if asset == 'USDT' else bal.get(asset, {}).get('free', 0.0)
    except:
        return 0.0

def real_buy(exchange, token, usdt_amount):
    if not exchange: return False, "Биржа не подключена"
    try:
        price = get_price(exchange, token)
        amount = usdt_amount / price
        exchange.create_market_buy_order(f"{token}/USDT", amount)
        return True, f"Куплено {amount:.8f} {token} за {usdt_amount} USDT"
    except Exception as e:
        return False, str(e)

def real_sell(exchange, token, amount_token):
    if not exchange: return False, "Биржа не подключена"
    try:
        exchange.create_market_sell_order(f"{token}/USDT", amount_token)
        price = get_price(exchange, token)
        usdt_received = amount_token * price
        return True, f"Продано {amount_token:.8f} {token} за {usdt_received:.2f} USDT"
    except Exception as e:
        return False, str(e)

# ------------------- АРБИТРАЖ -------------------
def find_opportunity(mode, fee, min_profit, min_trade, max_trade, demo_data, real_exchanges, public_clients):
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
                if mode == "Реальный":
                    if not real_exchanges.get(buy_ex) or not real_exchanges.get(sell_ex): continue
                    usdt = get_real_balance(real_exchanges[buy_ex], 'USDT')
                    token_amt = get_real_balance(real_exchanges[sell_ex], token)
                else:
                    usdt = demo_data['balances'].get(buy_ex, {}).get('USDT', 0)
                    token_amt = demo_data['balances'].get(sell_ex, {}).get('portfolio', {}).get(token, 0)
                max_by_usdt = usdt
                max_by_token = token_amt * sell_p
                max_possible = min(max_by_usdt, max_by_token)
                if max_possible < min_trade: continue
                trade_usdt = min(max_possible, max_trade)
                if trade_usdt < min_trade: continue
                amount = trade_usdt / buy_p
                # Добавляем запас 2% для токенов на продаже
                required_token = amount * 1.02
                if required_token > token_amt:
                    continue
                profit_before = (sell_p - buy_p) * amount
                profit = profit_before * (1 - fee/100)
                if profit < min_profit: continue
                opportunities.append({
                    'token':token, 'buy_ex':buy_ex, 'sell_ex':sell_ex,
                    'buy_price':buy_p, 'sell_price':sell_p,
                    'trade_usdt':trade_usdt, 'amount':amount, 'profit':profit
                })
    if not opportunities: return None
    return max(opportunities, key=lambda x: x['profit'])

def execute_arbitrage(mode, opp, user_id, demo_data, real_exchanges, public_clients):
    buy_ex = opp['buy_ex']; sell_ex = opp['sell_ex']; token = opp['token']
    amount = opp['amount']; trade_usdt = opp['trade_usdt']; sell_price = opp['sell_price']
    if mode == "Реальный":
        ok_buy, msg_buy = real_buy(real_exchanges[buy_ex], token, trade_usdt)
        if not ok_buy: return None, msg_buy
        # Перед продажей повторно проверяем баланс
        token_available = get_real_balance(real_exchanges[sell_ex], token)
        if token_available < amount:
            return None, f"После покупки не хватает {token} на {sell_ex}: нужно {amount:.8f}, доступно {token_available:.8f}"
        ok_sell, msg_sell = real_sell(real_exchanges[sell_ex], token, amount)
        if not ok_sell: return None, msg_sell
        real_profit = amount * sell_price - trade_usdt
        if 'real_profit' not in st.session_state: st.session_state.real_profit = 0
        if 'real_trades' not in st.session_state: st.session_state.real_trades = 0
        st.session_state.real_profit += real_profit
        st.session_state.real_trades += 1
        if 'real_history' not in st.session_state: st.session_state.real_history = []
        st.session_state.real_history.append(f"✅ {datetime.now()} | {token} | {buy_ex}→{sell_ex} | {amount:.8f} | +{real_profit:.2f} USDT")
        add_trade(user_id, mode, token, amount, real_profit, buy_ex, sell_ex)
        return real_profit, None
    else:
        ok_buy, msg_buy = demo_buy(user_id, buy_ex, token, trade_usdt, demo_data, public_clients)
        if not ok_buy: return None, msg_buy
        # Повторная проверка баланса перед продажей
        token_available = demo_data['balances'].get(sell_ex, {}).get('portfolio', {}).get(token, 0)
        if token_available < amount:
            return None, f"После покупки не хватает {token} на {sell_ex}: нужно {amount:.8f}, доступно {token_available:.8f}"
        ok_sell, msg_sell = demo_sell(user_id, sell_ex, token, amount, demo_data, public_clients)
        if not ok_sell: return None, msg_sell
        real_profit = amount * sell_price - trade_usdt
        demo_data['total_profit'] += real_profit
        demo_data['trade_count'] += 1
        entry = f"✅ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | {token} | {buy_ex}→{sell_ex} | {amount:.8f} | +{real_profit:.2f} USDT"
        demo_data['history'].append(entry)
        save_demo_data(user_id, demo_data)
        add_trade(user_id, mode, token, amount, real_profit, buy_ex, sell_ex)
        return real_profit, None

# ------------------- СЕССИЯ -------------------
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_id = None
    st.session_state.email = None
    st.session_state.username = None
    st.session_state.wallet = ''
    st.session_state.demo_data = None
    st.session_state.real_profit = 0
    st.session_state.real_trades = 0
    st.session_state.real_history = []
    st.session_state.trade_mode = "Демо"
    st.session_state.auto_log = []
    st.session_state.fee = 0.1
    st.session_state.min_profit = 0.1   # увеличена минимальная прибыль
    st.session_state.min_trade = 12.0
    st.session_state.max_trade = 15.0
    st.session_state.auto_trade_enabled = False
    st.session_state.scan_interval = 15
    st.session_state.last_scan_time = None
    st.session_state.chat_unread = 0

public_clients = init_public_clients()
real_exchanges = init_real_exchanges()

# ------------------- АВТО-ОБНОВЛЕНИЕ И СКАНИРОВАНИЕ -------------------
if st.session_state.get('auto_trade_enabled', False) and st.session_state.get('logged_in', False):
    interval = st.session_state.get('scan_interval', 15)
    st_autorefresh(interval=interval * 1000, key="auto_refresh")
    
    now = datetime.now()
    last = st.session_state.get('last_scan_time')
    if last is None or (now - last).total_seconds() >= interval:
        st.session_state.last_scan_time = now
        opp = find_opportunity(st.session_state.trade_mode, st.session_state.fee, st.session_state.min_profit,
                               st.session_state.min_trade, st.session_state.max_trade,
                               st.session_state.demo_data, real_exchanges, public_clients)
        if opp:
            st.session_state.auto_log.append(f"🔍 Найдено: {opp['token']} {opp['buy_ex']}→{opp['sell_ex']} | прибыль {opp['profit']:.4f} USDT")
            profit, err = execute_arbitrage(st.session_state.trade_mode, opp, st.session_state.user_id,
                                            st.session_state.demo_data, real_exchanges, public_clients)
            if profit:
                st.session_state.auto_log.append(f"✅ Сделка исполнена! +{profit:.2f} USDT")
            else:
                st.session_state.auto_log.append(f"❌ Ошибка: {err}")
        else:
            pass

# ------------------- ЛОГИН -------------------
if not st.session_state.logged_in:
    st.markdown('<div class="main-header"><h1>Арбитражный бот <span class="hovmel-highlight">HOVMEL</span></h1></div><div class="subtitle">⚡ Автоматический поиск межбиржевого арбитража 24/7 ⚡</div>', unsafe_allow_html=True)
    tab1, tab2 = st.tabs(["Вход", "Регистрация"])
    with tab1:
        email = st.text_input("Email")
        pwd = st.text_input("Пароль", type="password")
        if st.button("Войти"):
            user = get_user_by_email(email)
            if user and user['password_hash'] == pwd and user['registration_status'] == 'approved':
                st.session_state.logged_in = True
                st.session_state.user_id = user['id']
                st.session_state.email = user['email']
                st.session_state.username = user['full_name']
                st.session_state.wallet = user.get('wallet_address', '')
                st.session_state.demo_data = load_demo_data(user['id'])
                if not st.session_state.demo_data:
                    init_bal = {ex:{"USDT":0,"portfolio":{t:0 for t in TOKENS}} for ex in EXCHANGES}
                    st.session_state.demo_data = {'balances':init_bal,'total_profit':0,'trade_count':0,'history':[]}
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

# Кнопки СТАРТ и СТОП
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

# ------------------- РАСЧЁТ КАПИТАЛА -------------------
if st.session_state.trade_mode == "Реальный":
    total_usdt = sum(get_real_balance(real_exchanges.get(ex), 'USDT') for ex in EXCHANGES)
    total_portfolio = 0
    for ex in EXCHANGES:
        if real_exchanges.get(ex):
            for token in get_available_tokens():
                amt = get_real_balance(real_exchanges[ex], token)
                if amt > 0:
                    price = get_price(public_clients[ex], token)
                    if price: total_portfolio += amt * price
    total_capital = total_usdt + total_portfolio
else:
    balances = st.session_state.demo_data['balances']
    total_usdt = sum(balances.get(ex, {}).get('USDT',0) for ex in EXCHANGES)
    total_portfolio = 0
    for ex in EXCHANGES:
        for token, amt in balances.get(ex, {}).get('portfolio',{}).items():
            if amt>0 and public_clients[ex]:
                price = get_price(public_clients[ex], token)
                if price: total_portfolio += amt * price
    total_capital = total_usdt + total_portfolio

col_a, col_b, col_c, col_d = st.columns(4)
col_a.metric("💰 USDT на биржах", f"{total_usdt:.2f}")
col_b.metric("📦 Портфель (токены)", f"{total_portfolio:.2f}")
col_c.metric("💎 Общий капитал", f"{total_capital:.2f}")
trade_count = st.session_state.real_trades if st.session_state.trade_mode == "Реальный" else st.session_state.demo_data['trade_count']
col_d.metric("📊 Сделок", trade_count)

# ------------------- НАСТРОЙКИ -------------------
with st.expander("⚙️ Настройки арбитража"):
    st.session_state.fee = st.number_input("Комиссия (%)", 0.0, 0.5, st.session_state.fee, 0.01, format="%.2f")
    st.session_state.min_profit = st.number_input("Мин. прибыль (USDT)", 0.001, 1.0, st.session_state.min_profit, 0.01, format="%.3f")
    st.session_state.min_trade = st.number_input("Мин. сумма сделки (USDT)", 10.0, 15.0, st.session_state.min_trade, 1.0)
    st.session_state.max_trade = st.number_input("Макс. сумма сделки (USDT)", 12.0, 15.0, st.session_state.max_trade, 1.0)
    interval = st.number_input("Интервал сканирования (сек)", 5, 60, st.session_state.scan_interval, 5)
    if interval != st.session_state.scan_interval:
        st.session_state.scan_interval = interval
        st.rerun()
    st.info("💡 Сумма сделки ограничена 12-15 USDT в зависимости от доступных средств.")

# Лог авто-торговли
with st.expander("📋 Лог авто-торговли", expanded=True):
    if st.session_state.auto_log:
        for log in st.session_state.auto_log[-30:]:
            st.text(log)
    else:
        st.info("Нет событий. Запустите авто-торговлю кнопкой СТАРТ.")

# ------------------- ВКЛАДКИ -------------------
show_admin = is_admin(st.session_state.email)
tabs_list = ["📊 Dashboard", "📈 Графики", "🔄 Арбитраж", "📊 Статистика", "💼 Балансы", "💰 Вывод", "📜 История", "👤 Кабинет", "💬 Чат"]
if show_admin:
    tabs_list.append("👑 Админ-панель")
tabs = st.tabs(tabs_list)

# ---------- DASHBOARD ----------
with tabs[0]:
    st.subheader("📊 Dashboard")
    st.write("Добро пожаловать в арбитражного бота **HOVMEL**.")
    st.write("Используйте кнопки **СТАРТ** и **СТОП** для управления авто-торговлей.")
    st.write("Для ручного арбитража перейдите во вкладку **Арбитраж**.")
    st.write("Для ручной покупки/продажи токенов — вкладка **Балансы**.")

# ---------- ГРАФИКИ ----------
with tabs[1]:
    st.subheader("📈 Графики цен")
    tok = st.selectbox("Выберите токен", get_available_tokens())
    if tok:
        data = []
        for ex in EXCHANGES:
            if public_clients[ex]:
                p = get_price(public_clients[ex], tok)
                if p:
                    data.append({"Биржа": ex.upper(), "Цена": p})
        if data:
            df = pd.DataFrame(data)
            fig = px.bar(df, x="Биржа", y="Цена", title=f"{tok}/USDT", color="Биржа")
            st.plotly_chart(fig, use_container_width=True)

# ---------- АРБИТРАЖ (ручной) ----------
with tabs[2]:
    st.subheader("🔄 Ручной поиск арбитража")
    if st.button("🔍 Найти лучшую возможность"):
        opp = find_opportunity(st.session_state.trade_mode, st.session_state.fee, st.session_state.min_profit,
                               st.session_state.min_trade, st.session_state.max_trade,
                               st.session_state.demo_data, real_exchanges, public_clients)
        if opp:
            st.success(f"Найдена возможность: {opp['token']}")
            st.write(f"**Покупка:** {opp['buy_ex'].upper()} по {opp['buy_price']:.2f} USDT")
            st.write(f"**Продажа:** {opp['sell_ex'].upper()} по {opp['sell_price']:.2f} USDT")
            st.write(f"**Сумма сделки:** {opp['trade_usdt']:.2f} USDT")
            st.write(f"**Прибыль:** {opp['profit']:.4f} USDT")
            if st.button("✅ Выполнить сделку"):
                profit, err = execute_arbitrage(st.session_state.trade_mode, opp, st.session_state.user_id,
                                                st.session_state.demo_data, real_exchanges, public_clients)
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
    profit = st.session_state.real_profit if st.session_state.trade_mode == "Реальный" else st.session_state.demo_data['total_profit']
    trades = st.session_state.real_trades if st.session_state.trade_mode == "Реальный" else st.session_state.demo_data['trade_count']
    col1, col2 = st.columns(2)
    col1.metric("📈 Общая прибыль", f"{profit:.2f} USDT")
    col2.metric("🔄 Количество сделок", trades)
    if trades > 0:
        st.metric("📊 Средняя прибыль на сделку", f"{profit/trades:.2f} USDT")
    all_trades = get_all_trades(100)
    if all_trades:
        df_trades = pd.DataFrame(all_trades)
        df_trades['trade_time'] = pd.to_datetime(df_trades['trade_time'])
        df_trades = df_trades.sort_values('trade_time')
        df_trades['cumulative_profit'] = df_trades['profit'].cumsum()
        fig = px.line(df_trades, x='trade_time', y='cumulative_profit', title="Накопленная прибыль (все сделки)")
        st.plotly_chart(fig, use_container_width=True)

# ---------- БАЛАНСЫ ----------
with tabs[4]:
    st.subheader("💼 Балансы и ручная торговля")
    
    if st.session_state.trade_mode == "Демо":
        st.markdown("### 💰 Пополнение демо-балансов")
        col1, col2, col3 = st.columns(3)
        with col1:
            demo_exchange = st.selectbox("Биржа", EXCHANGES, key="demo_ex")
        with col2:
            asset_type = st.selectbox("Актив", ["USDT"] + get_available_tokens(), key="demo_asset")
        with col3:
            amount_add = st.number_input("Количество", min_value=0.0, step=10.0, key="demo_amount")
        if st.button("➕ Добавить на демо-счёт"):
            if amount_add > 0:
                update_demo_balance(st.session_state.user_id, demo_exchange, asset_type, amount_add, st.session_state.demo_data)
                st.success(f"Добавлено {amount_add} {asset_type} на {demo_exchange.upper()}")
                st.rerun()
        st.markdown("---")
        st.markdown("### ⚠️ Сброс демо-данных")
        if st.button("🧹 ПОЛНЫЙ СБРОС (балансы, прибыль, история)", use_container_width=True):
            reset_demo_data(st.session_state.user_id)
            st.success("Демо-данные сброшены!")
            st.rerun()
        st.warning("Это действие удалит все ваши демо-балансы, историю и статистику. Необратимо!")
        st.markdown("---")
    
    if st.session_state.trade_mode == "Реальный":
        if real_exchanges and any(real_exchanges.values()):
            balances = {}
            for ex in EXCHANGES:
                if real_exchanges.get(ex):
                    usdt = get_real_balance(real_exchanges[ex], 'USDT')
                    port = {t: get_real_balance(real_exchanges[ex], t) for t in get_available_tokens()}
                    balances[ex] = {'USDT': usdt, 'portfolio': port}
                else:
                    balances[ex] = {'USDT': 0, 'portfolio': {t: 0 for t in TOKENS}}
        else:
            balances = {ex: {'USDT': 0, 'portfolio': {t: 0 for t in TOKENS}} for ex in EXCHANGES}
            st.warning("Реальные биржи не подключены. Добавьте API-ключи в админ-панели.")
    else:
        balances = st.session_state.demo_data['balances']
    
    for ex in EXCHANGES:
        with st.expander(f"{ex.upper()}"):
            st.write(f"**USDT:** {balances[ex]['USDT']:.2f}")
            port = balances[ex]['portfolio']
            for token, amt in port.items():
                if amt > 0:
                    price = get_price(public_clients[ex], token) if public_clients[ex] else None
                    val = amt * price if price else 0
                    st.write(f"{token}: {amt:.8f} ≈ {val:.2f} USDT")
            st.markdown("---")
            colA, colB = st.columns(2)
            with colA:
                token_buy = st.selectbox("Купить", get_available_tokens(), key=f"buy_{ex}")
                usdt_amt = st.number_input("USDT", min_value=1.0, step=10.0, key=f"usdt_{ex}")
                if st.button(f"Купить {token_buy}", key=f"btn_buy_{ex}"):
                    if st.session_state.trade_mode == "Реальный":
                        ok, msg = real_buy(real_exchanges[ex], token_buy, usdt_amt)
                    else:
                        ok, msg = demo_buy(st.session_state.user_id, ex, token_buy, usdt_amt, st.session_state.demo_data, public_clients)
                    if ok:
                        if st.session_state.trade_mode == "Демо":
                            st.session_state.demo_data['trade_count'] += 1
                            entry = f"🟢 {datetime.now()} | Ручная покупка {token_buy} на {ex.upper()} на {usdt_amt} USDT"
                            st.session_state.demo_data['history'].append(entry)
                            save_demo_data(st.session_state.user_id, st.session_state.demo_data)
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
            with colB:
                token_sell = st.selectbox("Продать", get_available_tokens(), key=f"sell_{ex}")
                token_amt = st.number_input("Количество", min_value=0.000001, step=0.001, format="%.6f", key=f"amt_{ex}")
                if st.button(f"Продать {token_sell}", key=f"btn_sell_{ex}"):
                    if st.session_state.trade_mode == "Реальный":
                        ok, msg = real_sell(real_exchanges[ex], token_sell, token_amt)
                    else:
                        ok, msg = demo_sell(st.session_state.user_id, ex, token_sell, token_amt, st.session_state.demo_data, public_clients)
                    if ok:
                        if st.session_state.trade_mode == "Демо":
                            st.session_state.demo_data['trade_count'] += 1
                            entry = f"🔴 {datetime.now()} | Ручная продажа {token_sell} на {ex.upper()} {token_amt} шт"
                            st.session_state.demo_data['history'].append(entry)
                            save_demo_data(st.session_state.user_id, st.session_state.demo_data)
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)

# ---------- ВЫВОД ----------
with tabs[5]:
    st.subheader("💰 Вывод средств")
    st.info("Вывод возможен только после одобрения администратором (комиссия 22%).")
    withdrawable = st.session_state.demo_data.get('withdrawable_balance', 0.0) if st.session_state.trade_mode == "Демо" else 0.0
    st.write(f"Доступно для вывода: **{withdrawable:.2f} USDT**")
    amount = st.number_input("Сумма вывода (USDT)", min_value=1.0, max_value=max(1.0, withdrawable), step=10.0)
    wallet = st.text_input("Адрес USDT (TRC20)", value=st.session_state.wallet)
    if st.button("Запросить вывод"):
        if amount > 0 and wallet and withdrawable >= amount:
            create_withdrawal_request(st.session_state.user_id, amount, wallet)
            st.success("Заявка на вывод отправлена администратору!")
        else:
            st.error("Введите корректную сумму и адрес")

# ---------- ИСТОРИЯ ----------
with tabs[6]:
    st.subheader("📜 История сделок")
    if st.session_state.trade_mode == "Реальный":
        hist = st.session_state.real_history[-50:]
    else:
        hist = st.session_state.demo_data['history'][-50:]
    if hist:
        for h in reversed(hist):
            st.text(h)
    else:
        st.info("Сделок пока нет")

# ---------- КАБИНЕТ ----------
with tabs[7]:
    st.subheader("👤 Личный кабинет")
    col1, col2 = st.columns(2)
    with col1:
        st.write(f"**Имя:** {st.session_state.username}")
        st.write(f"**Email:** {st.session_state.email}")
        st.write(f"**Кошелёк:** {st.session_state.wallet}")
    with col2:
        trades = st.session_state.real_trades if st.session_state.trade_mode == "Реальный" else st.session_state.demo_data['trade_count']
        profit = st.session_state.real_profit if st.session_state.trade_mode == "Реальный" else st.session_state.demo_data['total_profit']
        st.write(f"**Всего сделок:** {trades}")
        st.write(f"**Общая прибыль:** {profit:.2f} USDT")
        st.write(f"**Общий капитал:** {total_capital:.2f} USDT")

# ---------- ЧАТ ----------
with tabs[8]:
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
    with tabs[9]:
        st.subheader("👑 Административная панель")
        admin_tabs = st.tabs(["Пользователи", "API ключи", "Выводы", "Конфиг", "Сообщения"])
        
        with admin_tabs[0]:
            st.markdown("#### Управление пользователями")
            users = get_all_users_for_admin()
            for user in users:
                with st.expander(f"{user['email']} - {user['full_name']}"):
                    st.write(f"Статус: {user['registration_status']}")
                    st.write(f"Сделок: {user.get('trade_count', 0)}")
                    new_status = st.selectbox("Изменить статус", ["approved", "blocked"], key=f"status_{user['id']}")
                    if st.button("Обновить", key=f"update_{user['id']}"):
                        update_user_status(user['id'], new_status)
                        st.rerun()
        
        with admin_tabs[1]:
            st.markdown("#### API ключи бирж (для реального режима)")
            for ex in EXCHANGES:
                with st.expander(f"{ex.upper()}"):
                    api_key = st.text_input(f"API Key ({ex})", type="password", key=f"api_{ex}")
                    secret = st.text_input(f"Secret Key ({ex})", type="password", key=f"sec_{ex}")
                    if st.button(f"Сохранить {ex}", key=f"save_{ex}"):
                        save_api_key(ex, api_key, secret, st.session_state.email)
                        st.success(f"Ключи для {ex} сохранены")
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
            all_messages = get_messages(limit=100)
            for msg in all_messages:
                if not msg['is_admin_reply']:
                    st.markdown(f"**{msg['user_name']}** ({msg['user_email']}): {msg['message']}  \n*{msg['created_at'][:16]}*")
                    reply = st.text_area("Ответ", key=f"reply_{msg['id']}")
                    if st.button("Отправить ответ", key=f"send_{msg['id']}"):
                        add_message(msg['user_id'], msg['user_email'], "Admin", reply, True)
                        st.rerun()
                    st.divider()
