"""Routes :class:`GestureEvent` instances to controller methods.

Reads its mapping from :class:`services.ConfigService` so users can rebind
gestures by editing ``config/gestures.yaml`` and reloading.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from .gesture_state_machine import GestureEvent
from .keyboard_controller import KeyboardController
from .os_controller import OSController
from .search_controller import SearchController
from .zoom_controller import ZoomController

logger = logging.getLogger(__name__)


@dataclass
class PendingConfirmation:
    action: str
    started_at: float
    timeout_ms: int

    def expired(self) -> bool:
        return (time.monotonic() - self.started_at) * 1000 > self.timeout_ms


# Type alias for UI callbacks (logged actions, search prompt, confirmation, ...)
UICallback = Callable[..., None]


class ActionDispatcher:
    """Translate gesture events into side effects."""

    def __init__(
        self,
        os_controller: OSController,
        keyboard_controller: KeyboardController,
        zoom_controller: ZoomController,
        search_controller: SearchController,
        gesture_mapping: List[Dict],
        confirmation_timeout_ms: int = 4000,
    ) -> None:
        self.os = os_controller
        self.kb = keyboard_controller
        self.zoom = zoom_controller
        self.search = search_controller
        self.confirmation_timeout_ms = confirmation_timeout_ms
        self.gesture_mapping: Dict[str, Dict] = {}
        self.set_mapping(gesture_mapping)

        # UI integration hooks (set externally by MainWindow)
        self.on_action_log: Optional[UICallback] = None
        self.on_confirmation_request: Optional[UICallback] = None
        self.on_confirmation_resolved: Optional[UICallback] = None
        self.on_open_search: Optional[UICallback] = None
        self.on_toggle_keyboard: Optional[UICallback] = None
        self.on_open_keyboard_for_input: Optional[UICallback] = None

        self._pending: Optional[PendingConfirmation] = None

        # Map action name -> handler.
        self._handlers: Dict[str, Callable[[GestureEvent], None]] = {
            "click": self._do_click,
            "double_click": self._do_double_click,
            "open_under_cursor": self._do_open_under_cursor,
            "close_window": self._do_close_window,
            "delete_selection": self._do_delete_selection,
            "open_search": self._do_open_search,
            "zoom_in": self._do_zoom_in,
            "zoom_out": self._do_zoom_out,
            "confirm": self._do_confirm,
            "cancel": self._do_cancel,
            "toggle_keyboard": self._do_toggle_keyboard,
            "open_keyboard_for_input": self._do_open_keyboard_for_input,
            "noop": lambda _e: None,
        }

    # ------------------------------------------------------------ public
    def set_mapping(self, mapping: List[Dict]) -> None:
        self.gesture_mapping = {
            entry["name"]: entry
            for entry in (mapping or [])
            if entry.get("enabled", True)
        }
        logger.info("ActionDispatcher mapping reloaded: %s", list(self.gesture_mapping))

    def dispatch(self, events: List[GestureEvent]) -> None:
        # Expire stale confirmations first.
        if self._pending and self._pending.expired():
            logger.info("Pending confirmation expired: %s", self._pending.action)
            self._notify_resolution(False)
            self._pending = None

        for event in events:
            entry = self.gesture_mapping.get(event.name)
            if not entry:
                continue
            action_name = entry.get("action", "noop")
            handler = self._handlers.get(action_name)
            if not handler:
                logger.warning("Unknown action %s for gesture %s", action_name, event.name)
                continue

            # Confirmation gating
            if entry.get("confirm") and event.name != "thumbs_up":
                self._request_confirmation(action_name)
                self._log(f"Confirm needed: {action_name}  (show 👍 to proceed)")
                continue

            try:
                handler(event)
            except Exception:
                logger.exception("Action %s raised", action_name)

    # ----------------------------------------------------- confirmation
    def _request_confirmation(self, action: str) -> None:
        self._pending = PendingConfirmation(
            action=action,
            started_at=time.monotonic(),
            timeout_ms=self.confirmation_timeout_ms,
        )
        if self.on_confirmation_request:
            self.on_confirmation_request(action, self.confirmation_timeout_ms)

    def _notify_resolution(self, confirmed: bool) -> None:
        if self.on_confirmation_resolved:
            self.on_confirmation_resolved(confirmed)

    # ------------------------------------------------------------ handlers
    def _log(self, msg: str) -> None:
        logger.info(msg)
        if self.on_action_log:
            self.on_action_log(msg)

    def _do_click(self, _e: GestureEvent) -> None:
        self.os.click()
        self._log("Click")

    def _do_double_click(self, _e: GestureEvent) -> None:
        self.os.double_click()
        self._log("Double click")

    def _do_open_under_cursor(self, _e: GestureEvent) -> None:
        # Best effort: simulate a click then enter to open the active item.
        self.os.click()
        self._log("Open / click under cursor")

    def _do_close_window(self, _e: GestureEvent) -> None:
        title = self.os.active_window_title()
        self.os.close_active_window()
        self._log(f"Close window: {title or '(foreground)'}")

    def _do_delete_selection(self, _e: GestureEvent) -> None:
        self.os.delete_selection()
        self._log("Delete (sent to Recycle Bin)")

    def _do_open_search(self, _e: GestureEvent) -> None:
        if self.on_open_search:
            self.on_open_search()
        self._log("Search overlay opened")

    def _do_zoom_in(self, _e: GestureEvent) -> None:
        self.zoom.zoom_in()
        self._log("Zoom in")

    def _do_zoom_out(self, _e: GestureEvent) -> None:
        self.zoom.zoom_out()
        self._log("Zoom out")

    def _do_confirm(self, _e: GestureEvent) -> None:
        if not self._pending:
            self._log("Confirm gesture detected (no pending action)")
            return
        action = self._pending.action
        self._pending = None
        handler = self._handlers.get(action)
        if not handler:
            self._log(f"No handler for confirmed action {action}")
            return
        try:
            handler(_e)
            self._log(f"Confirmed and executed: {action}")
            self._notify_resolution(True)
        except Exception:
            logger.exception("Confirmed action %s failed", action)
            self._notify_resolution(False)

    def _do_cancel(self, _e: GestureEvent) -> None:
        if self._pending:
            self._log(f"Cancelled pending action: {self._pending.action}")
            self._pending = None
            self._notify_resolution(False)
        else:
            self._log("Cancel gesture (nothing pending)")

    def _do_toggle_keyboard(self, _e: GestureEvent) -> None:
        if self.on_toggle_keyboard:
            self.on_toggle_keyboard()
        self._log("Toggled virtual keyboard")

    def _do_open_keyboard_for_input(self, _e: GestureEvent) -> None:
        """Open the virtual keyboard, anchored to the active app's window.

        Idempotent: if the keyboard is already open it stays open and is
        just re-anchored. Used by the four-finger "typing" gesture so the
        user can text into the focused search bar / input field.
        """
        if self.on_open_keyboard_for_input:
            self.on_open_keyboard_for_input()
        self._log("Virtual keyboard opened for text input")

    # -------------------------------------------------------- properties
    @property
    def has_pending(self) -> bool:
        return self._pending is not None

    @property
    def pending_action(self) -> Optional[str]:
        return self._pending.action if self._pending else None
