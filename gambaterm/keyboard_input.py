from __future__ import annotations

from enum import Flag, IntEnum
import sys
import time
import logging
from contextlib import contextmanager, closing
from typing import Callable, Iterator, TYPE_CHECKING, NamedTuple
from prompt_toolkit.application import create_app_session, AppSession
from prompt_toolkit.input.vt100 import Vt100Input
from prompt_toolkit.input.vt100_parser import Vt100Parser
from prompt_toolkit.keys import Keys
from prompt_toolkit.key_binding import KeyPress

from .console import Console, InputGetter
from .keyboard_protocol import CSI_TO_FUNCTIONAL_KEY, FUNCTIONAL_KEYS_TO_PT_KEYS


if TYPE_CHECKING:
    import pynput


def get_xlib_input_mapping(console: Console) -> dict[str, Console.Input]:
    return {
        # Directions
        "up": console.Input.UP,
        "down": console.Input.DOWN,
        "left": console.Input.LEFT,
        "right": console.Input.RIGHT,
        # A button
        "f": console.Input.A,
        "v": console.Input.A,
        "space": console.Input.A,
        # B button
        "d": console.Input.B,
        "c": console.Input.B,
        "alt_l": console.Input.B,
        "alt r": console.Input.B,
        # Start button
        "return": console.Input.START,
        "control_r": console.Input.START,
        # Select button
        "shift_r": console.Input.SELECT,
        "delete": console.Input.SELECT,
    }


def get_xlib_event_mapping(console: Console) -> dict[str, Console.Event]:
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


def get_pynput_input_mapping(console: Console) -> dict[str, Console.Input]:
    return {
        # Directions
        "up": console.Input.UP,
        "down": console.Input.DOWN,
        "left": console.Input.LEFT,
        "right": console.Input.RIGHT,
        # A button
        "f": console.Input.A,
        "v": console.Input.A,
        "space": console.Input.A,
        # B button
        "d": console.Input.B,
        "c": console.Input.B,
        "alt": console.Input.B,
        "alt_r": console.Input.B,
        # Start button
        "enter": console.Input.START,
        "ctrl_r": console.Input.START,
        # Select button
        "shift_r": console.Input.SELECT,
        "delete": console.Input.SELECT,
    }


def get_pynput_event_mapping(console: Console) -> dict[str, Console.Event]:
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


def get_keyboard_protocol_input_mapping(console: Console) -> dict[str, Console.Input]:
    return {
        # Directions
        "up": console.Input.UP,
        "down": console.Input.DOWN,
        "left": console.Input.LEFT,
        "right": console.Input.RIGHT,
        # A button
        "f": console.Input.A,
        "v": console.Input.A,
        " ": console.Input.A,
        # B button
        "d": console.Input.B,
        "c": console.Input.B,
        "left_alt": console.Input.B,
        "right_alt": console.Input.B,
        # Start button
        "enter": console.Input.START,
        "right_control": console.Input.START,
        # Select button
        "right_shift": console.Input.SELECT,
        "backspace": console.Input.SELECT,
    }


def get_keyboard_protocol_event_mapping(console: Console) -> dict[str, Console.Event]:
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
def xlib_key_pressed_context(
    display: str | None = None,
) -> Iterator[Callable[[], set[str]]]:
    from Xlib import XK
    from Xlib.ext import xinput
    from Xlib.display import Display

    with closing(Display(display)) as xdisplay:
        extension_info = xdisplay.query_extension("XInputExtension")
        xinput_major = extension_info is not None and extension_info.major_opcode
        # Set of currently pressed keys and focused flag
        pressed: set[str] = set()
        focused = True
        # Save current focus, as it is likely to be the terminal window
        term_window = xdisplay.get_input_focus().focus
        term_window.xinput_select_events(
            [(xinput.AllDevices, xinput.FocusInMask | xinput.FocusOutMask)]
        )
        # It is possible the select events directly on the terminal window, but for some
        # reasons, the events won't be propagated for some terminals like kitty.
        # Instead, we select the events on the root windows and then perform some
        # filtering.
        xdisplay.screen().root.xinput_select_events(
            [(xinput.AllDevices, xinput.KeyPressMask | xinput.KeyReleaseMask)]
        )

        # Build reverse lookup dict
        reverse_lookup = {
            v: k[3:].lower() for k, v in XK.__dict__.items() if k.startswith("XK_")
        }

        def get_pressed() -> set[str]:
            nonlocal focused
            # Loop over pending events
            while xdisplay.pending_events():
                event = xdisplay.next_event()
                # Unexpected events
                if not hasattr(event, "extension"):
                    continue
                if event.extension != xinput_major:
                    continue
                # Focus has been lost
                if event.evtype == xinput.FocusOut:
                    focused = False
                    pressed.clear()
                    continue
                # Focus has been retrieved
                if event.evtype == xinput.FocusIn:
                    focused = True
                    continue
                # The window is currently not focused
                if not focused:
                    continue
                # Extract key press/release information
                keycode = event.data.detail
                mods = event.data.mods.effective_mods
                keysym = xdisplay.keycode_to_keysym(keycode, 0)
                modkeysym = xdisplay.keycode_to_keysym(keycode, mods)
                keystr = xdisplay.lookup_string(keysym)
                repeat = event.data.flags & 0x10000
                is_key_pressed = event.evtype == xinput.KeyPress and not repeat
                is_key_released = event.evtype == xinput.KeyRelease
                keystr = reverse_lookup.get(keysym, "<unknown>")
                # Prepare info string
                info_string = f"keycode={keycode}, keysym={keysym}, keystr={keystr}"
                info_string += (
                    f"modkeysym={modkeysym}, keystr={keystr}, keystr={keystr}"
                )
                # Update the `pressed` set accordingly
                if is_key_pressed:
                    pressed.add(keystr)
                    logging.info("Key pressed: " + info_string)
                if is_key_released:
                    pressed.discard(keystr)
                    logging.info("Key released: " + info_string)

            # Return the currently pressed keys
            return pressed

        try:
            yield get_pressed
        finally:
            pressed.clear()


