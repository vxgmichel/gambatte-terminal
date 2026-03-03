from __future__ import annotations


from contextlib import contextmanager
from typing import Callable, Iterator

from .keys import (
    FunctionalKeys,
    LatinKeys,
    Keys,
)

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pynput.keyboard  # type: ignore


PYNPUT_KEY_TO_FUNCTIONAL_KEY_MAPPING: dict[pynput.keyboard.Key, Keys] = {}


def key_from_pynput_key(key: pynput.keyboard.Key) -> Keys | None:
    if not PYNPUT_KEY_TO_FUNCTIONAL_KEY_MAPPING:
        initialize_pynput_key_to_functional_key_mapping()
    return PYNPUT_KEY_TO_FUNCTIONAL_KEY_MAPPING.get(key)


def initialize_pynput_key_to_functional_key_mapping() -> None:
    import pynput.keyboard

    PYNPUT_KEY_TO_FUNCTIONAL_KEY_MAPPING.update(
        {
            pynput.keyboard.Key.alt: FunctionalKeys.LEFT_ALT,
            pynput.keyboard.Key.alt_l: FunctionalKeys.LEFT_ALT,
            pynput.keyboard.Key.alt_r: FunctionalKeys.RIGHT_ALT,
            pynput.keyboard.Key.alt_gr: FunctionalKeys.RIGHT_ALT,
            pynput.keyboard.Key.backspace: FunctionalKeys.BACKSPACE,
            pynput.keyboard.Key.caps_lock: FunctionalKeys.CAPS_LOCK,
            pynput.keyboard.Key.cmd: FunctionalKeys.LEFT_META,
            pynput.keyboard.Key.cmd_l: FunctionalKeys.LEFT_META,
            pynput.keyboard.Key.cmd_r: FunctionalKeys.RIGHT_META,
            pynput.keyboard.Key.ctrl: FunctionalKeys.LEFT_CONTROL,
            pynput.keyboard.Key.ctrl_l: FunctionalKeys.LEFT_CONTROL,
            pynput.keyboard.Key.ctrl_r: FunctionalKeys.RIGHT_CONTROL,
            pynput.keyboard.Key.delete: FunctionalKeys.DELETE,
            pynput.keyboard.Key.down: FunctionalKeys.DOWN,
            pynput.keyboard.Key.end: FunctionalKeys.END,
            pynput.keyboard.Key.enter: FunctionalKeys.ENTER,
            pynput.keyboard.Key.esc: FunctionalKeys.ESCAPE,
            pynput.keyboard.Key.f1: FunctionalKeys.F1,
            pynput.keyboard.Key.f2: FunctionalKeys.F2,
            pynput.keyboard.Key.f3: FunctionalKeys.F3,
            pynput.keyboard.Key.f4: FunctionalKeys.F4,
            pynput.keyboard.Key.f5: FunctionalKeys.F5,
            pynput.keyboard.Key.f6: FunctionalKeys.F6,
            pynput.keyboard.Key.f7: FunctionalKeys.F7,
            pynput.keyboard.Key.f8: FunctionalKeys.F8,
            pynput.keyboard.Key.f9: FunctionalKeys.F9,
            pynput.keyboard.Key.f10: FunctionalKeys.F10,
            pynput.keyboard.Key.f11: FunctionalKeys.F11,
            pynput.keyboard.Key.f12: FunctionalKeys.F12,
            pynput.keyboard.Key.f13: FunctionalKeys.F13,
            pynput.keyboard.Key.f14: FunctionalKeys.F14,
            pynput.keyboard.Key.f15: FunctionalKeys.F15,
            pynput.keyboard.Key.f16: FunctionalKeys.F16,
            pynput.keyboard.Key.f17: FunctionalKeys.F17,
            pynput.keyboard.Key.f18: FunctionalKeys.F18,
            pynput.keyboard.Key.f19: FunctionalKeys.F19,
            pynput.keyboard.Key.f20: FunctionalKeys.F20,
            pynput.keyboard.Key.home: FunctionalKeys.HOME,
            pynput.keyboard.Key.left: FunctionalKeys.LEFT,
            pynput.keyboard.Key.page_down: FunctionalKeys.PAGE_DOWN,
            pynput.keyboard.Key.page_up: FunctionalKeys.PAGE_UP,
            pynput.keyboard.Key.right: FunctionalKeys.RIGHT,
            pynput.keyboard.Key.shift: FunctionalKeys.LEFT_SHIFT,
            pynput.keyboard.Key.shift_l: FunctionalKeys.LEFT_SHIFT,
            pynput.keyboard.Key.shift_r: FunctionalKeys.RIGHT_SHIFT,
            pynput.keyboard.Key.space: LatinKeys.SPACE,  # Somehow, pynput exposes space as a functional key
            pynput.keyboard.Key.tab: FunctionalKeys.TAB,
            pynput.keyboard.Key.up: FunctionalKeys.UP,
            pynput.keyboard.Key.media_play_pause: FunctionalKeys.MEDIA_PLAY_PAUSE,
            pynput.keyboard.Key.media_stop: FunctionalKeys.MEDIA_STOP,
            pynput.keyboard.Key.media_volume_mute: FunctionalKeys.MUTE_VOLUME,
            pynput.keyboard.Key.media_volume_down: FunctionalKeys.LOWER_VOLUME,
            pynput.keyboard.Key.media_volume_up: FunctionalKeys.RAISE_VOLUME,
            pynput.keyboard.Key.media_previous: FunctionalKeys.MEDIA_TRACK_PREVIOUS,
            pynput.keyboard.Key.media_next: FunctionalKeys.MEDIA_TRACK_NEXT,
            pynput.keyboard.Key.insert: FunctionalKeys.INSERT,
            pynput.keyboard.Key.menu: FunctionalKeys.MENU,
            pynput.keyboard.Key.num_lock: FunctionalKeys.NUM_LOCK,
            pynput.keyboard.Key.pause: FunctionalKeys.PAUSE,
            pynput.keyboard.Key.print_screen: FunctionalKeys.PRINT_SCREEN,
            pynput.keyboard.Key.scroll_lock: FunctionalKeys.SCROLL_LOCK,
        }
    )


@contextmanager
def pynput_key_pressed_context() -> Iterator[Callable[[], set[Keys]]]:
    import pynput.keyboard

    def on_press(key: pynput.keyboard.Key | pynput.keyboard.KeyCode | None) -> None:
        value: Keys | None
        if isinstance(key, pynput.keyboard.KeyCode):
            value = None if key.char is None else LatinKeys.from_latin(key.char)
        elif isinstance(key, pynput.keyboard.Key):
            value = key_from_pynput_key(key)
        else:
            return
        if value is not None:
            pressed.add(value)

    def on_release(key: pynput.keyboard.Key | pynput.keyboard.KeyCode | None) -> None:
        value: Keys | None
        if isinstance(key, pynput.keyboard.KeyCode):
            value = None if key.char is None else LatinKeys.from_latin(key.char)
        elif isinstance(key, pynput.keyboard.Key):
            value = key_from_pynput_key(key)
        else:
            return
        if value is not None:
            pressed.discard(value)

    pressed: set[Keys] = set()
    listener = pynput.keyboard.Listener(on_press=on_press, on_release=on_release)
    try:
        listener.start()
        yield lambda: pressed
    finally:
        pressed.clear()
        listener.stop()
