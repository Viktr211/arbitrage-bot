import json
import os
import ccxt
import hashlib
from supabase import create_client, Client
from cryptography.fernet import Fernet
from datetime import datetime

# ------------------- SUPABASE -------------------
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise Exception("❌ Ошибка: не заданы SUPABASE_URL и SUPABASE_KEY.")

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
TOKENS = ["SOL", "LINK", "HYPE", "SUI", "ONDO", "PEPE", "WIF", "BOME", "BONK", "FLOKI"]

TOKEN_MAX_TRADE = {
    "BTC": 300, "ETH": 250, "SOL": 200, "BNB": 200, "TON": 150,
    "LINK": 100, "HYPE": 100, "SUI": 100, "ONDO": 100,
    "DOGE": 100, "SHIB": 100, "PEPE": 50, "WIF": 50, "FLOKI": 50,
    "BONK": 50, "MEME": 50, "BOME": 50, "NEIRO": 50, "BRETT": 50
}

# ------------------- БАЗА ДАННЫХ -------------------
def get_config(key: str):
    res = supabase.table('config').select('value').eq('key', key).execute()
    return json.loads(res.data[0]['value']) if res.data else None

def set_config(key: str, value):
    supabase.table('config').upsert({'key': key, 'value': json.dumps(value)}).execute()

def get_available_tokens():
    tokens_from_db = get_config('tokens')
    return tokens_from_db if tokens_from_db else TOKENS

def get_user_by_email(email):
    res = supabase.table('users').select('*').eq('email', email).execute()
    return res.data[0] if res.data else None

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

def get_user_settings(user_id):
    res = supabase.table('user_settings').select('*').eq('user_id', user_id).execute()
    return res.data[0] if res.data else None

def update_user_settings(user_id, settings):
    supabase.table('user_settings').update(settings).eq('user_id', user_id).execute()

def add_trade(user_id, mode, asset, amount, profit, buy_ex, sell_ex):
    try:
        result = supabase.table('trades').insert({
            'user_id': user_id,
            'mode': mode,
            'asset': asset,
            'amount': amount,
            'profit': profit,
            'buy_exchange': buy_ex,
            'sell_exchange': sell_ex
        }).execute()
        return True
    except Exception as e:
        print(f"❌ Ошибка сохранения сделки: {e}")
        return False

def get_user_trades(user_id, limit=100):
    try:
        res = supabase.table('trades').select('*').eq('user_id', user_id).order('trade_time', desc=True).limit(limit).execute()
        return res.data
    except:
        return []

def get_auto_trade_enabled(user_id):
    settings = get_user_settings(user_id)
    if settings:
        return settings.get('auto_trade_enabled', False)
    return False

def set_auto_trade_enabled(user_id, enabled):
    settings = get_user_settings(user_id)
    if settings:
        settings['auto_trade_enabled'] = enabled
        update_user_settings(user_id, settings)

# ------------------- СОХРАНЕНИЕ БАЛАНСОВ И ЛОГОВ -------------------
def save_balances(user_id, exchanges):
    """Сохраняет балансы всех бирж в БД"""
    try:
        tokens = get_available_tokens()
        for ex_name, ex_obj in exchanges.items():
            if ex_obj:
                try:
                    bal = ex_obj.fetch_balance()
                    # USDT
                    usdt_total = bal.get('USDT', {}).get('total', 0.0)
                    supabase.table('balances').insert({
                        'user_id': user_id,
                        'exchange': ex_name,
                        'asset': 'USDT',
                        'free': bal.get('USDT', {}).get('free', 0.0),
                        'used': bal.get('USDT', {}).get('used', 0.0),
                        'total': usdt_total,
                        'usdt_value': usdt_total
                    }).execute()
                    # Токены
                    for token in tokens:
                        free = bal.get(token, {}).get('free', 0.0)
                        if free > 0:
                            price = get_price(ex_obj, token)
                            usdt_value = free * price if price else 0
                            supabase.table('balances').insert({
                                'user_id': user_id,
                                'exchange': ex_name,
                                'asset': token,
                                'free': free,
                                'used': 0,
                                'total': free,
                                'usdt_value': usdt_value
                            }).execute()
                except Exception as e:
                    print(f"Ошибка сохранения баланса {ex_name}: {e}")
    except Exception as e:
        print(f"Ошибка сохранения балансов: {e}")

def save_log(user_id, message, log_type='info'):
    """Сохраняет лог в БД"""
    try:
        supabase.table('bot_logs').insert({
            'user_id': user_id,
            'message': message,
            'log_type': log_type
        }).execute()
    except Exception as e:
        print(f"Ошибка сохранения лога: {e}")

def get_latest_balances(user_id):
    """Получает последние сохранённые балансы для пользователя"""
    try:
        res = supabase.table('balances').select('*').eq('user_id', user_id).order('created_at', desc=True).limit(200).execute()
        return res.data
    except Exception as e:
        print(f"Ошибка получения балансов: {e}")
        return []

