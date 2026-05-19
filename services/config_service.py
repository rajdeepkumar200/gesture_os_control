"""YAML-backed configuration service with hot reload support."""
from __future__ import annotations

import logging
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

import yaml

logger = logging.getLogger(__name__)


class ConfigService:
    """Loads settings.yaml and gestures.yaml.

    Supports:
        * dotted-path access ``cfg.get("camera.width", 1280)``
        * mutation via ``cfg.set("camera.width", 640)`` (kept in memory)
        * ``save()`` to persist back to disk
        * subscribers via ``subscribe(callback)`` invoked on every reload / save
    """

    def __init__(self, config_dir: str | Path) -> None:
        self._config_dir = Path(config_dir)
        self._settings_path = self._config_dir / "settings.yaml"
        self._gestures_path = self._config_dir / "gestures.yaml"
        self._lock = threading.RLock()
        self._settings: dict[str, Any] = {}
        self._gestures: dict[str, Any] = {}
        self._subscribers: list[Callable[[ConfigService], None]] = []
        self.reload()

    # ------------------------------------------------------------------ I/O
    def reload(self) -> None:
        with self._lock:
            self._settings = self._load(self._settings_path)
            self._gestures = self._load(self._gestures_path)
        logger.info("Configuration loaded from %s", self._config_dir)
        self._notify()

    def save(self) -> None:
        with self._lock:
            self._dump(self._settings_path, self._settings)
            self._dump(self._gestures_path, self._gestures)
        logger.info("Configuration saved to %s", self._config_dir)
        self._notify()

    @staticmethod
    def _load(path: Path) -> dict[str, Any]:
        if not path.exists():
            logger.warning("Config file missing: %s", path)
            return {}
        try:
            with path.open("r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
            if not isinstance(data, dict):
                raise ValueError("Top-level YAML must be a mapping")
            return data
        except Exception:  # pragma: no cover - defensive
            logger.exception("Failed to load %s", path)
            return {}

    @staticmethod
    def _dump(path: Path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            yaml.safe_dump(data, fh, sort_keys=False, allow_unicode=True)

    # ----------------------------------------------------------- Accessors
    @property
    def settings(self) -> dict[str, Any]:
        with self._lock:
            return deepcopy(self._settings)

    @property
    def gestures(self) -> list[dict[str, Any]]:
        with self._lock:
            return deepcopy(self._gestures.get("gestures", []))

    def get(self, dotted_key: str, default: Any = None) -> Any:
        with self._lock:
            node: Any = self._settings
            for part in dotted_key.split("."):
                if not isinstance(node, dict) or part not in node:
                    return default
                node = node[part]
            return deepcopy(node)

    def set(self, dotted_key: str, value: Any) -> None:
        with self._lock:
            parts = dotted_key.split(".")
            node = self._settings
            for part in parts[:-1]:
                node = node.setdefault(part, {})
            node[parts[-1]] = value
        self._notify()

    # ----------------------------------------------------------- Pub / sub
    def subscribe(self, callback: Callable[["ConfigService"], None]) -> None:
        self._subscribers.append(callback)

    def _notify(self) -> None:
        for cb in list(self._subscribers):
            try:
                cb(self)
            except Exception:  # pragma: no cover
                logger.exception("Config subscriber raised")
