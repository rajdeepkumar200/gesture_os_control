"""ActionDispatcher routing tests, using mocks for the side-effectful controllers."""
from __future__ import annotations

import time
from unittest.mock import MagicMock

from core.action_dispatcher import ActionDispatcher
from core.gesture_state_machine import GestureEvent


def _dispatcher(mapping):
    os_ctrl = MagicMock()
    os_ctrl.active_window_title.return_value = "Window"
    kb_ctrl = MagicMock()
    zoom_ctrl = MagicMock()
    search_ctrl = MagicMock()
    d = ActionDispatcher(
        os_controller=os_ctrl,
        keyboard_controller=kb_ctrl,
        zoom_controller=zoom_ctrl,
        search_controller=search_ctrl,
        gesture_mapping=mapping,
        confirmation_timeout_ms=10_000,
    )
    return d, os_ctrl, zoom_ctrl


def test_pinch_routes_to_click():
    d, os_ctrl, _ = _dispatcher([
        {"name": "pinch", "action": "open_under_cursor", "enabled": True},
    ])
    d.dispatch([GestureEvent("pinch", time.monotonic())])
    assert os_ctrl.click.called


def test_disabled_gesture_does_nothing():
    d, os_ctrl, _ = _dispatcher([
        {"name": "pinch", "action": "open_under_cursor", "enabled": False},
    ])
    d.dispatch([GestureEvent("pinch", time.monotonic())])
    assert not os_ctrl.click.called


def test_confirm_required_blocks_until_thumbs_up():
    d, os_ctrl, _ = _dispatcher([
        {"name": "fist", "action": "delete_selection", "enabled": True, "confirm": True},
        {"name": "thumbs_up", "action": "confirm", "enabled": True},
    ])
    d.dispatch([GestureEvent("fist", time.monotonic())])
    assert not os_ctrl.delete_selection.called
    assert d.has_pending
    assert d.pending_action == "delete_selection"
    # Confirm with thumbs_up
    d.dispatch([GestureEvent("thumbs_up", time.monotonic())])
    assert os_ctrl.delete_selection.called
    assert not d.has_pending


def test_open_palm_cancels_pending():
    d, os_ctrl, _ = _dispatcher([
        {"name": "fist", "action": "delete_selection", "enabled": True, "confirm": True},
        {"name": "open_palm", "action": "cancel", "enabled": True},
        {"name": "thumbs_up", "action": "confirm", "enabled": True},
    ])
    d.dispatch([GestureEvent("fist", time.monotonic())])
    assert d.has_pending
    d.dispatch([GestureEvent("open_palm", time.monotonic())])
    assert not d.has_pending
    assert not os_ctrl.delete_selection.called


def test_zoom_actions_route():
    d, _os, zoom = _dispatcher([
        {"name": "five_finger_both_apart", "action": "zoom_in", "enabled": True},
        {"name": "five_finger_both_together", "action": "zoom_out", "enabled": True},
    ])
    d.dispatch([GestureEvent("five_finger_both_apart", time.monotonic())])
    d.dispatch([GestureEvent("five_finger_both_together", time.monotonic())])
    assert zoom.zoom_in.called
    assert zoom.zoom_out.called


def test_search_callback_invoked():
    d, *_ = _dispatcher([
        {"name": "four_finger_type", "action": "open_search", "enabled": True},
    ])
    cb = MagicMock()
    d.on_open_search = cb
    d.dispatch([GestureEvent("four_finger_type", time.monotonic())])
    assert cb.called
