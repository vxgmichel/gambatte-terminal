from __future__ import annotations

import os
import re
import sys
import time
import contextlib
from itertools import count
from collections import deque
from typing import Deque, Iterator

import numpy as np
from blessed import Terminal

from .termblit import blit
from .audio import AudioOut
from .console import Console
from .input_getter import BaseInputGetter
from .colors import ColorMode

_CPR_RE = re.compile(r"\x1b\[\d+;\d+R")


@contextlib.contextmanager
def timing(deltas: Deque[float]) -> Iterator[None]:
    start = time.perf_counter()
    try:
        yield
    finally:
        deltas.append(time.perf_counter() - start)


def get_ref(width: int, height: int, console: Console) -> tuple[int, int]:
    refx = 2 + max(0, (height - console.HEIGHT // 2) // 2)
    refy = 3 + max(0, (width - console.WIDTH) // 2)
    return refx, refy


def write_frame(term: Terminal, frame_data: bytes) -> None:
    # Fix code page issue on windows:
    # `sys.stdout.buffer.raw` is a `WindowsConsoleIO` that always support UTF-8
    # regardless of the configured codepage
    if sys.platform == "win32" and term.stream.fileno() == sys.stdout.fileno():
        sys.stdout.buffer.write(frame_data)
        sys.stdout.buffer.flush()
    else:
        os.write(term.stream.fileno(), frame_data)


def run(
    console: Console,
    input_getter: BaseInputGetter,
    term: Terminal,
    audio_out: AudioOut | None = None,
    frame_advance: int = 1,
    color_mode: ColorMode = ColorMode.HAS_24_BIT_COLOR,
    break_after: int | None = None,
    speed: float = 1.0,
    use_cpr_sync: bool = False,
) -> None:
    assert color_mode > 0

    # Prepare buffers with invalid data
    video = np.full((console.HEIGHT, console.WIDTH), 0, np.uint32)
    audio = np.full((2 * console.TICKS_IN_FRAME, 2), 0, np.int16)
    last_frame = video.copy()

    # Print area (default to 24x80 if terminal reports zero)
    height = term.height or 24
    width = term.width or 80
    refx, refy = get_ref(width, height, console)

    # Prepare reporting
    fps = console.FPS * speed
    average_over = int(round(fps))  # frames
    ticks: Deque[float] = deque(maxlen=average_over)
    emu_deltas: Deque[float] = deque(maxlen=average_over)
    audio_deltas: Deque[float] = deque(maxlen=average_over)
    video_deltas: Deque[float] = deque(maxlen=average_over)
    sync_deltas: Deque[float] = deque(maxlen=average_over)
    total_deltas: Deque[float] = deque(maxlen=average_over)
    shifting: Deque[float] = deque(maxlen=average_over)
    shown_frames: Deque[int] = deque(maxlen=average_over)
    data_length: Deque[int] = deque(maxlen=average_over)
    start = time.time()

    # Create a 100 ms time shift to fill up audio buffer
    if audio_out:
        start -= 0.1

    # Prepare state
    new_frame = False
    screen_ready = True
    frame_start_time = None
    frame_data = bytearray()
    current_title_sequence = b""

    # Loop over emulator frames
    for i in count():
        # Add total deltas
        if frame_start_time is not None:
            total_deltas.append(time.perf_counter() - frame_start_time)
        frame_start_time = time.perf_counter()

        # Break when frame limit is reach
        if break_after is not None and i >= break_after:
            return

        # Tick the emulator
        with timing(emu_deltas):
            console.set_input(input_getter.get_pressed())
            offset, samples = console.advance_one_frame(video, audio)
            new_frame = new_frame or offset > 0
            ticks.append(samples)

        # Send audio
        with timing(audio_deltas):
            if audio_out:
                audio_out.send(audio[:samples, :])

        # Read keys for ctrl-c, ctrl-d, and CPR response.
        # If the kitty keyboard protocol is used, all inputs are sent as CSI sequences
        # (e.g. `\x1b[99;5u` rather than raw `\x03`), so we check blessed's
        # decoded `key_name` attribute, since it ends up being `KEY_CTRL_C` for ctrl+c
        # and `KEY_CTRL_D` for ctrl+d regardless of the underlying encoding.
        new_color_mode = color_mode
        for key in input_getter.pop_keystrokes():
            if key.key_name == "KEY_CTRL_C":
                raise KeyboardInterrupt
            if key.key_name == "KEY_CTRL_D":
                raise EOFError
            if key.key_name == "KEY_TAB":
                new_color_mode = color_mode.cycle()
            if _CPR_RE.match(str(key)):
                screen_ready = True

        # Render video
        with timing(video_deltas):
            # Re-use the same buffer to accumulate frame data and avoid unnecessary allocations.
            frame_data.clear()

            # Detect if a shift is currently happening
            shift = shifting and shifting[-1] > 1 / fps

            # Render a new frame only if:
            # - it is the right time according to frame_advance
            # - a new frame is available from the emulator
            # - the screen is ready for a new frame (either CPR sync is disabled, or enabled and we received the CPR response)
            # - we are not currently shifting (to prevent flooding the terminal with new frames when the rendering is too slow)
            if i % frame_advance == 0 and new_frame and screen_ready and not shift:
                new_frame = False

                # Detect terminal resize and color mode change
                new_height = term.height or 24
                new_width = term.width or 80
                maybe_clear_sequence = b""
                if (new_height, new_width) != (
                    height,
                    width,
                ) or new_color_mode != color_mode:
                    maybe_clear_sequence = b"\033[H\033[2J"
                    height, width = new_height, new_width
                    refx, refy = get_ref(width, height, console)
                    color_mode = new_color_mode
                    last_frame.fill(0)

                # Render frame with synchronized output mode (DEC 2026) to prevent flickering
                # when the screen is cleared, or an artificial CRT-like "rolling band" side-effects
                # from fast "sprite blinking" meant to cause "transparency" effect on original HW,
                # https://zladx.github.io/posts/links-awakening-partial-translucency
                frame_data += b"\033[?2026h"
                frame_data += maybe_clear_sequence
                frame_data += blit(
                    video, last_frame, refx, refy, width - 1, height, color_mode
                )
                frame_data += b"\033[?2026l"
                last_frame = video.copy()

                # Update reporting
                data_length.append(len(frame_data))
                shown_frames.append(True)

            # Ignore this video frame
            else:
                data_length.append(0)
                shown_frames.append(False)

        # Pacing and synchronization
        with timing(sync_deltas):
            # Video sync
            if frame_data:
                # Send CPR request
                if use_cpr_sync:
                    frame_data += b"\033[1;1H\033[6n"
                    screen_ready = False
                # Add the current title
                frame_data += current_title_sequence
                # Write the entire frame in one go to avoid fragmentation
                write_frame(term, frame_data)
            # Timing sync
            increment = samples / console.TICKS_IN_FRAME
            deadline = start + increment / fps
            current = time.time()
            if current < deadline - 1e-3:
                time.sleep(deadline - current)
            # Use deadline as new reference to prevent shifting
            shifting.append(time.time() - deadline)
            start = deadline

        # Prepare title for the next frame
        if i % average_over == 1:
            tps = fps * console.TICKS_IN_FRAME
            emu_fps = tps * len(ticks) / sum(ticks)
            video_fps = emu_fps * sum(shown_frames) / len(shown_frames)
            total_fps = len(total_deltas) / sum(total_deltas)
            emu_percent = sum(emu_deltas) / len(emu_deltas) * total_fps * 100
            audio_percent = sum(audio_deltas) / len(audio_deltas) * total_fps * 100
            video_percent = sum(video_deltas) / len(video_deltas) * total_fps * 100
            data_rate = sum(data_length) / len(data_length) * total_fps / 1000
            title = f"Gambaterm - {total_fps:.0f} FPS | "
            title += f"{os.path.basename(console.romfile)} | "
            title += f"Emu: {emu_fps:.0f} FPS - {emu_percent:.0f}% CPU | "
            title += f"Video: {video_fps:.0f} FPS - {video_percent:.0f}% CPU - "
            title += f"{data_rate:.0f} KB/s | "
            title += f"Audio: {audio_percent:.0f}% CPU | "
            title += f"{color_mode.report()} mode"
            current_title_sequence = term.set_window_title(title).encode("utf-8")
