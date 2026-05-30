"""Windows 多屏截图区域检测。"""

import ctypes
from ctypes import wintypes


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", RECT),
        ("rcWork", RECT),
        ("dwFlags", wintypes.DWORD),
    ]


def get_monitor_rects() -> list[tuple[int, int, int, int]]:
    user32 = ctypes.windll.user32
    monitors: list[tuple[int, int, int, int]] = []
    enum_proc = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HANDLE, wintypes.HDC, ctypes.POINTER(RECT), wintypes.LPARAM
    )

    def _callback(hmonitor, _hdc, _lprc, _lparam):
        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(MONITORINFO)
        if user32.GetMonitorInfoW(hmonitor, ctypes.byref(mi)):
            r = mi.rcMonitor
            monitors.append((r.left, r.top, r.right, r.bottom))
        return True

    user32.EnumDisplayMonitors(0, 0, enum_proc(_callback), 0)
    return monitors


def find_warframe_window() -> int:
    user32 = ctypes.windll.user32
    hwnds: list[int] = []
    enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _callback(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        if "warframe" in buf.value.lower():
            hwnds.append(hwnd)
        return True

    user32.EnumWindows(enum_proc(_callback), 0)
    return hwnds[0] if hwnds else user32.GetForegroundWindow()


def get_window_rect(hwnd: int) -> tuple[int, int, int, int] | None:
    if not hwnd:
        return None
    rect = RECT()
    if not ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    return (rect.left, rect.top, rect.right, rect.bottom)


def rect_overlap_area(
    a: tuple[int, int, int, int], b: tuple[int, int, int, int]
) -> int:
    left = max(a[0], b[0])
    top = max(a[1], b[1])
    right = min(a[2], b[2])
    bottom = min(a[3], b[3])
    if right <= left or bottom <= top:
        return 0
    return (right - left) * (bottom - top)


class CaptureService:
    """根据 Warframe 窗口所在显示器决定截图 bbox。"""

    def __init__(self, fallback_bbox: list[int] | None = None):
        self.fallback_bbox = fallback_bbox or [0, 0, 1920, 1080]
        self._last_monitor: int | None = None

    def get_bbox(self, on_monitor_locked=None) -> tuple[int, int, int, int]:
        monitors = get_monitor_rects()
        if not monitors:
            return tuple(self.fallback_bbox)  # type: ignore[return-value]

        hwnd = find_warframe_window()
        window_rect = get_window_rect(hwnd)
        best_idx = 0

        if window_rect:
            best_area = -1
            for idx, mon in enumerate(monitors):
                area = rect_overlap_area(window_rect, mon)
                if area > best_area:
                    best_area = area
                    best_idx = idx

        if self._last_monitor != best_idx:
            self._last_monitor = best_idx
            if on_monitor_locked:
                on_monitor_locked(best_idx)

        return monitors[best_idx]
