"""Modal-ish countdown dialog used for destructive confirmations."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)


class ConfirmationDialog(QDialog):
    """Frame-less dialog displaying a countdown for a pending destructive action.

    Emits :pyattr:`confirmed` / :pyattr:`cancelled` rather than being driven by
    its own buttons - the user normally confirms with a thumbs-up gesture.
    """

    confirmed = Signal()
    cancelled = Signal()

    def __init__(self, action: str, timeout_ms: int = 4000, parent=None):
        super().__init__(parent)
        self.action = action
        self.timeout_ms = timeout_ms
        self._remaining = timeout_ms
        self._tick_ms = 50

        self.setWindowTitle("Confirm action")
        self.setWindowFlag(Qt.FramelessWindowHint, True)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setModal(False)
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)
        title = QLabel(f"Confirm: <b>{action}</b>")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 16px; padding: 6px;")
        layout.addWidget(title)

        msg = QLabel(
            "Show <b>👍 thumbs up</b> to proceed,<br>"
            "or hold an <b>open palm</b> to cancel."
        )
        msg.setAlignment(Qt.AlignCenter)
        layout.addWidget(msg)

        self.bar = QProgressBar()
        self.bar.setRange(0, timeout_ms)
        self.bar.setValue(timeout_ms)
        self.bar.setTextVisible(False)
        layout.addWidget(self.bar)

        btn_row = QHBoxLayout()
        ok = QPushButton("Confirm")
        ok.clicked.connect(self.on_confirm)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.on_cancel)
        btn_row.addWidget(ok)
        btn_row.addWidget(cancel)
        layout.addLayout(btn_row)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(self._tick_ms)

    # -------------------------------------------------------------- API
    def on_confirm(self) -> None:
        self._timer.stop()
        self.confirmed.emit()
        self.accept()

    def on_cancel(self) -> None:
        self._timer.stop()
        self.cancelled.emit()
        self.reject()

    # ----------------------------------------------------------- internals
    def _tick(self) -> None:
        self._remaining -= self._tick_ms
        if self._remaining <= 0:
            self.on_cancel()
            return
        self.bar.setValue(self._remaining)
