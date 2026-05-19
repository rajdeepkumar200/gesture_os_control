"""Temporal smoothing, cooldowns and edge-detection for gestures.

Converts raw per-frame :class:`GestureFrame` outputs into discrete
:class:`GestureEvent` instances which are then dispatched to actions.

The machine is *armed* / *disarmed* by waving an open palm horizontally
for a configurable duration. While disarmed every gesture (and the OS
cursor controlled by the worker) is suppressed -- only the wave gesture
is observed. This prevents accidental tracking when the user simply has
their hands in frame.

Gestures emitted (after the spec update):
    * ``tracking_armed`` / ``tracking_disarmed`` -- emitted on each
      successful palm-wave toggle.
    * ``pinch_hold`` -- thumb + index pinch held for >= 1.5 s.
    * ``five_finger_pinch_hold`` -- all five fingertips clustered for
      >= 2 s; fires repeatedly while held (with cooldown) for zoom-out.
    * ``five_finger_spread`` -- after a five_finger_pinch hold, fingers
      spreading back out within a short window emits this once for
      zoom-in.
    * ``fist_slide`` -- fist held for >= 2 s then translated by at least
      ``fist_slide_distance`` (normalised); fires once per slide.
    * ``thumbs_up`` -- rising-edge confirm.
    * ``open_palm`` -- held >= ``open_palm_hold_ms`` for cancel.
    * ``peace`` -- rising edge (toggle keyboard).
    * ``four_finger_type`` -- rising edge (search).
"""
from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, List, Optional, Tuple

from .gesture_classifier import GestureFrame

logger = logging.getLogger(__name__)


@dataclass
class GestureEvent:
    name: str
    timestamp: float
    cursor_xy: Optional[tuple] = None
    metadata: Optional[dict] = None


