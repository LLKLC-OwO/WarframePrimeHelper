"""自检：items_1.json 中的部件是否已在 wfm_dict 注册为组合 OCR 键。"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from wf9_vertical_optimized import (  # noqa: E402
    PART_MAP,
    SUFFIX_CN_NAME,
    VALID_PARTS_BY_KIND,
    WFPriceHelperApp,
    _KIND_PRIORITY,
    _PRIME_KIND_MAP,
    _build_prime_kind_map,
)

ITEMS_PATH = os.path.join(ROOT, "items.json")
ITEMS1_PATH = os.path.join(ROOT, "items_1.json")


def base_url_from_part(url: str) -> str | None:
    url = (url or "").lower()
    if not url.endswith("_prime") and "_prime_" not in url:
        return None
    if url.endswith("_set"):
        return None
    if url.endswith("_blueprint"):
        base = url[: -len("_blueprint")]
        return base if base.endswith("_prime") else None
    for suffix in sorted(SUFFIX_CN_NAME.keys(), key=len, reverse=True):
        token = f"_{suffix}"
        if url.endswith(token):
            base = url[: -len(token)]
            return base if base.endswith("_prime") else None
    return None


def suffix_from_part_url(url: str) -> str | None:
    return WFPriceHelperApp._parse_prime_part_url(url or "")[1] if WFPriceHelperApp._parse_prime_part_url(url or "") else None


def find_unparsed_items1(
    items1: dict, bodies: set[str]
) -> list[tuple[str, str, str]]:
    """items_1 中属于已知机体、但 _parse_prime_part_url 无法解析的条目。"""
    out: list[tuple[str, str, str]] = []
    for name, entry in items1.items():
        if not isinstance(entry, dict):
            continue
        url = entry.get("url_name", "")
        if not url or url.endswith("_set"):
            continue
        parsed = WFPriceHelperApp._parse_prime_part_url(url)
        if parsed:
            continue
        base = base_url_from_part(url)
        if not base and url.endswith("_blueprint"):
            base = url[: -len("_blueprint")]
        if base and base in bodies:
            out.append((name, url, base))
    return out


def expected_kind(url: str) -> str | None:
    kinds = _PRIME_KIND_MAP.get(url)
    if not kinds:
        return None
    for kind in _KIND_PRIORITY:
        if kind in kinds:
            return kind
    return next(iter(kinds))


def main() -> int:
    with open(ITEMS1_PATH, encoding="utf-8") as f:
        items1 = json.load(f)

    app = WFPriceHelperApp()
    app.withdraw()
    app._reload_wfm_dict_from_file()

    missing_in_dict: list[str] = []
    blocked_by_kind: list[str] = []
    cross_kind_registered: list[str] = []
    by_suffix: dict[str, int] = defaultdict(int)
    by_kind: dict[str, int] = defaultdict(int)
    unparsed_items1: list[tuple[str, str, str]] = []

    bodies_in_items = set()
    with open(ITEMS_PATH, encoding="utf-8") as f:
        for v in json.load(f).values():
            if isinstance(v, dict) and v.get("url_name", "").endswith("_prime"):
                bodies_in_items.add(v["url_name"])

    unparsed_items1 = find_unparsed_items1(items1, bodies_in_items)

    for name, entry in items1.items():
        if not isinstance(entry, dict):
            continue
        url = entry.get("url_name", "")
        if not url or url.endswith("_set"):
            continue
        base = base_url_from_part(url)
        suffix = suffix_from_part_url(url)
        if not base or not suffix:
            continue
        if base not in bodies_in_items and base != "forma":
            continue

        cn = entry.get("real_cn_name", name)
        key = app.normalize_text(cn)
        kind = expected_kind(base) or app._item_kind(base, cn)
        allowed = VALID_PARTS_BY_KIND.get(kind, frozenset())
        by_suffix[suffix] += 1
        by_kind[kind or "?"] += 1

        if suffix not in allowed:
            if key in app.wfm_dict:
                cross_kind_registered.append(
                    f"  [{kind}] {cn} ({url}) — suffix '{suffix}'"
                )
            else:
                blocked_by_kind.append(
                    f"  [{kind}] {cn} ({url}) — suffix '{suffix}' 不在 VALID_PARTS_BY_KIND"
                )

        if key not in app.wfm_dict:
            missing_in_dict.append(f"  {cn}  key={key!r}  ({url}, kind={kind})")

    # PART_MAP 中有但某类型未开放的部件
    part_map_suffixes = set(PART_MAP.values())
    kind_gaps: list[str] = []
    for suffix in sorted(part_map_suffixes):
        kinds_with = [k for k, parts in VALID_PARTS_BY_KIND.items() if suffix in parts]
        if not kinds_with:
            kind_gaps.append(f"  suffix '{suffix}' 未加入任何 VALID_PARTS_BY_KIND")

    lines = [
        f"字典组合键总数: {len(app.wfm_dict)}",
        f"items.json Prime 机体: {len(bodies_in_items)}",
        f"items_1 部件条目(可解析): {sum(by_suffix.values())}",
        "",
        f"未注册组合键: {len(missing_in_dict)}",
        f"类型表未覆盖但已注册: {len(cross_kind_registered)}",
        f"真正缺失: {len(blocked_by_kind)}",
        f"无法解析的 items_1 URL: {len(unparsed_items1)}",
        "",
    ]

    if unparsed_items1:
        lines.append("## items_1 URL 无法解析（缺 SUFFIX_CN_NAME 或别名）")
        for cn, url, base in unparsed_items1:
            lines.append(f"  {cn}  ({url})  body={base}")
        lines.append("")

    if missing_in_dict:
        lines.append("## 未注册（字典无此 OCR 键）")
        # group by suffix
        grouped: dict[str, list[str]] = defaultdict(list)
        for line in missing_in_dict:
            m = re.search(r"suffix='?(\w+)'?", line) or re.search(r"\((\w+_prime_\w+)\)", line)
            grouped["other"].append(line)
        for line in missing_in_dict[:60]:
            lines.append(line)
        if len(missing_in_dict) > 60:
            lines.append(f"  ... 另有 {len(missing_in_dict) - 60} 条")
        lines.append("")

    if cross_kind_registered:
        lines.append("## 跨类型部件（items_1 已注册，VALID_PARTS_BY_KIND 未含该 suffix）")
        for line in cross_kind_registered:
            lines.append(line)
        lines.append("")

    if blocked_by_kind:
        lines.append("## 类型未允许（与未注册通常一致）")
        for line in blocked_by_kind[:60]:
            lines.append(line)
        if len(blocked_by_kind) > 60:
            lines.append(f"  ... 另有 {len(blocked_by_kind) - 60} 条")
        lines.append("")

    if kind_gaps:
        lines.append("## PART_MAP suffix 无对应类型")
        lines.extend(kind_gaps)
        lines.append("")

    lines.append("## 按 suffix 统计 (items_1)")
    for suf, cnt in sorted(by_suffix.items(), key=lambda x: (-x[1], x[0])):
        kinds = [k for k, p in VALID_PARTS_BY_KIND.items() if suf in p]
        lines.append(f"  {suf}: {cnt}  (允许类型: {', '.join(kinds) or '无'})")

    ocr_samples = [
        "飞扬prime星镖",
        "飞扬prime镖袋",
        "凯旋之爪prime爪刃",
        "创伤prime锤头",
        "卡帕压力枪prime枪机",
        "科加基prime靴子",
        "喀婆萨prime项圈带",
        "喀婆萨prime项圈扣",
        "喀婆萨prime库狛项圈蓝图",
        "席瓦神盾prime护手",
        "眼镜蛇鹤prime护手",
    ]
    lines.append("")
    lines.append("## OCR 部件解析抽样")
    unresolved_ocr: list[str] = []
    for raw in ocr_samples:
        norm = app._apply_relic_ocr_typos(app.normalize_text(raw))
        key = app._pick_dict_key_for_ocr(norm)
        if not key:
            unresolved_ocr.append(f"  FAIL {raw} -> 无字典键")
            continue
        entry = app.wfm_dict[key]
        suffix, cn = app._resolve_part_from_cell(norm, key, entry)
        if suffix == "set":
            unresolved_ocr.append(f"  FAIL {raw} -> {key} suffix=set")
        else:
            lines.append(f"  OK {raw} -> {suffix} ({cn})")
    for line in unresolved_ocr:
        lines.append(line)

    text = "\n".join(lines)
    out = os.path.join(ROOT, "scripts", "audit_composite_report.txt")
    with open(out, "w", encoding="utf-8") as f:
        f.write(text)
    print(text)
    print(f"\n报告: {out}")
    return 1 if missing_in_dict or unparsed_items1 or unresolved_ocr else 0


if __name__ == "__main__":
    raise SystemExit(main())
