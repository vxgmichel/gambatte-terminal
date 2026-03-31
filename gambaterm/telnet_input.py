from __future__ import annotations

import os
import re
import time
import codecs
import asyncio
import threading
from collections.abc import Mapping
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from blessed.keyboard import Keystroke
    from telnetlib3.stream_reader import TelnetReader
    from telnetlib3.stream_writer import TelnetWriter

from .console import Console

# Matches a complete cursor-position response: ESC [ row ; col R
_CPR_RE = re.compile(r"\x1b\[\d+;\d+R")
# Matches a partial CPR prefix at end of buffer (wait for more data)
_CPR_PREFIX_RE = re.compile(r"\x1b\[\d*[;\d]*\Z")
# Matches Ctrl+] in legacy (\x1d) or kitty keyboard protocol (\x1b[93;5...)
_CTRL_BRACKET_RIGHT_RE = re.compile(rb"\x1d|\x1b\[93;5[u;]")
# Kitty Ctrl+C (\x1b[99;5u) and Ctrl+D (\x1b[100;5u)
_KITTY_CTRL_CD_RE = re.compile(rb"\x1b\[(99|100);5[u;]")

# Auto-release time for legacy (non-kitty) clients (~9 frames at 60fps)
HOLD_DURATION = 0.15
# Once kitty is confirmed we have explicit release events
KITTY_CONFIRMED_HOLD = 5.0

# Blessed Keystroke name -> Console.Input
# Blessed key names -> Console.Input
KEY_INPUT_MAP: dict[str, Console.Input] = {
    "KEY_UP": Console.Input.UP,
    "KEY_DOWN": Console.Input.DOWN,
    "KEY_LEFT": Console.Input.LEFT,
    "KEY_RIGHT": Console.Input.RIGHT,
    "KEY_ENTER": Console.Input.START,
    "KEY_SHIFT_RIGHT": Console.Input.SELECT,
}

# Character value -> Console.Input
# Matches keyboard_input.py get_input_mapping() DOM code mappings:
#   Arrows + WASD for directions, Z/K for A, X/J for B
CHAR_INPUT_MAP: dict[str, Console.Input] = {
    "w": Console.Input.UP,
    "a": Console.Input.LEFT,
    "s": Console.Input.DOWN,
    "d": Console.Input.RIGHT,
    "z": Console.Input.A,
    "k": Console.Input.A,
    "x": Console.Input.B,
    "j": Console.Input.B,
}

# Character value -> Console.Event
CHAR_EVENT_MAP: dict[str, Console.Event] = {
    "0": Console.Event.SELECT_STATE_0,
    "1": Console.Event.SELECT_STATE_1,
    "2": Console.Event.SELECT_STATE_2,
    "3": Console.Event.SELECT_STATE_3,
    "4": Console.Event.SELECT_STATE_4,
    "5": Console.Event.SELECT_STATE_5,
    "6": Console.Event.SELECT_STATE_6,
    "7": Console.Event.SELECT_STATE_7,
    "8": Console.Event.SELECT_STATE_8,
    "9": Console.Event.SELECT_STATE_9,
    "[": Console.Event.SAVE_STATE,
    "]": Console.Event.LOAD_STATE,
}


class TelnetInputState:
    """Thread-safe input state shared between async reader and game thread."""

    def __init__(self) -> None:
        self._pressed: dict[Console.Input, float] = {}
        self._events: list[Console.Event] = []
        self._lock = threading.Lock()

    def press(self, button: Console.Input, hold_duration: float) -> None:
        """Register a button press with auto-release timestamp."""
        with self._lock:
            self._pressed[button] = time.monotonic() + hold_duration

    def release(self, button: Console.Input) -> None:
        """Release a button immediately."""
        with self._lock:
            self._pressed.pop(button, None)

    def get_input(self) -> set[Console.Input]:
        """Return currently pressed buttons, expiring old presses."""
        now = time.monotonic()
        with self._lock:
            expired = [b for b, t in self._pressed.items() if t <= now]
            for b in expired:
                del self._pressed[b]
            return set(self._pressed)

    def queue_event(self, event: Console.Event) -> None:
        """Queue an event for the game thread."""
        with self._lock:
            self._events.append(event)

    def pop_events(self) -> list[Console.Event]:
        """Drain and return queued events."""
        with self._lock:
            events = self._events
            self._events = []
            return events


def _build_blessed_maps() -> tuple[Mapping[str, int], dict[int, str], set[str]]:
    """Build blessed keyboard maps using a Terminal instance."""
    from blessed import Terminal

    term = Terminal(kind="xterm-256color", force_styling=True)
    return term._keymap, term._keycodes, term._keymap_prefixes


def _resolve_keystroke(
    text: str,
    mapper: Mapping[str, int],
    codes: dict[int, str],
    prefixes: set[str],
    dec_mode_cache: dict[int, int],
) -> Keystroke:
    """Resolve a keystroke from text using blessed's standalone parser."""
    from blessed.keyboard import resolve_sequence

    return resolve_sequence(
        text, mapper, codes, prefixes, dec_mode_cache=dec_mode_cache
    )


