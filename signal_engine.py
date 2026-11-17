import streamlit as st
import streamlit.components.v1 as components
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import asyncio
import threading
import time
from datetime import datetime, timedelta

# ===== ПРАВИЛЬНЫЕ ИМПОРТЫ БИБЛИОТЕКИ =====
from pocket_option import PocketOptionClient
from pocket_option.models import AuthorizationData, Asset
from pocket_option.constants import Regions
from pocket_option.contrib.candles import MemoryCandleStorage

# ===== НАСТРОЙКИ =====
SYMBOLS = ["EURUSD_otc", "GBPUSD_otc", "USDJPY_otc", "AUDUSD_otc", "USDCAD_otc", "USDCHF_otc", "NZDUSD_otc", "XAUUSD_otc"]
SYMBOLS_DISPLAY = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD", "XAUUSD"]

EMA_FAST_M5 = 3
EMA_SLOW_M5 = 8
ABSORPTION_VOLUME_MULT = 1.2
MIN_SIGNAL_CONFIDENCE = 0.5

# ===== ГЛОБАЛЬНОЕ СОСТОЯНИЕ =====
STATE = {
    "data": {},
    "signals": [],
    "active_lights": {sym: None for sym in SYMBOLS_DISPLAY},
    "status": "⏳ Подключение к Pocket Option...",
    "connected": False
}

def calculate_ema(prices, period):
    if len(prices) < period: return None
    multiplier = 2 / (period + 1)
    ema = prices[0]
    for price in prices[1:]:
        ema = (price - ema) * multiplier + ema
    return ema

