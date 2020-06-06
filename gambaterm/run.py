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

# def gbc_to_rgb32(r, g, b):
#     new_r = ((r * 13 + g * 2 + b) >> 1) << 16
#     new_g = (g * 3 + b) << 9
#     new_b = (r * 3 + g * 2 + b * 11) >> 1
#     return new_r | new_g | new_b

# POSSIBLE_COLORS = list(starmap(gbc_to_rgb32, product(range(2**5), repeat=3)))


def wait_for_cpr(stdin, data=b""):
    while not CPR_PATTERN.search(data):
        data += stdin.read(1024)


def purge(stdin):
    while True:
        r, _, _ = select.select([stdin], (), (), 0)
        if not r:
            return
        stdin.read(1024)


def run(romfile, get_input, stdin, stdout, get_size, test=False, fast=False):
    # Load the rom
    gb = GB()
    return_code = gb.load(romfile)
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
    start = time.time()

    # Loop over emulator frames
    for i in count():

        # Break after 1 minute in test mode
        if test and i == 60*60:
            return 0

        # Tick the emulator
        gb.set_input(get_input())
        offset, samples = gb.run_for(video, 160, audio, 60 * 35112)
        assert offset > 0

        # Skip every other frame
        if i % 2 and not fast:
            continue

        # Check terminal size
        new_size = get_size()
        if new_size != (width, height):
            stdout.write(CSI + b"0m" + CSI + b"2J")
            width, height = new_size
            last_frame.fill(-1)

        # Render frame
        deltas1.append(time.time() - start)
        data = paint_frame(video, last_frame, refx, refy, width, height)
        last_frame = video.copy()
        deltas2.append(time.time() - start)

        # Make sure that terminal is done rendring the previous frame
        if i != 0:
            wait_for_cpr(stdin)

        # Write frame with CPR request
        stdout.write(data)
        stdout.write(CSI + b"6n")
        data_length.append(len(data))
        deltas3.append(time.time() - start)

        # Time control
        stop = time.time()
        deadline = start + (1/60 if fast else 1/30)
        if stop < deadline and not test:
            time.sleep(deadline - stop)
            stop = time.time()
        start, delta = stop, stop - start
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
            title += f"FPS: {avg:.0f} - "
            title += f"CPU: {cpu_percent:.0f}% - "
            title += f"IO: {io_percent:.0f}% - "
            title += f"{data_rate:.0f}KB/s"
            stdout.write(b"\x1b]0;%s\x07" % title.encode())