def _get_button(ks: Keystroke, codes: dict[int, str]) -> Console.Input | None:
    """Return the :class:`Console.Input` button for a keystroke, or ``None``.

    :param ks: resolved blessed Keystroke
    :param codes: blessed ``_keycodes`` mapping
    """
    name = ks.name
    if name:
        for suffix in ("_REPEATED", "_RELEASED"):
            if name.endswith(suffix):
                name = name[: -len(suffix)]
                break
        button = KEY_INPUT_MAP.get(name)
        if button is not None:
            return button

    if ks.uses_keyboard_protocol and ks._code is not None:
        base_name = codes.get(ks._code)
        if base_name:
            button = KEY_INPUT_MAP.get(base_name)
            if button is not None:
                return button

    if ks.uses_keyboard_protocol:
        char = ks.value
        if not char:
            match = getattr(ks, "_match", None)
            unicode_key = getattr(match, "unicode_key", None)
            if unicode_key is not None and 32 <= unicode_key <= 126:
                char = chr(unicode_key)
        if char and len(char) == 1:
            return CHAR_INPUT_MAP.get(char)

    char = str(ks)
    if len(char) == 1:
        return CHAR_INPUT_MAP.get(char)

    return None


def _map_keystroke(
    ks: Keystroke,
    state: TelnetInputState,
    kitty_detected: bool,
    codes: dict[int, str],
) -> bool:
    """Map a blessed Keystroke to input state updates.

    :param ks: resolved blessed Keystroke
    :param state: shared input state to update
    :param kitty_detected: whether kitty protocol has been seen this session
    :param codes: blessed ``_keycodes`` mapping
    :returns: updated kitty_detected flag
    """
    if ks.uses_keyboard_protocol and ks.released:
        kitty_detected = True
        button = _get_button(ks, codes)
        if button is not None:
            state.release(button)
        return kitty_detected

    if ks.uses_keyboard_protocol:
        kitty_detected = True
        hold = KITTY_CONFIRMED_HOLD
    elif kitty_detected:
        hold = KITTY_CONFIRMED_HOLD
    else:
        hold = HOLD_DURATION

    name = ks.name
    if name:
        base = name.removesuffix("_REPEATED")
        button = KEY_INPUT_MAP.get(base)
        if button is not None:
            state.press(button, hold)
            return kitty_detected

    if ks.uses_keyboard_protocol and ks._code is not None:
        base_name = codes.get(ks._code)
        if base_name:
            button = KEY_INPUT_MAP.get(base_name)
            if button is not None:
                state.press(button, hold)
                return kitty_detected

    char = ks.value if ks.uses_keyboard_protocol else str(ks)
    if len(char) == 1:
        if ks.uses_keyboard_protocol:
            match = getattr(ks, "_match", None)
            modifier = getattr(match, "modifier", 0) or 0
            if modifier > 1:
                return kitty_detected
        event = CHAR_EVENT_MAP.get(char)
        if event is not None:
            state.queue_event(event)
            return kitty_detected
        button = CHAR_INPUT_MAP.get(char)
        if button is not None:
            state.press(button, hold)
            return kitty_detected

    return kitty_detected


async def read_telnet_input(
    reader: TelnetReader,
    writer: TelnetWriter,
    state: TelnetInputState,
    input_write_fd: int,
) -> None:
    """Async reader loop: read bytes from telnet, parse keystrokes, update state.

    :param reader: telnetlib3 reader
    :param writer: telnetlib3 writer
    :param state: shared input state
    :param input_write_fd: write end of input pipe for forwarding Ctrl+C/D
    """
    mapper, codes, prefixes = _build_blessed_maps()
    dec_mode_cache: dict[int, int] = {}

    # Try to enable kitty keyboard protocol (disambiguate + report_events)
    writer.write(b"\x1b[=3u")

    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    kitty_detected = False
    buf = ""

    try:
        while True:
            data = await reader.read(4096)
            if not data:
                break
            raw = data if isinstance(data, bytes) else data.encode("latin-1")

            # Ctrl+] -- disconnect gracefully
            if _CTRL_BRACKET_RIGHT_RE.search(raw):
                try:
                    writer.write(b"\r\n\r\nCtrl+] received, disconnecting.\r\n")
                    writer.close()
                except (ConnectionError, OSError):
                    pass
                return

            # Forward Ctrl+C/D to input pipe for run.py detection
            if b"\x03" in raw:
                try:
                    os.write(input_write_fd, b"\x03")
                except OSError:
                    pass
            if b"\x04" in raw:
                try:
                    os.write(input_write_fd, b"\x04")
                except OSError:
                    pass
            # Kitty Ctrl+C/D arrive as \x1b[99;5u / \x1b[100;5u
            for km in _KITTY_CTRL_CD_RE.finditer(raw):
                byte = b"\x03" if km.group(1) == b"99" else b"\x04"
                try:
                    os.write(input_write_fd, byte)
                except OSError:
                    pass

            text = decoder.decode(raw)
            if not text:
                continue
            buf += text

            # Consume keystrokes from buffer
            while buf:
                m = _CPR_RE.match(buf)
                if m:
                    buf = buf[m.end() :]
                    continue
                if _CPR_PREFIX_RE.match(buf):
                    break
                ks = _resolve_keystroke(buf, mapper, codes, prefixes, dec_mode_cache)
                consumed = len(ks) if len(ks) > 0 else 1
                if consumed == 0:
                    break
                buf = buf[consumed:]
                kitty_detected = _map_keystroke(ks, state, kitty_detected, codes)
    except (asyncio.CancelledError, ConnectionError, EOFError):
        pass
    finally:
        # Cleanup: disable kitty protocol
        try:
            writer.write(b"\x1b[=0u")
        except (ConnectionError, OSError):
            pass
