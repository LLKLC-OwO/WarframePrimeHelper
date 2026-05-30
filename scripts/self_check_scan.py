"""自检：对已知裂缝/遗物截图跑 OCR 识别（无需 GUI）。"""
from __future__ import annotations

import glob
import json
import os
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

ASSET_DIRS = [
    os.path.join(ROOT, "assets"),
    os.path.join(os.path.dirname(ROOT), ".cursor", "projects", "e-Projects", "assets"),
    r"C:\Users\Administrator\.cursor\projects\e-Projects\assets",
]


def load_app() -> WFPriceHelperApp:
    app = WFPriceHelperApp()
    app.withdraw()
    app._reload_wfm_dict_from_file()
    cache_path = os.path.join(ROOT, PRICE_CACHE_FILE)
    if os.path.exists(cache_path):
        app._load_price_cache(quiet=True)
    app.ocr = RapidOCR()
    return app


def scan_image(app: WFPriceHelperApp, path: str) -> dict:
    img = Image.open(path).convert("RGB")
    if img.size[0] < 2000:
        img = img.resize((3840, 2160), Image.LANCZOS)
    w, h = img.size
    result, _ = RapidOCR()(np.asarray(img))
    if not result:
        return {"path": path, "mode": "empty", "hits": []}

    _, blocks = app._extract_ocr_blocks(result)
    fissure = app.build_fissure_reward_candidates(blocks, w, h, screen_blocks=blocks)
    grid = app.build_reward_grid_candidates(blocks, w, h, panel_only=False)
    if app._should_use_fissure_scan(fissure, grid, blocks=blocks, img_width=w):
        scan_entries, mode = fissure, f"fissure:{len(fissure)}"
    elif len(grid) >= 3:
        scan_entries, mode = grid, f"grid:{len(grid)}"
    else:
        scan = app.build_ocr_candidates(result, img_width=w, img_height=h)
        scan_entries = [
            {"text": t, "cx": cx, "cy": cy}
            for t, (cx, cy) in zip(
                scan, [app._estimate_candidate_layout(blocks, t) for t in scan]
            )
        ]
        mode = f"full:{len(scan)}"

    scan = [e["text"] for e in scan_entries]
    layouts = [(e["cx"], e["cy"]) for e in scan_entries]
    hits = app._sort_hits_by_screen_order(
        app._best_hit_per_base(app._gather_scan_hits(scan, layouts))
    )
    return {
        "path": os.path.basename(path),
        "mode": mode,
        "candidates": scan,
        "hits": [h["final_name"] for h in hits],
        "missed": [c for c in scan if not any(h["final_name"].startswith(
            app.wfm_dict.get(app._pick_dict_key_for_ocr(
                app._apply_relic_ocr_typos(app.normalize_text(c))
            ) or "", {}).get("real_cn_name", "???")
        ) for h in hits)],
    }


def main() -> int:
    app = load_app()
    paths: list[str] = []
    for folder in ASSET_DIRS:
        paths.extend(
            glob.glob(os.path.join(folder, "*Warframe*.png"))
            + glob.glob(os.path.join(folder, "*msedge*.png"))
        )
    paths = sorted(set(paths))
    if not paths:
        print("未找到测试截图 (*.png)")
        return 0

    failed = 0
    for path in paths:
        info = scan_image(app, path)
        print(f"\n=== {info['path']} [{info['mode']}] ===")
        for c in info["candidates"]:
            print(f"  cand: {c}")
        for name in info["hits"]:
            print(f"  hit:  {name}")
        unresolved = []
        for c in info["candidates"]:
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
            failed += 1
            print("  UNRESOLVED:", ", ".join(unresolved))
        else:
            print("  OK: 全部候选已解析")

    print(f"\n合计 {len(paths)} 张，未解析 {failed} 张")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
