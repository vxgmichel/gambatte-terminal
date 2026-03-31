from __future__ import annotations

import os
import sys
import time
from contextlib import contextmanager
from typing import Callable, Iterator

from blessed import Terminal

from .dom_codes import DomCode
from .console import Console, InputGetter
from .blessed_keyboard_input import KeyboardState, blessed_key_pressed_context
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


class GameInputGetter:
    """Callable that translates raw key state into console inputs."""

    def __init__(
        self,
        console: Console,
        get_pressed: Callable[[], set[DomCode] | KeyboardState],
    ) -> None:
        self._get_pressed = get_pressed
        self._current_pressed: set[DomCode] = set()
        self._input_mapping = get_input_mapping(console)
        self._event_mapping = get_event_mapping(console)
        self._console = console
        self.cpr_state = KeyboardState()

    def __call__(self) -> set[Console.Input]:
        result = self._get_pressed()
        if isinstance(result, KeyboardState):
            self.cpr_state.cpr_received = result.cpr_received
            self.cpr_state.keystrokes = result.keystrokes
            new_pressed = set(result.pressed)
        else:
            self.cpr_state.cpr_received = False
            new_pressed = set(result)
        old_pressed, self._current_pressed = self._current_pressed, new_pressed
        for event in map(self._event_mapping.get, new_pressed - old_pressed):
            if event is None:
                continue
            self._console.handle_event(event)
        return {
            self._input_mapping[keysym]
            for keysym in self._current_pressed
            if keysym in self._input_mapping
        }


def make_get_input(
    console: Console,
    get_pressed: Callable[[], set[DomCode] | KeyboardState],
) -> GameInputGetter:
    return GameInputGetter(console, get_pressed)


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
    console: Console, term: Terminal
) -> Iterator[InputGetter]:
    with blessed_key_pressed_context(term) as get_pressed:
        yield make_get_input(console, get_pressed)


@contextmanager
def console_input_from_x11_keyboard_context(
    console: Console, display: str | None = None
) -> Iterator[InputGetter]:
    with x11_key_pressed_context(display) as get_pressed:
        yield make_get_input(console, get_pressed)


@contextmanager
def console_input_from_pynput_keyboard_context(
    console: Console,
) -> Iterator[InputGetter]:
    with pynput_key_pressed_context() as get_pressed:
        yield make_get_input(console, get_pressed)


@contextmanager
def console_input_from_keyboard_context(
    console: Console,
    term: Terminal,
    display: str | None = None,
    xdg_session_type: str | None = None,
) -> Iterator[InputGetter]:
    if is_kitty_keyboard_protocol_supported(term):
        with console_input_from_keyboard_protocol_context(console, term) as get_input:
            yield get_input
    elif sys.platform == "linux":
        if xdg_session_type is None:
            xdg_session_type = os.environ.get("XDG_SESSION_TYPE", "")
        if xdg_session_type != "x11":
            raise RuntimeError(MESSAGE_SUGGESTING_KITTY_SUPPORT)
        with console_input_from_x11_keyboard_context(console, display) as get_input:
            yield get_input
    else:
        with console_input_from_pynput_keyboard_context(console) as get_input:
            yield get_input


@contextmanager
def key_pressed_context(
    term: Terminal,
    display: str | None = None,
    xdg_session_type: str | None = None,
) -> Iterator[tuple[str, Callable[[], set[DomCode] | KeyboardState]]]:
    if is_kitty_keyboard_protocol_supported(term):
        with blessed_key_pressed_context(term) as get_pressed:
            yield ("blessed", get_pressed)
    elif sys.platform == "linux":
        if xdg_session_type is None:
            xdg_session_type = os.environ.get("XDG_SESSION_TYPE", "")
        if xdg_session_type != "x11":
            raise RuntimeError(MESSAGE_SUGGESTING_KITTY_SUPPORT)
        with x11_key_pressed_context(display) as get_pressed:
            yield ("x11", get_pressed)
    else:
        with pynput_key_pressed_context() as get_pressed:
            yield ("pynput", get_pressed)


def main() -> None:
    term = Terminal()
    with term.raw():
        try:
            term.stream.write(term.hide_cursor)
            term.stream.flush()
            with key_pressed_context(term) as (source, get_pressed):
                print(f"Using keyboard input source: {source}")
                while True:
                    # Get codes
                    result = get_pressed()
                    if isinstance(result, KeyboardState):
                        pressed = result.pressed
                        keys = result.keystrokes
                    else:
                        pressed = result
                        keys = list(iter(lambda: term.inkey(timeout=0), ""))
                    # Check for ctrl+c or ctrl+d
                    for key in keys:
                        if key == "\x03" or key.key_name == "KEY_CTRL_C":
                            raise KeyboardInterrupt
                        if key == "\x04" or key.key_name == "KEY_CTRL_D":
                            raise EOFError
                    codes = " ".join(x.value for x in pressed)
                    # Print pressed key codes
                    term.stream.write(f"\r{codes}{term.clear_eol}")
                    # Clear line and hide cursor
                    term.stream.flush()
                    # Tick
                    time.sleep(1 / 30)
        except (KeyboardInterrupt, EOFError):
            term.stream.write(f"\r{term.clear_eol}")
        except RuntimeError as error:
            exit(str(error))
        finally:
            term.stream.write(term.normal_cursor)
            term.stream.flush()


if __name__ == "__main__":
    main()
