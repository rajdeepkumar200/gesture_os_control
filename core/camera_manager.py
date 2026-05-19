"""Threaded webcam capture wrapper."""
from __future__ import annotations

import logging
import threading
import time
from typing import Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class CameraManager:
    """Runs ``cv2.VideoCapture`` in a background thread.

    Always exposes the latest frame via :py:meth:`read`. Designed so the UI/CV
    pipeline never blocks on I/O.
    """

    def __init__(
        self,
        index: int = 0,
        width: int = 1280,
        height: int = 720,
        fps: int = 30,
        mirror: bool = True,
    ) -> None:
        self.index = index
        self.width = width
        self.height = height
        self.fps = fps
        self.mirror = mirror

        self._cap: Optional[cv2.VideoCapture] = None
        self._thread: Optional[threading.Thread] = None
        self._frame: Optional[np.ndarray] = None
        self._frame_lock = threading.Lock()
        self._running = threading.Event()
        self._last_capture_time = 0.0
        self._actual_fps = 0.0

    # ----------------------------------------------------------- lifecycle
    def start(self) -> bool:
        if self._running.is_set():
            return True
        cap = cv2.VideoCapture(self.index, cv2.CAP_DSHOW if hasattr(cv2, "CAP_DSHOW") else 0)
        if not cap.isOpened():
            cap.release()
            cap = cv2.VideoCapture(self.index)
        if not cap.isOpened():
            logger.error("Could not open camera index %d", self.index)
            return False
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        cap.set(cv2.CAP_PROP_FPS, self.fps)

        self._cap = cap
        self._running.set()
        self._thread = threading.Thread(target=self._loop, name="CameraThread", daemon=True)
        self._thread.start()
        logger.info("Camera %d started (%dx%d @ %d fps)", self.index, self.width, self.height, self.fps)
        return True

    def stop(self) -> None:
        self._running.clear()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        with self._frame_lock:
            self._frame = None
        logger.info("Camera stopped")

    # --------------------------------------------------------------- API
    def is_running(self) -> bool:
        return self._running.is_set()

    @property
    def actual_fps(self) -> float:
        return self._actual_fps

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        """Return the latest frame.  Non-blocking."""
        with self._frame_lock:
            if self._frame is None:
                return False, None
            return True, self._frame.copy()

    # ------------------------------------------------------------ thread
    def _loop(self) -> None:
        assert self._cap is not None
        alpha = 0.9
        while self._running.is_set():
            ok, frame = self._cap.read()
            if not ok or frame is None:
                time.sleep(0.01)
                continue
            if self.mirror:
                frame = cv2.flip(frame, 1)
            with self._frame_lock:
                self._frame = frame

            now = time.perf_counter()
            if self._last_capture_time:
                inst = 1.0 / max(now - self._last_capture_time, 1e-6)
                self._actual_fps = alpha * self._actual_fps + (1 - alpha) * inst
            self._last_capture_time = now
