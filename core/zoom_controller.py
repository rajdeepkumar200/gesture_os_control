"""Zoom in / out via Ctrl + scroll wheel and Ctrl + +/- fallback."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

try:
    import pyautogui  # type: ignore
    pyautogui.FAILSAFE = False
    _HAS_PYAUTOGUI = True
except Exception:
    pyautogui = None
    _HAS_PYAUTOGUI = False


class ZoomController:
    """Simulates ``Ctrl + scroll`` to zoom the focused application."""

    def __init__(self, scroll_step: int = 200) -> None:
        self.scroll_step = scroll_step

    def zoom_in(self) -> None:
        if not _HAS_PYAUTOGUI:
            return
        try:
            pyautogui.keyDown("ctrl")
            pyautogui.scroll(self.scroll_step)
            pyautogui.keyUp("ctrl")
        except Exception:
            logger.exception("zoom_in failed")
        logger.info("Zoom in")

    def zoom_out(self) -> None:
        if not _HAS_PYAUTOGUI:
            return
        try:
            pyautogui.keyDown("ctrl")
            pyautogui.scroll(-self.scroll_step)
            pyautogui.keyUp("ctrl")
        except Exception:
            logger.exception("zoom_out failed")
        logger.info("Zoom out")
