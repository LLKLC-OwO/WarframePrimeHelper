"""自检：items.json 中 Prime 类型是否与 items_1 部件表一致。"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from wf9_vertical_optimized import (  # noqa: E402
    WFPriceHelperApp,
    _KIND_PRIORITY,
    _PRIME_KIND_MAP,
    VALID_PARTS_BY_KIND,
)

ITEMS_PATH = os.path.join(ROOT, "items.json")


def expected_kind(url: str) -> str | None:
    kinds = _PRIME_KIND_MAP.get(url)
    if not kinds:
        return None
    if len(kinds) == 1:
        return next(iter(kinds))
    for kind in _KIND_PRIORITY:
        if kind in kinds:
            return kind
    return next(iter(kinds))


def main() -> int:
    with open(ITEMS_PATH, encoding="utf-8") as f:
        items = json.load(f)

    app = WFPriceHelperApp()
    app.withdraw()

    missing_map: list[str] = []
    mismatches: list[str] = []
    ok = 0

    for name, entry in items.items():
        if not isinstance(entry, dict):
            continue
        url = entry.get("url_name", "")
        if not url.endswith("_prime"):
            continue
        exp = expected_kind(url)
        got = app._item_kind(url, entry.get("real_cn_name", ""))
        if exp is None:
            missing_map.append(f"  {name} ({url}) -> {got}")
            continue
        if got != exp:
            mismatches.append(f"  {name} ({url}): got={got}, expected={exp}, kinds={sorted(_PRIME_KIND_MAP[url])}")
        else:
            ok += 1

    print(f"Prime 类型映射: {len(_PRIME_KIND_MAP)} 条 (来自 items_1.json)")
    print(f"一致: {ok}  不一致: {len(mismatches)}  无映射: {len(missing_map)}")

    if mismatches:
        print("\n[不一致]")
        print("\n".join(mismatches[:40]))
        if len(mismatches) > 40:
            print(f"  ... 另有 {len(mismatches) - 40} 条")

    if missing_map:
        print("\n[items_1 无部件表，仍用启发式]")
        print("\n".join(missing_map[:20]))
        if len(missing_map) > 20:
            print(f"  ... 另有 {len(missing_map) - 20} 条")

    # 抽样：武器部件在错误类型下是否仍能通过 clamp
    samples = [
        ("karyst_prime", "handle", "凯洛斯特prime握柄"),
        ("pandero_prime", "barrel", "手鼓prime枪管"),
        ("rubico_prime", "stock", "绝路prime枪托"),
        ("corinth_prime", "blueprint", "科林斯prime蓝图"),
    ]
    print("\n[部件解析抽样]")
    for url, suffix, ocr in samples:
        cn = {"handle": "握柄", "barrel": "枪管", "stock": "枪托", "blueprint": "蓝图"}[suffix]
        got_suffix, got_cn = app._clamp_part_to_item_kind(
            url, "", suffix, cn, ocr, ocr
        )
        status = "OK" if got_suffix == suffix else "FAIL"
        print(f"  {status} {url} + {suffix} -> {got_suffix} {got_cn}")

    return 1 if mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())
