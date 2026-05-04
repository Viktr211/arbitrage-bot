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

# Кастомный CSS
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
.status-running { color: #00FF88; }
.status-stopped { color: #FF4444; }
</style>
""", unsafe_allow_html=True)

# ---------- SUPABASE ----------
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

EXCHANGES = ["kucoin", "okx", "hitbtc"]
TOKENS = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "LINK", "SUI", "HYPE", "TON"]
ADMIN_EMAILS = ["cb777899@gmail.com"]

def is_admin(email): return email in ADMIN_EMAILS

# ---------- ФУНКЦИИ БАЗЫ ДАННЫХ ----------
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

# ---------- ПОДКЛЮЧЕНИЕ К БИРЖАМ ----------
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

# ---------- ДЕМО-ФУНКЦИИ ----------
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
    if data['balances'][exchange]['portfolio'].get(token,0) < amount_token:
        return False, f"Не хватает {token} (есть {data['balances'][exchange]['portfolio'].get(token,0):.8f})"
    usdt_received = amount_token * price
    update_demo_balance(user_id, exchange, token, -amount_token, data)
    update_demo_balance(user_id, exchange, 'USDT', usdt_received, data)
    return True, f"Продано {amount_token:.8f} {token} за {usdt_received:.2f} USDT"

# ---------- РЕАЛЬНЫЕ ФУНКЦИИ ----------
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

# ---------- АРБИТРАЖ ----------
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
        ok_sell, msg_sell = real_sell(real_exchanges[sell_ex], token, amount)
        if not ok_sell: return None, msg_sell
        real_profit = amount * sell_price - trade_usdt
        # Для реального режима статистика хранится в st.session_state
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

# ---------- СЕССИЯ ПОЛЬЗОВАТЕЛЯ ----------
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
    st.session_state.min_profit = 0.01
    st.session_state.min_trade = 12.0
    st.session_state.max_trade = 15.0
    st.session_state.auto_scan_enabled = True   # автоматическое сканирование при каждой перезагрузке
    st.session_state.last_scan_time = None

public_clients = init_public_clients()
real_exchanges = init_real_exchanges()

# ---------- АВТОМАТИЧЕСКАЯ ПЕРЕЗАГРУЗКА И СКАНИРОВАНИЕ ----------
# Устанавливаем автообновление страницы каждые N секунд (например, 15 секунд)
# Значение берём из настроек или стандартное 15
refresh_interval = st.session_state.get('scan_interval', 15)
st_autorefresh(interval=refresh_interval * 1000, key="auto_refresh")

# При каждом запуске страницы (в том числе после автообновления) выполняем сканирование, если авто-сканирование включено
if st.session_state.get('auto_scan_enabled', True) and st.session_state.get('logged_in', False):
    # Чтобы не сканировать слишком часто при ручных нажатиях, используем флаг времени
    now = datetime.now()
    last = st.session_state.get('last_scan_time')
    if last is None or (now - last).total_seconds() >= refresh_interval:
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
            st.session_state.auto_log.append("❌ Возможностей не найдено")

# ---------- ЛОГИН ----------
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

# ---------- ОСНОВНОЙ ИНТЕРФЕЙС ----------
st.markdown('<div class="main-header"><h1>Арбитражный бот <span class="hovmel-highlight">HOVMEL</span></h1></div><div class="subtitle">⚡ Автоматический поиск межбиржевого арбитража 24/7 ⚡</div>', unsafe_allow_html=True)

col1, col2, col3 = st.columns([2,1,1])
with col1:
    st.markdown(f"👤 {st.session_state.username} | {st.session_state.email}")
with col2:
    if st.session_state.trade_mode == "Демо":
        st.markdown('<span class="status-running">🟢 Демо режим</span>', unsafe_allow_html=True)
    else:
        st.markdown('<span class="status-stopped">🔴 Реальный режим</span>', unsafe_allow_html=True)
with col3:
    if st.button("🚪 Выйти"):
        st.session_state.logged_in = False
        st.rerun()

# Показываем подключённые биржи
connected = [ex.upper() for ex, cl in public_clients.items() if cl is not None]
st.success(f"🔌 Биржи для мониторинга: {', '.join(connected)}")

# Переключение режима
new_mode = st.radio("Режим", ["Демо", "Реальный"], horizontal=True, index=0 if st.session_state.trade_mode=="Демо" else 1)
if new_mode != st.session_state.trade_mode:
    st.session_state.trade_mode = new_mode
    st.rerun()

# ---------- РАСЧЁТ КАПИТАЛА ----------
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
    st.info(f"💰 **Реальные балансы** | USDT: {total_usdt:.2f} | Портфель: {total_portfolio:.2f} | Капитал: {total_capital:.2f}")
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
    st.info(f"🎮 **Демо-балансы** | USDT: {total_usdt:.2f} | Портфель: {total_portfolio:.2f} | Капитал: {total_capital:.2f}")

col_a, col_b, col_c, col_d = st.columns(4)
col_a.metric("USDT на биржах", f"{total_usdt:.2f}")
col_b.metric("Портфель (токены)", f"{total_portfolio:.2f}")
col_c.metric("Общий капитал", f"{total_capital:.2f}")
if st.session_state.trade_mode == "Реальный":
    trade_count = st.session_state.real_trades
else:
    trade_count = st.session_state.demo_data['trade_count']
col_d.metric("Сделок", trade_count)

# ---------- ДЕМО-УПРАВЛЕНИЕ ----------
if st.session_state.trade_mode == "Демо":
    with st.expander("💰 Пополнение демо-балансов"):
        ex_choice = st.selectbox("Биржа", EXCHANGES)
        asset_choice = st.selectbox("Актив", ["USDT"] + get_available_tokens())
        amount_add = st.number_input("Количество", min_value=0.0, step=10.0)
        if st.button("➕ Добавить"):
            if amount_add > 0:
                update_demo_balance(st.session_state.user_id, ex_choice, asset_choice, amount_add, st.session_state.demo_data)
                st.rerun()
    with st.expander("⚠️ Сброс демо-данных"):
        if st.button("🧹 Полный сброс (балансы, прибыль, история)"):
            init_bal = {ex:{"USDT":0,"portfolio":{t:0 for t in TOKENS}} for ex in EXCHANGES}
            st.session_state.demo_data = {'balances':init_bal,'total_profit':0,'trade_count':0,'history':[]}
            save_demo_data(st.session_state.user_id, st.session_state.demo_data)
            st.success("Сброшено!")
            st.rerun()

# ---------- НАСТРОЙКИ АРБИТРАЖА ----------
with st.expander("⚙️ Настройки арбитража"):
    st.session_state.fee = st.number_input("Комиссия (%)", 0.0, 0.5, st.session_state.fee, 0.01, format="%.2f")
    st.session_state.min_profit = st.number_input("Мин. прибыль (USDT)", 0.001, 1.0, st.session_state.min_profit, 0.01, format="%.3f")
    st.session_state.min_trade = st.number_input("Мин. сумма сделки (USDT)", 10.0, 15.0, st.session_state.min_trade, 1.0)
    st.session_state.max_trade = st.number_input("Макс. сумма сделки (USDT)", 12.0, 15.0, st.session_state.max_trade, 1.0)
    interval = st.number_input("Интервал сканирования (сек)", 5, 60, st.session_state.get('scan_interval', 15), 5)
    if interval != st.session_state.get('scan_interval', 15):
        st.session_state.scan_interval = interval
        st.rerun()
    auto_scan = st.checkbox("Автоматическое сканирование (24/7)", value=st.session_state.get('auto_scan_enabled', True))
    if auto_scan != st.session_state.get('auto_scan_enabled', True):
        st.session_state.auto_scan_enabled = auto_scan
        st.rerun()
    st.info("При автоматическом сканировании страница будет обновляться каждые N секунд, и бот будет искать арбитраж.")

# ---------- ЛОГ АВТО-ТОРГОВЛИ ----------
with st.expander("📋 Лог авто-торговли", expanded=True):
    for log in st.session_state.auto_log[-30:]:
        st.text(log)

# ---------- ВКЛАДКИ ----------
tabs = st.tabs(["📊 Dashboard", "📈 Графики", "🔄 Арбитраж", "📊 Статистика", "💼 Балансы", "📜 История", "👤 Кабинет"])

# Dashboard
with tabs[0]:
    st.subheader("Добро пожаловать!")
    st.write("Бот работает **автоматически 24/7** – каждые N секунд сканирует рынок и исполняет арбитражные сделки.")
    st.write("Вы можете настроить интервал сканирования и другие параметры в разделе 'Настройки арбитража'.")

# Графики
with tabs[1]:
    tok = st.selectbox("Токен", get_available_tokens())
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

# Ручной арбитраж (на случай, если нужно вручную)
with tabs[2]:
    st.subheader("Ручной поиск и исполнение")
    if st.button("🔍 Найти лучшую возможность (ручной режим)"):
        opp = find_opportunity(st.session_state.trade_mode, st.session_state.fee, st.session_state.min_profit,
                               st.session_state.min_trade, st.session_state.max_trade,
                               st.session_state.demo_data, real_exchanges, public_clients)
        if opp:
            st.success(f"Найдена {opp['token']}")
            st.write(f"Покупка: {opp['buy_ex'].upper()} по {opp['buy_price']:.2f}")
            st.write(f"Продажа: {opp['sell_ex'].upper()} по {opp['sell_price']:.2f}")
            st.write(f"Сумма: {opp['trade_usdt']:.2f} USDT, прибыль: {opp['profit']:.4f} USDT")
            if st.button("✅ Выполнить сделку"):
                profit, err = execute_arbitrage(st.session_state.trade_mode, opp, st.session_state.user_id,
                                                st.session_state.demo_data, real_exchanges, public_clients)
                if profit:
                    st.success(f"Прибыль: {profit:.2f} USDT")
                    st.rerun()
                else:
                    st.error(err)
        else:
            st.warning("Нет возможностей")

# Статистика
with tabs[3]:
    st.subheader("Статистика")
    if st.session_state.trade_mode == "Реальный":
        profit = st.session_state.real_profit
        trades = st.session_state.real_trades
    else:
        profit = st.session_state.demo_data['total_profit']
        trades = st.session_state.demo_data['trade_count']
    col1, col2 = st.columns(2)
    col1.metric("Общая прибыль", f"{profit:.2f} USDT")
    col2.metric("Количество сделок", trades)
    if trades > 0:
        st.metric("Средняя прибыль", f"{profit/trades:.2f} USDT")

# Балансы + ручная торговля
with tabs[4]:
    st.subheader("Балансы и ручные операции")
    if st.session_state.trade_mode == "Реальный":
        balances = {}
        for ex in EXCHANGES:
            if real_exchanges.get(ex):
                usdt = get_real_balance(real_exchanges[ex], 'USDT')
                port = {t: get_real_balance(real_exchanges[ex], t) for t in get_available_tokens()}
                balances[ex] = {'USDT':usdt, 'portfolio':port}
            else:
                balances[ex] = {'USDT':0, 'portfolio':{t:0 for t in TOKENS}}
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
                        # Увеличиваем счётчик сделок при ручной продаже
                        if st.session_state.trade_mode != "Реальный":
                            st.session_state.demo_data['trade_count'] += 1
                            entry = f"🟠 {datetime.now()} | Продажа {token_sell} на {ex.upper()} {token_amt} шт"
                            st.session_state.demo_data['history'].append(entry)
                            save_demo_data(st.session_state.user_id, st.session_state.demo_data)
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)

# История
with tabs[5]:
    st.subheader("История сделок")
    if st.session_state.trade_mode == "Реальный":
        hist = st.session_state.real_history[-50:]
    else:
        hist = st.session_state.demo_data['history'][-50:]
    for h in reversed(hist):
        st.text(h)

# Кабинет
with tabs[6]:
    st.subheader("Личный кабинет")
    st.write(f"**Имя:** {st.session_state.username}")
    st.write(f"**Email:** {st.session_state.email}")
    st.write(f"**Кошелёк:** {st.session_state.wallet}")
    if st.session_state.trade_mode == "Реальный":
        st.write(f"**Сделок:** {st.session_state.real_trades}")
        st.write(f"**Прибыль:** {st.session_state.real_profit:.2f} USDT")
    else:
        st.write(f"**Сделок:** {st.session_state.demo_data['trade_count']}")
        st.write(f"**Прибыль:** {st.session_state.demo_data['total_profit']:.2f} USDT")
    st.write(f"**Общий капитал:** {total_capital:.2f} USDT")

# ---------- АДМИН-ПАНЕЛЬ (только для администратора) ----------
if is_admin(st.session_state.email):
    with st.sidebar:
        st.header("👑 Админ-панель")
        with st.expander("API ключи"):
            for ex in EXCHANGES:
                api = st.text_input(f"{ex.upper()} API Key", type="password", key=f"api_{ex}")
                sec = st.text_input(f"{ex.upper()} Secret", type="password", key=f"sec_{ex}")
                if st.button(f"Сохранить {ex}", key=f"save_{ex}"):
                    save_api_key(ex, api, sec, st.session_state.email)
                    st.success("Сохранено")
                    st.rerun()
        with st.expander("Токены"):
            curr = ", ".join(get_available_tokens())
            new_tokens = st.text_area("Список токенов (через запятую)", curr)
            if st.button("Обновить"):
                tokens_list = [t.strip().upper() for t in new_tokens.split(",") if t.strip()]
                if tokens_list:
                    set_config('tokens', tokens_list)
                    st.success("OK")
                    st.rerun()
        with st.expander("Заявки на вывод"):
            res = supabase.table('withdrawals').select('*, users(email)').eq('status','pending').execute()
            for w in res.data:
                st.write(f"{w['users']['email']}: {w['amount']} USDT → {w['wallet_address']}")
                if st.button(f"Одобрить {w['id']}"):
                    supabase.table('withdrawals').update({'status':'approved','processed_at':datetime.now().isoformat()}).eq('id',w['id']).execute()
                    st.rerun()
