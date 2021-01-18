import os
import sys
import time
import select
import logging
from enum import IntEnum
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor

if os.name == "nt":
    from prompt_toolkit.input.win32 import raw_mode
else:
    from prompt_toolkit.input.vt100 import raw_mode


class GBInput(IntEnum):
    A = 0x01
    B = 0x02
    SELECT = 0x04
    START = 0x08
    RIGHT = 0x10
    LEFT = 0x20
    UP = 0x40
    DOWN = 0x80


def get_mapping():
    from Xlib import XK

    return {
        XK.XK_Up: GBInput.UP,
        XK.XK_Down: GBInput.DOWN,
        XK.XK_Left: GBInput.LEFT,
        XK.XK_Right: GBInput.RIGHT,
        XK.XK_f: GBInput.A,
        XK.XK_space: GBInput.A,
        XK.XK_d: GBInput.B,
        XK.XK_Alt_L: GBInput.B,
        XK.XK_Return: GBInput.START,
        XK.XK_Control_R: GBInput.START,
        XK.XK_Shift_L: GBInput.SELECT,
        XK.XK_Shift_R: GBInput.SELECT,
    }


@contextmanager
def key_pressed_context(display=None):
    from Xlib.ext import xinput
    from Xlib.display import Display

    def target():
        xdisplay = Display(display)
        try:
            extension_info = xdisplay.query_extension("XInputExtension")
            xinput_major = extension_info.major_opcode
            window = xdisplay.get_input_focus().focus
            if isinstance(window, int):
                window = xdisplay.screen().root
            window.xinput_select_events(
                [
                    (xinput.AllDevices, xinput.KeyPressMask | xinput.KeyReleaseMask),
                ]
            )
            while running:
                # Check running
                if not xdisplay.pending_events():
                    select.select([xdisplay], [], [], 0.1)
                    continue
                event = xdisplay.next_event()
                assert event.extension == xinput_major, event
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
                # Update the `pressed` accordingly
                if is_key_pressed:
                    pressed.add(keysym)
                    logging.info("Key pressed: " + info_string)
                if is_key_released:
                    pressed.discard(keysym)
                    logging.info("Key released: " + info_string)
        finally:
            xdisplay.close()

    with ThreadPoolExecutor() as executor:
        running = True
        pressed = set()
        try:
            executor.submit(target)
            yield lambda: pressed
        finally:
            running = False
            pressed.clear()


@contextmanager
def gb_input_context(display=None):
    mapping = get_mapping()

    def get_gb_input():
        value = 0
        for keysym in get_pressed():
            value |= mapping.get(keysym, 0)
        return value

    with key_pressed_context(display=display) as get_pressed:
        yield get_gb_input


@contextmanager
def cbreak_mode():
    # Open stdin and stdout
    stdin_fd = sys.stdin.fileno()
    stdout_fd = sys.stdout.fileno()
    stdin = os.fdopen(stdin_fd, "rb", buffering=0)
    stdout = os.fdopen(stdout_fd, "wb", buffering=0)
    try:
        with raw_mode(stdin_fd):
            stdout.write(b"\033[?25l")
            yield (stdin, stdout)
    finally:
        stdout.write(b"\033[?25h")


def main():
    from Xlib import XK

    reverse_lookup = {v: k[3:] for k, v in XK.__dict__.items() if k.startswith("XK_")}
    try:
        with cbreak_mode() as (_, stdout):
            with key_pressed_context() as get_pressed:
                while True:
                    # Get codes
                    codes = list(map(reverse_lookup.get, get_pressed()))
                    # Print pressed key codes
                    print(*codes, flush=True, end="")
                    # Tick
                    time.sleep(1 / 30)
                    # Clear line and hide cursor
                    stdout.write(b"\033[2K\r")
    except KeyboardInterrupt:
        print()


if __name__ == "__main__":
    main()
