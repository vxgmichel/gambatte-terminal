import os
from contextlib import contextmanager

from .constants import GBInput


def get_controller_mapping():
    return {
        # Directions
        "A1-": GBInput.UP,
        "H1-": GBInput.UP,
        "A1+": GBInput.DOWN,
        "H1+": GBInput.DOWN,
        "A0-": GBInput.LEFT,
        "H0-": GBInput.LEFT,
        "A0+": GBInput.RIGHT,
        "H0+": GBInput.RIGHT,
        # A button
        "B0": GBInput.A,
        "B3": GBInput.A,
        # B button
        "B1": GBInput.B,
        "B2": GBInput.B,
        # Start button
        "B7": GBInput.START,
        # Select button
        "B6": GBInput.SELECT,
    }


@contextmanager
def pygame_button_pressed_context(deadzone=0.4):
    os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
    import pygame

    pygame.init()
    pygame.joystick.init()
    joystick = None

    def get_pressed():
        nonlocal joystick
        pygame.event.get()
        if pygame.joystick.get_count() == 0:
            joystick = None
            return {}
        if joystick is None:
            joystick = pygame.joystick.Joystick(0)
        pressed = {
            f"B{x}" for x in range(joystick.get_numbuttons()) if joystick.get_button(x)
        }
        if joystick.get_numhats() >= 1:
            if joystick.get_hat(0)[0] > 0:
                pressed.add(f"H0+")
            if joystick.get_hat(0)[0] < 0:
                pressed.add(f"H0-")
            if joystick.get_hat(0)[1] < 0:
                pressed.add(f"H1+")
            if joystick.get_hat(0)[1] > 0:
                pressed.add(f"H1-")
        if joystick.get_numaxes() >= 2:
            if joystick.get_axis(0) > deadzone:
                pressed.add(f"A0+")
            if joystick.get_axis(0) < -deadzone:
                pressed.add(f"A0-")
            if joystick.get_axis(1) > deadzone:
                pressed.add(f"A1+")
            if joystick.get_axis(1) < -deadzone:
                pressed.add(f"A1-")
        return pressed

    yield get_pressed


@contextmanager
def gb_input_from_controller_context():
    controller_mapping = get_controller_mapping()

    def get_gb_input():
        value = 0
        for keysym in joystick_get_pressed():
            value |= controller_mapping.get(keysym, 0)
        return value

    with pygame_button_pressed_context() as joystick_get_pressed:
        yield get_gb_input


@contextmanager
def combine_gb_input_from_controller_context(context):
    with context as getter1:
        with gb_input_from_controller_context() as getter2:
            yield lambda: getter1() | getter2()
