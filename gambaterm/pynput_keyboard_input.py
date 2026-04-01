from __future__ import annotations

import sys
from contextlib import contextmanager
from typing import Callable, Iterator, TYPE_CHECKING

from .dom_codes import DomCode

if TYPE_CHECKING:
    import pynput.keyboard  # type: ignore


def get_value_from_pynput_key_code(key: pynput.keyboard.KeyCode) -> DomCode | None:
    if sys.platform == "win32":
        from pynput.keyboard._win32 import KeyCode as WinKeyCode  # type: ignore

        assert isinstance(key, WinKeyCode)
        scan = key._parameters(True).get("wScan", None)
        if scan is None:
            return None
        return DomCode.from_win_scancode(scan)

    elif sys.platform == "darwin":
        from pynput.keyboard._darwin import KeyCode as DarwinKeyCode  # type: ignore

        assert isinstance(key, DarwinKeyCode)
        scan = key.vk
        if scan is None:
            return None
        return DomCode.from_mac_scancode(scan)

    else:
        assert False


@contextmanager
def pynput_key_pressed_context() -> Iterator[Callable[[], set[DomCode]]]:
    import pynput.keyboard

    def on_press(key: pynput.keyboard.Key | pynput.keyboard.KeyCode | None) -> None:
        value: DomCode | None
        if isinstance(key, pynput.keyboard.KeyCode):
            value = get_value_from_pynput_key_code(key)
        elif isinstance(key, pynput.keyboard.Key):
            value = get_value_from_pynput_key_code(key.value)
        else:
            return
        if value is not None:
            pressed.add(value)

    def on_release(key: pynput.keyboard.Key | pynput.keyboard.KeyCode | None) -> None:
        value: DomCode | None
        if isinstance(key, pynput.keyboard.KeyCode):
            value = get_value_from_pynput_key_code(key)
        elif isinstance(key, pynput.keyboard.Key):
            value = get_value_from_pynput_key_code(key.value)
        else:
            return
        if value is not None:
            pressed.discard(value)

    pressed: set[DomCode] = set()
    listener = pynput.keyboard.Listener(on_press=on_press, on_release=on_release)
    try:
        listener.start()
        yield lambda: pressed.copy()
    finally:
        pressed.clear()
        listener.stop()
