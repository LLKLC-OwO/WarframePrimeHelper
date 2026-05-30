"""文本规范化（OCR 与字典键对齐）。"""

import unicodedata


def normalize_text(text: str | None) -> str:
    if text is None:
        return ""
    s = unicodedata.normalize("NFKC", str(text)).lower()
    for typo, fix in (("握图", "握柄"), ("握东", "握柄")):
        s = s.replace(typo, fix)
    return "".join(ch for ch in s if ch.isalnum() or ("\u4e00" <= ch <= "\u9fff"))
