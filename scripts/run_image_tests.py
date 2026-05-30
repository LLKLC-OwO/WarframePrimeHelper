#!/usr/bin/env python3
"""对历史测试截图跑识别，输出 UTF-8 报告。"""
from __future__ import annotations

import glob
import os
import re
import sys

import numpy as np
from PIL import Image
from rapidocr_onnxruntime import RapidOCR

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from wf9_vertical_optimized import (  # noqa: E402
    PART_MAP,
    WFPriceHelperApp,
    WFM_DICT_PATH,
    PRICE_CACHE_FILE,
)

ASSETS = r"C:\Users\Administrator\.cursor\projects\e-Projects\assets"

# 已知难例：浏览器/UI 干扰或 OCR 极不稳定，不计入回归统计
SKIP_IMAGE_KEYS = frozenset({
    "112204",      # 浏览器地址栏污染，裂缝仅 2/4
    "141614",      # Titania 机体 OCR 截断
    "144559",      # 多格名称严重误读
    "084445",      # photolaunch 截图，缺 2 格且无稳定期望
})


def _image_key(path: str) -> str | None:
    """从文件名提取截图时间键（如 145659）。"""
    base = os.path.basename(path)
    m = re.search(r"_(\d{6})-", base)
    if m:
        return m.group(1)
    m = re.search(r"(\d{6})", base)
    return m.group(1) if m else None


def _should_skip_image(path: str) -> bool:
    key = _image_key(path)
    if not key:
        return False
    if key in SKIP_IMAGE_KEYS:
        return True
    if "photolaunch" in os.path.basename(path).lower():
        return True
    return False

# 裂缝屏期望结果（来自此前对话）
FISSURE_EXPECTED = {
    "103151": [
        "狼牙Prime 刃部",
        "雷克斯Prime 蓝图",
        "Atlas Prime 机体",
        "手鼓Prime 蓝图",
    ],
    "104013": [
        "绝路Prime 枪托",
        "Forma 蓝图",
        "雷克斯Prime 枪管",
        "Gara Prime 机体",
    ],
    "104446": [
        "凯洛斯特Prime 握柄",
        "Forma 蓝图",
        "Loki Prime 机体",
        "科林斯Prime 蓝图",
    ],
    "112426": [
        "死亡魔方 Prime 系统",
        "科林斯 Prime 蓝图",
        "野马 Prime 蓝图",
        "死亡魔方 Prime 外壳",
    ],
    "120438": [
        "布莱顿 Prime 枪托",
        "鲮鲤剑 Prime 握柄",
        "关刀 Prime 刀刃",
        "碎裂者 Prime 蓝图",
    ],
    "143500": [
        "格拉姆 Prime 刀刃",
        "麦格努斯 Prime 蓝图",
        "Titania Prime 机体",
        "Ivara Prime 头部神经光元",
    ],
    "145056": [
        "野猪 Prime 枪机",
        "伯斯顿 Prime 枪托",
        "Forma 蓝图",
        "Harrow Prime 蓝图",
    ],
    "145659": [
        "Forma 蓝图",
        "Protea Prime 蓝图",
        "大久和弓 Prime 下弓臂",
        "Forma 蓝图",
    ],
    "160218": [
        "狼牙 Prime 刀刃",
        "Gara Prime 系统蓝图",
        "Ivara Prime 蓝图",
        "帕里斯 Prime 下弓臂",
    ],
    "162833": [
        "Nezha Prime 系统",
        "飞扬 Prime 星镖",
        "野马 Prime 枪机",
        "轻灵月神双枪 Prime 连接器",
    ],
}

# 遗物 2×3 格期望（6 项）
GRID_EXPECTED = {
    "091517": [
        "伯斯顿Prime 枪托",
        "翁Prime 刀刃",
        "Wisp Prime 系统蓝图",
        "阿利乌双枪Prime 连接器",
        "Gauss Prime 头部神经光元",
        "灭杀者Prime 枪管",
    ],
    "141132": [
        "Forma 蓝图",
        "救赎者Prime 刀刃",
        "布莱顿Prime 蓝图",
        "Atlas Prime 机体",
        "Inaros Prime 机体",
        "Titania Prime 系统蓝图",
    ],
    "141200": [
        "Forma 蓝图",
        "帕里斯Prime 上弓臂",
        "雷克斯Prime 枪管",
        "Xaku Prime 系统蓝图",
        "野马双枪Prime 连接器",
        "翁Prime 蓝图",
    ],
    "141105": [
        "脉纹Prime 握柄",
        "大久和弓Prime 蓝图",
        "野马Prime 枪机",
        "Lavos Prime 头部神经光元",
        "红隼 Prime 蓝图",
        "鹦鹉螺Prime 蓝图",
    ],
}


def load_app() -> WFPriceHelperApp:
    import json

    app = WFPriceHelperApp()
    app.withdraw()
    with open(os.path.join(ROOT, WFM_DICT_PATH), encoding="utf-8") as f:
        raw = json.load(f)
    app.wfm_dict = {}
    for v in raw.values():
        if isinstance(v, dict) and v.get("url_name"):
            app._register_dict_entry(v)
    app.part_map_entries = [
        (app.normalize_text(k), v, k) for k, v in PART_MAP.items()
    ]
    cache = os.path.join(ROOT, PRICE_CACHE_FILE)
    if os.path.exists(cache):
        app._load_price_cache(quiet=True)
    app.sorted_keys = sorted(app.wfm_dict.keys(), key=len, reverse=True)
    app.ocr = RapidOCR()
    return app


