from __future__ import annotations

from contextlib import contextmanager, closing
from typing import Callable, Iterator
from .keys import (
    FunctionalKeys,
    LatinKeys,
    Keys,
)

XLIB_SYMKEY_TO_FUNCTIONAL_KEY_MAPPING: dict[int, FunctionalKeys] = {}


def key_from_xlib_keysym(keysym: int) -> Keys | None:
    latin_key = LatinKeys.from_latin(keysym)
    if latin_key is not None:
        return latin_key
    if not XLIB_SYMKEY_TO_FUNCTIONAL_KEY_MAPPING:
        initialize_xlib_symkey_to_functional_key_mapping()
    return XLIB_SYMKEY_TO_FUNCTIONAL_KEY_MAPPING.get(keysym)


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


@contextmanager
def x11_key_pressed_context(
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
                group = event.data.groups.effective_group * 2
                keysym = xdisplay.keycode_to_keysym(keycode, group)
                repeat = event.data.flags & 0x10000
                is_key_pressed = event.evtype == xinput.KeyPress and not repeat
                is_key_released = event.evtype == xinput.KeyRelease

                # Convert into
                key = key_from_xlib_keysym(keysym)
                if key is None:
                    continue

                # Update the `pressed` set accordingly
                if is_key_pressed:
                    pressed.add(key)
                if is_key_released:
                    pressed.discard(key)

            # Return the currently pressed keys
            return pressed

        try:
            yield get_pressed
        finally:
            pressed.clear()
