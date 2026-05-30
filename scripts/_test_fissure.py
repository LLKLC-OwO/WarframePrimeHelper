import json
import os
import sys

import numpy as np
from PIL import Image
from rapidocr_onnxruntime import RapidOCR

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from wf9_vertical_optimized import PART_MAP, WFPriceHelperApp, WFM_DICT_PATH, PRICE_CACHE_FILE

img_path = (
    r"C:\Users\Administrator\.cursor\projects\e-Projects\assets"
    r"\c__Users_Administrator_AppData_Roaming_Cursor_User_workspaceStorage_"
    r"empty-window_images_msedge.exe_20260529_103151-bc46ffcc-47b2-4e85-b12d-04ce2717bd19.png"
)

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
if os.path.exists(os.path.join(ROOT, PRICE_CACHE_FILE)):
    app._load_price_cache(quiet=True)
app.sorted_keys = sorted(app.wfm_dict.keys(), key=len, reverse=True)

img = Image.open(img_path).convert("RGB")
if img.size[0] < 2000:
    img = img.resize((3840, 2160), Image.LANCZOS)
w, h = img.size
result, _ = RapidOCR()(np.asarray(img))
_, blocks = app._extract_ocr_blocks(result)
fissure = app.build_fissure_reward_candidates(blocks, w, h)
scan = [e["text"] for e in fissure]
layouts = [(e["cx"], e["cy"]) for e in fissure]
lines = ["fissure:"] + scan + [""]
for e in fissure:
    g = e["text"]
    c = app._apply_relic_ocr_typos(app.normalize_text(g))
    dk = app._pick_dict_key_for_ocr(c)
    if dk:
        suf, cn = app._resolve_part_from_cell(c, dk, app.wfm_dict[dk])
        lines.append(f"  {g!r} -> {app.wfm_dict[dk]['real_cn_name']} {cn} [{suf}]")
    else:
        lines.append(f"  {g!r} -> NO KEY ({c})")
lines.append("")
lines.append("hits:")
for hit in app._sort_hits_by_screen_order(
    app._best_hit_per_base(app._gather_scan_hits(scan, layouts))
):
    lines.append(hit["final_name"])
open(os.path.join(ROOT, "scripts", "ocr_fissure.txt"), "w", encoding="utf-8").write(
    "\n".join(lines)
)
