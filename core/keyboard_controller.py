"""Simulated keystroke injection used by the virtual keyboard."""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import pyautogui  # type: ignore
    pyautogui.FAILSAFE = False
    _HAS_PYAUTOGUI = True
except Exception:  # pragma: no cover
    pyautogui = None
    _HAS_PYAUTOGUI = False


class KeyboardController:
    """Sends keystrokes to the OS-level focused application."""

    # PyAutoGUI key-name map for special keys
    SPECIAL_KEYS = {
        "BACKSPACE": "backspace",
        "ENTER": "enter",
        "SPACE": "space",
        "TAB": "tab",
        "ESC": "esc",
        "SHIFT": "shift",
        "CAPS": "capslock",
        "LEFT": "left",
        "RIGHT": "right",
        "UP": "up",
        "DOWN": "down",
    }

    def __init__(self) -> None:
        self._shift_active = False
        self._caps_active = False

    # ----------------------------------------------------------- modifiers
    def toggle_shift(self) -> bool:
        self._shift_active = not self._shift_active
        logger.debug("Shift -> %s", self._shift_active)
        return self._shift_active

    def toggle_caps(self) -> bool:
        self._caps_active = not self._caps_active
        logger.debug("Caps -> %s", self._caps_active)
        return self._caps_active

    @property
    def shift_active(self) -> bool:
        return self._shift_active

    @property
    def caps_active(self) -> bool:
        return self._caps_active

    @property
    def uppercase_active(self) -> bool:
        """Whether printed letters should be uppercase right now."""
        return self._shift_active ^ self._caps_active

    # ------------------------------------------------------------- press
    def press_key(self, key: str) -> Optional[str]:
        """Press a single key.

        ``key`` is either a single character (case is decided by current
        shift / caps state) or one of :data:`SPECIAL_KEYS`. Returns the actual
        character emitted (or None for special keys).
        """
        if not _HAS_PYAUTOGUI:
            logger.warning("PyAutoGUI not available; cannot press %r", key)
            return None

        if key in self.SPECIAL_KEYS:
            mapped = self.SPECIAL_KEYS[key]
            try:
                pyautogui.press(mapped, _pause=False)
            except Exception:
                logger.exception("press failed for %s", key)
            # Shift is "sticky-one-shot" – consumed after the next key.
            if key == "SHIFT":
                self._shift_active = not self._shift_active
            if key == "CAPS":
                self._caps_active = not self._caps_active
            return None

        # Regular character
        out = key.upper() if self.uppercase_active and key.isalpha() else key.lower() if key.isalpha() else key
        try:
            pyautogui.typewrite(out, interval=0, _pause=False)
        except Exception:
            logger.exception("typewrite failed for %r", out)

        # Auto-release shift after a character (like a real keyboard).
        if self._shift_active and not self._caps_active:
            self._shift_active = False
        return out

    def type_text(self, text: str, interval: float = 0.0) -> None:
        if not _HAS_PYAUTOGUI:
            return
        pyautogui.typewrite(text, interval=interval, _pause=False)