def get_logs(user_id, limit=100):
    """Получает последние логи"""
    try:
        res = supabase.table('bot_logs').select('*').eq('user_id', user_id).order('created_at', desc=True).limit(limit).execute()
        return res.data
    except Exception as e:
        print(f"Ошибка получения логов: {e}")
        return []

# ------------------- БИРЖИ (синхронные для worker) -------------------
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
            except Exception as e:
                print(f"Ошибка инициализации {ex}: {e}")
                exchanges[ex] = None
        else:
            exchanges[ex] = None
    return exchanges

def get_real_balance(exchange, asset):
    if not exchange: return 0.0
    try:
        bal = exchange.fetch_balance()
        if asset == 'USDT':
            return bal.get('USDT', {}).get('free', 0.0)
        else:
            return bal.get(asset, {}).get('free', 0.0)
    except: return 0.0

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
            if not asks:
                return None, 0, "Нет данных в стакане (asks)"
            total_usdt = 0; total_amount = 0
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
                avg_price = total_usdt / total_amount if total_amount > 0 else None
                return avg_price, total_usdt, f"Доступно только {total_usdt:.2f} USDT"
            avg_price = total_usdt / total_amount
            return avg_price, total_usdt, None
        else:  # sell
            bids = orderbook['bids']
            if not bids:
                return None, 0, "Нет данных в стакане (bids)"
            remaining = amount_usdt; total_amount = 0; total_received = 0
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

def find_arbitrage_opportunity(fee, min_profit, min_trade, max_trade, depth, use_orderbook, real_exchanges, max_slippage=0.3):
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
    
    opportunities = []
    for buy_ex in EXCHANGES:
        for sell_ex in EXCHANGES:
            if buy_ex == sell_ex: continue
            for token in tokens:
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
                    'token': token,
                    'buy_ex': buy_ex,
                    'sell_ex': sell_ex,
                    'buy_price': buy_price,
                    'sell_price': sell_price,
                    'trade_usdt': trade_usdt,
                    'amount': amount,
                    'profit': profit
                })
    if not opportunities:
        return None
    return max(opportunities, key=lambda x: x['profit'])

def execute_real_arbitrage(opp, user_id, real_exchanges, reinvest_percent, use_orderbook=True, depth=20, max_slippage=0.3):
    buy_ex = opp['buy_ex']; sell_ex = opp['sell_ex']; token = opp['token']
    amount = opp['amount']; trade_usdt = opp['trade_usdt']; sell_price = opp['sell_price']
    
    if not real_exchanges or not any(real_exchanges.values()):
        return None, "Реальные биржи не подключены"
    
    exch_buy = real_exchanges.get(buy_ex)
    exch_sell = real_exchanges.get(sell_ex)
    if not exch_buy or not exch_sell:
        return None, f"Одна из бирж не подключена: buy={buy_ex}, sell={sell_ex}"
    
    usdt_balance = get_real_balance(exch_buy, 'USDT')
    token_balance = get_real_balance(exch_sell, token)
    
    if usdt_balance < trade_usdt:
        trade_usdt = min(trade_usdt, usdt_balance)
        if trade_usdt < 5:
            return None, f"Не хватает USDT на {buy_ex}: {usdt_balance:.2f}"
        amount = trade_usdt / opp['buy_price']
    
    if token_balance < amount * 1.02:
        max_sell_usdt = token_balance * opp['sell_price'] * 0.98
        trade_usdt = min(trade_usdt, max_sell_usdt)
        if trade_usdt < 5:
            return None, f"Не хватает {token} на {sell_ex}: нужно {amount:.8f}, доступно {token_balance:.8f}"
        amount = trade_usdt / opp['buy_price']
    
    # Покупка
    ticker = exch_buy.fetch_ticker(f"{token}/USDT")
    price = ticker['last']
    amount_token = trade_usdt / price
    order = exch_buy.create_market_buy_order(f"{token}/USDT", amount_token)
    filled = order.get('filled', amount_token)
    cost = order.get('cost', trade_usdt)
    if not filled:
        return None, "Не удалось получить данные о покупке"
    real_buy_price = cost / filled
    
    # Продажа
    sell_amount = filled
    ticker_sell = exch_sell.fetch_ticker(f"{token}/USDT")
    sell_price_ticker = ticker_sell['last']
    sell_usdt = sell_amount * sell_price_ticker
    order_sell = exch_sell.create_market_sell_order(f"{token}/USDT", sell_amount)
    filled_sell = order_sell.get('filled', sell_amount)
    cost_sell = order_sell.get('cost', sell_usdt)
    if not filled_sell:
        return None, "Не удалось получить данные о продаже"
    real_sell_price = cost_sell / filled_sell
    
    # Прибыль
    real_profit = (real_sell_price - real_buy_price) * filled_sell
    total_turnover = trade_usdt + sell_usdt
    real_profit -= total_turnover * 0.002
    real_profit -= 0.005
    
    if real_profit < 0.005:
        return None, f"Убыток {real_profit:.4f} USDT"
    
    add_trade(user_id, "Реальный", token, filled_sell, real_profit, buy_ex, sell_ex)
    return real_profit, f"Сделка выполнена! Прибыль: {real_profit:.2f} USDT"
