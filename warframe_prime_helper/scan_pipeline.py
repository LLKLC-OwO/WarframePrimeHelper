"""OCR 候选文本 -> 物品匹配 -> 价格解析（与 UI 解耦）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from warframe_prime_helper.dictionary import ItemDictionary
from warframe_prime_helper.hooks import hooks
from warframe_prime_helper.part_matcher import PartMatcher
from warframe_prime_helper.price_service import PriceService

LogFn = Callable[[str], None]


@dataclass
class ScanMatch:
    final_name: str
    final_url: str
    price_str: str
    is_fast: bool
    set_price_str: str


class ScanPipeline:
    """核心扫描流水线，二次开发可子类化 override 某一步。"""

    def __init__(
        self,
        dictionary: ItemDictionary,
        parts: PartMatcher,
        prices: PriceService,
    ):
        self.dictionary = dictionary
        self.parts = parts
        self.prices = prices

    def scan_candidates(
        self,
        text_candidates: list[str],
        log: LogFn | None = None,
    ) -> list[ScanMatch]:
        _log = log or (lambda _m: None)
        self.prices.clear_set_cache()
        results: list[ScanMatch] = []
        seen: set[str] = set()

        for clean_ocr in text_candidates:
            if len(clean_ocr) < 2:
                continue

            hit = self.dictionary.find_in_text(clean_ocr)
            if not hit:
                continue

            dict_key, entry = hit
            base_url = entry["url_name"]
            real_name = entry["real_cn_name"]
            leftover = clean_ocr.replace(dict_key, "", 1)
            final_suffix, cn_part_name = self.parts.resolve_part_suffix(leftover)

            if final_suffix == "set":
                fb = self.parts.try_bow_part_fallback(
                    base_url,
                    real_name,
                    clean_ocr,
                    lambda u: self.prices.fetch_price_hybrid(u, log=_log),
                )
                if not fb[0]:
                    continue
                final_suffix, cn_part_name, price_str, is_fast = fb
                final_url = f"{base_url}_{final_suffix}"
                final_name = f"{real_name} {cn_part_name}"
            else:
                final_url = f"{base_url}_{final_suffix}"
                final_name = f"{real_name} {cn_part_name}"
                price_str, is_fast = None, False

            if final_name in seen:
                continue

            _log(f"🔎 识别: {final_name}")

            if final_suffix != "set" and price_str is None:
                price_str, is_fast = self.prices.fetch_price_hybrid(final_url, log=_log)

            if not price_str and final_suffix == "handle":
                for alt_suffix, cn_label in (("hilt", "握柄"), ("grip", "弓身")):
                    alt_url = f"{base_url}_{alt_suffix}"
                    alt_price, alt_fast = self.prices.fetch_price_hybrid(alt_url, log=_log)
                    if alt_price:
                        final_url = alt_url
                        final_suffix = alt_suffix
                        final_name = f"{real_name} {cn_label}"
                        price_str, is_fast = alt_price, alt_fast
                        _log(f"   ↪ 已回退为 {cn_label}({alt_suffix}) 查询")
                        break

            set_label = self.prices.get_set_price_label(base_url, log=_log)

            if not price_str:
                _log("   -> ❌ 未找到价格数据")
                continue

            _log(f"   -> {price_str}")
            seen.add(final_name)
            match = ScanMatch(
                final_name=final_name,
                final_url=final_url,
                price_str=price_str,
                is_fast=is_fast,
                set_price_str=set_label,
            )
            results.append(match)
            hooks.emit_item_matched(match, {"ocr": clean_ocr})

        hooks.emit_scan_complete(results)
        return results
