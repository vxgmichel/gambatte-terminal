from __future__ import annotations

import os
import sys
import time
from contextlib import contextmanager
from typing import Callable, Iterator
from prompt_toolkit.application import create_app_session, AppSession

from .dom_codes import DomCode
from .console import Console, InputGetter
from .ansi_escape_code import (
    detect_keyboard_protocol_support_parser,
    run_parser_in_app_session,
)

from .pynput_keyboard_input import pynput_key_pressed_context
from .x11_keyboard_input import x11_key_pressed_context
from .keyboard_protocol_input import keyboard_protocol_key_pressed_context


MESSAGE_FOR_WAYLAND_USERS = """\
Your terminal does not support the kitty keyboard protocol
Here is a list of terminals supporting this protocol:
- The alacritty terminal
- The ghostty terminal
- The foot terminal
- The iTerm2 terminal
- The rio terminal
- The WezTerm terminal
- The TuiOS terminal (multiplexer)
More information here: (https://sw.kovidgoyal.net/kitty/keyboard-protocol)\
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
        DomCode.US_Z: console.Input.A,
        DomCode.US_X: console.Input.B,
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


def make_get_input(
    console: Console,
    get_pressed: Callable[[], set[DomCode]],
) -> InputGetter:
    current_pressed: set[DomCode] = set()
    input_mapping = get_input_mapping(console)
    event_mapping = get_event_mapping(console)

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

    return get_input


@contextmanager
def console_input_from_keyboard_protocol_context(
    console: Console, app_session: AppSession
) -> Iterator[InputGetter]:
    with keyboard_protocol_key_pressed_context(app_session) as get_pressed:
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
    app_session: AppSession,
    display: str | None = None,
    xdg_session_type: str | None = None,
) -> Iterator[InputGetter]:
    if run_parser_in_app_session(
        app_session, detect_keyboard_protocol_support_parser
    ).is_supported():
        with console_input_from_keyboard_protocol_context(
            console, app_session
        ) as get_input:
            yield get_input
    elif sys.platform == "linux":
        if xdg_session_type is None:
            xdg_session_type = os.environ.get("XDG_SESSION_TYPE", "")
        if xdg_session_type != "x11":
            raise RuntimeError(MESSAGE_FOR_WAYLAND_USERS)
        with console_input_from_x11_keyboard_context(console, display) as get_input:
            yield get_input
    else:
        with console_input_from_pynput_keyboard_context(console) as get_input:
            yield get_input


@contextmanager
def key_pressed_context(
    app_session: AppSession,
    display: str | None = None,
    xdg_session_type: str | None = None,
) -> Iterator[Callable[[], set[DomCode]]]:
    if run_parser_in_app_session(
        app_session, detect_keyboard_protocol_support_parser
    ).is_supported():
        with keyboard_protocol_key_pressed_context(app_session) as get_pressed:
            yield get_pressed
    elif sys.platform == "linux":
        if xdg_session_type is None:
            xdg_session_type = os.environ.get("XDG_SESSION_TYPE", "")
        if xdg_session_type != "x11":
            raise RuntimeError(MESSAGE_FOR_WAYLAND_USERS)
        with x11_key_pressed_context(display) as get_pressed:
            yield get_pressed
    else:
        with pynput_key_pressed_context() as get_pressed:
            yield get_pressed


def main() -> None:
    with create_app_session() as app_session:
        from prompt_toolkit.application import get_app_session

        assert get_app_session() is app_session
        with app_session.input.raw_mode():
            try:
                app_session.output.hide_cursor()
                with key_pressed_context(app_session) as get_pressed:
                    while True:
                        # Read keys
                        for key in app_session.input.read_keys():
                            if key.key == "c-c":
                                raise KeyboardInterrupt
                            if key.key == "c-d":
                                raise EOFError
                        # Get codes
                        line = " ".join(x.value for x in get_pressed())
                        # Print pressed key codes
                        app_session.output.write_raw(f"\r{line}")
                        app_session.output.erase_down()
                        # Flush output
                        app_session.output.flush()
                        # Tick
                        time.sleep(1 / 30)
            except (KeyboardInterrupt, EOFError):
                pass
            except RuntimeError as error:
                exit(str(error))
            finally:
                app_session.output.show_cursor()
                app_session.output.flush()
                print()


if __name__ == "__main__":
    main()
