"""KeyboardController unit tests using a stubbed pyautogui."""
from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from core import keyboard_controller as kc_mod


@contextmanager
def _patched_pyautogui():
    """Patch ``_HAS_PYAUTOGUI`` and ``pyautogui`` for the whole test body."""
    fake = MagicMock()
    with patch.object(kc_mod, "_HAS_PYAUTOGUI", True), patch.object(kc_mod, "pyautogui", fake):
        yield kc_mod.KeyboardController(), fake


def test_lowercase_letter_typed():
    with _patched_pyautogui() as (kb, fake):
        kb.press_key("a")
        fake.typewrite.assert_called_with("a", interval=0, _pause=False)


def test_shift_uppercases_next_letter_only():
    with _patched_pyautogui() as (kb, fake):
        kb.press_key("SHIFT")
        kb.press_key("a")
        kb.press_key("b")
        args_list = [c.args[0] for c in fake.typewrite.call_args_list]
        assert args_list[0] == "A"
        assert args_list[1] == "b"


def test_caps_makes_letters_uppercase():
    with _patched_pyautogui() as (kb, fake):
        kb.press_key("CAPS")
        kb.press_key("z")
        kb.press_key("y")
        args_list = [c.args[0] for c in fake.typewrite.call_args_list]
        assert args_list == ["Z", "Y"]


def test_backspace_press_uses_press():
    with _patched_pyautogui() as (kb, fake):
        kb.press_key("BACKSPACE")
        fake.press.assert_called_with("backspace", _pause=False)
