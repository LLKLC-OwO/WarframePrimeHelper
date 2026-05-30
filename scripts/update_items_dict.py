#!/usr/bin/env python3
"""命令行更新 items.json（游戏上新 Prime 后运行此脚本）。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from warframe_prime_helper.config import AppConfig
from warframe_prime_helper.dictionary import ItemDictionary


def main() -> None:
    parser = argparse.ArgumentParser(description="从 Warframe Market 更新 items.json")
    parser.add_argument(
        "--proxy",
        default="",
        help="HTTP 代理，如 127.0.0.1:7890（默认读取 config.json）",
    )
    args = parser.parse_args()

    proxy = args.proxy.strip() or AppConfig().get("proxy", "")
    if proxy:
        print(f"使用代理: {proxy}")

    d = ItemDictionary()
    count = d.update_from_wfm(proxy=proxy, log=print)
    print(f"\n完成：items.json 已更新，共 {count} 个 Prime 本体。")
    print("若程序正在运行，请重启或重新加载字典。")


if __name__ == "__main__":
    main()
