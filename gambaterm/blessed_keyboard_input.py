from __future__ import annotations

from contextlib import contextmanager
from typing import Callable, Iterator

from blessed import Terminal
from blessed.keyboard import Keystroke

from .dom_codes import DomCode
from .keys import ASCII_PRINTABLE_TO_DOM_CODE


# Blessed synthesizes key_name as "KEY_{char}" for A-Z and 0-9 on release
# and repeat events, so we need mappings for both functional keys and
# printable keys that are used in game input/event mappings.
BLESSED_NAME_TO_DOM_CODE: dict[str, DomCode] = {
    "KEY_UP": DomCode.ARROW_UP,
    "KEY_DOWN": DomCode.ARROW_DOWN,
    "KEY_LEFT": DomCode.ARROW_LEFT,
    "KEY_RIGHT": DomCode.ARROW_RIGHT,
    "KEY_ENTER": DomCode.ENTER,
    "KEY_RIGHT_SHIFT": DomCode.SHIFT_RIGHT,
    "KEY_RIGHT_CONTROL": DomCode.CONTROL_RIGHT,
    "KEY_LEFT_SHIFT": DomCode.SHIFT_LEFT,
    "KEY_LEFT_CONTROL": DomCode.CONTROL_LEFT,
    "KEY_MENU": DomCode.CONTEXT_MENU,
    "KEY_LEFT_ALT": DomCode.ALT_LEFT,
    "KEY_ISO_LEVEL3_SHIFT": DomCode.ALT_RIGHT,
    "KEY_LEFT_SQUARE_BRACKET": DomCode.BRACKET_LEFT,
    "KEY_BACKSLASH": DomCode.BACKSLASH,
    "KEY_RIGHT_SQUARE_BRACKET": DomCode.BRACKET_RIGHT,
    "KEY_GRAVE_ACCENT": DomCode.BACKQUOTE,
    "KEY_LESS_THAN": DomCode.INTL_BACKSLASH,
    "KEY_SPACE": DomCode.SPACE,
    "KEY_APOSTROPHE": DomCode.QUOTE,
    "KEY_COMMA": DomCode.COMMA,
    "KEY_MINUS": DomCode.MINUS,
    "KEY_PERIOD": DomCode.PERIOD,
    "KEY_SLASH": DomCode.SLASH,
    "KEY_SEMICOLON": DomCode.SEMICOLON,
    "KEY_EQUALS": DomCode.EQUAL,
    "KEY_BACKSPACE": DomCode.BACKSPACE,
    "KEY_DELETE": DomCode.DEL,
    "KEY_INSERT": DomCode.INSERT,
    "KEY_TAB": DomCode.TAB,
}
# Add "KEY_{char}" entries for all printable keys in the ASCII mapping,
# matching the names blessed synthesizes for release/repeat events.
BLESSED_NAME_TO_DOM_CODE.update(
    (f"KEY_{ch.upper()}", dom_code)
    for ch, dom_code in ASCII_PRINTABLE_TO_DOM_CODE.items()
    if ch.isalnum()
)


def keystroke_to_dom_code(keystroke: Keystroke) -> DomCode | None:
    """Convert a blessed Keystroke to a DomCode."""
    name = keystroke.key_name
    if name is not None:
        dom_code = BLESSED_NAME_TO_DOM_CODE.get(name)
        if dom_code is not None:
            return dom_code
    return None


@contextmanager
def blessed_key_pressed_context(
    term: Terminal,
) -> Iterator[tuple[Callable[[], set[DomCode]], Callable[[], list[Keystroke]]]]:
    """Context manager providing a get_pressed() callable using blessed's kitty protocol."""
    # `pressed` is the set of currently pressed keys
    #  reported as DOM codes (i.e layout-agnostic key identifiers)
    pressed: set[DomCode] = set()
    # `keystrokes` is the list of keystrokes that have occurred since the last call to pop_keystrokes(),
    # as blessed `Keystroke` objects (i.e layout-aware data)
    keystrokes: list[Keystroke] = []

    # Note: keystrokes are typically used for ctrl-c/ctrl-d detection,
    # which is why they have to be layout-aware.
    # For instance, when a Bépo user presses ctrl+c (physically ctrl+h on US layout),
    # the terminal translates it to `\x03` (ETX) before putting it on stdin.

    with term.enable_kitty_keyboard(
        report_events=True,
        report_alternates=True,
        report_all_keys=True,
    ):

        def _update() -> None:
            while True:
                key = term.inkey(timeout=0)
                if not key:
                    break
                if not key.released:
                    keystrokes.append(key)
                dom_code = keystroke_to_dom_code(key)
                if dom_code is None:
                    continue
                if key.released:
                    pressed.discard(dom_code)
                else:
                    pressed.add(dom_code)

        def get_pressed() -> set[DomCode]:
            _update()
            return pressed.copy()

        def pop_keystrokes() -> list[Keystroke]:
            nonlocal keystrokes
            _update()
            result, keystrokes = keystrokes, []
            return result

        try:
            yield get_pressed, pop_keystrokes
        finally:
            pressed.clear()
