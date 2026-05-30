"""路径解析（支持 PyInstaller 打包）。"""

import os
import sys

from warframe_prime_helper.constants import SOUND_DIR


def get_base_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resource_path(relative_path: str) -> str:
    try:
        base_path = sys._MEIPASS  # type: ignore[attr-defined]
    except Exception:
        base_path = get_base_dir()
    return os.path.join(base_path, relative_path)


def get_sound_dir() -> str:
    sound_path = os.path.join(get_base_dir(), SOUND_DIR)
    os.makedirs(sound_path, exist_ok=True)
    return sound_path
