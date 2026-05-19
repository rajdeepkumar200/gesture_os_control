"""Centralised logging configuration with rotating file output."""
from __future__ import annotations

import logging
import logging.handlers
import os
from pathlib import Path

_DEFAULT_FORMAT = (
    "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
)


def setup_logging(
    level: str = "INFO",
    file: str = "logs/gesture_os_pro.log",
    max_bytes: int = 1_048_576,
    backup_count: int = 5,
) -> None:
    """Configure root logger.  Idempotent."""
    root = logging.getLogger()
    if getattr(root, "_gop_configured", False):
        root.setLevel(level)
        return

    root.setLevel(level)
    fmt = logging.Formatter(_DEFAULT_FORMAT)

    # Console
    console = logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(fmt)
    root.addHandler(console)

    # File
    try:
        log_path = Path(file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)
    except OSError:  # pragma: no cover - permission issues etc.
        root.warning("Could not create file log handler at %s", file)

    # Silence chatty third-parties
    for noisy in ("PIL", "matplotlib", "mediapipe"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    setattr(root, "_gop_configured", True)
    root.info("Logging initialised (level=%s, pid=%d)", level, os.getpid())
