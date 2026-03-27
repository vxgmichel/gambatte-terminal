from __future__ import annotations

from enum import Enum, auto

from .dom_codes import DomCode

ASCII_PRINTABLE_TO_DOM_CODE: dict[str, DomCode] = {
    " ": DomCode.SPACE,
    "'": DomCode.QUOTE,
    ",": DomCode.COMMA,
    "-": DomCode.MINUS,
    ".": DomCode.PERIOD,
    "/": DomCode.SLASH,
    "0": DomCode.DIGIT0,
    "1": DomCode.DIGIT1,
    "2": DomCode.DIGIT2,
    "3": DomCode.DIGIT3,
    "4": DomCode.DIGIT4,
    "5": DomCode.DIGIT5,
    "6": DomCode.DIGIT6,
    "7": DomCode.DIGIT7,
    "8": DomCode.DIGIT8,
    "9": DomCode.DIGIT9,
    ";": DomCode.SEMICOLON,
    "=": DomCode.EQUAL,
    "a": DomCode.US_A,
    "b": DomCode.US_B,
    "c": DomCode.US_C,
    "d": DomCode.US_D,
    "e": DomCode.US_E,
    "f": DomCode.US_F,
    "g": DomCode.US_G,
    "h": DomCode.US_H,
    "i": DomCode.US_I,
    "j": DomCode.US_J,
    "k": DomCode.US_K,
    "l": DomCode.US_L,
    "m": DomCode.US_M,
    "n": DomCode.US_N,
    "o": DomCode.US_O,
    "p": DomCode.US_P,
    "q": DomCode.US_Q,
    "r": DomCode.US_R,
    "s": DomCode.US_S,
    "t": DomCode.US_T,
    "u": DomCode.US_U,
    "v": DomCode.US_V,
    "w": DomCode.US_W,
    "x": DomCode.US_X,
    "y": DomCode.US_Y,
    "z": DomCode.US_Z,
    "[": DomCode.BRACKET_LEFT,
    "\\": DomCode.BACKSLASH,
    "]": DomCode.BRACKET_RIGHT,
    "`": DomCode.BACKQUOTE,
    "<": DomCode.INTL_BACKSLASH,
}


class FunctionalKeys(Enum):
    ESCAPE = auto()
    ENTER = auto()
    TAB = auto()
    BACKSPACE = auto()
    INSERT = auto()
    DELETE = auto()
    LEFT = auto()
    RIGHT = auto()
    UP = auto()
    DOWN = auto()
    PAGE_UP = auto()
    PAGE_DOWN = auto()
    HOME = auto()
    END = auto()
    CAPS_LOCK = auto()
    SCROLL_LOCK = auto()
    NUM_LOCK = auto()
    PRINT_SCREEN = auto()
    PAUSE = auto()
    MENU = auto()
    F1 = auto()
    F2 = auto()
    F3 = auto()
    F4 = auto()
    F5 = auto()
    F6 = auto()
    F7 = auto()
    F8 = auto()
    F9 = auto()
    F10 = auto()
    F11 = auto()
    F12 = auto()
    F13 = auto()
    F14 = auto()
    F15 = auto()
    F16 = auto()
    F17 = auto()
    F18 = auto()
    F19 = auto()
    F20 = auto()
    F21 = auto()
    F22 = auto()
    F23 = auto()
    F24 = auto()
    F25 = auto()
    F26 = auto()
    F27 = auto()
    F28 = auto()
    F29 = auto()
    F30 = auto()
    F31 = auto()
    F32 = auto()
    F33 = auto()
    F34 = auto()
    F35 = auto()
    KP_0 = auto()
    KP_1 = auto()
    KP_2 = auto()
    KP_3 = auto()
    KP_4 = auto()
    KP_5 = auto()
    KP_6 = auto()
    KP_7 = auto()
    KP_8 = auto()
    KP_9 = auto()
    KP_DECIMAL = auto()
    KP_DIVIDE = auto()
    KP_MULTIPLY = auto()
    KP_SUBTRACT = auto()
    KP_ADD = auto()
    KP_ENTER = auto()
    KP_EQUAL = auto()
    KP_SEPARATOR = auto()
    KP_LEFT = auto()
    KP_RIGHT = auto()
    KP_UP = auto()
    KP_DOWN = auto()
    KP_PAGE_UP = auto()
    KP_PAGE_DOWN = auto()
    KP_HOME = auto()
    KP_END = auto()
    KP_INSERT = auto()
    KP_DELETE = auto()
    KP_BEGIN = auto()
    MEDIA_PLAY = auto()
    MEDIA_PAUSE = auto()
    MEDIA_PLAY_PAUSE = auto()
    MEDIA_REVERSE = auto()
    MEDIA_STOP = auto()
    MEDIA_FAST_FORWARD = auto()
    MEDIA_REWIND = auto()
    MEDIA_TRACK_NEXT = auto()
    MEDIA_TRACK_PREVIOUS = auto()
    MEDIA_RECORD = auto()
    LOWER_VOLUME = auto()
    RAISE_VOLUME = auto()
    MUTE_VOLUME = auto()
    LEFT_SHIFT = auto()
    LEFT_CONTROL = auto()
    LEFT_ALT = auto()
    LEFT_SUPER = auto()
    LEFT_HYPER = auto()
    LEFT_META = auto()
    RIGHT_SHIFT = auto()
    RIGHT_CONTROL = auto()
    RIGHT_ALT = auto()
    RIGHT_SUPER = auto()
    RIGHT_HYPER = auto()
    RIGHT_META = auto()
    ISO_LEVEL3_SHIFT = auto()
    ISO_LEVEL5_SHIFT = auto()


