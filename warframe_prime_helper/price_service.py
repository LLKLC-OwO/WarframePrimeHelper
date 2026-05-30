"""价格查询：WFInfo 极速缓存 + Warframe Market 实时订单。"""

from __future__ import annotations

import json
import urllib.parse
from typing import Callable

import requests

from warframe_prime_helper.hooks import hooks


LogFn = Callable[[str], None]


class PriceService:
    def __init__(self, proxy: str = ""):
        self.proxy = proxy.strip()
        self.price_mode = "fast"
        self.wfinfo_prices: dict[str, int] = {}
        self.set_price_cache: dict[str, str] = {}

    def set_proxy(self, proxy: str) -> None:
        self.proxy = proxy.strip()

    def set_mode(self, mode: str) -> None:
        if mode in ("fast", "live"):
            self.price_mode = mode

    def clear_set_cache(self) -> None:
        self.set_price_cache.clear()

    def get_session(self) -> requests.Session:
        s = requests.Session()
        if self.proxy:
            url = self.proxy if self.proxy.startswith("http") else f"http://{self.proxy}"
            s.proxies = {"http": url, "https": url}
            s.trust_env = True
        else:
            s.trust_env = False
            s.proxies = {}
        s.headers.update({"User-Agent": "Mozilla/5.0"})
        return s

    def sync_wfinfo_prices(self, log: LogFn | None = None) -> bool:
        _log = log or (lambda _m: None)
        target_url = "https://api.warframestat.us/wfinfo/prices/"
        encoded_url = urllib.parse.quote(target_url)
        sources = [
            (f"https://api.allorigins.win/raw?url={encoded_url}", "云线路 A"),
            (f"https://api.codetabs.com/v1/proxy?quest={encoded_url}", "云线路 B"),
            (target_url, "官方直连"),
        ]

        _log("📡 开始同步价格库...")
        session = self.get_session()
        for i, (url, name) in enumerate(sources):
            try:
                _log(f"   🔄 正在尝试线路 {i + 1}: {name}")
                resp = session.get(url, timeout=15)
                if resp.status_code != 200:
                    _log(f"   ❌ 失败: HTTP {resp.status_code}")
                    continue

                data = resp.json()
                if "contents" in data and isinstance(data["contents"], str):
                    data = json.loads(data["contents"])

                new_prices: dict[str, int] = {}
                count = 0
                data_list = data if isinstance(data, list) else data.get("prices", [])

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
                            count += 1
                    except (TypeError, ValueError):
                        pass

                if count > 0:
                    self.wfinfo_prices = new_prices
                    _log(f"✅ 成功! 线路: {name}")
                    _log(f"   已缓存 {count} 个物品")
                    return True
                _log("   ❌ 解析错误")
            except Exception:
                _log("   ❌ 连接异常")
        _log("⚠️ 所有线路失败，可切换到实时模式")
        return False

    def _lookup_cached_price(self, mem_key: str) -> int:
        if mem_key in self.wfinfo_prices:
            return self.wfinfo_prices[mem_key]
        if "blueprint" in mem_key:
            found = self.wfinfo_prices.get(mem_key.replace("blueprint", ""), 0)
            if found:
                return found
        else:
            found = self.wfinfo_prices.get(f"{mem_key}blueprint", 0)
            if found:
                return found
        return 0

    def _fetch_wfm_stat_price(self, url_name: str) -> int | None:
        try:
            resp = self.get_session().get(
                f"https://api.warframe.market/v1/items/{url_name}/statistics",
                headers={"Platform": "pc"},
                timeout=12,
            )
            if resp.status_code != 200:
                return None
            hours = resp.json().get("payload", {}).get("statistics_closed", {}).get("48hours", [])
            if not hours:
                return None
            median = hours[-1].get("median") or hours[-1].get("avg_price")
            if median and float(median) > 0:
                price = int(float(median))
                self.wfinfo_prices[url_name.replace("_", "").lower().strip()] = price
                return price
        except Exception:
            pass
        return None

    def fetch_price_hybrid(self, url_name: str, log: LogFn | None = None) -> tuple[str | None, bool]:
        _log = log or (lambda _m: None)

        override = hooks.try_override_price(url_name)
        if override:
            return override, True

        mem_key = url_name.replace("_", "").lower().strip()
        found = self._lookup_cached_price(mem_key)
        if found > 0:
            prefix = "⚡ 极速" if self.price_mode == "fast" else "☁️ 实时"
            return f"{prefix}均价: {found} P", self.price_mode == "fast"

        if self.price_mode == "fast":
            _log("   ⚠️ 缓存未命中，正在向 Warframe Market 查询...")
        else:
            _log("   ☁️ 实时模式：查询 WFM 统计价...")

        price = self._fetch_wfm_stat_price(url_name)
        if price:
            prefix = "⚡ 极速" if self.price_mode == "fast" else "☁️ 实时"
            return f"{prefix}均价: {price} P", self.price_mode == "fast"
        return None, False

    def get_set_price_label(self, base_url: str, log: LogFn | None = None) -> str:
        if base_url in self.set_price_cache:
            return self.set_price_cache[base_url]
        price_str, _ = self.fetch_price_hybrid(f"{base_url}_set", log=log)
        label = f"套装价格: {price_str}" if price_str else "套装价格: 暂无数据"
        self.set_price_cache[base_url] = label
        return label