# ===== ФОНОВЫЙ БОТ =====
async def bot_worker():
    try:
        session = st.secrets.get("PO_SESSION")
        uid = st.secrets.get("PO_UID")
        if not session or not uid:
            STATE["status"] = "❌ PO_SESSION или PO_UID не найдены в секретах"
            return

        client = PocketOptionClient()
        # Создаем хранилище для свечей
        candle_storage = MemoryCandleStorage(client)

        @client.on.connect
        async def on_connect(data: None):
            STATE["status"] = "✅ Подключено к Pocket Option, авторизация..."
            await client.emit.auth(
                AuthorizationData.model_validate({
                    "session": session,
                    "isDemo": 1,
                    "uid": int(uid),
                    "platform": 2,
                    "isFastHistory": True,
                    "isOptimized": True,
                })
            )

        @client.on.success_auth
        async def on_success_auth(data):
            STATE["status"] = "✅ Авторизация успешна. Подписка на активы..."
            STATE["connected"] = True
            for sym in SYMBOLS:
                asset = getattr(Asset, sym)
                await client.emit.subscribe_symbol(asset)
                await client.emit.change_symbol(asset, period=60) # M1

        await client.connect(Regions.DEMO)

        # Основной цикл анализа (данные уже накапливаются в candle_storage)
        while True:
            now = datetime.now()
            for i, sym in enumerate(SYMBOLS):
                sym_disp = SYMBOLS_DISPLAY[i]
                try:
                    asset = getattr(Asset, sym)
                    # Получаем свечи из встроенного хранилища
                    candles = candle_storage.get_candles(asset, period=60, count=100)
                    if not candles: continue
                    
                    df = pd.DataFrame([{
                        "time": pd.to_datetime(c.timestamp, unit='s'),
                        "open": c.open, "high": c.high, "low": c.low, "close": c.close, "volume": c.volume
                    } for c in candles])
                    
                    if df.empty: continue
                    df = df.sort_values('time').reset_index(drop=True)
                    df['delta'] = (df['close'] - df['open']) * df['volume']
                    
                    STATE["data"][sym_disp] = df
                    
                    # Логика поиска сигналов
                    last_sig = next((s for s in reversed(STATE["signals"]) if s["symbol"] == sym_disp), None)
                    if not last_sig or (now - last_sig["time"]).seconds > 300:
                        df_m5 = df.set_index("time").resample("5min").agg({"close": "last"}).dropna().reset_index()
                        if len(df_m5) >= EMA_SLOW_M5 + 1:
                            prices_m5 = df_m5["close"].tolist()
                            ema_f = calculate_ema(prices_m5, EMA_FAST_M5)
                            ema_s = calculate_ema(prices_m5, EMA_SLOW_M5)
                            if ema_f and ema_s:
                                trend = 1 if ema_f > ema_s else (-1 if ema_f < ema_s else 0)
                                last = df.iloc[-1]
                                avg_vol = df['volume'].tail(20).mean()
                                if avg_vol > 0 and trend != 0:
                                    vol_ratio = last['volume'] / avg_vol
                                    if vol_ratio > ABSORPTION_VOLUME_MULT:
                                        signal = 0
                                        reason = ""
                                        if last['delta'] > 0 and trend == 1:
                                            signal, reason = 1, f"Абсорбция продаж (vol x{vol_ratio:.1f})"
                                        elif last['delta'] < 0 and trend == -1:
                                            signal, reason = -1, f"Абсорбция покупок (vol x{vol_ratio:.1f})"
                                        
                                        if signal != 0:
                                            entry_time = (now + timedelta(minutes=1)).replace(second=0, microsecond=0)
                                            STATE["active_lights"][sym_disp] = "CALL" if signal == 1 else "PUT"
                                            STATE["signals"].append({
                                                "time": now, "entry_time": entry_time, "expiry": "1-3 мин",
                                                "symbol": sym_disp, "direction": "CALL" if signal == 1 else "PUT",
                                                "confidence": min(0.9, 0.5 + vol_ratio*0.1), "reason": reason
                                            })
                                            if len(STATE["signals"]) > 100: STATE["signals"] = STATE["signals"][-100:]
                except Exception as e:
                    # Пропускаем ошибки по отдельным парам, чтобы не ронять цикл
                    continue
            
            # Гасим светофоры старше 1 минуты
            for sym_disp in SYMBOLS_DISPLAY:
                sig = next((s for s in reversed(STATE["signals"]) if s["symbol"] == sym_disp), None)
                if sig and (datetime.now() - sig["time"]).seconds > 60:
                    STATE["active_lights"][sym_disp] = None

            await asyncio.sleep(30) # Обновляем анализ каждые 30 секунд

    except Exception as e:
        STATE["status"] = f"❌ Ошибка: {type(e).__name__}: {e}"
        STATE["connected"] = False

def start_background_loop():
    asyncio.run(bot_worker())

# ===== ИНТЕРФЕЙС =====
st.set_page_config(page_title="Signal Engine (PO)", layout="wide")
st.title("🎯 SIGNAL CONFLUENCE ENGINE v5.1 (Pocket Option)")

if "bot_started" not in st.session_state:
    thread = threading.Thread(target=start_background_loop, daemon=True)
    thread.start()
    st.session_state.bot_started = True

def play_sound(direction):
    freq = 880 if direction == "CALL" else 330
    wave_type = "sine" if direction == "CALL" else "square"
    js_code = f"""
    <script>
    try {{
        var audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        if (audioCtx.state === 'suspended') {{ audioCtx.resume(); }}
        var oscillator = audioCtx.createOscillator();
        var gainNode = audioCtx.createGain();
        oscillator.connect(gainNode);
        gainNode.connect(audioCtx.destination);
        oscillator.type = '{wave_type}';
        oscillator.frequency.value = {freq};
        gainNode.gain.setValueAtTime(0.5, audioCtx.currentTime);
        gainNode.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.4);
        oscillator.start();
        oscillator.stop(audioCtx.currentTime + 0.4);
    }} catch(e) {{ console.log("Audio blocked"); }}
    </script>
    """
    components.html(js_code, height=0)

