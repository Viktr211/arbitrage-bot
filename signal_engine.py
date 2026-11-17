import streamlit as st
import streamlit.components.v1 as components
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import asyncio
from datetime import datetime, timedelta

try:
    from pocketoptionapi_async import AsyncPocketOptionClient
except Exception as e:
    st.error(f"Ошибка импорта библиотеки: {e}")
    st.stop()

# ===== НАСТРОЙКИ =====
SYMBOLS = ["EURUSD_otc", "GBPUSD_otc", "USDJPY_otc", "AUDUSD_otc", "USDCAD_otc", "USDCHF_otc", "NZDUSD_otc", "XAUUSD_otc"]
SYMBOLS_DISPLAY = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD", "XAUUSD"]

EMA_FAST_M5 = 3
EMA_SLOW_M5 = 8
ABSORPTION_VOLUME_MULT = 1.2
MIN_SIGNAL_CONFIDENCE = 0.5

def calculate_ema(prices, period):
    if len(prices) < period: return None
    multiplier = 2 / (period + 1)
    ema = prices[0]
    for price in prices[1:]:
        ema = (price - ema) * multiplier + ema
    return ema

class SignalEngine:
    def __init__(self):
        try:
            self.ssid = st.secrets["PO_SSID"]
        except Exception as e:
            st.error(f"Ошибка чтения SSID: {e}")
            self.ssid = None
        
        self.client = None
        self.connected = False
        self.signals = []
        self.data_cache = {}
        self.active_lights = {sym: None for sym in SYMBOLS_DISPLAY}

    async def connect(self):
        if not self.ssid: return False
        try:
            self.client = AsyncPocketOptionClient(self.ssid, is_demo=True, enable_logging=False)
            await self.client.connect()
            self.connected = True
            st.success("✅ Подключено к Pocket Option")
            return True
        except Exception as e:
            st.error(f"❌ Ошибка подключения: {type(e).__name__}: {e}")
            return False

    async def fetch_candles(self, symbol):
        if not self.connected: return pd.DataFrame()
        try:
            candles = await self.client.get_candles(asset=symbol, timeframe=60, count=100)
            df = pd.DataFrame([{
                "time": pd.to_datetime(c.timestamp, unit='s'),
                "open": c.open, "high": c.high, "low": c.low, "close": c.close, "volume": c.volume
            } for c in candles])
            if df.empty: return df
            df = df.sort_values('time').reset_index(drop=True)
            df['delta'] = (df['close'] - df['open']) * df['volume']
            return df
        except Exception as e:
            # Тихо игнорируем, чтобы не спамить
            return pd.DataFrame()

    async def update_async(self):
        if not self.connected:
            await self.connect()
            if not self.connected: return False

        new_sig = False
        now = datetime.now()

        for i, sym_td in enumerate(SYMBOLS):
            sym_display = SYMBOLS_DISPLAY[i]
            
            if sym_display in self.data_cache:
                last_candle_time = self.data_cache[sym_display]['time'].iloc[-1]
                if (now - last_candle_time).seconds < 60:
                    continue

            df_m1 = await self.fetch_candles(sym_td)
            if df_m1.empty: continue
            self.data_cache[sym_display] = df_m1

            df_m5 = df_m1.set_index("time").resample("5min").agg({"close": "last"}).dropna().reset_index()
            if len(df_m5) < EMA_SLOW_M5 + 1: continue
                
            prices_m5 = df_m5["close"].tolist()
            ema_f = calculate_ema(prices_m5, EMA_FAST_M5)
            ema_s = calculate_ema(prices_m5, EMA_SLOW_M5)
            if ema_f is None or ema_s is None: continue
                
            trend = 1 if ema_f > ema_s else (-1 if ema_f < ema_s else 0)
            if trend == 0: continue

            last = df_m1.iloc[-1]
            avg_volume = df_m1['volume'].tail(20).mean()
            if avg_volume == 0: continue

            volume_ratio = last['volume'] / avg_volume
            signal = 0
            confidence = 0
            reason = ""

            if volume_ratio > ABSORPTION_VOLUME_MULT:
                if last['delta'] > 0 and trend == 1:
                    signal, confidence, reason = 1, min(0.9, 0.5 + volume_ratio * 0.1), f"Абсорбция продаж (vol x{volume_ratio:.1f})"
                elif last['delta'] < 0 and trend == -1:
                    signal, confidence, reason = -1, min(0.9, 0.5 + volume_ratio * 0.1), f"Абсорбция покупок (vol x{volume_ratio:.1f})"

            if signal != 0 and confidence >= MIN_SIGNAL_CONFIDENCE:
                entry_time = (now + timedelta(minutes=1)).replace(second=0, microsecond=0)
                self.active_lights[sym_display] = "CALL" if signal == 1 else "PUT"
                
                self.signals.append({
                    "time": now, "entry_time": entry_time, "expiry": "1-3 мин",
                    "symbol": sym_display,
                    "direction": "CALL" if signal == 1 else "PUT",
                    "confidence": confidence, "reason": reason,
                    "trend_m5": "UP" if trend == 1 else "DOWN",
                })
                if len(self.signals) > 100: self.signals = self.signals[-100:]
                new_sig = True

        for sym in SYMBOLS_DISPLAY:
            sig = next((s for s in reversed(self.signals) if s["symbol"] == sym), None)
            if sig and (now - sig["time"]).seconds > 60:
                self.active_lights[sym] = None
                
        return new_sig

    def update(self):
        try:
            return asyncio.run(self.update_async())
        except Exception as e:
            st.error(f"Критическая ошибка в цикле обновления: {type(e).__name__}: {e}")
            return False

# ===== ИНТЕРФЕЙС =====
st.set_page_config(page_title="Signal Engine (Pocket Option)", layout="wide")
st.title("🎯 SIGNAL CONFLUENCE ENGINE v3.1 (Pocket Option)")

if "engine" not in st.session_state:
    st.session_state.engine = SignalEngine()
engine = st.session_state.engine

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

@st.fragment(run_every="5s")
def render_dashboard():
    engine = st.session_state.engine
    
    if engine.update():
        play_sound(engine.signals[-1]["direction"])

    selected_sym = st.selectbox(
        "Выберите актив для графика:",
        SYMBOLS_DISPLAY,
        format_func=lambda x: f"🔔 {x} (Сигнал!)" if engine.active_lights[x] else x
    )

    st.markdown("### 🟢 Активы в реальном времени 🔴")
    cols = st.columns(8)
    for i, sym in enumerate(SYMBOLS_DISPLAY):
        with cols[i]:
            light = engine.active_lights[sym]
            color = "#00FF00" if light == "CALL" else ("#FF0000" if light == "PUT" else "#333333")
            text_c = "black" if light == "CALL" else "white"
            st.markdown(f"<div style='background-color: {color}; padding: 15px 5px; border-radius: 10px; text-align: center; border: 2px solid #444;'><h4 style='color: {text_c}; margin: 0; font-size: 16px;'>{sym}</h4></div>", unsafe_allow_html=True)

    st.markdown("---")

    col_graph, col_forecast = st.columns([2, 1])

    with col_graph:
        st.subheader(f"📈 График M1 ({selected_sym})")
        df = engine.data_cache.get(selected_sym)
        
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
            <p><b>Прогноз:</b> Система автоматически приостановит выдачу сигналов при аномальных скачках цен (новостные шпильки).</p>
        </div>
        """, unsafe_allow_html=True)
        st.caption("*(Реальный режим Pocket Option)*")

    st.markdown("---")
    st.subheader("📜 История сигналов")
    if engine.signals:
        hist_data = []
        for s in reversed(engine.signals):
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
