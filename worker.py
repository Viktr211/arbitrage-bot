import time
import asyncio
import os
from datetime import datetime
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from utils import (
    get_user_by_email,
    get_user_settings,
    set_auto_trade_enabled,
    init_real_exchanges,
    find_arbitrage_opportunity,
    execute_real_arbitrage,
    save_balances,
    save_log,
    get_config,
    set_config
)

ADMIN_EMAIL = "cb777899@gmail.com"
SCAN_INTERVAL = 30
BALANCE_SAVE_INTERVAL = 300  # 5 минут

def log(msg):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] {msg}")
    # Сохраняем в БД
    admin_user = get_user_by_email(ADMIN_EMAIL)
    if admin_user:
        save_log(admin_user['id'], msg)

def get_worker_settings():
    admin_user = get_user_by_email(ADMIN_EMAIL)
    if not admin_user:
        log("❌ Администратор не найден")
        return None
    settings = get_user_settings(admin_user['id'])
    if not settings:
        log("❌ Настройки пользователя не найдены")
        return None
    return settings

async def main_loop():
    log("🚀 Worker запущен")
    
    real_exchanges = init_real_exchanges()
    if not any(real_exchanges.values()):
        log("❌ Не удалось подключиться ни к одной бирже. Проверьте API-ключи.")
        return
    
    log(f"✅ Подключены биржи: {', '.join([ex for ex, c in real_exchanges.items() if c])}")
    
    last_trade_info = {}
    balance_counter = 0
    
    while True:
        try:
            settings = get_worker_settings()
            if not settings:
                await asyncio.sleep(SCAN_INTERVAL)
                continue
            
            if not settings.get('auto_trade_enabled', False):
                await asyncio.sleep(SCAN_INTERVAL)
                continue
            
            fee = settings.get('fee', 0.2)
            min_profit = settings.get('min_profit', 0.03)
            min_trade = settings.get('min_trade', 8.0)
            max_trade = settings.get('max_trade', 20.0)
            use_orderbook = settings.get('use_orderbook', True)
            max_slippage = settings.get('max_slippage', 0.3)
            orderbook_depth = settings.get('orderbook_depth', 20)
            reinvest_percent = settings.get('reinvest_percent', 0)
            
            opp = find_arbitrage_opportunity(
                fee, min_profit, min_trade, max_trade,
                orderbook_depth, use_orderbook,
                real_exchanges, max_slippage
            )
            
            if opp:
                token = opp['token']
                now = datetime.now()
                if token in last_trade_info:
                    last_dir = last_trade_info[token].get('direction')
                    last_time = last_trade_info[token].get('timestamp')
                    if last_time and (now - last_time).seconds < 60:
                        if last_dir and (opp['buy_ex'], opp['sell_ex']) != last_dir:
                            log(f"⏳ Пропускаем {token} (обратная сделка < 1 мин)")
                            await asyncio.sleep(1)
                            continue
                
                log(f"🔍 Найдена возможность: {token} {opp['buy_ex']}→{opp['sell_ex']} | прибыль {opp['profit']:.4f} USDT")
                
                admin_user = get_user_by_email(ADMIN_EMAIL)
                if admin_user:
                    profit, msg = execute_real_arbitrage(
                        opp, admin_user['id'], real_exchanges,
                        reinvest_percent, use_orderbook, orderbook_depth, max_slippage
                    )
                    if profit:
                        log(f"✅ Исполнено! +{profit:.2f} USDT")
                        last_trade_info[token] = {
                            'direction': (opp['buy_ex'], opp['sell_ex']),
                            'timestamp': datetime.now()
                        }
                    else:
                        log(f"❌ Ошибка: {msg}")
                else:
                    log("❌ Администратор не найден")
            else:
                log("⏳ Сканирование завершено, возможностей не найдено")
            
            # Сохраняем балансы раз в 5 минут
            balance_counter += SCAN_INTERVAL
            if balance_counter >= BALANCE_SAVE_INTERVAL:
                balance_counter = 0
                admin_user = get_user_by_email(ADMIN_EMAIL)
                if admin_user:
                    save_balances(admin_user['id'], real_exchanges)
                    log("💾 Балансы сохранены в БД")
            
            await asyncio.sleep(SCAN_INTERVAL)
            
        except Exception as e:
            log(f"❌ Ошибка в цикле: {e}")
            await asyncio.sleep(SCAN_INTERVAL)

if __name__ == "__main__":
    asyncio.run(main_loop())
