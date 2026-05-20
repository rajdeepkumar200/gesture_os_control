"""GestureOS Pro main window.

This file is the orchestrator: it owns the long-lived services and core
modules, drives a worker thread that captures + processes frames, and
streams results back to the Qt main thread for rendering.
"""
from __future__ import annotations

import logging
import time
from typing import List, Optional, Tuple

import cv2
import numpy as np
from PySide6.QtCore import QObject, QThread, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QAction, QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QMainWindow,
    QPushButton,
    QSplitter,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from core.action_dispatcher import ActionDispatcher
from core.camera_manager import CameraManager
from core.gesture_classifier import GestureClassifier, GestureFrame
from core.gesture_state_machine import GestureEvent, GestureStateMachine
from core.hand_tracker import HandTracker, INDEX_PIP, INDEX_TIP
from core.keyboard_controller import KeyboardController
from core.os_controller import OSController
from core.search_controller import SearchController
from core.zoom_controller import ZoomController
from services.audio_service import AudioService
from services.config_service import ConfigService
from ui.confirmation_dialog import ConfirmationDialog
from ui.overlays import draw_cursor, draw_hud
from ui.settings_dialog import SettingsDialog
from ui.status_panel import StatusPanel
from ui.virtual_keyboard import VirtualKeyboardWindow

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------- styles
DARK_QSS = """
QWidget { background-color: #1e1f22; color: #e8e8e8; }
QPushButton { background-color: #2d2f34; border: 1px solid #3a3d44;
              padding: 8px 14px; border-radius: 6px; }
QPushButton:hover { background-color: #393c43; }
QPushButton:pressed { background-color: #4a4e57; }
QLabel#header { font-size: 18px; font-weight: 700; padding: 6px; }
QListWidget { background-color: #16171a; border: 1px solid #2c2e33; }
QStatusBar { background-color: #16171a; }
"""
LIGHT_QSS = """
QWidget { background-color: #f4f4f6; color: #1d1d1f; }
QPushButton { background-color: #ffffff; border: 1px solid #c8c8cc;
              padding: 8px 14px; border-radius: 6px; }
QPushButton:hover { background-color: #ececef; }
QLabel#header { font-size: 18px; font-weight: 700; padding: 6px; }
QListWidget { background-color: #ffffff; border: 1px solid #d0d0d4; }
"""


