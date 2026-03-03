from __future__ import annotations

from enum import Flag, IntEnum
import sys
import time
import logging
from contextlib import contextmanager, closing
from typing import Callable, Iterator, NamedTuple
from prompt_toolkit.application import create_app_session, AppSession
from prompt_toolkit.input.vt100_parser import Vt100Parser
from prompt_toolkit.keys import Keys as PromptToolkitKeys
from prompt_toolkit.key_binding import KeyPress

from .console import Console, InputGetter
from .keyboard_protocol import (
    CSI_TO_FUNCTIONAL_KEY,
    FUNCTIONAL_KEYS_TO_PT_KEYS,
    FunctionalKeys,
    LatinKeys,
    Keys,
)
from .ansi_escape_code import (
    CSI,
    detect_keyboard_protocol_support_parser,
    parse_ansi_escape_code,
    run_parser_in_app_session,
)


def get_input_mapping(console: Console) -> dict[Keys, Console.Input]:
    return {
        # Directions
        FunctionalKeys.UP: console.Input.UP,
        FunctionalKeys.DOWN: console.Input.DOWN,
        FunctionalKeys.LEFT: console.Input.LEFT,
        FunctionalKeys.RIGHT: console.Input.RIGHT,
        # A button
        LatinKeys.F: console.Input.A,
        LatinKeys.V: console.Input.A,
        LatinKeys.SPACE: console.Input.A,
        # B button
        LatinKeys.D: console.Input.B,
        LatinKeys.C: console.Input.B,
        FunctionalKeys.LEFT_ALT: console.Input.B,
        FunctionalKeys.RIGHT_ALT: console.Input.B,
        # Start button
        FunctionalKeys.ENTER: console.Input.START,
        FunctionalKeys.RIGHT_CONTROL: console.Input.START,
        # Select button
        FunctionalKeys.RIGHT_SHIFT: console.Input.SELECT,
        FunctionalKeys.BACKSPACE: console.Input.SELECT,
    }


def get_event_mapping(console: Console) -> dict[Keys, Console.Event]:
    return {
        LatinKeys.DIGIT_0: console.Event.SELECT_STATE_0,
        LatinKeys.DIGIT_1: console.Event.SELECT_STATE_1,
        LatinKeys.DIGIT_2: console.Event.SELECT_STATE_2,
        LatinKeys.DIGIT_3: console.Event.SELECT_STATE_3,
        LatinKeys.DIGIT_4: console.Event.SELECT_STATE_4,
        LatinKeys.DIGIT_5: console.Event.SELECT_STATE_5,
        LatinKeys.DIGIT_6: console.Event.SELECT_STATE_6,
        LatinKeys.DIGIT_7: console.Event.SELECT_STATE_7,
        LatinKeys.DIGIT_8: console.Event.SELECT_STATE_8,
        LatinKeys.DIGIT_9: console.Event.SELECT_STATE_9,
        LatinKeys.L: console.Event.LOAD_STATE,
        LatinKeys.K: console.Event.SAVE_STATE,
    }


@contextmanager
def xlib_key_pressed_context(
    display: str | None = None,
) -> Iterator[Callable[[], set[Keys]]]:
    from Xlib.ext import xinput
    from Xlib.display import Display

    with closing(Display(display)) as xdisplay:
        extension_info = xdisplay.query_extension("XInputExtension")
        xinput_major = extension_info is not None and extension_info.major_opcode
        # Set of currently pressed keys and focused flag
        pressed: set[Keys] = set()
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

        def get_pressed() -> set[Keys]:
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

                # Convert into
                key: Keys | None = LatinKeys.from_latin(keysym)
                if key is None:
                    key = FunctionalKeys.from_xlib_keysym(keysym)
                if key is None:
                    continue

                # Prepare info string
                info_string = f"keycode={keycode}, keysym={keysym}, modkeysym={modkeysym}, keystr={keystr}, key={key}"

                # Update the `pressed` set accordingly
                if is_key_pressed:
                    pressed.add(key)
                    logging.info("Key pressed: " + info_string)
                if is_key_released:
                    pressed.discard(key)
                    logging.info("Key released: " + info_string)

            # Return the currently pressed keys
            return pressed

        try:
            yield get_pressed
        finally:
            pressed.clear()


@contextmanager
def pynput_key_pressed_context() -> Iterator[Callable[[], set[Keys]]]:
    import pynput.keyboard  # type: ignore

    def on_press(key: pynput.keyboard.Key | pynput.keyboard.KeyCode | None) -> None:
        value: Keys | None
        if isinstance(key, pynput.keyboard.KeyCode):
            value = None if key.char is None else LatinKeys.from_latin(key.char)
        elif isinstance(key, pynput.keyboard.Key):
            value = FunctionalKeys.from_pynput_key(key)
        else:
            return
        if value is not None:
            pressed.add(value)

    def on_release(key: pynput.keyboard.Key | pynput.keyboard.KeyCode | None) -> None:
        value: Keys | None
        if isinstance(key, pynput.keyboard.KeyCode):
            value = None if key.char is None else LatinKeys.from_latin(key.char)
        elif isinstance(key, pynput.keyboard.Key):
            value = FunctionalKeys.from_pynput_key(key)
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


def make_get_input(
    console: Console,
    get_pressed: Callable[[], set[Keys]],
) -> InputGetter:
    current_pressed: set[Keys] = set()
    input_mapping = get_input_mapping(console)
    event_mapping = get_event_mapping(console)

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

    return get_input


