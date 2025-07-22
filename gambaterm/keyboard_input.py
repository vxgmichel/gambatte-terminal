from __future__ import annotations

import sys
import time
import logging
import threading
import os
import subprocess
import json
from contextlib import contextmanager, closing
from typing import Callable, Iterator, TYPE_CHECKING
from prompt_toolkit.application import create_app_session

from .console import Console, InputGetter

_last_focus_check_time = 0.0
_last_focus_state = True # Assume focused initially

def is_terminal_focused() -> bool:
    """
    Checks if the terminal running gambaterm is currently focused in Hyprland.
    Caches the result for a short period to reduce overhead.
    """
    global _last_focus_check_time, _last_focus_state
    
    # Cache duration in seconds
    CACHE_DURATION = 0.2 # 200ms

    current_time = time.time()
    if (current_time - _last_focus_check_time) < CACHE_DURATION:
        return _last_focus_state

    try:
        current_pid = os.getpid()
        logging.debug(f"Current gambaterm PID: {current_pid}")

        def get_process_info(pid: int) -> tuple[str, int]:
            """Helper to get process name and parent PID."""
            try:
                # Use ps to get command name and parent PID
                ps_output = subprocess.run(
                    ['ps', '-o', 'comm=', '-o', 'ppid=', '-p', str(pid)],
                    capture_output=True, text=True, check=True
                ).stdout.strip()
                parts = ps_output.split()
                if len(parts) == 2:
                    return parts[0], int(parts[1])
                return "", 0 # Should not happen if ps output is as expected
            except (subprocess.CalledProcessError, ValueError):
                return "", 0

        # Find the terminal emulator's PID by traversing the process tree
        terminal_emulator_pid = 0
        pid_to_check = current_pid
        
        # List of common terminal emulator process names
        terminal_emulators = ["kitty", "wezterm", "alacritty", "gnome-terminal-", "konsole", "foot"]

        # Traverse up the process tree
        while pid_to_check != 0:
            comm, ppid = get_process_info(pid_to_check)
            logging.debug(f"Checking PID {pid_to_check}: comm='{comm}', ppid={ppid}")
            
            if any(term_name in comm for term_name in terminal_emulators):
                terminal_emulator_pid = pid_to_check
                logging.debug(f"Identified terminal emulator PID: {terminal_emulator_pid} ({comm})")
                break
            
            if pid_to_check == ppid: # Reached init or systemd, or a loop
                break
            
            pid_to_check = ppid
            if pid_to_check == 1: # Reached init process, stop
                break

        if terminal_emulator_pid == 0:
            logging.warning("Could not identify terminal emulator PID. Assuming focused.")
            _last_focus_state = True
            _last_focus_check_time = current_time
            return True

        # Get active window info from Hyprland
        result = subprocess.run(['hyprctl', 'activewindow', '-j'], capture_output=True, text=True, check=True)
        active_window_data = json.loads(result.stdout)
        logging.debug(f"Hyprctl activewindow data: {active_window_data}")

        focused_pid = active_window_data.get('pid')
        focused_title = active_window_data.get('title')
        focused_class = active_window_data.get('class')
        logging.debug(f"Focused client: PID={focused_pid}, Title='{focused_title}', Class='{focused_class}'")

        is_focused = False
        if focused_pid == terminal_emulator_pid:
            logging.debug("Terminal is focused.")
            is_focused = True
        else:
            logging.debug("Terminal is not focused.")
            is_focused = False
        
        _last_focus_state = is_focused
        _last_focus_check_time = current_time
        return is_focused

    except FileNotFoundError:
        logging.warning("Error: 'hyprctl' or 'ps' command not found. Make sure they are installed and in your PATH.")
        _last_focus_state = True # Assume focused if commands are missing
        _last_focus_check_time = current_time
        return True
    except subprocess.CalledProcessError as e:
        logging.warning(f"Error executing command: {e}\nStderr: {e.stderr}")
        _last_focus_state = True # Assume focused on error
        _last_focus_check_time = current_time
        return True
    except json.JSONDecodeError:
        logging.warning("Error: Could not decode JSON from 'hyprctl activewindow -j'.")
        _last_focus_state = True # Assume focused on JSON error
        _last_focus_check_time = current_time
        return True



