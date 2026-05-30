import os
import sys
import shutil


def _prepare_native_dll_paths() -> None:
    """单文件 exe 解压后，确保 onnxruntime 等原生 DLL 可被加载。"""
    if not getattr(sys, "frozen", False):
        return
    base = getattr(sys, "_MEIPASS", "")
    if not base:
        return
    # numpy.libs 自带的 MSVCP140 若优先加载会导致 onnxruntime.dll 初始化失败 (WinError 1114)
    dirs = [
        os.path.join(base, "onnxruntime", "capi"),
        os.path.join(base, "cv2"),
        os.path.join(base, "shapely.libs"),
        base,
        os.path.join(base, "numpy.libs"),
    ]
    path_parts = []
    for d in dirs:
        if os.path.isdir(d):
            path_parts.append(d)
            if hasattr(os, "add_dll_directory"):
                try:
                    os.add_dll_directory(d)
                except OSError:
                    pass
    if path_parts:
        os.environ["PATH"] = os.pathsep.join(path_parts) + os.pathsep + os.environ.get(
            "PATH", ""
        )


_prepare_native_dll_paths()

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageGrab, ImageTk
import keyboard
import numpy as np
import requests
import json
import threading
import queue
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib.parse
try:
    from warframe_prime_helper.dictionary import ItemDictionary
except ImportError:
    ItemDictionary = None  # type: ignore
try:
    import pygame
    _HAS_PYGAME = True
except ImportError:
    pygame = None  # type: ignore
    _HAS_PYGAME = False
import re
import unicodedata
import ctypes
from ctypes import wintypes

# ====== 閰嶇疆鍖哄煙 ======
DEFAULT_CONFIG = {
    "hotkey": "alt+q",
    "bbox": [0,0,1920,1080],
    "proxy": "",
    "sound_file": "default",
    "sound_volume": 0.5,
    "last_price_sync": 0,
}
CONFIG_FILE = "config.json"
WFM_DICT_PATH = "items.json"
PRICE_CACHE_FILE = "wfinfo_prices_cache.json"
PRICE_CACHE_TTL_SEC = 2 * 3600
QR_IMAGE_PATH = "qr.png" 
SOUND_DIR = "sound"


def get_app_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def get_data_path(filename: str) -> str:
    """数据文件：优先 exe 同目录（可更新），否则使用打包内资源。"""
    user_path = os.path.join(get_app_dir(), filename)
    if os.path.exists(user_path):
        return user_path
    try:
        bundled = os.path.join(sys._MEIPASS, filename)  # type: ignore[attr-defined]
        if os.path.exists(bundled):
            return bundled
    except Exception:
        pass
    return user_path


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", RECT),
        ("rcWork", RECT),
        ("dwFlags", wintypes.DWORD),
    ]

THEME = {
    "bg": "#070b14", "card_bg": "#101a2f", "text": "#eaf1ff",
    "gold": "#ff9f1c", "gold_hover": "#f18701",
    "fast_text": "#34d399", "live_text": "#38bdf8",
    "info_btn": "#2563eb", "info_hover": "#1d4ed8",
    "progress_bg": "#1f2a44", "progress_fill": "#22d3ee", "progress_err": "#ef4444",
    "panel_border": "#24365b", "input_bg": "#0e1830", "muted": "#92a3c3",
    "highlight": "#ffcc00", "highlight_bg": "#1c2a14",
}

# 同一行里多个部件词时，数值越大越优先（避免「握柄」被「蓝图」盖住）
# 遗物界面常见 Prime 类型（用于限制部件，避免列拼接误判）
_BOW_BASE_HINTS = (
    "daikyu_prime", "cernos_prime", "paris_prime", "zhuge_prime", "attica_prime",
    "britus_prime", "lenko_prime", "quartakk_prime",
)
_MELEE_BASE_HINTS = (
    "venato_prime", "kestrel_prime", "orthos_prime", "gram_prime", "dakra_prime",
    "glaive_prime", "kronen_prime", "tatsu_prime", "nikana_prime", "okina_prime",
    "pangolin_prime", "reaper_prime", "redeemer_prime", "fang_prime", "galatine_prime", "scindo_prime", "broken_prime",
    "silva_prime", "keratinos_prime", "ninkondi_prime", "guandao_prime", "hate_prime", "karyst_prime",
)
_SENTINEL_BASE_HINTS = (
    "carrier_prime", "helios_prime", "shade_prime", "dethcube_prime", "nautilus_prime",
    "djinn_prime", "regard_prime", "prisma_prime",
)
_GUN_BASE_HINTS = (
    "braton_prime", "latron_prime", "boltor_prime", "bronco_prime", "rubico_prime",
    "strun_prime", "tenora_prime", "soma_prime", "synapse_prime", "baza_prime",
    "tigris_prime", "corinth_prime", "vectis_prime", "knell_prime", "phenmor_prime",
    "fulmin_prime", "acceltra_prime", "afuris_prime", "akarius_prime",
    "burston_prime", "trumna_prime",
    "bronco_prime", "akbronco_prime", "lex_prime", "sicarus_prime",
)

VALID_PARTS_BY_KIND = {
    "warframe": frozenset({"neuroptics", "chassis", "systems", "blueprint"}),
    "bow": frozenset({"blueprint", "grip", "string", "limb", "upper_limb", "lower_limb"}),
    "melee": frozenset({"blueprint", "blade", "blades", "handle", "hilt", "gauntlet", "guard", "head", "boot", "ornament", "disc", "chain"}),
    "gun": frozenset({"blueprint", "barrel", "receiver", "stock", "link"}),
    "sentinel": frozenset({"blueprint", "systems", "carapace", "cerebrum", "harness", "wings", "engine", "band", "buckle"}),
    "throwing": frozenset({"blueprint", "stars", "pouch", "chain"}),
}

_ITEMS_PARTS_PATH = "items_1.json"
_SENTINEL_PART_MARKERS = frozenset(
    {"carapace", "cerebrum", "harness", "wings", "pouch", "engine", "band", "buckle"}
)
_WARFRAME_PART_MARKERS = frozenset({"neuroptics", "chassis"})
_GUN_PART_MARKERS = frozenset({"barrel", "receiver", "stock", "link"})
_MELEE_PART_MARKERS = frozenset(
    {"blade", "blades", "handle", "hilt", "gauntlet", "guard", "head", "boot", "chain"}
)
_BOW_PART_MARKERS = frozenset({"grip", "string", "limb", "upper_limb", "lower_limb"})
_THROWING_PART_MARKERS = frozenset({"stars", "chain"})
_KIND_PRIORITY = ("gun", "melee", "bow", "throwing", "sentinel", "warframe", "other")


def _build_prime_kind_map() -> dict[str, frozenset[str]]:
    """从 items_1.json 部件表推导 Prime 基础 url 的类型（避免武器被当成战甲）。"""
    path = get_data_path(_ITEMS_PARTS_PATH)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}

    base_suffixes: dict[str, set[str]] = {}
    part_tokens = (
        "neuroptics_blueprint",
        "chassis_blueprint",
        "systems_blueprint",
        "upper_limb",
        "lower_limb",
        "neuroptics",
        "carapace",
        "cerebrum",
        "receiver",
        "barrel",
        "chassis",
        "systems",
        "harness",
        "gauntlet",
        "guard",
        "head",
        "boot",
        "band",
        "buckle",
        "handle",
        "string",
        "stock",
        "blade",
        "blades",
        "wings",
        "grip",
        "limb",
        "hilt",
        "link",
        "chain",
        "stars",
        "pouch",
        "engine",
        "disc",
        "blueprint",
    )
    for entry in data.values():
        if not isinstance(entry, dict):
            continue
        url = (entry.get("url_name") or "").lower()
        if "_prime" not in url or url.endswith("_set"):
            continue
        matched_suffix = ""
        for suffix in sorted(part_tokens, key=len, reverse=True):
            token = f"_{suffix}"
            if url.endswith(token):
                matched_suffix = suffix
                base = url[: -len(token)]
                break
        else:
            continue
        if not base.endswith("_prime"):
            continue
        if matched_suffix == "blueprint":
            continue
        base_suffixes.setdefault(base, set()).add(matched_suffix)

    mapping: dict[str, set[str]] = {}
    for base, suffixes in base_suffixes.items():
        kinds: set[str] = set()
        sentinel_base = bool(suffixes & _SENTINEL_PART_MARKERS)
        if suffixes & _WARFRAME_PART_MARKERS:
            kinds.add("warframe")
        if suffixes & _GUN_PART_MARKERS:
            kinds.add("gun")
        if suffixes & _MELEE_PART_MARKERS:
            kinds.add("melee")
        if suffixes & _BOW_PART_MARKERS:
            kinds.add("bow")
        if suffixes & _THROWING_PART_MARKERS:
            kinds.add("throwing")
        if suffixes & _SENTINEL_PART_MARKERS and "throwing" not in kinds:
            kinds.add("sentinel")
        if "systems" in suffixes and not sentinel_base:
            kinds.add("warframe")
        elif "systems" in suffixes and sentinel_base:
            kinds.add("sentinel")
        if kinds:
            mapping[base] = kinds
    return {k: frozenset(v) for k, v in mapping.items()}


_PRIME_KIND_MAP = _build_prime_kind_map()


def _kind_for_part_suffix(suffix: str) -> str | None:
    for kind, parts in VALID_PARTS_BY_KIND.items():
        if suffix in parts:
            return kind
    return None

PART_MATCH_PRIORITY = {
    "handle": 90, "hilt": 89, "blade": 88, "blades": 88, "gauntlet": 87, "guard": 86,
    "head": 85, "boot": 84,
    "receiver": 83, "barrel": 82, "stock": 81, "link": 80,
    "grip": 82, "string": 81, "limb": 80, "upper_limb": 79, "lower_limb": 78,
    "neuroptics": 75, "chassis": 74, "systems": 73,
    "harness": 72, "wings": 71, "engine": 70, "carapace": 69, "cerebrum": 68,
    "band": 67, "buckle": 66,
    "stars": 67, "pouch": 66, "chain": 65,
    "disc": 50, "ornament": 49,
    "blueprint": 10, "set": 0,
}

PART_MAP = {
    "蓝图": "blueprint", "总图": "blueprint",
    "机体": "chassis", "系统": "systems", "系统蓝图": "systems",
    "神经光元": "neuroptics", "神经元": "neuroptics", "头部神经元": "neuroptics",
    "头部神经光元": "neuroptics", "视光器": "neuroptics",
    "枪机": "receiver", "枪管": "barrel", "枪托": "stock", "连接器": "link",
    "刀刃": "blade", "刃部": "blade", "握柄": "handle", "握把": "handle", "握图": "handle",
    "handle": "handle", "receiver": "receiver", "barrel": "barrel", "stock": "stock",
    "护手": "gauntlet", "拳套": "gauntlet", "手套": "gauntlet",
    "爪刃": "blades", "锤头": "head", "靴子": "boot",
    "项圈带": "band", "项圈扣": "buckle",
    "圆盘": "disc", "饰物": "ornament",
    "弓身": "grip", "弓臂": "limb", "上弓臂": "upper_limb", "下弓臂": "lower_limb",
    "弓弦": "string", "握把套": "grip",
    "缰绳": "harness", "机翼": "wings", "引擎": "engine",
    "外壳": "carapace", "脑部": "cerebrum", "头部": "cerebrum",
        "星镖": "stars", "镖袋": "pouch", "链条": "chain",
        "项圈带": "band", "项圈扣": "buckle",
    }

SUFFIX_CN_NAME = {
    "blueprint": "蓝图",
    "chassis": "机体",
    "systems": "系统",
    "neuroptics": "神经光元",
    "neuroptics_blueprint": "神经光元蓝图",
    "receiver": "枪机",
    "barrel": "枪管",
    "stock": "枪托",
    "link": "连接器",
    "blade": "刀刃",
    "handle": "握柄",
    "hilt": "握柄",
    "gauntlet": "护手",
    "guard": "护手",
    "blades": "爪刃",
    "head": "锤头",
    "boot": "靴子",
    "band": "项圈带",
    "buckle": "项圈扣",
    "disc": "圆盘",
    "ornament": "饰物",
    "limb": "弓臂",
    "upper_limb": "上弓臂",
    "lower_limb": "下弓臂",
    "string": "弓弦",
    "grip": "弓身",
    "harness": "缰绳",
    "wings": "机翼",
    "engine": "引擎",
    "carapace": "外壳",
    "cerebrum": "脑部",
    "stars": "星镖",
    "pouch": "镖袋",
    "chain": "链条",
}

ctk.set_appearance_mode("Dark") 
ctk.set_default_color_theme("dark-blue")

def resource_path(relative_path):
    user_path = os.path.join(get_app_dir(), relative_path)
    if os.path.exists(user_path):
        return user_path
    try:
        return os.path.join(sys._MEIPASS, relative_path)  # type: ignore[attr-defined]
    except Exception:
        return user_path

def get_sound_dir():
    sound_path = os.path.join(get_app_dir(), SOUND_DIR)
    if not os.path.exists(sound_path):
        try:
            os.makedirs(sound_path)
        except:
            pass
    return sound_path

class WFPriceHelperApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Warframe 开核桃助手 [V5.4.1]")
        self.geometry("520x700")
        self.minsize(500, 800)
        self.configure(fg_color=THEME["bg"]) 

        self.wfinfo_prices = {}
        self._load_price_cache(quiet=True)
        self.price_mode = "fast"
        self.sync_running = False
        self._price_sync_done = False
        self.dict_updating = False
        self.hotkey_registered = None
        self.part_map_entries = []
        self.set_price_cache = {}
        self.init_state = "loading"
        self.init_error = ""
        self.last_capture_monitor = None
        self.is_ready = False
        self.init_lock = threading.Lock()
        
        # 1. 鍔犺浇閰嶇疆
        self.load_config()
        
        # 2. 初始化音效
        if _HAS_PYGAME:
            pygame.mixer.init()
        self.current_sound = None
        self.sound_files = []
        self.scan_sound_files()
        self.load_custom_sound() 
        
        # 3. 鏋勫缓鐣岄潰
        self.setup_ui()
        self._screen_height = self.winfo_screenheight()
        self._log_queue: queue.Queue[str] = queue.Queue()
        self._status_queue: queue.Queue[str] = queue.Queue()
        self._overlay_queue_ui: queue.Queue[dict] = queue.Queue()
        self.after(50, self._drain_ui_queues)
        self.set_price_mode("fast")
        self.register_hotkey(self.config["hotkey"])
        self.part_map_entries = [
            (self.normalize_text(k), v, k)
            for k, v in PART_MAP.items()
        ]
        
        self.log("正在初始化系统...")
        if self.wfinfo_prices:
            self.log(f"📂 已载入本地价格缓存 {len(self.wfinfo_prices)} 条")
        threading.Thread(target=self.init_resources, daemon=True).start()
        self.maybe_start_auto_sync()

    def load_config(self):
        config_path = os.path.join(get_app_dir(), CONFIG_FILE)
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
            except:
                self.config = DEFAULT_CONFIG
        else:
            self.config = DEFAULT_CONFIG
            self.save_config()
        
        defaults = {
            "proxy": "",
            "sound_file": "default",
            "sound_volume": 0.5,
            "last_price_sync": 0,
        }
        for k, v in defaults.items():
            if k not in self.config:
                self.config[k] = v

    def save_config(self):
        try:
            with open(os.path.join(get_app_dir(), CONFIG_FILE), 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4)
        except:
            pass

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
        
        if os.path.exists(full_path) and _HAS_PYGAME:
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

    @staticmethod
    def normalize_text(text):
        if text is None:
            return ""
        s = unicodedata.normalize("NFKC", str(text)).lower()
        for typo, fix in (
            ("握图", "握柄"), ("握东", "握柄"),
            ("统蓝图", "系统蓝图"), ("抢托", "枪托"),
            ("系系统", "系统"),
            ("布菜顿", "布莱顿"),
            ("布菜prime", "布莱顿prime"),
            ("玻之武妆", "玻之武杖"),
            ("prime舒物", "prime饰物"),
        ):
            s = s.replace(typo, fix)
        s = re.sub(r"布菜[顿域球]", "布莱顿", s)
        s = re.sub(r"(?<!蛟)龙prime(?=.*外壳)", "蛟龙prime", s)
        # 保留中文/字母/数字，去掉空格和各类符号，统一 OCR 与字典键格式
        return "".join(ch for ch in s if ch.isalnum() or ("\u4e00" <= ch <= "\u9fff"))

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

    def _pick_part_match(self, matches: list[tuple[str, str, str]]) -> tuple[str, str, str]:
        non_blueprint = [m for m in matches if m[1] != "blueprint"]
        pool = non_blueprint or matches
        return max(
            pool,
            key=lambda m: (len(m[0]), PART_MATCH_PRIORITY.get(m[1], 5)),
        )

    def resolve_part_suffix(self, leftover_text):
        matches = []
        for cn_norm, en, cn_display in self.part_map_entries:
            if cn_norm and cn_norm in leftover_text:
                matches.append((cn_norm, en, cn_display))

        if not matches:
            return "set", ""

        chosen = self._pick_part_match(matches)
        return chosen[1], chosen[2]

    def _strip_item_prefix(self, clean_ocr: str, dict_key: str, entry: dict) -> str:
        text = clean_ocr.replace(dict_key, "", 1)
        url = entry.get("url_name", "")
        if url:
            text = text.replace(self.normalize_text(url.replace("_", "")), "", 1)
            text = text.replace(self.normalize_text(url.replace("_", " ")), "", 1)
        return text

    @staticmethod
    def _part_window_after_name(clean_ocr: str, dict_key: str, window: int = 48) -> str:
        """只取物品名后一小段文字判部件，避免同列其它遗物文字污染。"""
        idx = clean_ocr.find(dict_key)
        if idx < 0:
            return ""
        return clean_ocr[idx + len(dict_key): idx + len(dict_key) + window]

    def _item_kind(self, base_url: str, real_name: str = "", part_suffix: str = "") -> str:
        slug = (base_url or "").lower()
        kinds = _PRIME_KIND_MAP.get(slug)
        if kinds:
            if part_suffix:
                for kind in _KIND_PRIORITY:
                    if kind in kinds and part_suffix in VALID_PARTS_BY_KIND.get(kind, ()):
                        return kind
            if len(kinds) == 1:
                return next(iter(kinds))
            for kind in _KIND_PRIORITY:
                if kind in kinds:
                    return kind
        if any(h in slug for h in _SENTINEL_BASE_HINTS):
            return "sentinel"
        if any(h in slug for h in _BOW_BASE_HINTS):
            return "bow"
        if any(h in slug for h in _MELEE_BASE_HINTS):
            return "melee"
        if any(h in slug for h in _GUN_BASE_HINTS):
            return "gun"
        if real_name and "弓" in real_name and "prime" in real_name.lower():
            return "bow"
        if slug.endswith("_prime"):
            return "warframe"
        return "other"

    def _resolve_part_allowed(self, text: str, allowed: frozenset[str]) -> tuple[str, str]:
        matches = []
        for cn_norm, en, cn_display in self.part_map_entries:
            if cn_norm and cn_norm in text and en in allowed:
                matches.append((cn_norm, en, cn_display))
        if not matches:
            return "set", ""
        chosen = self._pick_part_match(matches)
        return chosen[1], chosen[2]

    def _clamp_part_to_item_kind(
        self,
        base_url: str,
        real_name: str,
        suffix: str,
        cn: str,
        near_text: str,
        tail_text: str,
    ) -> tuple[str, str]:
        kind = self._item_kind(base_url, real_name, suffix)
        allowed = VALID_PARTS_BY_KIND.get(kind)
        if not allowed:
            return suffix, cn
        if suffix in allowed:
            return suffix, cn
        suffix_kind = _kind_for_part_suffix(suffix)
        if suffix_kind and suffix in VALID_PARTS_BY_KIND.get(suffix_kind, ()):
            return suffix, cn
        fixed, fixed_cn = self._resolve_part_allowed(near_text, allowed)
        if fixed != "set":
            return fixed, fixed_cn
        fixed, fixed_cn = self._resolve_part_allowed(tail_text, allowed)
        if fixed != "set":
            return fixed, fixed_cn
        blob = near_text + tail_text
        if "blueprint" in allowed and any(
            x in blob for x in ("蓝图", "总图", "blueprint")
        ):
            return "blueprint", "蓝图"
        return "set", ""

    def resolve_part_for_item(self, clean_ocr: str, dict_key: str, entry: dict) -> tuple[str, str]:
        """解析部件名；组合键直接命中，避免 url 里的 blueprint 子串误判。"""
        if entry.get("forced_suffix"):
            suffix = entry["forced_suffix"]
            cn = entry.get("forced_cn_part", SUFFIX_CN_NAME.get(suffix, ""))
            base_url = entry.get("url_name", "")
            near = self._part_window_after_name(clean_ocr, dict_key)
            return self._clamp_part_to_item_kind(
                base_url, entry.get("real_cn_name", ""), suffix, cn, near,
                self._strip_item_prefix(clean_ocr, dict_key, entry),
            )

        base_url = entry.get("url_name", "")
        real_name = entry.get("real_cn_name", "")
        near = self._part_window_after_name(clean_ocr, dict_key)
        tail = self._strip_item_prefix(clean_ocr, dict_key, entry)
        suffix, cn = self.resolve_part_suffix(near)
        if suffix in ("set", "blueprint"):
            suffix2, cn2 = self.resolve_part_suffix(tail)
            if suffix2 not in ("set",):
                suffix, cn = suffix2, cn2
        kind = self._item_kind(base_url, real_name)
        if suffix == "blueprint" and kind == "melee":
            blob = near + tail
            if any(k in blob for k in ("握柄", "握把", "握图", "handle", "hilt")):
                return "handle", "握柄"
            if "握" in blob and "柄" in blob:
                return "handle", "握柄"
            if "blade" in blob or "刀刃" in blob:
                return "blade", "刀刃"
            if base_url == "venato_prime" and "握" in clean_ocr:
                return "handle", "握柄"
        if suffix == "blueprint" and kind == "gun":
            blob = near + tail
            if any(k in blob for k in ("枪机", "枪管", "枪托", "receiver", "barrel", "stock")):
                return self._resolve_part_allowed(blob, VALID_PARTS_BY_KIND["gun"])
        if suffix == "neuroptics" and ("头部" in near or "头部" in clean_ocr):
            cn = "头部神经光元"
        return self._clamp_part_to_item_kind(base_url, real_name, suffix, cn, near, tail)

    def _resolve_part_from_cell(self, clean_ocr: str, dict_key: str, entry: dict) -> tuple[str, str]:
        """遗物奖励格内整格解析部件（行距小、常多行拼成一条）。"""
        if entry.get("forced_suffix"):
            return self.resolve_part_for_item(clean_ocr, dict_key, entry)
        base_url = entry.get("url_name", "")
        real_name = entry.get("real_cn_name", "")
        tail = self._strip_item_prefix(clean_ocr, dict_key, entry)
        for text in (tail, clean_ocr, self._part_window_after_name(clean_ocr, dict_key, 64)):
            suffix, cn = self.resolve_part_suffix(text)
            if suffix != "set":
                return self._clamp_part_to_item_kind(
                    base_url, real_name, suffix, cn, text, tail
                )
        kind = self._item_kind(base_url, real_name)
        allowed = VALID_PARTS_BY_KIND.get(kind)
        if allowed:
            inferred, cn = self._resolve_part_allowed(clean_ocr, allowed)
            if inferred != "set":
                return inferred, cn
            inferred, cn = self._resolve_part_allowed(tail, allowed)
            if inferred != "set":
                return inferred, cn
        return self.resolve_part_for_item(clean_ocr, dict_key, entry)

    def _build_panel_cell_texts(
        self, blocks: list[dict], panel_w: int, panel_h: int
    ) -> list[str]:
        if len(blocks) < 2:
            return [b["clean"] for b in blocks if b.get("clean")]
        min_x = self._auto_reward_panel_min_x(panel_w, panel_h)
        skip_y = panel_h * 0.10
        work = [
            b
            for b in blocks
            if b.get("clean") and b["cy"] >= skip_y and b["cx"] >= min_x
        ]
        if len(work) < 2:
            work = [b for b in blocks if b.get("clean") and b["cx"] >= min_x]
        if len(work) < 2:
            work = [b for b in blocks if b.get("clean")]
        rows = self._cluster_blocks_into_rows(work)
        reward_rows = self._pick_reward_grid_rows(rows, panel_h)
        texts: list[str] = []
        for row in reward_rows:
            for cell in self._cluster_row_into_cells(row, panel_w):
                merged = self._merge_reward_cell_text(cell)
                if merged:
                    texts.append(merged)
        return list(dict.fromkeys(texts))

    @staticmethod
    def _auto_reward_panel_min_x(img_width: int, img_height: int | None) -> float:
        """宽屏遗物界面：奖励格在右侧，全屏 OCR 时仍用此边界做格点聚类。"""
        if img_width < 1200:
            return 0.0
        if img_height and img_height > 0:
            if (img_width / img_height) < 1.55:
                return 0.0
        if img_width >= 3000:
            return img_width * 0.50
        if img_width >= 1600:
            return img_width * 0.55
        return img_width * 0.42

    @staticmethod
    def _row_looks_like_reward(row_blocks: list[dict]) -> bool:
        for block in row_blocks:
            text = block.get("clean", "")
            if not text:
                continue
            low = text.lower()
            if "prime" in low or "prm" in low:
                return True
            if any(k in text for k in ("蓝图", "枪托", "枪机", "枪管", "刀刃", "连接器", "神经光元", "握柄", "握", "机体")):
                return True
        return False

    def _pick_reward_grid_rows(
        self, rows: list[list[dict]], img_height: int | None
    ) -> list[list[dict]]:
        """取画面中部含 Prime 奖励的两行，避免误用底部 UI 行。"""
        if not rows:
            return []
        if not img_height:
            return rows[-2:] if len(rows) >= 2 else rows
        y0, y1 = img_height * 0.30, img_height * 0.72
        reward_rows = [
            row
            for row in rows
            if self._row_looks_like_reward(row)
            and any(y0 <= b["cy"] <= y1 for b in row)
        ]
        if len(reward_rows) >= 2:
            return reward_rows[:2]
        if reward_rows:
            return reward_rows
        mid_rows = [row for row in rows if any(y0 <= b["cy"] <= y1 for b in row)]
        if len(mid_rows) >= 2:
            return mid_rows[:2]
        return rows[-2:] if len(rows) >= 2 else rows

    def _apply_relic_ocr_typos(self, clean_ocr: str) -> str:
        """遗物奖励格常见 OCR 误读修正（仍全屏扫描，仅纠正文本）。"""
        text = clean_ocr
        text = text.replace("布菜顿", "布莱顿")
        text = text.replace("布菜prime", "布莱顿prime")
        text = text.replace("玻之武妆", "玻之武杖")
        text = text.replace("prime舒物", "prime饰物")
        text = re.sub(r"布菜[顿域球]", "布莱顿", text)
        text = re.sub(r"(?<!蛟)龙prime(?=.*外壳)", "蛟龙prime", text)
        text = text.replace("阿利鸟", "阿利乌")
        text = text.replace("手龄prime", "手鼓prime")
        text = text.replace("红华prime", "红隼prime")
        text = text.replace("死广魔方", "死亡魔方")
        text = text.replace("机依", "机体")
        text = text.replace("机达", "机体")
        text = re.sub(r"大久和prime", "大久和弓prime", text)
        text = text.replace("潮鹉澡prime", "鹦鹉螺prime")
        text = re.sub(r"脉纹prime据$", "脉纹prime握柄", text)
        if re.fullmatch(r"灭杀者prime", text):
            text = "灭杀者prime枪管"
        text = re.sub(r"狼牙pr[mｍ]", "狼牙prime", text, flags=re.IGNORECASE)
        if "狼牙" in text and re.search(r"狼牙prime", text, re.I):
            if not any(x in text for x in ("蓝图", "刀刃", "刃部", "握柄")):
                text = re.sub(r"狼牙prime[\u4e00a-z0-9]*", "狼牙prime刃部", text, count=1)
        if re.fullmatch(r"狼牙prime", text):
            text = "狼牙prime刃部"
        if "枪托" in text and "prime" in text:
            if "伯斯顿" not in text and "burston" not in text:
                if any(x in text for x in ("斯顿", "伯斯", "burs")):
                    text = re.sub(
                        r"[\u4e00-\u9fff]{2,6}prime(?=.*枪托)",
                        "伯斯顿prime",
                        text,
                        count=1,
                    )
        text = text.replace("系统系统", "系统")
        # 奖励格 OCR 常被裁切掉最后一字
        text = re.sub(r"prime握$", "prime握柄", text)
        text = re.sub(r"prime刃$", "prime刀刃", text)
        text = re.sub(r"prime托$", "prime枪托", text)
        text = re.sub(r"prime枪$", "prime枪机", text)
        text = re.sub(r"prime蓝$", "prime蓝图", text)
        text = re.sub(r"神经光元蓝$", "神经光元蓝图", text)
        text = re.sub(r"机体蓝(?!图)", "机体蓝图", text)
        text = re.sub(r"titaniaprme", "titaniaprime", text, flags=re.IGNORECASE)
        text = re.sub(r"titaniarne", "titaniaprime", text, flags=re.IGNORECASE)
        text = re.sub(r"titaniaerme", "titaniaprime", text, flags=re.IGNORECASE)
        text = re.sub(r"(?<!i)varaprime", "ivaraprime", text, flags=re.IGNORECASE)
        text = re.sub(r"naraprime", "ivaraprime", text, flags=re.IGNORECASE)
        text = re.sub(r"waraprime", "ivaraprime", text, flags=re.IGNORECASE)
        text = re.sub(r"pnme", "prime", text, flags=re.IGNORECASE)
        text = text.replace("刀力", "刀刃")
        text = text.replace("双抢", "双枪")
        text = re.sub(r"死l魔方", "死亡魔方", text)
        text = text.replace("白斯顿", "伯斯顿")
        text = re.sub(r"prime检托", "prime枪托", text)
        text = re.sub(r"odonataprime机蓝", "odonataprime机体蓝图", text)
        text = re.sub(r"odonataprime", "陨蜓prime", text, flags=re.IGNORECASE)
        text = text.replace("爱格努斯", "麦格努斯")
        text = text.replace("麦格斯", "麦格努斯")
        text = re.sub(r"^\d+x", "", text)
        text = text.replace("foma", "forma")
        text = re.sub(r"proteaprime", "proteaprime", text, flags=re.IGNORECASE)
        text = re.sub(r"下号", "下弓臂", text)
        text = re.sub(r"上号", "上弓臂", text)
        text = re.sub(r"下弓[街背]", "下弓臂", text)
        text = re.sub(r"上弓[街背]", "上弓臂", text)
        text = text.replace("刀列", "刀刃")
        return text

    _REWARD_PART_SUFFIXES = (
        "头部神经光元", "神经光元", "上弓臂", "下弓臂", "连接器", "刀刃", "刀列",
        "枪机", "枪管", "枪托", "握柄", "蓝图", "机体", "系统", "刃部", "握把",
        "弓弦", "弓身", "饰物", "外壳", "头部",
    )

    def _trim_merged_cell_ocr(self, text: str) -> str:
        """单格 OCR 串台时，截取首个可命中字典的「机体+部件」前缀。"""
        norm = self._apply_relic_ocr_typos(self.normalize_text(text))
        if not norm:
            return norm
        if self._pick_dict_key_for_ocr(norm):
            return norm
        part_pat = "|".join(
            re.escape(p) for p in sorted(self._REWARD_PART_SUFFIXES, key=len, reverse=True)
        )
        m = re.match(rf"^(.+?prime(?:{part_pat})).*$", norm, flags=re.IGNORECASE)
        if m:
            prefix = self._apply_relic_ocr_typos(m.group(1))
            if self._pick_dict_key_for_ocr(prefix):
                return prefix
        return norm

    _FISSURE_PART_HINTS = (
        "蓝图", "刀刃", "刃部", "爪刃", "锤头", "枪机", "枪管", "枪托", "机体", "握柄", "握", "刃", "托", "枪",
        "饰物", "外壳", "头部", "系统", "星镖", "镖袋", "连接器", "靴子", "项圈",
    )

    def _count_prime_bases_in_text(self, clean_ocr: str) -> int:
        bases: set[str] = set()
        for key in self.sorted_keys:
            if key not in clean_ocr:
                continue
            entry = self.wfm_dict.get(key, {})
            url = entry.get("url_name")
            if not url:
                continue
            if not (key.endswith("prime") or entry.get("forced_suffix")):
                continue
            bases.add(url)
        return len(bases)

    def _looks_like_multi_prime_reward(self, clean_ocr: str) -> bool:
        if self._count_prime_bases_in_text(clean_ocr) >= 2:
            return True
        return len(re.findall(r"pr[ie]me", clean_ocr, flags=re.IGNORECASE)) >= 2

    def _expand_polluted_candidates(self, text_candidates: list[str]) -> list[str]:
        expanded: list[str] = []
        for raw in text_candidates:
            clean = self._apply_relic_ocr_typos(self.normalize_text(raw))
            if not clean:
                continue
            clean = self._trim_merged_cell_ocr(clean)
            expanded.append(clean)
            if self._looks_like_multi_prime_reward(clean):
                for chunk in self._split_prime_reward_chunks(clean):
                    expanded.append(self._apply_relic_ocr_typos(chunk))
        return list(dict.fromkeys(expanded))

    def _merge_reward_cell_text(self, cell_blocks: list[dict]) -> str:
        """遗物单格内先按 x 分列、列内再按 y 拼接（适配名称换行）。"""
        blocks = [b for b in cell_blocks if b.get("clean")]
        if not blocks:
            return ""
        if len(blocks) == 1:
            return blocks[0]["clean"]

        subcols: list[dict] = []
        for block in sorted(blocks, key=lambda b: b["cx"]):
            placed = False
            for col in subcols:
                if abs(block["cx"] - col["avg_cx"]) <= max(90.0, block["width"] * 1.6):
                    col["items"].append(block)
                    n = len(col["items"])
                    col["avg_cx"] = (col["avg_cx"] * (n - 1) + block["cx"]) / n
                    placed = True
                    break
            if not placed:
                subcols.append({"items": [block], "avg_cx": block["cx"]})

        parts: list[str] = []
        for col in sorted(subcols, key=lambda c: c["avg_cx"]):
            merged = "".join(
                b["clean"] for b in sorted(col["items"], key=lambda b: b["cy"])
            )
            if merged:
                parts.append(merged)
        return "".join(parts)

    def _register_composite_part_keys(self, entry: dict) -> None:
        """注册「脉纹Prime握柄」等组合键，优先于仅匹配机体名。"""
        cn = entry.get("real_cn_name", "")
        url = entry.get("url_name", "")
        if not cn:
            return
        kind = self._item_kind(url, cn)
        allowed = VALID_PARTS_BY_KIND.get(kind)
        for part_cn, suffix in PART_MAP.items():
            if allowed and suffix not in allowed:
                continue
            combo = self.normalize_text(f"{cn}{part_cn}")
            if not combo or combo in self.wfm_dict:
                continue
            comp = dict(entry)
            comp["forced_suffix"] = suffix
            comp["forced_cn_part"] = part_cn
            self.wfm_dict[combo] = comp
            if url:
                en_combo = self.normalize_text(f"{url.replace('_', '')}{suffix}")
                if en_combo and en_combo not in self.wfm_dict:
                    self.wfm_dict[en_combo] = comp

    def try_bow_part_fallback(self, base_url, real_name, clean_ocr):
        if self._item_kind(base_url, real_name) != "bow":
            return None, None, None, None

        inferred, cn = self._resolve_part_allowed(
            clean_ocr, VALID_PARTS_BY_KIND["bow"]
        )
        if inferred != "set":
            test_price, test_is_fast, _ = self.fetch_price_for_part(
                base_url, inferred, quiet=True
            )
            if test_price:
                return inferred, cn, test_price, test_is_fast

        if any(x in clean_ocr for x in ("下弓臂", "下弓", "下号")):
            test_price, test_is_fast, _ = self.fetch_price_for_part(
                base_url, "lower_limb", quiet=True
            )
            if test_price:
                return "lower_limb", "下弓臂", test_price, test_is_fast
        if any(x in clean_ocr for x in ("上弓臂", "上弓", "上号")):
            test_price, test_is_fast, _ = self.fetch_price_for_part(
                base_url, "upper_limb", quiet=True
            )
            if test_price:
                return "upper_limb", "上弓臂", test_price, test_is_fast

        suffix_candidates = [
            "upper_limb", "lower_limb", "grip", "string", "limb", "blueprint"
        ]
        for suffix in suffix_candidates:
            test_price, test_is_fast, _ = self.fetch_price_for_part(
                base_url, suffix, quiet=True
            )
            if test_price:
                cn_name = SUFFIX_CN_NAME.get(suffix, suffix)
                return suffix, cn_name, test_price, test_is_fast

        return None, None, None, None

    def try_melee_part_fallback(self, base_url, real_name, clean_ocr):
        melee_parts = VALID_PARTS_BY_KIND["melee"]
        has_melee_hint = (
            any(
                k in clean_ocr
                for k in ("握柄", "握把", "握图", "刀刃", "刃部", "护手")
            )
            or (
                ("prime" in clean_ocr or "prm" in clean_ocr)
                and any(k in clean_ocr for k in ("握", "刃"))
            )
        )
        if self._item_kind(base_url, real_name) != "melee" and not has_melee_hint:
            return None, None, None, None

        inferred, cn = self._resolve_part_allowed(clean_ocr, melee_parts)
        if inferred != "set":
            test_price, test_is_fast, _ = self.fetch_price_for_part(
                base_url, inferred, quiet=True
            )
            if test_price:
                return inferred, cn, test_price, test_is_fast

        if "握" in clean_ocr:
            for suffix, cn_name in (("handle", "握柄"), ("hilt", "握柄")):
                test_price, test_is_fast, _ = self.fetch_price_for_part(
                    base_url, suffix, quiet=True
                )
                if test_price:
                    return suffix, cn_name, test_price, test_is_fast
        if any(k in clean_ocr for k in ("刃", "刀刃", "刃部")):
            test_price, test_is_fast, _ = self.fetch_price_for_part(
                base_url, "blade", quiet=True
            )
            if test_price:
                return "blade", "刀刃", test_price, test_is_fast

        return None, None, None, None

    def try_gun_part_fallback(self, base_url, real_name, clean_ocr):
        gun_parts = VALID_PARTS_BY_KIND["gun"]
        has_gun_hint = (
            any(k in clean_ocr for k in ("枪机", "枪管", "枪托", "连接器"))
            or (
                ("prime" in clean_ocr or "prm" in clean_ocr)
                and any(k in clean_ocr for k in ("枪", "托"))
            )
        )
        if self._item_kind(base_url, real_name) != "gun" and not has_gun_hint:
            return None, None, None, None

        inferred, cn = self._resolve_part_allowed(
            clean_ocr, gun_parts
        )
        if inferred != "set":
            test_price, test_is_fast, _ = self.fetch_price_for_part(
                base_url, inferred, quiet=True
            )
            if test_price:
                return inferred, cn, test_price, test_is_fast

        if "枪机" in clean_ocr:
            test_price, test_is_fast, _ = self.fetch_price_for_part(
                base_url, "receiver", quiet=True
            )
            if test_price:
                return "receiver", "枪机", test_price, test_is_fast

        if "蓝图" in clean_ocr:
            test_price, test_is_fast, _ = self.fetch_price_for_part(
                base_url, "blueprint", quiet=True
            )
            if test_price:
                return "blueprint", "蓝图", test_price, test_is_fast

        best_suffix, best_cn, best_val = None, None, -1
        for suffix in VALID_PARTS_BY_KIND["gun"]:
            if suffix == "blueprint":
                continue
            for slug in self._slug_variants(base_url, suffix):
                found = self._lookup_cached_price(slug.replace("_", "").lower())
                if found > best_val:
                    best_val = found
                    best_suffix = suffix
                    best_cn = SUFFIX_CN_NAME.get(suffix, suffix)
        if not best_suffix:
            return None, None, None, None
        test_price, test_is_fast, _ = self.fetch_price_for_part(
            base_url, best_suffix, quiet=True
        )
        if test_price:
            return best_suffix, best_cn, test_price, test_is_fast
        return None, None, None, None

    def _estimate_candidate_layout(
        self, blocks: list[dict], raw: str
    ) -> tuple[float, float]:
        """根据 OCR 块坐标估计候选项在画面中的位置（用于从左到右排序）。"""
        norm = self._apply_relic_ocr_typos(self.normalize_text(raw))
        raw_norm = self.normalize_text(raw)
        matched: list[dict] = []
        for b in blocks:
            bc = b.get("clean", "")
            if not bc:
                continue
            bn = self.normalize_text(bc)
            if bn in norm or norm in bn or bn in raw_norm or bc in raw:
                matched.append(b)
        if not matched:
            return (1e9, 1e9)
        cx = sum(b["cx"] for b in matched) / len(matched)
        cy = sum(b["cy"] for b in matched) / len(matched)
        return (cx, cy)

    @staticmethod
    def _sort_hits_by_screen_order(hits: list[dict]) -> list[dict]:
        """先按行（y）再按列（x）排列，与奖励从左到右一致。"""
        return sorted(
            hits,
            key=lambda h: (h.get("screen_cy", 1e9), h.get("screen_cx", 1e9)),
        )

    def _gather_scan_hits(
        self,
        text_candidates: list[str],
        layouts: list[tuple[float, float]] | None = None,
    ) -> list[dict]:
        hits: list[dict] = []
        for order, raw in enumerate(text_candidates):
            if layouts and order < len(layouts):
                pos_cx, pos_cy = layouts[order]
            else:
                pos_cx, pos_cy = float(order), 0.0
            for clean_ocr in self._expand_polluted_candidates([raw]):
                if len(clean_ocr) < 2:
                    continue
                if self._count_prime_bases_in_text(clean_ocr) >= 2:
                    continue
                dict_key = self._pick_dict_key_for_ocr(clean_ocr)
                if not dict_key:
                    continue
                entry = self.wfm_dict[dict_key]
                base_url = entry["url_name"]
                real_name = entry["real_cn_name"]
                final_suffix, cn_part_name = self._resolve_part_from_cell(
                    clean_ocr, dict_key, entry
                )
                if final_suffix == "set":
                    fb_suffix, fb_cn_name, fb_price, fb_is_fast = self.try_bow_part_fallback(
                        base_url, real_name, clean_ocr
                    )
                    if not fb_suffix:
                        fb_suffix, fb_cn_name, fb_price, fb_is_fast = self.try_melee_part_fallback(
                            base_url, real_name, clean_ocr
                        )
                    if not fb_suffix:
                        fb_suffix, fb_cn_name, fb_price, fb_is_fast = self.try_gun_part_fallback(
                            base_url, real_name, clean_ocr
                        )
                    if not fb_suffix:
                        continue
                    hits.append({
                        "base_url": base_url,
                        "real_name": real_name,
                        "suffix": fb_suffix,
                        "cn_part": fb_cn_name,
                        "final_name": f"{real_name} {fb_cn_name}",
                        "pre_price": fb_price,
                        "pre_is_fast": fb_is_fast,
                        "prio": max(1, PART_MATCH_PRIORITY.get(fb_suffix, 5) - 15),
                        "dict_key": dict_key,
                        "cand_len": len(clean_ocr),
                        "screen_cx": pos_cx,
                        "screen_cy": pos_cy,
                        "screen_order": order,
                    })
                    continue
                hits.append({
                    "base_url": base_url,
                    "real_name": real_name,
                    "suffix": final_suffix,
                    "cn_part": cn_part_name,
                    "final_name": f"{real_name} {cn_part_name}",
                    "pre_price": None,
                    "pre_is_fast": False,
                    "prio": PART_MATCH_PRIORITY.get(final_suffix, 5),
                    "dict_key": dict_key,
                    "cand_len": len(clean_ocr),
                    "screen_cx": pos_cx,
                    "screen_cy": pos_cy,
                    "screen_order": order,
                })
        return hits

    @staticmethod
    def _best_hit_per_base(hits: list[dict]) -> list[dict]:
        """同一 Prime 的不同部件（如系统+外壳）应分别保留。"""
        best: dict[tuple[str, str], dict] = {}
        for h in hits:
            key = (h["base_url"], h.get("suffix", "set"))
            cur = best.get(key)
            if not cur:
                best[key] = h
                continue
            h_score = (h["prio"], -h.get("cand_len", 999))
            c_score = (cur["prio"], -cur.get("cand_len", 999))
            if h_score > c_score:
                best[key] = h
        return list(best.values())

    @staticmethod
    def _best_hit_per_fissure_slot(hits: list[dict]) -> list[dict]:
        """裂缝一排：按格子顺序保留，允许重复 Forma。"""
        by_order: dict[int, dict] = {}
        for h in hits:
            order = int(h.get("screen_order", 0))
            cur = by_order.get(order)
            h_score = (h.get("prio", 0), -h.get("cand_len", 999))
            if not cur:
                by_order[order] = h
                continue
            c_score = (cur.get("prio", 0), -cur.get("cand_len", 999))
            if h_score > c_score:
                by_order[order] = h
        return list(by_order.values())

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

    def _get_monitor_rects(self):
        user32 = ctypes.windll.user32
        monitors = []
        enum_proc = ctypes.WINFUNCTYPE(
            wintypes.BOOL, wintypes.HANDLE, wintypes.HDC, ctypes.POINTER(RECT), wintypes.LPARAM
        )

        def _callback(hmonitor, _hdc, _lprc, _lparam):
            mi = MONITORINFO()
            mi.cbSize = ctypes.sizeof(MONITORINFO)
            if user32.GetMonitorInfoW(hmonitor, ctypes.byref(mi)):
                monitors.append((mi.rcMonitor.left, mi.rcMonitor.top, mi.rcMonitor.right, mi.rcMonitor.bottom))
            return True

        user32.EnumDisplayMonitors(0, 0, enum_proc(_callback), 0)
        return monitors

    def _find_warframe_window(self):
        user32 = ctypes.windll.user32
        hwnds = []
        enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def _callback(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return True
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            if "warframe" in buf.value.lower():
                hwnds.append(hwnd)
            return True

        user32.EnumWindows(enum_proc(_callback), 0)
        return hwnds[0] if hwnds else user32.GetForegroundWindow()

    def _get_window_rect(self, hwnd):
        if not hwnd:
            return None
        user32 = ctypes.windll.user32
        rect = RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return None
        return (rect.left, rect.top, rect.right, rect.bottom)

    @staticmethod
    def _rect_overlap_area(a, b):
        left = max(a[0], b[0])
        top = max(a[1], b[1])
        right = min(a[2], b[2])
        bottom = min(a[3], b[3])
        if right <= left or bottom <= top:
            return 0
        return (right - left) * (bottom - top)

    def get_capture_bbox(self):
        monitors = self._get_monitor_rects()
        if not monitors:
            return tuple(self.config.get("bbox", [0, 0, 1920, 1080]))

        hwnd = self._find_warframe_window()
        window_rect = self._get_window_rect(hwnd)

        if window_rect:
            best_idx = 0
            best_area = -1
            for idx, mon in enumerate(monitors):
                area = self._rect_overlap_area(window_rect, mon)
                if area > best_area:
                    best_area = area
                    best_idx = idx
        else:
            best_idx = 0

        bbox = monitors[best_idx]
        if self.last_capture_monitor != best_idx:
            self.last_capture_monitor = best_idx
            self.log(f"🖥 已锁定截图屏幕: {best_idx + 1}")
        return bbox

    def update_proxy(self):
        proxy = self.entry_proxy.get().strip()
        self.config['proxy'] = proxy
        self.save_config()
        self.log("✅ 代理配置已保存（如需更新价格请点击「拉取价格」）")

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

    def _local_dict_path(self) -> str:
        return os.path.join(get_app_dir(), WFM_DICT_PATH)

    def _fetch_and_save_wfm_dict(self, proxy: str | None = None) -> int:
        """从 Warframe Market 拉取 Prime 列表并写入本地 items.json。"""
        if ItemDictionary is None:
            raise RuntimeError("缺少 warframe_prime_helper 模块")
        if proxy is None:
            proxy = self.config.get("proxy", "")
            if hasattr(self, "entry_proxy"):
                proxy = self.entry_proxy.get().strip() or proxy
        d = ItemDictionary(self._local_dict_path())
        return d.update_from_wfm(proxy=proxy, log=self.log)

    def _ensure_local_dict(self) -> bool:
        """首次启动：本地无 items.json 时自动生成（失败则回退内置字典）。"""
        local_path = self._local_dict_path()
        if os.path.isfile(local_path):
            return True

        self.log("📡 首次启动，正在从 Warframe Market 生成字典...")
        self.update_status("首次生成字典...")

        try:
            self._fetch_and_save_wfm_dict()
            self.log("✅ 字典已生成并保存")
            return True
        except Exception as e:
            self.log(f"⚠️ 在线生成失败: {e}")

        bundled = get_data_path(WFM_DICT_PATH)
        if os.path.isfile(bundled) and os.path.abspath(bundled) != os.path.abspath(local_path):
            shutil.copy2(bundled, local_path)
            self.log("📂 已使用内置字典（可稍后点「更新字典」获取最新版）")
            return True

        return False

    def update_wfm_dict(self):
        if self.dict_updating:
            self.log("⏳ 字典正在更新中...")
            return

        def _update_task():
            self.dict_updating = True
            self.after(0, lambda: self.btn_update_dict.configure(state="disabled"))
            self.log("📡 正在从 Warframe Market 更新字典...")
            self.update_status("更新字典中...")
            try:
                count = self._fetch_and_save_wfm_dict()
                body_count = self._reload_wfm_dict_from_file()
                self.log(f"✅ 字典已热加载，当前 {body_count} 个条目（文件 {count} 条）")
                self.update_status("字典已更新")
                self.after(
                    0,
                    lambda: messagebox.showinfo(
                        "成功", f"字典已更新至最新版\n共收录 {count} 个 Prime 本体"
                    ),
                )
            except Exception as e:
                self.log(f"❌ 更新错误: {e}")
                self.update_status("字典更新失败")
            finally:
                self.dict_updating = False
                self.after(0, self._update_dict_status_label)
                self.after(0, lambda: self.btn_update_dict.configure(state="normal"))

        if messagebox.askyesno(
            "更新字典",
            "从 Warframe Market 下载最新 Prime 列表并覆盖 items.json？\n"
            "（游戏版本更新后若识别不到新甲，请先点此更新）\n"
            "可能需要几十秒；失败请在设置中填写代理后重试。",
        ):
            threading.Thread(target=_update_task, daemon=True).start()

    def _reload_wfm_dict_from_file(self) -> int:
        """从 items.json 重新加载字典到内存。"""
        path = get_data_path(WFM_DICT_PATH)
        if not os.path.exists(path):
            raise FileNotFoundError(f"缺少字典文件: {WFM_DICT_PATH}")
        with open(path, "r", encoding="utf-8") as f:
            raw_dict = json.load(f)
        with self.init_lock:
            self.wfm_dict = {}
            bodies: set[str] = set()
            for v in raw_dict.values():
                if isinstance(v, dict) and "url_name" in v and "real_cn_name" in v:
                    self._register_dict_entry(v)
                    url = v.get("url_name", "")
                    if isinstance(url, str) and url.endswith("_prime"):
                        bodies.add(url)
            self._register_items1_composite_keys(bodies)
            global _PRIME_KIND_MAP
            _PRIME_KIND_MAP = _build_prime_kind_map()
            self.sorted_keys = sorted(self.wfm_dict.keys(), key=len, reverse=True)
        self.after(0, self._update_dict_status_label)
        return len({v.get("url_name") for v in self.wfm_dict.values() if v.get("url_name")})

    def _update_dict_status_label(self):
        if not hasattr(self, "dict_status_label"):
            return
        path = get_data_path(WFM_DICT_PATH)
        if not os.path.exists(path):
            self.dict_status_label.configure(text="未找到 items.json")
            return
        bodies = len({v.get("url_name") for v in self.wfm_dict.values() if v.get("url_name")})
        keys = len(self.wfm_dict)
        self.dict_status_label.configure(text=f"已加载 {bodies} 个 Prime 本体（{keys} 条键）")

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
        self._log_queue.put(msg)

    def _log_thread_safe(self, msg):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"{msg}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _drain_ui_queues(self):
        try:
            while True:
                self._log_thread_safe(self._log_queue.get_nowait())
        except queue.Empty:
            pass
        try:
            while True:
                self.status_label.configure(text=self._status_queue.get_nowait())
        except queue.Empty:
            pass
        try:
            while True:
                payload = self._overlay_queue_ui.get_nowait()
                self._create_overlay_window(**payload)
        except queue.Empty:
            pass
        self.after(50, self._drain_ui_queues)

    def _set_init_state(self, state, error=""):
        with self.init_lock:
            self.init_state = state
            self.init_error = error
            self.is_ready = (state == "ready")

    def _create_ocr_with_timeout(self, timeout_sec=20):
        result = {"ocr": None, "error": None}

        def _worker():
            try:
                from rapidocr_onnxruntime import RapidOCR

                result["ocr"] = RapidOCR()
            except Exception as e:
                result["error"] = e

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        t.join(timeout_sec)
        if t.is_alive():
            return None, f"OCR 初始化超时（>{timeout_sec}s）"
        if result["error"] is not None:
            return None, str(result["error"])
        return result["ocr"], None

    def set_price_mode(self, mode, log_change=False):
        if mode not in ("fast", "live"):
            return
        self.price_mode = mode
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
            self.maybe_start_auto_sync()

    def update_status(self, msg):
        self._status_queue.put(msg)

    # ====== 缃戠粶閫昏緫 ======
    def get_clean_session(self):
        s = requests.Session()
        proxy_url = self.config.get("proxy", "").strip()
        if proxy_url:
            if not proxy_url.startswith("http"): proxy_url = "http://" + proxy_url
            s.proxies = {"http": proxy_url, "https": proxy_url}
            s.trust_env = True
        else:
            s.trust_env = False 
            s.proxies = {}
        s.headers.update({"User-Agent": "Mozilla/5.0"})
        return s

    def _get_last_sync_time(self) -> float:
        last = float(self.config.get("last_price_sync", 0) or 0)
        if last > 0:
            return last
        if os.path.exists(os.path.join(get_app_dir(), PRICE_CACHE_FILE)):
            return os.path.getmtime(os.path.join(get_app_dir(), PRICE_CACHE_FILE))
        return 0.0

    def _format_cache_age(self) -> str:
        last = self._get_last_sync_time()
        if last <= 0:
            return "未同步"
        age = max(0.0, time.time() - last)
        if age < 120:
            return "刚刚"
        if age < 3600:
            return f"{int(age / 60)} 分钟前"
        return f"{int(age / 3600)} 小时前"

    def _is_price_cache_fresh(self) -> bool:
        if len(self.wfinfo_prices) < 10:
            return False
        last = self._get_last_sync_time()
        if last <= 0:
            return False
        return (time.time() - last) < PRICE_CACHE_TTL_SEC

    def _mark_price_sync_success(self) -> None:
        self.config["last_price_sync"] = time.time()
        self.save_config()
        self.after(0, self._update_price_cache_status_label)

    def _update_price_cache_status_label(self) -> None:
        if not hasattr(self, "price_cache_status_label"):
            return
        n = len(self.wfinfo_prices)
        fresh = self._is_price_cache_fresh()
        hint = "2小时内有效" if fresh else "可手动更新"
        self.price_cache_status_label.configure(
            text=f"本地 {n} 条 · {self._format_cache_age()} · {hint}"
        )

    def maybe_start_auto_sync(self) -> None:
        self._update_price_cache_status_label()
        if self._is_price_cache_fresh():
            self._price_sync_done = True
            self.log(
                f"📂 价格缓存仍在有效期内（{len(self.wfinfo_prices)} 条，"
                f"{self._format_cache_age()}），已跳过自动同步"
            )
            self.log("   需要最新价格请点击「拉取价格」")
            self.update_status(f"价格库就绪 ({len(self.wfinfo_prices)} 条)")
            return
        if len(self.wfinfo_prices) > 0:
            self.log("📡 价格缓存已过期，开始后台同步…")
        else:
            self.log("📡 本地无价格缓存，开始首次同步…")
        self.start_sync_task()

    def manual_sync_prices(self) -> None:
        if self.sync_running:
            self.log("⏳ 价格库同步进行中，请稍候…")
            return
        self.log("🔄 手动拉取价格库…")
        self.start_sync_task()

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
        if hasattr(self, "btn_sync_prices"):
            self.btn_sync_prices.configure(state="disabled")

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
            if hasattr(self, "btn_sync_prices"):
                self.after(0, lambda: self.btn_sync_prices.configure(state="normal"))

        threading.Thread(target=_finish_anim, daemon=True).start()

    def _parse_wfinfo_price_list(self, data):
        if isinstance(data, dict) and "contents" in data and isinstance(data["contents"], str):
            data = json.loads(data["contents"])
        data_list = data if isinstance(data, list) else data.get("prices", [])
        new_prices = {}
        for item in data_list:
            if not isinstance(item, dict):
                continue
            name_val = item.get("name") or item.get("item_name")
            if not name_val:
                continue
            clean_name = name_val.lower().replace(" ", "").replace("_", "").strip()
            price_val = item.get("custom_avg") or item.get("plat") or item.get("platinum")
            if not price_val:
                continue
            try:
                if float(price_val) > 0:
                    new_prices[clean_name] = int(float(price_val))
            except Exception:
                pass
        return new_prices

    def _load_price_cache(self, quiet: bool = False) -> bool:
        cache_path = os.path.join(get_app_dir(), PRICE_CACHE_FILE)
        if not os.path.exists(cache_path):
            return False
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cached = json.load(f)
            if isinstance(cached, dict) and len(cached) > 0:
                merged = dict(self.wfinfo_prices)
                merged.update({k: int(v) for k, v in cached.items() if v})
                self.wfinfo_prices = merged
                if not quiet:
                    self.log(f"📂 已加载本地价格缓存 ({len(self.wfinfo_prices)} 条)")
                return True
        except Exception:
            pass
        return False

    def _save_price_cache(self, prices: dict | None = None) -> None:
        payload = prices if prices is not None else self.wfinfo_prices
        try:
            with open(os.path.join(get_app_dir(), PRICE_CACHE_FILE), "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)
        except Exception:
            pass

    def _fetch_one_wfm_stat(self, session, slug: str, retries: int = 3):
        url = f"https://api.warframe.market/v1/items/{slug}/statistics"
        for attempt in range(retries):
            try:
                resp = session.get(url, headers={"Platform": "pc"}, timeout=12)
                if resp.status_code == 429:
                    time.sleep(0.8 * (attempt + 1))
                    continue
                if resp.status_code != 200:
                    return None
                hours = resp.json().get("payload", {}).get("statistics_closed", {}).get("48hours", [])
                if not hours:
                    return None
                median = hours[-1].get("median") or hours[-1].get("avg_price")
                if median and float(median) > 0:
                    key = slug.replace("_", "").lower().strip()
                    return key, int(float(median))
            except Exception:
                if attempt < retries - 1:
                    time.sleep(0.3)
        return None

    def _register_dict_entry(self, entry: dict) -> None:
        """为每个物品仅注册一条规范键（real_cn_name）。"""
        cn = entry.get("real_cn_name", "")
        key = self.normalize_text(cn)
        if key:
            self.wfm_dict[key] = entry
        self._register_composite_part_keys(entry)

    @staticmethod
    def _parse_prime_part_url(url: str) -> tuple[str, str] | None:
        """解析部件 url，返回 (base_url, suffix)。"""
        url = (url or "").lower().strip()
        if not url or url.endswith("_set"):
            return None
        if url.endswith("_kubrow_collar_blueprint"):
            base = url[: -len("_kubrow_collar_blueprint")]
            if base.endswith("_prime"):
                return base, "blueprint"
            return None
        for part in ("neuroptics", "chassis", "systems"):
            token = f"_{part}_blueprint"
            if url.endswith(token):
                base = url[: -len(token)]
                if base.endswith("_prime"):
                    return base, part
        if url.endswith("_blueprint"):
            base = url[: -len("_blueprint")]
            if base.endswith("_prime"):
                return base, "blueprint"
            return None
        if url.endswith("_reciever"):
            base = url[: -len("_reciever")]
            if base.endswith("_prime"):
                return base, "receiver"
            return None
        for suffix in sorted(SUFFIX_CN_NAME.keys(), key=len, reverse=True):
            token = f"_{suffix}"
            if url.endswith(token):
                base = url[: -len(token)]
                if base.endswith("_prime"):
                    return base, suffix
        return None

    def _register_items1_composite_keys(self, bodies: set[str]) -> int:
        """用 items_1.json 的规范中文名补全全部部件组合键。"""
        path = get_data_path(_ITEMS_PARTS_PATH)
        if not os.path.isfile(path):
            return 0
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return 0

        body_tpl: dict[str, dict] = {}
        for v in self.wfm_dict.values():
            url = v.get("url_name", "")
            if url in bodies and not v.get("forced_suffix"):
                body_tpl[url] = v

        added = 0
        for entry in data.values():
            if not isinstance(entry, dict):
                continue
            parsed = self._parse_prime_part_url(entry.get("url_name", ""))
            if not parsed:
                continue
            base, suffix = parsed
            if base not in bodies:
                continue
            tpl = body_tpl.get(base)
            if not tpl:
                continue
            full_cn = entry.get("real_cn_name", "")
            key = self.normalize_text(full_cn)
            if not key:
                continue
            base_cn = tpl.get("real_cn_name", "")
            part_cn = (
                full_cn[len(base_cn) :].strip()
                if base_cn and full_cn.startswith(base_cn)
                else SUFFIX_CN_NAME.get(suffix, "")
            )
            comp = dict(tpl)
            comp["forced_suffix"] = suffix
            comp["forced_cn_part"] = part_cn
            if key not in self.wfm_dict:
                added += 1
            self.wfm_dict[key] = comp
            en_key = self.normalize_text(f"{base.replace('_', '')}{suffix}")
            if en_key:
                self.wfm_dict[en_key] = comp
        return added

    def _pick_dict_key_strict(self, clean_ocr: str) -> str | None:
        matched = [
            k
            for k in self.sorted_keys
            if k in clean_ocr
            and not (
                self.wfm_dict[k].get("url_name") == "trumna_prime"
                and "灭杀者" not in clean_ocr
                and "trumna" not in clean_ocr
            )
        ]
        if not matched:
            return None
        if "迅发" in clean_ocr or "xunfa" in clean_ocr:
            for key in matched:
                if self.wfm_dict[key].get("url_name") == "acceltra_prime":
                    return key
        if "灭杀者" in clean_ocr and not any(
            x in clean_ocr for x in ("迅发", "xunfa", "acceltra")
        ):
            for key in matched:
                if self.wfm_dict[key].get("url_name") == "trumna_prime":
                    return key
        if "枪托" in clean_ocr and any(
            x in clean_ocr for x in ("伯斯顿", "斯顿", "burston", "burs")
        ):
            for key in matched:
                if self.wfm_dict[key].get("url_name") == "burston_prime":
                    return key
        if "绝路" in clean_ocr or "rubico" in clean_ocr:
            for key in matched:
                if self.wfm_dict[key].get("url_name") == "rubico_prime":
                    return key
        return matched[0]

    def _pick_dict_key_fuzzy(self, clean_ocr: str) -> str | None:
        if "prime" not in clean_ocr:
            return None
        hits: list[str] = []
        for key in self.sorted_keys:
            if not key.endswith("prime") or len(key) < 7:
                continue
            base = key[:-5]
            if len(base) < 2 or base not in clean_ocr:
                continue
            entry = self.wfm_dict.get(key, {})
            if (
                entry.get("url_name") == "trumna_prime"
                and "灭杀者" not in clean_ocr
                and "trumna" not in clean_ocr
            ):
                continue
            if key in clean_ocr or re.search(
                re.escape(base) + r".{0,10}prime", clean_ocr, flags=re.IGNORECASE
            ):
                hits.append(key)
        if not hits:
            return None
        hits.sort(key=len, reverse=True)
        if "迅发" in clean_ocr or "xunfa" in clean_ocr:
            for key in hits:
                if self.wfm_dict[key].get("url_name") == "acceltra_prime":
                    return key
        return hits[0]

    def _pick_dict_key_for_ocr(self, clean_ocr: str) -> str | None:
        text = self._apply_relic_ocr_typos(clean_ocr)
        key = self._pick_dict_key_strict(text) or self._pick_dict_key_fuzzy(text)
        if key:
            return key
        for variant in self._ocr_lookup_variants(text):
            key = self._pick_dict_key_strict(variant) or self._pick_dict_key_fuzzy(variant)
            if key:
                return key
        return None

    @staticmethod
    def _ocr_lookup_variants(text: str) -> list[str]:
        """常见 OCR 形近字互换后再试匹配。"""
        if not text:
            return []
        pairs = (("菜", "莱"), ("莱", "菜"), ("鸟", "乌"), ("依", "体"), ("达", "体"))
        variants: list[str] = []
        for src, dst in pairs:
            if src in text:
                variants.append(text.replace(src, dst))
        return list(dict.fromkeys(variants))

    @staticmethod
    def _is_non_tradable_item(base_url: str) -> bool:
        return base_url == "forma"

    @staticmethod
    def _slug_variants(base_url: str, suffix: str) -> list[str]:
        """WFM 上战甲部件多为 *_blueprint，武器部件命名也不统一。"""
        if base_url == "forma":
            return []
        variants: list[str] = []
        if base_url == "kavasa_prime" and suffix == "blueprint":
            variants.append(f"{base_url}_kubrow_collar_blueprint")
        if suffix in ("neuroptics", "chassis", "systems"):
            variants.append(f"{base_url}_{suffix}_blueprint")
        if suffix == "blade":
            variants.extend([f"{base_url}_blades", f"{base_url}_{suffix}"])
        if suffix == "blades":
            variants.append(f"{base_url}_blade")
        if suffix == "receiver":
            variants.append(f"{base_url}_reciever")
        if suffix == "gauntlet":
            variants.append(f"{base_url}_{suffix}")
        variants.append(f"{base_url}_{suffix}")
        if suffix == "handle":
            variants.append(f"{base_url}_hilt")
        return list(dict.fromkeys(variants))

    def fetch_price_for_part(
        self, base_url: str, suffix: str, quiet: bool = False
    ) -> tuple[str | None, bool, bool]:
        """返回 (价格文案, 是否极速展示, 是否本次联网命中)。"""
        if self._is_non_tradable_item(base_url):
            return None, False, False
        for slug in self._slug_variants(base_url, suffix):
            mem_key = slug.replace("_", "").lower()
            found = self._lookup_cached_price(mem_key)
            if found > 0:
                prefix = "⚡ 极速" if self.price_mode == "fast" else "☁️ 实时"
                return f"{prefix}均价: {found} P", self.price_mode == "fast", False
        for slug in self._slug_variants(base_url, suffix):
            live, is_fast = self._fetch_live_wfm_price(slug)
            if live:
                if not quiet:
                    self.log(f"   ↪ 命中市场条目: {slug}")
                return live, is_fast, True
        return None, False, False

    def _lookup_cached_price(self, mem_key: str) -> int:
        if mem_key in self.wfinfo_prices:
            return self.wfinfo_prices[mem_key]
        if "blueprint" in mem_key:
            alt = mem_key.replace("blueprint", "")
            if alt in self.wfinfo_prices:
                return self.wfinfo_prices[alt]
        elif not any(
            x in mem_key
            for x in ("handle", "hilt", "blade", "receiver", "barrel", "stock", "link", "grip", "gauntlet")
        ):
            alt = f"{mem_key}blueprint"
            if alt in self.wfinfo_prices:
                return self.wfinfo_prices[alt]
        for suffix in ("hilt", "grip", "handle"):
            if suffix in mem_key:
                alt = mem_key.replace(suffix, "handle")
                if alt in self.wfinfo_prices:
                    return self.wfinfo_prices[alt]
                alt = mem_key.replace(suffix, "grip")
                if alt in self.wfinfo_prices:
                    return self.wfinfo_prices[alt]
        return 0

    def _fetch_live_wfm_price(self, url_name: str) -> tuple[str | None, bool]:
        """缓存未命中时向 WFM 统计接口单条查询，并写回缓存。"""
        session = self.get_clean_session()
        result = self._fetch_one_wfm_stat(session, url_name, retries=3)
        if not result:
            return None, False
        key, price = result
        self.wfinfo_prices[key] = price
        self._save_price_cache()
        is_fast = self.price_mode == "fast"
        prefix = "⚡ 极速" if is_fast else "☁️ 实时"
        return f"{prefix}均价: {price} P", is_fast

    def _get_sync_slug_list(self, session) -> list[str]:
        """优先同步 items.json 里会出现的 Prime 部件 slug。"""
        bases: list[str] = []
        if os.path.exists(get_data_path(WFM_DICT_PATH)):
            try:
                with open(get_data_path(WFM_DICT_PATH), "r", encoding="utf-8") as f:
                    raw = json.load(f)
                for v in raw.values():
                    if isinstance(v, dict) and v.get("url_name"):
                        bases.append(v["url_name"])
            except Exception:
                pass

        suffixes = (
            "set", "blueprint", "chassis", "systems", "neuroptics",
            "barrel", "receiver", "stock", "blade", "blades", "handle", "hilt", "grip",
            "string", "limb", "upper_limb", "lower_limb", "link", "gauntlet",
        )
        resp = session.get(
            "https://api.warframe.market/v2/items",
            headers={"Language": "zh-hans", "Platform": "pc"},
            timeout=45,
        )
        if resp.status_code != 200:
            return []
        all_slugs = {it.get("slug") for it in resp.json().get("data", []) if it.get("slug")}
        slugs: set[str] = set()
        for base in bases:
            for suf in suffixes:
                for candidate in self._slug_variants(base, suf):
                    if candidate in all_slugs:
                        slugs.add(candidate)
        if not slugs:
            slugs = {s for s in all_slugs if "prime" in s}
        return sorted(slugs)

    def _sync_from_wfm_statistics(self, session) -> bool:
        """WFInfo 源不可用时的备用：从 Warframe Market 48h 统计拉取 Prime 部件价。"""
        self.log("⚠️ WFInfo 价格源暂不可用，改用 Warframe Market 统计...")
        self.update_sync_text("正在从 WFM 拉取统计价...")
        try:
            slugs = self._get_sync_slug_list(session)
            if not slugs:
                self.log("   ❌ 无法构建同步列表")
                return False
            self.log(f"   共 {len(slugs)} 个相关部件，正在查询（约 1~2 分钟）...")
            merged = dict(self.wfinfo_prices)
            done = 0
            with ThreadPoolExecutor(max_workers=4) as pool:
                futures = {pool.submit(self._fetch_one_wfm_stat, session, s): s for s in slugs}
                for fut in as_completed(futures):
                    result = fut.result()
                    if result:
                        key, price = result
                        merged[key] = price
                    done += 1
                    if done % 100 == 0:
                        self.log(f"   ... 进度 {done}/{len(slugs)}（已收录 {len(merged)}）")
            if len(merged) > len(self.wfinfo_prices):
                self.wfinfo_prices = merged
                self._save_price_cache(merged)
                self.log(f"✅ WFM 统计同步成功，价格库共 {len(self.wfinfo_prices)} 条")
                return True
            if len(merged) > 0:
                self.wfinfo_prices = merged
                self._save_price_cache(merged)
                self.log(f"✅ 价格库维持 {len(self.wfinfo_prices)} 条（本次无新增）")
                return True
            self.log("   ❌ WFM 统计未返回有效价格")
        except Exception as e:
            self.log(f"   ❌ WFM 统计同步失败: {e}")
        return False

    def download_price_table_smart(self):
        target_url = "https://api.warframestat.us/wfinfo/prices/"
        encoded_url = urllib.parse.quote(target_url)

        sources = [
            (target_url, "WFInfo 直连"),
            (f"https://api.allorigins.win/raw?url={encoded_url}", "WFInfo 云线路 A"),
            (f"https://api.codetabs.com/v1/proxy?quest={encoded_url}", "WFInfo 云线路 B"),
        ]

        self.log("📡 开始同步价格库...")
        session = self.get_clean_session()
        success = False
        network_synced = False

        for i, (url, name) in enumerate(sources):
            try:
                self.log(f"   🔄 正在尝试线路 {i+1}: {name}")
                resp = session.get(url, timeout=20)
                if resp.status_code != 200:
                    self.log(f"   ❌ 失败: HTTP {resp.status_code}")
                    continue
                try:
                    new_prices = self._parse_wfinfo_price_list(resp.json())
                    if len(new_prices) > 0:
                        self.wfinfo_prices = new_prices
                        self._save_price_cache(new_prices)
                        self.log(f"✅ 成功! 线路: {name}")
                        self.log(f"   已缓存 {len(new_prices)} 个物品")
                        success = True
                        network_synced = True
                        break
                    self.log("   ❌ 解析后无有效价格")
                except Exception:
                    self.log("   ❌ 解析错误")
            except Exception:
                self.log("   ❌ 连接异常")

        if not success:
            if self._sync_from_wfm_statistics(session):
                success = True
                network_synced = True

        if not success:
            success = self._load_price_cache()

        self._price_sync_done = True
        if network_synced and len(self.wfinfo_prices) > 0:
            self._mark_price_sync_success()
        self.after(0, self._update_price_cache_status_label)
        if success:
            self.finish_progress(True)
        else:
            if len(self.wfinfo_prices) > 0:
                self.log(f"⚠️ 在线同步未完成，仍可使用本地缓存 ({len(self.wfinfo_prices)} 条)")
                self.finish_progress(True)
            else:
                self.log("⚠️ 价格库为空：识别时会逐条联网查价，或切换「实时模式」")
                self.log("   （可在设置中填写代理后重启）")
                self.finish_progress(False)

    # ====== 鐣岄潰鏋勫缓 ======
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

        ctk.CTkLabel(self.settings_frame, text="价格库", font=label_font, text_color=THEME["text"]).grid(
            row=3, column=0, padx=14, pady=10, sticky="w"
        )
        self.price_cache_status_label = ctk.CTkLabel(
            self.settings_frame,
            text="加载中…",
            font=("微软雅黑", 11),
            text_color=THEME["muted"],
            anchor="w",
        )
        self.price_cache_status_label.grid(row=3, column=1, sticky="w", padx=8)
        sync_btn_style = dict(action_btn_style)
        sync_btn_style["fg_color"] = THEME["info_btn"]
        sync_btn_style["hover_color"] = THEME["info_hover"]
        sync_btn_style["text_color"] = THEME["text"]
        self.btn_sync_prices = ctk.CTkButton(
            self.settings_frame,
            text="拉取价格",
            command=self.manual_sync_prices,
            **sync_btn_style,
        )
        self.btn_sync_prices.grid(row=3, column=2, padx=10)
        self._update_price_cache_status_label()

        ctk.CTkLabel(self.settings_frame, text="提示音效", font=label_font, text_color=THEME["text"]).grid(row=4, column=0, padx=14, pady=10, sticky="w")
        sound_frame = ctk.CTkFrame(self.settings_frame, fg_color="transparent")
        sound_frame.grid(row=4, column=1, padx=8, sticky="ew")
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
        ctk.CTkButton(self.settings_frame, text="打开目录", command=lambda: os.startfile(get_sound_dir()), **action_btn_style).grid(row=4, column=2, padx=10)

        ctk.CTkLabel(self.settings_frame, text="音量调节", font=label_font, text_color=THEME["text"]).grid(row=5, column=0, padx=14, pady=10, sticky="w")
        vol_f = ctk.CTkFrame(self.settings_frame, fg_color="transparent")
        vol_f.grid(row=5, column=1, columnspan=2, sticky="ew", padx=8, pady=(0, 8))
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
            row=6, column=0, padx=14, pady=10, sticky="w"
        )
        self.dict_status_label = ctk.CTkLabel(
            self.settings_frame,
            text="加载中…",
            font=("微软雅黑", 11),
            text_color=THEME["muted"],
            anchor="w",
        )
        self.dict_status_label.grid(row=6, column=1, sticky="w", padx=8)
        dict_btn_style = dict(sync_btn_style)
        dict_btn_style["text"] = "更新字典"
        self.btn_update_dict = ctk.CTkButton(
            self.settings_frame,
            command=self.update_wfm_dict,
            **dict_btn_style,
        )
        self.btn_update_dict.grid(row=6, column=2, padx=10)

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

            ocr, ocr_error = self._create_ocr_with_timeout(timeout_sec=20)
            if ocr_error:
                self._set_init_state("failed", f"OCR: {ocr_error}")
                self.log(f"❌ OCR 初始化失败: {ocr_error}")
                self.update_status("初始化失败")
                return
            self.ocr = ocr
            self.log("✅ OCR 引擎就绪")
            if not self._ensure_local_dict():
                self.log(f"❌ 找不到字典文件: {WFM_DICT_PATH}")
                self._set_init_state("failed", f"缺少字典文件: {WFM_DICT_PATH}")
                self.update_status("初始化失败")
                return
            body_count = self._reload_wfm_dict_from_file()
            if not self.wfm_dict:
                self._set_init_state("failed", "字典为空或格式不匹配")
                self.log("❌ 字典为空或格式不匹配")
                self.update_status("初始化失败")
                return

            self.log(f"📖 字典加载: {body_count} 个 Prime 本体")
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

    def fetch_price_hybrid(self, url_name, quiet: bool = False):
        mem_key = url_name.replace("_", "").lower().strip()
        found_price = self._lookup_cached_price(mem_key)

        if found_price > 0:
            prefix = "⚡ 极速" if self.price_mode == "fast" else "☁️ 实时"
            return f"{prefix}均价: {found_price} P", self.price_mode == "fast"

        live = self._fetch_live_wfm_price(url_name)
        if not live and not quiet:
            self.log(f"   ❌ 未查到价格: {url_name}")
        return live

    def get_set_price_label(self, base_url, only_cached: bool = False):
        if base_url in self.set_price_cache:
            return self.set_price_cache[base_url]
        if only_cached:
            return None

        set_url = f"{base_url}_set"
        price_str, _ = self.fetch_price_hybrid(set_url)
        if price_str:
            label = f"套装价格: {price_str}"
        else:
            label = "套装价格: 暂无数据"
        self.set_price_cache[base_url] = label
        return label

    @staticmethod
    def _parse_price_value(price_str) -> float | None:
        if not price_str:
            return None
        match = re.search(r"(\d+(?:\.\d+)?)\s*P", str(price_str))
        if not match:
            return None
        try:
            return float(match.group(1))
        except ValueError:
            return None

    @staticmethod
    def _overlay_inner_height(highlight: bool, has_sub: bool, title: str = "") -> int:
        tall_title = len(title) > 14
        if highlight and has_sub:
            return 168 if tall_title else 158
        if has_sub:
            return 158 if tall_title else 145
        if highlight:
            return 148 if tall_title else 130
        return 132 if tall_title else 120

    def _overlay_outer_height(self, highlight: bool, has_sub: bool, title: str = "") -> int:
        """含最高价外框时的总高度。"""
        return self._overlay_inner_height(highlight, has_sub, title) + (8 if highlight else 0)

    def _layout_overlay_y_positions(self, items: list[dict]) -> list[int]:
        screen_h = self._screen_height
        base_y = (screen_h // 2) - 180
        gap = 14
        y = float(base_y)
        positions: list[int] = []
        for item in items:
            highlight = bool(item.get("highlight"))
            has_sub = bool(item.get("sub_content"))
            title = str(item.get("title", ""))
            positions.append(int(y))
            y += self._overlay_outer_height(highlight, has_sub, title) + gap
        return positions

    def show_overlay(
        self,
        title,
        content,
        is_fast,
        index=0,
        sub_content=None,
        highlight: bool = False,
        start_y: int | None = None,
    ):
        self._overlay_queue_ui.put({
            "title": title,
            "content": content,
            "is_fast": is_fast,
            "index": index,
            "sub_content": sub_content,
            "highlight": highlight,
            "start_y": start_y,
        })

    def _create_overlay_window(
        self,
        title,
        content,
        is_fast,
        index=0,
        sub_content=None,
        highlight: bool = False,
        start_y: int | None = None,
    ):
            top = tk.Toplevel(self)
            top.overrideredirect(True)
            top.attributes('-topmost', True)
            top.attributes('-alpha', 0.96 if highlight else 0.90)
            top.config(bg=THEME["highlight"] if highlight else THEME["bg"])

            has_sub = bool(sub_content)
            win_w = 460
            win_h = self._overlay_inner_height(highlight, has_sub, title)
            screen_h = self._screen_height
            if start_y is None:
                gap = 14
                y = float((screen_h // 2) - 180)
                for _ in range(index):
                    y += self._overlay_outer_height(highlight, has_sub, title) + gap
                pos_y = int(y)
            else:
                pos_y = int(start_y)
            
            hidden_x = -win_w - 20 
            target_x = 30 
            top.geometry(f"{win_w}x{win_h}+{hidden_x}+{pos_y}")

            outer_bg = THEME["highlight"] if highlight else THEME["bg"]
            outer = tk.Frame(top, bg=outer_bg)
            outer.pack(fill="both", expand=True, padx=(2 if highlight else 0), pady=(2 if highlight else 0))

            main_frame = tk.Frame(
                outer,
                bg=THEME["highlight_bg"] if highlight else THEME["card_bg"],
            )
            main_frame.pack(fill="both", expand=True, padx=2, pady=2)

            strip_color = THEME["highlight"] if highlight else THEME["gold"]
            strip = tk.Frame(main_frame, bg=strip_color, width=16 if highlight else 10)
            strip.pack(side="left", fill="y")

            card_bg = THEME["highlight_bg"] if highlight else THEME["card_bg"]
            right_bg = THEME["input_bg"]

            right_frame = tk.Frame(main_frame, bg=right_bg, width=112)
            right_frame.pack(side="right", fill="y", padx=(0, 2), pady=2)
            right_frame.pack_propagate(False)

            content_frame = tk.Frame(main_frame, bg=card_bg, padx=16, pady=6)
            content_frame.pack(side="left", fill="both", expand=True)
            
            title_font = ("微软雅黑", 15, "bold") if len(title) > 14 else ("微软雅黑", 17, "bold")
            tk.Label(
                content_frame,
                text=title,
                fg=THEME["highlight"] if highlight else THEME["gold"],
                bg=card_bg,
                font=title_font,
                anchor="w",
                justify="left",
                wraplength=300,
            ).pack(fill="x", pady=(6, 4))
            
            text_color = THEME["fast_text"] if is_fast else THEME["live_text"]
            price_font = ("Segoe UI", 18, "bold") if highlight else ("Segoe UI", 16, "bold")
            price_row = tk.Frame(content_frame, bg=card_bg)
            price_row.pack(fill="x", pady=(0, 6))
            if highlight:
                tk.Label(
                    price_row,
                    text="最高价",
                    fg="#1a1200",
                    bg=THEME["highlight"],
                    font=("微软雅黑", 10, "bold"),
                    padx=8,
                    pady=2,
                ).pack(side="left", padx=(0, 8))
            tk.Label(
                price_row,
                text=content,
                fg=text_color,
                bg=card_bg,
                font=price_font,
                anchor="w",
            ).pack(side="left", fill="x", expand=True)
            if has_sub:
                tk.Label(
                    content_frame,
                    text=sub_content,
                    fg=THEME["muted"],
                    bg=card_bg,
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
                            top.geometry(f"{win_w}x{win_h}+{int(anim_data['curr_x'])}+{pos_y}")
                            top.after(10, animate)
                        else:
                            anim_data["curr_x"] = target_x
                            top.geometry(f"{win_w}x{win_h}+{int(anim_data['curr_x'])}+{pos_y}")
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
                            top.geometry(f"{win_w}x{win_h}+{int(anim_data['curr_x'])}+{pos_y}")
                            top.after(10, animate)
                        else:
                            top.destroy()
                except:
                    pass

            top.after(10, animate)

    def _extract_ocr_blocks(self, ocr_result):
        singles: list[str] = []
        blocks: list[dict] = []

        for line in ocr_result:
            if not isinstance(line, (list, tuple)) or len(line) < 2:
                continue

            raw_text = line[1]
            clean_text = self.normalize_text(raw_text)
            if clean_text:
                singles.append(clean_text)

            box = line[0]
            if not isinstance(box, (list, tuple)) or len(box) < 4:
                continue

            try:
                xs = [float(p[0]) for p in box]
                ys = [float(p[1]) for p in box]
                xmin, xmax = min(xs), max(xs)
                ymin, ymax = min(ys), max(ys)
                cx = sum(xs) / len(xs)
                cy = sum(ys) / len(ys)
                width = xmax - xmin
                height = ymax - ymin
                if clean_text:
                    blocks.append({
                        "clean": clean_text,
                        "cx": cx,
                        "cy": cy,
                        "xmin": xmin,
                        "xmax": xmax,
                        "ymin": ymin,
                        "ymax": ymax,
                        "width": width,
                        "height": height,
                    })
            except Exception:
                continue

        return singles, blocks

    def _prepare_ocr_image(
        self, img_np: np.ndarray, max_width: int = 2560
    ) -> tuple[np.ndarray, float]:
        """4K 全屏 OCR 降采样，坐标在 _rescale_ocr_blocks 中还原。"""
        full_h, full_w = img_np.shape[:2]
        if full_w <= max_width:
            return img_np, 1.0
        scale = max_width / full_w
        new_w = max_width
        new_h = max(1, int(full_h * scale))
        resized = np.asarray(
            Image.fromarray(img_np).resize((new_w, new_h), Image.LANCZOS)
        )
        return resized, scale

    @staticmethod
    def _rescale_ocr_blocks(blocks: list[dict], ocr_scale: float) -> None:
        if ocr_scale == 1.0:
            return
        inv = 1.0 / ocr_scale
        for block in blocks:
            for key in ("cx", "cy", "xmin", "xmax", "ymin", "ymax", "width", "height"):
                if key in block:
                    block[key] *= inv

    def _cluster_blocks_into_rows(self, blocks: list[dict]) -> list[list[dict]]:
        if not blocks:
            return []
        blocks = sorted(blocks, key=lambda b: b["cy"])
        rows: list[list[dict]] = [[blocks[0]]]
        for block in blocks[1:]:
            prev = rows[-1][-1]
            gap = max(40.0, prev["height"] * 2.8)
            if block["cy"] - prev["cy"] > gap:
                rows.append([block])
            else:
                rows[-1].append(block)
        return rows

    @staticmethod
    def _cell_center(cell: list[dict]) -> tuple[float, float]:
        if not cell:
            return (1e9, 1e9)
        cx = sum(b["cx"] for b in cell) / len(cell)
        cy = sum(b["cy"] for b in cell) / len(cell)
        return (cx, cy)

    @staticmethod
    def _dedupe_reward_entries(
        entries: list[dict], *, by_position: bool = False
    ) -> list[dict]:
        seen: set[str] = set()
        out: list[dict] = []
        for e in entries:
            text = e["text"]
            if by_position:
                key = f"{text}@{int(e.get('cx', 0) // 120)}"
            else:
                key = text
            if key in seen:
                continue
            seen.add(key)
            out.append(e)
        return out

    def _cluster_row_into_cells(
        self, row_blocks: list[dict], img_width: int | None = None
    ) -> list[list[dict]]:
        row_blocks = sorted(row_blocks, key=lambda b: b["cx"])
        if len(row_blocks) <= 1:
            return [row_blocks]
        cells: list[list[dict]] = [[row_blocks[0]]]
        if img_width and img_width >= 3000:
            col_gap = max(160.0, img_width * 0.065)
        elif img_width and img_width >= 1600:
            col_gap = max(130.0, img_width * 0.08)
        elif img_width and img_width >= 1200:
            col_gap = max(140.0, img_width * 0.11)
        else:
            col_gap = max(140.0, row_blocks[0]["width"] * 4.0)
        for block in row_blocks[1:]:
            prev = cells[-1][-1]
            if block["cx"] - prev["cx"] > col_gap:
                cells.append([block])
            else:
                cells[-1].append(block)
        return cells

    def _cluster_row_into_fissure_cells(
        self, row_blocks: list[dict], img_width: int | None
    ) -> list[list[dict]]:
        """裂缝结算：横向 4 格奖励，列间距更大。"""
        row_blocks = sorted(row_blocks, key=lambda b: b["cx"])
        if len(row_blocks) <= 1:
            return [row_blocks]
        col_gap = max(220.0, (img_width or 1920) * 0.11)
        cells: list[list[dict]] = [[row_blocks[0]]]
        for block in row_blocks[1:]:
            prev = cells[-1][-1]
            if block["cx"] - prev["cx"] > col_gap:
                cells.append([block])
            else:
                cells[-1].append(block)
        return cells

    _FISSURE_MAX_SLOTS = 4

    @staticmethod
    def _default_fissure_slot_centers(img_width: int, slot_count: int = 4) -> list[float]:
        """无 OCR 标签时的默认槽位中心（1–4 格）。"""
        n = max(1, min(int(slot_count), WFPriceHelperApp._FISSURE_MAX_SLOTS))
        slot_w = img_width * 0.115
        mid = img_width * 0.5
        if n == 1:
            return [mid]
        if n == 2:
            return [mid - 0.5 * slot_w, mid + 0.5 * slot_w]
        if n == 3:
            return [mid - slot_w, mid, mid + slot_w]
        return [
            mid - 1.5 * slot_w,
            mid - 0.5 * slot_w,
            mid + 0.5 * slot_w,
            mid + 1.5 * slot_w,
        ]

    def _fissure_row_label_blocks(
        self, row_blocks: list[dict], img_width: int | None = None
    ) -> list[dict]:
        """裂缝一排奖励：仅物品名行，排除玩家 ID、左侧叠加 UI。"""
        labels = self._fissure_cell_label_blocks(row_blocks)
        out: list[dict] = []
        for block in labels:
            clean = block.get("clean", "")
            norm = self.normalize_text(clean)
            if not norm or norm in ("已拥有",):
                continue
            if re.fullmatch(r"[a-z0-9]{3,24}", norm):
                continue
            if re.fullmatch(r"[金银铜]\d+", norm):
                continue
            if re.search(r"\d+已制造", norm):
                continue
            if re.search(r"总局数|虚空裂缝|报酬", norm):
                continue
            is_reward = (
                "prime" in norm
                or "forma" in norm
                or any(k in norm for k in self._FISSURE_PART_HINTS)
            )
            if (
                img_width
                and block["cx"] < img_width * 0.16
                and not is_reward
            ):
                continue
            out.append(block)
        return out

    def _fissure_slot_centers_from_labels(
        self, label_blocks: list[dict], img_width: int
    ) -> list[float]:
        """由标签块 x 坐标推断 1–4 格中心，不填充空槽。"""
        if not label_blocks:
            return self._default_fissure_slot_centers(img_width, 4)
        xs = sorted(b["cx"] for b in label_blocks)
        gap = max(120.0, img_width * 0.075)
        clusters: list[list[float]] = [[xs[0]]]
        for x in xs[1:]:
            if x - clusters[-1][-1] > gap:
                clusters.append([x])
            else:
                clusters[-1].append(x)
        centers = [sum(c) / len(c) for c in clusters]
        if len(centers) > self._FISSURE_MAX_SLOTS:
            centers = sorted(centers)[-self._FISSURE_MAX_SLOTS :]
        return centers

    def _assign_blocks_to_fissure_slots(
        self,
        label_blocks: list[dict],
        slot_centers: list[float],
        img_width: int,
    ) -> list[list[dict]]:
        n = len(slot_centers)
        slots: list[list[dict]] = [[] for _ in range(n)]
        if not label_blocks:
            return slots
        max_dist = max((img_width or 1920) * 0.095, 180.0)
        for block in label_blocks:
            best_i = min(
                range(n), key=lambda i: abs(block["cx"] - slot_centers[i])
            )
            if abs(block["cx"] - slot_centers[best_i]) <= max_dist:
                slots[best_i].append(block)
        return slots

    def _collect_fissure_label_blocks(
        self, band_blocks: list[dict], img_width: int
    ) -> list[dict]:
        """汇总奖励名行（跨多行 OCR），排除玩家 ID 行干扰聚类。"""
        rows = self._cluster_blocks_into_rows(band_blocks)
        seen: set[tuple[int, str]] = set()
        labels: list[dict] = []
        for row in rows:
            if not self._row_looks_like_reward(row):
                continue
            for block in self._fissure_row_label_blocks(row, img_width):
                norm = self.normalize_text(block.get("clean", ""))
                key = (int(block["cx"] // 80), norm)
                if key in seen:
                    continue
                seen.add(key)
                labels.append(block)
        return sorted(labels, key=lambda b: b["cx"])

    def _has_fissure_reward_header(self, blocks: list[dict]) -> bool:
        if not blocks:
            return False
        joined = "".join(
            self.normalize_text(b.get("clean", "")) for b in blocks if b.get("clean")
        )
        return bool(re.search(r"虚空裂缝", joined))

    def _score_reward_grid_entries(self, grid_entries: list[dict]) -> int:
        score = 0
        for entry in grid_entries:
            norm = self.normalize_text(entry.get("text", ""))
            if not norm:
                continue
            if 6 <= len(norm) <= 30 and "prime" in norm:
                score += 2
            if len(norm) > 32:
                score -= 2
            if self._count_prime_bases_in_text(norm) >= 2:
                score -= 3
            if re.search(
                r"timekeeper|chnprime|dervin|darkangel|mengyu|bilibili|\d{2,}[a-z]{2,}",
                norm,
                re.I,
            ):
                score -= 4
        return score

    def _fissure_layout_confidence(
        self, fissure_entries: list[dict], img_width: int | None
    ) -> int:
        if len(fissure_entries) < 2 or not img_width:
            return 0
        cys = [e.get("cy", 0.0) for e in fissure_entries]
        cxs = [e.get("cx", 0.0) for e in fissure_entries]
        if max(cys) - min(cys) > max(90.0, img_width * 0.025):
            return 0
        if max(cxs) - min(cxs) < img_width * 0.18:
            return 0
        return 8 + len(fissure_entries) * 2

    def _should_use_fissure_scan(
        self,
        fissure_entries: list[dict],
        grid_entries: list[dict],
        blocks: list[dict] | None = None,
        img_width: int | None = None,
    ) -> bool:
        """遗物 2×3 格优先走 grid；裂缝横条 1–4 格。"""
        if not fissure_entries:
            return False
        gn = len(grid_entries)
        fn = len(fissure_entries)
        if gn >= 6:
            return False
        has_header = bool(blocks and self._has_fissure_reward_header(blocks))
        grid_score = self._score_reward_grid_entries(grid_entries)
        fissure_score = self._fissure_layout_confidence(fissure_entries, img_width)

        if has_header and fn >= 1:
            return True
        if fn >= 2 and fissure_score > grid_score + 1 and gn < 3:
            return True
        if gn >= 3 and gn >= fn:
            if grid_score >= fn * 2 and not has_header:
                return False
            if fn >= 2:
                return True
            return False
        if fn >= 3 and gn < 3:
            return True
        if gn >= 3:
            return False
        return fn >= 1

    def _append_fissure_reward_entries(
        self,
        entries: list[dict],
        text: str,
        rect: tuple[int, int, int, int],
    ) -> None:
        norm = self._apply_relic_ocr_typos(self.normalize_text(text))
        if not norm or re.fullmatch(r"[a-z0-9]{3,24}", norm):
            return
        if not (
            "prime" in norm
            or any(k in norm for k in self._FISSURE_PART_HINTS)
        ):
            return
        chunks: list[str]
        if self._looks_like_multi_prime_reward(norm):
            chunks = self._split_prime_reward_chunks(norm)
        else:
            chunks = [norm]
        if not chunks:
            chunks = [norm]
        cx_base = (rect[0] + rect[2]) / 2
        cy_base = (rect[1] + rect[3]) / 2
        slot_w = max(40.0, rect[2] - rect[0])
        for i, chunk in enumerate(chunks):
            piece = self._apply_relic_ocr_typos(self.normalize_text(chunk))
            if not piece:
                continue
            offset = (i - (len(chunks) - 1) / 2) * slot_w * 0.12
            entries.append(
                {"text": piece, "cx": cx_base + offset, "cy": cy_base}
            )

    @staticmethod
    def _fissure_cell_label_blocks(cell_blocks: list[dict]) -> list[dict]:
        """只取卡片标题行，排除下方玩家 ID。"""
        if not cell_blocks:
            return []
        min_cy = min(b["cy"] for b in cell_blocks)
        gap = max(55.0, cell_blocks[0].get("height", 36) * 2.2)
        return [b for b in cell_blocks if b["cy"] - min_cy <= gap]

    def _fissure_block_text_trusted(self, block_text: str) -> bool:
        if not block_text:
            return False
        norm = self._apply_relic_ocr_typos(self.normalize_text(block_text))
        if not norm or re.fullmatch(r"[a-z0-9]{3,24}", norm):
            return False
        if not ("prime" in norm or any(k in norm for k in self._FISSURE_PART_HINTS)):
            return False
        return bool(self._pick_dict_key_for_ocr(norm))

    @staticmethod
    def _crop_has_gold_frame(crop: np.ndarray) -> bool:
        if crop.size == 0:
            return False
        r = crop[..., 0].astype(np.float32)
        g = crop[..., 1].astype(np.float32)
        b = crop[..., 2].astype(np.float32)
        gold = (r > 130) & (g > 100) & (b < r * 0.9)
        return float(gold.mean()) > 0.12

    def _ocr_crop_to_text(self, crop: np.ndarray) -> str:
        if crop.size == 0 or not getattr(self, "ocr", None):
            return ""
        try:
            result, _ = self.ocr(crop)
        except Exception:
            return ""
        if not result:
            return ""
        parts: list[str] = []
        for line in result:
            if not isinstance(line, (list, tuple)) or len(line) < 2:
                continue
            clean = self.normalize_text(line[1])
            if clean and not re.fullmatch(r"[a-z0-9]{3,24}", clean):
                parts.append(clean)
        if not parts:
            return ""
        return self._apply_relic_ocr_typos(self._trim_fissure_cell_ocr("".join(parts)))

    def _preprocess_fissure_cell_image(self, crop: np.ndarray) -> np.ndarray:
        """金框选中格黄底对比度低，压低金色后再拉伸灰度便于 OCR。"""
        if crop.size == 0:
            return crop
        arr = crop.astype(np.float32)
        r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
        lum = 0.299 * r + 0.587 * g + 0.114 * b
        gold = (r > 130) & (g > 100) & (b < r * 0.9) & (lum > 70)
        arr[..., 0] = np.where(gold, np.clip(r * 0.45, 0, 255), r)
        arr[..., 1] = np.where(gold, np.clip(g * 0.45, 0, 255), g)
        arr[..., 2] = np.where(gold, np.clip(b + 35, 0, 255), b)
        gray = 0.299 * arr[..., 0] + 0.587 * arr[..., 1] + 0.114 * arr[..., 2]
        lo = float(np.percentile(gray, 3))
        hi = float(np.percentile(gray, 97))
        if hi <= lo + 1:
            hi = lo + 1
        gray = np.clip((gray - lo) * 255.0 / (hi - lo), 0, 255).astype(np.uint8)
        return np.stack([gray, gray, gray], axis=-1)

    def _score_fissure_cell_text(self, text: str) -> int:
        if not text:
            return -1
        score = len(text)
        if "prime" in text:
            score += 30
        if any(k in text for k in self._FISSURE_PART_HINTS):
            score += 15
        if re.search(r"[a-z]{5,}\d{2,}", text):
            score -= 40
        if re.search(r"timekeeper|darkangel|mengyu|dervin", text, re.I):
            score -= 40
        return score

    @staticmethod
    def _trim_fissure_cell_ocr(text: str) -> str:
        if not text:
            return ""
        text = re.split(
            r"(?:timekeeper|darkangel|mengyu|dervin|bilibili)[a-z0-9]*",
            text,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
        return text.strip()

    def _ocr_fissure_cell_text(
        self, crop: np.ndarray, gold_hint: bool = False
    ) -> str:
        if crop.size == 0 or not getattr(self, "ocr", None):
            return ""
        candidates: list[str] = []
        raw = self._ocr_crop_to_text(crop)
        if raw:
            candidates.append(raw)
        norm = self._apply_relic_ocr_typos(self.normalize_text(raw or ""))
        need_gold = gold_hint and (
            not raw or not self._pick_dict_key_for_ocr(norm)
        )
        if need_gold:
            pre_text = self._ocr_crop_to_text(self._preprocess_fissure_cell_image(crop))
            if pre_text:
                candidates.append(pre_text)
        if not candidates:
            return ""
        return max(candidates, key=self._score_fissure_cell_text)

    def _best_fissure_cell_text(self, *candidates: str) -> str:
        uniq = list(dict.fromkeys(c for c in candidates if c))
        if not uniq:
            return ""
        best_text = ""
        best_score = -1
        for cand in uniq:
            norm = self._apply_relic_ocr_typos(self.normalize_text(cand))
            score = self._score_fissure_cell_text(norm)
            if self._pick_dict_key_for_ocr(norm):
                score += 80
            if score > best_score:
                best_score = score
                best_text = cand
        return best_text

    def _fissure_reward_slot_rects(
        self,
        best_row: list[dict],
        cells: list[list[dict]],
        img_width: int,
        img_height: int,
        slot_centers: list[float] | None = None,
    ) -> list[tuple[int, int, int, int]]:
        """裂缝一排奖励格裁剪区（仅物品名，避开玩家 ID）。"""
        if not best_row or not img_width or not img_height:
            return []
        row_ymin = min(b["ymin"] for b in best_row)
        row_ymax = max(b["ymax"] for b in best_row)
        row_h = max(24.0, row_ymax - row_ymin)
        label_bottom = row_ymin + min(95.0, row_h * 1.15)
        pad_y_top = max(20.0, img_height * 0.01)

        if slot_centers:
            centers = list(slot_centers)
        else:
            centers = []
            for cell in cells:
                if cell:
                    centers.append(sum(b["cx"] for b in cell) / len(cell))
            centers.sort()

        if not centers:
            centers = self._default_fissure_slot_centers(img_width, 4)

        if len(centers) >= 2:
            gaps = [centers[i + 1] - centers[i] for i in range(len(centers) - 1)]
            slot_w = max(gaps) * 0.92 if gaps else img_width * 0.115
        else:
            slot_w = img_width * 0.115

        rects: list[tuple[int, int, int, int]] = []
        for cx in centers:
            x0 = int(max(0, cx - slot_w / 2))
            x1 = int(min(img_width, cx + slot_w / 2))
            y0 = int(max(0, row_ymin - pad_y_top))
            y1 = int(min(img_height, label_bottom))
            if x1 > x0 + 40 and y1 > y0 + 20:
                rects.append((x0, y0, x1, y1))
        return rects

    def build_fissure_reward_candidates(
        self,
        blocks: list[dict],
        img_width: int | None,
        img_height: int | None = None,
        img_np: np.ndarray | None = None,
        screen_blocks: list[dict] | None = None,
    ) -> list[dict]:
        """虚空裂缝/任务结算：画面中部横向一排奖励。返回 text + 格子中心坐标。"""
        if not blocks or not img_width or not img_height:
            return []
        y0, y1 = img_height * 0.36, img_height * 0.70
        band = [b for b in blocks if y0 <= b["cy"] <= y1]
        if not band:
            return []

        rows = self._cluster_blocks_into_rows(band)
        label_blocks = self._collect_fissure_label_blocks(band, img_width)
        if not label_blocks:
            return []

        rect_row = label_blocks
        slot_centers = self._fissure_slot_centers_from_labels(
            label_blocks, img_width
        )
        header_blocks = screen_blocks if screen_blocks is not None else blocks
        if self._has_fissure_reward_header(header_blocks) and len(label_blocks) >= 2:
            xs = sorted(b["cx"] for b in label_blocks)
            if xs[-1] - xs[0] >= img_width * 0.28:
                slot_centers = self._default_fissure_slot_centers(img_width, 4)
        slot_blocks = self._assign_blocks_to_fissure_slots(
            label_blocks, slot_centers, img_width
        )
        occupied = sum(1 for cell in slot_blocks if cell)
        if occupied < 1:
            return []

        slot_rects = self._fissure_reward_slot_rects(
            rect_row,
            slot_blocks,
            img_width,
            img_height,
            slot_centers=slot_centers,
        )

        entries: list[dict] = []
        for idx, rect in enumerate(slot_rects):
            cell = slot_blocks[idx] if idx < len(slot_blocks) else []
            block_text = self._trim_merged_cell_ocr(
                self._merge_reward_cell_text(cell)
            )

            text = block_text
            if not self._fissure_block_text_trusted(block_text) and img_np is not None:
                x0, y0, x1, y1 = rect
                crop = img_np[y0:y1, x0:x1]
                cell_text = self._ocr_fissure_cell_text(
                    crop, gold_hint=self._crop_has_gold_frame(crop)
                )
                text = self._best_fissure_cell_text(cell_text, block_text)

            if text:
                text = self._trim_merged_cell_ocr(text)
                self._append_fissure_reward_entries(entries, text, rect)
        return self._dedupe_reward_entries(entries, by_position=True)

    def _split_prime_reward_chunks(self, blob: str) -> list[str]:
        """OCR 仍合成一整条时，按 prime 词条拆成单条奖励。"""
        if not blob or "prime" not in blob.lower():
            return []
        norm = self._apply_relic_ocr_typos(self.normalize_text(blob))
        head = r"(?:[\u4e00-\u9fff]{1,14}|[a-z]{3,20})pr[ie]me"
        matches = list(re.finditer(head, norm, flags=re.IGNORECASE))
        if len(matches) < 2:
            return []
        parts: list[str] = []
        for i, m in enumerate(matches):
            start = m.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(norm)
            chunk = norm[start:end].strip()
            if len(chunk) > 6:
                parts.append(chunk)
        return list(dict.fromkeys(parts))

    def build_reward_grid_candidates(
        self,
        blocks: list[dict],
        img_width: int | None,
        img_height: int | None = None,
        panel_only: bool = False,
    ) -> list[dict]:
        """遗物精炼右侧 2×3 奖励格：按坐标分格 OCR，避免整列拼接串台。"""
        if not blocks or not img_width or img_width < 400:
            return []
        panel_min_x = self._auto_reward_panel_min_x(img_width, img_height)
        if panel_only and panel_min_x <= 0:
            panel_min_x = img_width * 0.42
        panel_blocks = [b for b in blocks if b["cx"] >= panel_min_x]
        if img_height:
            y0, y1 = img_height * 0.08, img_height * 0.92
            panel_blocks = [b for b in panel_blocks if y0 <= b["cy"] <= y1]
        if len(panel_blocks) < 3:
            return []

        rows = self._cluster_blocks_into_rows(panel_blocks)
        grid_entries: list[dict] = []
        reward_rows = self._pick_reward_grid_rows(rows, img_height)
        for row in reward_rows:
            for cell in self._cluster_row_into_cells(row, img_width):
                merged = self._merge_reward_cell_text(cell)
                if not merged:
                    continue
                cx, cy = self._cell_center(cell)
                norm_merged = self.normalize_text(merged)
                if len(norm_merged) > 28 and self._count_prime_bases_in_text(norm_merged) >= 2:
                    split = self._split_prime_reward_chunks(norm_merged)
                    if len(split) >= 2:
                        for chunk in split:
                            grid_entries.append({"text": chunk, "cx": cx, "cy": cy})
                        continue
                if "prime" in merged or any(
                    k in merged
                    for k in ("蓝图", "握柄", "枪机", "枪托", "神经光元", "刀刃", "连接器")
                ):
                    grid_entries.append({"text": merged, "cx": cx, "cy": cy})

        grid_entries = self._dedupe_reward_entries(grid_entries)
        if len(grid_entries) <= 2 and any(len(e["text"]) > 56 for e in grid_entries):
            split_all: list[dict] = []
            for item in grid_entries:
                chunks = self._split_prime_reward_chunks(item["text"])
                if chunks:
                    for chunk in chunks:
                        split_all.append(
                            {"text": chunk, "cx": item["cx"], "cy": item["cy"]}
                        )
                else:
                    split_all.append(item)
            if len(split_all) >= 2:
                return self._dedupe_reward_entries(split_all)
        return grid_entries

    def build_ocr_candidates(
        self,
        ocr_result,
        img_width: int | None = None,
        img_height: int | None = None,
    ):
        singles, blocks = self._extract_ocr_blocks(ocr_result)
        candidates: list[str] = list(singles)

        if len(blocks) < 2:
            return list(dict.fromkeys(candidates))

        grid_entries = self.build_reward_grid_candidates(
            blocks, img_width, img_height
        )
        use_grid_mode = len(grid_entries) >= 3
        if grid_entries:
            candidates = [e["text"] for e in grid_entries] + candidates

        # 先按 x 聚类到“列”，再按 y 拼接同列相邻文本
        blocks.sort(key=lambda b: b["cx"])
        columns = []
        for block in blocks:
            placed = False
            for col in columns:
                # 扩大同列判定范围，适配长词换行时的轻微横向偏移
                x_threshold = max(85.0, col["avg_w"] * 1.35)
                if abs(block["cx"] - col["avg_cx"]) <= x_threshold:
                    col["items"].append(block)
                    n = len(col["items"])
                    col["avg_cx"] = (col["avg_cx"] * (n - 1) + block["cx"]) / n
                    col["avg_w"] = (col["avg_w"] * (n - 1) + max(block["width"], 1.0)) / n
                    col["avg_h"] = (col["avg_h"] * (n - 1) + max(block["height"], 1.0)) / n
                    placed = True
                    break
            if not placed:
                columns.append({
                    "items": [block],
                    "avg_cx": block["cx"],
                    "avg_w": max(block["width"], 1.0),
                    "avg_h": max(block["height"], 1.0),
                })

        for col in columns:
            items = sorted(col["items"], key=lambda b: b["cy"])
            if not items:
                continue

            if not use_grid_mode:
                col_merged_all = "".join(x["clean"] for x in items if x.get("clean"))
                if col_merged_all:
                    candidates.append(col_merged_all)

            group = [items[0]["clean"]]
            prev_cy = items[0]["cy"]
            # 扩大同列上下行拼接间距
            line_gap_threshold = max(42.0, col["avg_h"] * 3.2)

            for item in items[1:]:
                if (item["cy"] - prev_cy) <= line_gap_threshold:
                    group.append(item["clean"])
                else:
                    merged = "".join(group)
                    if merged:
                        candidates.append(merged)
                    group = [item["clean"]]
                prev_cy = item["cy"]

            merged = "".join(group)
            if merged:
                candidates.append(merged)

            if not use_grid_mode:
                n = len(items)
                long_gap_limit = max(260.0, col["avg_h"] * 12.0)
                for i in range(n):
                    base = items[i]
                    combo = base["clean"]
                    if combo:
                        candidates.append(combo)
                    for j in range(i + 1, min(i + 8, n)):
                        if (items[j]["cy"] - base["cy"]) > long_gap_limit:
                            break
                        combo += items[j]["clean"]
                        if combo:
                            candidates.append(combo)

        return list(dict.fromkeys(candidates))

    @staticmethod
    def _fmt_elapsed(seconds: float) -> str:
        if seconds < 1.0:
            return f"{seconds * 1000:.0f}ms"
        return f"{seconds:.2f}s"

    def process_screenshot(self):
        t_scan = time.perf_counter()
        bbox = self.get_capture_bbox()
        self.log(f"\n📸 正在扫描区域: {bbox}")
        if self.price_mode == "fast" and len(self.wfinfo_prices) < 50:
            if not self._price_sync_done:
                self.log("⏳ 价格库仍在同步，部分物品可能需联网查询...")
            else:
                self.log(f"⚠️ 价格库条目较少 ({len(self.wfinfo_prices)})，缺失项将自动联网补全")
        try:
            self.set_price_cache = {}
            live_query_count = 0
            try:
                img = ImageGrab.grab(bbox=bbox, all_screens=True)
            except TypeError:
                img = ImageGrab.grab(bbox=bbox)
            t_grab = time.perf_counter()
            img_np = np.asarray(img.convert("RGB"))
            full_w, full_h = int(img_np.shape[1]), int(img_np.shape[0])
            ocr_np, ocr_scale = self._prepare_ocr_image(img_np)
            result, _ = self.ocr(ocr_np)

            if not result:
                self.log(
                    f"⚠️ 画面无文字 · 用时 {self._fmt_elapsed(time.perf_counter() - t_scan)}"
                )
                return

            t_ocr = time.perf_counter()
            self.log(
                f"📺 全屏识别（{full_w}x{full_h}）"
                f" · 截图 {self._fmt_elapsed(t_grab - t_scan)}"
                f" · OCR {self._fmt_elapsed(t_ocr - t_grab)}"
            )
            _, blocks = self._extract_ocr_blocks(result)
            self._rescale_ocr_blocks(blocks, ocr_scale)

            found_count = 0
            seen_items = set()

            grid_entries = self.build_reward_grid_candidates(
                blocks, full_w, full_h, panel_only=False
            )
            fissure_entries = self.build_fissure_reward_candidates(
                blocks, full_w, full_h, img_np=img_np, screen_blocks=blocks
            )
            cell_texts = (
                self._build_panel_cell_texts(blocks, full_w, full_h)
                if len(blocks) >= 2
                else []
            )
            if self._should_use_fissure_scan(
                fissure_entries, grid_entries, blocks=blocks, img_width=full_w
            ):
                scan_entries = list(fissure_entries)
                scan_layout = "fissure"
                self.log(
                    f"🎯 裂缝报酬识别 {len(fissure_entries)} 项"
                    f" · 解析 {self._fmt_elapsed(time.perf_counter() - t_ocr)}"
                )
            elif len(grid_entries) >= 3:
                scan_entries = list(grid_entries)
                seen_texts = {e["text"] for e in scan_entries}
                for t in cell_texts:
                    if t in seen_texts:
                        continue
                    cx, cy = self._estimate_candidate_layout(blocks, t)
                    scan_entries.append({"text": t, "cx": cx, "cy": cy})
                    seen_texts.add(t)
                scan_layout = "grid"
                self.log(
                    f"📋 奖励格识别 {len(grid_entries)} 格"
                    f"（已忽略左侧遗物列表）"
                    f" · 解析 {self._fmt_elapsed(time.perf_counter() - t_ocr)}"
                )
            else:
                text_candidates = self.build_ocr_candidates(
                    result, img_width=full_w, img_height=full_h
                )
                merged_texts = list(
                    dict.fromkeys(
                        text_candidates
                        + cell_texts
                        + [e["text"] for e in grid_entries]
                    )
                )
                scan_entries = [
                    {
                        "text": t,
                        "cx": cx,
                        "cy": cy,
                    }
                    for t, (cx, cy) in zip(
                        merged_texts,
                        [
                            self._estimate_candidate_layout(blocks, t)
                            for t in merged_texts
                        ],
                    )
                ]
                scan_layout = "full"
                self.log(
                    f"📋 全屏候选 {len(scan_entries)} 条"
                    f" · 解析 {self._fmt_elapsed(time.perf_counter() - t_ocr)}"
                )
            t_parse = time.perf_counter()
            if scan_layout == "full":
                scan_entries.sort(
                    key=lambda e: (
                        len(e["text"]) <= 64,
                        any(
                            p in e["text"]
                            for p in ("握柄", "握把", "枪机", "神经光元", "头部神经光元", "刀刃")
                        ),
                        -("蓝图" in e["text"] and "握柄" not in e["text"] and "握把" not in e["text"]),
                        -len(e["text"]),
                    ),
                    reverse=True,
                )

            scan_candidates = [e["text"] for e in scan_entries]
            candidate_layouts = [(e["cx"], e["cy"]) for e in scan_entries]
            raw_hits = self._gather_scan_hits(scan_candidates, candidate_layouts)
            if scan_layout == "fissure" and len(raw_hits) < len(scan_candidates):
                hit_orders = {h.get("screen_order") for h in raw_hits}
                missed = [
                    scan_candidates[i]
                    for i in range(len(scan_candidates))
                    if i not in hit_orders
                ]
                if missed:
                    preview = " | ".join(missed[:3])
                    self.log(f"⚠️ 未命中字典: {preview[:100]}")
            if not raw_hits and scan_candidates:
                preview = " | ".join(scan_candidates[:5])
                self.log(f"⚠️ 未命中字典，OCR 示例: {preview[:120]}")
            if scan_layout == "fissure":
                display_hits = sorted(
                    self._best_hit_per_fissure_slot(raw_hits),
                    key=lambda h: (h.get("screen_order", 1e9), h.get("screen_cx", 0)),
                )
            elif scan_layout == "grid":
                display_hits = sorted(
                    self._best_hit_per_base(raw_hits),
                    key=lambda h: (h.get("screen_order", 1e9), h.get("screen_cx", 0)),
                )
            else:
                display_hits = self._sort_hits_by_screen_order(
                    self._best_hit_per_base(raw_hits)
                )
            t_match = time.perf_counter()
            overlay_queue: list[dict] = []
            for hit in display_hits:
                base_url = hit["base_url"]
                real_name = hit["real_name"]
                final_suffix = hit["suffix"]
                final_name = hit["final_name"]

                if scan_layout == "fissure":
                    item_key = hit.get("screen_order", final_name)
                else:
                    item_key = final_name
                if item_key in seen_items:
                    continue

                self.log(f"🔎 识别: {final_name}")
                if self._is_non_tradable_item(base_url):
                    self.log("   -> Forma（不可交易）")
                    seen_items.add(item_key)
                    found_count += 1
                    overlay_queue.append({
                        "title": final_name,
                        "content": "不可交易",
                        "is_fast": False,
                        "sub_content": None,
                        "price_value": None,
                    })
                    continue

                price_str = hit.get("pre_price")
                is_fast = hit.get("pre_is_fast", False)
                if final_suffix != "set" and not price_str:
                    price_str, is_fast, from_live = self.fetch_price_for_part(
                        base_url, final_suffix, quiet=True
                    )
                    if from_live:
                        live_query_count += 1

                if (not price_str) and final_suffix == "handle":
                    alt_parts = [("hilt", "握柄")]
                    if self._item_kind(base_url, real_name) == "bow":
                        alt_parts.append(("grip", "弓身"))
                    for alt_suffix, cn_label in alt_parts:
                        price_str, is_fast, from_live = self.fetch_price_for_part(
                            base_url, alt_suffix, quiet=True
                        )
                        if from_live:
                            live_query_count += 1
                        if price_str:
                            final_name = f"{real_name} {cn_label}"
                            self.log(f"   ↪ 已回退为{cn_label}({alt_suffix})查询")
                            break

                if (not price_str) and self._item_kind(base_url, real_name) == "bow":
                    if final_suffix == "limb":
                        for alt_suffix, cn_label in (
                            ("upper_limb", "上弓臂"),
                            ("lower_limb", "下弓臂"),
                        ):
                            price_str, is_fast, from_live = self.fetch_price_for_part(
                                base_url, alt_suffix, quiet=True
                            )
                            if from_live:
                                live_query_count += 1
                            if price_str:
                                final_name = f"{real_name} {cn_label}"
                                self.log(f"   ↪ 已回退为{cn_label}({alt_suffix})查询")
                                break

                set_price_str = self.get_set_price_label(base_url, only_cached=True)

                if price_str and "查询无结果" not in str(price_str):
                    self.log(f"   -> {price_str}")
                else:
                    self.log("   -> ❌ 未找到价格数据")
                    continue

                seen_items.add(item_key)
                found_count += 1
                overlay_queue.append({
                    "title": final_name,
                    "content": price_str,
                    "is_fast": is_fast,
                    "sub_content": set_price_str,
                    "price_value": self._parse_price_value(price_str),
                })

            t_price = time.perf_counter()
            priced = [o for o in overlay_queue if o["price_value"] is not None]
            max_price = max((o["price_value"] for o in priced), default=None)
            if max_price is not None and len(priced) >= 2:
                top_names = [
                    o["title"] for o in priced if o["price_value"] == max_price
                ]
                if len(top_names) == 1:
                    self.log(f"🏆 最高价: {top_names[0]} ({int(max_price)} P)")
                else:
                    self.log(
                        f"🏆 最高价并列 ({int(max_price)} P): "
                        + "、".join(top_names)
                    )

            for item in overlay_queue:
                item["highlight"] = (
                    max_price is not None
                    and len(priced) >= 2
                    and item["price_value"] == max_price
                )
            overlay_y_positions = self._layout_overlay_y_positions(overlay_queue)
            for item, pos_y in zip(overlay_queue, overlay_y_positions):
                self.show_overlay(
                    item["title"],
                    item["content"],
                    item["is_fast"],
                    sub_content=item["sub_content"],
                    highlight=item["highlight"],
                    start_y=pos_y,
                )
             
            if live_query_count > 0:
                self.log(f"🌐 本次有 {live_query_count} 个物品通过联网补全价格（已写入缓存）")
            t_end = time.perf_counter()
            timing = (
                f"⏱ 截图 {self._fmt_elapsed(t_grab - t_scan)}"
                f" · OCR {self._fmt_elapsed(t_ocr - t_grab)}"
                f" · 解析 {self._fmt_elapsed(t_parse - t_ocr)}"
                f" · 匹配 {self._fmt_elapsed(t_match - t_parse)}"
                f" · 查价 {self._fmt_elapsed(t_price - t_match)}"
            )
            elapsed = self._fmt_elapsed(t_end - t_scan)
            msg = (
                f"完成 (找到 {found_count} 个) · {timing} · 合计 {elapsed}"
                if found_count
                else f"未匹配到物品 · {timing} · 合计 {elapsed}"
            )
            self.update_status(msg)
            self.log(msg)

        except Exception as e:
            self.log(f"❌ Error: {e}")

if __name__ == "__main__":
    app = WFPriceHelperApp()
    app.protocol("WM_DELETE_WINDOW", lambda: (keyboard.unhook_all(), app.destroy()))
    app.mainloop()


