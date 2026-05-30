#!/usr/bin/env python3
"""
从 Warframe Market 杜卡德计算器同源数据生成 items_1.json。

数据来源: GET https://api.warframe.market/v2/items
筛选条件: 含 ducats 字段的 Prime 物品（与 /zh-hans/tools/ducats 列表一致）

不会修改 items.json；输出默认写入项目根目录 items_1.json。
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
WFM_ITEMS_URL = "https://api.warframe.market/v2/items"


def fetch_items(proxy: str = "", timeout: int = 60) -> list[dict]:
    session = requests.Session()
    proxy = proxy.strip()
    if proxy:
        if not proxy.startswith("http"):
            proxy = f"http://{proxy}"
        session.proxies = {"http": proxy, "https": proxy}
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0",
            "Language": "zh-hans",
            "Platform": "pc",
        }
    )

    encoded = urllib.parse.quote(WFM_ITEMS_URL)
    sources = [
        (WFM_ITEMS_URL, "直连"),
        (f"https://api.allorigins.win/raw?url={encoded}", "allorigins"),
        (f"https://api.codetabs.com/v1/proxy?quest={encoded}", "codetabs"),
    ]
    last_err: Exception | None = None
    for url, name in sources:
        try:
            print(f"  -> {name} ...")
            resp = session.get(url, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict) and isinstance(data.get("contents"), str):
                data = json.loads(data["contents"])
            items = data.get("data") if isinstance(data, dict) else None
            if items:
                print(f"  OK，共 {len(items)} 条")
                return items
        except Exception as e:
            last_err = e
            print(f"  失败: {e}")
    raise RuntimeError(f"无法拉取物品列表: {last_err}")


def build_ducats_dict(items: list[dict]) -> dict[str, dict]:
    """构建与 items.json 兼容的字典，额外保留 ducats 供杜卡德工具对照。"""
    result: dict[str, dict] = {}
    skipped = 0

    for item in items:
        ducats = item.get("ducats")
        if not ducats:
            continue
        tags = item.get("tags") or []
        if "prime" not in tags:
            continue

        slug = item.get("slug") or ""
        zh = (item.get("i18n") or {}).get("zh-hans", {}).get("name")
        if not slug or not zh:
            skipped += 1
            continue

        entry = {
            "url_name": slug,
            "real_cn_name": zh,
            "ducats": int(ducats),
        }
        # 以中文名为键；重名时保留杜卡德更高者（少见）
        if zh in result and result[zh].get("ducats", 0) >= entry["ducats"]:
            continue
        result[zh] = entry

    print(f"收录 {len(result)} 条 Prime（杜卡德），跳过 {skipped} 条无中文名")
    return dict(sorted(result.items(), key=lambda x: x[0]))


def main() -> None:
    parser = argparse.ArgumentParser(description="生成 items_1.json（杜卡德字典，不覆盖 items.json）")
    parser.add_argument(
        "-o",
        "--output",
        default=str(ROOT / "items_1.json"),
        help="输出路径（默认项目根目录 items_1.json）",
    )
    parser.add_argument("--proxy", default="", help="HTTP 代理，如 127.0.0.1:7890")
    args = parser.parse_args()

    print("从 Warframe Market 拉取杜卡德物品列表 ...")
    items = fetch_items(proxy=args.proxy)
    payload = build_ducats_dict(items)

    meta = {
        "_meta": {
            "source": "https://warframe.market/zh-hans/tools/ducats",
            "api": WFM_ITEMS_URL,
            "filter": "prime + ducats > 0",
            "count": len(payload),
            "note": "未应用；确认后可手动替换或合并到 items.json",
        }
    }
    out = {**meta, **payload}

    out_path = Path(args.output)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=4)

    print(f"已写入: {out_path.resolve()}")
    print("items.json 未改动。")


if __name__ == "__main__":
    main()