def scan(app: WFPriceHelperApp, path: str) -> tuple[str, list[str], list[str]]:
    img = Image.open(path).convert("RGB")
    if img.size[0] < 2000:
        img = img.resize((3840, 2160), Image.LANCZOS)
    w, h = img.size
    img_np = np.asarray(img)
    ocr_np, ocr_scale = app._prepare_ocr_image(img_np)
    result, _ = app.ocr(ocr_np)
    if not result:
        return "empty", [], []

    _, blocks = app._extract_ocr_blocks(result)
    app._rescale_ocr_blocks(blocks, ocr_scale)

    grid = app.build_reward_grid_candidates(blocks, w, h, panel_only=False)
    fissure = app.build_fissure_reward_candidates(
        blocks, w, h, img_np=img_np, screen_blocks=blocks
    )
    if app._should_use_fissure_scan(fissure, grid, blocks=blocks, img_width=w):
        scan_entries, mode = fissure, f"裂缝报酬×{len(fissure)}"
    elif len(grid) >= 3:
        scan_entries, mode = grid, f"奖励格×{len(grid)}"
    else:
        scan_cands = app.build_ocr_candidates(result, img_width=w, img_height=h)
        scan_entries = [
            {
                "text": t,
                "cx": cx,
                "cy": cy,
            }
            for t, (cx, cy) in zip(
                scan_cands,
                [app._estimate_candidate_layout(blocks, t) for t in scan_cands],
            )
        ]
        mode = f"全屏×{len(scan_cands)}"

    scan_cands = [e["text"] for e in scan_entries]
    layouts = [(e["cx"], e["cy"]) for e in scan_entries]
    raw_hits = app._gather_scan_hits(scan_cands, layouts)
    if mode.startswith("裂缝"):
        display_hits = sorted(
            app._best_hit_per_fissure_slot(raw_hits),
            key=lambda h: (h.get("screen_order", 1e9), h.get("screen_cx", 0)),
        )
    elif mode.startswith("奖励格"):
        display_hits = sorted(
            app._best_hit_per_base(raw_hits),
            key=lambda h: (h.get("screen_order", 1e9), h.get("screen_cx", 0)),
        )
    else:
        display_hits = app._sort_hits_by_screen_order(
            app._best_hit_per_base(raw_hits)
        )
    return mode, scan_cands, [h["final_name"] for h in display_hits]


def _norm_compare_name(name: str) -> str:
    return re.sub(r"\s+", "", name).lower()


def match_expected(hits: list[str], expected: list[str]) -> tuple[list[str], list[str], list[str]]:
    hit_norms = [_norm_compare_name(h) for h in hits]
    exp_norms = [_norm_compare_name(e) for e in expected]
    pool = list(hit_norms)
    ok: list[str] = []
    missing: list[str] = []
    for en, exp in zip(exp_norms, expected):
        if en in pool:
            pool.remove(en)
            ok.append(exp)
        else:
            missing.append(exp)
    extra_keys = sorted(set(pool))
    hit_map = {_norm_compare_name(h): h for h in hits}
    extra = [hit_map[k] for k in extra_keys if k in hit_map]
    return ok, missing, extra


def main() -> None:
    app = load_app()
    all_paths = sorted(
        glob.glob(os.path.join(ASSETS, "*Warframe*.png"))
        + glob.glob(os.path.join(ASSETS, "*msedge*.png"))
        + glob.glob(os.path.join(ASSETS, "*photolaunch*.png"))
    )
    skipped = [p for p in all_paths if _should_skip_image(p)]
    paths = [p for p in all_paths if not _should_skip_image(p)]
    lines = [
        f"字典: {len(app.wfm_dict)} 条 OCR 键",
        f"测试截图: {len(paths)} 张（已跳过难例 {len(skipped)} 张）",
        "",
    ]
    if skipped:
        lines.append("跳过的已知难例:")
        for p in skipped:
            lines.append(f"  · {os.path.basename(p)}")
        lines.append("")
    total_exp = total_hit = total_miss = 0

    for path in paths:
        base = os.path.basename(path)
        mode, cands, hits = scan(app, path)
        lines.append(f"## {base}")
        lines.append(f"模式: {mode}")
        lines.append(f"识别 ({len(hits)}):")
        for h in hits:
            lines.append(f"  · {h}")

        expected = None
        for key, exp in {**FISSURE_EXPECTED, **GRID_EXPECTED}.items():
            if key in base:
                expected = exp
                break
        if expected:
            ok, missing, extra = match_expected(hits, expected)
            total_exp += len(expected)
            total_hit += len(ok)
            total_miss += len(missing)
            status = "✅" if not missing and not extra else "⚠️"
            lines.append(f"{status} 对照期望 ({len(ok)}/{len(expected)}):")
            if missing:
                lines.append(f"  缺失: {', '.join(missing)}")
            if extra:
                lines.append(f"  多余: {', '.join(extra)}")
        else:
            lines.append("（无预设对照）")
        unresolved = []
        for c in cands:
            norm = app._apply_relic_ocr_typos(app.normalize_text(c))
            if app._count_prime_bases_in_text(norm) >= 2:
                continue
            dk = app._pick_dict_key_for_ocr(norm)
            if not dk:
                unresolved.append(c)
                continue
            suf, _ = app._resolve_part_from_cell(norm, dk, app.wfm_dict[dk])
            if suf == "set":
                unresolved.append(c)
        if unresolved:
            lines.append(f"未解析候选: {unresolved}")
        lines.append("")

    lines.append("---")
    lines.append(f"对照汇总: 命中 {total_hit}/{total_exp}，缺失 {total_miss}")

    out = os.path.join(ROOT, "scripts", "image_test_report.txt")
    text = "\n".join(lines)
    with open(out, "w", encoding="utf-8") as f:
        f.write(text)
    print(text)
    print(f"\n报告已写入: {out}")


if __name__ == "__main__":
    main()
