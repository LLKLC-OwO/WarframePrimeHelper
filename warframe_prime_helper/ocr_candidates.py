"""从 OCR 原始结果构建候选文本（多列、多行拼接）。"""

from warframe_prime_helper.text import normalize_text


def build_ocr_candidates(ocr_result: list) -> list[str]:
    candidates: list[str] = []
    blocks: list[dict] = []

    for line in ocr_result:
        if not isinstance(line, (list, tuple)) or len(line) < 2:
            continue

        raw_text = line[1]
        clean_text = normalize_text(raw_text)
        if clean_text:
            candidates.append(clean_text)

        box = line[0]
        if not isinstance(box, (list, tuple)) or len(box) < 4:
            continue

        try:
            xs = [float(p[0]) for p in box]
            ys = [float(p[1]) for p in box]
            xmin, xmax = min(xs), max(xs)
            ymin, ymax = min(ys), max(ys)
            cx = sum(xs) / len(xs)
            cy = sum(ys) / len(ys)
            width = xmax - xmin
            height = ymax - ymin
            if clean_text:
                blocks.append(
                    {
                        "clean": clean_text,
                        "cx": cx,
                        "cy": cy,
                        "width": width,
                        "height": height,
                    }
                )
        except Exception:
            continue

    if len(blocks) < 2:
        return list(dict.fromkeys(candidates))

    blocks.sort(key=lambda b: b["cx"])
    columns: list[dict] = []
    for block in blocks:
        placed = False
        for col in columns:
            x_threshold = max(85.0, col["avg_w"] * 1.35)
            if abs(block["cx"] - col["avg_cx"]) <= x_threshold:
                col["items"].append(block)
                n = len(col["items"])
                col["avg_cx"] = (col["avg_cx"] * (n - 1) + block["cx"]) / n
                col["avg_w"] = (col["avg_w"] * (n - 1) + max(block["width"], 1.0)) / n
                col["avg_h"] = (col["avg_h"] * (n - 1) + max(block["height"], 1.0)) / n
                placed = True
                break
        if not placed:
            columns.append(
                {
                    "items": [block],
                    "avg_cx": block["cx"],
                    "avg_w": max(block["width"], 1.0),
                    "avg_h": max(block["height"], 1.0),
                }
            )

    for col in columns:
        items = sorted(col["items"], key=lambda b: b["cy"])
        if not items:
            continue

        col_merged_all = "".join(x["clean"] for x in items if x.get("clean"))
        if col_merged_all:
            candidates.append(col_merged_all)

        group = [items[0]["clean"]]
        prev_cy = items[0]["cy"]
        line_gap_threshold = max(42.0, col["avg_h"] * 3.2)

        for item in items[1:]:
            if (item["cy"] - prev_cy) <= line_gap_threshold:
                group.append(item["clean"])
            else:
                merged = "".join(group)
                if merged:
                    candidates.append(merged)
                group = [item["clean"]]
            prev_cy = item["cy"]

        merged = "".join(group)
        if merged:
            candidates.append(merged)

        n = len(items)
        long_gap_limit = max(260.0, col["avg_h"] * 12.0)
        for i in range(n):
            base = items[i]
            combo = base["clean"]
            if combo:
                candidates.append(combo)
            for j in range(i + 1, min(i + 8, n)):
                if (items[j]["cy"] - base["cy"]) > long_gap_limit:
                    break
                combo += items[j]["clean"]
                if combo:
                    candidates.append(combo)

    return list(dict.fromkeys(candidates))
