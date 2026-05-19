"""Shared pytest fixtures and helpers."""
from __future__ import annotations

import sys
from pathlib import Path

# Make ``gesture_os_pro`` importable when running ``pytest`` from the repo root.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from typing import List

import pytest

from core.hand_tracker import Hand, Landmark


def make_landmarks(values: List[tuple]) -> List[Landmark]:
    return [Landmark(x, y, 0.0) for x, y in values]


def _baseline_hand_landmarks(open_palm: bool = True) -> List[Landmark]:
    """Construct a synthetic right-hand pose.

    Image coords are normalised; origin = top-left, y axis grows downward.
    For an open palm we want fingertips above their PIP joints (smaller y).
    """
    # All zeros baseline; we'll overwrite indices we care about.
    lms = [Landmark(0.5, 0.5, 0.0)] * 21
    # Wrist
    lms[0] = Landmark(0.5, 0.9, 0.0)
    # Thumb (idx 1..4). For right hand, thumb tip should be left of MCP.
    lms[1] = Landmark(0.45, 0.85, 0.0)
    lms[2] = Landmark(0.42, 0.82, 0.0)  # MCP
    lms[3] = Landmark(0.40, 0.78, 0.0)  # IP
    lms[4] = Landmark(0.38, 0.74, 0.0)  # tip
    # Index 5..8 (MCP, PIP, DIP, TIP)
    lms[5] = Landmark(0.48, 0.7, 0.0)
    lms[6] = Landmark(0.48, 0.6, 0.0)
    lms[7] = Landmark(0.48, 0.5, 0.0)
    lms[8] = Landmark(0.48, 0.4 if open_palm else 0.65, 0.0)
    # Middle 9..12
    lms[9] = Landmark(0.5, 0.7, 0.0)
    lms[10] = Landmark(0.5, 0.6, 0.0)
    lms[11] = Landmark(0.5, 0.5, 0.0)
    lms[12] = Landmark(0.5, 0.4 if open_palm else 0.65, 0.0)
    # Ring 13..16
    lms[13] = Landmark(0.52, 0.7, 0.0)
    lms[14] = Landmark(0.52, 0.6, 0.0)
    lms[15] = Landmark(0.52, 0.5, 0.0)
    lms[16] = Landmark(0.52, 0.4 if open_palm else 0.65, 0.0)
    # Pinky 17..20
    lms[17] = Landmark(0.54, 0.7, 0.0)
    lms[18] = Landmark(0.54, 0.6, 0.0)
    lms[19] = Landmark(0.54, 0.5, 0.0)
    lms[20] = Landmark(0.54, 0.4 if open_palm else 0.65, 0.0)
    return lms


@pytest.fixture
def open_palm_hand() -> Hand:
    return Hand(label="Right", score=0.99, landmarks=_baseline_hand_landmarks(open_palm=True))


@pytest.fixture
def fist_hand() -> Hand:
    lms = _baseline_hand_landmarks(open_palm=False)
    # Tuck thumb so it is not extended either: place tip to right of MCP.
    lms[4] = Landmark(0.50, 0.80, 0.0)
    return Hand(label="Right", score=0.99, landmarks=lms)


@pytest.fixture
def thumbs_up_hand() -> Hand:
    lms = _baseline_hand_landmarks(open_palm=False)
    # Thumb extended upward (tip far above wrist), other fingers folded.
    lms[4] = Landmark(0.40, 0.30, 0.0)
    lms[3] = Landmark(0.42, 0.45, 0.0)
    lms[2] = Landmark(0.44, 0.55, 0.0)
    return Hand(label="Right", score=0.99, landmarks=lms)


@pytest.fixture
def pinch_hand() -> Hand:
    lms = _baseline_hand_landmarks(open_palm=True)
    # Bring index tip onto thumb tip
    lms[8] = Landmark(0.385, 0.745, 0.0)
    return Hand(label="Right", score=0.99, landmarks=lms)


@pytest.fixture
def five_finger_pinch_hand() -> Hand:
    """All five fingertips clustered around (0.5, 0.5)."""
    lms = [Landmark(0.5, 0.5, 0.0) for _ in range(21)]
    lms[0] = Landmark(0.5, 0.9, 0.0)
    # Cluster all fingertips very tightly.
    for tip in (4, 8, 12, 16, 20):
        lms[tip] = Landmark(0.500 + (tip * 0.0005), 0.500, 0.0)
    return Hand(label="Right", score=0.99, landmarks=lms)


def shifted_open_palm(dx: float, dy: float = 0.0) -> Hand:
    """Open palm displaced by ``dx, dy`` in normalised coords (helper)."""
    lms = _baseline_hand_landmarks(open_palm=True)
    lms = [Landmark(p.x + dx, p.y + dy, p.z) for p in lms]
    return Hand(label="Right", score=0.99, landmarks=lms)
