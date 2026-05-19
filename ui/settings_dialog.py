"""Settings dialog backed by ConfigService."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QSpinBox,
    QVBoxLayout,
)

from services.config_service import ConfigService


class SettingsDialog(QDialog):
    """Adjust app, camera, gesture, cursor and keyboard parameters."""

    def __init__(self, config: ConfigService, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("GestureOS Pro – Settings")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)

        # ---------- App ----------
        app_box = QGroupBox("Application")
        app_form = QFormLayout(app_box)
        self.theme = QComboBox()
        self.theme.addItems(["dark", "light"])
        self.theme.setCurrentText(config.get("app.theme", "dark"))
        app_form.addRow("Theme", self.theme)
        self.voice_feedback = QCheckBox()
        self.voice_feedback.setChecked(bool(config.get("app.voice_feedback", False)))
        app_form.addRow("Voice feedback", self.voice_feedback)
        layout.addWidget(app_box)

        # ---------- Camera ----------
        cam_box = QGroupBox("Camera")
        cam_form = QFormLayout(cam_box)
        self.cam_index = QSpinBox()
        self.cam_index.setRange(0, 8)
        self.cam_index.setValue(int(config.get("camera.index", 0)))
        cam_form.addRow("Index", self.cam_index)
        self.cam_w = QSpinBox()
        self.cam_w.setRange(320, 3840)
        self.cam_w.setValue(int(config.get("camera.width", 1280)))
        cam_form.addRow("Width", self.cam_w)
        self.cam_h = QSpinBox()
        self.cam_h.setRange(240, 2160)
        self.cam_h.setValue(int(config.get("camera.height", 720)))
        cam_form.addRow("Height", self.cam_h)
        self.cam_fps = QSpinBox()
        self.cam_fps.setRange(5, 120)
        self.cam_fps.setValue(int(config.get("camera.fps", 30)))
        cam_form.addRow("Target FPS", self.cam_fps)
        self.cam_mirror = QCheckBox()
        self.cam_mirror.setChecked(bool(config.get("camera.mirror", True)))
        cam_form.addRow("Mirror", self.cam_mirror)
        self.cam_skip = QSpinBox()
        self.cam_skip.setRange(0, 5)
        self.cam_skip.setValue(int(config.get("camera.frame_skip", 0)))
        cam_form.addRow("Frame skip", self.cam_skip)
        layout.addWidget(cam_box)

        # ---------- Hand tracking ----------
        ht_box = QGroupBox("Hand tracking")
        ht_form = QFormLayout(ht_box)
        self.det_conf = QDoubleSpinBox()
        self.det_conf.setRange(0.1, 0.95)
        self.det_conf.setSingleStep(0.05)
        self.det_conf.setValue(float(config.get("hand_tracking.min_detection_confidence", 0.7)))
        ht_form.addRow("Detection confidence", self.det_conf)
        self.trk_conf = QDoubleSpinBox()
        self.trk_conf.setRange(0.1, 0.95)
        self.trk_conf.setSingleStep(0.05)
        self.trk_conf.setValue(float(config.get("hand_tracking.min_tracking_confidence", 0.6)))
        ht_form.addRow("Tracking confidence", self.trk_conf)
        layout.addWidget(ht_box)

        # ---------- Gestures ----------
        g_box = QGroupBox("Gestures")
        g_form = QFormLayout(g_box)
        self.cooldown = QSpinBox()
        self.cooldown.setRange(0, 5000)
        self.cooldown.setSingleStep(50)
        self.cooldown.setValue(int(config.get("gestures.cooldown_ms", 700)))
        g_form.addRow("Default cooldown (ms)", self.cooldown)
        self.smoothing = QSpinBox()
        self.smoothing.setRange(1, 30)
        self.smoothing.setValue(int(config.get("gestures.smoothing_window", 5)))
        g_form.addRow("Smoothing window (frames)", self.smoothing)
        self.pinch = QDoubleSpinBox()
        self.pinch.setRange(0.01, 0.2)
        self.pinch.setSingleStep(0.005)
        self.pinch.setDecimals(3)
        self.pinch.setValue(float(config.get("gestures.pinch_threshold", 0.045)))
        g_form.addRow("Pinch threshold", self.pinch)
        layout.addWidget(g_box)

        # ---------- Cursor ----------
        cur_box = QGroupBox("Cursor")
        cur_form = QFormLayout(cur_box)
        self.cur_enabled = QCheckBox()
        self.cur_enabled.setChecked(bool(config.get("cursor.enabled", True)))
        cur_form.addRow("Move cursor with hand", self.cur_enabled)
        self.cur_smooth = QDoubleSpinBox()
        self.cur_smooth.setRange(0.0, 0.95)
        self.cur_smooth.setSingleStep(0.05)
        self.cur_smooth.setValue(float(config.get("cursor.smoothing", 0.35)))
        cur_form.addRow("Smoothing", self.cur_smooth)
        self.cur_sens = QDoubleSpinBox()
        self.cur_sens.setRange(0.5, 4.0)
        self.cur_sens.setSingleStep(0.1)
        self.cur_sens.setValue(float(config.get("cursor.sensitivity", 1.6)))
        cur_form.addRow("Sensitivity", self.cur_sens)
        layout.addWidget(cur_box)

        # ---------- Buttons ----------
        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.apply_and_close)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    # ------------------------------------------------------------ API
    def apply_and_close(self) -> None:
        c = self.config
        c.set("app.theme", self.theme.currentText())
        c.set("app.voice_feedback", self.voice_feedback.isChecked())
        c.set("camera.index", self.cam_index.value())
        c.set("camera.width", self.cam_w.value())
        c.set("camera.height", self.cam_h.value())
        c.set("camera.fps", self.cam_fps.value())
        c.set("camera.mirror", self.cam_mirror.isChecked())
        c.set("camera.frame_skip", self.cam_skip.value())
        c.set("hand_tracking.min_detection_confidence", self.det_conf.value())
        c.set("hand_tracking.min_tracking_confidence", self.trk_conf.value())
        c.set("gestures.cooldown_ms", self.cooldown.value())
        c.set("gestures.smoothing_window", self.smoothing.value())
        c.set("gestures.pinch_threshold", self.pinch.value())
        c.set("cursor.enabled", self.cur_enabled.isChecked())
        c.set("cursor.smoothing", self.cur_smooth.value())
        c.set("cursor.sensitivity", self.cur_sens.value())
        c.save()
        self.accept()
