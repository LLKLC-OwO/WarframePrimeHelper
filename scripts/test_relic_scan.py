"""用截图测试 OCR + 识别（全屏，无需打开 GUI）。"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
from PIL import Image
from rapidocr_onnxruntime import RapidOCR

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from wf9_vertical_optimized import PART_MAP, WFPriceHelperApp, WFM_DICT_PATH, PRICE_CACHE_FILE

DEFAULT_IMAGE = (
    r"C:\Users\Administrator\.cursor\projects\e-Projects\assets"
    r"\c__Users_Administrator_AppData_Roaming_Cursor_User_workspaceStorage_"
    r"empty-window_images_Warframe.x64.exe_20260529_091517-fa2ccbaa-53d3-4150-9487-f22eb69582ef.png"
)


def load_app_stub() -> WFPriceHelperApp:
    app = WFPriceHelperApp()
    app.withdraw()
    with open(os.path.join(ROOT, WFM_DICT_PATH), encoding="utf-8") as f:
        raw = json.load(f)
    app.wfm_dict = {}
    for v in raw.values():
        if isinstance(v, dict) and v.get("url_name"):
            app._register_dict_entry(v)
    app.sorted_keys = sorted(app.wfm_dict.keys(), key=len, reverse=True)
    app.part_map_entries = [
        (app.normalize_text(k), v, k) for k, v in PART_MAP.items()
    ]
    cache_path = os.path.join(ROOT, PRICE_CACHE_FILE)
    if os.path.exists(cache_path):
        app._load_price_cache(quiet=True)
    app.sorted_keys = sorted(app.wfm_dict.keys(), key=len, reverse=True)
    return app


def run(image_path: str) -> None:
    path = os.path.normpath(image_path)
    if not os.path.isfile(path):
        print(f"找不到图片: {path}")
        sys.exit(1)

    app = load_app_stub()
    img = Image.open(path).convert("RGB")
    if img.size[0] < 2000:
        img = img.resize((3840, 2160), Image.LANCZOS)
    full_w, full_h = img.size
    img_np = np.asarray(img)
    ocr = RapidOCR()
    result, _ = ocr(img_np)
    if not result:
        print("OCR 无结果")
        return

    _, blocks = app._extract_ocr_blocks(result)
    cell_texts = app._build_panel_cell_texts(blocks, full_w, full_h) if blocks else []
    grid = app.build_reward_grid_candidates(blocks, full_w, full_h, panel_only=False)
    fissure = app.build_fissure_reward_candidates(blocks, full_w, full_h)
    if len(fissure) >= 2:
        scan_entries = list(fissure)
        mode = f"裂缝报酬 {len(fissure)} 项"
    elif len(grid) >= 3:
        scan_entries = list(grid)
        seen = {e["text"] for e in scan_entries}
        for t in cell_texts:
            if t not in seen:
                cx, cy = app._estimate_candidate_layout(blocks, t)
                scan_entries.append({"text": t, "cx": cx, "cy": cy})
        mode = f"奖励格 {len(grid)} 格"
    else:
        cands = app.build_ocr_candidates(result, img_width=full_w, img_height=full_h)
        merged = list(dict.fromkeys(cands + cell_texts + [e["text"] for e in grid]))
        scan_entries = [
            {"text": t, "cx": cx, "cy": cy}
            for t, (cx, cy) in zip(
                merged, [app._estimate_candidate_layout(blocks, t) for t in merged]
            )
        ]
        mode = "全屏"

    scan = [e["text"] for e in scan_entries]
    layouts = [(e["cx"], e["cy"]) for e in scan_entries]

    print(f"图片: {path} ({full_w}x{full_h}) {mode}")
    print(f"候选 {len(scan)} 条，示例:")
    for c in scan[:8]:
        print(f"  · {c}")
    print("最佳识别:")
    for hit in app._sort_hits_by_screen_order(
        app._best_hit_per_base(app._gather_scan_hits(scan, layouts))
    ):
        print(f"  · {hit['final_name']}  [{hit['suffix']}]")


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_IMAGE)
