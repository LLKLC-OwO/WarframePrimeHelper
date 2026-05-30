# PyInstaller runtime hook: native DLL search paths (onefile/onedir)
import os
import sys

if getattr(sys, "frozen", False):
    base = getattr(sys, "_MEIPASS", "")
    if base:
        # 勿将 numpy.libs 的 MSVCP140 置于 onnxruntime 之前，否则会触发 WinError 1114
        dirs = [
            os.path.join(base, "onnxruntime", "capi"),
            os.path.join(base, "cv2"),
            os.path.join(base, "shapely.libs"),
            base,
            os.path.join(base, "numpy.libs"),
        ]
        path_parts = []
        for d in dirs:
            if os.path.isdir(d):
                path_parts.append(d)
                if hasattr(os, "add_dll_directory"):
                    try:
                        os.add_dll_directory(d)
                    except OSError:
                        pass
        if path_parts:
            os.environ["PATH"] = os.pathsep.join(path_parts) + os.pathsep + os.environ.get(
                "PATH", ""
            )
