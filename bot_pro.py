#!/usr/bin/env python3
import asyncio
import json
import os
import time
import threading
import random
import tkinter as tk
import customtkinter as ctk
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import pandas as pd
from dotenv import load_dotenv

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ================== КОНФИГ ==================
CONFIG_FILE = 'config.json'
with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
    config = json.load(f)

EXCHANGE_IDS = config.get('exchange_ids', ['binance'])
MAIN_EXCHANGE = config.get('main_exchange', 'binance')
TEST_MODE = config.get('test_mode', True)
ASSET_CONFIG = config.get('asset_config', [])

load_dotenv()

bot_running = False
bot_paused = False
trade_count = 0
total_profit = 0.0
loop = asyncio.new_event_loop()

class ProGUI:
    def __init__(self, master):
        self.master = master
        master.title("🚀 Arbitrage Bot PRO 2026")
        master.geometry("1150x750")  # Уже, чтобы не вылезало
        master.minsize(1050, 650)

        # Красивый фон
        self.bg = tk.Canvas(master, highlightthickness=0)
        self.bg.place(x=0, y=0, relwidth=1, relheight=1)
        for i in range(750):
            r = 10
            g = int(70 + i * 0.15)
            b = int(190 + i * 0.06)
            g = max(0, min(255, g))
            b = max(0, min(255, b))
            color = f"#{r:02x}{g:02x}{b:02x}"
            self.bg.create_line(0, i, 1150, i, fill=color)

        self.main_frame = ctk.CTkFrame(master, fg_color="transparent")
        self.main_frame.place(relx=0.5, rely=0.5, anchor="center", relwidth=0.98, relheight=0.96)

        # ========== TOP BAR ==========
        top = ctk.CTkFrame(self.main_frame, height=110, fg_color="#001a33")
        top.pack(fill="x", pady=8, padx=12)
        
        # Заголовок (слева)
        ctk.CTkLabel(top, text="🚀 ARBITRAGE BOT PRO 2026", 
                    font=ctk.CTkFont(size=20, weight="bold"), 
                    text_color="#00D4FF").pack(side="left", padx=15)
        
        # Статус (рядом с заголовком)
        self.status_label = ctk.CTkLabel(top, text="● ОСТАНОВЛЕН", 
                                        font=ctk.CTkFont(size=14, weight="bold"), 
                                        text_color="#FF4444")
        self.status_label.pack(side="left", padx=20)
        
        # ===== КНОПКИ (в отдельном ряду, под заголовком, смещены влево) =====
        btn_row = ctk.CTkFrame(top, fg_color="transparent")
        btn_row.pack(side="bottom", fill="x", pady=8, padx=10)
        
        # СТАРТ
        self.start_btn = ctk.CTkButton(
            btn_row, text="▶ СТАРТ", width=100, height=38, 
            fg_color="#00AA44", hover_color="#00DD66",
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self.start_bot
        )
        self.start_btn.pack(side="left", padx=6)
        
        # ПАУЗА
        self.pause_btn = ctk.CTkButton(
            btn_row, text="⏸ ПАУЗА", width=100, height=38,
            fg_color="#CC8800", hover_color="#EEAA22",
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self.toggle_pause, state="disabled"
        )
        self.pause_btn.pack(side="left", padx=6)
        
        # СТОП
        self.stop_btn = ctk.CTkButton(
            btn_row, text="⏹ СТОП", width=100, height=38,
            fg_color="#CC3333", hover_color="#FF5555",
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self.stop_bot, state="disabled"
        )
        self.stop_btn.pack(side="left", padx=6)

        # ========== TABS ==========
        self.tabview = ctk.CTkTabview(self.main_frame, corner_radius=12)
        self.tabview.pack(fill="both", expand=True, padx=12, pady=8)

        self.tabview.add("📊 Dashboard")
        self.tabview.add("📈 Графики")
        self.tabview.add("📜 История сделок")
        self.tabview.add("💰 Ввод/Вывод")
        self.tabview.add("⚙ Настройки")

        self.build_dashboard()
        self.build_charts()
        self.build_history()
        self.build_funds()
        self.build_settings()

        self.master.after(1000, self.update_gui)

    def build_dashboard(self):
        frame = ctk.CTkFrame(self.tabview.tab("📊 Dashboard"))
        frame.pack(fill="both", expand=True, padx=12, pady=12)
        
        # Верхняя информационная панель
        info_frame = ctk.CTkFrame(frame, fg_color="#0a2a3a")
        info_frame.pack(fill="x", pady=6)
        
        self.trade_count_label = ctk.CTkLabel(info_frame, text="📊 Сделок: 0", 
                                              font=ctk.CTkFont(size=14), text_color="#00FFAA")
        self.trade_count_label.pack(side="left", padx=25, pady=8)
        
        self.profit_label = ctk.CTkLabel(info_frame, text="💰 Прибыль: 0.00 USDT", 
                                        font=ctk.CTkFont(size=14), text_color="#FFDD44")
        self.profit_label.pack(side="left", padx=25, pady=8)
        
        # Текстовое поле
        self.dashboard_text = ctk.CTkTextbox(frame, height=350, font=ctk.CTkFont(size=12))
        self.dashboard_text.pack(fill="both", expand=True, pady=6)
        self.dashboard_text.insert("0.0", "🤖 Бот готов к работе\n\nНажмите СТАРТ для запуска арбитража\n")

    def build_charts(self):
        frame = ctk.CTkFrame(self.tabview.tab("📈 Графики"))
        frame.pack(fill="both", expand=True, padx=12, pady=12)
        ctk.CTkLabel(frame, text="Выберите монету", font=ctk.CTkFont(size=13)).pack(pady=8)
        self.asset_var = ctk.StringVar(value="BTC")
        ctk.CTkOptionMenu(frame, values=["BTC", "ETH", "BNB", "SOL"], 
                         variable=self.asset_var, command=self.draw_chart, width=100).pack(pady=4)

        self.chart_fig = plt.Figure(figsize=(8, 4.5), dpi=100)
        self.chart_canvas = FigureCanvasTkAgg(self.chart_fig, frame)
        self.chart_canvas.get_tk_widget().pack(fill="both", expand=True)
        self.draw_chart()

    def draw_chart(self, *args):
        self.chart_fig.clear()
        ax = self.chart_fig.add_subplot(111)
        ax.set_title(f"График {self.asset_var.get()}/USDT", fontsize=11, color='white')
        ax.set_facecolor('#1a1a2e')
        ax.text(0.5, 0.5, "Симуляция\n(реальные данные позже)", 
                ha='center', va='center', fontsize=11, alpha=0.7, color='white')
        ax.tick_params(colors='white')
        self.chart_canvas.draw()

    def build_history(self):
        frame = ctk.CTkFrame(self.tabview.tab("📜 История сделок"))
        frame.pack(fill="both", expand=True, padx=12, pady=12)
        self.history_text = ctk.CTkTextbox(frame, font=ctk.CTkFont(size=12))
        self.history_text.pack(fill="both", expand=True)
        self.history_text.insert("0.0", "📋 Здесь будут появляться совершённые сделки...\n")

    def build_funds(self):
        frame = ctk.CTkFrame(self.tabview.tab("💰 Ввод/Вывод"))
        frame.pack(fill="both", expand=True, padx=12, pady=12)
        ctk.CTkLabel(frame, text="💰 Управление средствами", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=15)
        ctk.CTkLabel(frame, text="Функция ввода и вывода в разработке", font=ctk.CTkFont(size=13)).pack(pady=8)

    def build_settings(self):
        frame = ctk.CTkFrame(self.tabview.tab("⚙ Настройки"))
        frame.pack(fill="both", expand=True, padx=12, pady=12)
        ctk.CTkLabel(frame, text="⚙ НАСТРОЙКИ БОТА", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=12)
        ctk.CTkLabel(frame, text=f"🏦 Главная биржа: {MAIN_EXCHANGE.upper()}", font=ctk.CTkFont(size=13)).pack(pady=4)
        ctk.CTkLabel(frame, text=f"🎮 Режим: {'ТЕСТОВЫЙ (симуляция)' if TEST_MODE else 'РЕАЛЬНЫЙ'}", font=ctk.CTkFont(size=13)).pack(pady=4)

    def start_bot(self):
        global bot_running, bot_paused, trade_count, total_profit
        if bot_running and not bot_paused:
            return
        if bot_paused:
            bot_paused = False
            self.status_label.configure(text="● РАБОТАЕТ", text_color="#00FF88")
            self.pause_btn.configure(text="⏸ ПАУЗА", fg_color="#CC8800")
            log("Бот возобновлён")
            return
            
        bot_running = True
        bot_paused = False
        trade_count = 0
        total_profit = 0.0
        self.status_label.configure(text="● РАБОТАЕТ", text_color="#00FF88")
        self.start_btn.configure(state="disabled", fg_color="#555555")
        self.pause_btn.configure(state="normal", fg_color="#CC8800")
        self.stop_btn.configure(state="normal", fg_color="#CC3333")
        self.history_text.delete("0.0", "end")
        self.history_text.insert("0.0", "📋 Запуск бота...\n\n")
        log("🚀 Бот запущен — симуляция арбитража активна")
        threading.Thread(target=self.simulation_loop, daemon=True).start()

    def toggle_pause(self):
        global bot_paused
        if not bot_running:
            return
        bot_paused = not bot_paused
        if bot_paused:
            self.status_label.configure(text="⏸ ПАУЗА", text_color="#FFAA00")
            self.pause_btn.configure(text="▶ ПРОДОЛЖИТЬ", fg_color="#00AA44")
            log("⏸ Бот на паузе")
        else:
            self.status_label.configure(text="● РАБОТАЕТ", text_color="#00FF88")
            self.pause_btn.configure(text="⏸ ПАУЗА", fg_color="#CC8800")
            log("▶ Бот продолжает работу")

    def stop_bot(self):
        global bot_running, bot_paused
        bot_running = False
        bot_paused = False
        self.status_label.configure(text="● ОСТАНОВЛЕН", text_color="#FF4444")
        self.start_btn.configure(state="normal", fg_color="#00AA44")
        self.pause_btn.configure(state="disabled", text="⏸ ПАУЗА", fg_color="#CC8800")
        self.stop_btn.configure(state="disabled", fg_color="#CC3333")
        log("⏹ Бот остановлен")

    def simulation_loop(self):
        global trade_count, total_profit, bot_running, bot_paused
        while bot_running:
            if bot_paused:
                time.sleep(1)
                continue
            time.sleep(random.uniform(5, 15))
            if not bot_running or bot_paused:
                continue
            profit = round(random.uniform(0.5, 3.8), 4)
            total_profit += profit
            trade_count += 1
            asset = random.choice(["BTC", "ETH", "BNB", "SOL"])
            
            log_text = f"✅ СДЕЛКА #{trade_count} | {asset}/USDT | ПРИБЫЛЬ: +{profit} USDT"
            self.add_to_history(log_text)
            log(log_text)
            self.master.after(0, self.update_stats)

    def add_to_history(self, text):
        if hasattr(self, 'history_text'):
            self.history_text.insert("end", text + "\n")
            self.history_text.see("end")

    def update_stats(self):
        if hasattr(self, 'trade_count_label'):
            self.trade_count_label.configure(text=f"📊 Сделок: {trade_count}")
            self.profit_label.configure(text=f"💰 Прибыль: {total_profit:.4f} USDT")

    def update_gui(self):
        if hasattr(self, 'dashboard_text') and bot_running:
            text = f"🏦 ГЛАВНАЯ БИРЖА: {MAIN_EXCHANGE.upper()}\n"
            text += f"🎮 СТАТУС: {'РАБОТАЕТ' if bot_running and not bot_paused else 'ПАУЗА' if bot_paused else 'ОСТАНОВЛЕН'}\n"
            text += f"📊 СОВЕРШЕНО СДЕЛОК: {trade_count}\n"
            text += f"💰 ОБЩАЯ ПРИБЫЛЬ: {total_profit:.6f} USDT\n\n"
            text += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            text += "📌 ЦЕЛЕВЫЕ АКТИВЫ ДЛЯ НАКОПЛЕНИЯ:\n"
            for asset in ASSET_CONFIG:
                target = config.get('target_asset_amount', {}).get(asset.get('asset'), 0)
                text += f"   • {asset.get('asset')}: цель {target}\n"
            text += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            self.dashboard_text.delete("0.0", "end")
            self.dashboard_text.insert("0.0", text)
        self.master.after(2000, self.update_gui)

def log(message):
    timestamp = time.strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}")

def main():
    threading.Thread(target=lambda: asyncio.set_event_loop(loop) or loop.run_forever(), daemon=True).start()
    root = ctk.CTk()
    gui = ProGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()