"""PyInstaller build script for GestureOS Pro.

Run with:  python build.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
BUILD = ROOT / "build"


def main() -> int:
    if DIST.exists():
        shutil.rmtree(DIST)
    if BUILD.exists():
        shutil.rmtree(BUILD)

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name",
        "GestureOSPro",
        "--add-data",
        f"config{';' if sys.platform == 'win32' else ':'}config",
        "--add-data",
        f"assets{';' if sys.platform == 'win32' else ':'}assets",
        # MediaPipe ships native binaries that PyInstaller can miss:
        "--collect-all",
        "mediapipe",
        "--collect-all",
        "cv2",
        "main.py",
    ]
    print(" ".join(cmd))
    return subprocess.call(cmd, cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
