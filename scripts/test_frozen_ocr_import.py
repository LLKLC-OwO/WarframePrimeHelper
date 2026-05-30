import os
import sys

if getattr(sys, "frozen", False):
    base = getattr(sys, "_MEIPASS", "")
    capi = os.path.join(base, "onnxruntime", "capi")
    if os.path.isdir(capi) and hasattr(os, "add_dll_directory"):
        os.add_dll_directory(capi)
        os.environ["PATH"] = capi + os.pathsep + os.environ.get("PATH", "")

from rapidocr_onnxruntime import RapidOCR

RapidOCR()
print("OCR_IMPORT_OK")
