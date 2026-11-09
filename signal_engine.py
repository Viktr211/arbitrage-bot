import streamlit as st
import streamlit.components.v1 as components
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import time
import random
from datetime import datetime, timedelta
from collections import deque

# ===== НАСТРОЙКИ =====
SYMBOLS = [
    "EURUSD_otc", "GBPUSD_otc", "USDJPY_otc", 
    "AUDUSD_otc", "USDCAD_otc", "USDCHF_otc", 
    "NZDUSD_otc", "XAUUSD_otc"
]

EMA_FAST_M5 = 3
EMA_SLOW_M5 = 8
ABSORPTION_VOLUME_MULT = 0.8 # Для демо-теста оставляем мягким
MIN_SIGNAL_CONFIDENCE = 0.5

# ===== ГЕНЕРАТОР (ДЕМО) =====
class TickGenerator:
    def __init__(self, symbol):
        self.symbol = symbol
        self.price = 2000.0 if "XAU" in symbol else 1.2000
        self.volatility = 0.05 if "XAU" in symbol else 0.0001
        self.trend = 0.0
        self.trend_timer = 0

    def next_tick(self):
        self.trend_timer -= 1
        if self.trend_timer <= 0:
            self.trend = random.uniform(-1, 1) * self.volatility * 0.5
            self.trend_timer = random.randint(30, 100)
        change = random.gauss(0, self.volatility) + self.trend
        self.price += change
        return {
            "time": datetime.now(),
            "price": round(self.price, 5),
            "volume": random.randint(1, 10),
            "direction": 1 if change > 0 else -1
        }

# ===== АНАЛИЗАТОР =====
class OrderFlowAnalyzer:
    def __init__(self):
        self.ticks = deque(maxlen=5000)
        self.candles_m1 = []
        self.current_minute = None
        self.current_candle = None

    def add_tick(self, tick):
        self.ticks.append(tick)
        minute = tick["time"].replace(second=0, microsecond=0)
        if self.current_minute != minute:
            if self.current_candle:
                self._finalize_candle()
            self.current_minute = minute
            self.current_candle = {
                "time": minute, "open": tick["price"], "high": tick["price"],
                "low": tick["price"], "close": tick["price"],
                "volume": 0, "delta": 0, "buy_volume": 0, "sell_volume": 0,
            }
        c = self.current_candle
        c["high"] = max(c["high"], tick["price"])
        c["low"] = min(c["low"], tick["price"])
        c["close"] = tick["price"]
        c["volume"] += tick["volume"]
        if tick["direction"] == 1: c["buy_volume"] += tick["volume"]
        else: c["sell_volume"] += tick["volume"]
        c["delta"] = c["buy_volume"] - c["sell_volume"]

    def _finalize_candle(self):
        self.candles_m1.append(self.current_candle.copy())
        if len(self.candles_m1) > 300: self.candles_m1 = self.candles_m1[-300:]

    def get_m1_dataframe(self):
        return pd.DataFrame(self.candles_m1) if self.candles_m1 else pd.DataFrame()

    def detect_absorption(self, lookback=20):
        if len(self.candles_m1) < lookback + 1: return 0, 0, ""
        df = pd.DataFrame(self.candles_m1[-lookback:])
        last = df.iloc[-1]
        avg_vol = df["volume"].mean()
        avg_rng = (df["high"] - df["low"]).mean()
        if avg_vol == 0 or avg_rng == 0: return 0, 0, ""

        vol_ratio = last["volume"] / avg_vol
        rng_ratio = (last["high"] - last["low"]) / avg_rng

        if vol_ratio > ABSORPTION_VOLUME_MULT and rng_ratio < 0.8:
            if last["delta"] > 0:
                return 1, min(0.95, 0.5 + vol_ratio * 0.1), f"Абсорбция продаж (vol x{vol_ratio:.1f})"
            elif last["delta"] < 0:
                return -1, min(0.95, 0.5 + vol_ratio * 0.1), f"Абсорбция покупок (vol x{vol_ratio:.1f})"
        return 0, 0, ""