@contextmanager
def pynput_key_pressed_context() -> Iterator[Callable[[], set[str]]]:
    from pynput import keyboard

    def on_press(key: pynput.keyboard.Key | pynput.keyboard.KeyCode | None) -> None:
        if isinstance(key, pynput.keyboard.KeyCode):
            value = key.char
        elif isinstance(key, pynput.keyboard.Key):
            value = key.name
        else:
            return
        if value is not None:
            pressed.add(value.lower())

    def on_release(key: pynput.keyboard.Key | pynput.keyboard.KeyCode | None) -> None:
        if isinstance(key, pynput.keyboard.KeyCode):
            value = key.char
        elif isinstance(key, pynput.keyboard.Key):
            value = key.name
        else:
            return
        if value is not None:
            pressed.discard(value.lower())

    pressed: set[str] = set()
    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    try:
        listener.start()
        yield lambda: pressed
    finally:
        pressed.clear()
        listener.stop()


@contextmanager
def console_input_from_keyboard_context(
    console: Console, app_session: AppSession, display: str | None = None
) -> Iterator[InputGetter]:
    get_pressed: Callable[[], set[str]]
    current_pressed: set[str] = set()

    def get_input() -> set[Console.Input]:
        nonlocal current_pressed
        old_pressed, current_pressed = current_pressed, set(get_pressed())
        for event in map(event_mapping.get, current_pressed - old_pressed):
            if event is None:
                continue
            console.handle_event(event)
        return {
            input_mapping[keysym]
            for keysym in current_pressed
            if keysym in input_mapping
        }

    if detect_keyboard_protocol_support(app_session):
        input_mapping = get_keyboard_protocol_input_mapping(console)
        event_mapping = get_keyboard_protocol_event_mapping(console)
        with keyboard_protocol_key_pressed_context(app_session) as get_pressed:
            yield get_input
    elif sys.platform == "linux":
        input_mapping = get_xlib_input_mapping(console)
        event_mapping = get_xlib_event_mapping(console)
        with xlib_key_pressed_context(display) as get_pressed:
            yield get_input
    else:
        input_mapping = get_pynput_input_mapping(console)
        event_mapping = get_pynput_event_mapping(console)
        with pynput_key_pressed_context() as get_pressed:
            yield get_input


def detect_keyboard_protocol_support(app_session: AppSession) -> bool:
    # Query current progressive enhancement
    app_session.output.write_raw("\033[?u")
    # Query primary device attributes
    app_session.output.write_raw("\033[c")
    # Flush
    app_session.output.flush()
    # Wait for reply
    data = ""
    while "\033[?" not in data:
        keys = app_session.input.read_keys()
        data += "".join(x.data for x in keys)
    # Return whether comprehensive keyboard handling is supported
    _, first, *_ = data.split("\033[?")
    for c in first:
        if c.isalpha():
            return c == "u"
    return False


class EventType(IntEnum):
    PRESSED = 1
    REPEAT = 2
    RELEASED = 3


class Modifiers(Flag):
    shift = 0b1
    alt = 0b10
    ctrl = 0b100
    super = 0b1000
    hyper = 0b10000
    meta = 0b100000
    caps_lock = 0b1000000
    num_lock = 0b10000000


ASCII_SYMBOL_TO_NAME = {
    "@": "At",
    "\\": "Backslash",
    "]": "SquareClose",
    "^": "ControlCircumflex",
    "_": "Underscore",
}


