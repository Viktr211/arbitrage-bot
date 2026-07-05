import sys
import os
import time
import asyncio
from datetime import datetime

# Принудительно сбрасываем буферы вывода
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

# Добавляем путь к проекту
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.getcwd())

# Пишем в stderr сразу при старте, чтобы точно увидеть
print("🚀 Worker: старт скрипта", file=sys.stderr, flush=True)

try:
    from utils import (
        supabase,
        get_user_by_email,
        get_user_settings,
        set_auto_trade_enabled,
        init_real_exchanges,
        find_arbitrage_opportunity,
        execute_arbitrage,
        save_balances,
        save_log,
        get_logs,
        get_trade_mode,
        get_demo_data,
        reset_demo_data,
        EXCHANGES,
        TOKENS
    )
    print("✅ Worker: импорт utils успешен", file=sys.stderr, flush=True)
except Exception as e:
    print(f"❌ Worker: ошибка импорта utils: {e}", file=sys.stderr, flush=True)
    sys.exit(1)

ADMIN_EMAIL = "cb777899@gmail.com"
SCAN_INTERVAL = 30
BALANCE_SAVE_INTERVAL = 300

def log(msg, log_type='info'):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    full_msg = f"[{timestamp}] {msg}"
    # Пишем и в stdout, и в stderr для надёжности
    print(full_msg, flush=True)
    print(full_msg, file=sys.stderr, flush=True)
    admin_user = get_user_by_email(ADMIN_EMAIL)
    if admin_user:
        try:
            save_log(admin_user['id'], msg, log_type)
        except Exception as e:
            print(f"❌ Ошибка сохранения лога: {e}", file=sys.stderr, flush=True)

def get_worker_settings():
    admin_user = get_user_by_email(ADMIN_EMAIL)
    if not admin_user:
        log("❌ Администратор не найден", 'error')
        return None, None
    settings = get_user_settings(admin_user['id'])
    if not settings:
        log("❌ Настройки пользователя не найдены", 'error')
        return None, None
    return settings, admin_user

async def main_loop():
    log("🚀 Worker запущен")
    
    real_exchanges = init_real_exchanges()
    if not any(real_exchanges.values()):
        log("❌ Не удалось подключиться ни к одной бирже. Проверьте API-ключи.", 'error')
        return
    
    log(f"✅ Подключены биржи: {', '.join([ex for ex, c in real_exchanges.items() if c])}")
    
    last_trade_info = {}
    balance_counter = 0
    demo_data = None
    first_run = True
    
    while True:
        try:
            settings, admin_user = get_worker_settings()
            if not settings or not admin_user:
                await asyncio.sleep(SCAN_INTERVAL)
                continue
            
            if not settings.get('auto_trade_enabled', False):
                # Логируем раз в 5 сканов, чтобы не засорять
                if balance_counter % (SCAN_INTERVAL * 5) == 0:
                    log("⏸ Авто-торговля остановлена в настройках")
                await asyncio.sleep(SCAN_INTERVAL)
                continue
            
            trade_mode = get_trade_mode(admin_user['id'])
            is_demo = (trade_mode == 'демо')
            
            if is_demo:
                if first_run:
                    demo_data = get_demo_data(admin_user['id'])
                    if not demo_data:
                        log("🔄 Создание демо-данных...")
                        demo_data = reset_demo_data(admin_user['id'])
                    first_run = False
                if not demo_data:
                    log("❌ Демо-данные не загружены", 'error')
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
                
                profit, msg = execute_arbitrage(
                    opp, admin_user['id'], real_exchanges,
                    reinvest_percent, use_orderbook, orderbook_depth, max_slippage,
                    is_demo, demo_data
                )
                if profit:
                    log(f"✅ Исполнено! +{profit:.2f} USDT")
                    last_trade_info[token] = {
                        'direction': (opp['buy_ex'], opp['sell_ex']),
                        'timestamp': datetime.now()
                    }
                    if not is_demo:
                        save_balances(admin_user['id'], real_exchanges)
                else:
                    log(f"❌ Ошибка: {msg}", 'error')
            else:
                log("⏳ Сканирование завершено, возможностей не найдено")
            
            balance_counter += SCAN_INTERVAL
            if balance_counter >= BALANCE_SAVE_INTERVAL:
                balance_counter = 0
                if not is_demo:
                    save_balances(admin_user['id'], real_exchanges)
                    log("💾 Балансы сохранены в БД")
            
            await asyncio.sleep(SCAN_INTERVAL)
            
        except Exception as e:
            log(f"❌ Ошибка в цикле: {e}", 'error')
            await asyncio.sleep(SCAN_INTERVAL)

if __name__ == "__main__":
    try:
        asyncio.run(main_loop())
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}", file=sys.stderr, flush=True)
        sys.exit(1)
