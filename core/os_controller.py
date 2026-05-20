"""OS-level actions: open/close/delete, mouse control, etc.

Uses PyAutoGUI for cross-platform basics and pywin32 / send2trash for
Windows-specific functionality when available.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

try:
    import pyautogui  # type: ignore
    pyautogui.FAILSAFE = False
    _HAS_PYAUTOGUI = True
except Exception:  # pragma: no cover
    pyautogui = None
    _HAS_PYAUTOGUI = False

try:
    from send2trash import send2trash  # type: ignore
    _HAS_SEND2TRASH = True
except Exception:
    _HAS_SEND2TRASH = False

_IS_WIN = sys.platform.startswith("win")
if _IS_WIN:
    try:
        import win32gui  # type: ignore
        import win32con  # type: ignore
        _HAS_PYWIN32 = True
    except Exception:  # pragma: no cover
        _HAS_PYWIN32 = False
else:
    _HAS_PYWIN32 = False


class OSController:
    """Encapsulates all OS-side side effects."""

    def __init__(self, cursor_smoothing: float = 0.35, cursor_sensitivity: float = 1.6):
        self.cursor_smoothing = cursor_smoothing
        self.cursor_sensitivity = cursor_sensitivity
        self._screen_size: Optional[Tuple[int, int]] = None
        self._last_cursor: Optional[Tuple[float, float]] = None

    # ----------------------------------------------------------- screen
    def screen_size(self) -> Tuple[int, int]:
        if self._screen_size is None and _HAS_PYAUTOGUI:
            self._screen_size = pyautogui.size()
        return self._screen_size or (1920, 1080)

    # ----------------------------------------------------------- cursor
    def move_cursor_normalised(self, nx: float, ny: float) -> None:
        """Move cursor based on normalised (0-1) hand coords with smoothing."""
        if not _HAS_PYAUTOGUI:
            return
        w, h = self.screen_size()
        # Map normalised hand coords to screen. Apply sensitivity centred on (0.5, 0.5).
        cx = 0.5 + (nx - 0.5) * self.cursor_sensitivity
        cy = 0.5 + (ny - 0.5) * self.cursor_sensitivity
        target = (max(0.0, min(1.0, cx)) * w, max(0.0, min(1.0, cy)) * h)
        if self._last_cursor is not None:
            s = self.cursor_smoothing
            target = (
                self._last_cursor[0] * s + target[0] * (1 - s),
                self._last_cursor[1] * s + target[1] * (1 - s),
            )
        self._last_cursor = target
        try:
            pyautogui.moveTo(int(target[0]), int(target[1]), _pause=False)
        except Exception:  # pragma: no cover
            logger.debug("moveTo failed", exc_info=True)

    # ----------------------------------------------------------- mouse
    def click(self, button: str = "left") -> None:
        if not _HAS_PYAUTOGUI:
            return
        try:
            pyautogui.click(button=button, _pause=False)
            logger.info("Mouse click (%s)", button)
        except Exception:
            logger.exception("click failed")

    def double_click(self) -> None:
        if not _HAS_PYAUTOGUI:
            return
        try:
            pyautogui.doubleClick(_pause=False)
            logger.info("Mouse double click")
        except Exception:
            logger.exception("double_click failed")

    def press_enter(self) -> None:
        if _HAS_PYAUTOGUI:
            pyautogui.press("enter")

    def hotkey(self, *keys: str) -> None:
        if _HAS_PYAUTOGUI:
            pyautogui.hotkey(*keys)
            logger.info("Hotkey: %s", "+".join(keys))

    # ----------------------------------------------------------- windows
    def close_active_window(self) -> None:
        if _HAS_PYWIN32:
            try:
                hwnd = win32gui.GetForegroundWindow()
                if hwnd:
                    win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
                    logger.info("Closed window hwnd=%s", hwnd)
                    return
            except Exception:
                logger.exception("pywin32 close failed; falling back to Alt+F4")
        self.hotkey("alt", "f4")

    def active_window_title(self) -> str:
        if _HAS_PYWIN32:
            try:
                hwnd = win32gui.GetForegroundWindow()
                return win32gui.GetWindowText(hwnd) or ""
            except Exception:
                return ""
        return ""

    def foreground_window_rect(self) -> Optional[Tuple[int, int, int, int]]:
        """Return ``(x, y, w, h)`` of the foreground window, or ``None``.

        Used by features that need to anchor an overlay (e.g. the virtual
        keyboard) to whatever app the user is currently focused on.
        """
        if not _HAS_PYWIN32:
            return None
        try:
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd:
                return None
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            return (left, top, max(0, right - left), max(0, bottom - top))
        except Exception:
            logger.debug("foreground_window_rect failed", exc_info=True)
            return None

    # --------------------------------------------------------- launching
    def open_path(self, path: str | Path) -> bool:
        path = Path(path)
        if not path.exists():
            logger.warning("open_path: path does not exist: %s", path)
            return False
        try:
            if _IS_WIN:
                os.startfile(str(path))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
            logger.info("Opened path: %s", path)
            return True
        except Exception:
            logger.exception("Failed to open %s", path)
            return False

    def open_under_cursor(self) -> None:
        """Best-effort: simulate Enter (works for selected items, links, etc.)."""
        # Fallback chain: try double-click first.
        self.double_click()

    def open_url(self, url: str) -> None:
        webbrowser.open(url, new=2, autoraise=True)
        logger.info("Opened URL: %s", url)

    # ------------------------------------------------------------ delete
    def delete_path(self, path: str | Path) -> bool:
        path = Path(path)
        if not path.exists():
            logger.warning("delete_path: not found %s", path)
            return False
        try:
            if _HAS_SEND2TRASH:
                send2trash(str(path))
                logger.info("Sent to trash: %s", path)
                return True
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            logger.info("Permanently deleted: %s", path)
            return True
        except Exception:
            logger.exception("Failed to delete %s", path)
            return False

    def delete_selection(self) -> None:
        """Send the OS delete shortcut to remove the currently selected item.

        On Windows / most Linux DEs ``Delete`` moves the selection to the
        Recycle Bin / Trash.
        """
        self.hotkey("delete")
