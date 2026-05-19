"""Helper drawing routines for the live camera preview."""
from __future__ import annotations

from typing import Iterable, Tuple

import cv2
import numpy as np

from core.gesture_classifier import GestureFrame


def draw_hud(
    frame: np.ndarray,
    fps: float,
    gesture_frame: GestureFrame,
    current_action: str = "",
    pending_action: str | None = None,
) -> np.ndarray:
    """Overlay status text on the BGR frame.  Returns the modified frame."""
    h, w = frame.shape[:2]
    # Top bar
    cv2.rectangle(frame, (0, 0), (w, 36), (20, 20, 20), -1)
    cv2.putText(frame, f"FPS: {fps:5.1f}", (12, 24),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 120), 2, cv2.LINE_AA)
    label = "+".join(gesture_frame.labels) if gesture_frame.labels else "none"
    cv2.putText(frame, f"Gesture: {label}", (140, 24),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2, cv2.LINE_AA)

    if current_action:
        cv2.putText(frame, f"Action: {current_action}", (w // 2, 24),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 200, 0), 2, cv2.LINE_AA)

    # Pinch strength bar
    bar_w = 160
    cv2.rectangle(frame, (w - bar_w - 12, 8), (w - 12, 28), (60, 60, 60), 1)
    fill = int(bar_w * gesture_frame.pinch_strength)
    cv2.rectangle(frame, (w - bar_w - 12, 8), (w - bar_w - 12 + fill, 28),
                  (0, 180, 255), -1)
    cv2.putText(frame, "Pinch", (w - bar_w - 60, 24),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1, cv2.LINE_AA)

    if pending_action:
        cv2.rectangle(frame, (0, h - 40), (w, h), (20, 20, 80), -1)
        cv2.putText(frame, f"Pending: {pending_action} - thumbs up to confirm, open palm to cancel",
                    (12, h - 14), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)

    return frame


def draw_cursor(frame: np.ndarray, xy_norm: Tuple[float, float]) -> np.ndarray:
    h, w = frame.shape[:2]
    cx, cy = int(xy_norm[0] * w), int(xy_norm[1] * h)
    cv2.circle(frame, (cx, cy), 12, (0, 255, 0), 2)
    cv2.circle(frame, (cx, cy), 2, (0, 255, 0), -1)
    return frame
