import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import time
import random
from datetime import datetime, timedelta
from collections import deque

# ===== НАСТРОЙКИ =====
SYMBOLS = ["EURUSD_otc", "GBPUSD_otc", "USDJPY_otc"]
EMA_FAST_M5 = 3
EMA_SLOW_M5 = 8
ABSORPTION_VOLUME_MULT = 2.0
MIN_SIGNAL_CONFIDENCE = 0.6

# ===== ГЕНЕРАТОР ТИКОВ =====
class TickGenerator:
    def __init__(self, symbol, base_price=1.2000, volatility=0.0001):
        self.symbol = symbol
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

    def get_m5_dataframe(self):
        df = self.get_m1_dataframe()
        if df.empty:
            return df
        df = df.set_index("time")
        ohlc = df.resample("5min").agg({
            "open": "first", "high": "max", "low": "min", "close": "last",
            "volume": "sum", "delta": "sum", "buy_volume": "sum", "sell_volume": "sum",
        }).dropna()
        return ohlc.reset_index()

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

        if volume_ratio > ABSORPTION_VOLUME_MULT and range_ratio < 0.5:
            if last["delta"] > 0:
                confidence = min(0.9, 0.6 + volume_ratio * 0.05)
                return 1, confidence, f"Абсорбция продаж (vol x{volume_ratio:.1f}, delta +{last['delta']})"
            elif last["delta"] < 0:
                confidence = min(0.9, 0.6 + volume_ratio * 0.05)
                return -1, confidence, f"Абсорбция покупок (vol x{volume_ratio:.1f}, delta {last['delta']})"
        return 0, 0, ""

# ===== ФИЛЬТР ТРЕНДА =====
def get_m5_trend(analyzer):
    df_m5 = analyzer.get_m5_dataframe()
    if len(df_m5) < EMA_SLOW_M5 + 1:
        return 0
    prices = df_m5["close"].tolist()
    multiplier_f = 2 / (EMA_FAST_M5 + 1)
    ema_f = prices[0]
    for p in prices[1:]:
        ema_f = (p - ema_f) * multiplier_f + ema_f
        
    multiplier_s = 2 / (EMA_SLOW_M5 + 1)
    ema_s = prices[0]
    for p in prices[1:]:
        ema_s = (p - ema_s) * multiplier_s + ema_s

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
        
        # РАЗОГРЕВ (WARM-UP)
        start_time = datetime.now() - timedelta(minutes=300)
        for sym in SYMBOLS:
            gen = self.generators[sym]
            analyzer = self.analyzers[sym]
            for i in range(3000):
                tick = gen.next_tick()
                tick["time"] = start_time + timedelta(seconds=i * 6)
                analyzer.add_tick(tick)

    def update(self):
        for sym in SYMBOLS:
            gen = self.generators[sym]
            analyzer = self.analyzers[sym]
            for _ in range(5):
                tick = gen.next_tick()
                analyzer.add_tick(tick)

            now = datetime.now()
            if self.last_signal_time[sym] and (now - self.last_signal_time[sym]).seconds < 60:
                continue

            trend = get_m5_trend(analyzer)
            if trend == 0:
                continue

            signal, confidence, reason = analyzer.detect_absorption()
            if signal == 0 or signal != trend or confidence < MIN_SIGNAL_CONFIDENCE:
                continue

            self.last_signal_time[sym] = now
            self.signals.append({
                "time": now, "symbol": sym,
                "direction": "CALL" if signal == 1 else "PUT",
                "confidence": confidence, "reason": reason,
                "trend_m5": "UP" if trend == 1 else "DOWN",
            })
            if len(self.signals) > 50:
                self.signals = self.signals[-50:]

# ===== ИНТЕРФЕЙС =====
st.set_page_config(page_title="Signal Engine", layout="wide")
st.title("🎯 SIGNAL CONFLUENCE ENGINE v0.2")

if "engine" not in st.session_state:
    st.session_state.engine = SignalEngine()
engine = st.session_state.engine

engine.update()

with st.sidebar:
    st.header("📊 Статус")
    st.metric("Активов", len(SYMBOLS))
    st.metric("Сигналов", len(engine.signals))
    st.caption(f"Обновлено: {datetime.now().strftime('%H:%M:%S')}")

col_left, col_right = st.columns([3, 2])

with col_left:
    st.subheader("📈 График M1 (EURUSD_otc)")
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
        
        fig.update_layout(height=500, template="plotly_dark", xaxis_rangeslider_visible=False, margin=dict(l=20, r=20, t=30, b=20))
        
        # Исправлено предупреждение Streamlit
        st.plotly_chart(fig, width='stretch')
    else:
        st.info("Ожидание данных...")

with col_right:
    st.subheader("🎯 Сигналы (последние 10)")
    if engine.signals:
        for sig in reversed(engine.signals[-10:]):
            color = "🟢" if sig["direction"] == "CALL" else "🔴"
            st.markdown(f"""
            **{color} {sig['symbol']} — {sig['direction']}**  
            ⏰ `{sig['time'].strftime('%H:%M:%S')}` | Уверенность: **{sig['confidence']*100:.0f}%**  
            📝 _{sig['reason']}_  
            📊 Тренд M5: {sig['trend_m5']}
            ---
            """)
    else:
        st.info("Сигналов пока нет. Система анализирует рынок...")

time.sleep(3)
st.rerun()