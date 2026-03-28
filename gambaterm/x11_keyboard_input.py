from __future__ import annotations

from contextlib import contextmanager, closing
from typing import Callable, Iterator
from .dom_codes import DomCode


def is_x11_display_functional(display: str | None = None) -> bool:
    from Xlib.display import Display
    from Xlib.xobject.drawable import Window

    try:
        with closing(Display(display)) as xdisplay:
            extension_info = xdisplay.query_extension("XInputExtension")
            if extension_info is None:
                return False
            xinput_major = extension_info.major_opcode
            if xinput_major is None:
                return False
            term_window = xdisplay.get_input_focus().focus
            if not isinstance(term_window, Window):
                return False
            root = xdisplay.screen().root
            if not isinstance(root, Window):
                return False
    except OSError:
        return False
    return True


@contextmanager
def x11_key_pressed_context(
    display: str | None = None,
) -> Iterator[Callable[[], set[DomCode]]]:
    from Xlib.ext import xinput
    from Xlib.display import Display

    with closing(Display(display)) as xdisplay:
        extension_info = xdisplay.query_extension("XInputExtension")
        xinput_major = extension_info is not None and extension_info.major_opcode
        # Set of currently pressed keys and focused flag
        pressed: set[DomCode] = set()
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

        def get_pressed() -> set[DomCode]:
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
                repeat = event.data.flags & 0x10000
                is_key_pressed = event.evtype == xinput.KeyPress and not repeat
                is_key_released = event.evtype == xinput.KeyRelease

                # Convert into DOM code
                key = DomCode.from_xkb_scancode(keycode)
                if key is None:
                    continue

                # Update the `pressed` set accordingly
                if is_key_pressed:
                    pressed.add(key)
                if is_key_released:
                    pressed.discard(key)

            # Check for Ctrl+C / Ctrl+D
            if DomCode.CONTROL_LEFT in pressed or DomCode.CONTROL_RIGHT in pressed:
                if DomCode.US_C in pressed:
                    raise KeyboardInterrupt
                if DomCode.US_D in pressed:
                    raise OSError

            # Return the currently pressed keys
            return pressed

        try:
            yield get_pressed
        finally:
            pressed.clear()
