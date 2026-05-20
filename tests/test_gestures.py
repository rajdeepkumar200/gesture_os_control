"""Tests for GestureClassifier + GestureStateMachine.

The state machine uses real wall-clock time, so tests pass tiny
thresholds (a few hundredths of a second) via the constructor instead
of sleeping for the production defaults of 1.5 / 2 / 5 seconds.
"""
from __future__ import annotations

import time

from core.gesture_classifier import GestureClassifier
from core.gesture_state_machine import GestureStateMachine
from core.hand_tracker import Hand, Landmark

from .conftest import shifted_open_palm


# =============================================================== classifier
def test_open_palm_detected(open_palm_hand):
    g = GestureClassifier()
    frame = g.classify([open_palm_hand])
    assert "open_palm" in frame.labels
    assert "fist" not in frame.labels


def test_fist_detected(fist_hand):
    g = GestureClassifier()
    frame = g.classify([fist_hand])
    assert "fist" in frame.labels
    assert "open_palm" not in frame.labels


def test_thumbs_up_detected(thumbs_up_hand):
    g = GestureClassifier()
    frame = g.classify([thumbs_up_hand])
    assert "thumbs_up" in frame.labels


def test_pinch_detected(pinch_hand):
    g = GestureClassifier(pinch_threshold=0.05)
    frame = g.classify([pinch_hand])
    assert "pinch" in frame.labels
    assert frame.pinch_strength > 0.5


def test_five_finger_pinch_detected(five_finger_pinch_hand):
    g = GestureClassifier()
    frame = g.classify([five_finger_pinch_hand])
    assert "five_finger_pinch" in frame.labels


# =================================================== state machine: arming
def _fast_sm(**overrides) -> GestureStateMachine:
    """State machine with very short timing windows for unit tests."""
    defaults = dict(
        smoothing_window=2,
        default_cooldown_ms=0,
        wave_window_s=0.20,
        wave_min_amplitude=0.10,
        wave_min_direction_changes=2,
        wave_cooldown_s=0.05,
        pinch_click_hold_s=0.05,
        zoom_out_hold_s=0.05,
        zoom_in_release_window_s=0.5,
        fist_hold_s=0.05,
        fist_slide_distance=0.15,
    )
    defaults.update(overrides)
    return GestureStateMachine(**defaults)


def test_state_machine_starts_disarmed(open_palm_hand):
    sm = _fast_sm()
    assert sm.armed is False
    # Even thumbs-up should not fire while disarmed.
    g = GestureClassifier()
    events = []
    for _ in range(4):
        events.extend(sm.update(g.classify([open_palm_hand])))
    assert all(e.name not in ("thumbs_up", "pinch_hold") for e in events)


def test_palm_wave_arms_state_machine():
    """Lateral oscillation of an open palm for >= wave_window_s arms."""
    g = GestureClassifier()
    sm = _fast_sm()
    events = []
    deadline = time.monotonic() + 0.6
    sign = 1
    while time.monotonic() < deadline:
        hand = shifted_open_palm(dx=0.10 * sign)
        events.extend(sm.update(g.classify([hand])))
        sign *= -1
        time.sleep(0.02)
    assert sm.armed is True
    assert any(e.name == "tracking_armed" for e in events)


def test_palm_wave_disarms_when_already_armed():
    g = GestureClassifier()
    sm = _fast_sm(start_armed=True)
    events = []
    deadline = time.monotonic() + 0.6
    sign = 1
    while time.monotonic() < deadline:
        events.extend(sm.update(g.classify([shifted_open_palm(dx=0.10 * sign)])))
        sign *= -1
        time.sleep(0.02)
    assert sm.armed is False
    assert any(e.name == "tracking_disarmed" for e in events)


# ============================================ state machine: hold gestures
def test_pinch_hold_emits_click(pinch_hand):
    g = GestureClassifier(pinch_threshold=0.05)
    sm = _fast_sm(start_armed=True)
    events = []
    deadline = time.monotonic() + 0.20
    while time.monotonic() < deadline:
        events.extend(sm.update(g.classify([pinch_hand])))
        time.sleep(0.01)
    assert sum(1 for e in events if e.name == "pinch_hold") == 1


def test_pinch_hold_does_not_fire_when_disarmed(pinch_hand):
    g = GestureClassifier(pinch_threshold=0.05)
    sm = _fast_sm()  # disarmed
    events = []
    deadline = time.monotonic() + 0.20
    while time.monotonic() < deadline:
        events.extend(sm.update(g.classify([pinch_hand])))
        time.sleep(0.01)
    assert not any(e.name == "pinch_hold" for e in events)


