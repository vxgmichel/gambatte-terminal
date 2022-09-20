from __future__ import annotations

import os
import time
import contextlib
from itertools import count
from collections import deque
from typing import Deque, Iterator

import numpy as np
from prompt_toolkit.application import AppSession

from .termblit import blit
from .audio import AudioOut
from .console import Console, InputGetter
from .colors import ColorMode


@contextlib.contextmanager
def timing(deltas: Deque) -> Iterator[None]:
    try:
        start = time.perf_counter()
        yield
    finally:
        deltas.append(time.perf_counter() - start)


def get_ref(width: int, height: int, console: Console) -> tuple[int, int]:
    refx = 2 + max(0, (height - console.HEIGHT // 2) // 2)
    refy = 3 + max(0, (width - console.WIDTH) // 2)
    return refx, refy


def run(
    console: Console,
    get_input: InputGetter,
    app_session: AppSession,
    audio_out: AudioOut | None = None,
    frame_advance: int = 1,
    color_mode: ColorMode = ColorMode.HAS_24_BIT_COLOR,
    break_after: int | None = None,
    speed_factor: float = 1.0,
    use_cpr_sync: bool = False,
) -> None:
    assert color_mode > 0

    # Prepare buffers with invalid data
    video = np.full((console.HEIGHT, console.WIDTH), -1, np.uint32)
    audio = np.full((2 * console.TICKS_IN_FRAME, 2), -1, np.int16)
    last_frame = video.copy()

    # Print area
    height, width = app_session.output.get_size()
    refx, refy = get_ref(width, height, console)

    # Prepare reporting
    fps = console.FPS * speed_factor
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
            console.set_input(get_input())
            offset, samples = console.advance_one_frame(video, audio)
            new_frame = new_frame or offset > 0
            ticks.append(samples)

        # Send audio
        with timing(audio_deltas):
            if audio_out:
                audio_out.send(audio[:samples, :])

        # Read keys
        for event in app_session.input.read_keys():
            if event.key == "c-c":
                raise KeyboardInterrupt
            if event.key == "c-d":
                raise OSError
            if event.key == "<cursor-position-response>":
                screen_ready = True

        # Render video
        with timing(video_deltas):
            # Send the frame
            shift = shifting and shifting[-1] > 1 / fps
            if i % frame_advance == 0 and new_frame and screen_ready and not shift:
                new_frame = False
                # Check terminal size
                new_size = app_session.output.get_size()
                if new_size != (height, width):
                    app_session.output.erase_screen()
                    app_session.output.flush()
                    height, width = new_size
                    refx, refy = get_ref(width, height, console)
                    last_frame.fill(-1)
                # Render frame
                video_data = blit(
                    video, last_frame, refx, refy, width - 1, height, color_mode
                )
                last_frame = video.copy()
                # Update reporting
                data_length.append(len(video_data))
                shown_frames.append(True)
            # Ignore this video frame
            else:
                video_data = None
                data_length.append(0)
                shown_frames.append(False)

        with timing(sync_deltas):
            # Video sync
            if video_data:
                # Write video frame, might block
                os.write(app_session.output.fileno(), video_data)
                # Send CPR request
                if use_cpr_sync:
                    app_session.output.ask_for_cpr()
                    screen_ready = False
            # Timing sync
            increment = samples / console.TICKS_IN_FRAME
            deadline = start + increment / fps
            current = time.time()
            if current < deadline - 1e-3:
                time.sleep(deadline - current)
            # Use deadline as new reference to prevent shifting
            shifting.append(time.time() - deadline)
            start = deadline

        # Reporting
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
            title += f"Audio: {audio_percent:.0f}% CPU"
            app_session.output.set_title(title)
            app_session.output.flush()
