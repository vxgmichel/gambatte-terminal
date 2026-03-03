from __future__ import annotations

from enum import Enum, auto
from prompt_toolkit.keys import Keys as PromptToolkitKeys

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pynput.keyboard  # type: ignore


XLIB_SYMKEY_TO_FUNCTIONAL_KEY_MAPPING: dict[int, FunctionalKeys] = {}
PYNPUT_KEY_TO_FUNCTIONAL_KEY_MAPPING: dict[pynput.keyboard.Key, Keys] = {}


def initialize_xlib_symkey_to_functional_key_mapping() -> None:
    from Xlib import XK

    XLIB_SYMKEY_TO_FUNCTIONAL_KEY_MAPPING.update(
        {
            XK.XK_BackSpace: FunctionalKeys.BACKSPACE,
            XK.XK_Tab: FunctionalKeys.TAB,
            # XK.XK_Linefeed: FunctionalKeys.NOT_FOUND,
            # XK.XK_Clear: FunctionalKeys.NOT_FOUND,
            XK.XK_Return: FunctionalKeys.ENTER,
            XK.XK_Pause: FunctionalKeys.PAUSE,
            XK.XK_Scroll_Lock: FunctionalKeys.SCROLL_LOCK,
            # XK.XK_Sys_Req: FunctionalKeys.NOT_FOUND,
            XK.XK_Escape: FunctionalKeys.ESCAPE,
            # XK.XK_Multi_key: FunctionalKeys.NOT_FOUND,
            # XK.XK_Kanji: FunctionalKeys.NOT_FOUND,
            # XK.XK_Muhenkan: FunctionalKeys.NOT_FOUND,
            # XK.XK_Henkan_Mode: FunctionalKeys.NOT_FOUND,
            # XK.XK_Romaji: FunctionalKeys.NOT_FOUND,
            # XK.XK_Hiragana: FunctionalKeys.NOT_FOUND,
            # XK.XK_Katakana: FunctionalKeys.NOT_FOUND,
            # XK.XK_Hiragana_Katakana: FunctionalKeys.NOT_FOUND,
            # XK.XK_Zenkaku: FunctionalKeys.NOT_FOUND,
            # XK.XK_Hankaku: FunctionalKeys.NOT_FOUND,
            # XK.XK_Zenkaku_Hankaku: FunctionalKeys.NOT_FOUND,
            # XK.XK_Touroku: FunctionalKeys.NOT_FOUND,
            # XK.XK_Massyo: FunctionalKeys.NOT_FOUND,
            # XK.XK_Kana_Lock: FunctionalKeys.NOT_FOUND,
            # XK.XK_Kana_Shift: FunctionalKeys.NOT_FOUND,
            # XK.XK_Eisu_Shift: FunctionalKeys.NOT_FOUND,
            # XK.XK_Eisu_toggle: FunctionalKeys.NOT_FOUND,
            # XK.XK_SingleCandidate: FunctionalKeys.NOT_FOUND,
            # XK.XK_Zen_Koho: FunctionalKeys.NOT_FOUND,
            # XK.XK_PreviousCandidate: FunctionalKeys.NOT_FOUND,
            XK.XK_Home: FunctionalKeys.HOME,
            XK.XK_Left: FunctionalKeys.LEFT,
            XK.XK_Up: FunctionalKeys.UP,
            XK.XK_Right: FunctionalKeys.RIGHT,
            XK.XK_Down: FunctionalKeys.DOWN,
            XK.XK_Page_Up: FunctionalKeys.PAGE_UP,
            XK.XK_Page_Down: FunctionalKeys.PAGE_DOWN,
            XK.XK_End: FunctionalKeys.END,
            XK.XK_Begin: FunctionalKeys.KP_BEGIN,
            # XK.XK_Select: FunctionalKeys.NOT_FOUND,
            XK.XK_Print: FunctionalKeys.PRINT_SCREEN,
            # XK.XK_Execute: FunctionalKeys.NOT_FOUND,
            XK.XK_Insert: FunctionalKeys.INSERT,
            # XK.XK_Undo: FunctionalKeys.NOT_FOUND,
            # XK.XK_Redo: FunctionalKeys.NOT_FOUND,
            XK.XK_Menu: FunctionalKeys.MENU,
            # XK.XK_Find: FunctionalKeys.NOT_FOUND,
            # XK.XK_Cancel: FunctionalKeys.NOT_FOUND,
            # XK.XK_Help: FunctionalKeys.NOT_FOUND,
            # XK.XK_Break: FunctionalKeys.NOT_FOUND,
            # XK.XK_Mode_switch: FunctionalKeys.NOT_FOUND,
            XK.XK_Num_Lock: FunctionalKeys.NUM_LOCK,
            # XK.XK_KP_Space: FunctionalKeys.NOT_FOUND,
            # XK.XK_KP_Tab: FunctionalKeys.NOT_FOUND,
            XK.XK_KP_Enter: FunctionalKeys.KP_ENTER,
            # XK.XK_KP_F1: FunctionalKeys.NOT_FOUND,
            # XK.XK_KP_F2: FunctionalKeys.NOT_FOUND,
            # XK.XK_KP_F3: FunctionalKeys.NOT_FOUND,
            # XK.XK_KP_F4: FunctionalKeys.NOT_FOUND,
            XK.XK_KP_Home: FunctionalKeys.KP_HOME,
            XK.XK_KP_Left: FunctionalKeys.KP_LEFT,
            XK.XK_KP_Up: FunctionalKeys.KP_UP,
            XK.XK_KP_Right: FunctionalKeys.KP_RIGHT,
            XK.XK_KP_Down: FunctionalKeys.KP_DOWN,
            # XK.XK_KP_Prior: FunctionalKeys.NOT_FOUND,
            XK.XK_KP_Page_Down: FunctionalKeys.KP_PAGE_DOWN,
            XK.XK_KP_End: FunctionalKeys.KP_END,
            XK.XK_KP_Begin: FunctionalKeys.KP_BEGIN,
            XK.XK_KP_Insert: FunctionalKeys.KP_INSERT,
            XK.XK_KP_Delete: FunctionalKeys.KP_DELETE,
            XK.XK_KP_Multiply: FunctionalKeys.KP_MULTIPLY,
            XK.XK_KP_Add: FunctionalKeys.KP_ADD,
            XK.XK_KP_Separator: FunctionalKeys.KP_SEPARATOR,
            XK.XK_KP_Subtract: FunctionalKeys.KP_SUBTRACT,
            XK.XK_KP_Decimal: FunctionalKeys.KP_DECIMAL,
            XK.XK_KP_Divide: FunctionalKeys.KP_DIVIDE,
            XK.XK_KP_0: FunctionalKeys.KP_0,
            XK.XK_KP_1: FunctionalKeys.KP_1,
            XK.XK_KP_2: FunctionalKeys.KP_2,
            XK.XK_KP_3: FunctionalKeys.KP_3,
            XK.XK_KP_4: FunctionalKeys.KP_4,
            XK.XK_KP_5: FunctionalKeys.KP_5,
            XK.XK_KP_6: FunctionalKeys.KP_6,
            XK.XK_KP_7: FunctionalKeys.KP_7,
            XK.XK_KP_8: FunctionalKeys.KP_8,
            XK.XK_KP_9: FunctionalKeys.KP_9,
            XK.XK_KP_Equal: FunctionalKeys.KP_EQUAL,
            XK.XK_F1: FunctionalKeys.F1,
            XK.XK_F2: FunctionalKeys.F2,
            XK.XK_F3: FunctionalKeys.F3,
            XK.XK_F4: FunctionalKeys.F4,
            XK.XK_F5: FunctionalKeys.F5,
            XK.XK_F6: FunctionalKeys.F6,
            XK.XK_F7: FunctionalKeys.F7,
            XK.XK_F8: FunctionalKeys.F8,
            XK.XK_F9: FunctionalKeys.F9,
            XK.XK_F10: FunctionalKeys.F10,
            XK.XK_F11: FunctionalKeys.F11,
            XK.XK_F12: FunctionalKeys.F12,
            XK.XK_F13: FunctionalKeys.F13,
            XK.XK_F14: FunctionalKeys.F14,
            XK.XK_F15: FunctionalKeys.F15,
            XK.XK_F16: FunctionalKeys.F16,
            XK.XK_F17: FunctionalKeys.F17,
            XK.XK_F18: FunctionalKeys.F18,
            XK.XK_F19: FunctionalKeys.F19,
            XK.XK_F20: FunctionalKeys.F20,
            XK.XK_F21: FunctionalKeys.F21,
            XK.XK_F22: FunctionalKeys.F22,
            XK.XK_F23: FunctionalKeys.F23,
            XK.XK_F24: FunctionalKeys.F24,
            XK.XK_F25: FunctionalKeys.F25,
            XK.XK_F26: FunctionalKeys.F26,
            XK.XK_F27: FunctionalKeys.F27,
            XK.XK_F28: FunctionalKeys.F28,
            XK.XK_F29: FunctionalKeys.F29,
            XK.XK_F30: FunctionalKeys.F30,
            XK.XK_F31: FunctionalKeys.F31,
            XK.XK_F32: FunctionalKeys.F32,
            XK.XK_F33: FunctionalKeys.F33,
            XK.XK_F34: FunctionalKeys.F34,
            XK.XK_F35: FunctionalKeys.F35,
            XK.XK_Shift_L: FunctionalKeys.LEFT_SHIFT,
            XK.XK_Shift_R: FunctionalKeys.RIGHT_SHIFT,
            XK.XK_Control_L: FunctionalKeys.LEFT_CONTROL,
            XK.XK_Control_R: FunctionalKeys.RIGHT_CONTROL,
            XK.XK_Caps_Lock: FunctionalKeys.CAPS_LOCK,
            # XK.XK_Shift_Lock: FunctionalKeys.NOT_FOUND,
            XK.XK_Meta_L: FunctionalKeys.LEFT_META,
            XK.XK_Meta_R: FunctionalKeys.RIGHT_META,
            XK.XK_Alt_L: FunctionalKeys.LEFT_ALT,
            XK.XK_Alt_R: FunctionalKeys.RIGHT_ALT,
            XK.XK_Super_L: FunctionalKeys.LEFT_SUPER,
            XK.XK_Super_R: FunctionalKeys.RIGHT_SUPER,
            XK.XK_Hyper_L: FunctionalKeys.LEFT_HYPER,
            XK.XK_Hyper_R: FunctionalKeys.RIGHT_HYPER,
            XK.XK_Delete: FunctionalKeys.DELETE,
        }
    )


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


