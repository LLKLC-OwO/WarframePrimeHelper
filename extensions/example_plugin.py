"""
示例插件：演示如何通过钩子扩展功能。

在 run.py 或自定义启动脚本中 import 本模块即可生效::

    import extensions.example_plugin  # noqa: F401
    from warframe_prime_helper.app import main
    main()
"""

from warframe_prime_helper.hooks import hooks
from warframe_prime_helper.scan_pipeline import ScanMatch


def on_item_matched(match: ScanMatch, context: dict) -> None:
    # 例如：写入本地日志、推送到 Discord、过滤低价物品等
    print(f"[插件] 命中: {match.final_name} -> {match.price_str}")


def on_scan_complete(matches: list[ScanMatch], context: dict) -> None:
    print(f"[插件] 本次扫描共 {len(matches)} 个结果")


hooks.on_item_matched(on_item_matched)
hooks.on_scan_complete(on_scan_complete)