@contextmanager
def console_input_from_keyboard_protocol_context(
    console: Console, app_session: AppSession
) -> Iterator[InputGetter]:
    with keyboard_protocol_key_pressed_context(app_session) as get_pressed:
        yield make_get_input(console, get_pressed)


@contextmanager
def console_input_from_x11_keyboard_context(
    console: Console, display: str | None = None
) -> Iterator[InputGetter]:
    with xlib_key_pressed_context(display) as get_pressed:
        yield make_get_input(console, get_pressed)


@contextmanager
def console_input_from_pynput_keyboard_context(
    console: Console,
) -> Iterator[InputGetter]:
    with pynput_key_pressed_context() as get_pressed:
        yield make_get_input(console, get_pressed)


@contextmanager
def console_input_from_keyboard_context(
    console: Console, app_session: AppSession, display: str | None = None
) -> Iterator[InputGetter]:
    if run_parser_in_app_session(
        app_session, detect_keyboard_protocol_support_parser
    ).is_supported():
        with console_input_from_keyboard_protocol_context(
            console, app_session
        ) as get_input:
            yield get_input
    elif sys.platform == "linux":
        with console_input_from_x11_keyboard_context(console, display) as get_input:
            yield get_input
    else:
        with console_input_from_pynput_keyboard_context(console) as get_input:
            yield get_input


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


class KeyboardProtocolEvent(NamedTuple):
    code: str
    char: int
    modifiers: Modifiers
    event_type: EventType
    raw_data: str

    def to_key(self) -> FunctionalKeys | LatinKeys | None:
        if self.code == "u":
            latin_key = LatinKeys.from_latin(self.char)
            if latin_key is not None:
                return latin_key
        return CSI_TO_FUNCTIONAL_KEY.get((self.code, self.char))

    def to_prompt_toolkit_key(self) -> PromptToolkitKeys | str:
        ctrl = "Control" if Modifiers.ctrl in self.modifiers else ""
        shift = "Shift" if Modifiers.shift in self.modifiers else ""
        # Functional keys
        maybe_key = CSI_TO_FUNCTIONAL_KEY.get((self.code, self.char))
        if maybe_key is not None:
            key = FUNCTIONAL_KEYS_TO_PT_KEYS.get(maybe_key, PromptToolkitKeys.Ignore)
            name = f"{ctrl}{shift}{key.name}"
            return getattr(PromptToolkitKeys, name, key)
        # ASCII keys
        if self.code == "u" and 0 <= self.char < 256:
            ascii = chr(self.char)
            upper = ascii.upper()
            name = f"{ctrl}{shift}{ASCII_SYMBOL_TO_NAME.get(ascii, upper)}"
            return getattr(PromptToolkitKeys, name, upper if shift else ascii)
        # Ignore
        return PromptToolkitKeys.Ignore

    def to_prompt_toolkit_key_press(self) -> KeyPress | None:
        if self.event_type == self.event_type.RELEASED:
            return None
        return KeyPress(self.to_prompt_toolkit_key(), self.raw_data)


class KeyboardProtocolParser(Vt100Parser):
    def __init__(self, vt100_input: Vt100Parser) -> None:
        super().__init__(vt100_input.feed_key_callback)
        self.pressed: set[Keys] = set()
        self.ansi_escape_code_parser = parse_ansi_escape_code()
        assert next(self.ansi_escape_code_parser) is None

    def get_pressed(self) -> set[Keys]:
        return self.pressed

    def _handle_event(self, event: KeyboardProtocolEvent) -> None:
        key = event.to_key()
        if key is None:
            return
        if event.event_type == event.event_type.PRESSED:
            self.pressed.add(key)
        elif event.event_type == event.event_type.RELEASED:
            self.pressed.discard(key)

    def feed(self, data: str) -> None:
        data_out: list[str] = []
        for char in data:
            item = self.ansi_escape_code_parser.send(char)
            if isinstance(item, str):
                data_out.append(item)
                continue
            if not isinstance(item, CSI):
                continue
            event = self._process_csi(item)
            if event is None:
                continue
            self._handle_event(event)
            key_press = event.to_prompt_toolkit_key_press()
            if key_press is None:
                continue
            self.feed_key_callback(key_press)
        super().feed("".join(data_out))

    def _process_csi(self, csi: CSI) -> KeyboardProtocolEvent | None:
        if csi.code not in "ABCDEFHPQSu~":
            return None
        if ";" not in csi.payload:
            raw_char = csi.payload
            raw_modifier = "1"
            raw_event = "1"
        else:
            raw_char, subpayload = csi.payload.split(";", maxsplit=1)
            if ":" not in subpayload:
                raw_modifier = subpayload
                raw_event = "1"
            else:
                raw_modifier, raw_event = subpayload.split(":", maxsplit=1)
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
        return KeyboardProtocolEvent(csi.code, char, modifier, event, csi.raw())


@contextmanager
def keyboard_protocol_key_pressed_context(
    app_session: AppSession,
) -> Iterator[Callable[[], set[Keys]]]:
    app_session.output.write_raw("\033[>11u")
    app_session.output.flush()
    if sys.platform == "win32":
        from prompt_toolkit.input.win32 import Win32Input

        assert isinstance(app_session.input, Win32Input)
        parser = KeyboardProtocolParser(app_session.input._vt100_parser)
        app_session.input._vt100_parser = parser
    else:
        from prompt_toolkit.input.vt100 import Vt100Input

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
) -> Iterator[Callable[[], set[Keys]]]:
    if run_parser_in_app_session(
        app_session, detect_keyboard_protocol_support_parser
    ).is_supported():
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
                        codes = (x.name for x in get_pressed())
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
