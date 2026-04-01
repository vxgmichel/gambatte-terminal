from __future__ import annotations

import os
import sys
import time
from functools import partial
from contextlib import contextmanager
from typing import Callable, Iterator

from blessed import Terminal
from blessed.keyboard import Keystroke

from .console import Console
from .dom_codes import DomCode
from .input_getter import BaseInputGetter, pop_keystrokes_from_terminal
from .blessed_keyboard_input import blessed_key_pressed_context
from .pynput_keyboard_input import pynput_key_pressed_context
from .x11_keyboard_input import x11_key_pressed_context

MESSAGE_SUGGESTING_KITTY_SUPPORT = """\
Your terminal does not support the kitty keyboard protocol
Here is a list of terminals known to support this protocol:

- kitty https://sw.kovidgoyal.net/kitty/
- alacritty https://alacritty.org/
- ghostty https://ghostty.org/
- foot https://codeberg.org/dnkl/foot
- iTerm2 https://iterm2.com/
- Rio https://rioterm.com/
- Windows Terminal.exe https://github.com/microsoft/terminal
- WezTerm (enable by configuration) https://wezfurlong.org/wezterm/
- TuiOS (multiplexer) https://terminaltrove.com/tuios/
- libvterm (vim's :terminal, emacs-libvterm) https://www.leonerd.org.uk/code/libvterm/

More information here: (https://sw.kovidgoyal.net/kitty/keyboard-protocol)
"""


def get_input_mapping(console: Console) -> dict[DomCode, Console.Input]:
    return {
        # Generic start/select
        DomCode.ENTER: console.Input.START,
        DomCode.SHIFT_RIGHT: console.Input.SELECT,
        # Arrow controls
        DomCode.ARROW_UP: console.Input.UP,
        DomCode.ARROW_DOWN: console.Input.DOWN,
        DomCode.ARROW_LEFT: console.Input.LEFT,
        DomCode.ARROW_RIGHT: console.Input.RIGHT,
        DomCode.NUMPAD8: console.Input.UP,
        DomCode.NUMPAD2: console.Input.DOWN,
        DomCode.NUMPAD4: console.Input.LEFT,
        DomCode.NUMPAD6: console.Input.RIGHT,
        DomCode.US_X: console.Input.A,
        DomCode.US_Z: console.Input.B,
        # WASD controls
        DomCode.US_W: console.Input.UP,
        DomCode.US_S: console.Input.DOWN,
        DomCode.US_A: console.Input.LEFT,
        DomCode.US_D: console.Input.RIGHT,
        DomCode.US_K: console.Input.A,
        DomCode.US_J: console.Input.B,
    }


def get_event_mapping(console: Console) -> dict[DomCode, Console.Event]:
    return {
        DomCode.DIGIT0: console.Event.SELECT_STATE_0,
        DomCode.DIGIT1: console.Event.SELECT_STATE_1,
        DomCode.DIGIT2: console.Event.SELECT_STATE_2,
        DomCode.DIGIT3: console.Event.SELECT_STATE_3,
        DomCode.DIGIT4: console.Event.SELECT_STATE_4,
        DomCode.DIGIT5: console.Event.SELECT_STATE_5,
        DomCode.DIGIT6: console.Event.SELECT_STATE_6,
        DomCode.DIGIT7: console.Event.SELECT_STATE_7,
        DomCode.DIGIT8: console.Event.SELECT_STATE_8,
        DomCode.DIGIT9: console.Event.SELECT_STATE_9,
        DomCode.BRACKET_LEFT: console.Event.SAVE_STATE,
        DomCode.BRACKET_RIGHT: console.Event.LOAD_STATE,
    }


class KeyboardInputGetter(BaseInputGetter):
    def __init__(
        self,
        console: Console,
        terminal: Terminal,
        get_pressed: Callable[[], set[DomCode]],
    ) -> None:
        super().__init__(console, terminal)
        self._get_pressed = get_pressed
        self._current_pressed: set[DomCode] = set()
        self._input_mapping = get_input_mapping(console)
        self._event_mapping = get_event_mapping(console)

    def get_pressed(self) -> set[Console.Input]:
        new_pressed = self._get_pressed()
        old_pressed, self._current_pressed = self._current_pressed, new_pressed
        for event in map(self._event_mapping.get, new_pressed - old_pressed):
            if event is None:
                continue
            self.console.handle_event(event)
        return {
            self._input_mapping[keysym]
            for keysym in self._current_pressed
            if keysym in self._input_mapping
        }


class X11KeyboardInputGetter(KeyboardInputGetter):
    pass


class PynputKeyboardInputGetter(KeyboardInputGetter):
    pass


class KittyKeyboardInputGetter(KeyboardInputGetter):
    def __init__(
        self,
        console: Console,
        terminal: Terminal,
        get_pressed: Callable[[], set[DomCode]],
        pop_keystrokes: Callable[[], list[Keystroke]],
    ) -> None:
        super().__init__(console, terminal, get_pressed)
        self._pop_keystrokes = pop_keystrokes

    def pop_keystrokes(self) -> list[Keystroke]:
        if self._pop_keystrokes is not None:
            return self._pop_keystrokes()
        return super().pop_keystrokes()


