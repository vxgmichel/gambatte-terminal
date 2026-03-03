from __future__ import annotations

import sys
import time
from contextlib import contextmanager
from typing import Callable, Iterator
from prompt_toolkit.application import create_app_session, AppSession

from .console import Console, InputGetter
from .keys import (
    FunctionalKeys,
    LatinKeys,
    Keys,
)
from .ansi_escape_code import (
    detect_keyboard_protocol_support_parser,
    run_parser_in_app_session,
)

from .pynput_keyboard_input import pynput_key_pressed_context
from .x11_keyboard_input import x11_key_pressed_context
from .keyboard_protocol_input import keyboard_protocol_key_pressed_context


def get_input_mapping(console: Console) -> dict[Keys, Console.Input]:
    return {
        # Directions
        FunctionalKeys.UP: console.Input.UP,
        FunctionalKeys.DOWN: console.Input.DOWN,
        FunctionalKeys.LEFT: console.Input.LEFT,
        FunctionalKeys.RIGHT: console.Input.RIGHT,
        # A button
        LatinKeys.F: console.Input.A,
        LatinKeys.V: console.Input.A,
        LatinKeys.SPACE: console.Input.A,
        # B button
        LatinKeys.D: console.Input.B,
        LatinKeys.C: console.Input.B,
        FunctionalKeys.LEFT_ALT: console.Input.B,
        FunctionalKeys.RIGHT_ALT: console.Input.B,
        # Start button
        FunctionalKeys.ENTER: console.Input.START,
        FunctionalKeys.RIGHT_CONTROL: console.Input.START,
        # Select button
        FunctionalKeys.RIGHT_SHIFT: console.Input.SELECT,
        FunctionalKeys.BACKSPACE: console.Input.SELECT,
    }


def get_event_mapping(console: Console) -> dict[Keys, Console.Event]:
    return {
        LatinKeys.DIGIT_0: console.Event.SELECT_STATE_0,
        LatinKeys.DIGIT_1: console.Event.SELECT_STATE_1,
        LatinKeys.DIGIT_2: console.Event.SELECT_STATE_2,
        LatinKeys.DIGIT_3: console.Event.SELECT_STATE_3,
        LatinKeys.DIGIT_4: console.Event.SELECT_STATE_4,
        LatinKeys.DIGIT_5: console.Event.SELECT_STATE_5,
        LatinKeys.DIGIT_6: console.Event.SELECT_STATE_6,
        LatinKeys.DIGIT_7: console.Event.SELECT_STATE_7,
        LatinKeys.DIGIT_8: console.Event.SELECT_STATE_8,
        LatinKeys.DIGIT_9: console.Event.SELECT_STATE_9,
        LatinKeys.L: console.Event.LOAD_STATE,
        LatinKeys.K: console.Event.SAVE_STATE,
    }


def make_get_input(
    console: Console,
    get_pressed: Callable[[], set[Keys]],
) -> InputGetter:
    current_pressed: set[Keys] = set()
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
    console: Console, app_session: AppSession, display: str | None = None
) -> Iterator[InputGetter]:
    if run_parser_in_app_session(
        app_session, detect_keyboard_protocol_support_parser
    ).is_supported():
        with console_input_from_keyboard_protocol_context(
            console, app_session
        ) as get_input:
            yield get_input
    elif sys.platform == "linux":
        with console_input_from_x11_keyboard_context(console, display) as get_input:
            yield get_input
    else:
        with console_input_from_pynput_keyboard_context(console) as get_input:
            yield get_input


@contextmanager
def key_pressed_context(
    app_session: AppSession,
    display: str | None = None,
) -> Iterator[Callable[[], set[Keys]]]:
    if run_parser_in_app_session(
        app_session, detect_keyboard_protocol_support_parser
    ).is_supported():
        with keyboard_protocol_key_pressed_context(app_session) as get_pressed:
            yield get_pressed
    elif sys.platform == "linux":
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
                        codes = (x.name for x in get_pressed())
                        # Print pressed key codes
                        print(*codes, flush=True, end="")
                        # Tick
                        time.sleep(1 / 30)
                        # Clear line and hide cursor
                        app_session.output.write_raw("\r")
                        app_session.output.erase_down()
                        # Flush output
                        app_session.output.flush()
            except (KeyboardInterrupt, EOFError):
                pass
            finally:
                app_session.output.show_cursor()
                app_session.output.flush()
                print()


if __name__ == "__main__":
    main()
