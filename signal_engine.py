import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import time
import random
from datetime import datetime, timedelta
from collections import deque

# ===== НАСТРОЙКИ АКТИВОВ =====
# 7 валютных пар + Золото
SYMBOLS = [
    "EURUSD_otc", "GBPUSD_otc", "USDJPY_otc", 
    "AUDUSD_otc", "USDCAD_otc", "USDCHF_otc", 
    "NZDUSD_otc", "XAUUSD_otc"
]

EMA_FAST_M5 = 3
EMA_SLOW_M5 = 8
ABSORPTION_VOLUME_MULT = 1.2
MIN_SIGNAL_CONFIDENCE = 0.5

# ===== ГЕНЕРАТОР ТИКОВ (ДЕМО) =====
class TickGenerator:
    def __init__(self, symbol, base_price=1.2000, volatility=0.0001):
        self.symbol = symbol
        # Для золота другие цены
        if "XAU" in symbol: 
            self.price = 2000.0
            self.volatility = 0.05
        else:
            self.price = base_price
            self.volatility = volatility
        self.trend = 0.0
        self.trend_timer = 0

    def next_tick(self):
        self.trend_timer -= 1
        if self.trend_timer <= 0:
            self.trend = random.uniform(-1, 1) * self.volatility * 0.5
            self.trend_timer = random.randint(30, 100)

        change = random.gauss(0, self.volatility) + self.trend
        self.price += change
        volume = random.randint(1, 10)
        direction = 1 if change > 0 else -1
        return {
            "time": datetime.now(),
            "price": round(self.price, 5),
            "volume": volume,
            "direction": direction
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
        if tick["direction"] == 1:
            c["buy_volume"] += tick["volume"]
        else:
            c["sell_volume"] += tick["volume"]
        c["delta"] = c["buy_volume"] - c["sell_volume"]

    def _finalize_candle(self):
        self.candles_m1.append(self.current_candle.copy())
        if len(self.candles_m1) > 300:
            self.candles_m1 = self.candles_m1[-300:]

    def get_m1_dataframe(self):
        if not self.candles_m1:
            return pd.DataFrame()
        return pd.DataFrame(self.candles_m1)

    def detect_absorption(self, lookback=20):
        if len(self.candles_m1) < lookback + 1:
            return 0, 0, ""
        df = pd.DataFrame(self.candles_m1[-lookback:])
        last = df.iloc[-1]
        avg_volume = df["volume"].mean()
        avg_range = (df["high"] - df["low"]).mean()

        if avg_volume == 0 or avg_range == 0:
            return 0, 0, ""

        volume_ratio = last["volume"] / avg_volume
        price_range = last["high"] - last["low"]
        range_ratio = price_range / avg_range if avg_range > 0 else 1

        if volume_ratio > ABSORPTION_VOLUME_MULT and range_ratio < 0.8:
            if last["delta"] > 0:
                return 1, min(0.95, 0.5 + volume_ratio * 0.1), f"Абсорбция продаж (vol x{volume_ratio:.1f})"
            elif last["delta"] < 0:
                return -1, min(0.95, 0.5 + volume_ratio * 0.1), f"Абсорбция покупок (vol x{volume_ratio:.1f})"
        return 0, 0, ""

def get_m5_trend(analyzer):
    df_m1 = analyzer.get_m1_dataframe()
    if df_m1.empty or len(df_m1) < 25: return 0
    df_m5 = df_m1.set_index("time").resample("5min").agg({"close": "last"}).dropna().reset_index()
    if len(df_m5) < EMA_SLOW_M5 + 1: return 0
    prices = df_m5["close"].tolist()
    
    ema_f = prices[0]
    for p in prices[1:]:
        ema_f = (p - ema_f) * (2 / (EMA_FAST_M5 + 1)) + ema_f
    ema_s = prices[0]
    for p in prices[1:]:
        ema_s = (p - ema_s) * (2 / (EMA_SLOW_M5 + 1)) + ema_s

    if ema_f > ema_s: return 1
    elif ema_f < ema_s: return -1
    return 0

# ===== ДВИЖОК =====
class SignalEngine:
    def __init__(self):
        self.generators = {sym: TickGenerator(sym) for sym in SYMBOLS}
        self.analyzers = {sym: OrderFlowAnalyzer() for sym in SYMBOLS}
        self.signals = []
        self.last_signal_time = {sym: None for sym in SYMBOLS}
        self.active_lights = {sym: None for sym in SYMBOLS} # Для светофора
        
        # РАЗОГРЕВ
        start_time = datetime.now() - timedelta(minutes=300)
        for sym in SYMBOLS:
            gen = self.generators[sym]
            analyzer = self.analyzers[sym]
            for i in range(3000):
                tick = gen.next_tick()
                tick["time"] = start_time + timedelta(seconds=i * 6)
                analyzer.add_tick(tick)

    def update(self):
        new_signal_triggered = False
        for sym in SYMBOLS:
            gen = self.generators[sym]
            analyzer = self.analyzers[sym]
            for _ in range(5):
                tick = gen.next_tick()
                analyzer.add_tick(tick)

            now = datetime.now()
            # Для демо-режима ускорим генерацию сигналов
            if self.last_signal_time[sym] and (now - self.last_signal_time[sym]).seconds < 15:
                continue

            trend = get_m5_trend(analyzer)
            if trend == 0: continue

            signal, confidence, reason = analyzer.detect_absorption()
            if signal == 0 or signal != trend or confidence < MIN_SIGNAL_CONFIDENCE:
                continue

            # Зажигаем светофор
            self.active_lights[sym] = "CALL" if signal == 1 else "PUT"
            self.last_signal_time[sym] = now
            
            # Добавляем в историю
            self.signals.append({
                "time": now, "symbol": sym,
                "direction": "CALL" if signal == 1 else "PUT",
                "confidence": confidence, "reason": reason,
                "trend_m5": "UP" if trend == 1 else "DOWN",
            })
            if len(self.signals) > 100:
                self.signals = self.signals[-100:]
            new_signal_triggered = True
            
        # Гасим светофоры, если сигналу больше 1 минуты
        for sym in SYMBOLS:
            if self.last_signal_time[sym] and (datetime.now() - self.last_signal_time[sym]).seconds > 60:
                self.active_lights[sym] = None

        return new_signal_triggered

# ===== ИНТЕРФЕЙС =====
st.set_page_config(page_title="Signal Engine v1.5", layout="wide")
st.title("🎯 SIGNAL CONFLUENCE ENGINE v1.5")

if "engine" not in st.session_state:
    st.session_state.engine = SignalEngine()
engine = st.session_state.engine

# Звуковое сопровождение (HTML/JS)
def play_sound(direction):
    if direction == "CALL":
        # Звук покупки (высокий)
        audio_html = """<audio autoplay><source src="https://actions.google.com/sounds/v1/alarms/beep_short.ogg" type="audio/ogg"></audio>"""
    else:
        # Звук продажи (низкий)
        audio_html = """<audio autoplay><source src="https://actions.google.com/sounds/v1/alarms/alert_1.ogg" type="audio/ogg"></audio>"""
    st.markdown(audio_html, unsafe_allow_html=True)

if engine.update():
    # Если появился новый сигнал, играем звук последнего
    play_sound(engine.signals[-1]["direction"])

# ===== ВЕРХНЯЯ ПАНЕЛЬ (СВЕТОФОР) =====
st.markdown("### 🟢 Активы в реальном времени 🔴")
cols = st.columns(8)
for i, sym in enumerate(SYMBOLS):
    with cols[i]:
        light = engine.active_lights[sym]
        # Форматируем название (убираем _otc)
        display_name = sym.replace("_otc", "")
        
        if light == "CALL":
            color = "#00FF00" # Ярко-зеленый
            text_color = "black"
        elif light == "PUT":
            color = "#FF0000" # Ярко-красный
            text_color = "white"
        else:
            color = "#333333" # Темно-серый (нет сигнала)
            text_color = "#888888"
            
        st.markdown(f"""
        <div style="background-color: {color}; padding: 15px 5px; border-radius: 10px; text-align: center; border: 2px solid #444;">
            <h4 style="color: {text_color}; margin: 0; font-size: 16px;">{display_name}</h4>
        </div>
        """, unsafe_allow_html=True)

st.markdown("---")

# ===== ОСНОВНОЙ ЭКРАН =====
col_left, col_right = st.columns([2, 1])

with col_left:
    st.subheader("📈 График M1 (EURUSD)")
    analyzer = engine.analyzers["EURUSD_otc"]
    df = analyzer.get_m1_dataframe()
    
    if not df.empty:
        df = df.tail(60).copy() 
        df["time"] = pd.to_datetime(df["time"])
        
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                            subplot_titles=("Цена", "Delta (Buy - Sell)"),
                            vertical_spacing=0.08)
        
        fig.add_trace(go.Candlestick(
            x=df["time"], open=df["open"], high=df["high"],
            low=df["low"], close=df["close"], name="Цена",
            increasing_line_color="lime", decreasing_line_color="red"
        ), row=1, col=1)
        
        colors = ["lime" if d > 0 else "red" for d in df["delta"]]
        fig.add_trace(go.Bar(x=df["time"], y=df["delta"], name="Delta", marker_color=colors), row=2, col=1)
        
        fig.update_layout(height=500, template="plotly_dark", xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=30, b=10))
        st.plotly_chart(fig, width='stretch')

