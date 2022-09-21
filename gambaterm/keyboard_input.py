from __future__ import annotations

import sys
import time
import logging
from contextlib import contextmanager, closing
from typing import Callable, Iterator, TYPE_CHECKING
from prompt_toolkit.application import create_app_session

from .console import Console, InputGetter

if TYPE_CHECKING:
    import pynput  # type: ignore


def get_xlib_input_mapping(console: Console) -> dict[int, Console.Input]:
    from Xlib import XK  # type: ignore

    return {
        # Directions
        XK.XK_Up: console.Input.UP,
        XK.XK_Down: console.Input.DOWN,
        XK.XK_Left: console.Input.LEFT,
        XK.XK_Right: console.Input.RIGHT,
        # A button
        XK.XK_f: console.Input.A,
        XK.XK_v: console.Input.A,
        XK.XK_space: console.Input.A,
        # B button
        XK.XK_d: console.Input.B,
        XK.XK_c: console.Input.B,
        XK.XK_Alt_L: console.Input.B,
        XK.XK_Alt_R: console.Input.B,
        # Start button
        XK.XK_Return: console.Input.START,
        XK.XK_Control_R: console.Input.START,
        # Select button
        XK.XK_Shift_R: console.Input.SELECT,
        XK.XK_Delete: console.Input.SELECT,
    }


def get_xlib_event_mapping(console: Console) -> dict[int, Console.Event]:
    from Xlib import XK  # type: ignore

    return {
        XK.XK_0: console.Event.SELECT_STATE_0,
        XK.XK_1: console.Event.SELECT_STATE_1,
        XK.XK_2: console.Event.SELECT_STATE_2,
        XK.XK_3: console.Event.SELECT_STATE_3,
        XK.XK_4: console.Event.SELECT_STATE_4,
        XK.XK_5: console.Event.SELECT_STATE_5,
        XK.XK_6: console.Event.SELECT_STATE_6,
        XK.XK_7: console.Event.SELECT_STATE_7,
        XK.XK_8: console.Event.SELECT_STATE_8,
        XK.XK_9: console.Event.SELECT_STATE_9,
        XK.XK_l: console.Event.LOAD_STATE,
        XK.XK_k: console.Event.SAVE_STATE,
    }


def get_keyboard_input_mapping(console: Console) -> dict[str, Console.Input]:
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


def get_keyboard_event_mapping(console: Console) -> dict[str, Console.Event]:
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
) -> Iterator[Callable[[], set[int]]]:
    from Xlib.ext import xinput  # type: ignore
    from Xlib.display import Display  # type: ignore

    with closing(Display(display)) as xdisplay:
        extension_info = xdisplay.query_extension("XInputExtension")
        xinput_major = extension_info.major_opcode
        # Set of currently pressed keys and focused flag
        pressed: set[int] = set()
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

        def get_pressed() -> set[int]:
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
                # Prepare info string
                info_string = f"keycode={keycode}, keysym={keysym}, "
                info_string += f"modkeysym={modkeysym}, keystr={keystr}"
                # Update the `pressed` set accordingly
                if is_key_pressed:
                    pressed.add(keysym)
                    logging.info("Key pressed: " + info_string)
                if is_key_released:
                    pressed.discard(keysym)
                    logging.info("Key released: " + info_string)

            # Return the currently pressed keys
            return pressed

        try:
            yield get_pressed
        finally:
            pressed.clear()


@contextmanager
def pynput_key_pressed_context(
    display: str | None = None,
) -> Iterator[Callable[[], set[str]]]:
    from pynput import keyboard  # type: ignore

    def on_press(key: pynput.keyboard.Key) -> None:
        try:
            value = key.char
        except AttributeError:
            value = key.name
        try:
            value = value.lower()
        except AttributeError:
            return
        pressed.add(value)

    def on_release(key: pynput.keyboard.Key) -> None:
        try:
            value = key.char
        except AttributeError:
            value = key.name
        try:
            value = value.lower()
        except AttributeError:
            return
        pressed.discard(value)

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
    console: Console, display: str | None = None
) -> Iterator[InputGetter]:
    if sys.platform == "linux":
        current_pressed: set[int] = set()
        input_mapping = get_xlib_input_mapping(console)
        event_mapping = get_xlib_event_mapping(console)
        key_pressed_context = xlib_key_pressed_context
    else:
        current_pressed: set[str] = set()
        input_mapping = get_keyboard_input_mapping(console)
        event_mapping = get_keyboard_event_mapping(console)
        key_pressed_context = pynput_key_pressed_context

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

    with key_pressed_context(display=display) as get_pressed:
        yield get_input


def main() -> None:
    if sys.platform == "linux":
        from Xlib import XK

        key_pressed_context = xlib_key_pressed_context
        reverse_lookup = {
            v: k[3:] for k, v in XK.__dict__.items() if k.startswith("XK_")
        }
        mapping = reverse_lookup.get
    else:
        key_pressed_context = pynput_key_pressed_context
        mapping = str

    with create_app_session() as session:
        with session.input.raw_mode():
            try:
                session.output.hide_cursor()
                with key_pressed_context() as get_pressed:
                    while True:
                        # Read keys
                        for key in session.input.read_keys():
                            if key.key == "c-c":
                                raise KeyboardInterrupt
                            if key.key == "c-d":
                                raise EOFError
                        # Get codes
                        codes = list(map(mapping, get_pressed()))
                        # Print pressed key codes
                        print(*codes, flush=True, end="")
                        # Tick
                        time.sleep(1 / 30)
                        # Clear line and hide cursor
                        session.output.write_raw("\r")
                        session.output.erase_down()
                        # Flush output
                        session.output.flush()
            except (KeyboardInterrupt, EOFError):
                pass
            finally:
                session.output.show_cursor()
                session.output.flush()
                print()


if __name__ == "__main__":
    main()
