"""Dual-hand virtual keyboard.

A frameless, always-on-top window that the user can hover over with both
hands. Two cursor "dots" track the index-fingertips of the two detected
hands; pinching with either hand presses the highlighted key.

The keyboard *does not* steal focus from other applications - keystrokes
are sent via the global :class:`KeyboardController` to whichever window had
focus before the keyboard was shown.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import Qt, QRect, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QBrush
from PySide6.QtWidgets import QWidget

from core.keyboard_controller import KeyboardController

logger = logging.getLogger(__name__)


# Keyboard layout (QWERTY).  Tuples represent (label, width_units).
# Default width unit is 1.
QWERTY_LOWER: List[List[Tuple[str, float]]] = [
    [("`", 1), ("1", 1), ("2", 1), ("3", 1), ("4", 1), ("5", 1),
     ("6", 1), ("7", 1), ("8", 1), ("9", 1), ("0", 1), ("-", 1),
     ("=", 1), ("BACKSPACE", 2)],
    [("TAB", 1.5), ("q", 1), ("w", 1), ("e", 1), ("r", 1), ("t", 1),
     ("y", 1), ("u", 1), ("i", 1), ("o", 1), ("p", 1), ("[", 1),
     ("]", 1), ("\\", 1.5)],
    [("CAPS", 1.75), ("a", 1), ("s", 1), ("d", 1), ("f", 1), ("g", 1),
     ("h", 1), ("j", 1), ("k", 1), ("l", 1), (";", 1), ("'", 1),
     ("ENTER", 2.25)],
    [("SHIFT", 2.25), ("z", 1), ("x", 1), ("c", 1), ("v", 1), ("b", 1),
     ("n", 1), ("m", 1), (",", 1), (".", 1), ("/", 1), ("SHIFT", 2.75)],
    [("CTRL", 1.25), ("WIN", 1.25), ("ALT", 1.25), ("SPACE", 6.5),
     ("ALT", 1.25), ("CTRL", 1.25)],
]

# Shifted character map for the number row & symbols.
SHIFT_MAP: Dict[str, str] = {
    "`": "~", "1": "!", "2": "@", "3": "#", "4": "$", "5": "%",
    "6": "^", "7": "&", "8": "*", "9": "(", "0": ")", "-": "_",
    "=": "+", "[": "{", "]": "}", "\\": "|", ";": ":", "'": "\"",
    ",": "<", ".": ">", "/": "?",
}


@dataclass
class Key:
    label: str
    rect: QRect
    is_special: bool


class VirtualKeyboardWindow(QWidget):
    """Frameless on-screen keyboard with pinch-to-press input."""

    keyPressed = Signal(str)  # emits final emitted text/special name

    KEY_PAD = 4

    def __init__(
        self,
        keyboard_controller: KeyboardController,
        scale: float = 1.0,
        opacity: float = 0.92,
        key_dwell_ms: int = 250,
        hover_dwell_ms: int = 500,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.kb = keyboard_controller
        self.scale = scale
        self._opacity = opacity
        self.key_dwell_ms = key_dwell_ms
        self.hover_dwell_ms = hover_dwell_ms

        self._keys: List[Key] = []
        self._hover_keys: Dict[int, Optional[Key]] = {0: None, 1: None}
        self._hover_start: Dict[int, Optional[float]] = {0: None, 1: None}
        self._pinching: Dict[int, bool] = {0: False, 1: False}
        self._last_press_at: Dict[str, float] = {}

        self.setWindowTitle("GestureOS Pro – Virtual Keyboard")
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.NoFocus)
        self.setWindowOpacity(self._opacity)

        self._rebuild_layout()

    # ----------------------------------------------------------- layout
    def _rebuild_layout(self) -> None:
        rows = QWERTY_LOWER
        unit_w = int(48 * self.scale)
        row_h = int(54 * self.scale)
        # Compute total width using the longest row.
        max_units = max(sum(w for _, w in row) for row in rows)
        total_w = int(max_units * unit_w) + self.KEY_PAD * 2
        total_h = row_h * len(rows) + self.KEY_PAD * 2
        self.resize(total_w, total_h)

        keys: List[Key] = []
        for row_idx, row in enumerate(rows):
            x = self.KEY_PAD
            y = self.KEY_PAD + row_idx * row_h
            for label, units in row:
                w = int(units * unit_w) - self.KEY_PAD
                rect = QRect(x, y, w, row_h - self.KEY_PAD)
                keys.append(Key(label=label, rect=rect, is_special=len(label) > 1))
                x += int(units * unit_w)
        self._keys = keys

    # ----------------------------------------------------------- API
    def update_pointers(self, pointers: List[Tuple[float, float, bool]]) -> None:
        """Receive normalised (0-1, in *window-local* space) pointer states.

        Each tuple = ``(x_norm, y_norm, is_pinching)``.
        A key is only pressable after the pointer has dwelled on it for
        ``hover_dwell_ms`` (default 500 ms) to prevent accidental rapid
        key-hopping.
        """
        now = time.monotonic()
        new_hover: Dict[int, Optional[Key]] = {0: None, 1: None}
        for i, (nx, ny, _pinch) in enumerate(pointers[:2]):
            px = int(nx * self.width())
            py = int(ny * self.height())
            for k in self._keys:
                if k.rect.contains(px, py):
                    new_hover[i] = k
                    break

        # Reset dwell timer when the hovered key changes.
        for i in (0, 1):
            if new_hover.get(i) != self._hover_keys.get(i):
                self._hover_start[i] = now

        # Edge-trigger press: pinch transitioned from False -> True over a key
        # that has been hovered for at least hover_dwell_ms.
        for i, (_, _, pinch) in enumerate(pointers[:2]):
            was = self._pinching.get(i, False)
            self._pinching[i] = pinch
            if pinch and not was and new_hover[i] is not None:
                started = self._hover_start.get(i)
                if started is not None and (now - started) * 1000 >= self.hover_dwell_ms:
                    self._press_key(new_hover[i])

        self._hover_keys = new_hover
        self.update()

    def _press_key(self, key: Key) -> None:
        now = time.monotonic()
        last = self._last_press_at.get(key.label, 0.0)
        if (now - last) * 1000 < self.key_dwell_ms:
            return
        self._last_press_at[key.label] = now

        label = key.label
        if label in self.kb.SPECIAL_KEYS:
            self.kb.press_key(label)
            self.keyPressed.emit(label)
            return
        if label in ("CTRL", "WIN", "ALT"):
            # Tap-and-release modifiers. We don't currently chord with hand
            # gestures, but emitting them is harmless.
            return
        # Regular printable character. Honour shift map for symbols.
        if self.kb.uppercase_active and label in SHIFT_MAP:
            self.kb.type_text(SHIFT_MAP[label])
            emitted = SHIFT_MAP[label]
        else:
            emitted = self.kb.press_key(label) or label
        self.keyPressed.emit(emitted or label)

    # ----------------------------------------------------------- painting
    def paintEvent(self, _event):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.fillRect(self.rect(), QColor(20, 20, 22))

        base = QColor(45, 47, 52)
        special = QColor(60, 65, 75)
        hover_color = QColor(0, 180, 255)
        font = QFont("Segoe UI", int(11 * self.scale), QFont.Bold)
        p.setFont(font)

        # Use object identity for hover comparison – `Key` is a regular
        # dataclass and not hashable.
        hover_ids = {id(k) for k in self._hover_keys.values() if k is not None}
        for k in self._keys:
            color = special if k.is_special else base
            if id(k) in hover_ids:
                color = hover_color
            p.fillRect(k.rect, color)
            p.setPen(QPen(QColor(80, 85, 95), 1))
            p.drawRect(k.rect)
            p.setPen(QPen(QColor(235, 235, 235)))
            label = k.label
            if not k.is_special:
                if self.kb.uppercase_active:
                    label = SHIFT_MAP.get(label, label.upper())
            p.drawText(k.rect, Qt.AlignCenter, label)

        # Status hint at top right
        status_parts = []
        if self.kb.shift_active:
            status_parts.append("SHIFT")
        if self.kb.caps_active:
            status_parts.append("CAPS")
        if status_parts:
            p.setPen(QColor(0, 220, 120))
            p.drawText(self.rect().adjusted(0, 4, -8, 0), Qt.AlignTop | Qt.AlignRight,
                       " | ".join(status_parts))

        # Draw hand pointers
        for i, key in self._hover_keys.items():
            if key is None:
                continue
            color = QColor(0, 255, 80) if self._pinching.get(i) else QColor(0, 220, 255)
            p.setPen(QPen(color, 3))
            p.setBrush(QBrush(Qt.NoBrush))
            p.drawEllipse(key.rect.center(), 18, 18)

        p.end()

    # ----------------------------------------------------- mouse fallback
    def mousePressEvent(self, ev):  # noqa: N802
        for k in self._keys:
            if k.rect.contains(ev.pos()):
                self._press_key(k)
                break
