from enum import Enum, auto
from prompt_toolkit.keys import Keys


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

FUNCTIONAL_KEYS_TO_PT_KEYS = {
    FunctionalKeys.ESCAPE: Keys.Escape,
    FunctionalKeys.ENTER: Keys.Enter,
    FunctionalKeys.TAB: Keys.Tab,
    FunctionalKeys.BACKSPACE: Keys.Backspace,
    FunctionalKeys.INSERT: Keys.Insert,
    FunctionalKeys.DELETE: Keys.Delete,
    FunctionalKeys.LEFT: Keys.Left,
    FunctionalKeys.RIGHT: Keys.Right,
    FunctionalKeys.UP: Keys.Up,
    FunctionalKeys.DOWN: Keys.Down,
    FunctionalKeys.PAGE_UP: Keys.PageUp,
    FunctionalKeys.PAGE_DOWN: Keys.PageDown,
    FunctionalKeys.HOME: Keys.Home,
    FunctionalKeys.END: Keys.End,
    # FunctionalKeys.CAPS_LOCK: Keys.CapsLock,
    # FunctionalKeys.SCROLL_LOCK: Keys.ScrollLock,
    # FunctionalKeys.NUM_LOCK: Keys.NumLock,
    # FunctionalKeys.PRINT_SCREEN: Keys.PrintScreen,
    # FunctionalKeys.PAUSE: Keys.Pause,
    # FunctionalKeys.MENU: Keys.Menu,
    FunctionalKeys.F1: Keys.F1,
    FunctionalKeys.F2: Keys.F2,
    FunctionalKeys.F3: Keys.F3,
    FunctionalKeys.F4: Keys.F4,
    FunctionalKeys.F5: Keys.F5,
    FunctionalKeys.F6: Keys.F6,
    FunctionalKeys.F7: Keys.F7,
    FunctionalKeys.F8: Keys.F8,
    FunctionalKeys.F9: Keys.F9,
    FunctionalKeys.F10: Keys.F10,
    FunctionalKeys.F11: Keys.F11,
    FunctionalKeys.F12: Keys.F12,
    FunctionalKeys.F13: Keys.F13,
    FunctionalKeys.F14: Keys.F14,
    FunctionalKeys.F15: Keys.F15,
    FunctionalKeys.F16: Keys.F16,
    FunctionalKeys.F17: Keys.F17,
    FunctionalKeys.F18: Keys.F18,
    FunctionalKeys.F19: Keys.F19,
    FunctionalKeys.F20: Keys.F20,
    FunctionalKeys.F21: Keys.F21,
    FunctionalKeys.F22: Keys.F22,
    FunctionalKeys.F23: Keys.F23,
    FunctionalKeys.F24: Keys.F24,
    # FunctionalKeys.F25: Keys.F25,
    # FunctionalKeys.F26: Keys.F26,
    # FunctionalKeys.F27: Keys.F27,
    # FunctionalKeys.F28: Keys.F28,
    # FunctionalKeys.F29: Keys.F29,
    # FunctionalKeys.F30: Keys.F30,
    # FunctionalKeys.F31: Keys.F31,
    # FunctionalKeys.F32: Keys.F32,
    # FunctionalKeys.F33: Keys.F33,
    # FunctionalKeys.F34: Keys.F34,
    # FunctionalKeys.F35: Keys.F35,
    # FunctionalKeys.KP_0: Keys.Kp0,
    # FunctionalKeys.KP_1: Keys.Kp1,
    # FunctionalKeys.KP_2: Keys.Kp2,
    # FunctionalKeys.KP_3: Keys.Kp3,
    # FunctionalKeys.KP_4: Keys.Kp4,
    # FunctionalKeys.KP_5: Keys.Kp5,
    # FunctionalKeys.KP_6: Keys.Kp6,
    # FunctionalKeys.KP_7: Keys.Kp7,
    # FunctionalKeys.KP_8: Keys.Kp8,
    # FunctionalKeys.KP_9: Keys.Kp9,
    # FunctionalKeys.KP_DECIMAL: Keys.KpDecimal,
    # FunctionalKeys.KP_DIVIDE: Keys.KpDivide,
    # FunctionalKeys.KP_MULTIPLY: Keys.KpMultiply,
    # FunctionalKeys.KP_SUBTRACT: Keys.KpSubtract,
    # FunctionalKeys.KP_ADD: Keys.KpAdd,
    # FunctionalKeys.KP_ENTER: Keys.KpEnter,
    # FunctionalKeys.KP_EQUAL: Keys.KpEqual,
    # FunctionalKeys.KP_SEPARATOR: Keys.KpSeparator,
    # FunctionalKeys.KP_LEFT: Keys.KpLeft,
    # FunctionalKeys.KP_RIGHT: Keys.KpRight,
    # FunctionalKeys.KP_UP: Keys.KpUp,
    # FunctionalKeys.KP_DOWN: Keys.KpDown,
    # FunctionalKeys.KP_PAGE_UP: Keys.KpPageUp,
    # FunctionalKeys.KP_PAGE_DOWN: Keys.KpPageDown,
    # FunctionalKeys.KP_HOME: Keys.KpHome,
    # FunctionalKeys.KP_END: Keys.KpEnd,
    # FunctionalKeys.KP_INSERT: Keys.KpInsert,
    # FunctionalKeys.KP_DELETE: Keys.KpDelete,
    # FunctionalKeys.KP_BEGIN: Keys.KpBegin,
    # FunctionalKeys.MEDIA_PLAY: Keys.MediaPlay,
    # FunctionalKeys.MEDIA_PAUSE: Keys.MediaPause,
    # FunctionalKeys.MEDIA_PLAY_PAUSE: Keys.MediaPlayPause,
    # FunctionalKeys.MEDIA_REVERSE: Keys.MediaReverse,
    # FunctionalKeys.MEDIA_STOP: Keys.MediaStop,
    # FunctionalKeys.MEDIA_FAST_FORWARD: Keys.MediaFastForward,
    # FunctionalKeys.MEDIA_REWIND: Keys.MediaRewind,
    # FunctionalKeys.MEDIA_TRACK_NEXT: Keys.MediaTrackNext,
    # FunctionalKeys.MEDIA_TRACK_PREVIOUS: Keys.MediaTrackPrevious,
    # FunctionalKeys.MEDIA_RECORD: Keys.MediaRecord,
    # FunctionalKeys.LOWER_VOLUME: Keys.LowerVolume,
    # FunctionalKeys.RAISE_VOLUME: Keys.RaiseVolume,
    # FunctionalKeys.MUTE_VOLUME: Keys.MuteVolume,
    # FunctionalKeys.LEFT_SHIFT: Keys.LeftShift,
    # FunctionalKeys.LEFT_CONTROL: Keys.LeftControl,
    # FunctionalKeys.LEFT_ALT: Keys.LeftAlt,
    # FunctionalKeys.LEFT_SUPER: Keys.LeftSuper,
    # FunctionalKeys.LEFT_HYPER: Keys.LeftHyper,
    # FunctionalKeys.LEFT_META: Keys.LeftMeta,
    # FunctionalKeys.RIGHT_SHIFT: Keys.RightShift,
    # FunctionalKeys.RIGHT_CONTROL: Keys.RightControl,
    # FunctionalKeys.RIGHT_ALT: Keys.RightAlt,
    # FunctionalKeys.RIGHT_SUPER: Keys.RightSuper,
    # FunctionalKeys.RIGHT_HYPER: Keys.RightHyper,
    # FunctionalKeys.RIGHT_META: Keys.RightMeta,
    # FunctionalKeys.ISO_LEVEL3_SHIFT: Keys.IsoLevel3Shift,
    # FunctionalKeys.ISO_LEVEL5_SHIFT: Keys.IsoLevel5Shift,
}