with col_right:
    st.subheader("🎯 Последний сигнал")
    if engine.signals:
        sig = engine.signals[-1]
        color = "green" if sig["direction"] == "CALL" else "red"
        
        # Красивая карточка сигнала
        st.markdown(f"""
        <div style="background-color: #1E1E1E; padding: 20px; border-radius: 10px; border-left: 5px solid {color};">
            <h2 style="color: {color}; margin-top: 0;">{sig['symbol'].replace('_otc','')} — {sig['direction']}</h2>
            <p style="font-size: 18px;"><b>Время:</b> {sig['time'].strftime('%H:%M:%S')}</p>
            <p style="font-size: 16px;"><b>Причина:</b> {sig['reason']}</p>
            <p style="font-size: 16px;"><b>Тренд M5:</b> {sig['trend_m5']}</p>
        </div>
        """, unsafe_allow_html=True)
        
        # Шкала уверенности
        st.write("Уверенность:")
        st.progress(float(sig['confidence']), text=f"{sig['confidence']*100:.0f}%")
    else:
        st.info("Сигналов пока нет. Ждем-с...")

# ===== ИСТОРИЯ СИГНАЛОВ =====
st.markdown("---")
st.subheader("📜 История всех сигналов")
if engine.signals:
    # Создаем DataFrame для красивого отображения
    hist_data = []
    for s in reversed(engine.signals):
        hist_data.append({
            "Время": s['time'].strftime('%H:%M:%S'),
            "Актив": s['symbol'].replace('_otc',''),
            "Сигнал": "🟢 BUY" if s['direction'] == "CALL" else "🔴 SELL",
            "Уверенность": f"{s['confidence']*100:.0f}%",
            "Причина": s['reason']
        })
    df_hist = pd.DataFrame(hist_data)
    
    # Кнопка скачивания CSV
    csv = df_hist.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Скачать историю (CSV)",
        data=csv,
        file_name=f"signals_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv",
    )
    
    # Красивая таблица
    st.dataframe(df_hist, width='stretch', height=300)
else:
    st.info("История пока пуста.")

# Автообновление каждые 3 сек
time.sleep(3)
st.rerun()
