from __future__ import annotations

from enum import Flag, IntEnum
import sys
from contextlib import contextmanager
from typing import Callable, Iterator, NamedTuple
from prompt_toolkit.application import AppSession
from prompt_toolkit.input.vt100_parser import Vt100Parser
from prompt_toolkit.keys import Keys as PromptToolkitKeys
from prompt_toolkit.key_binding import KeyPress

from .dom_codes import DomCode
from .keys import (
    FunctionalKeys,
    ASCII_PRINTABLE_TO_DOM_CODE,
    FUNCTIONAL_KEY_TO_DOM_CODE,
)
from .ansi_escape_code import (
    CSI,
    parse_ansi_escape_code,
)

CSI_TO_FUNCTIONAL_KEY = {
    ("u", 27): FunctionalKeys.ESCAPE,
    ("u", 13): FunctionalKeys.ENTER,
    ("u", 9): FunctionalKeys.TAB,
    ("u", 127): FunctionalKeys.BACKSPACE,
    ("~", 2): FunctionalKeys.INSERT,
    ("~", 3): FunctionalKeys.DELETE,
    ("D", 1): FunctionalKeys.LEFT,
    ("C", 1): FunctionalKeys.RIGHT,
    ("A", 1): FunctionalKeys.UP,
    ("B", 1): FunctionalKeys.DOWN,
    ("~", 5): FunctionalKeys.PAGE_UP,
    ("~", 6): FunctionalKeys.PAGE_DOWN,
    ("H", 1): FunctionalKeys.HOME,
    ("~", 7): FunctionalKeys.HOME,
    ("F", 1): FunctionalKeys.END,
    ("~", 8): FunctionalKeys.END,
    ("u", 57358): FunctionalKeys.CAPS_LOCK,
    ("u", 57359): FunctionalKeys.SCROLL_LOCK,
    ("u", 57360): FunctionalKeys.NUM_LOCK,
    ("u", 57361): FunctionalKeys.PRINT_SCREEN,
    ("u", 57362): FunctionalKeys.PAUSE,
    ("u", 57363): FunctionalKeys.MENU,
    ("P", 1): FunctionalKeys.F1,
    ("~", 11): FunctionalKeys.F1,
    ("Q", 1): FunctionalKeys.F2,
    ("~", 12): FunctionalKeys.F2,
    ("~", 13): FunctionalKeys.F3,
    ("S", 1): FunctionalKeys.F4,
    ("~", 14): FunctionalKeys.F4,
    ("~", 15): FunctionalKeys.F5,
    ("~", 17): FunctionalKeys.F6,
    ("~", 18): FunctionalKeys.F7,
    ("~", 19): FunctionalKeys.F8,
    ("~", 20): FunctionalKeys.F9,
    ("~", 21): FunctionalKeys.F10,
    ("~", 23): FunctionalKeys.F11,
    ("~", 24): FunctionalKeys.F12,
    ("u", 57376): FunctionalKeys.F13,
    ("u", 57377): FunctionalKeys.F14,
    ("u", 57378): FunctionalKeys.F15,
    ("u", 57379): FunctionalKeys.F16,
    ("u", 57380): FunctionalKeys.F17,
    ("u", 57381): FunctionalKeys.F18,
    ("u", 57382): FunctionalKeys.F19,
    ("u", 57383): FunctionalKeys.F20,
    ("u", 57384): FunctionalKeys.F21,
    ("u", 57385): FunctionalKeys.F22,
    ("u", 57386): FunctionalKeys.F23,
    ("u", 57387): FunctionalKeys.F24,
    ("u", 57388): FunctionalKeys.F25,
    ("u", 57389): FunctionalKeys.F26,
    ("u", 57390): FunctionalKeys.F27,
    ("u", 57391): FunctionalKeys.F28,
    ("u", 57392): FunctionalKeys.F29,
    ("u", 57393): FunctionalKeys.F30,
    ("u", 57394): FunctionalKeys.F31,
    ("u", 57395): FunctionalKeys.F32,
    ("u", 57396): FunctionalKeys.F33,
    ("u", 57397): FunctionalKeys.F34,
    ("u", 57398): FunctionalKeys.F35,
    ("u", 57399): FunctionalKeys.KP_0,
    ("u", 57400): FunctionalKeys.KP_1,
    ("u", 57401): FunctionalKeys.KP_2,
    ("u", 57402): FunctionalKeys.KP_3,
    ("u", 57403): FunctionalKeys.KP_4,
    ("u", 57404): FunctionalKeys.KP_5,
    ("u", 57405): FunctionalKeys.KP_6,
    ("u", 57406): FunctionalKeys.KP_7,
    ("u", 57407): FunctionalKeys.KP_8,
    ("u", 57408): FunctionalKeys.KP_9,
    ("u", 57409): FunctionalKeys.KP_DECIMAL,
    ("u", 57410): FunctionalKeys.KP_DIVIDE,
    ("u", 57411): FunctionalKeys.KP_MULTIPLY,
    ("u", 57412): FunctionalKeys.KP_SUBTRACT,
    ("u", 57413): FunctionalKeys.KP_ADD,
    ("u", 57414): FunctionalKeys.KP_ENTER,
    ("u", 57415): FunctionalKeys.KP_EQUAL,
    ("u", 57416): FunctionalKeys.KP_SEPARATOR,
    ("u", 57417): FunctionalKeys.KP_LEFT,
    ("u", 57418): FunctionalKeys.KP_RIGHT,
    ("u", 57419): FunctionalKeys.KP_UP,
    ("u", 57420): FunctionalKeys.KP_DOWN,
    ("u", 57421): FunctionalKeys.KP_PAGE_UP,
    ("u", 57422): FunctionalKeys.KP_PAGE_DOWN,
    ("u", 57423): FunctionalKeys.KP_HOME,
    ("u", 57424): FunctionalKeys.KP_END,
    ("u", 57425): FunctionalKeys.KP_INSERT,
    ("u", 57426): FunctionalKeys.KP_DELETE,
    ("~", 57427): FunctionalKeys.KP_BEGIN,
    ("E", 1): FunctionalKeys.KP_BEGIN,
    ("u", 57428): FunctionalKeys.MEDIA_PLAY,
    ("u", 57429): FunctionalKeys.MEDIA_PAUSE,
    ("u", 57430): FunctionalKeys.MEDIA_PLAY_PAUSE,
    ("u", 57431): FunctionalKeys.MEDIA_REVERSE,
    ("u", 57432): FunctionalKeys.MEDIA_STOP,
    ("u", 57433): FunctionalKeys.MEDIA_FAST_FORWARD,
    ("u", 57434): FunctionalKeys.MEDIA_REWIND,
    ("u", 57435): FunctionalKeys.MEDIA_TRACK_NEXT,
    ("u", 57436): FunctionalKeys.MEDIA_TRACK_PREVIOUS,
    ("u", 57437): FunctionalKeys.MEDIA_RECORD,
    ("u", 57438): FunctionalKeys.LOWER_VOLUME,
    ("u", 57439): FunctionalKeys.RAISE_VOLUME,
    ("u", 57440): FunctionalKeys.MUTE_VOLUME,
    ("u", 57441): FunctionalKeys.LEFT_SHIFT,
    ("u", 57442): FunctionalKeys.LEFT_CONTROL,
    ("u", 57443): FunctionalKeys.LEFT_ALT,
    ("u", 57444): FunctionalKeys.LEFT_SUPER,
    ("u", 57445): FunctionalKeys.LEFT_HYPER,
    ("u", 57446): FunctionalKeys.LEFT_META,
    ("u", 57447): FunctionalKeys.RIGHT_SHIFT,
    ("u", 57448): FunctionalKeys.RIGHT_CONTROL,
    ("u", 57449): FunctionalKeys.RIGHT_ALT,
    ("u", 57450): FunctionalKeys.RIGHT_SUPER,
    ("u", 57451): FunctionalKeys.RIGHT_HYPER,
    ("u", 57452): FunctionalKeys.RIGHT_META,
    ("u", 57453): FunctionalKeys.ISO_LEVEL3_SHIFT,
    ("u", 57454): FunctionalKeys.ISO_LEVEL5_SHIFT,
}