# ========================================================== worker thread
class VisionWorker(QObject):
    """Captures + processes frames off the GUI thread."""

    frameReady = Signal(QImage, float, object)  # image, fps, gesture_frame
    eventsReady = Signal(list)  # List[GestureEvent]
    pointersReady = Signal(list)  # list of (x_norm, y_norm, pinch)
    armedChanged = Signal(bool)  # tracking armed/disarmed
    stopped = Signal()

    def __init__(
        self,
        camera: CameraManager,
        tracker: HandTracker,
        classifier: GestureClassifier,
        state_machine: GestureStateMachine,
        os_ctrl: OSController,
        cursor_enabled: bool,
        cursor_point_only: bool,
        open_palm_hold_ms: int,
        frame_skip: int,
    ) -> None:
        super().__init__()
        self.camera = camera
        self.tracker = tracker
        self.classifier = classifier
        self.state_machine = state_machine
        self.os_ctrl = os_ctrl
        self.cursor_enabled = cursor_enabled
        self.cursor_point_only = cursor_point_only
        self.open_palm_hold_ms = open_palm_hold_ms
        self.frame_skip = frame_skip
        self._running = False
        self._processed_fps = 0.0
        self._kb_window_geom: Optional[Tuple[int, int, int, int]] = None
        self._last_armed: Optional[bool] = None
        self.keyboard_visible: bool = False

    def set_keyboard_geom(self, geom: Optional[Tuple[int, int, int, int]]) -> None:
        self._kb_window_geom = geom

    def stop(self) -> None:
        self._running = False

    @Slot()
    def run(self) -> None:
        self._running = True
        last = time.perf_counter()
        alpha = 0.9
        skip_counter = 0

        while self._running:
            ok, frame = self.camera.read()
            if not ok or frame is None:
                time.sleep(0.005)
                continue

            if self.frame_skip and skip_counter < self.frame_skip:
                skip_counter += 1
                continue
            skip_counter = 0

            hands = self.tracker.process(frame)
            gesture_frame = self.classifier.classify(hands)
            events = self.state_machine.update(gesture_frame, self.open_palm_hold_ms)

            # Surface arming changes to the UI.
            if self.state_machine.armed != self._last_armed:
                self._last_armed = self.state_machine.armed
                self.armedChanged.emit(self.state_machine.armed)

            # Render overlays
            display = frame.copy()
            self.tracker.draw(display, hands)
            if gesture_frame.cursor_xy:
                draw_cursor(display, gesture_frame.cursor_xy)

            now = time.perf_counter()
            inst = 1.0 / max(now - last, 1e-6)
            self._processed_fps = alpha * self._processed_fps + (1 - alpha) * inst
            last = now

            draw_hud(display, self._processed_fps, gesture_frame)

            # OS-level cursor + virtual-keyboard pointers are GATED on the
            # state-machine's armed flag, so the system is dormant until the
            # user explicitly arms it. Additionally, when ``cursor_point_only``
            # is on, the cursor only follows the hand while the index finger
            # is extended AND the hand is not in a "hold" pose (fist /
            # five-finger cluster). The strict ``point`` pose (only-index)
            # is unreliable in practice -- MediaPipe often misreads slightly
            # bent middle/ring fingers as extended -- so we use the looser
            # "index up" check instead. The cursor still freezes during a
            # pinch hold (because pinching folds the index toward the thumb,
            # so ``index_extended`` becomes false) and during fist / grab
            # gestures, which is what the user wants for stable click /
            # close / zoom interactions.
            should_move_cursor = (
                self.cursor_enabled
                and self.state_machine.armed
                and gesture_frame.cursor_xy is not None
                and not self.keyboard_visible
            )
            if self.cursor_point_only and hands:
                primary = max(hands, key=lambda h: h.score)
                index_extended = primary.is_finger_extended(INDEX_TIP, INDEX_PIP)
                in_hold_pose = (
                    "fist" in gesture_frame.labels
                    or "five_finger_pinch" in gesture_frame.labels
                )
                should_move_cursor = (
                    should_move_cursor and index_extended and not in_hold_pose
                )
            elif self.cursor_point_only and not hands:
                should_move_cursor = False
            if should_move_cursor:
                nx, ny = gesture_frame.cursor_xy
                self.os_ctrl.move_cursor_normalised(nx, ny)

            # Virtual-keyboard pointers are NOT gated on `armed`: the
            # keyboard is only visible when the user has explicitly opened
            # it, so pointer input is already opt-in. Emit even an empty
            # list so that the keyboard can release stale pinch state when
            # hands leave its bounds.
            if self._kb_window_geom is not None:
                pointers = self._compute_keyboard_pointers(hands, gesture_frame) if hands else []
                self.pointersReady.emit(pointers)

            if events:
                self.eventsReady.emit(events)

            qimg = self._to_qimage(display)
            self.frameReady.emit(qimg, self._processed_fps, gesture_frame)

        self.stopped.emit()

    # ------------------------------------------------------ helpers
    def _compute_keyboard_pointers(self, hands, gesture_frame) -> list:
        """Convert hand index-fingertips to local coords for the keyboard."""
        if not self._kb_window_geom:
            return []
        kx, ky, kw, kh = self._kb_window_geom
        screen_w, screen_h = self.os_ctrl.screen_size()
        result = []
        for h in hands[:2]:
            tip = h.landmarks[8]  # INDEX_TIP
            sx = tip.x * screen_w
            sy = tip.y * screen_h
            lx = (sx - kx) / max(kw, 1)
            ly = (sy - ky) / max(kh, 1)
            if -0.2 <= lx <= 1.2 and -0.2 <= ly <= 1.2:
                pinch = h.distance(4, 8) < self.classifier.pinch_threshold
                result.append((max(0.0, min(1.0, lx)), max(0.0, min(1.0, ly)), pinch))
        return result

    @staticmethod
    def _to_qimage(frame_bgr: np.ndarray) -> QImage:
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        h, w, _ = rgb.shape
        return QImage(rgb.data, w, h, w * 3, QImage.Format_RGB888).copy()


