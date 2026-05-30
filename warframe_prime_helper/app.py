"""GUI 主程序 — 业务逻辑已接入 warframe_prime_helper 包。"""

import json
import os
import threading
import time

import customtkinter as ctk
import keyboard
import pygame
import requests
import tkinter as tk
from PIL import Image, ImageGrab
from tkinter import messagebox

from warframe_prime_helper import __version__
from warframe_prime_helper.config import AppConfig
from warframe_prime_helper.constants import ITEMS_DICT_FILE, QR_IMAGE_PATH, THEME
from warframe_prime_helper.dictionary import ItemDictionary
from warframe_prime_helper.ocr_candidates import build_ocr_candidates
from warframe_prime_helper.ocr_engine import create_ocr_with_timeout, run_ocr
from warframe_prime_helper.part_matcher import PartMatcher
from warframe_prime_helper.paths import get_sound_dir, resource_path
from warframe_prime_helper.price_service import PriceService
from warframe_prime_helper.scan_pipeline import ScanPipeline
from warframe_prime_helper.text import normalize_text
from warframe_prime_helper.win_capture import CaptureService

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("dark-blue")

class WFPriceHelperApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(f"Warframe 开核桃助手 [v{__version__}]")
        self.geometry("520x700")
        self.minsize(500, 800)
        self.configure(fg_color=THEME["bg"]) 

        self.sync_running = False
        self.hotkey_registered = None
        self.init_state = "loading"
        self.init_error = ""
        self.is_ready = False
        self.init_lock = threading.Lock()

        self.app_config = AppConfig()
        self.config = self.app_config.data
        self.prices = PriceService(proxy=self.config.get("proxy", ""))
        self.prices.set_mode("fast")
        self.dictionary = ItemDictionary()
        self.parts = PartMatcher()
        self.capture = CaptureService(fallback_bbox=self.config.get("bbox"))
        self.pipeline = ScanPipeline(self.dictionary, self.parts, self.prices)
        self.price_mode = "fast"

        # 2. 初始化音效
        pygame.mixer.init()
        self.current_sound = None
        self.sound_files = []
        self.scan_sound_files()
        self.load_custom_sound() 
        
        # 3. 鏋勫缓鐣岄潰
        self.setup_ui()
        self.set_price_mode("fast")
        self.register_hotkey(self.config["hotkey"])
        self.log("正在初始化系统...")
        threading.Thread(target=self.init_resources, daemon=True).start()
        self.start_sync_task()

    def save_config(self):
        self.app_config.data = self.config
        self.app_config.save()

    # ====== 音频功能 ======
    
    def scan_sound_files(self):
        self.sound_files = ["default"]
        sound_dir = get_sound_dir()
        if os.path.exists(sound_dir):
            for f in os.listdir(sound_dir):
                if f.lower().endswith(('.mp3', '.wav', '.ogg')):
                    self.sound_files.append(f)

    def load_custom_sound(self):
        filename = self.config.get("sound_file", "default")
        volume = self.config.get("sound_volume", 0.5)
        
        if filename == "default":
            self.current_sound = None
            return

        full_path = os.path.join(get_sound_dir(), filename)
        
        if os.path.exists(full_path):
            try:
                self.current_sound = pygame.mixer.Sound(full_path)
                self.current_sound.set_volume(volume)
            except Exception as e:
                self.log(f"音效加载失败: {e}")
                self.current_sound = None 
        else:
            self.current_sound = None

    def play_trigger_sound(self):
        if self.current_sound:
            self.current_sound.play()
        else:
            try:
                import winsound
                winsound.Beep(1000, 100)
            except:
                pass

    # ====== 鐣岄潰鍥炶皟鍑芥暟 ======

    normalize_text = staticmethod(normalize_text)

    def register_hotkey(self, hotkey):
        try:
            if self.hotkey_registered:
                keyboard.remove_hotkey(self.hotkey_registered)
        except:
            pass

        try:
            keyboard.add_hotkey(hotkey, self.on_hotkey)
            self.hotkey_registered = hotkey
            return True
        except Exception as e:
            self.hotkey_registered = None
            self.log(f"❌ 热键注册失败: {e}")
            return False

    def update_hotkey(self):
        new_hk = self.entry_hotkey.get().strip()
        try:
            if self.register_hotkey(new_hk):
                self.config['hotkey'] = new_hk
                self.save_config()
                self.log(f"✅ 热键更新为: {new_hk}")
            else:
                self.log("❌ 热键格式错误")
        except:
            self.log("❌ 热键格式错误")

    def update_bbox(self):
        try:
            vals = [int(e.get()) for e in self.bbox_entries]
            self.config['bbox'] = vals
            self.save_config()
            self.log(f"✅ 范围已保存: {vals}")
        except:
            self.log("❌ 坐标必须是整数")

    def get_capture_bbox(self):
        return self.capture.get_bbox(
            on_monitor_locked=lambda idx: self.log(f"🖥 已锁定截图屏幕: {idx + 1}")
        )

    def update_proxy(self):
        proxy = self.entry_proxy.get().strip()
        self.config['proxy'] = proxy
        self.prices.set_proxy(proxy)
        self.save_config()
        self.log("✅ 代理配置已保存")
        self.start_sync_task()

    def update_volume(self, value):
        self.config["sound_volume"] = float(value)
        if self.current_sound:
            self.current_sound.set_volume(float(value))
        self.save_config()

    def change_sound(self, choice):
        self.config["sound_file"] = choice
        self.save_config()
        self.load_custom_sound()
        self.log(f"🔔 音效已切换: {choice}")
        self.play_trigger_sound()

    def refresh_sounds(self):
        self.scan_sound_files()
        self.combo_sound.configure(values=self.sound_files)
        current = self.config.get("sound_file", "default")
        if current not in self.sound_files:
            current = "default"
            self.config["sound_file"] = "default"
            self.save_config()
        self.combo_sound.set(current)
        self.log("📁 音效列表已刷新")

    def select_sound_file(self):
        self.log("📂 请把音频文件放进 sound 文件夹，再点击刷新。")
        try:
            os.startfile(get_sound_dir())
        except:
            pass

    def update_wfm_dict(self):
        def _update_task():
            self.update_status("更新字典中...")
            try:
                proxy = self.config.get("proxy", "")
                count = self.dictionary.update_from_wfm(proxy=proxy, log=self.log)
                self.dictionary.load()
                self.log(f"✅ 字典已热加载，当前 {count} 个 Prime 本体")
                self.update_status("字典已更新")
                messagebox.showinfo("成功", f"字典已更新至最新版\n共收录 {count} 个物品")
            except Exception as e:
                self.log(f"❌ 更新错误: {e}")
                self.update_status("更新失败")

        if messagebox.askyesno(
            "更新字典",
            "从 Warframe Market 下载最新 Prime 列表并覆盖 items.json？\n"
            "（游戏版本更新后若识别不到新甲，请先点此更新）\n"
            "可能需要几十秒；失败请在设置中填写代理后重试。",
        ):
            threading.Thread(target=_update_task, daemon=True).start()

    def show_tutorial(self):
        try:
            top = ctk.CTkToplevel(self)
            top.title("使用说明")
            top.geometry("500x550")
            top.attributes("-topmost", True) 
            text_area = ctk.CTkTextbox(top, font=("微软雅黑", 13), activate_scrollbars=True)
            text_area.pack(fill="both", expand=True, padx=15, pady=15)
            
            tutorial_content = """
【快速上手】
1. 游戏建议使用无边框窗口模式；程序会自动识别游戏所在屏幕并截图，多屏场景也可自动切换；
一般来说无需注意。
3. 按下快捷键（默认 =）。
4. 等待 1-2 秒，左侧会弹出价格结果。

【模式选择】
1. 极速模式：提前加载Wfinfo的价格数据，查询时间约1秒。
2. 实时模式：识别到物品后再向Warframe Market查询物品价格，总查询时间首先与网络状况有关，其次与物品数量有关，若极速模式可用，不推荐使用本模式。

【均价算法】
均价=Warframe Market内该物品卖价去掉最低价后的最低五位的平均数

【自定义音效】
1. 软件目录下会自动生成 sound 文件夹。
2. 把 MP3 / WAV / OGG 放进该文件夹。
3. 点击界面里的「刷新」按钮。
4. 在下拉框里切换并试听。


【同步说明】
程序启动后会自动同步市场缓存，代理变更后会自动重试同步。
            """
            text_area.insert("0.0", tutorial_content)
            text_area.configure(state="disabled") 
        except: pass

    def show_donate_qr(self):
        try:
            top = ctk.CTkToplevel(self)
            top.title("感谢支持")
            top.geometry("300x380")
            top.attributes("-topmost", True) 
            img_path = resource_path(QR_IMAGE_PATH)
            if not os.path.exists(img_path): return
            pil_image = Image.open(img_path)
            my_image = ctk.CTkImage(light_image=pil_image, dark_image=pil_image, size=(250, 250))
            ctk.CTkLabel(top, image=my_image, text="").pack(pady=(20, 10))
            ctk.CTkLabel(top, text="欢迎扫码支持", font=("微软雅黑", 12)).pack()
        except: pass

    def log(self, msg):
        self.after(0, lambda: self._log_thread_safe(msg))

    def _log_thread_safe(self, msg):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"{msg}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _set_init_state(self, state, error=""):
        with self.init_lock:
            self.init_state = state
            self.init_error = error
            self.is_ready = (state == "ready")

    def set_price_mode(self, mode, log_change=False):
        if mode not in ("fast", "live"):
            return
        self.price_mode = mode
        self.prices.set_mode(mode)
        mode_text = "极速模式" if mode == "fast" else "实时模式"
        mode_color = THEME["gold"] if mode == "fast" else THEME["live_text"]

        if hasattr(self, "mode_value_label"):
            self.mode_value_label.configure(text=mode_text, text_color=mode_color)
        if hasattr(self, "mode_toggle_btn"):
            self.mode_toggle_btn.configure(text="切到实时" if mode == "fast" else "切到极速")
        if log_change:
            self.log(f"🎛 已切换为{mode_text}")

    def toggle_price_mode(self):
        next_mode = "live" if self.price_mode == "fast" else "fast"
        self.set_price_mode(next_mode, log_change=True)
        self.update_status(f"当前{ '实时模式' if next_mode == 'live' else '极速模式' }")
        if next_mode == "fast":
            self.log("📡 切换到极速模式，正在重新同步价格库...")
            self.start_sync_task()

    def update_status(self, msg):
        self.after(0, lambda: self.status_label.configure(text=msg))

    def start_sync_task(self):
        if self.sync_running:
            self.log("⏳ 价格库同步进行中，请稍候...")
            return
        self.progress_bar.set(0)
        self.progress_bar.configure(progress_color=THEME["progress_fill"])
        self.progress_bar.pack(fill="x", padx=15, pady=(15, 0), before=self.header_frame)
        self.progress_label = ctk.CTkLabel(self, text="正在准备同步...", font=("Arial", 11), text_color="gray")
        self.progress_label.pack(fill="x", padx=15, pady=(2, 5), before=self.header_frame)
        
        self.sync_running = True
        self.target_progress = 0.0
        self.current_progress = 0.0
        
        threading.Thread(target=self.smooth_animation_loop, daemon=True).start()
        threading.Thread(target=self.download_price_table_smart, daemon=True).start()

    def update_sync_text(self, text):
        try: self.after(0, lambda: self.progress_label.configure(text=text))
        except: pass

    def smooth_animation_loop(self):
        self.target_progress = 0.2
        self.update_sync_text("正在连接云端服务...")
        
        while self.sync_running:
            if self.target_progress < 0.85:
                self.target_progress += 0.002
            
            if 0.3 < self.current_progress < 0.6:
                self.update_sync_text("正在下载 WFInfo 价格表...")
            elif self.current_progress > 0.6:
                self.update_sync_text("正在解析数据...")

            diff = self.target_progress - self.current_progress
            if diff > 0.001:
                self.current_progress += diff * 0.1
                self.update_progress(self.current_progress)
            
            time.sleep(0.03)

    def update_progress(self, value):
        try: self.after(0, lambda: self.progress_bar.set(value))
        except: pass

    def finish_progress(self, success=True):
        self.sync_running = False
        
        def _finish_anim():
            current = self.current_progress
            while current < 1.0:
                current += (1.05 - current) * 0.2
                self.update_progress(min(1.0, current))
                time.sleep(0.03)
            
            self.update_progress(1.0)
            
            if success:
                self.update_sync_text("✅ 同步完成")
                self.update_status("价格库已同步")
                time.sleep(1.2)
                self.after(0, lambda: self.progress_bar.pack_forget())
                self.after(0, lambda: self.progress_label.pack_forget())
            else:
                self.after(0, lambda: self.progress_bar.configure(progress_color=THEME["progress_err"]))
                self.update_sync_text("❌ 同步失败，可切换实时模式")
                self.update_status("同步失败")
                time.sleep(3.0)
                self.after(0, lambda: self.progress_bar.pack_forget())
                self.after(0, lambda: self.progress_label.pack_forget())

        threading.Thread(target=_finish_anim, daemon=True).start()

    def download_price_table_smart(self):
        success = self.prices.sync_wfinfo_prices(log=self.log)
        self.finish_progress(success)

    # ====== 界面构建 ======
    def setup_ui(self):
        self.progress_bar = ctk.CTkProgressBar(
            self,
            height=12,
            corner_radius=999,
            fg_color=THEME["progress_bg"],
            progress_color=THEME["progress_fill"],
            border_width=0
        )
        self.progress_bar.set(0)
        self.progress_bar.pack(fill="x", padx=24, pady=(14, 8))

        self.header_frame = ctk.CTkFrame(
            self,
            fg_color=THEME["card_bg"],
            corner_radius=18,
            border_width=1,
            border_color=THEME["panel_border"]
        )
        self.header_frame.pack(fill="x", padx=20, pady=(0, 10))

        ctk.CTkLabel(
            self.header_frame,
            text="WARFRAME PRIME SCAN",
            font=("Segoe UI", 12, "bold"),
            text_color=THEME["live_text"]
        ).pack(anchor="w", padx=18, pady=(14, 0))
        ctk.CTkLabel(
            self.header_frame,
            text="开核桃助手 V5.4.1",
            font=("微软雅黑", 26, "bold"),
            text_color=THEME["text"]
        ).pack(anchor="w", padx=18, pady=(2, 0))
        ctk.CTkLabel(
            self.header_frame,
            text="一键识别遗物奖励，极速给出市场价格。",
            font=("微软雅黑", 12),
            text_color=THEME["muted"]
        ).pack(anchor="w", padx=18, pady=(2, 10))
        ctk.CTkLabel(
            self.header_frame,
            text="by RanAway22",
            font=("Segoe UI", 11, "bold"),
            text_color=THEME["gold"]
        ).pack(anchor="w", padx=18, pady=(0, 10))

        status_chip = ctk.CTkFrame(
            self.header_frame,
            fg_color=THEME["input_bg"],
            corner_radius=999,
            border_width=1,
            border_color=THEME["panel_border"]
        )
        status_chip.pack(anchor="e", padx=14, pady=(0, 12))
        self.status_label = ctk.CTkLabel(status_chip, text="Initializing...", text_color=THEME["gold"], font=("Consolas", 11, "bold"))
        self.status_label.grid(row=0, column=0, padx=(10, 8), pady=4)
        ctk.CTkLabel(status_chip, text="模式:", font=("微软雅黑", 11), text_color=THEME["muted"]).grid(row=0, column=1, padx=(0, 4), pady=4)
        self.mode_value_label = ctk.CTkLabel(status_chip, text="极速模式", text_color=THEME["gold"], font=("微软雅黑", 11, "bold"))
        self.mode_value_label.grid(row=0, column=2, padx=(0, 8), pady=4)
        self.mode_toggle_btn = ctk.CTkButton(
            status_chip,
            text="切到实时",
            width=74,
            height=24,
            corner_radius=999,
            fg_color=THEME["info_btn"],
            hover_color=THEME["info_hover"],
            font=("微软雅黑", 10, "bold"),
            command=self.toggle_price_mode
        )
        self.mode_toggle_btn.grid(row=0, column=3, padx=(0, 8), pady=4)

        action_row = ctk.CTkFrame(
            self,
            fg_color=THEME["card_bg"],
            corner_radius=12,
            border_width=1,
            border_color=THEME["panel_border"]
        )
        action_row.pack(fill="x", padx=20, pady=(2, 10))
        action_row.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkButton(
            action_row,
            text="📘 新手教程",
            height=40,
            corner_radius=12,
            fg_color=THEME["info_btn"],
            hover_color=THEME["info_hover"],
            font=("微软雅黑", 13, "bold"),
            command=self.show_tutorial
        ).grid(row=0, column=0, padx=(10, 6), pady=10, sticky="ew")
        ctk.CTkButton(
            action_row,
            text="☕ 支持作者",
            height=40,
            corner_radius=12,
            fg_color=THEME["gold"],
            hover_color=THEME["gold_hover"],
            text_color="#111111",
            font=("微软雅黑", 13, "bold"),
            command=self.show_donate_qr
        ).grid(row=0, column=1, padx=(6, 10), pady=10, sticky="ew")

        ctk.CTkLabel(self, text="控制台设置", font=("微软雅黑", 14, "bold"), text_color=THEME["live_text"]).pack(anchor="w", padx=24, pady=(0, 6))

        self.settings_frame = ctk.CTkFrame(
            self,
            fg_color=THEME["card_bg"],
            corner_radius=14,
            border_width=1,
            border_color=THEME["panel_border"]
        )
        self.settings_frame.pack(fill="x", padx=20, pady=2)
        self.settings_frame.grid_columnconfigure(1, weight=1)

        label_font = ("微软雅黑", 13)
        input_font = ("Consolas", 12)
        input_style = {
            "fg_color": THEME["input_bg"],
            "border_color": THEME["panel_border"],
            "text_color": THEME["text"],
            "font": input_font,
            "height": 34
        }
        action_btn_style = {
            "width": 88,
            "height": 34,
            "corner_radius": 10,
            "fg_color": THEME["gold"],
            "hover_color": THEME["gold_hover"],
            "text_color": "#0b0f1a",
            "font": ("微软雅黑", 12, "bold")
        }

        ctk.CTkLabel(self.settings_frame, text="触发热键", font=label_font, text_color=THEME["text"]).grid(row=0, column=0, padx=14, pady=10, sticky="w")
        self.entry_hotkey = ctk.CTkEntry(self.settings_frame, **input_style)
        self.entry_hotkey.insert(0, self.config['hotkey'])
        self.entry_hotkey.grid(row=0, column=1, padx=8, sticky="ew")
        ctk.CTkButton(self.settings_frame, text="应用", command=self.update_hotkey, **action_btn_style).grid(row=0, column=2, padx=10)

        ctk.CTkLabel(self.settings_frame, text="截图屏幕", font=label_font, text_color=THEME["text"]).grid(row=1, column=0, padx=14, pady=10, sticky="w")
        ctk.CTkLabel(
            self.settings_frame,
            text="自动检测游戏所在屏幕（多屏环境可自动切换）",
            font=("微软雅黑", 11),
            text_color=THEME["muted"]
        ).grid(row=1, column=1, sticky="w", padx=8)
        ctk.CTkButton(self.settings_frame, text="重检", command=lambda: self.log("🧭 下次截图时将重新锁定屏幕"), **action_btn_style).grid(row=1, column=2, padx=10)

        ctk.CTkLabel(self.settings_frame, text="本地代理", font=label_font, text_color=THEME["text"]).grid(row=2, column=0, padx=14, pady=10, sticky="w")
        self.entry_proxy = ctk.CTkEntry(self.settings_frame, placeholder_text="留空使用直连或云加速", **input_style)
        self.entry_proxy.insert(0, self.config.get('proxy', ''))
        self.entry_proxy.grid(row=2, column=1, padx=8, sticky="ew")
        ctk.CTkButton(self.settings_frame, text="保存", command=self.update_proxy, **action_btn_style).grid(row=2, column=2, padx=10)

        ctk.CTkLabel(self.settings_frame, text="提示音效", font=label_font, text_color=THEME["text"]).grid(row=3, column=0, padx=14, pady=10, sticky="w")
        sound_frame = ctk.CTkFrame(self.settings_frame, fg_color="transparent")
        sound_frame.grid(row=3, column=1, padx=8, sticky="ew")
        sound_frame.grid_columnconfigure(0, weight=1)
        self.combo_sound = ctk.CTkComboBox(
            sound_frame,
            values=self.sound_files,
            command=self.change_sound,
            fg_color=THEME["input_bg"],
            border_color=THEME["panel_border"],
            button_color=THEME["info_btn"],
            button_hover_color=THEME["info_hover"],
            dropdown_fg_color=THEME["card_bg"],
            dropdown_hover_color=THEME["input_bg"],
            dropdown_text_color=THEME["text"],
            font=input_font,
            height=34
        )
        self.combo_sound.set(self.config.get("sound_file", "default"))
        self.combo_sound.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(
            sound_frame,
            text="刷新",
            width=60,
            height=34,
            corner_radius=10,
            fg_color="transparent",
            hover_color=THEME["input_bg"],
            border_width=1,
            border_color=THEME["panel_border"],
            command=self.refresh_sounds
        ).grid(row=0, column=1, padx=(6, 0))
        ctk.CTkButton(self.settings_frame, text="打开目录", command=lambda: os.startfile(get_sound_dir()), **action_btn_style).grid(row=3, column=2, padx=10)

        ctk.CTkLabel(self.settings_frame, text="音量调节", font=label_font, text_color=THEME["text"]).grid(row=4, column=0, padx=14, pady=10, sticky="w")
        vol_f = ctk.CTkFrame(self.settings_frame, fg_color="transparent")
        vol_f.grid(row=4, column=1, columnspan=2, sticky="ew", padx=8, pady=(0, 8))
        vol_f.grid_columnconfigure(0, weight=1)
        self.slider_volume = ctk.CTkSlider(
            vol_f,
            from_=0,
            to=1,
            number_of_steps=100,
            command=self.update_volume,
            progress_color=THEME["live_text"],
            button_color=THEME["gold"],
            button_hover_color=THEME["gold_hover"]
        )
        self.slider_volume.set(self.config.get("sound_volume", 0.5))
        self.slider_volume.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ctk.CTkButton(vol_f, text="🔊 试听", command=self.play_trigger_sound, **action_btn_style).grid(row=0, column=1)

        ctk.CTkLabel(self.settings_frame, text="物品字典", font=label_font, text_color=THEME["text"]).grid(
            row=5, column=0, padx=14, pady=10, sticky="w"
        )
        ctk.CTkLabel(
            self.settings_frame,
            text="游戏更新后若新 Prime 无法识别，点此同步",
            font=("微软雅黑", 11),
            text_color=THEME["muted"],
        ).grid(row=5, column=1, sticky="w", padx=8)
        ctk.CTkButton(
            self.settings_frame,
            text="更新字典",
            command=self.update_wfm_dict,
            **action_btn_style,
        ).grid(row=5, column=2, padx=10)

        ctk.CTkLabel(self, text="运行日志", font=("微软雅黑", 14, "bold"), text_color=THEME["live_text"]).pack(anchor="w", padx=24, pady=(0, 6))
        log_wrap = ctk.CTkFrame(self, fg_color=THEME["card_bg"], corner_radius=12, border_width=1, border_color=THEME["panel_border"])
        log_wrap.pack(fill="both", expand=True, padx=20, pady=0)
        self.log_text = ctk.CTkTextbox(
            log_wrap,
            font=("Consolas", 12),
            activate_scrollbars=True,
            fg_color=THEME["card_bg"],
            border_width=0,
            text_color=THEME["text"]
        )
        self.log_text.pack(fill="both", expand=True, padx=8, pady=8)
        self.log_text.configure(state="disabled")
        ctk.CTkLabel(self, text="Designed for Tenno · RanAway22", font=("Segoe UI", 10, "bold"), text_color=THEME["muted"]).pack(pady=8)

    def init_resources(self):
        try:
            self._set_init_state("loading")
            self.update_status("系统初始化中...")

            ocr, ocr_error = create_ocr_with_timeout(timeout_sec=20)
            if ocr_error:
                self._set_init_state("failed", f"OCR: {ocr_error}")
                self.log(f"❌ OCR 初始化失败: {ocr_error}")
                self.update_status("初始化失败")
                return
            self.ocr = ocr
            self.log("✅ OCR 引擎就绪")
            try:
                count = self.dictionary.load()
            except FileNotFoundError:
                self.log(f"❌ 找不到字典文件: {ITEMS_DICT_FILE}")
                self._set_init_state("failed", f"缺少字典文件: {ITEMS_DICT_FILE}")
                self.update_status("初始化失败")
                return
            self.log(f"📖 字典加载: {count} 条目")
            if count == 0:
                self._set_init_state("failed", "字典为空或格式不匹配")
                self.log("❌ 字典为空或格式不匹配")
                self.update_status("初始化失败")
                return

            self._set_init_state("ready")

            self.log(f"🚀 等待指令 (按 {self.config['hotkey']})")
            self.update_status("系统就绪")
        except Exception as e:
            self._set_init_state("failed", str(e))
            self.log(f"❌ 初始化失败: {e}")
            self.update_status("初始化失败")

    def on_hotkey(self):
        with self.init_lock:
            is_ready = self.is_ready
            init_state = self.init_state
            init_error = self.init_error

        if not is_ready:
            if init_state == "failed":
                self.log(f"❌ 系统初始化失败: {init_error}")
                self.log("🔄 正在尝试重新初始化...")
                self._set_init_state("loading")
                self.update_status("重试初始化中...")
                threading.Thread(target=self.init_resources, daemon=True).start()
            else:
                self.log("⏳ 系统加载中...")
            return
        self.play_trigger_sound()
        self.update_status("扫描中...")
        threading.Thread(target=self.process_screenshot, daemon=True).start()

    def show_overlay(self, title, content, is_fast, index=0, sub_content=None):
        def _show():
            top = tk.Toplevel(self)
            top.overrideredirect(True)
            top.attributes('-topmost', True)
            top.attributes('-alpha', 0.90) 
            top.config(bg=THEME["bg"]) 

            has_sub = bool(sub_content)
            win_w, win_h = 460, (145 if has_sub else 120)
            screen_h = self.winfo_screenheight()
            step = 155 if has_sub else 130
            start_y = (screen_h // 2) - 180 + (index * step)
            
            hidden_x = -win_w - 20 
            target_x = 30 
            top.geometry(f"{win_w}x{win_h}+{hidden_x}+{int(start_y)}")

            main_frame = tk.Frame(top, bg=THEME["card_bg"])
            main_frame.pack(fill="both", expand=True, padx=2, pady=2)

            strip = tk.Frame(main_frame, bg=THEME["gold"], width=10)
            strip.pack(side="left", fill="y")

            right_frame = tk.Frame(main_frame, bg=THEME["input_bg"], width=112)
            right_frame.pack(side="right", fill="y", padx=(0, 2), pady=2)
            right_frame.pack_propagate(False)

            content_frame = tk.Frame(main_frame, bg=THEME["card_bg"], padx=16, pady=6)
            content_frame.pack(side="left", fill="both", expand=True)
            
            tk.Label(content_frame, text=title, fg=THEME["gold"], bg=THEME["card_bg"], 
                     font=("微软雅黑", 17, "bold"), anchor="w").pack(fill="x", pady=(6, 4))
            
            text_color = THEME["fast_text"] if is_fast else THEME["live_text"]
            tk.Label(content_frame, text=content, fg=text_color, bg=THEME["card_bg"], 
                     font=("Segoe UI", 16, "bold"), anchor="w").pack(fill="x", pady=(0, 6))
            if has_sub:
                tk.Label(
                    content_frame,
                    text=sub_content,
                    fg=THEME["muted"],
                    bg=THEME["card_bg"],
                    font=("微软雅黑", 12),
                    anchor="w"
                ).pack(fill="x", pady=(0, 4))

            mode_text = "极速" if is_fast else "实时"
            mode_color = THEME["fast_text"] if is_fast else THEME["live_text"]

            tk.Label(
                right_frame,
                text="模式",
                fg=THEME["muted"],
                bg=THEME["input_bg"],
                font=("微软雅黑", 10)
            ).pack(anchor="center", pady=(14, 2))
            tk.Label(
                right_frame,
                text=mode_text,
                fg=mode_color,
                bg=THEME["input_bg"],
                font=("微软雅黑", 13, "bold")
            ).pack(anchor="center", pady=(0, 10))

            tk.Frame(right_frame, bg=THEME["panel_border"], height=1).pack(fill="x", padx=10, pady=(0, 8))

            tk.Label(
                right_frame,
                text="来源",
                fg=THEME["muted"],
                bg=THEME["input_bg"],
                font=("微软雅黑", 10)
            ).pack(anchor="center")
            tk.Label(
                right_frame,
                text="Warframe\nMarket",
                fg=THEME["text"],
                bg=THEME["input_bg"],
                font=("Segoe UI", 10, "bold"),
                justify="center"
            ).pack(anchor="center", pady=(2, 0))

            anim_data = {"curr_x": hidden_x, "state": "in", "velocity": 40}

            def animate():
                try:
                    if not top.winfo_exists(): return
                    if anim_data["state"] == "in":
                        dist = target_x - anim_data["curr_x"]
                        if dist > 1:
                            move = max(dist * 0.15, 2) 
                            anim_data["curr_x"] += move
                            top.geometry(f"{win_w}x{win_h}+{int(anim_data['curr_x'])}+{int(start_y)}")
                            top.after(10, animate)
                        else:
                            anim_data["curr_x"] = target_x
                            top.geometry(f"{win_w}x{win_h}+{int(anim_data['curr_x'])}+{int(start_y)}")
                            anim_data["state"] = "wait"
                            top.after(9500, animate) 

                    elif anim_data["state"] == "wait":
                        anim_data["state"] = "out"
                        animate()

                    elif anim_data["state"] == "out":
                        dist = anim_data["curr_x"] - hidden_x
                        if dist > 1:
                            move = max(dist * 0.15, 2)
                            anim_data["curr_x"] -= move
                            top.geometry(f"{win_w}x{win_h}+{int(anim_data['curr_x'])}+{int(start_y)}")
                            top.after(10, animate)
                        else:
                            top.destroy()
                except:
                    pass

            top.after(10, animate)
        self.after(0, _show)

    def process_screenshot(self):
        bbox = self.get_capture_bbox()
        self.log(f"\n📸 正在扫描区域: {bbox}")
        try:
            try:
                img = ImageGrab.grab(bbox=bbox, all_screens=True)
            except TypeError:
                img = ImageGrab.grab(bbox=bbox)
            result, _ = run_ocr(self.ocr, img)

            if not result:
                self.log("⚠️ 画面无文字")
                return

            candidates = build_ocr_candidates(result)
            matches = self.pipeline.scan_candidates(candidates, log=self.log)

            for i, match in enumerate(matches):
                self.show_overlay(
                    match.final_name,
                    match.price_str,
                    match.is_fast,
                    index=i,
                    sub_content=match.set_price_str,
                )

            msg = f"完成 (找到 {len(matches)} 个)" if matches else "未匹配到物品"
            self.update_status(msg)
            self.log(msg)
        except Exception as e:
            self.log(f"❌ Error: {e}")


def main():
    app = WFPriceHelperApp()
    app.protocol("WM_DELETE_WINDOW", lambda: (keyboard.unhook_all(), app.destroy()))
    app.mainloop()


if __name__ == "__main__":
    main()

