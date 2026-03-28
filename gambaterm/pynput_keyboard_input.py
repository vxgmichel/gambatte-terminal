from __future__ import annotations

import sys
import threading
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

    ctrl_c_event = threading.Event()
    ctrl_d_event = threading.Event()

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
        # Check for Ctrl+C / Ctrl+D
        ctrl_held = (
            DomCode.CONTROL_LEFT in pressed
            or DomCode.CONTROL_RIGHT in pressed
        )
        if ctrl_held:
            if DomCode.US_C in pressed:
                ctrl_c_event.set()
            elif DomCode.US_D in pressed:
                ctrl_d_event.set()

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

    def get_pressed() -> set[DomCode]:
        if ctrl_c_event.is_set():
            raise KeyboardInterrupt
        if ctrl_d_event.is_set():
            raise OSError
        return pressed

    pressed: set[DomCode] = set()
    listener = pynput.keyboard.Listener(on_press=on_press, on_release=on_release)
    try:
        listener.start()
        yield get_pressed
    finally:
        pressed.clear()
        listener.stop()
