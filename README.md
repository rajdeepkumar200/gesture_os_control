<h1 align="center">🤚 GestureOS Pro</h1>

<p align="center"><b>Control your operating system with hand gestures — plus a dual-hand virtual keyboard you type on by pinching the air ✋⌨️✨</b></p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%20%2F%203.11-blue?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.10 / 3.11" />
  <img src="https://img.shields.io/badge/MediaPipe-Hands%20%C2%B7%2021%20landmarks-orange?style=for-the-badge" alt="MediaPipe Hands" />
  <img src="https://img.shields.io/badge/OpenCV-Real--time%20CV-green?style=for-the-badge&logo=opencv&logoColor=white" alt="OpenCV" />
  <img src="https://img.shields.io/badge/UI-PySide6-41CD52?style=for-the-badge&logo=qt&logoColor=white" alt="PySide6" />
  <img src="https://img.shields.io/badge/Platform-Windows%2010%20%2F%2011-0078D6?style=for-the-badge&logo=windows&logoColor=white" alt="Windows 10 / 11" />
  <img src="https://img.shields.io/badge/Tests-pytest-yellow?style=for-the-badge&logo=pytest&logoColor=black" alt="pytest" />
</p>

---

## 📑 Table of Contents

- [📖 About](#about)
- [✨ Features](#features)
- [🎮 Gesture Guide](#gesture-guide)
- [🛠️ Tech Stack](#tech-stack)
- [📂 Project Structure](#project-structure)
- [⚙️ Prerequisites](#prerequisites)
- [🚀 Installation](#installation)
- [💻 Usage](#usage)
- [🔧 Troubleshooting](#troubleshooting)
- [⚡ Performance Tips](#performance-tips)
- [🔒 Security Notes](#security-notes)
- [📦 Packaging (Windows EXE)](#packaging-windows-exe)
- [🧪 Testing](#testing)
- [🤝 Contributing](#contributing)
- [📄 License](#license)
- [👨‍💻 Author](#author)

---

## 📖 About

A production-grade desktop application that lets you control your operating system with **computer-vision-based hand gestures** and a fully functional **dual-hand virtual keyboard** 🤯.

Built with Python, PySide6, OpenCV, and MediaPipe — wave to arm the system, pinch to click, and give a thumbs-up to confirm the serious stuff 👍. No touchscreen, no wearables, just a webcam and your hands.

---

## ✨ Features

- 🎥 Real-time hand tracking at **30+ FPS** using MediaPipe Hands (21 landmarks per hand)
- 🎯 Robust gesture recognition with temporal smoothing and per-gesture cooldowns
- 🖥️ OS control: open files / folders, close windows, delete to Recycle Bin, zoom, search
- ⌨️ Dual-hand virtual keyboard with pinch-to-press input (letters, numbers, symbols, Shift, Caps Lock, Backspace, Enter, Space)
- 🛡️ Safety confirmations for destructive actions (thumbs-up to confirm, open palm to cancel)
- 📜 Live action log, FPS display, sensitivity controls and theme switching
- 🔄 YAML-driven configuration with hot reload
- 📝 Comprehensive logging with rotating file handler
- 🧪 Unit tests with `pytest`
- 📦 Standalone Windows executable via PyInstaller

---

## 🎮 Gesture Guide

GestureOS Pro is **disarmed** by default — your hands can be in frame without affecting anything 😌. You explicitly **arm** the system by waving.

### 👋 Arm / Disarm

| Gesture | Action |
| ----------------------------------------------------------- | ----------------------------------- |
| **Open palm, wave side-to-side for ~5 s** | Toggle tracking on (arm) |
| **Open palm, wave side-to-side for ~5 s** (while armed) | Toggle tracking off (disarm) |

While disarmed the OS cursor is *not* moved and no actions fire 🔒.

### ✋ Active Gestures (require armed state)

| Gesture | Action |
| ----------------------------------------------------------- | ----------------------------------- |
| **Thumb + index pinch held for ~1.5 s** | Left click 🖱️ |
| **All five fingertips clustered to one point for ~2 s** | Zoom out 🔍 |
| **Spread fingers outward right after the cluster** | Zoom in 🔎 |
| **Fist held for ~2 s, then slide hand away** | Close active window ❌ |
| **Thumbs up** | Confirm a pending action 👍 |
| **Open palm held still for ~1.5 s** | Cancel a pending action ✋ |
| **Peace sign (✌)** | Toggle the on-screen keyboard ⌨️ |
| Both hands over the virtual keyboard + pinch | Press a key 🤏 |

> ⚙️ All thresholds (hold times, slide distance, wave amplitude) are configurable in `config/settings.yaml`; mappings live in `config/gestures.yaml` and are hot-reloadable.

---

## 🛠️ Tech Stack

- 🐍 **Language:** Python 3.10 / 3.11
- 🖼️ **GUI:** PySide6 (Qt)
- 👁️ **Computer Vision:** OpenCV, MediaPipe Hands, NumPy
- 🖱️ **OS Automation:** PyAutoGUI, pynput, keyboard, mouse, pywin32 (Windows)
- ⚙️ **Configuration:** PyYAML (`config/settings.yaml`, `config/gestures.yaml`)
- 🎵 **Audio Feedback:** playsound
- 🧪 **Testing:** pytest, pytest-mock
- 📦 **Packaging:** PyInstaller

---

## 📂 Project Structure

```
gesture_os_control/
├── main.py                # 🚀 App entry point
├── build.py               # 📦 PyInstaller build script
├── requirements.txt       # 📋 Python dependencies
├── pytest.ini             # 🧪 Test configuration
├── config/
│   ├── settings.yaml      # ⚙️ App settings (thresholds, resolution, smoothing)
│   └── gestures.yaml      # 🎮 Gesture → action mappings (hot-reloadable)
├── core/                  # 🧠 CV + control logic
├── ui/                    # 🎨 PySide6 GUI
├── services/              # 🔧 Cross-cutting concerns
├── tests/                 # 🧪 pytest suite
└── assets/
    ├── icons/             # 🖼️ Icons
    └── sounds/            # 🔊 Sounds
```

---

## ⚙️ Prerequisites

- 🪟 Windows 10 / 11 (primary). Linux & macOS supported for core CV; some OS actions are Windows-only.
- 🐍 Python 3.10 or 3.11 (MediaPipe currently does not support 3.12+ on all platforms)
- 📷 A webcam (720p recommended)

---

## 🚀 Installation

### 1️⃣ Clone the repo

```powershell
git clone https://github.com/rajdeepkumar200/gesture_os_control.git
cd gesture_os_control
```

### 2️⃣ Create a virtual environment & install dependencies 📦

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 3️⃣ Run it ▶️

```powershell
python main.py
```

---

## 💻 Usage

1. Launch the app with `python main.py` 🚀
2. 👋 **Wave an open palm side-to-side for ~5 s** to arm tracking
3. Use the gestures from the [Gesture Guide](#gesture-guide) — pinch to click, ✌ to bring up the virtual keyboard, 👍 / ✋ to confirm or cancel pending actions
4. Wave again to disarm when you're done 😎

🎛️ Sensitivity, theme, and per-gesture settings can be tweaked in the app and in `config/settings.yaml` — changes hot-reload, no restart needed.

---

## 🔧 Troubleshooting

- 📷 **Webcam not detected** – check Windows privacy settings, try a different camera index in Settings.
- 🐢 **Low FPS** – reduce capture resolution in `config/settings.yaml`, close other webcam apps, ensure you are running on the dedicated GPU.
- 💥 **MediaPipe install fails** – use Python 3.10 / 3.11 (`pip install mediapipe==0.10.9`).
- 🎯 **Cursor jitter** – increase `smoothing.window` in `settings.yaml`.

---

## ⚡ Performance Tips

- 💡 Use a well-lit environment with a plain background
- 📏 Keep hands within 30–80 cm of the camera
- ⏩ Enable "Frame skipping" in settings on low-end machines
- 🚫 Disable unused gestures in `gestures.yaml` to reduce CPU load

---

## 🔒 Security Notes

Destructive actions (delete, close) always require a secondary **thumbs-up** confirmation 👍 with a countdown timer that can be cancelled with an **open palm** ✋. Files are moved to the Recycle Bin rather than permanently deleted whenever the OS supports it 🗑️.

---

## 📦 Packaging (Windows EXE)

```powershell
pip install pyinstaller
python build.py
```

The standalone executable will be created in `dist/GestureOSPro/` 🎉.

---

## 🧪 Testing

Unit tests live in `tests/` and run with pytest:

```powershell
pytest
```

---

## 🤝 Contributing

Ideas for new gestures, better smoothing, or platform fixes? 😄 Issues and pull requests are welcome — please keep the safety-confirmation pattern for anything destructive 🙏.

---

## 📄 License

⚠️ No license file has been added to this repository yet — please contact the author before reusing the code.

---

## 👨‍💻 Author

**Rajdeep Kumar Singh** — AI/ML engineer working on computer vision and human-computer interaction 🚀

- 🐙 GitHub: [https://github.com/rajdeepkumar200](https://github.com/rajdeepkumar200)
- 💼 LinkedIn: [https://www.linkedin.com/in/rajdeep-kumar-singh-ai](https://www.linkedin.com/in/rajdeep-kumar-singh-ai)
- 🤗 Hugging Face: [https://huggingface.co/rajdeepkumar200](https://huggingface.co/rajdeepkumar200)

⭐ If GestureOS made you smile (or saved you a mouse reach), drop a star!