def test_five_finger_pinch_hold_emits_zoom_out(five_finger_pinch_hand):
    g = GestureClassifier()
    sm = _fast_sm(start_armed=True)
    events = []
    deadline = time.monotonic() + 0.30
    while time.monotonic() < deadline:
        events.extend(sm.update(g.classify([five_finger_pinch_hand])))
        time.sleep(0.01)
    assert any(e.name == "five_finger_pinch_hold" for e in events)


def test_five_finger_spread_emits_zoom_in_after_cluster(five_finger_pinch_hand, open_palm_hand):
    g = GestureClassifier()
    sm = _fast_sm(start_armed=True)
    events = []
    # Hold cluster long enough to mark "was_clustered".
    deadline = time.monotonic() + 0.10
    while time.monotonic() < deadline:
        events.extend(sm.update(g.classify([five_finger_pinch_hand])))
        time.sleep(0.01)
    # Now release into open palm within the spread window.
    for _ in range(4):
        events.extend(sm.update(g.classify([open_palm_hand])))
        time.sleep(0.01)
    assert any(e.name == "five_finger_spread" for e in events)


def test_fist_slide_emits_close(fist_hand):
    g = GestureClassifier()
    sm = _fast_sm(start_armed=True)
    events = []
    # Hold the fist for >= fist_hold_s.
    deadline = time.monotonic() + 0.10
    while time.monotonic() < deadline:
        events.extend(sm.update(g.classify([fist_hand])))
        time.sleep(0.01)
    # Now slide the fist far to one side.
    moved_lms = [Landmark(p.x + 0.30, p.y, p.z) for p in fist_hand.landmarks]
    moved = Hand(label="Right", score=0.99, landmarks=moved_lms)
    for _ in range(3):
        events.extend(sm.update(g.classify([moved])))
        time.sleep(0.01)
    assert any(e.name == "fist_slide" for e in events)


def test_fist_slide_requires_full_hold(fist_hand):
    """Sliding the fist before the hold completes must NOT close anything."""
    g = GestureClassifier()
    sm = _fast_sm(start_armed=True, fist_hold_s=2.0)  # deliberately long hold
    events = []
    # Slide immediately; only a few frames before sliding.
    sm.update(g.classify([fist_hand]))
    moved_lms = [Landmark(p.x + 0.30, p.y, p.z) for p in fist_hand.landmarks]
    moved = Hand(label="Right", score=0.99, landmarks=moved_lms)
    for _ in range(3):
        events.extend(sm.update(g.classify([moved])))
        time.sleep(0.01)
    assert not any(e.name == "fist_slide" for e in events)


def test_thumbs_up_rising_edge(thumbs_up_hand):
    g = GestureClassifier()
    sm = _fast_sm(start_armed=True, default_cooldown_ms=10_000)
    events = []
    for _ in range(6):
        events.extend(sm.update(g.classify([thumbs_up_hand])))
    assert sum(1 for e in events if e.name == "thumbs_up") == 1


def test_clap_detected(open_palm_hand):
    g = GestureClassifier()
    # Create a second hand far to the right.
    right_lms = [Hand(label="Left", score=0.99, landmarks=[Landmark(p.x + 0.5, p.y, p.z) for p in open_palm_hand.landmarks])]
    right = right_lms[0]
    # Fill clap history with far-apart hands.
    for _ in range(12):
        g.classify([open_palm_hand, right])
    # Bring hands together.
    close_right_lms = [Landmark(p.x - 0.4, p.y, p.z) for p in right.landmarks]
    close_right = Hand(label="Left", score=0.99, landmarks=close_right_lms)
    frame = g.classify([open_palm_hand, close_right])
    assert "clap" in frame.labels


def test_clap_rising_edge(open_palm_hand):
    g = GestureClassifier()
    sm = _fast_sm(start_armed=True, default_cooldown_ms=10_000)
    right_lms = [Landmark(p.x + 0.5, p.y, p.z) for p in open_palm_hand.landmarks]
    right = Hand(label="Left", score=0.99, landmarks=right_lms)
    # Fill history with far-apart hands.
    for _ in range(12):
        g.classify([open_palm_hand, right])
    events = []
    close_right_lms = [Landmark(p.x - 0.4, p.y, p.z) for p in right_lms]
    close_right = Hand(label="Left", score=0.99, landmarks=close_right_lms)
    for _ in range(6):
        events.extend(sm.update(g.classify([open_palm_hand, close_right])))
    assert sum(1 for e in events if e.name == "clap") == 1
