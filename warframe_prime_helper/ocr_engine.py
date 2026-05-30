"""OCR 引擎封装。"""

import threading
from typing import Any

import numpy as np
from PIL import Image
from rapidocr_onnxruntime import RapidOCR


def pil_to_ocr_input(img: Image.Image) -> np.ndarray:
    """RapidOCR 不接受 PIL.Image，需转为 RGB ndarray。"""
    return np.asarray(img.convert("RGB"))


def run_ocr(ocr: Any, image: Any):
    if isinstance(image, Image.Image):
        image = pil_to_ocr_input(image)
    return ocr(image)


def create_ocr_with_timeout(timeout_sec: float = 20) -> tuple[Any | None, str | None]:
    result: dict[str, Any] = {"ocr": None, "error": None}

    def _worker():
        try:
            result["ocr"] = RapidOCR()
        except Exception as e:
            result["error"] = e

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    t.join(timeout_sec)
    if t.is_alive():
        return None, f"OCR 初始化超时（>{timeout_sec}s）"
    if result["error"] is not None:
        return None, str(result["error"])
    return result["ocr"], None
