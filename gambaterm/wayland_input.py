from contextlib import contextmanager
from typing import Callable, Iterator, Set

from pywayland.client import Display
from wlroots import ffi, lib

from .console import Console, InputGetter


def get_wayland_input_mapping(console: Console) -> dict[str, Console.Input]:
    return {
        "up": console.Input.UP,
        "down": console.Input.DOWN,
        "left": console.Input.LEFT,
        "right": console.Input.RIGHT,
        "f": console.Input.A,
        "v": console.Input.A,
        "space": console.Input.A,
        "d": console.Input.B,
        "c": console.Input.B,
        "alt": console.Input.B,
        "alt_r": console.Input.B,
        "enter": console.Input.START,
        "ctrl_r": console.Input.START,
        "shift_r": console.Input.SELECT,
        "delete": console.Input.SELECT,
    }


def get_wayland_event_mapping(console: Console) -> dict[str, Console.Event]:
    return {
        "0": console.Event.SELECT_STATE_0,
        "1": console.Event.SELECT_STATE_1,
        "2": console.Event.SELECT_STATE_2,
        "3": console.Event.SELECT_STATE_3,
        "4": console.Event.SELECT_STATE_4,
        "5": console.Event.SELECT_STATE_5,
        "6": console.Event.SELECT_STATE_6,
        "7": console.Event.SELECT_STATE_7,
        "8": console.Event.SELECT_STATE_8,
        "9": console.Event.SELECT_STATE_9,
        "l": console.Event.LOAD_STATE,
        "k": console.Event.SAVE_STATE,
    }


@contextmanager
def wayland_key_pressed_context() -> Iterator[Callable[[], Set[str]]]:
    display = Display()
    pressed: Set[str] = set()

    def on_key(event) -> None:
        key = ffi.string(lib.wlr_event_keyboard_get_key(event)).decode("utf-8")
        if event.state == lib.WLR_KEY_PRESSED:
            pressed.add(key)
        elif event.state == lib.WLR_KEY_RELEASED:
            pressed.discard(key)

    display.set_event_handler(lib.wlr_event_keyboard_key, on_key)

    try:
        yield lambda: pressed
    finally:
        pressed.clear()
        display.disconnect()
