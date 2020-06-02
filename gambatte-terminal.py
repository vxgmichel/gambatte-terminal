#!/usr/bin/env python3

import sys
import time
import shutil
import argparse
from collections import deque
from itertools import count
from functools import lru_cache

import numpy as np

from _gambatte import GB

CSI = b"\033["
UPPER_HALF_BLOCK = "\u2580".encode()
LOWER_HALF_BLOCK = "\u2584".encode()

TEMPLATE_FG = CSI + b"38;2;%d;%d;%dm"
TEMPLATE_BG = CSI + b"48;2;%d;%d;%dm"



@lru_cache(maxsize=None)
def set_color(n, foreground):
    b = n & 0xff
    g = (n >> 8) & 0xff
    r = (n >> 16) & 0xff
    template = TEMPLATE_FG if foreground else TEMPLATE_BG
    return template % (r, g, b)


@lru_cache(maxsize=None)
def move_absolute(x, y):
    if x == 1 and y == 1:
        return CSI + b"H"
    if y == 1:
        return CSI + b"%dH" % y
    if x == 1:
        return CSI + b";%dH" % y
    return CSI + b"%d;%dH" % (x, y)


@lru_cache(maxsize=None)
def move_relative(dx, dy):
    result = b""
    # Vertical move
    if dx < -1:
        result += CSI + b"%dA" % abs(dx)
    elif dx == -1:
        result += CSI + b"A"
    elif dx == 1:
        result += CSI + b"B"
    elif dx > 1:
        result += CSI + b"%dB" % dx
    # Horizontal move
    if dy < -1:
        result += CSI + b"%dD" % abs(dy)
    elif dy == -1:
        result += CSI + b"D"
    elif dy == 1:
        result += CSI + b"C"
    elif dy > 1:
        result += CSI + b"%dC" % dy
    return result


def from_to(from_x, from_y, to_x, to_y):
    return move_relative(to_x - from_x, to_y - from_y)


def paint_frame(video, last, refx, refy, width, height):
    result = [move_absolute(refx, refy)]
    current_x, current_y = refx, refy
    current_fg = current_bg = None
    for row_index in range(min(height - refx, 144 // 2)):
        for column_index in range(min(width - refy, 160)):

            # Extract colors
            color1 = video[2 * row_index + 0, column_index]
            color2 = video[2 * row_index + 1, column_index]

            # Skip if identical to last printed frame
            if (
                last is not None and
                last[2 * row_index + 0, column_index] == color1 and
                last[2 * row_index + 1, column_index] == color2
            ):
                continue

            # Go to the new position
            new_x, new_y = row_index + refx, column_index + refy
            result.append(from_to(current_x, current_y, new_x, new_y))
            current_x, current_y = new_x, new_y

            # Regular print
            if (
                current_fg == color1 or current_bg == color2 or
                current_fg != color2 and current_bg != color1
            ):
                half_block = UPPER_HALF_BLOCK

            # Inverted print
            else:
                half_block = LOWER_HALF_BLOCK
                color1, color2 = color2, color1

            # Set background and foreground colors if necessary
            if current_fg != color1:
                result.append(set_color(color1, True))
                current_fg = color1
            if current_bg != color2:
                result.append(set_color(color2, False))
                current_bg = color2

            # Print half_block
            result.append(half_block)
            current_y += 1

    return b"".join(result)


def main(arg, test=False):

    # Load the rom
    gb = GB()
    return_code = gb.load(arg)
    if return_code != 0:
        exit(return_code)

    # Prepare buffer
    video = np.zeros((144, 160), np.uint32)
    audio = np.zeros(2 * 35112, np.uint32)

    # Print area
    refx, refy = 1, 1
    width, height = shutil.get_terminal_size((80, 60))

    # Clear screen
    sys.stdout.buffer.write(CSI + b"2J")

    # Blink off
    sys.stdout.buffer.write(CSI + b"25m")

    # Loop over frames
    last_frame = None
    average_over = 30  # frames
    deltas = deque(maxlen=average_over)
    deltas1 = deque(maxlen=average_over)
    deltas2 = deque(maxlen=average_over)
    deltas3 = deque(maxlen=average_over)
    data_length = deque(maxlen=average_over)
    start = time.time()
    for i in count():
        # Break after 30 seconds
        if test and i == 30*60:
            sys.stdout.buffer.write(CSI + b"0m\n")
            breakpoint()
            break

        # Tick the emulator
        offset, samples = gb.runFor(video, 160, audio, 2 * 35112)
        assert offset > 0

        # Skip every other frame
        if i % 2:
            continue

        # Display frame
        deltas1.append(time.time() - start)
        data = paint_frame(video, last_frame, refx, refy, width, height)
        last_frame = video.copy()
        deltas2.append(time.time() - start)
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()
        data_length.append(len(data))
        deltas3.append(time.time() - start)

        # Time control
        stop = time.time()
        deadline = start + 1/30
        if stop < deadline and not test:
            time.sleep(deadline - stop)
            stop = time.time()
        start, delta = stop, stop - start
        deltas.append(delta)

        # Print FPS
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Gambatte terminal frontend')
    parser.add_argument('romfile', metavar='ROM', type=str)
    parser.add_argument('--test', '-t', action='store_true')
    args = parser.parse_args()
    main(args.romfile, args.test)
