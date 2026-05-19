"""Rule-based gesture classification.

Each :py:meth:`classify` call receives the list of currently detected
:class:`~core.hand_tracker.Hand` objects and returns a :class:`GestureFrame`
containing all *candidate* gesture labels that match this single frame.

The downstream :class:`core.gesture_state_machine.GestureStateMachine` is
responsible for temporal smoothing, cooldowns and edge detection.
"""
from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, List, Optional, Sequence, Tuple

from .hand_tracker import (
    Hand,
    INDEX_TIP,
    MIDDLE_TIP,
    RING_TIP,
    PINKY_TIP,
    THUMB_TIP,
    WRIST,
)

logger = logging.getLogger(__name__)


@dataclass
class GestureFrame:
    """Result of a single classification pass."""
    labels: List[str] = field(default_factory=list)
    cursor_xy: Optional[Tuple[float, float]] = None  # normalised 0-1
    pinch_strength: float = 0.0  # 0 -> open, 1 -> closed
    two_hand_distance: float = 0.0
    timestamp: float = field(default_factory=time.monotonic)

    def has(self, label: str) -> bool:
        return label in self.labels


class GestureClassifier:
    """Classifies hand poses into named gestures."""

    def __init__(
        self,
        pinch_threshold: float = 0.045,
        typing_motion_window: int = 12,
        typing_motion_min_oscillations: int = 4,
    ) -> None:
        self.pinch_threshold = pinch_threshold
        self._typing_history: Deque[Tuple[float, float]] = deque(maxlen=typing_motion_window)
        self._typing_min_osc = typing_motion_min_oscillations
        self._prev_two_hand_distance: Optional[float] = None

    # ----------------------------------------------------------- helpers
    @staticmethod
    def _is_open_palm(hand: Hand) -> bool:
        return all(hand.extended_fingers())

    @staticmethod
    def _is_fist(hand: Hand) -> bool:
        return not any(hand.extended_fingers())

    @staticmethod
    def _is_five_finger_pinch(hand: Hand, threshold: float = 0.07) -> bool:
        """All five fingertips converge to a tight cluster ("grabbing")."""
        tips_idx = (THUMB_TIP, INDEX_TIP, MIDDLE_TIP, RING_TIP, PINKY_TIP)
        tips = [hand.lm(t) for t in tips_idx]
        cx = sum(t.x for t in tips) / 5
        cy = sum(t.y for t in tips) / 5
        max_dist = max(
            ((t.x - cx) ** 2 + (t.y - cy) ** 2) ** 0.5 for t in tips
        )
        return max_dist < threshold

    @staticmethod
    def _is_thumbs_up(hand: Hand) -> bool:
        thumb, index, middle, ring, pinky = hand.extended_fingers()
        if not thumb or any((index, middle, ring, pinky)):
            return False
        # Thumb tip should be above the wrist
        return hand.lm(THUMB_TIP).y < hand.lm(WRIST).y - 0.05

    @staticmethod
    def _is_peace(hand: Hand) -> bool:
        thumb, index, middle, ring, pinky = hand.extended_fingers()
        return index and middle and not ring and not pinky

    @staticmethod
    def _is_point(hand: Hand) -> bool:
        thumb, index, middle, ring, pinky = hand.extended_fingers()
        return index and not middle and not ring and not pinky

    def _pinch_strength(self, hand: Hand) -> float:
        d = hand.distance(THUMB_TIP, INDEX_TIP)
        # Map [0, 2*threshold] -> [1, 0]
        return float(max(0.0, min(1.0, 1.0 - d / (2 * self.pinch_threshold))))

    def _is_pinch(self, hand: Hand) -> bool:
        return hand.distance(THUMB_TIP, INDEX_TIP) < self.pinch_threshold

    def _is_typing_motion(self, hands: Sequence[Hand]) -> bool:
        """Detect rapid up/down oscillation of four fingertips on either hand."""
        if not hands:
            return False
        # Track the dominant (first) hand average fingertip Y
        h = hands[0]
        avg_y = sum(h.lm(t).y for t in (INDEX_TIP, MIDDLE_TIP, RING_TIP, PINKY_TIP)) / 4
        self._typing_history.append((time.monotonic(), avg_y))
        if len(self._typing_history) < self._typing_history.maxlen:
            return False

        ys = [y for _, y in self._typing_history]
        # Count direction changes
        changes = 0
        for i in range(2, len(ys)):
            if (ys[i] - ys[i - 1]) * (ys[i - 1] - ys[i - 2]) < 0:
                changes += 1
        amplitude = max(ys) - min(ys)
        # All four fingers should be extended for "typing" pose
        all_extended = all(h.extended_fingers()[1:])
        return all_extended and changes >= self._typing_min_osc and amplitude > 0.03

    # ------------------------------------------------------------ public
    def classify(self, hands: Sequence[Hand]) -> GestureFrame:
        frame = GestureFrame()
        if not hands:
            self._prev_two_hand_distance = None
            return frame

        # Single-hand poses (consider the most confident hand)
        primary = max(hands, key=lambda h: h.score)
        frame.pinch_strength = self._pinch_strength(primary)
        # Cursor follows the index fingertip of the primary hand.
        idx_tip = primary.lm(INDEX_TIP)
        frame.cursor_xy = (idx_tip.x, idx_tip.y)

        # Five-finger pinch ("grab") is checked before two-finger pinch so it
        # takes priority when fingertips converge.
        five_pinch = self._is_five_finger_pinch(primary)
        two_pinch = self._is_pinch(primary)
        if five_pinch:
            frame.labels.append("five_finger_pinch")
        elif two_pinch:
            # Suppress two-finger pinch while a five-finger pinch is active to
            # avoid the delete + open conflict.
            frame.labels.append("pinch")
        if self._is_fist(primary):
            frame.labels.append("fist")
        if self._is_open_palm(primary):
            frame.labels.append("open_palm")
        if self._is_thumbs_up(primary):
            frame.labels.append("thumbs_up")
        if self._is_peace(primary):
            frame.labels.append("peace")
        if self._is_point(primary):
            frame.labels.append("point")

        if self._is_typing_motion(hands):
            frame.labels.append("four_finger_type")

        # Two-hand wrist distance is still surfaced for the status panel,
        # but two-hand zoom gestures have been replaced by single-hand
        # five_finger_pinch / spread (see GestureStateMachine).
        if len(hands) >= 2:
            a, b = hands[0], hands[1]
            frame.two_hand_distance = float(
                ((a.lm(WRIST).x - b.lm(WRIST).x) ** 2
                 + (a.lm(WRIST).y - b.lm(WRIST).y) ** 2) ** 0.5
            )
        self._prev_two_hand_distance = None

        return frame
