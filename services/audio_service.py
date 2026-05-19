"""Audio feedback service.

Uses ``winsound`` on Windows (always available, zero-dependency) and falls back to
``playsound`` elsewhere. Silently no-ops if no backend is available.
"""
from __future__ import annotations

import logging
import sys
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    import winsound  # type: ignore
    _HAS_WINSOUND = True
except ImportError:  # pragma: no cover - non-windows
    _HAS_WINSOUND = False

try:  # optional
    from playsound import playsound as _playsound  # type: ignore
    _HAS_PLAYSOUND = True
except Exception:  # pragma: no cover
    _HAS_PLAYSOUND = False


class AudioService:
    """Small wrapper that plays short feedback sounds asynchronously."""

    BEEP_OK = (880, 90)         # Hz, ms
    BEEP_WARN = (440, 120)
    BEEP_ERROR = (220, 200)

    def __init__(self, enabled: bool = True, assets_dir: str | Path | None = None):
        self.enabled = enabled
        self._assets = Path(assets_dir) if assets_dir else None

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled

    # ---------------------------------------------------------- public API
    def ok(self) -> None:
        self._beep(*self.BEEP_OK)

    def warn(self) -> None:
        self._beep(*self.BEEP_WARN)

    def error(self) -> None:
        self._beep(*self.BEEP_ERROR)

    def play(self, name: str) -> None:
        """Play a wav file from the assets/sounds folder by stem name."""
        if not self.enabled or self._assets is None:
            return
        path = self._assets / "sounds" / f"{name}.wav"
        if not path.exists():
            logger.debug("Audio asset missing: %s", path)
            return
        threading.Thread(target=self._play_file, args=(str(path),), daemon=True).start()

    # ---------------------------------------------------------- internals
    def _beep(self, freq: int, duration_ms: int) -> None:
        if not self.enabled:
            return
        if _HAS_WINSOUND:
            try:
                threading.Thread(
                    target=winsound.Beep,
                    args=(freq, duration_ms),
                    daemon=True,
                ).start()
                return
            except RuntimeError:
                pass
        # No-op on other platforms unless we add a sound file.
        logger.debug("Beep %dHz/%dms suppressed (no audio backend)", freq, duration_ms)

    @staticmethod
    def _play_file(path: str) -> None:
        try:
            if _HAS_WINSOUND and sys.platform == "win32":
                winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
            elif _HAS_PLAYSOUND:
                _playsound(path, block=False)
        except Exception:  # pragma: no cover
            logger.exception("Failed to play %s", path)