FUNCTIONAL_KEY_TO_DOM_CODE: dict[FunctionalKeys, DomCode] = {
    FunctionalKeys.ESCAPE: DomCode.ESCAPE,
    FunctionalKeys.ENTER: DomCode.ENTER,
    FunctionalKeys.TAB: DomCode.TAB,
    FunctionalKeys.BACKSPACE: DomCode.BACKSPACE,
    FunctionalKeys.INSERT: DomCode.INSERT,
    FunctionalKeys.DELETE: DomCode.DEL,
    FunctionalKeys.LEFT: DomCode.ARROW_LEFT,
    FunctionalKeys.RIGHT: DomCode.ARROW_RIGHT,
    FunctionalKeys.UP: DomCode.ARROW_UP,
    FunctionalKeys.DOWN: DomCode.ARROW_DOWN,
    FunctionalKeys.PAGE_UP: DomCode.PAGE_UP,
    FunctionalKeys.PAGE_DOWN: DomCode.PAGE_DOWN,
    FunctionalKeys.HOME: DomCode.HOME,
    FunctionalKeys.END: DomCode.END,
    FunctionalKeys.CAPS_LOCK: DomCode.CAPS_LOCK,
    FunctionalKeys.SCROLL_LOCK: DomCode.SCROLL_LOCK,
    FunctionalKeys.NUM_LOCK: DomCode.NUM_LOCK,
    FunctionalKeys.PRINT_SCREEN: DomCode.PRINT_SCREEN,
    FunctionalKeys.PAUSE: DomCode.PAUSE,
    FunctionalKeys.MENU: DomCode.CONTEXT_MENU,
    FunctionalKeys.F1: DomCode.F1,
    FunctionalKeys.F2: DomCode.F2,
    FunctionalKeys.F3: DomCode.F3,
    FunctionalKeys.F4: DomCode.F4,
    FunctionalKeys.F5: DomCode.F5,
    FunctionalKeys.F6: DomCode.F6,
    FunctionalKeys.F7: DomCode.F7,
    FunctionalKeys.F8: DomCode.F8,
    FunctionalKeys.F9: DomCode.F9,
    FunctionalKeys.F10: DomCode.F10,
    FunctionalKeys.F11: DomCode.F11,
    FunctionalKeys.F12: DomCode.F12,
    FunctionalKeys.F13: DomCode.F13,
    FunctionalKeys.F14: DomCode.F14,
    FunctionalKeys.F15: DomCode.F15,
    FunctionalKeys.F16: DomCode.F16,
    FunctionalKeys.F17: DomCode.F17,
    FunctionalKeys.F18: DomCode.F18,
    FunctionalKeys.F19: DomCode.F19,
    FunctionalKeys.F20: DomCode.F20,
    FunctionalKeys.F21: DomCode.F21,
    FunctionalKeys.F22: DomCode.F22,
    FunctionalKeys.F23: DomCode.F23,
    FunctionalKeys.F24: DomCode.F24,
    FunctionalKeys.KP_0: DomCode.NUMPAD0,
    FunctionalKeys.KP_1: DomCode.NUMPAD1,
    FunctionalKeys.KP_2: DomCode.NUMPAD2,
    FunctionalKeys.KP_3: DomCode.NUMPAD3,
    FunctionalKeys.KP_4: DomCode.NUMPAD4,
    FunctionalKeys.KP_5: DomCode.NUMPAD5,
    FunctionalKeys.KP_6: DomCode.NUMPAD6,
    FunctionalKeys.KP_7: DomCode.NUMPAD7,
    FunctionalKeys.KP_8: DomCode.NUMPAD8,
    FunctionalKeys.KP_9: DomCode.NUMPAD9,
    FunctionalKeys.KP_DECIMAL: DomCode.NUMPAD_DECIMAL,
    FunctionalKeys.KP_DIVIDE: DomCode.NUMPAD_DIVIDE,
    FunctionalKeys.KP_MULTIPLY: DomCode.NUMPAD_MULTIPLY,
    FunctionalKeys.KP_SUBTRACT: DomCode.NUMPAD_SUBTRACT,
    FunctionalKeys.KP_ADD: DomCode.NUMPAD_ADD,
    FunctionalKeys.KP_ENTER: DomCode.NUMPAD_ENTER,
    FunctionalKeys.KP_EQUAL: DomCode.NUMPAD_EQUAL,
    FunctionalKeys.KP_SEPARATOR: DomCode.NUMPAD_COMMA,
    FunctionalKeys.KP_LEFT: DomCode.NUMPAD4,
    FunctionalKeys.KP_RIGHT: DomCode.NUMPAD6,
    FunctionalKeys.KP_UP: DomCode.NUMPAD8,
    FunctionalKeys.KP_DOWN: DomCode.NUMPAD2,
    FunctionalKeys.KP_PAGE_UP: DomCode.NUMPAD9,
    FunctionalKeys.KP_PAGE_DOWN: DomCode.NUMPAD3,
    FunctionalKeys.KP_HOME: DomCode.NUMPAD7,
    FunctionalKeys.KP_END: DomCode.NUMPAD1,
    FunctionalKeys.KP_INSERT: DomCode.NUMPAD0,
    FunctionalKeys.KP_DELETE: DomCode.NUMPAD_DECIMAL,
    FunctionalKeys.KP_BEGIN: DomCode.NUMPAD5,
    FunctionalKeys.MEDIA_PLAY: DomCode.MEDIA_PLAY,
    FunctionalKeys.MEDIA_PAUSE: DomCode.MEDIA_PAUSE,
    FunctionalKeys.MEDIA_PLAY_PAUSE: DomCode.MEDIA_PLAY_PAUSE,
    FunctionalKeys.MEDIA_REVERSE: DomCode.MEDIA_REWIND,
    FunctionalKeys.MEDIA_STOP: DomCode.MEDIA_STOP,
    FunctionalKeys.MEDIA_FAST_FORWARD: DomCode.MEDIA_FAST_FORWARD,
    FunctionalKeys.MEDIA_REWIND: DomCode.MEDIA_REWIND,
    FunctionalKeys.MEDIA_TRACK_NEXT: DomCode.MEDIA_TRACK_NEXT,
    FunctionalKeys.MEDIA_TRACK_PREVIOUS: DomCode.MEDIA_TRACK_PREVIOUS,
    FunctionalKeys.MEDIA_RECORD: DomCode.MEDIA_RECORD,
    FunctionalKeys.LOWER_VOLUME: DomCode.VOLUME_DOWN,
    FunctionalKeys.RAISE_VOLUME: DomCode.VOLUME_UP,
    FunctionalKeys.MUTE_VOLUME: DomCode.VOLUME_MUTE,
    FunctionalKeys.LEFT_SHIFT: DomCode.SHIFT_LEFT,
    FunctionalKeys.LEFT_CONTROL: DomCode.CONTROL_LEFT,
    FunctionalKeys.LEFT_ALT: DomCode.ALT_LEFT,
    FunctionalKeys.LEFT_META: DomCode.META_LEFT,
    FunctionalKeys.RIGHT_SHIFT: DomCode.SHIFT_RIGHT,
    FunctionalKeys.RIGHT_CONTROL: DomCode.CONTROL_RIGHT,
    FunctionalKeys.RIGHT_ALT: DomCode.ALT_RIGHT,
    FunctionalKeys.RIGHT_META: DomCode.META_RIGHT,
    FunctionalKeys.ISO_LEVEL3_SHIFT: DomCode.ALT_RIGHT,
    FunctionalKeys.ISO_LEVEL5_SHIFT: DomCode.SHIFT_RIGHT,
}