class LatinKeys(Enum):
    SPACE = " "
    EXCLAM = "!"
    QUOTEDBL = '"'
    NUMBERSIGN = "#"
    DOLLAR = "$"
    PERCENT = "%"
    AMPERSAND = "&"
    QUOTERIGHT = "'"
    PARENLEFT = "("
    PARENRIGHT = ")"
    ASTERISK = "*"
    PLUS = "+"
    COMMA = ","
    MINUS = "-"
    PERIOD = "."
    SLASH = "/"
    DIGIT_0 = "0"
    DIGIT_1 = "1"
    DIGIT_2 = "2"
    DIGIT_3 = "3"
    DIGIT_4 = "4"
    DIGIT_5 = "5"
    DIGIT_6 = "6"
    DIGIT_7 = "7"
    DIGIT_8 = "8"
    DIGIT_9 = "9"
    COLON = ":"
    SEMICOLON = ";"
    LESS = "<"
    EQUAL = "="
    GREATER = ">"
    QUESTION = "?"
    AT = "@"
    CAPITAL_A = "A"
    CAPITAL_B = "B"
    CAPITAL_C = "C"
    CAPITAL_D = "D"
    CAPITAL_E = "E"
    CAPITAL_F = "F"
    CAPITAL_G = "G"
    CAPITAL_H = "H"
    CAPITAL_I = "I"
    CAPITAL_J = "J"
    CAPITAL_K = "K"
    CAPITAL_L = "L"
    CAPITAL_M = "M"
    CAPITAL_N = "N"
    CAPITAL_O = "O"
    CAPITAL_P = "P"
    CAPITAL_Q = "Q"
    CAPITAL_R = "R"
    CAPITAL_S = "S"
    CAPITAL_T = "T"
    CAPITAL_U = "U"
    CAPITAL_V = "V"
    CAPITAL_W = "W"
    CAPITAL_X = "X"
    CAPITAL_Y = "Y"
    CAPITAL_Z = "Z"
    BRACKETLEFT = "["
    BACKSLASH = "\\"
    BRACKETRIGHT = "]"
    ASCIICIRCUM = "^"
    UNDERSCORE = "_"
    QUOTELEFT = "`"
    A = "a"
    B = "b"
    C = "c"
    D = "d"
    E = "e"
    F = "f"
    G = "g"
    H = "h"
    I = "i"  # noqa: E741
    J = "j"
    K = "k"
    L = "l"
    M = "m"
    N = "n"
    O = "o"  # noqa: E741
    P = "p"
    Q = "q"
    R = "r"
    S = "s"
    T = "t"
    U = "u"
    V = "v"
    W = "w"
    X = "x"
    Y = "y"
    Z = "z"
    BRACELEFT = "{"
    BAR = "|"
    BRACERIGHT = "}"
    ASCIITILDE = "~"
    NOBREAKSPACE = "\xa0"
    EXCLAMDOWN = "¡"
    CENT = "¢"
    STERLING = "£"
    CURRENCY = "¤"
    YEN = "¥"
    BROKENBAR = "¦"
    SECTION = "§"
    DIAERESIS = "¨"
    COPYRIGHT = "©"
    ORDFEMININE = "ª"
    GUILLEMOTLEFT = "«"
    NOTSIGN = "¬"
    HYPHEN = "\xad"
    REGISTERED = "®"
    MACRON = "¯"
    DEGREE = "°"
    PLUSMINUS = "±"
    TWOSUPERIOR = "²"
    THREESUPERIOR = "³"
    ACUTE = "´"
    MU = "µ"
    PARAGRAPH = "¶"
    PERIODCENTERED = "·"
    CEDILLA = "¸"
    ONESUPERIOR = "¹"
    MASCULINE = "º"
    GUILLEMOTRIGHT = "»"
    ONEQUARTER = "¼"
    ONEHALF = "½"
    THREEQUARTERS = "¾"
    QUESTIONDOWN = "¿"
    CAPITAL_A_GRAVE = "À"
    CAPITAL_A_ACUTE = "Á"
    CAPITAL_A_CIRCUMFLEX = "Â"
    CAPITAL_A_TILDE = "Ã"
    CAPITAL_A_DIAERESIS = "Ä"
    CAPITAL_A_RING = "Å"
    CAPITAL_A_E = "Æ"
    CAPITAL_C_CEDILLA = "Ç"
    CAPITAL_E_GRAVE = "È"
    CAPITAL_E_ACUTE = "É"
    CAPITAL_E_CIRCUMFLEX = "Ê"
    CAPITAL_E_DIAERESIS = "Ë"
    CAPITAL_I_GRAVE = "Ì"
    CAPITAL_I_ACUTE = "Í"
    CAPITAL_I_CIRCUMFLEX = "Î"
    CAPITAL_I_DIAERESIS = "Ï"
    CAPITAL_E_TH = "Ð"
    CAPITAL_N_TILDE = "Ñ"
    CAPITAL_O_GRAVE = "Ò"
    CAPITAL_O_ACUTE = "Ó"
    CAPITAL_O_CIRCUMFLEX = "Ô"
    CAPITAL_O_TILDE = "Õ"
    CAPITAL_O_DIAERESIS = "Ö"
    MULTIPLY = "×"
    CAPITAL_O_OBLIQUE = "Ø"
    CAPITAL_U_GRAVE = "Ù"
    CAPITAL_U_ACUTE = "Ú"
    CAPITAL_U_CIRCUMFLEX = "Û"
    CAPITAL_U_DIAERESIS = "Ü"
    CAPITAL_Y_ACUTE = "Ý"
    CAPITAL_T_HORN = "Þ"
    SSHARP = "ß"
    A_GRAVE = "à"
    A_ACUTE = "á"
    A_CIRCUMFLEX = "â"
    A_TILDE = "ã"
    A_DIAERESIS = "ä"
    A_RING = "å"
    A_E = "æ"
    C_CEDILLA = "ç"
    E_GRAVE = "è"
    E_ACUTE = "é"
    E_CIRCUMFLEX = "ê"
    E_DIAERESIS = "ë"
    I_GRAVE = "ì"
    I_ACUTE = "í"
    I_CIRCUMFLEX = "î"
    I_DIAERESIS = "ï"
    E_TH = "ð"
    N_TILDE = "ñ"
    O_GRAVE = "ò"
    O_ACUTE = "ó"
    O_CIRCUMFLEX = "ô"
    O_TILDE = "õ"
    O_DIAERESIS = "ö"
    DIVISION = "÷"
    OSLASH = "ø"
    U_GRAVE = "ù"
    U_ACUTE = "ú"
    U_CIRCUMFLEX = "û"
    U_DIAERESIS = "ü"
    Y_ACUTE = "ý"
    T_HORN = "þ"
    Y_DIAERESIS = "ÿ"

    @classmethod
    def from_latin(cls, code: int | str) -> LatinKeys | None:
        try:
            as_str = code if isinstance(code, str) else chr(code)
            return cls(as_str)
        except ValueError:
            return None


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

    @classmethod
    def from_xlib_keysym(cls, keysym: int) -> FunctionalKeys | None:
        if not XLIB_SYMKEY_TO_FUNCTIONAL_KEY_MAPPING:
            initialize_xlib_symkey_to_functional_key_mapping()
        return XLIB_SYMKEY_TO_FUNCTIONAL_KEY_MAPPING.get(keysym)

    @classmethod
    def from_pynput_key(cls, key: pynput.keyboard.Key) -> Keys | None:
        if not PYNPUT_KEY_TO_FUNCTIONAL_KEY_MAPPING:
            initialize_pynput_key_to_functional_key_mapping()
        return PYNPUT_KEY_TO_FUNCTIONAL_KEY_MAPPING.get(key)


Keys = LatinKeys | FunctionalKeys


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
