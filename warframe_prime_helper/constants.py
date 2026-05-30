"""全局常量与主题配置，二次开发时可在此扩展部件映射。"""

DEFAULT_CONFIG = {
    "hotkey": "alt+q",
    "bbox": [0, 0, 1920, 1080],
    "proxy": "",
    "sound_file": "default",
    "sound_volume": 0.5,
}

CONFIG_FILE = "config.json"
ITEMS_DICT_FILE = "items.json"
QR_IMAGE_PATH = "qr.png"
SOUND_DIR = "sound"

THEME = {
    "bg": "#070b14",
    "card_bg": "#101a2f",
    "text": "#eaf1ff",
    "gold": "#ff9f1c",
    "gold_hover": "#f18701",
    "fast_text": "#34d399",
    "live_text": "#38bdf8",
    "info_btn": "#2563eb",
    "info_hover": "#1d4ed8",
    "progress_bg": "#1f2a44",
    "progress_fill": "#22d3ee",
    "progress_err": "#ef4444",
    "panel_border": "#24365b",
    "input_bg": "#0e1830",
    "muted": "#92a3c3",
}

PART_MATCH_PRIORITY = {
    "handle": 90,
    "hilt": 89,
    "blade": 88,
    "blades": 88,
    "gauntlet": 87,
    "receiver": 86,
    "barrel": 85,
    "stock": 84,
    "link": 83,
    "grip": 82,
    "string": 81,
    "limb": 80,
    "upper_limb": 79,
    "lower_limb": 78,
    "neuroptics": 75,
    "chassis": 74,
    "systems": 73,
    "blueprint": 10,
    "set": 0,
}

# 中文部件名 -> WFM url 后缀
PART_MAP = {
    "蓝图": "blueprint",
    "总图": "blueprint",
    "机体": "chassis",
    "系统": "systems",
    "神经光元": "neuroptics",
    "视光器": "neuroptics",
    "枪机": "receiver",
    "枪管": "barrel",
    "枪托": "stock",
    "连接器": "link",
    "刀刃": "blade",
    "握柄": "handle",
    "握把": "handle",
    "握图": "handle",
    "护手": "gauntlet",
    "圆盘": "disc",
    "饰物": "ornament",
    "弓身": "grip",
    "弓臂": "limb",
    "上弓臂": "upper_limb",
    "下弓臂": "lower_limb",
    "弓弦": "string",
    "握把套": "grip",
    "缰绳": "harness",
    "机翼": "wings",
    "引擎": "engine",
    "外壳": "carapace",
    "脑部": "cerebrum",
}

SUFFIX_CN_NAME = {
    "blueprint": "蓝图",
    "chassis": "机体",
    "systems": "系统",
    "neuroptics": "神经光元",
    "receiver": "枪机",
    "barrel": "枪管",
    "stock": "枪托",
    "link": "连接器",
    "blade": "刀刃",
    "handle": "握柄",
    "hilt": "握柄",
    "gauntlet": "护手",
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
}