class GestureStateMachine:
    """Smooths per-frame gesture detections and synthesises temporal gestures.

    Notes
    -----
    * "Majority" smoothing means a label must appear in at least
      ``majority_ratio`` of the last ``smoothing_window`` frames before
      it is considered active. This filters out single-frame flickers
      from MediaPipe.
    * All hold thresholds are configurable so tests can drive the
      machine with real-time but very small windows.
    """

    def __init__(
        self,
        smoothing_window: int = 5,
        default_cooldown_ms: int = 700,
        per_gesture_cooldown_ms: Optional[Dict[str, int]] = None,
        majority_ratio: float = 0.6,
        # Wave-to-arm tunables.
        wave_window_s: float = 5.0,
        wave_min_amplitude: float = 0.18,
        wave_min_direction_changes: int = 4,
        wave_cooldown_s: float = 1.5,
        # Pinch-hold tunables.
        pinch_click_hold_s: float = 1.5,
        # Five-finger-pinch tunables.
        zoom_out_hold_s: float = 2.0,
        zoom_in_release_window_s: float = 1.0,
        # Fist-slide tunables.
        fist_hold_s: float = 2.0,
        fist_slide_distance: float = 0.20,
        # Initial state.
        start_armed: bool = False,
    ) -> None:
        self.smoothing_window = max(1, smoothing_window)
        self.default_cooldown_ms = default_cooldown_ms
        self.per_gesture_cooldown_ms = per_gesture_cooldown_ms or {}
        self.majority_ratio = majority_ratio

        # Tunables -------------------------------------------------------
        self.wave_window_s = wave_window_s
        self.wave_min_amplitude = wave_min_amplitude
        self.wave_min_direction_changes = wave_min_direction_changes
        self.wave_cooldown_s = wave_cooldown_s
        self.pinch_click_hold_s = pinch_click_hold_s
        self.zoom_out_hold_s = zoom_out_hold_s
        self.zoom_in_release_window_s = zoom_in_release_window_s
        self.fist_hold_s = fist_hold_s
        self.fist_slide_distance = fist_slide_distance

        # Public state ---------------------------------------------------
        self.armed: bool = start_armed

        # Internal state -------------------------------------------------
        self._history: Deque[List[str]] = deque(maxlen=self.smoothing_window)
        self._active: Dict[str, bool] = {}
        self._last_fired_at: Dict[str, float] = {}

        # Wave detection (palm wave -> toggle armed).
        self._wave_history: Deque[Tuple[float, float]] = deque()
        self._last_wave_emit_at: float = 0.0

        # Pinch hold (left click).
        self._pinch_started_at: Optional[float] = None
        self._pinch_hold_emitted: bool = False

        # Five-finger pinch hold (zoom out) and release window (zoom in).
        self._five_pinch_started_at: Optional[float] = None
        self._five_pinch_was_clustered: bool = False
        self._five_pinch_release_window_until: float = 0.0

        # Fist hold + slide (close window).
        self._fist_started_at: Optional[float] = None
        self._fist_hold_armed: bool = False
        self._fist_anchor_xy: Optional[Tuple[float, float]] = None

        # Open-palm hold (cancel).
        self._open_palm_started_at: Optional[float] = None

    # ----------------------------------------------------------- helpers
    def _cooldown_ms(self, name: str) -> int:
        return int(self.per_gesture_cooldown_ms.get(name, self.default_cooldown_ms))

    def _is_majority(self, name: str) -> bool:
        if not self._history:
            return False
        count = sum(1 for labels in self._history if name in labels)
        return count >= max(1, int(self.majority_ratio * len(self._history)))

    def _can_fire(self, name: str, now: float) -> bool:
        cd = self._cooldown_ms(name) / 1000.0
        return (now - self._last_fired_at.get(name, 0.0)) >= cd

    def _mark_fired(self, name: str, now: float) -> None:
        self._last_fired_at[name] = now

    def _reset_holds(self) -> None:
        self._pinch_started_at = None
        self._pinch_hold_emitted = False
        self._five_pinch_started_at = None
        self._five_pinch_was_clustered = False
        self._five_pinch_release_window_until = 0.0
        self._fist_started_at = None
        self._fist_hold_armed = False
        self._fist_anchor_xy = None
        self._open_palm_started_at = None

    # ------------------------------------------------------------ public
    def update(self, frame: GestureFrame, open_palm_hold_ms: int = 1500) -> List[GestureEvent]:
        now = time.monotonic()
        self._history.append(list(frame.labels))
        events: List[GestureEvent] = []

        # ------------------- 1) Wave-to-arm/disarm --------------------
        # Always evaluated, regardless of armed state -- this is the only
        # way for the user to bring the system in or out of tracking.
        wave_event = self._update_wave(frame, now)
        if wave_event is not None:
            events.append(wave_event)
            return events  # avoid spurious gestures on the toggling frame

        # If the system is *not* armed, suppress all other gestures.
        if not self.armed:
            self._reset_holds()
            return events

        # ------------------- 2) Pinch hold (1.5s -> click) ------------
        events.extend(self._update_pinch_hold(frame, now))

        # ------------------- 3) Five-finger pinch hold / spread -------
        events.extend(self._update_five_finger(frame, now))

        # ------------------- 4) Fist hold + slide ---------------------
        events.extend(self._update_fist_slide(frame, now))

        # ------------------- 5) Misc rising-edge / hold gestures ------
        events.extend(self._update_misc(frame, now, open_palm_hold_ms))

        return events

    # =========================================================== wave
    def _update_wave(self, frame: GestureFrame, now: float) -> Optional[GestureEvent]:
        """Detect lateral palm-wave for ``wave_window_s``; toggles ``armed``."""
        if "open_palm" in frame.labels and frame.cursor_xy is not None:
            self._wave_history.append((now, float(frame.cursor_xy[0])))
        else:
            # Open palm broken -> wave attempt aborted.
            self._wave_history.clear()
            return None

        cutoff = now - self.wave_window_s
        while self._wave_history and self._wave_history[0][0] < cutoff:
            self._wave_history.popleft()

        # Need a (nearly) full window of samples.
        if not self._wave_history:
            return None
        span = now - self._wave_history[0][0]
        if span < self.wave_window_s - 0.05:
            return None

        xs = [x for _, x in self._wave_history]
        amplitude = max(xs) - min(xs)
        changes = 0
        for i in range(2, len(xs)):
            if (xs[i] - xs[i - 1]) * (xs[i - 1] - xs[i - 2]) < 0:
                changes += 1

        if (
            amplitude >= self.wave_min_amplitude
            and changes >= self.wave_min_direction_changes
            and (now - self._last_wave_emit_at) >= self.wave_cooldown_s
        ):
            self.armed = not self.armed
            self._last_wave_emit_at = now
            self._wave_history.clear()
            self._history.clear()
            self._active.clear()
            self._reset_holds()
            name = "tracking_armed" if self.armed else "tracking_disarmed"
            logger.info("Palm wave detected -> %s", name)
            return GestureEvent(name=name, timestamp=now, cursor_xy=frame.cursor_xy)

        return None

    # ====================================================== pinch hold
    def _update_pinch_hold(self, frame: GestureFrame, now: float) -> List[GestureEvent]:
        events: List[GestureEvent] = []
        pinch_now = self._is_majority("pinch")
        if pinch_now:
            if self._pinch_started_at is None:
                self._pinch_started_at = now
                self._pinch_hold_emitted = False
            elif (
                not self._pinch_hold_emitted
                and (now - self._pinch_started_at) >= self.pinch_click_hold_s
                and self._can_fire("pinch_hold", now)
            ):
                events.append(GestureEvent(
                    name="pinch_hold", timestamp=now, cursor_xy=frame.cursor_xy,
                ))
                self._mark_fired("pinch_hold", now)
                self._pinch_hold_emitted = True
        else:
            self._pinch_started_at = None
            self._pinch_hold_emitted = False
        return events

    # ============================================ five-finger pinch / spread
    def _update_five_finger(self, frame: GestureFrame, now: float) -> List[GestureEvent]:
        events: List[GestureEvent] = []
        clustered = self._is_majority("five_finger_pinch")

        if clustered:
            if self._five_pinch_started_at is None:
                self._five_pinch_started_at = now
                self._five_pinch_was_clustered = True
            held_for = now - self._five_pinch_started_at
            if held_for >= self.zoom_out_hold_s and self._can_fire("five_finger_pinch_hold", now):
                events.append(GestureEvent(
                    name="five_finger_pinch_hold",
                    timestamp=now,
                    cursor_xy=frame.cursor_xy,
                    metadata={"held_s": held_for},
                ))
                self._mark_fired("five_finger_pinch_hold", now)
        else:
            # Just released? Open a window during which a transition to
            # ``open_palm`` will count as a spread (zoom in).
            if self._five_pinch_was_clustered:
                self._five_pinch_release_window_until = now + self.zoom_in_release_window_s
            self._five_pinch_started_at = None
            self._five_pinch_was_clustered = False

            if (
                "open_palm" in frame.labels
                and now <= self._five_pinch_release_window_until
                and self._can_fire("five_finger_spread", now)
            ):
                events.append(GestureEvent(
                    name="five_finger_spread", timestamp=now, cursor_xy=frame.cursor_xy,
                ))
                self._mark_fired("five_finger_spread", now)
                self._five_pinch_release_window_until = 0.0
        return events

    # =================================================== fist hold + slide
    def _update_fist_slide(self, frame: GestureFrame, now: float) -> List[GestureEvent]:
        events: List[GestureEvent] = []
        fist_now = self._is_majority("fist")

        if not fist_now:
            self._fist_started_at = None
            self._fist_hold_armed = False
            self._fist_anchor_xy = None
            return events

        if self._fist_started_at is None:
            self._fist_started_at = now
            self._fist_hold_armed = False
            self._fist_anchor_xy = frame.cursor_xy
            return events

        if not self._fist_hold_armed:
            if (now - self._fist_started_at) >= self.fist_hold_s:
                self._fist_hold_armed = True
                # Re-anchor at the moment the hold completes so distance
                # measures "slide after hold", not total drift.
                self._fist_anchor_xy = frame.cursor_xy
            return events

        # Armed: look for a slide of at least ``fist_slide_distance``.
        if self._fist_anchor_xy is None or frame.cursor_xy is None:
            return events
        dx = frame.cursor_xy[0] - self._fist_anchor_xy[0]
        dy = frame.cursor_xy[1] - self._fist_anchor_xy[1]
        if (dx * dx + dy * dy) ** 0.5 >= self.fist_slide_distance and self._can_fire("fist_slide", now):
            events.append(GestureEvent(
                name="fist_slide",
                timestamp=now,
                cursor_xy=frame.cursor_xy,
                metadata={"dx": dx, "dy": dy},
            ))
            self._mark_fired("fist_slide", now)
            # Require a fresh hold before another slide can fire.
            self._fist_started_at = None
            self._fist_hold_armed = False
            self._fist_anchor_xy = None
        return events

    # ====================================================== misc gestures
    def _update_misc(
        self, frame: GestureFrame, now: float, open_palm_hold_ms: int
    ) -> List[GestureEvent]:
        events: List[GestureEvent] = []

        # Track open-palm hold for the cancel gesture.
        if "open_palm" in frame.labels:
            if self._open_palm_started_at is None:
                self._open_palm_started_at = now
        else:
            self._open_palm_started_at = None

        # Plain rising-edge gestures.
        for name in ("thumbs_up", "peace", "four_finger_type"):
            active = self._is_majority(name)
            previously = self._active.get(name, False)
            if active and not previously and self._can_fire(name, now):
                events.append(GestureEvent(name=name, timestamp=now, cursor_xy=frame.cursor_xy))
                self._mark_fired(name, now)
            self._active[name] = active

        # open_palm cancel: only fires after the configured hold.
        op_active = self._is_majority("open_palm")
        if op_active and self._open_palm_started_at is not None:
            if (now - self._open_palm_started_at) * 1000 >= open_palm_hold_ms and self._can_fire("open_palm", now):
                events.append(GestureEvent(name="open_palm", timestamp=now, cursor_xy=frame.cursor_xy))
                self._mark_fired("open_palm", now)
        self._active["open_palm"] = op_active

        return events

    # ============================================================== reset
    def reset(self) -> None:
        self._history.clear()
        self._active.clear()
        self._last_fired_at.clear()
        self._wave_history.clear()
        self._last_wave_emit_at = 0.0
        self._reset_holds()
        self.armed = False