class Event(NamedTuple):
    code: str
    char: int
    modifiers: Modifiers
    event_type: EventType
    raw_data: str

    def to_key(self) -> Keys | str:
        ctrl = "Control" if Modifiers.ctrl in self.modifiers else ""
        shift = "Shift" if Modifiers.shift in self.modifiers else ""
        # Functional keys
        maybe_key = CSI_TO_FUNCTIONAL_KEY.get((self.code, self.char))
        if maybe_key is not None:
            key = FUNCTIONAL_KEYS_TO_PT_KEYS.get(maybe_key, Keys.Ignore)
            name = f"{ctrl}{shift}{key.name}"
            return getattr(Keys, name, key)
        # ASCII keys
        if self.code == "u" and 0 <= self.char < 128:
            ascii = chr(self.char)
            upper = ascii.upper()
            name = f"{ctrl}{shift}{ASCII_SYMBOL_TO_NAME.get(ascii, upper)}"
            return getattr(Keys, name, upper if shift else ascii)
        # Ignore
        return Keys.Ignore

    def to_key_press(self) -> KeyPress | None:
        if self.event_type == self.event_type.RELEASED:
            return None
        return KeyPress(self.to_key(), self.raw_data)


class KeyboardProtocolParser(Vt100Parser):
    def __init__(self, vt100_input: Vt100Parser) -> None:
        super().__init__(vt100_input.feed_key_callback)
        self.pressed: set[str] = set()

    def get_pressed(self) -> set[str]:
        return self.pressed

    def _handle_event(self, event: Event) -> None:
        maybe_key = CSI_TO_FUNCTIONAL_KEY.get((event.code, event.char))
        if maybe_key is not None:
            str_key = maybe_key.value
        elif event.code == "u" and 0 <= event.char < 128:
            str_key = chr(event.char)
        else:
            return None
        if event.event_type == event.event_type.PRESSED:
            self.pressed.add(str_key)
        elif event.event_type == event.event_type.RELEASED:
            self.pressed.discard(str_key)

    def feed(self, data: str) -> None:
        it = iter(enumerate(data))
        i = 0
        for j, x in it:
            if x != "\033":
                continue
            k = self._extract_csi(it)
            if k is None:
                continue
            event = self._process_csi(data[j:k])
            if event is None:
                continue
            self._handle_event(event)
            key_press = event.to_key_press()
            if key_press is not None:
                self.feed_key_callback(key_press)
            if i != j:
                super().feed(data[i:j])
            i = k
        super().feed(data[i:])

    def _extract_csi(self, it: Iterator[tuple[int, str]]) -> int | None:
        k, c = next(it)
        if c != "[":
            return None
        for k, c in it:
            if c.isalpha() or c == "~":
                break
        else:
            return None
        return k + 1

    def _process_csi(self, data: str) -> Event | None:
        assert data[0:2] == "\033["
        code = data[-1]
        if code not in "ABCDEFHPQSu~":
            return None
        raw = data[2:-1]
        if ";" not in raw:
            raw_char = raw
            raw_modifier = "1"
            raw_event = "1"
        else:
            raw_char, raw = raw.split(";", maxsplit=1)
            if ":" not in raw:
                raw_modifier = raw
                raw_event = "1"
            else:
                raw_modifier, raw_event = raw.split(":", maxsplit=1)
        try:
            char = int(raw_char)
        except ValueError:
            return None
        try:
            modifier = Modifiers(int(raw_modifier) - 1)
        except ValueError:
            return None
        try:
            event = EventType(int(raw_event))
        except ValueError:
            return None
        return Event(code, char, modifier, event, data)


@contextmanager
def keyboard_protocol_key_pressed_context(
    app_session: AppSession,
) -> Iterator[Callable[[], set[str]]]:
    app_session.output.write_raw("\033[>11u")
    app_session.output.flush()
    assert isinstance(app_session.input, Vt100Input)
    parser = KeyboardProtocolParser(app_session.input.vt100_parser)
    app_session.input.vt100_parser = parser
    try:
        yield parser.get_pressed
    finally:
        app_session.output.write_raw("\033[<u")
        app_session.output.flush()


@contextmanager
def key_pressed_context(
    app_session: AppSession,
    display: str | None = None,
) -> Iterator[Callable[[], set[str]]]:
    if detect_keyboard_protocol_support(app_session):
        with keyboard_protocol_key_pressed_context(app_session) as get_pressed:
            yield get_pressed
    elif sys.platform == "linux":
        with xlib_key_pressed_context(display) as get_pressed:
            yield get_pressed
    else:
        with pynput_key_pressed_context() as get_pressed:
            yield get_pressed


def main() -> None:
    with create_app_session() as app_session:
        from prompt_toolkit.application import get_app_session

        assert get_app_session() is app_session
        with app_session.input.raw_mode():
            try:
                app_session.output.hide_cursor()
                with key_pressed_context(app_session) as get_pressed:
                    while True:
                        # Read keys
                        for key in app_session.input.read_keys():
                            if key.key == "c-c":
                                raise KeyboardInterrupt
                            if key.key == "c-d":
                                raise EOFError
                        # Get codes
                        codes = list(get_pressed())
                        # Print pressed key codes
                        print(*codes, flush=True, end="")
                        # Tick
                        time.sleep(1 / 30)
                        # Clear line and hide cursor
                        app_session.output.write_raw("\r")
                        app_session.output.erase_down()
                        # Flush output
                        app_session.output.flush()
            except (KeyboardInterrupt, EOFError):
                pass
            finally:
                app_session.output.show_cursor()
                app_session.output.flush()
                print()


if __name__ == "__main__":
    main()
