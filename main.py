"""GestureOS Pro – application entry point."""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure project root is importable when launched directly or via PyInstaller.
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402

from services.config_service import ConfigService  # noqa: E402
from services.logging_service import setup_logging  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402


def main() -> int:
    config = ConfigService(ROOT / "config")
    log_cfg = config.get("logging", {}) or {}
    setup_logging(
        level=log_cfg.get("level", "INFO"),
        file=log_cfg.get("file", "logs/gesture_os_pro.log"),
        max_bytes=int(log_cfg.get("max_bytes", 1_048_576)),
        backup_count=int(log_cfg.get("backup_count", 5)),
    )

    # On Windows high-DPI looks better with this attribute on.
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")

    app = QApplication(sys.argv)
    app.setApplicationName(config.get("app.name", "GestureOS Pro"))

    window = MainWindow(config)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