def is_kitty_keyboard_protocol_supported(
    term: Terminal, timeout: float | None = None
) -> bool:
    """Check if the terminal supports the kitty keyboard protocol.

    Some terminals (e.g. last release of Contour) responds to the kitty keyboard query but ignore
    the flags we set, so we verify that report_events is actually enabled after requesting it.
    """
    state = term.get_kitty_keyboard_state(timeout=timeout)
    if state is None:
        return False
    with term.enable_kitty_keyboard(report_events=True, timeout=timeout):
        active = term.get_kitty_keyboard_state(timeout=timeout)
    return active is not None and active.report_events


@contextmanager
def console_input_from_keyboard_protocol_context(
    console: Console, terminal: Terminal
) -> Iterator[KeyboardInputGetter]:
    with blessed_key_pressed_context(terminal) as (get_pressed, pop_keystrokes):
        yield KittyKeyboardInputGetter(console, terminal, get_pressed, pop_keystrokes)


@contextmanager
def console_input_from_x11_keyboard_context(
    console: Console, terminal: Terminal, display: str | None = None
) -> Iterator[KeyboardInputGetter]:
    with x11_key_pressed_context(display) as get_pressed:
        yield X11KeyboardInputGetter(console, terminal, get_pressed)


@contextmanager
def console_input_from_pynput_keyboard_context(
    console: Console, terminal: Terminal
) -> Iterator[KeyboardInputGetter]:
    with pynput_key_pressed_context() as get_pressed:
        yield PynputKeyboardInputGetter(console, terminal, get_pressed)


@contextmanager
def console_input_from_keyboard_context(
    console: Console,
    terminal: Terminal,
    display: str | None = None,
    xdg_session_type: str | None = None,
) -> Iterator[KeyboardInputGetter]:
    if is_kitty_keyboard_protocol_supported(terminal):
        with console_input_from_keyboard_protocol_context(
            console, terminal
        ) as get_input:
            yield get_input
    elif sys.platform == "linux":
        if xdg_session_type is None:
            xdg_session_type = os.environ.get("XDG_SESSION_TYPE", "")
        if xdg_session_type != "x11":
            raise RuntimeError(MESSAGE_SUGGESTING_KITTY_SUPPORT)
        with console_input_from_x11_keyboard_context(
            console, terminal, display
        ) as get_input:
            yield get_input
    else:
        with console_input_from_pynput_keyboard_context(console, terminal) as get_input:
            yield get_input


# Entry point for testing keyboard input, that prints the currently pressed keys every frame.


@contextmanager
def key_pressed_context(
    terminal: Terminal,
    display: str | None = None,
    xdg_session_type: str | None = None,
) -> Iterator[tuple[str, Callable[[], set[DomCode]], Callable[[], list[Keystroke]]]]:
    """
    This helper is only used for the `keyboard_input.py` entry point, that allows for testing keyboard input.
    """
    if is_kitty_keyboard_protocol_supported(terminal):
        with blessed_key_pressed_context(terminal) as (get_pressed, pop_keystrokes):
            yield ("blessed", get_pressed, pop_keystrokes)
    elif sys.platform == "linux":
        if xdg_session_type is None:
            xdg_session_type = os.environ.get("XDG_SESSION_TYPE", "")
        if xdg_session_type != "x11":
            raise RuntimeError(MESSAGE_SUGGESTING_KITTY_SUPPORT)
        with x11_key_pressed_context(display) as get_pressed:
            yield ("x11", get_pressed, partial(pop_keystrokes_from_terminal, terminal))
    else:
        with pynput_key_pressed_context() as get_pressed:
            yield (
                "pynput",
                get_pressed,
                partial(pop_keystrokes_from_terminal, terminal),
            )


def main() -> None:
    terminal = Terminal()
    with terminal.raw():
        try:
            terminal.stream.write(terminal.hide_cursor)
            terminal.stream.flush()
            with key_pressed_context(terminal) as (source, get_pressed, pop_keystrokes):
                print(f"Using keyboard input source: {source}")
                while True:
                    # Get codes
                    pressed = get_pressed()
                    keys = pop_keystrokes()
                    # Check for ctrl+c or ctrl+d
                    for key in keys:
                        if key == "\x03" or key.key_name == "KEY_CTRL_C":
                            raise KeyboardInterrupt
                        if key == "\x04" or key.key_name == "KEY_CTRL_D":
                            raise EOFError
                    codes = " ".join(x.value for x in pressed)
                    # Print pressed key codes
                    terminal.stream.write(f"\r{codes}{terminal.clear_eol}")
                    # Clear line and hide cursor
                    terminal.stream.flush()
                    # Tick
                    time.sleep(1 / 30)
        except (KeyboardInterrupt, EOFError):
            terminal.stream.write(f"\r{terminal.clear_eol}")
        except RuntimeError as error:
            exit(str(error))
        finally:
            terminal.stream.write(terminal.normal_cursor)
            terminal.stream.flush()


if __name__ == "__main__":
    main()
