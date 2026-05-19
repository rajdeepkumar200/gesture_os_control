"""Headless status panel - shows gesture & hand state without a video feed.

This is the default "stage" widget displayed in the main window. It lets
the user run GestureOS Pro without the camera preview taking over the
screen; the CV pipeline still runs in the background.
"""
from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget


class StatusPanel(QWidget):
    """Large status indicator: current gesture, hands, FPS, pending action."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumSize(560, 360)
        self.setStyleSheet("background: transparent;")

        self._gesture_label: str = "idle"
        self._gesture_color = QColor(120, 130, 140)
        self._hands_count: int = 0
        self._fps: float = 0.0
        self._pinch_strength: float = 0.0
        self._last_action: str = "—"
        self._pending_action: Optional[str] = None
        self._running: bool = False
        self._armed: bool = False

        # Pulse animation for active gestures.
        self._pulse: float = 0.0
        self._pulse_dir: float = 1.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(40)

    # ----------------------------------------------------------- updates
    def set_running(self, running: bool) -> None:
        self._running = running
        if not running:
            self._gesture_label = "stopped"
            self._gesture_color = QColor(120, 130, 140)
            self._armed = False
        self.update()

    def set_armed(self, armed: bool) -> None:
        self._armed = armed
        self.update()

    def update_gesture(
        self,
        labels: List[str],
        hands: int,
        fps: float,
        pinch_strength: float,
    ) -> None:
        if labels:
            self._gesture_label = labels[0]
            self._gesture_color = QColor(0, 200, 255)
        else:
            self._gesture_label = "—"
            self._gesture_color = QColor(80, 90, 100)
        self._hands_count = hands
        self._fps = fps
        self._pinch_strength = pinch_strength
        self.update()

    def set_last_action(self, action: str) -> None:
        self._last_action = action
        self.update()

    def set_pending(self, action: Optional[str]) -> None:
        self._pending_action = action
        self.update()

    # ----------------------------------------------------------- painting
    def _tick(self) -> None:
        self._pulse += 0.05 * self._pulse_dir
        if self._pulse >= 1.0:
            self._pulse, self._pulse_dir = 1.0, -1.0
        elif self._pulse <= 0.0:
            self._pulse, self._pulse_dir = 0.0, 1.0
        if self._gesture_label not in ("idle", "—", "stopped"):
            self.update()

    def paintEvent(self, _event):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        # Background gradient panel
        rect = self.rect().adjusted(8, 8, -8, -8)
        bg = QColor(24, 26, 30)
        p.setPen(QPen(QColor(50, 55, 65), 1))
        p.setBrush(bg)
        p.drawRoundedRect(rect, 14, 14)

        # Status dot (running indicator)
        dot_r = 9
        if not self._running:
            dot_color = QColor(180, 60, 60)
            status_text = "STOPPED"
        elif self._armed:
            dot_color = QColor(0, 220, 120)
            status_text = "ARMED"
        else:
            dot_color = QColor(230, 170, 40)
            status_text = "DISARMED \u2014 wave palm 5 s to arm"
        p.setBrush(dot_color)
        p.setPen(Qt.NoPen)
        p.drawEllipse(rect.left() + 22, rect.top() + 22, dot_r * 2, dot_r * 2)
        p.setPen(QColor(220, 220, 220))
        p.setFont(QFont("Segoe UI", 11, QFont.Bold))
        p.drawText(rect.left() + 46, rect.top() + 38, status_text)

        # FPS top-right
        p.setFont(QFont("Segoe UI", 11))
        p.setPen(QColor(180, 185, 195))
        p.drawText(rect.adjusted(0, 22, -22, 0), Qt.AlignTop | Qt.AlignRight,
                   f"{self._fps:5.1f} FPS   |   hands: {self._hands_count}")

        # Big gesture name in centre
        gesture_text = self._gesture_label.replace("_", " ").upper()
        # Pulsing color
        c = QColor(self._gesture_color)
        if self._gesture_label not in ("idle", "—", "stopped"):
            alpha = int(180 + 75 * self._pulse)
            c.setAlpha(alpha)
        p.setPen(c)
        p.setFont(QFont("Segoe UI", 36, QFont.Bold))
        gesture_rect = rect.adjusted(0, 70, 0, -120)
        p.drawText(gesture_rect, Qt.AlignCenter, gesture_text)

        # Subtitle under gesture
        p.setFont(QFont("Segoe UI", 10))
        p.setPen(QColor(150, 155, 165))
        p.drawText(rect.adjusted(0, gesture_rect.bottom() - rect.top() + 4, 0, 0),
                   Qt.AlignHCenter | Qt.AlignTop,
                   "Detected gesture")

        # Pinch strength bar near bottom
        bar_y = rect.bottom() - 92
        bar_w = rect.width() - 80
        bar_x = rect.left() + 40
        p.setPen(QPen(QColor(60, 65, 75), 1))
        p.setBrush(QColor(28, 30, 34))
        p.drawRoundedRect(bar_x, bar_y, bar_w, 14, 7, 7)
        fill_w = int(bar_w * max(0.0, min(1.0, self._pinch_strength)))
        if fill_w > 0:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 180, 255))
            p.drawRoundedRect(bar_x, bar_y, fill_w, 14, 7, 7)
        p.setPen(QColor(160, 165, 175))
        p.setFont(QFont("Segoe UI", 9))
        p.drawText(bar_x, bar_y - 4, "Pinch strength")

        # Last action
        p.setPen(QColor(200, 205, 215))
        p.setFont(QFont("Segoe UI", 11))
        p.drawText(rect.adjusted(40, 0, -40, -38),
                   Qt.AlignBottom | Qt.AlignLeft,
                   f"Last action:   {self._last_action}")

        # Pending action banner at the bottom
        if self._pending_action:
            banner = rect.adjusted(0, 0, 0, 0)
            banner.setTop(rect.bottom() - 30)
            p.setBrush(QColor(80, 30, 40))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(banner, 8, 8)
            p.setPen(QColor(255, 230, 230))
            p.setFont(QFont("Segoe UI", 11, QFont.Bold))
            p.drawText(banner, Qt.AlignCenter,
                       f"PENDING: {self._pending_action}   |   "
                       f"👍 to confirm   |   ✋ hold to cancel")

        p.end()
