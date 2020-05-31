#!/usr/bin/env python3

import time
import shutil
import argparse
from itertools import count
from collections import deque

import numpy as np

from _gambatte import GB

CSI = "\033["
UPPER_HALF_BLOCK = "\u2580"
LOWER_HALF_BLOCK = "\u2584"


def paint_frame(data):
    result = ""
    # Reset screen
    result += f"{CSI}3J"
    result += f"{CSI}1;1H"
    # Get screen size
    width, height = shutil.get_terminal_size((80, 60))
    for first_row, second_row in zip(data[0::2], data[1::2]):
        for _, first, second in zip(range(width), first_row, second_row):
            b1, g1, r1, a1 = first
            b2, g2, r2, a2 = second
            result += f"{CSI}38;2;{r1:03};{g1:03};{b1:03}m"
            result += f"{CSI}48;2;{r2:03};{g2:03};{b2:03}m"
            result += UPPER_HALF_BLOCK
        result += f"{CSI}0m\n"
    return result


def main(arg):

    # Load the rom
    gb = GB()
    return_code = gb.load(arg)
    if return_code != 0:
        exit(return_code)

    # Prepare buffer
    video = np.zeros((144, 160, 4), np.uint8)
    audio = np.zeros(2 * 35112, np.uint32)
    # data = bytearray(441226)

    # Loop over frames
    deltas = deque(maxlen=60)
    deltas1 = deque(maxlen=60)
    deltas2 = deque(maxlen=60)
    start = time.time()
    for i in count():

        # Tick
        offset, samples = gb.runFor(video, 160, audio, 2 * 35112)
        deltas1.append(time.time() - start)
        assert offset > 0
        data = paint_frame(video)
        deltas2.append(time.time() - start)
        print(data)

        # Time control
        stop = time.time()
        start, delta = stop, stop - start
        deltas.append(delta)

        # Print FPS
        if i % 60 == 0:
            avg = len(deltas) / sum(deltas)
            part1 = sum(deltas1) / sum(deltas) * 100
            part2 = (sum(deltas2) - sum(deltas1)) / sum(deltas) * 100
            part3 = (sum(deltas) - sum(deltas2)) / sum(deltas) * 100
            print(
                f"\x1b]0;FPS: {avg:.1f} - {part1:.1f} {part2:.1f} {part3:.1f}\x07",
                end="",
                flush=True
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Gambatte terminal frontend')
    parser.add_argument('romfile', metavar='ROM', type=str)
    args = parser.parse_args()
    main(args.romfile)
