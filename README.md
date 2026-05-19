# GestureOS Pro

A production-grade desktop application that lets you control your operating system with
**computer-vision-based hand gestures** and a fully functional **dual-hand virtual
keyboard**.

> Built with Python, PySide6, OpenCV, and MediaPipe.

---

## Features

- Real-time hand tracking at 30+ FPS using MediaPipe Hands (21 landmarks per hand).
- Robust gesture recognition with temporal smoothing and per-gesture cooldowns.
- OS control: open files / folders, close windows, delete to Recycle Bin, zoom, search.
- Dual-hand virtual keyboard with pinch-to-press input (letters, numbers, symbols,
  Shift, Caps Lock, Backspace, Enter, Space).
- Safety confirmations for destructive actions (thumbs-up to confirm, open palm to
  cancel).
- Live action log, FPS display, sensitivity controls and theme switching.
- YAML-driven configuration with hot reload.
- Comprehensive logging with rotating file handler.
- Unit tests with `pytest`.
- Standalone Windows executable via PyInstaller.

---

## Installation

### 1. Requirements

- Windows 10 / 11 (primary). Linux & macOS supported for core CV; some OS actions are
  Windows-only.
- Python 3.10 or 3.11 (MediaPipe currently does not support 3.12+ on all platforms).
- A webcam (720p recommended).

### 2. Setup

```powershell
git clone <your-repo> gesture_os_pro
cd gesture_os_pro
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 3. Run

```powershell
python main.py
```

---

## Gesture Guide

GestureOS Pro is **disarmed** by default — your hands can be in frame
without affecting anything. You explicitly **arm** the system by waving.

### Arm / disarm

| Gesture                                                     | Action                              |
| ----------------------------------------------------------- | ----------------------------------- |
| **Open palm, wave side-to-side for ~5 s**                   | Toggle tracking on (arm)            |
| **Open palm, wave side-to-side for ~5 s** (while armed)     | Toggle tracking off (disarm)        |

While disarmed the OS cursor is *not* moved and no actions fire.

### Active gestures (require armed state)

| Gesture                                                     | Action                              |
| ----------------------------------------------------------- | ----------------------------------- |
| **Thumb + index pinch held for ~1.5 s**                     | Left click                          |
| **All five fingertips clustered to one point for ~2 s**     | Zoom out                            |
| **Spread fingers outward right after the cluster**          | Zoom in                             |
| **Fist held for ~2 s, then slide hand away**                | Close active window                 |
| **Thumbs up**                                               | Confirm a pending action            |
| **Open palm held still for ~1.5 s**                         | Cancel a pending action             |
| **Peace sign (✌)**                                           | Toggle the on-screen keyboard       |
| Both hands over the virtual keyboard + pinch                | Press a key                         |

All thresholds (hold times, slide distance, wave amplitude) are
configurable in `config/settings.yaml`; mappings live in
`config/gestures.yaml` and are hot-reloadable.

---

## Troubleshooting

- **Webcam not detected** – check Windows privacy settings, try a different camera
  index in Settings.
- **Low FPS** – reduce capture resolution in `config/settings.yaml`, close other
  webcam apps, ensure you are running on the dedicated GPU.
- **MediaPipe install fails** – use Python 3.10 / 3.11 (`pip install
  mediapipe==0.10.9`).
- **Cursor jitter** – increase `smoothing.window` in `settings.yaml`.

## Performance Tips

- Use a well-lit environment with a plain background.
- Keep hands within 30–80 cm of the camera.
- Enable "Frame skipping" in settings on low-end machines.
- Disable unused gestures in `gestures.yaml` to reduce CPU load.

## Security Notes

Destructive actions (delete, close) always require a secondary **thumbs-up**
confirmation with a countdown timer that can be cancelled with an **open palm**.
Files are moved to the Recycle Bin rather than permanently deleted whenever the OS
supports it.

## Packaging (Windows EXE)

```powershell
pip install pyinstaller
python build.py
```

The standalone executable will be created in `dist/GestureOSPro/`.

## Project Layout

```
gesture_os_pro/
├── main.py
├── build.py
├── requirements.txt
├── config/
│   ├── settings.yaml
│   └── gestures.yaml
├── core/                # CV + control logic
├── ui/                  # PySide6 GUI
├── services/            # Cross-cutting concerns
├── tests/               # pytest suite
└── assets/
    ├── icons/
    └── sounds/
```

## License

MIT. See `LICENSE` (add your own).
