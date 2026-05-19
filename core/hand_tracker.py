"""MediaPipe-backed hand tracker producing a clean domain model."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# MediaPipe is heavy; import lazily so unit tests / headless servers can load
# the module without it being installed.
try:
    import mediapipe as mp  # type: ignore
    # Newer mediapipe wheels (>= 0.10.30 on some Python builds) do not
    # auto-import the ``solutions`` sub-package, so do it explicitly.
    from mediapipe import solutions as _mp_solutions  # type: ignore

    _MP_HANDS = _mp_solutions.hands
    _MP_DRAW = _mp_solutions.drawing_utils
    _MP_STYLES = _mp_solutions.drawing_styles
    _HAS_MP = True
except Exception as _mp_import_err:  # pragma: no cover - mediapipe not installed
    logger.warning("MediaPipe unavailable: %s", _mp_import_err)
    _HAS_MP = False
    _MP_HANDS = None
    _MP_DRAW = None
    _MP_STYLES = None


# MediaPipe landmark indices
WRIST = 0
THUMB_TIP = 4
INDEX_MCP = 5
INDEX_PIP = 6
INDEX_TIP = 8
MIDDLE_MCP = 9
MIDDLE_PIP = 10
MIDDLE_TIP = 12
RING_MCP = 13
RING_PIP = 14
RING_TIP = 16
PINKY_MCP = 17
PINKY_PIP = 18
PINKY_TIP = 20

FINGER_TIPS = (INDEX_TIP, MIDDLE_TIP, RING_TIP, PINKY_TIP)
FINGER_PIPS = (INDEX_PIP, MIDDLE_PIP, RING_PIP, PINKY_PIP)


@dataclass(frozen=True)
class Landmark:
    x: float
    y: float
    z: float = 0.0


@dataclass
class Hand:
    """A single detected hand."""
    label: str  # "Left" | "Right"
    score: float
    landmarks: List[Landmark] = field(default_factory=list)

    # Helpers --------------------------------------------------------
    def lm(self, idx: int) -> Landmark:
        return self.landmarks[idx]

    def pixel(self, idx: int, image_shape: Tuple[int, int]) -> Tuple[int, int]:
        h, w = image_shape[:2]
        p = self.landmarks[idx]
        return int(p.x * w), int(p.y * h)

    def distance(self, a: int, b: int) -> float:
        la = self.landmarks[a]
        lb = self.landmarks[b]
        return float(np.hypot(la.x - lb.x, la.y - lb.y))

    def is_finger_extended(self, tip: int, pip: int) -> bool:
        """A finger is extended when its tip is above (smaller y) its PIP joint
        in image coordinates (origin = top-left).
        """
        return self.landmarks[tip].y < self.landmarks[pip].y

    def is_thumb_extended(self) -> bool:
        """Thumb extended check (mirrors for left / right hand)."""
        tip = self.landmarks[THUMB_TIP]
        ip = self.landmarks[3]
        mcp = self.landmarks[2]
        # Horizontal separation of tip vs MCP, accounting for handedness.
        if self.label == "Right":
            return tip.x < mcp.x and tip.x < ip.x
        return tip.x > mcp.x and tip.x > ip.x

    def extended_fingers(self) -> List[bool]:
        """[thumb, index, middle, ring, pinky] extended booleans."""
        return [
            self.is_thumb_extended(),
            self.is_finger_extended(INDEX_TIP, INDEX_PIP),
            self.is_finger_extended(MIDDLE_TIP, MIDDLE_PIP),
            self.is_finger_extended(RING_TIP, RING_PIP),
            self.is_finger_extended(PINKY_TIP, PINKY_PIP),
        ]


class HandTracker:
    """Thin facade over MediaPipe Hands."""

    def __init__(
        self,
        max_num_hands: int = 2,
        min_detection_confidence: float = 0.7,
        min_tracking_confidence: float = 0.6,
        model_complexity: int = 1,
    ) -> None:
        self.max_num_hands = max_num_hands
        self.min_detection_confidence = min_detection_confidence
        self.min_tracking_confidence = min_tracking_confidence
        self.model_complexity = model_complexity

        if not _HAS_MP:
            logger.error("mediapipe is not installed. HandTracker disabled.")
            self._hands = None
            return

        self._hands = _MP_HANDS.Hands(
            static_image_mode=False,
            max_num_hands=max_num_hands,
            model_complexity=model_complexity,
            min_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )

    # -------------------------------------------------------------- API
    def process(self, frame_bgr: np.ndarray) -> List[Hand]:
        if self._hands is None or frame_bgr is None:
            return []
        import cv2

        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        frame_rgb.flags.writeable = False
        try:
            result = self._hands.process(frame_rgb)
        except Exception:  # pragma: no cover
            logger.exception("MediaPipe process failed")
            return []

        hands: List[Hand] = []
        if not result.multi_hand_landmarks:
            return hands
        handednesses = result.multi_handedness or []
        for i, hand_lms in enumerate(result.multi_hand_landmarks):
            label = "Right"
            score = 1.0
            if i < len(handednesses):
                cls = handednesses[i].classification[0]
                # MediaPipe reports the label as seen by the camera; in mirrored
                # view, the user's right hand appears as "Left" - we swap so the
                # rest of the system thinks in *user* coordinates.
                label = "Right" if cls.label == "Left" else "Left"
                score = float(cls.score)
            landmarks = [Landmark(p.x, p.y, p.z) for p in hand_lms.landmark]
            hands.append(Hand(label=label, score=score, landmarks=landmarks))
        return hands

    def draw(self, frame_bgr: np.ndarray, hands: List[Hand]) -> np.ndarray:
        """Overlay landmarks on a frame (BGR, in-place safe)."""
        if not _HAS_MP or not hands:
            return frame_bgr
        import cv2
        h, w = frame_bgr.shape[:2]
        for hand in hands:
            for a, b in _MP_HANDS.HAND_CONNECTIONS:
                pa = hand.pixel(a, frame_bgr.shape)
                pb = hand.pixel(b, frame_bgr.shape)
                cv2.line(frame_bgr, pa, pb, (180, 180, 180), 2)
            for i, lm in enumerate(hand.landmarks):
                cx, cy = int(lm.x * w), int(lm.y * h)
                color = (0, 200, 255) if i in FINGER_TIPS or i == THUMB_TIP else (0, 255, 80)
                cv2.circle(frame_bgr, (cx, cy), 4, color, -1)
            wx, wy = hand.pixel(WRIST, frame_bgr.shape)
            cv2.putText(
                frame_bgr,
                f"{hand.label} {hand.score:.2f}",
                (wx - 20, max(20, wy - 10)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )
        return frame_bgr

    def close(self) -> None:
        if self._hands is not None:
            self._hands.close()
            self._hands = None
