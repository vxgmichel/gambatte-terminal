from __future__ import annotations

import sys
import time
import logging
import threading
from contextlib import contextmanager
from typing import Callable, Iterator, TYPE_CHECKING
from prompt_toolkit.application import create_app_session

from .console import Console, InputGetter

if sys.platform == "linux":
    try:
        import evdev
    except ImportError:
        evdev = None
else:
    evdev = None

if TYPE_CHECKING:
    import pynput


def get_evdev_input_mapping(console: Console) -> dict[int, Console.Input]:
    return {
        # Directions
        evdev.ecodes.KEY_UP: console.Input.UP,
        evdev.ecodes.KEY_DOWN: console.Input.DOWN,
        evdev.ecodes.KEY_LEFT: console.Input.LEFT,
        evdev.ecodes.KEY_RIGHT: console.Input.RIGHT,
        # A button
        evdev.ecodes.KEY_F: console.Input.A,
        evdev.ecodes.KEY_V: console.Input.A,
        evdev.ecodes.KEY_SPACE: console.Input.A,
        # B button
        evdev.ecodes.KEY_D: console.Input.B,
        evdev.ecodes.KEY_C: console.Input.B,
        evdev.ecodes.KEY_LEFTALT: console.Input.B,
        evdev.ecodes.KEY_RIGHTALT: console.Input.B,
        # Start button
        evdev.ecodes.KEY_ENTER: console.Input.START,
        evdev.ecodes.KEY_RIGHTCTRL: console.Input.START,
        # Select button
        evdev.ecodes.KEY_RIGHTSHIFT: console.Input.SELECT,
        evdev.ecodes.KEY_DELETE: console.Input.SELECT,
    }


def get_evdev_event_mapping(console: Console) -> dict[int, Console.Event]:
    return {
        evdev.ecodes.KEY_0: console.Event.SELECT_STATE_0,
        evdev.ecodes.KEY_1: console.Event.SELECT_STATE_1,
        evdev.ecodes.KEY_2: console.Event.SELECT_STATE_2,
        evdev.ecodes.KEY_3: console.Event.SELECT_STATE_3,
        evdev.ecodes.KEY_4: console.Event.SELECT_STATE_4,
        evdev.ecodes.KEY_5: console.Event.SELECT_STATE_5,
        evdev.ecodes.KEY_6: console.Event.SELECT_STATE_6,
        evdev.ecodes.KEY_7: console.Event.SELECT_STATE_7,
        evdev.ecodes.KEY_8: console.Event.SELECT_STATE_8,
        evdev.ecodes.KEY_9: console.Event.SELECT_STATE_9,
        evdev.ecodes.KEY_L: console.Event.LOAD_STATE,
        evdev.ecodes.KEY_K: console.Event.SAVE_STATE,
    }


def get_pynput_input_mapping(console: Console) -> dict[str, Console.Input]:
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


def get_pynput_event_mapping(console: Console) -> dict[str, Console.Event]:
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
def evdev_key_pressed_context(
    device_path: str | None = None,
) -> Iterator[Callable[[], set[int]]]:
    if evdev is None:
        raise RuntimeError("evdev library not found.")

    try:
        if device_path is None:
            devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
            keyboards = [
                device
                for device in devices
                if evdev.ecodes.EV_KEY in device.capabilities()
            ]
            if not keyboards:
                logging.warning("No keyboards found.")
                raise ValueError("No keyboards found")
            logging.info(f"Found keyboards: {[d.name for d in keyboards]}")
            keyboard = next((d for d in keyboards if "keyboard" in d.name.lower()), None)
            if keyboard is None:
                logging.warning("No keyboard found, falling back to first device.")
                device = keyboards[0]
            else:
                device = keyboard
            logging.info(f"Using device: {device.name}")
        else:
            device = evdev.InputDevice(device_path)
            logging.info(f"Using device: {device.name}")
    except PermissionError:
        print("Permission denied to read from /dev/input/*.", file=sys.stderr)
        print("Please add your user to the 'input' group:", file=sys.stderr)
        print(f"  sudo usermod -aG input $USER", file=sys.stderr)
        print("Then, log out and log back in for the change to take effect.", file=sys.stderr)
        raise

    pressed: set[int] = set()
    stop_event = threading.Event()

    def read_loop() -> None:
        try:
            for event in device.read_loop():
                if stop_event.is_set():
                    break
                if event.type == evdev.ecodes.EV_KEY:
                    if event.value == 1:  # Key press
                        pressed.add(event.code)
                    elif event.value == 0:  # Key release
                        pressed.discard(event.code)
        except OSError as e:
            logging.warning(f"evdev loop error: {e}")

    thread = threading.Thread(target=read_loop, daemon=True)

    try:
        thread.start()
        yield lambda: pressed
    finally:
        stop_event.set()


@contextmanager
def pynput_key_pressed_context(
    display: str | None = None,
) -> Iterator[Callable[[], set[str]]]:
    from pynput import keyboard

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
        key_pressed_context = evdev_key_pressed_context
        input_mapping = get_evdev_input_mapping(console)
        event_mapping = get_evdev_event_mapping(console)
        current_pressed: set[int] = set()
    else:
        key_pressed_context = pynput_key_pressed_context
        input_mapping = get_pynput_input_mapping(console)
        event_mapping = get_pynput_event_mapping(console)
        current_pressed: set[str] = set()

    def get_input() -> set[Console.Input]:
        nonlocal current_pressed
        new_pressed = set(get_pressed())
        old_pressed, current_pressed = current_pressed, new_pressed
        for event in map(event_mapping.get, current_pressed - old_pressed):
            if event is None:
                continue
            console.handle_event(event)
        return {
            input_mapping[keysym]
            for keysym in current_pressed
            if keysym in input_mapping
        }

    with key_pressed_context() as get_pressed:
        yield get_input


def main() -> None:
    if sys.platform != "linux":
        print("This input test is only for linux")
        return

    with create_app_session() as session:
        with session.input.raw_mode():
            try:
                session.output.hide_cursor()
                with evdev_key_pressed_context() as get_pressed:
                    while True:
                        for key in session.input.read_keys():
                            if key.key == "c-c":
                                raise KeyboardInterrupt
                            if key.key == "c-d":
                                raise EOFError
                        
                        codes = [evdev.ecodes.KEY[code] for code in get_pressed()]
                        
                        print(*codes, flush=True, end="")
                        
                        time.sleep(1 / 30);
                        
                        session.output.write_raw("\r")
                        session.output.erase_down()
                        session.output.flush()
            except (KeyboardInterrupt, EOFError):
                pass
            finally:
                session.output.show_cursor()
                session.output.flush()
                print()


if __name__ == "__main__":
    main()
