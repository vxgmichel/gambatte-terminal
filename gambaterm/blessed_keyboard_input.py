from __future__ import annotations

import re
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Callable, Iterator

from blessed import Terminal
from blessed.keyboard import Keystroke

from .dom_codes import DomCode
from .keys import ASCII_PRINTABLE_TO_DOM_CODE

_CPR_RE = re.compile(r"\x1b\[\d+;\d+R")


@dataclass
class KeyboardState:
    """Snapshot returned by a keyboard polling function."""

    pressed: set[DomCode] = field(default_factory=set)
    cpr_received: bool = False


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
    # Fall through to key_value for printable keys and any unrecognized
    # synthesized names (e.g. blessed returns "CSI" for '[')
    value = keystroke.key_value
    if value:
        return ASCII_PRINTABLE_TO_DOM_CODE.get(value)
    return None


@contextmanager
def blessed_key_pressed_context(
    term: Terminal,
) -> Iterator[Callable[[], KeyboardState]]:
    """Context manager providing a get_pressed() callable using blessed's kitty protocol."""
    state = KeyboardState()

    with term.enable_kitty_keyboard(
        report_events=True,
        report_alternates=True,
        report_all_keys=True,
    ):

        def get_pressed() -> KeyboardState:
            state.cpr_received = False
            while True:
                key = term.inkey(timeout=0)
                if not key:
                    break
                # Ctrl+C
                ctrl = key.modifiers_bits & 4
                if (
                    str(key) == "\x03"
                    or key.key_name == "KEY_CTRL_C"
                    or (ctrl and key.key_value == "c")
                ):
                    raise KeyboardInterrupt
                # Ctrl+D
                if (
                    str(key) == "\x04"
                    or key.key_name == "KEY_CTRL_D"
                    or (ctrl and key.key_value == "d")
                ):
                    raise OSError
                # Cursor position response
                if _CPR_RE.match(str(key)):
                    state.cpr_received = True
                    continue
                dom_code = keystroke_to_dom_code(key)
                if dom_code is None:
                    continue
                if key.released:
                    state.pressed.discard(dom_code)
                else:
                    state.pressed.add(dom_code)
            return state

        try:
            yield get_pressed
        finally:
            state.pressed.clear()