def get_m5_trend(analyzer):
    df = analyzer.get_m1_dataframe()
    if df.empty or len(df) < 25: return 0
    df_m5 = df.set_index("time").resample("5min").agg({"close": "last"}).dropna().reset_index()
    if len(df_m5) < EMA_SLOW_M5 + 1: return 0
    prices = df_m5["close"].tolist()
    ema_f = prices[0]
    for p in prices[1:]: ema_f = (p - ema_f) * (2 / (EMA_FAST_M5 + 1)) + ema_f
    ema_s = prices[0]
    for p in prices[1:]: ema_s = (p - ema_s) * (2 / (EMA_SLOW_M5 + 1)) + ema_s
    return 1 if ema_f > ema_s else (-1 if ema_f < ema_s else 0)

# ===== ДВИЖОК =====
class SignalEngine:
    def __init__(self):
        self.generators = {sym: TickGenerator(sym) for sym in SYMBOLS}
        self.analyzers = {sym: OrderFlowAnalyzer() for sym in SYMBOLS}
        self.signals = []
        self.last_signal_time = {sym: None for sym in SYMBOLS}
        self.active_lights = {sym: None for sym in SYMBOLS}
        
        # НОВОЕ: Переменная для хранения актива, по которому был последний сигнал
        self.last_signaled_symbol = "EURUSD_otc" 
        
        # Разогрев
        start_time = datetime.now() - timedelta(minutes=300)
        for sym in SYMBOLS:
            gen = self.generators[sym]
            analyzer = self.analyzers[sym]
            for i in range(3000):
                tick = gen.next_tick()
                tick["time"] = start_time + timedelta(seconds=i * 6)
                analyzer.add_tick(tick)

    def update(self):
        new_sig = False
        for sym in SYMBOLS:
            gen = self.generators[sym]
            analyzer = self.analyzers[sym]
            for _ in range(5):
                analyzer.add_tick(gen.next_tick())

            now = datetime.now()
            # Защита от дублей: не чаще раза в 10 секунд (для теста)
            if self.last_signal_time[sym] and (now - self.last_signal_time[sym]).seconds < 10:
                continue

            trend = get_m5_trend(analyzer)
            if trend == 0: continue

            signal, confidence, reason = analyzer.detect_absorption()
            if signal == 0 or signal != trend or confidence < MIN_SIGNAL_CONFIDENCE:
                continue

            entry_time = (now + timedelta(minutes=1)).replace(second=0, microsecond=0)
            
            self.active_lights[sym] = "CALL" if signal == 1 else "PUT"
            self.last_signal_time[sym] = now
            
            # НОВОЕ: Обновляем актив для графика
            self.last_signaled_symbol = sym 
            
            self.signals.append({
                "time": now, 
                "entry_time": entry_time,
                "expiry": "1-3 мин",
                "symbol": sym,
                "direction": "CALL" if signal == 1 else "PUT",
                "confidence": confidence, "reason": reason,
                "trend_m5": "UP" if trend == 1 else "DOWN",
            })
            if len(self.signals) > 100: self.signals = self.signals[-100:]
            new_sig = True
            
        for sym in SYMBOLS:
            if self.last_signal_time[sym] and (datetime.now() - self.last_signal_time[sym]).seconds > 60:
                self.active_lights[sym] = None
        return new_sig

# ===== ИНТЕРФЕЙС =====
st.set_page_config(page_title="Signal Engine v1.7", layout="wide")
st.title("🎯 SIGNAL CONFLUENCE ENGINE v1.7")

if "engine" not in st.session_state:
    st.session_state.engine = SignalEngine()
engine = st.session_state.engine

