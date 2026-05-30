"""应用配置读写。"""

import json
import os
from typing import Any

from warframe_prime_helper.constants import CONFIG_FILE, DEFAULT_CONFIG
from warframe_prime_helper.paths import get_base_dir


class AppConfig:
    def __init__(self, path: str | None = None):
        self.path = path or os.path.join(get_base_dir(), CONFIG_FILE)
        self.data: dict[str, Any] = {}
        self.load()

    def load(self) -> dict[str, Any]:
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
            except (json.JSONDecodeError, OSError):
                self.data = dict(DEFAULT_CONFIG)
        else:
            self.data = dict(DEFAULT_CONFIG)
            self.save()

        for key, value in DEFAULT_CONFIG.items():
            self.data.setdefault(key, value)
        return self.data

    def save(self) -> None:
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=4, ensure_ascii=False)
        except OSError:
            pass

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value
