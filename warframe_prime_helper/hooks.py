"""扩展钩子：二次开发时注册回调，无需改核心扫描逻辑。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class HookRegistry:
    """事件钩子注册表。

    示例::

        from warframe_prime_helper.hooks import hooks

        def on_match(match, ctx):
            print("命中", match.final_name)

        hooks.on_item_matched(on_match)
    """

    _item_matched: list[Callable[..., Any]] = field(default_factory=list)
    _scan_complete: list[Callable[..., Any]] = field(default_factory=list)
    _before_price_fetch: list[Callable[..., Any]] = field(default_factory=list)

    def on_item_matched(self, callback: Callable[..., Any]) -> None:
        self._item_matched.append(callback)

    def on_scan_complete(self, callback: Callable[..., Any]) -> None:
        self._scan_complete.append(callback)

    def on_before_price_fetch(self, callback: Callable[..., Any]) -> None:
        """callback(url_name: str) -> str | None；返回非空则覆盖默认价格文案。"""
        self._before_price_fetch.append(callback)

    def emit_item_matched(self, match: Any, context: dict[str, Any] | None = None) -> None:
        ctx = context or {}
        for cb in self._item_matched:
            try:
                cb(match, ctx)
            except Exception:
                pass

    def emit_scan_complete(self, matches: list[Any], context: dict[str, Any] | None = None) -> None:
        ctx = context or {}
        for cb in self._scan_complete:
            try:
                cb(matches, ctx)
            except Exception:
                pass

    def try_override_price(self, url_name: str) -> str | None:
        for cb in self._before_price_fetch:
            try:
                result = cb(url_name)
                if result:
                    return str(result)
            except Exception:
                pass
        return None


hooks = HookRegistry()
