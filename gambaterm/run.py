#!/usr/bin/env python3

import re
import os
import time
import select
from itertools import count
from collections import deque

import numpy as np

from ._gambatte import GB, paint_frame

CSI = b"\033["
CPR_PATTERN = re.compile(rb"\033\[\d+;\d+R")
TICKS_IN_FRAME = 35112


def wait_for_cpr(stdin, data=b""):
    while not CPR_PATTERN.search(data):
        data += stdin.read(1024)


def purge(stdin):
    while True:
        r, _, _ = select.select([stdin], (), (), 0)
        if not r:
            return
        stdin.read(1024)


def run(
    romfile,
    get_input,
    stdin,
    stdout,
    get_size,
    audio_out=None,
    color_mode=False,
    frame_advance=1,
    frame_limit=None,
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
    video = np.full((144, 160), -1, np.int32)
    audio = np.full(60 * 35112, -1, np.int32)
    last_frame = video.copy()

    # Print area
    refx, refy = 1, 1
    width, height = get_size()

    # Prepare reporting
    average_over = 30  # frames
    deltas = deque(maxlen=average_over)
    deltas1 = deque(maxlen=average_over)
    deltas2 = deque(maxlen=average_over)
    deltas3 = deque(maxlen=average_over)
    data_length = deque(maxlen=average_over)
    start = real_start = time.time()

    # Loop over emulator frames
    new_frame = False
    for i in count():

        # Break when frame limit is reach
        if frame_limit is not None and i >= frame_limit:
            return 0

        # Tick the emulator
        gb.set_input(get_input())
        offset, samples = gb.run_for(video, 160, audio, TICKS_IN_FRAME)
        new_frame = new_frame or offset > 0

        # Send audio
        if audio_out:
            audio_out.send(audio[:samples])

        # This frame is displayed
        if i % frame_advance == 0 and new_frame:
            new_frame = False

            # Check terminal size
            new_size = get_size()
            if new_size != (width, height):
                stdout.write(CSI + b"0m" + CSI + b"2J")
                width, height = new_size
                last_frame.fill(-1)

            # Render frame
            deltas1.append(time.time() - real_start)
            data = paint_frame(video, last_frame, refx, refy, width, height, color_mode)
            last_frame = video.copy()
            deltas2.append(time.time() - real_start)

            # Make sure that terminal is done rendring the previous frame
            if i != 0:
                wait_for_cpr(stdin)

            # Write frame with CPR request
            stdout.write(data)
            stdout.write(CSI + b"6n")
            data_length.append(len(data))
            deltas3.append(time.time() - real_start)

        # This frame is not displayed
        else:
            deltas2.append(time.time() - real_start)
            deltas3.append(time.time() - real_start)

        # Make sure we don't go faster than audio
        if audio_out:
            audio_out.sync()

        # Time control
        increment = samples / TICKS_IN_FRAME / 60
        deadline = start + increment / speed_factor
        current = time.time()
        if current < deadline - 1e-3:
            time.sleep(deadline - current)
            current = time.time()
        start, real_start, delta = deadline, current, current - real_start
        deltas.append(delta)

        # Reporting
        if i % average_over == 0:
            sum_deltas = sum(deltas)
            sum_deltas1 = sum(deltas1)
            sum_deltas2 = sum(deltas2)
            sum_deltas3 = sum(deltas3)
            avg = len(deltas) / sum_deltas
            part1 = sum_deltas1 / sum_deltas * 100
            part2 = (sum_deltas2 - sum_deltas1) / sum_deltas * 100
            part3 = (sum_deltas3 - sum_deltas2) / sum_deltas * 100
            cpu_percent, io_percent = part1 + part2, part3
            data_rate = sum(data_length) / len(data_length) * avg / 1024
            title = f"Gambaterm - "
            title += f"{os.path.basename(romfile)} - "
            title += f"FPS: {avg / frame_advance:.0f} - "
            title += f"CPU: {cpu_percent:.0f}% - "
            title += f"IO: {io_percent:.0f}% - "
            title += f"{data_rate:.0f}KB/s"
            stdout.write(b"\x1b]0;%s\x07" % title.encode())