@st.fragment(run_every="3s")
def render_dashboard():
    if STATE["signals"]:
        last_sig = STATE["signals"][-1]
        if "last_played_sig" not in st.session_state or st.session_state.last_played_sig != last_sig["time"]:
            play_sound(last_sig["direction"])
            st.session_state.last_played_sig = last_sig["time"]

    if STATE["connected"]:
        st.success(STATE["status"])
    else:
        st.warning(STATE["status"])

    selected_sym = st.selectbox(
        "Выберите актив для графика:",
        SYMBOLS_DISPLAY,
        format_func=lambda x: f"🔔 {x} (Сигнал!)" if STATE["active_lights"][x] else x
    )

    st.markdown("### 🟢 Активы в реальном времени 🔴")
    cols = st.columns(8)
    for i, sym in enumerate(SYMBOLS_DISPLAY):
        with cols[i]:
            light = STATE["active_lights"][sym]
            color = "#00FF00" if light == "CALL" else ("#FF0000" if light == "PUT" else "#333333")
            text_c = "black" if light == "CALL" else "white"
            st.markdown(f"<div style='background-color: {color}; padding: 15px 5px; border-radius: 10px; text-align: center; border: 2px solid #444;'><h4 style='color: {text_c}; margin: 0; font-size: 16px;'>{sym}</h4></div>", unsafe_allow_html=True)

    st.markdown("---")

    col_graph, col_forecast = st.columns([2, 1])

    with col_graph:
        st.subheader(f"📈 График M1 ({selected_sym})")
        df = STATE["data"].get(selected_sym)
        
        if df is not None and not df.empty:
            df_plot = df.tail(60).copy() 
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, subplot_titles=("Цена", "Delta"), vertical_spacing=0.08)
            fig.add_trace(go.Candlestick(x=df_plot["time"], open=df_plot["open"], high=df_plot["high"], low=df_plot["low"], close=df_plot["close"], name="Цена", increasing_line_color="lime", decreasing_line_color="red"), row=1, col=1)
            colors = ["lime" if d > 0 else "red" for d in df_plot["delta"]]
            fig.add_trace(go.Bar(x=df_plot["time"], y=df_plot["delta"], name="Delta", marker_color=colors), row=2, col=1)
            fig.update_layout(height=450, template="plotly_dark", xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=30, b=10))
            st.plotly_chart(fig, width='stretch')
        else:
            st.info("Загрузка данных с Pocket Option... Подождите несколько секунд.")

    with col_forecast:
        st.subheader("🔮 AI Forecast")
        st.markdown("""
        <div style="background-color: #1E1E1E; padding: 15px; border-radius: 10px; border: 1px solid #444;">
            <h4 style="color: #FFA500; margin-top: 0;">📅 Фундаментальный фон</h4>
            <p><b>Статус:</b> Ожидание выхода новостей.</p>
            <p><b>Техника:</b> Оценка волатильности в реальном времени.</p>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")
    st.subheader("📜 История сигналов")
    if STATE["signals"]:
        hist_data = []
        for s in reversed(STATE["signals"]):
            hist_data.append({
                "Сформирован": s['time'].strftime('%H:%M:%S'),
                "Вход": s['entry_time'].strftime('%H:%M:%S'),
                "Экспирация": s['expiry'],
                "Актив": s['symbol'],
                "Сигнал": "🟢 BUY" if s['direction'] == "CALL" else "🔴 SELL",
                "Уверенность": f"{s['confidence']*100:.0f}%",
                "Причина": s['reason']
            })
        df_hist = pd.DataFrame(hist_data)
        
        csv = df_hist.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Скачать историю (CSV)", csv, f"signals_{datetime.now().strftime('%Y%m%d')}.csv", "text/csv")
        st.dataframe(df_hist, width='stretch', height=300)
    else:
        st.info("Ожидание реальных сигналов с Pocket Option. Это может занять некоторое время.")

render_dashboard()
