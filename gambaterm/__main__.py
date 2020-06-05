#!/usr/bin/env python3

import re
import time
import shutil
import select
import argparse
from itertools import count
from collections import deque

import numpy as np

from ._gambatte import GB, paint_frame
from .xinput import gb_input_context, cbreak_mode

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


def run(romfile, get_input, stdout, stdin, test=False, fast=True):

    # Load the rom
    gb = GB()
    return_code = gb.load(romfile)
    if return_code != 0:
        exit(return_code)

    # Prepare buffers with invalid data
    video = np.full((144, 160), -1, np.int32)
    audio = np.full(10 * 35112, -1, np.int32)
    last_frame = video.copy()

    # Print area
    refx, refy = 1, 1
    width, height = shutil.get_terminal_size((80, 60))

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
            break

        # Tick the emulator
        gb.set_input(get_input())
        offset, samples = gb.run_for(video, 160, audio, 10 * 35112)
        assert offset > 0

        # Skip every other frame
        if i % 2 and not fast:
            continue

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
            part4 = (sum_deltas - sum_deltas3) / sum_deltas * 100
            data_rate = sum(data_length) / len(data_length) * avg / 1024
            title = f"FPS: {avg:.1f} - "
            title += f"{part1:.1f}% {part2:.1f}% {part3:.1f}% {part4:.1f}%"
            title += f" - {data_rate:.1f}KB/s"
            print(f"\x1b]0;{title}\x07", end="", flush=True)


def main(args=None):
    parser = argparse.ArgumentParser(description='Gambatte terminal frontend')
    parser.add_argument('romfile', metavar='ROM', type=str)
    parser.add_argument('--test', '-t', action='store_true')
    parser.add_argument('--fast', '-f', action='store_true')
    args = parser.parse_args(args)

    with cbreak_mode() as (stdin, stdout):
        try:
            stdout.write(CSI + b"2J")
            with gb_input_context() as get_gb_input:
                run(
                    args.romfile,
                    get_gb_input,
                    stdout,
                    stdin,
                    test=args.test,
                    fast=args.fast
                )
        except KeyboardInterrupt:
            pass
        finally:
            purge(stdin)
            stdout.write(CSI + b"0m" + CSI + b"2J" + b"\n")


if __name__ == "__main__":
    main()