# =============================================================== window
class MainWindow(QMainWindow):
    """Primary application window."""

    def __init__(self, config: ConfigService) -> None:
        super().__init__()
        self.config = config
        self.audio = AudioService(enabled=bool(config.get("app.voice_feedback", False)))

        self.setWindowTitle("GestureOS Pro")
        self.resize(1280, 760)

        # Build core modules ----------------------------------------------
        self.camera = self._build_camera()
        self.tracker = self._build_tracker()
        self.classifier = self._build_classifier()
        self.state_machine = self._build_state_machine()
        self.os_ctrl = OSController(
            cursor_smoothing=float(config.get("cursor.smoothing", 0.35)),
            cursor_sensitivity=float(config.get("cursor.sensitivity", 1.6)),
        )
        self.kb_ctrl = KeyboardController()
        self.zoom_ctrl = ZoomController()
        self.search_ctrl = SearchController()
        self.dispatcher = ActionDispatcher(
            os_controller=self.os_ctrl,
            keyboard_controller=self.kb_ctrl,
            zoom_controller=self.zoom_ctrl,
            search_controller=self.search_ctrl,
            gesture_mapping=config.gestures,
            confirmation_timeout_ms=int(config.get("gestures.confirmation_timeout_ms", 4000)),
        )
        self.dispatcher.on_action_log = self.log_action
        self.dispatcher.on_confirmation_request = self._on_confirmation_request
        self.dispatcher.on_confirmation_resolved = self._on_confirmation_resolved
        self.dispatcher.on_open_search = self.open_search_prompt
        self.dispatcher.on_toggle_keyboard = self.toggle_virtual_keyboard
        self.dispatcher.on_open_keyboard_for_input = self.open_keyboard_for_input

        # Virtual keyboard window
        self.keyboard_window: Optional[VirtualKeyboardWindow] = None

        # Worker thread placeholders
        self._worker: Optional[VisionWorker] = None
        self._worker_thread: Optional[QThread] = None

        # UI --------------------------------------------------------------
        self._build_ui()
        self._apply_theme(self.config.get("app.theme", "dark"))

        # Config hot-reload
        self.config.subscribe(self._on_config_changed)

        # Pending confirmation dialog reference
        self._confirm_dialog: Optional[ConfirmationDialog] = None

    # ============================================================ builders
    def _build_camera(self) -> CameraManager:
        return CameraManager(
            index=int(self.config.get("camera.index", 0)),
            width=int(self.config.get("camera.width", 1280)),
            height=int(self.config.get("camera.height", 720)),
            fps=int(self.config.get("camera.fps", 30)),
            mirror=bool(self.config.get("camera.mirror", True)),
        )

    def _build_tracker(self) -> HandTracker:
        return HandTracker(
            max_num_hands=int(self.config.get("hand_tracking.max_num_hands", 2)),
            min_detection_confidence=float(
                self.config.get("hand_tracking.min_detection_confidence", 0.7)
            ),
            min_tracking_confidence=float(
                self.config.get("hand_tracking.min_tracking_confidence", 0.6)
            ),
            model_complexity=int(self.config.get("hand_tracking.model_complexity", 1)),
        )

    def _build_classifier(self) -> GestureClassifier:
        return GestureClassifier(
            pinch_threshold=float(self.config.get("gestures.pinch_threshold", 0.045)),
        )

    def _build_state_machine(self) -> GestureStateMachine:
        per_gesture = {}
        for entry in self.config.gestures:
            if "cooldown_ms" in entry:
                per_gesture[entry["name"]] = entry["cooldown_ms"]
        return GestureStateMachine(
            smoothing_window=int(self.config.get("gestures.smoothing_window", 5)),
            default_cooldown_ms=int(self.config.get("gestures.cooldown_ms", 700)),
            per_gesture_cooldown_ms=per_gesture,
            wave_window_s=float(self.config.get("gestures.wave_window_s", 3.0)),
            wave_min_amplitude=float(self.config.get("gestures.wave_min_amplitude", 0.12)),
            wave_min_direction_changes=int(self.config.get("gestures.wave_min_direction_changes", 3)),
            pinch_click_hold_s=float(self.config.get("gestures.pinch_click_hold_s", 1.5)),
            zoom_out_hold_s=float(self.config.get("gestures.zoom_out_hold_s", 2.0)),
            zoom_in_release_window_s=float(self.config.get("gestures.zoom_in_release_window_s", 1.0)),
            fist_hold_s=float(self.config.get("gestures.fist_hold_s", 2.0)),
            fist_slide_distance=float(self.config.get("gestures.fist_slide_distance", 0.20)),
        )

    # ================================================================ UI
    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        root = QHBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        splitter = QSplitter(Qt.Horizontal)
        root.addWidget(splitter)

        # ============================== LEFT: status stage (no video by default)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)

        header = QLabel("GestureOS Pro")
        header.setObjectName("header")
        left_layout.addWidget(header)

        # Large status panel
        self.status_panel = StatusPanel()
        left_layout.addWidget(self.status_panel, 1)

        # Hidden-by-default video preview (small).
        self.video_label = QLabel()
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setMinimumHeight(180)
        self.video_label.setMaximumHeight(260)
        self.video_label.setStyleSheet(
            "background-color: #0c0c0e; border: 1px solid #2a2c30; border-radius: 8px;"
        )
        self.video_label.setVisible(False)
        left_layout.addWidget(self.video_label)

        controls = QHBoxLayout()
        self.start_btn = QPushButton("Start")
        self.start_btn.clicked.connect(self.start_pipeline)
        controls.addWidget(self.start_btn)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.clicked.connect(self.stop_pipeline)
        self.stop_btn.setEnabled(False)
        controls.addWidget(self.stop_btn)
        # Manual arm/disarm toggle -- the wave gesture still works but this
        # gives the user a guaranteed-reliable way to enable tracking.
        self.arm_btn = QPushButton("Arm tracking")
        self.arm_btn.setCheckable(True)
        self.arm_btn.setEnabled(False)
        self.arm_btn.toggled.connect(self._on_arm_button_toggled)
        controls.addWidget(self.arm_btn)
        self.kb_btn = QPushButton("Virtual Keyboard")
        self.kb_btn.setCheckable(True)
        self.kb_btn.clicked.connect(self.toggle_virtual_keyboard)
        controls.addWidget(self.kb_btn)
        self.preview_btn = QPushButton("Show camera preview")
        self.preview_btn.setCheckable(True)
        self.preview_btn.toggled.connect(self._toggle_preview)
        controls.addWidget(self.preview_btn)
        self.settings_btn = QPushButton("Settings")
        self.settings_btn.clicked.connect(self.open_settings)
        controls.addWidget(self.settings_btn)
        controls.addStretch(1)
        left_layout.addLayout(controls)

        splitter.addWidget(left)

        # ============================== RIGHT: gesture toggles + action log
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)

        right_header = QLabel("Activity")
        right_header.setObjectName("header")
        right_layout.addWidget(right_header)

        self.gesture_toggles_label = QLabel("Enabled gestures:")
        right_layout.addWidget(self.gesture_toggles_label)
        self.toggle_container = QVBoxLayout()
        right_layout.addLayout(self.toggle_container)
        self._gesture_toggles: List[QCheckBox] = []
        self._rebuild_gesture_toggles()

        right_layout.addWidget(QLabel("Action log:"))
        self.log_list = QListWidget()
        right_layout.addWidget(self.log_list, 1)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        # Status bar
        self.setStatusBar(QStatusBar(self))
        self.statusBar().showMessage("Idle. Press Start to begin.")

        # Toolbar (extras)
        toolbar = QToolBar("Main")
        self.addToolBar(toolbar)
        reload_act = QAction("Reload config", self)
        reload_act.triggered.connect(self.config.reload)
        toolbar.addAction(reload_act)
        theme_act = QAction("Toggle theme", self)
        theme_act.triggered.connect(self._toggle_theme)
        toolbar.addAction(theme_act)

    def _toggle_preview(self, on: bool) -> None:
        self.video_label.setVisible(on)
        self.preview_btn.setText("Hide camera preview" if on else "Show camera preview")

    def _rebuild_gesture_toggles(self) -> None:
        for cb in self._gesture_toggles:
            self.toggle_container.removeWidget(cb)
            cb.deleteLater()
        self._gesture_toggles.clear()
        for entry in self.config.gestures:
            cb = QCheckBox(f"{entry['name']} → {entry.get('action', 'noop')}")
            cb.setChecked(bool(entry.get("enabled", True)))
            cb.toggled.connect(lambda checked, name=entry["name"]: self._on_gesture_toggle(name, checked))
            self.toggle_container.addWidget(cb)
            self._gesture_toggles.append(cb)

    # ======================================================== pipeline
    def start_pipeline(self) -> None:
        if not self.camera.start():
            self.statusBar().showMessage("Failed to start camera.")
            self.audio.error()
            return

        cursor_enabled = bool(self.config.get("cursor.enabled", True))
        cursor_point_only = bool(self.config.get("cursor.point_only", True))
        open_palm_hold_ms = int(self.config.get("gestures.open_palm_hold_ms", 1500))
        frame_skip = int(self.config.get("camera.frame_skip", 0))

        self._worker_thread = QThread(self)
        self._worker = VisionWorker(
            camera=self.camera,
            tracker=self.tracker,
            classifier=self.classifier,
            state_machine=self.state_machine,
            os_ctrl=self.os_ctrl,
            cursor_enabled=cursor_enabled,
            cursor_point_only=cursor_point_only,
            open_palm_hold_ms=open_palm_hold_ms,
            frame_skip=frame_skip,
        )
        self._worker.moveToThread(self._worker_thread)
        self._worker_thread.started.connect(self._worker.run)
        self._worker.frameReady.connect(self._on_frame)
        self._worker.eventsReady.connect(self._on_events)
        self._worker.pointersReady.connect(self._on_pointers)
        self._worker.armedChanged.connect(self._on_armed_changed)
        self._worker.stopped.connect(self._worker_thread.quit)
        self._worker_thread.finished.connect(self._worker_thread.deleteLater)
        self._worker_thread.start()

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.arm_btn.setEnabled(True)
        self.arm_btn.blockSignals(True)
        self.arm_btn.setChecked(self.state_machine.armed)
        self.arm_btn.setText(
            "Disarm tracking" if self.state_machine.armed else "Arm tracking"
        )
        self.arm_btn.blockSignals(False)
        self.statusBar().showMessage(
            "Running. Click \"Arm tracking\" or wave an open palm to enable gestures."
        )
        self.status_panel.set_running(True)
        self.status_panel.set_armed(self.state_machine.armed)
        self.audio.ok()

    def stop_pipeline(self) -> None:
        if self._worker:
            self._worker.keyboard_visible = False
            self._worker.stop()
            self._worker = None
        if self._worker_thread:
            self._worker_thread.quit()
            self._worker_thread.wait(1500)
            self._worker_thread = None
        self.camera.stop()
        self.video_label.clear()
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        # Disarm + disable the arm button when the pipeline is stopped.
        self.state_machine.armed = False
        self.arm_btn.blockSignals(True)
        self.arm_btn.setChecked(False)
        self.arm_btn.setText("Arm tracking")
        self.arm_btn.setEnabled(False)
        self.arm_btn.blockSignals(False)
        self.statusBar().showMessage("Stopped.")
        self.status_panel.set_running(False)
        self.status_panel.set_armed(False)
        self.status_panel.set_pending(None)

    # ----------------------------------------------------------- slots
    @Slot(QImage, float, object)
    def _on_frame(self, qimg: QImage, fps: float, gesture_frame: GestureFrame) -> None:
        # Update camera preview only if user has chosen to show it.
        if self.video_label.isVisible():
            pix = QPixmap.fromImage(qimg).scaled(
                self.video_label.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            self.video_label.setPixmap(pix)
        # Status panel always gets the latest gesture/FPS regardless of preview.
        hands = 0
        if gesture_frame.two_hand_distance > 0:
            hands = 2
        elif gesture_frame.labels or gesture_frame.cursor_xy:
            hands = 1
        self.status_panel.update_gesture(
            labels=gesture_frame.labels,
            hands=hands,
            fps=fps,
            pinch_strength=gesture_frame.pinch_strength,
        )

    @Slot(list)
    def _on_events(self, events: List[GestureEvent]) -> None:
        # Surface arming events explicitly -- they are noop in the
        # dispatcher but we still want a clear log entry / status update.
        for e in events:
            if e.name == "tracking_armed":
                self.log_action("Tracking ARMED \u2014 gestures live.")
                self.audio.ok()
            elif e.name == "tracking_disarmed":
                self.log_action("Tracking DISARMED \u2014 wave again to resume.")
                self.audio.warn()
        self.dispatcher.dispatch(events)
        self.status_panel.set_pending(self.dispatcher.pending_action)

    @Slot(bool)
    def _on_armed_changed(self, armed: bool) -> None:
        self.status_panel.set_armed(armed)
        # Keep the button visually in sync with the actual state without
        # re-emitting toggled().
        self.arm_btn.blockSignals(True)
        self.arm_btn.setChecked(armed)
        self.arm_btn.setText("Disarm tracking" if armed else "Arm tracking")
        self.arm_btn.blockSignals(False)
        msg = (
            "Tracking armed. All gestures are live."
            if armed
            else "Tracking disarmed. Click \"Arm tracking\" or wave palm to arm."
        )
        self.statusBar().showMessage(msg)

    def _on_arm_button_toggled(self, checked: bool) -> None:
        """Manual arm/disarm via the toolbar button."""
        self.state_machine.armed = checked
        # Make sure the worker's change-detection re-fires the signal.
        if self._worker is not None:
            self._worker._last_armed = None  # force re-emit on next frame
        self._on_armed_changed(checked)
        self.log_action(
            "Tracking ARMED (manual)." if checked else "Tracking DISARMED (manual)."
        )
        if checked:
            self.audio.ok()
        else:
            self.audio.warn()

    @Slot(list)
    def _on_pointers(self, pointers: List) -> None:
        if self.keyboard_window and self.keyboard_window.isVisible():
            self.keyboard_window.update_pointers(pointers)

    # ------------------------------------------------------ confirmations
    def _on_confirmation_request(self, action: str, timeout_ms: int) -> None:
        if self._confirm_dialog is not None:
            self._confirm_dialog.close()
        self.audio.warn()
        dlg = ConfirmationDialog(action, timeout_ms, parent=self)
        self._confirm_dialog = dlg
        dlg.show()

    def _on_confirmation_resolved(self, confirmed: bool) -> None:
        if self._confirm_dialog is not None:
            self._confirm_dialog.close()
            self._confirm_dialog = None
        self.status_panel.set_pending(None)
        (self.audio.ok if confirmed else self.audio.warn)()

    # ----------------------------------------------------- virtual keyboard
    def toggle_virtual_keyboard(self) -> None:
        if self.keyboard_window is None or not self.keyboard_window.isVisible():
            if self.keyboard_window is None:
                self.keyboard_window = VirtualKeyboardWindow(
                    self.kb_ctrl,
                    scale=float(self.config.get("virtual_keyboard.scale", 1.0)),
                    opacity=float(self.config.get("virtual_keyboard.opacity", 0.92)),
                    key_dwell_ms=int(self.config.get("virtual_keyboard.key_dwell_ms", 250)),
                )
                self.keyboard_window.keyPressed.connect(
                    lambda c: self.log_action(f"Key: {c}")
                )
            # Position near the bottom of the screen
            screen = QApplication.primaryScreen().geometry()
            kw = self.keyboard_window.width()
            kh = self.keyboard_window.height()
            self.keyboard_window.move(
                (screen.width() - kw) // 2,
                screen.height() - kh - 80,
            )
            self.keyboard_window.show()
            self.kb_btn.setChecked(True)
            self._update_kb_geom()
            if self._worker:
                self._worker.keyboard_visible = True
        else:
            self.keyboard_window.hide()
            self.kb_btn.setChecked(False)
            if self._worker:
                self._worker.set_keyboard_geom(None)
                self._worker.keyboard_visible = False

    def _update_kb_geom(self) -> None:
        if not (self.keyboard_window and self._worker):
            return
        geo = self.keyboard_window.geometry()
        self._worker.set_keyboard_geom((geo.x(), geo.y(), geo.width(), geo.height()))

    def open_keyboard_for_input(self) -> None:
        """Open (or re-anchor) the virtual keyboard near the focused app's
        search bar / input field.

        We don't have universal search-bar detection -- that would require
        per-app UI Automation. As a robust heuristic the keyboard is placed
        just below the foreground window's bottom edge so the search bar
        (typically near the top of the window) stays visible while the user
        types.
        """
        # Ensure the keyboard exists and is visible (idempotent open).
        if self.keyboard_window is None or not self.keyboard_window.isVisible():
            self.toggle_virtual_keyboard()
        if self.keyboard_window is None:
            return

        screen = QApplication.primaryScreen().geometry()
        kw = self.keyboard_window.width()
        kh = self.keyboard_window.height()

        target_x = (screen.width() - kw) // 2
        target_y = screen.height() - kh - 80

        rect = self.os_ctrl.foreground_window_rect()
        if rect is not None:
            wx, wy, ww, wh = rect
            # Centre horizontally on the window; place just below it.
            target_x = wx + (ww - kw) // 2
            target_y = wy + wh + 8
            # Clamp into the screen so the keyboard never lands off-screen.
            target_x = max(0, min(target_x, screen.width() - kw))
            if target_y + kh > screen.height():
                # Window extends to the bottom of the screen -- overlap the
                # bottom of the window instead of going off-screen.
                target_y = max(0, screen.height() - kh - 8)

        self.keyboard_window.move(target_x, target_y)
        self.keyboard_window.raise_()
        self._update_kb_geom()
        if self._worker:
            self._worker.keyboard_visible = True
        self.log_action(
            f"Keyboard anchored to: {self.os_ctrl.active_window_title() or '(foreground)'}"
        )

    def moveEvent(self, ev):  # noqa: N802
        super().moveEvent(ev)
        QTimer.singleShot(0, self._update_kb_geom)

    # ---------------------------------------------------------- search
    def open_search_prompt(self) -> None:
        text, ok = QInputDialog.getText(self, "Search", "What would you like to search?")
        if not ok or not text:
            return
        self.log_action(f"Search: {text}")
        local = self.search_ctrl.search_local(text)
        if local:
            self.log_action(f"  found {len(local)} local results")
        # Always also open a web search.
        self.search_ctrl.search_web(text)

    # ---------------------------------------------------------- settings
    def open_settings(self) -> None:
        dlg = SettingsDialog(self.config, parent=self)
        if dlg.exec():
            self.log_action("Settings saved")

    # ----------------------------------------------------------- logging
    def log_action(self, msg: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        self.log_list.addItem(f"[{timestamp}] {msg}")
        if self.log_list.count() > 500:
            self.log_list.takeItem(0)
        self.log_list.scrollToBottom()
        self.status_panel.set_last_action(msg)

    # ------------------------------------------------------------ theme
    def _apply_theme(self, theme: str) -> None:
        qss = DARK_QSS if theme == "dark" else LIGHT_QSS
        self.setStyleSheet(qss)

    def _toggle_theme(self) -> None:
        current = self.config.get("app.theme", "dark")
        new = "light" if current == "dark" else "dark"
        self.config.set("app.theme", new)
        self._apply_theme(new)

    # ------------------------------------------------------ config reload
    def _on_config_changed(self, _cfg: ConfigService) -> None:
        # Re-apply lightweight settings live. Camera / tracker changes require
        # a restart - we surface a status message instead of disrupting the
        # running pipeline.
        self._apply_theme(self.config.get("app.theme", "dark"))
        self.os_ctrl.cursor_smoothing = float(self.config.get("cursor.smoothing", 0.35))
        self.os_ctrl.cursor_sensitivity = float(self.config.get("cursor.sensitivity", 1.6))
        self.audio.set_enabled(bool(self.config.get("app.voice_feedback", False)))
        self.dispatcher.set_mapping(self.config.gestures)
        self.classifier.pinch_threshold = float(self.config.get("gestures.pinch_threshold", 0.045))
        self.statusBar().showMessage("Config reloaded.", 3000)
        self._rebuild_gesture_toggles()

    def _on_gesture_toggle(self, name: str, enabled: bool) -> None:
        gestures = self.config.gestures
        for entry in gestures:
            if entry["name"] == name:
                entry["enabled"] = enabled
                break
        # Update mapping in-memory without writing to disk.
        self.config._gestures["gestures"] = gestures  # type: ignore[attr-defined]
        self.dispatcher.set_mapping(gestures)
        self.log_action(f"{'Enabled' if enabled else 'Disabled'} gesture {name}")

    # ----------------------------------------------------------- shutdown
    def closeEvent(self, event):  # noqa: N802
        try:
            self.stop_pipeline()
            self.tracker.close()
            if self.keyboard_window:
                self.keyboard_window.close()
        finally:
            super().closeEvent(event)