FUNCTIONAL_KEY_TO_PROMPT_TOOLKIT_KEY = {
    FunctionalKeys.ESCAPE: PromptToolkitKeys.Escape,
    FunctionalKeys.ENTER: PromptToolkitKeys.Enter,
    FunctionalKeys.TAB: PromptToolkitKeys.Tab,
    FunctionalKeys.BACKSPACE: PromptToolkitKeys.Backspace,
    FunctionalKeys.INSERT: PromptToolkitKeys.Insert,
    FunctionalKeys.DELETE: PromptToolkitKeys.Delete,
    FunctionalKeys.LEFT: PromptToolkitKeys.Left,
    FunctionalKeys.RIGHT: PromptToolkitKeys.Right,
    FunctionalKeys.UP: PromptToolkitKeys.Up,
    FunctionalKeys.DOWN: PromptToolkitKeys.Down,
    FunctionalKeys.PAGE_UP: PromptToolkitKeys.PageUp,
    FunctionalKeys.PAGE_DOWN: PromptToolkitKeys.PageDown,
    FunctionalKeys.HOME: PromptToolkitKeys.Home,
    FunctionalKeys.END: PromptToolkitKeys.End,
    # FunctionalKeys.CAPS_LOCK: PromptToolkitKeys.CapsLock,
    # FunctionalKeys.SCROLL_LOCK: PromptToolkitKeys.ScrollLock,
    # FunctionalKeys.NUM_LOCK: PromptToolkitKeys.NumLock,
    # FunctionalKeys.PRINT_SCREEN: PromptToolkitKeys.PrintScreen,
    # FunctionalKeys.PAUSE: PromptToolkitKeys.Pause,
    # FunctionalKeys.MENU: PromptToolkitKeys.Menu,
    FunctionalKeys.F1: PromptToolkitKeys.F1,
    FunctionalKeys.F2: PromptToolkitKeys.F2,
    FunctionalKeys.F3: PromptToolkitKeys.F3,
    FunctionalKeys.F4: PromptToolkitKeys.F4,
    FunctionalKeys.F5: PromptToolkitKeys.F5,
    FunctionalKeys.F6: PromptToolkitKeys.F6,
    FunctionalKeys.F7: PromptToolkitKeys.F7,
    FunctionalKeys.F8: PromptToolkitKeys.F8,
    FunctionalKeys.F9: PromptToolkitKeys.F9,
    FunctionalKeys.F10: PromptToolkitKeys.F10,
    FunctionalKeys.F11: PromptToolkitKeys.F11,
    FunctionalKeys.F12: PromptToolkitKeys.F12,
    FunctionalKeys.F13: PromptToolkitKeys.F13,
    FunctionalKeys.F14: PromptToolkitKeys.F14,
    FunctionalKeys.F15: PromptToolkitKeys.F15,
    FunctionalKeys.F16: PromptToolkitKeys.F16,
    FunctionalKeys.F17: PromptToolkitKeys.F17,
    FunctionalKeys.F18: PromptToolkitKeys.F18,
    FunctionalKeys.F19: PromptToolkitKeys.F19,
    FunctionalKeys.F20: PromptToolkitKeys.F20,
    FunctionalKeys.F21: PromptToolkitKeys.F21,
    FunctionalKeys.F22: PromptToolkitKeys.F22,
    FunctionalKeys.F23: PromptToolkitKeys.F23,
    FunctionalKeys.F24: PromptToolkitKeys.F24,
    # FunctionalKeys.F25: PromptToolkitKeys.F25,
    # FunctionalKeys.F26: PromptToolkitKeys.F26,
    # FunctionalKeys.F27: PromptToolkitKeys.F27,
    # FunctionalKeys.F28: PromptToolkitKeys.F28,
    # FunctionalKeys.F29: PromptToolkitKeys.F29,
    # FunctionalKeys.F30: PromptToolkitKeys.F30,
    # FunctionalKeys.F31: PromptToolkitKeys.F31,
    # FunctionalKeys.F32: PromptToolkitKeys.F32,
    # FunctionalKeys.F33: PromptToolkitKeys.F33,
    # FunctionalKeys.F34: PromptToolkitKeys.F34,
    # FunctionalKeys.F35: PromptToolkitKeys.F35,
    # FunctionalKeys.KP_0: PromptToolkitKeys.Kp0,
    # FunctionalKeys.KP_1: PromptToolkitKeys.Kp1,
    # FunctionalKeys.KP_2: PromptToolkitKeys.Kp2,
    # FunctionalKeys.KP_3: PromptToolkitKeys.Kp3,
    # FunctionalKeys.KP_4: PromptToolkitKeys.Kp4,
    # FunctionalKeys.KP_5: PromptToolkitKeys.Kp5,
    # FunctionalKeys.KP_6: PromptToolkitKeys.Kp6,
    # FunctionalKeys.KP_7: PromptToolkitKeys.Kp7,
    # FunctionalKeys.KP_8: PromptToolkitKeys.Kp8,
    # FunctionalKeys.KP_9: PromptToolkitKeys.Kp9,
    # FunctionalKeys.KP_DECIMAL: PromptToolkitKeys.KpDecimal,
    # FunctionalKeys.KP_DIVIDE: PromptToolkitKeys.KpDivide,
    # FunctionalKeys.KP_MULTIPLY: PromptToolkitKeys.KpMultiply,
    # FunctionalKeys.KP_SUBTRACT: PromptToolkitKeys.KpSubtract,
    # FunctionalKeys.KP_ADD: PromptToolkitKeys.KpAdd,
    # FunctionalKeys.KP_ENTER: PromptToolkitKeys.KpEnter,
    # FunctionalKeys.KP_EQUAL: PromptToolkitKeys.KpEqual,
    # FunctionalKeys.KP_SEPARATOR: PromptToolkitKeys.KpSeparator,
    # FunctionalKeys.KP_LEFT: PromptToolkitKeys.KpLeft,
    # FunctionalKeys.KP_RIGHT: PromptToolkitKeys.KpRight,
    # FunctionalKeys.KP_UP: PromptToolkitKeys.KpUp,
    # FunctionalKeys.KP_DOWN: PromptToolkitKeys.KpDown,
    # FunctionalKeys.KP_PAGE_UP: PromptToolkitKeys.KpPageUp,
    # FunctionalKeys.KP_PAGE_DOWN: PromptToolkitKeys.KpPageDown,
    # FunctionalKeys.KP_HOME: PromptToolkitKeys.KpHome,
    # FunctionalKeys.KP_END: PromptToolkitKeys.KpEnd,
    # FunctionalKeys.KP_INSERT: PromptToolkitKeys.KpInsert,
    # FunctionalKeys.KP_DELETE: PromptToolkitKeys.KpDelete,
    # FunctionalKeys.KP_BEGIN: PromptToolkitKeys.KpBegin,
    # FunctionalKeys.MEDIA_PLAY: PromptToolkitKeys.MediaPlay,
    # FunctionalKeys.MEDIA_PAUSE: PromptToolkitKeys.MediaPause,
    # FunctionalKeys.MEDIA_PLAY_PAUSE: PromptToolkitKeys.MediaPlayPause,
    # FunctionalKeys.MEDIA_REVERSE: PromptToolkitKeys.MediaReverse,
    # FunctionalKeys.MEDIA_STOP: PromptToolkitKeys.MediaStop,
    # FunctionalKeys.MEDIA_FAST_FORWARD: PromptToolkitKeys.MediaFastForward,
    # FunctionalKeys.MEDIA_REWIND: PromptToolkitKeys.MediaRewind,
    # FunctionalKeys.MEDIA_TRACK_NEXT: PromptToolkitKeys.MediaTrackNext,
    # FunctionalKeys.MEDIA_TRACK_PREVIOUS: PromptToolkitKeys.MediaTrackPrevious,
    # FunctionalKeys.MEDIA_RECORD: PromptToolkitKeys.MediaRecord,
    # FunctionalKeys.LOWER_VOLUME: PromptToolkitKeys.LowerVolume,
    # FunctionalKeys.RAISE_VOLUME: PromptToolkitKeys.RaiseVolume,
    # FunctionalKeys.MUTE_VOLUME: PromptToolkitKeys.MuteVolume,
    # FunctionalKeys.LEFT_SHIFT: PromptToolkitKeys.LeftShift,
    # FunctionalKeys.LEFT_CONTROL: PromptToolkitKeys.LeftControl,
    # FunctionalKeys.LEFT_ALT: PromptToolkitKeys.LeftAlt,
    # FunctionalKeys.LEFT_SUPER: PromptToolkitKeys.LeftSuper,
    # FunctionalKeys.LEFT_HYPER: PromptToolkitKeys.LeftHyper,
    # FunctionalKeys.LEFT_META: PromptToolkitKeys.LeftMeta,
    # FunctionalKeys.RIGHT_SHIFT: PromptToolkitKeys.RightShift,
    # FunctionalKeys.RIGHT_CONTROL: PromptToolkitKeys.RightControl,
    # FunctionalKeys.RIGHT_ALT: PromptToolkitKeys.RightAlt,
    # FunctionalKeys.RIGHT_SUPER: PromptToolkitKeys.RightSuper,
    # FunctionalKeys.RIGHT_HYPER: PromptToolkitKeys.RightHyper,
    # FunctionalKeys.RIGHT_META: PromptToolkitKeys.RightMeta,
    # FunctionalKeys.ISO_LEVEL3_SHIFT: PromptToolkitKeys.IsoLevel3Shift,
    # FunctionalKeys.ISO_LEVEL5_SHIFT: PromptToolkitKeys.IsoLevel5Shift,
}


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
    shifted: int | None
    base_layout: int | None
    modifiers: Modifiers
    event_type: EventType
    codepoints: str
    raw_data: str

    def to_key(self) -> DomCode | None:
        char = self.base_layout if self.base_layout is not None else self.char
        if self.code == "u" and 0 <= char < 128:
            ascii = chr(char)
            dom_code = ASCII_PRINTABLE_TO_DOM_CODE.get(ascii)
            if dom_code is not None:
                return dom_code
        functional_key = CSI_TO_FUNCTIONAL_KEY.get((self.code, char))
        if functional_key is None:
            return None
        return FUNCTIONAL_KEY_TO_DOM_CODE.get(functional_key, None)

    def to_prompt_toolkit_key(self) -> PromptToolkitKeys | str:
        ctrl = "Control" if Modifiers.ctrl in self.modifiers else ""
        shift = "Shift" if Modifiers.shift in self.modifiers else ""
        # ASCII keys
        if self.code == "u" and 0 <= self.char < 256:
            ascii = chr(self.char)
            upper = ascii.upper()
            name = f"{ctrl}{shift}{ASCII_SYMBOL_TO_NAME.get(ascii, upper)}"
            return getattr(PromptToolkitKeys, name, upper if shift else ascii)
        # Functional keys
        maybe_key = CSI_TO_FUNCTIONAL_KEY.get((self.code, self.char))
        if maybe_key is None:
            return PromptToolkitKeys.Ignore
        prompt_toolkit_key = FUNCTIONAL_KEY_TO_PROMPT_TOOLKIT_KEY.get(maybe_key)
        if prompt_toolkit_key is None:
            return PromptToolkitKeys.Ignore
        name = f"{ctrl}{shift}{prompt_toolkit_key.name}"
        return getattr(PromptToolkitKeys, name, PromptToolkitKeys.Ignore)

    def to_prompt_toolkit_key_press(self) -> KeyPress | None:
        if self.event_type == self.event_type.RELEASED:
            return KeyPress(PromptToolkitKeys.Ignore, self.raw_data)
        return KeyPress(self.to_prompt_toolkit_key(), self.raw_data)


