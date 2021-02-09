import sys
import time
import logging
from enum import IntEnum
from contextlib import contextmanager, closing
from prompt_toolkit.application import create_app_session


class GBInput(IntEnum):
    A = 0x01
    B = 0x02
    SELECT = 0x04
    START = 0x08
    RIGHT = 0x10
    LEFT = 0x20
    UP = 0x40
    DOWN = 0x80


def get_xlib_mapping():
    from Xlib import XK

    return {
        # Directions
        XK.XK_Up: GBInput.UP,
        XK.XK_Down: GBInput.DOWN,
        XK.XK_Left: GBInput.LEFT,
        XK.XK_Right: GBInput.RIGHT,
        # A button
        XK.XK_f: GBInput.A,
        XK.XK_v: GBInput.A,
        XK.XK_space: GBInput.A,
        # B button
        XK.XK_d: GBInput.B,
        XK.XK_c: GBInput.B,
        XK.XK_Alt_L: GBInput.B,
        XK.XK_Alt_R: GBInput.B,
        # Start button
        XK.XK_Return: GBInput.START,
        XK.XK_Control_R: GBInput.START,
        # Select button
        XK.XK_Shift_R: GBInput.SELECT,
        XK.XK_Delete: GBInput.SELECT,
    }


def get_keyboard_mapping():
    return {
        # Directions
        "up": GBInput.UP,
        "down": GBInput.DOWN,
        "left": GBInput.LEFT,
        "right": GBInput.RIGHT,
        # A button
        "f": GBInput.A,
        "v": GBInput.A,
        "space": GBInput.A,
        # B button
        "d": GBInput.B,
        "c": GBInput.B,
        "alt": GBInput.B,
        "alt_r": GBInput.B,
        # Start button
        "enter": GBInput.START,
        "ctrl_r": GBInput.START,
        # Select button
        "shift_r": GBInput.SELECT,
        "delete": GBInput.SELECT,
    }


@contextmanager
def xlib_key_pressed_context(display=None):
    from Xlib.ext import xinput
    from Xlib.display import Display

    with closing(Display(display)) as xdisplay:
        extension_info = xdisplay.query_extension("XInputExtension")
        xinput_major = extension_info.major_opcode
        # Set of currently pressed keys
        pressed = set()
        # Save current focus, as it is likely to be the terminal window
        term_window = xdisplay.get_input_focus().focus
        # It is possible the select events directly on the terminal window,
        # but for some reasons, the events won't be propagated for some terminals like kitty.
        # Instead, we select the events on the root windows and then perform some filtering.
        xdisplay.screen().root.xinput_select_events(
            [(xinput.AllDevices, xinput.KeyPressMask | xinput.KeyReleaseMask)]
        )

        def get_pressed():
            # Loop over pending events
            while xdisplay.pending_events():
                event = xdisplay.next_event()
                assert event.extension == xinput_major, event
                # Check whether the focus is currently on the terminal window
                if xdisplay.get_input_focus().focus != term_window:
                    pressed.clear()
                    continue
                # Extract information
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
def pynput_key_pressed_context(display=None):
    from pynput import keyboard

    def on_press(key):
        try:
            value = key.char
        except AttributeError:
            value = key.name
        try:
            value = value.lower()
        except AttributeError:
            return
        pressed.add(value)

    def on_release(key):
        try:
            value = key.char
        except AttributeError:
            value = key.name
        try:
            value = value.lower()
        except AttributeError:
            return
        pressed.discard(value)

    pressed = set()
    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    try:
        listener.start()
        yield lambda: pressed
    finally:
        pressed.clear()
        listener.stop()


@contextmanager
def gb_input_from_keyboard_context(display=None):
    if sys.platform == "linux":
        mapping = get_xlib_mapping()
        key_pressed_context = xlib_key_pressed_context
    else:
        mapping = get_keyboard_mapping()
        key_pressed_context = pynput_key_pressed_context

    def get_gb_input():
        value = 0
        for keysym in get_pressed():
            value |= mapping.get(keysym, 0)
        return value

    with key_pressed_context(display=display) as get_pressed:
        yield get_gb_input


def main():
    if sys.platform == "linux":
        from Xlib import XK

        mapping = get_xlib_mapping()
        key_pressed_context = xlib_key_pressed_context
        reverse_lookup = {
            v: k[3:] for k, v in XK.__dict__.items() if k.startswith("XK_")
        }
        mapping = reverse_lookup.get
    else:
        mapping = get_keyboard_mapping()
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
