#!/usr/bin/env python3

import os
import time
import contextlib
from itertools import count
from collections import deque

import numpy as np

from .libgambatte import GB
from .termblit import blit

# Gameboy constants
GB_WIDTH = 160
GB_HEIGHT = 144
GB_FPS = 59.727500569606
GB_TICKS_IN_FRAME = 35112


@contextlib.contextmanager
def timing(deltas):
    try:
        start = time.time()
        yield
    finally:
        deltas.append(time.time() - start)


def get_ref(width, height):
    refx = 2 + max(0, (height - GB_HEIGHT // 2) // 2)
    refy = 3 + max(0, (width - GB_WIDTH) // 2)
    return refx, refy


def run(
    romfile,
    get_input,
    app_session,
    audio_out=None,
    color_mode=False,
    frame_advance=1,
    break_after=None,
    speed_factor=1.0,
    save_directory=None,
    force_gameboy=False,
):
    assert color_mode > 0

    # Set save_directory
    gb = GB()
    if save_directory:
        gb.set_save_directory(save_directory)

    # Load the rom
    return_code = gb.load(romfile, 1 if force_gameboy else 0)
    if return_code != 0:
        return return_code

    # Prepare buffers with invalid data
    video = np.full((GB_HEIGHT, GB_WIDTH), -1, np.int32)
    audio = np.full(2 * GB_TICKS_IN_FRAME, -1, np.int32)
    last_frame = video.copy()

    # Print area
    height, width = app_session.output.get_size()
    refx, refy = get_ref(width, height)

    # Prepare reporting
    fps = GB_FPS * speed_factor
    average_over = int(round(fps))  # frames
    ticks = deque(maxlen=average_over)
    emu_deltas = deque(maxlen=average_over)
    audio_deltas = deque(maxlen=average_over)
    video_deltas = deque(maxlen=average_over)
    sync_deltas = deque(maxlen=average_over)
    shown_frames = deque(maxlen=average_over)
    data_length = deque(maxlen=average_over)
    start = time.time()

    # Prepare CPR handling
    got_cpr_response = True

    # Loop over emulator frames
    new_frame = False
    for i in count():

        # Break when frame limit is reach
        if break_after is not None and i >= break_after:
            return 0

        # Tick the emulator
        with timing(emu_deltas):
            gb.set_input(get_input())
            offset, samples = gb.run_for(video, GB_WIDTH, audio, GB_TICKS_IN_FRAME)
            new_frame = new_frame or offset > 0
            ticks.append(samples)

        # Send audio
        with timing(audio_deltas):
            if audio_out:
                audio_out.send(audio[:samples])

        # Read keys
        for event in app_session.input.read_keys():
            if event.key == "c-c":
                raise KeyboardInterrupt
            if event.key == "c-d":
                raise OSError
            if event.key == "<cursor-position-response>":
                got_cpr_response = True

        # Send video
        with timing(video_deltas):
            # Send the frame
            if i % frame_advance == 0 and new_frame and got_cpr_response:
                new_frame = False
                # Check terminal size
                new_size = app_session.output.get_size()
                if new_size != (height, width):
                    app_session.output.erase_screen()
                    app_session.output.flush()
                    height, width = new_size
                    refx, refy = get_ref(width, height)
                    last_frame.fill(-1)
                # Render frame
                data = blit(
                    video, last_frame, refx, refy, width - 1, height, color_mode
                )
                last_frame = video.copy()
                # Write frame with CPR request
                os.write(app_session.output.fileno(), data)
                app_session.output.ask_for_cpr()
                got_cpr_response = False
                data_length.append(len(data))
                shown_frames.append(True)
            # Ignore this video frame
            else:
                data_length.append(0)
                shown_frames.append(False)

        with timing(sync_deltas):
            # Audio sync
            if audio_out:
                audio_out.sync()
            # Timing sync
            increment = samples / GB_TICKS_IN_FRAME
            deadline = start + increment / fps
            current = time.time()
            if current < deadline - 1e-3:
                time.sleep(deadline - current)
            # Use deadline as new reference to prevent shifting
            start = deadline

        # Reporting
        if i % average_over == 0:
            tps = fps * GB_TICKS_IN_FRAME
            emu_fps = tps * len(ticks) / sum(ticks)
            video_fps = emu_fps * sum(shown_frames) / len(shown_frames)
            emu_percent = sum(emu_deltas) / len(emu_deltas) * emu_fps * 100
            audio_percent = sum(audio_deltas) / len(audio_deltas) * emu_fps * 100
            video_percent = sum(video_deltas) / len(video_deltas) * emu_fps * 100
            data_rate = sum(data_length) / len(data_length) * emu_fps / 1024
            title = f"Gambaterm | "
            title += f"{os.path.basename(romfile)} | "
            title += f"Emu: {emu_fps:.0f} FPS - {emu_percent:.0f}% CPU | "
            title += f"Video: {video_fps:.0f} FPS - {video_percent:.0f}% CPU - {data_rate:.0f} KB/s | "
            title += f"Audio: {audio_percent:.0f}% CPU"
            app_session.output.set_title(title)
            app_session.output.flush()