if sys.platform == "linux":
    try:
        import evdev
    except ImportError:
        evdev = None
    try:
        from Xlib import XK
        from Xlib.ext import xinput
        from Xlib.display import Display
    except ImportError:
        XK = None
        xinput = None
        Display = None
else:
    evdev = None
    XK = None
    xinput = None
    Display = None

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


def get_xlib_input_mapping(console: Console) -> dict[int, Console.Input]:
    return {
        # Directions
        XK.XK_Up: console.Input.UP,
        XK.XK_Down: console.Input.DOWN,
        XK.XK_Left: console.Input.LEFT,
        XK.XK_Right: console.Input.RIGHT,
        # A button
        XK.XK_f: console.Input.A,
        XK.XK_v: console.Input.A,
        XK.XK_space: console.Input.A,
        # B button
        XK.XK_d: console.Input.B,
        XK.XK_c: console.Input.B,
        XK.XK_Alt_L: console.Input.B,
        XK.XK_Alt_R: console.Input.B,
        # Start button
        XK.XK_Return: console.Input.START,
        XK.XK_Control_R: console.Input.START,
        # Select button
        XK.XK_Shift_R: console.Input.SELECT,
        XK.XK_Delete: console.Input.SELECT,
    }


def get_xlib_event_mapping(console: Console) -> dict[int, Console.Event]:
    return {
        XK.XK_0: console.Event.SELECT_STATE_0,
        XK.XK_1: console.Event.SELECT_STATE_1,
        XK.XK_2: console.Event.SELECT_STATE_2,
        XK.XK_3: console.Event.SELECT_STATE_3,
        XK.XK_4: console.Event.SELECT_STATE_4,
        XK.XK_5: console.Event.SELECT_STATE_5,
        XK.XK_6: console.Event.SELECT_STATE_6,
        XK.XK_7: console.Event.SELECT_STATE_7,
        XK.XK_8: console.Event.SELECT_STATE_8,
        XK.XK_9: console.Event.SELECT_STATE_9,
        XK.XK_l: console.Event.LOAD_STATE,
        XK.XK_k: console.Event.SAVE_STATE,
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
                # Only process events if the terminal is focused
                if not is_terminal_focused():
                    continue
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
def xlib_key_pressed_context(
    display: str | None = None,
) -> Iterator[Callable[[], set[int]]]:
    if XK is None or xinput is None or Display is None:
        raise RuntimeError("Xlib library not found.")

    with closing(Display(display)) as xdisplay:
        extension_info = xdisplay.query_extension("XInputExtension")
        xinput_major = extension_info.major_opcode
        # Set of currently pressed keys and focused flag
        pressed: set[int] = set()
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

        def get_pressed() -> set[int]:
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
        if os.environ.get("XDG_SESSION_TYPE") == "wayland":
            key_pressed_context = evdev_key_pressed_context
            input_mapping = get_evdev_input_mapping(console)
            event_mapping = get_evdev_event_mapping(console)
            current_pressed: set[int] = set()
        else:
            key_pressed_context = xlib_key_pressed_context
            input_mapping = get_xlib_input_mapping(console)
            event_mapping = get_xlib_event_mapping(console)
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

    if key_pressed_context == evdev_key_pressed_context:
        with key_pressed_context() as get_pressed:
            yield get_input
    else:
        with key_pressed_context(display=display) as get_pressed:
            yield get_input
        yield get_input


def _run_input_loop(session, get_pressed, mapping):
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

def main() -> None:
    if sys.platform != "linux":
        print("This input test is only for linux")
        return

    with create_app_session() as session:
        with session.input.raw_mode():
            try:
                session.output.hide_cursor()
                if os.environ.get("XDG_SESSION_TYPE") == "wayland":
                    key_pressed_context = evdev_key_pressed_context
                    mapping = lambda code: evdev.ecodes.KEY[code]
                    with key_pressed_context() as get_pressed:
                        _run_input_loop(session, get_pressed, mapping)
                else:
                    key_pressed_context = xlib_key_pressed_context
                    reverse_lookup = {
                        v: k[3:] for k, v in XK.__dict__.items() if k.startswith("XK_")
                    }
                    mapping = reverse_lookup.get
                    with key_pressed_context() as get_pressed:
                        _run_input_loop(session, get_pressed, mapping)
            except (KeyboardInterrupt, EOFError):
                pass
            finally:
                session.output.show_cursor()
                session.output.flush()
                print()


if __name__ == "__main__":
    main()
