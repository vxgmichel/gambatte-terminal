#!/usr/bin/env python3

import sys
import time
import shutil
import argparse
from collections import deque
from itertools import count

import numpy as np

from _gambatte import GB

CSI = "\033["
UPPER_HALF_BLOCK = "\u2580"
LOWER_HALF_BLOCK = "\u2584"

TEMPLATE = b"%03d;%03d;%03d"


def int32_to_ansibytes(n):
    b = n & 0xff
    g = (n >> 8) & 0xff
    r = (n >> 16) & 0xff
    return TEMPLATE % (r, g, b)


def make_data():
    result = ""
    # Reset screen
    result += f"{CSI}3J"
    result += f"{CSI}1;1H"
    # Get screen size
    width, height = shutil.get_terminal_size((80, 60))
    # Loop over 2-rows
    for _ in range(144 // 2):
        # Loop over columns
        for _, _ in zip(range(width), range(160)):
            result += f"{CSI}38;2;000;000;000m"
            result += f"{CSI}48;2;000;000;000m"
            result += UPPER_HALF_BLOCK
        result += f"{CSI}0m\n"
    raw = result.encode()
    return bytearray(raw), width


def paint_frame(video, data, width, cache={}):
    index = 10
    for row_index in range(0, 144, 2):
        for column_index in range(min(width, 160)):
            for row_offset in (0, 1):
                index += 7
                key = video[row_index + row_offset, column_index]
                value = cache.get(key)
                if value is None:
                    value = int32_to_ansibytes(key)
                    cache[key] = value
                data[index:index+11] = cache[key]
                index += 12

            index += 3

        index += 5


def main(arg):

    # Load the rom
    gb = GB()
    return_code = gb.load(arg)
    if return_code != 0:
        exit(return_code)

    # Prepare buffer
    video = np.zeros((144, 160), np.uint32)
    audio = np.zeros(2 * 35112, np.uint32)
    data, width = make_data()

    # Loop over frames
    deltas = deque(maxlen=60)
    deltas1 = deque(maxlen=60)
    deltas2 = deque(maxlen=60)
    deltas3 = deque(maxlen=60)
    start = time.time()
    for i in count():

        # Tick the emulator
        offset, samples = gb.runFor(video, 160, audio, 2 * 35112)
        assert offset > 0

        # Skip every other frame
        if i % 2:
            continue

        # Display frame
        deltas1.append(time.time() - start)
        paint_frame(video, data, width)
        deltas2.append(time.time() - start)
        sys.stdout.buffer.write(data)
        deltas3.append(time.time() - start)

        # Time control
        stop = time.time()
        deadline = start + 1/30
        if stop < deadline:
            time.sleep(deadline - stop)
            stop = time.time()
        time.sleep(max(0, start + 1/30 - time.time()))
        start, delta = stop, stop - start
        deltas.append(delta)

        # Print FPS
        if i % 60 == 0:
            sum_deltas = sum(deltas)
            sum_deltas1 = sum(deltas1)
            sum_deltas2 = sum(deltas2)
            sum_deltas3 = sum(deltas3)
            avg = len(deltas) / sum_deltas
            part1 = sum_deltas1 / sum_deltas * 100
            part2 = (sum_deltas2 - sum_deltas1) / sum_deltas * 100
            part3 = (sum_deltas3 - sum_deltas2) / sum_deltas * 100
            part4 = (sum_deltas - sum_deltas3) / sum_deltas * 100
            title = f"FPS: {avg:.1f} - "
            title += f"{part1:.1f}% {part2:.1f}% {part3:.1f}% {part4:.1f}%"
            print(f"\x1b]0;{title}\x07", end="", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Gambatte terminal frontend')
    parser.add_argument('romfile', metavar='ROM', type=str)
    args = parser.parse_args()
    main(args.romfile)
