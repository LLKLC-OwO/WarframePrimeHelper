"""物品字典：加载、更新、匹配。"""

from __future__ import annotations

import json
import os
import urllib.parse
from typing import Any, Callable

import requests

from warframe_prime_helper.constants import ITEMS_DICT_FILE
from warframe_prime_helper.paths import get_base_dir
from warframe_prime_helper.text import normalize_text

LogFn = Callable[[str], None]

WFM_ITEMS_URL = "https://api.warframe.market/v2/items"
PART_SUFFIXES = (
    "_blueprint",
    "_chassis",
    "_systems",
    "_neuroptics",
    "_harness",
    "_wings",
    "_barrel",
    "_blade",
    "_handle",
    "_hilt",
    "_grip",
    "_string",
    "_limb",
    "_receiver",
    "_stock",
)


class ItemDictionary:
    """items.json 读写与 Prime 本体索引。"""

    def __init__(self, path: str | None = None):
        self.path = path or os.path.join(get_base_dir(), ITEMS_DICT_FILE)
        self.entries: dict[str, dict[str, str]] = {}
        self.sorted_keys: list[str] = []

    def load(self) -> int:
        if not os.path.exists(self.path):
            raise FileNotFoundError(f"缺少字典文件: {self.path}")

        with open(self.path, "r", encoding="utf-8") as f:
            raw = json.load(f)

        self.entries = {
            normalize_text(k): v
            for k, v in raw.items()
            if isinstance(v, dict) and "url_name" in v and "real_cn_name" in v
        }
        self.sorted_keys = sorted(self.entries.keys(), key=len, reverse=True)
        return len(self.entries)

    @staticmethod
    def _dedupe_by_url(data: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
        """每个 url_name 只保留一条，键名为 real_cn_name。"""
        by_url: dict[str, dict[str, str]] = {}
        for entry in data.values():
            if not isinstance(entry, dict):
                continue
            url = entry.get("url_name")
            cn = entry.get("real_cn_name")
            if not url or not cn:
                continue
            prev = by_url.get(url)
            if not prev:
                by_url[url] = entry
                continue
            prev_cn = prev.get("real_cn_name", "")
            # 优先保留含中文的官方市场名
            prev_zh = any("\u4e00" <= c <= "\u9fff" for c in prev_cn)
            cur_zh = any("\u4e00" <= c <= "\u9fff" for c in cn)
            if cur_zh and not prev_zh:
                by_url[url] = entry
        return {normalize_text(v["real_cn_name"]): v for v in by_url.values()}

    def save(self, data: dict[str, Any] | None = None) -> None:
        payload = self._dedupe_by_url(data if data is not None else self.entries)
        out = {entry["real_cn_name"]: entry for entry in payload.values()}
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=4)

    def find_in_text(self, clean_ocr: str) -> tuple[str, dict[str, str]] | None:
        for key in self.sorted_keys:
            if key in clean_ocr:
                return key, self.entries[key]
        return None

    @staticmethod
    def _build_session(proxy: str) -> requests.Session:
        s = requests.Session()
        proxy = (proxy or "").strip()
        if proxy:
            if not proxy.startswith("http"):
                proxy = f"http://{proxy}"
            s.proxies = {"http": proxy, "https": proxy}
            s.trust_env = True
        else:
            s.trust_env = False
            s.proxies = {}
        s.headers.update(
            {
                "User-Agent": "Mozilla/5.0",
                "Language": "zh-hans",
                "Platform": "pc",
            }
        )
        return s

    @staticmethod
    def _normalize_wfm_item(item: dict) -> dict | None:
        """统一 v1(payload.items) 与 v2(data[]) 字段为 url_name + item_name。"""
        if not isinstance(item, dict):
            return None
        if "url_name" in item and item.get("item_name"):
            return {"url_name": item["url_name"], "item_name": item["item_name"]}
        slug = item.get("slug")
        if not slug:
            return None
        name = (
            item.get("i18n", {}).get("zh-hans", {}).get("name")
            or item.get("i18n", {}).get("en", {}).get("name")
            or slug.replace("_", " ").title()
        )
        return {"url_name": slug, "item_name": name}

    @staticmethod
    def _parse_items_payload(data: Any) -> list[dict]:
        if isinstance(data, str):
            data = json.loads(data)
        if isinstance(data, dict) and "contents" in data and isinstance(data["contents"], str):
            data = json.loads(data["contents"])

        raw_list: list[dict] = []
        if isinstance(data, dict):
            if isinstance(data.get("data"), list):
                raw_list = data["data"]
            else:
                raw_list = data.get("payload", {}).get("items", []) or []
        elif isinstance(data, list):
            raw_list = data

        out: list[dict] = []
        for item in raw_list:
            norm = ItemDictionary._normalize_wfm_item(item)
            if norm:
                out.append(norm)
        return out

    def _fetch_wfm_items(
        self,
        proxy: str = "",
        timeout: int = 60,
        log: LogFn | None = None,
    ) -> list[dict]:
        _log = log or (lambda _m: None)
        encoded = urllib.parse.quote(WFM_ITEMS_URL)
        session = self._build_session(proxy)

        sources: list[tuple[str, str, bool]] = [
            (WFM_ITEMS_URL, "Warframe Market 直连", False),
            (f"https://api.allorigins.win/raw?url={encoded}", "云线路 A (allorigins)", True),
            (f"https://api.codetabs.com/v1/proxy?quest={encoded}", "云线路 B (codetabs)", True),
        ]

        last_error: Exception | None = None
        for url, name, _ in sources:
            try:
                _log(f"   -> 尝试: {name}")
                resp = session.get(url, timeout=timeout)
                if resp.status_code != 200:
                    _log(f"   !! HTTP {resp.status_code}")
                    continue
                items = self._parse_items_payload(resp.json())
                if items:
                    _log(f"   OK {name}，共 {len(items)} 条市场条目")
                    return items
                _log("   !! 响应无 items 数据")
            except Exception as e:
                last_error = e
                _log(f"   !! 连接失败: {e}")

        if last_error:
            raise RuntimeError(f"所有线路均失败，请配置 config.json 中的 proxy。最后错误: {last_error}")
        raise RuntimeError("所有线路均失败，请检查网络或配置代理")

    @staticmethod
    def _is_prime_base_url(url_name: str) -> bool:
        """仅 Prime 武器/战甲/同伴本体，排除部件与 Prime Mod。"""
        slug = (url_name or "").lower()
        if not slug.endswith("_prime"):
            return False
        if slug.startswith("primed_"):
            return False
        if "_prime_" in slug:
            return False
        return True

    @staticmethod
    def _is_prime_part_url(url_name: str) -> bool:
        return any(url_name.endswith(suffix) for suffix in PART_SUFFIXES)

    @staticmethod
    def _add_prime_entry(
        final_dict: dict[str, dict[str, str]],
        url_name: str,
        display_name: str,
    ) -> bool:
        if not url_name or not display_name:
            return False
        if not ItemDictionary._is_prime_base_url(url_name):
            return False
        if "_set" in url_name or ItemDictionary._is_prime_part_url(url_name):
            return False
        if "prime" not in url_name.lower() and "Prime" not in display_name:
            return False
        if "Set" in display_name or "套装" in display_name or "一套" in display_name:
            return False

        key = normalize_text(display_name)
        if key in final_dict:
            return False
        final_dict[key] = {"url_name": url_name, "real_cn_name": display_name}
        return True

    @staticmethod
    def _build_dict_from_items(items: list[dict]) -> dict[str, dict[str, str]]:
        final_dict: dict[str, dict[str, str]] = {}

        # 路径 1：市场条目中的 Prime 本体（中文名）
        for item in items:
            item_name = item.get("item_name", "")
            url_name = item.get("url_name", "")
            ItemDictionary._add_prime_entry(final_dict, url_name, item_name)

        # 路径 2：从 *_set 套装反推本体（新 Prime 常先上套装条目）
        for item in items:
            url_name = item.get("url_name", "")
            if "prime" not in url_name.lower() or "_set" not in url_name:
                continue
            base_url = url_name.replace("_set", "")
            item_name = item.get("item_name", "")
            display = (
                item_name.replace(" Set", "")
                .replace("套装", "")
                .replace(" set", "")
                .replace("一套", "")
                .strip()
            )
            ItemDictionary._add_prime_entry(final_dict, base_url, display)

        return final_dict

    def update_from_wfm(
        self,
        proxy: str = "",
        timeout: int = 60,
        log: LogFn | None = None,
    ) -> int:
        """从 Warframe Market v2 API 拉取最新 Prime 本体并写入 items.json。"""
        _log = log or print
        _log("[字典] 正在从 Warframe Market 更新物品字典...")
        items = self._fetch_wfm_items(proxy=proxy, timeout=timeout, log=_log)
        final_dict = self._build_dict_from_items(items)
        if not any(v.get("url_name") == "forma" for v in final_dict.values()):
            final_dict[normalize_text("Forma")] = {
                "url_name": "forma",
                "real_cn_name": "Forma",
            }
            _log("[字典] 已补全 Forma")
        final_dict = self._dedupe_by_url(final_dict)
        count = len(final_dict)
        if count == 0:
            raise RuntimeError("未解析到任何 Prime 条目，请稍后重试")

        self.entries = final_dict
        self.sorted_keys = sorted(self.entries.keys(), key=len, reverse=True)
        self.save(final_dict)
        _log(f"[字典] 已写入 {self.path}，收录 {count} 个 Prime 本体")
        return count
