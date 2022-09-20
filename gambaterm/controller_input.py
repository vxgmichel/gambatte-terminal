from __future__ import annotations

import os
from typing import Callable, ContextManager, Iterator
from contextlib import contextmanager

from .console import Console, InputGetter


def get_controller_mapping(console: Console) -> dict[str, Console.Input]:
    return {
        # Directions
        "A1-": console.Input.UP,
        "H1-": console.Input.UP,
        "A1+": console.Input.DOWN,
        "H1+": console.Input.DOWN,
        "A0-": console.Input.LEFT,
        "H0-": console.Input.LEFT,
        "A0+": console.Input.RIGHT,
        "H0+": console.Input.RIGHT,
        # A button
        "B0": console.Input.A,
        "B3": console.Input.A,
        # B button
        "B1": console.Input.B,
        "B2": console.Input.B,
        # Start button
        "B7": console.Input.START,
        # Select button
        "B6": console.Input.SELECT,
    }


@contextmanager
def pygame_button_pressed_context(
    deadzone: float = 0.4,
) -> Iterator[Callable[[], set[str]]]:
    os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

    try:
        import pygame
    except ImportError:
        raise SystemExit(
            """\
The pygame library is not available, which is required to get controller support.
Please use the following command to install gambaterm with controller support:
  pip3 install gambaterm[controller-support]
"""
        )

    pygame.init()
    pygame.joystick.init()
    joystick = None

    def get_pressed() -> set[str]:
        nonlocal joystick
        pygame.event.get()
        if pygame.joystick.get_count() == 0:
            joystick = None
            return set()
        if joystick is None:
            joystick = pygame.joystick.Joystick(0)
        pressed = {
            f"B{x}" for x in range(joystick.get_numbuttons()) if joystick.get_button(x)
        }
        if joystick.get_numhats() >= 1:
            if joystick.get_hat(0)[0] > 0:
                pressed.add("H0+")
            if joystick.get_hat(0)[0] < 0:
                pressed.add("H0-")
            if joystick.get_hat(0)[1] < 0:
                pressed.add("H1+")
            if joystick.get_hat(0)[1] > 0:
                pressed.add("H1-")
        if joystick.get_numaxes() >= 2:
            if joystick.get_axis(0) > deadzone:
                pressed.add("A0+")
            if joystick.get_axis(0) < -deadzone:
                pressed.add("A0-")
            if joystick.get_axis(1) > deadzone:
                pressed.add("A1+")
            if joystick.get_axis(1) < -deadzone:
                pressed.add("A1-")
        return pressed

    yield get_pressed


@contextmanager
def console_input_from_controller_context(console: Console) -> Iterator[InputGetter]:
    controller_mapping = get_controller_mapping(console)

    def get_gb_input() -> set[Console.Input]:
        return {
            controller_mapping[keysym]
            for keysym in joystick_get_pressed()
            if keysym in controller_mapping
        }

    with pygame_button_pressed_context() as joystick_get_pressed:
        yield get_gb_input


@contextmanager
def combine_console_input_from_controller_context(
    console: Console, context: ContextManager[InputGetter]
) -> Iterator[InputGetter]:
    with context as getter1:
        with console_input_from_controller_context(console) as getter2:
            yield lambda: getter1() | getter2()