class KeyboardProtocolParser(Vt100Parser):
    def __init__(self, vt100_input: Vt100Parser) -> None:
        super().__init__(vt100_input.feed_key_callback)
        self.pressed: set[DomCode] = set()
        self.ansi_escape_code_parser = parse_ansi_escape_code()
        assert not next(self.ansi_escape_code_parser)

    def get_pressed(self) -> set[DomCode]:
        return self.pressed

    def feed(self, data: str) -> None:
        data_out: list[str] = []
        ready = self.ansi_escape_code_parser.send(data)
        for item in ready:
            if item is None:
                continue
            if isinstance(item, str):
                data_out.append(item)
                continue
            if not isinstance(item, CSI):
                data_out.append(item.raw())
                continue
            event = self._process_csi(item)
            if event is None:
                data_out.append(item.raw())
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

        # Parse payload
        payload_splitted = csi.payload.split(";", maxsplit=2)
        raw_event_info: str = ""
        raw_codepoints: str = ""
        if len(payload_splitted) == 1:
            (raw_keycode,) = payload_splitted
        elif len(payload_splitted) == 2:
            raw_keycode, raw_event_info = payload_splitted
        elif len(payload_splitted) == 3:
            raw_keycode, raw_event_info, raw_codepoints = payload_splitted
        else:
            assert False

        # Parse key code
        keycode_splitted = raw_keycode.split(":", maxsplit=2)
        raw_shifted: str = ""
        raw_base_layout: str = ""
        if len(keycode_splitted) == 1:
            (raw_char,) = keycode_splitted
        elif len(keycode_splitted) == 2:
            raw_char, raw_shifted = keycode_splitted
        elif len(keycode_splitted) == 3:
            raw_char, raw_shifted, raw_base_layout = keycode_splitted
        else:
            assert False

        # Parse event info
        raw_modifier: str = ""
        raw_event: str = ""
        if raw_event_info is not None:
            event_info_splitted = raw_event_info.split(":", maxsplit=1)
            if len(event_info_splitted) == 1:
                (raw_modifier,) = event_info_splitted
            elif len(event_info_splitted) == 2:
                raw_modifier, raw_event = event_info_splitted
            else:
                assert False

        # Parse codepoints
        codepoints = ""
        if raw_codepoints:
            for raw_codepoint in raw_codepoints.split(":"):
                try:
                    codepoints += chr(int(raw_codepoint))
                except ValueError:
                    return None

        try:
            char = int(raw_char)
        except ValueError:
            return None
        try:
            shifted = int(raw_shifted) if raw_shifted else None
        except ValueError:
            return None
        try:
            base_layout = int(raw_base_layout) if raw_base_layout else None
        except ValueError:
            return None
        try:
            modifier = (
                Modifiers(int(raw_modifier) - 1) if raw_modifier else Modifiers(0)
            )
        except ValueError:
            return None
        try:
            event = EventType(int(raw_event)) if raw_event else EventType.PRESSED
        except ValueError:
            return None
        return KeyboardProtocolEvent(
            csi.code, char, shifted, base_layout, modifier, event, codepoints, csi.raw()
        )

    def _handle_event(self, event: KeyboardProtocolEvent) -> None:
        key = event.to_key()
        if key is None:
            return
        if event.event_type == event.event_type.PRESSED:
            self.pressed.add(key)
        elif event.event_type == event.event_type.RELEASED:
            self.pressed.discard(key)


@contextmanager
def keyboard_protocol_key_pressed_context(
    app_session: AppSession,
) -> Iterator[Callable[[], set[DomCode]]]:
    app_session.output.write_raw("\033[>31u")
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