# НОВЫЙ ЗВУК (Web Audio API)
def play_sound(direction):
    # Генерируем звук прямо в браузере (обходит блокировки)
    freq = 880 if direction == "CALL" else 330 # Высокий для CALL, низкий для PUT
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
    }} catch(e) {{ console.log("Audio blocked by browser"); }}
    </script>
    """
    components.html(js_code, height=0)

if engine.update():
    play_sound(engine.signals[-1]["direction"])

# ===== СВЕТОФОР =====
st.markdown("### 🟢 Активы в реальном времени 🔴")
cols = st.columns(8)
for i, sym in enumerate(SYMBOLS):
    with cols[i]:
        light = engine.active_lights[sym]
        name = sym.replace("_otc", "")
        color = "#00FF00" if light == "CALL" else ("#FF0000" if light == "PUT" else "#333333")
        text_c = "black" if light == "CALL" else "white"
        st.markdown(f"<div style='background-color: {color}; padding: 15px 5px; border-radius: 10px; text-align: center; border: 2px solid #444;'><h4 style='color: {text_c}; margin: 0; font-size: 16px;'>{name}</h4></div>", unsafe_allow_html=True)

st.markdown("---")

# ===== ГРАФИК И ПРОГНОЗ =====
col_graph, col_forecast = st.columns([2, 1])

with col_graph:
    # НОВОЕ: Берем актив, по которому был последний сигнал
    target_sym = engine.last_signaled_symbol
    display_name = target_sym.replace("_otc", "")
    
    st.subheader(f"📈 График M1 ({display_name})")
    df = engine.analyzers[target_sym].get_m1_dataframe()
    
    if not df.empty:
        df_plot = df.tail(60).copy() 
        df_plot["time"] = pd.to_datetime(df_plot["time"])
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, subplot_titles=("Цена", "Delta"), vertical_spacing=0.08)
        fig.add_trace(go.Candlestick(x=df_plot["time"], open=df_plot["open"], high=df_plot["high"], low=df_plot["low"], close=df_plot["close"], name="Цена", increasing_line_color="lime", decreasing_line_color="red"), row=1, col=1)
        colors = ["lime" if d > 0 else "red" for d in df_plot["delta"]]
        fig.add_trace(go.Bar(x=df_plot["time"], y=df_plot["delta"], name="Delta", marker_color=colors), row=2, col=1)
        fig.update_layout(height=450, template="plotly_dark", xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=30, b=10))
        st.plotly_chart(fig, width='stretch')

with col_forecast:
    st.subheader("🔮 AI Forecast")
    st.markdown("""
    <div style="background-color: #1E1E1E; padding: 15px; border-radius: 10px; border: 1px solid #444;">
        <h4 style="color: #FFA500; margin-top: 0;">📅 16:15 — ВВП США (News)</h4>
        <p><b>Техника:</b> Сопротивление 1.2050 (M15)</p>
        <p><b>Прогноз:</b> Ожидается высокая волатильность. При отбое от уровня — <span style="color:red; font-weight:bold;">PUT</span> на 3 минуты.</p>
        <hr style="border-color: #444;">
        <h4 style="color: #00BFFF; margin-top: 10px;">📅 18:30 — Отчет по занятости (News)</h4>
        <p><b>Техника:</b> Поддержка 1.1980 (M5)</p>
        <p><b>Прогноз:</b> Сценарий на пробой вверх — <span style="color:green; font-weight:bold;">CALL</span> на 1 минуту.</p>
    </div>
    """, unsafe_allow_html=True)
    st.caption("*(Демо-режим)*")

# ===== ИСТОРИЯ =====
st.markdown("---")
st.subheader("📜 История сигналов")
if engine.signals:
    hist_data = []
    for s in reversed(engine.signals):
        hist_data.append({
            "Сформирован": s['time'].strftime('%H:%M:%S'),
            "Вход": s['entry_time'].strftime('%H:%M:%S'),
            "Экспирация": s['expiry'],
            "Актив": s['symbol'].replace('_otc',''),
            "Сигнал": "🟢 BUY" if s['direction'] == "CALL" else "🔴 SELL",
            "Уверенность": f"{s['confidence']*100:.0f}%",
            "Причина": s['reason']
        })
    df_hist = pd.DataFrame(hist_data)
    
    csv = df_hist.to_csv(index=False).encode('utf-8')
    st.download_button("📥 Скачать историю (CSV)", csv, f"signals_{datetime.now().strftime('%Y%m%d')}.csv", "text/csv")
    st.dataframe(df_hist, width='stretch', height=300)
else:
    st.info("История пока пуста.")

time.sleep(3)
st.rerun()
