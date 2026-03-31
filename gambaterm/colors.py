from __future__ import annotations

import sys
from enum import IntEnum

from blessed import Terminal


class ColorMode(IntEnum):
    COULD_NOT_DETECT = 0
    HAS_2_BIT_COLOR = 1
    HAS_4_BIT_COLOR = 2
    HAS_8_BIT_COLOR = 3
    HAS_24_BIT_COLOR = 4

    def cycle(self) -> ColorMode:
        """Cycle to the next color mode, for testing purposes."""
        value = (self + 1) % len(ColorMode)
        if value == ColorMode.COULD_NOT_DETECT:
            value += 1
        return ColorMode(value)


def detect_local_color_mode(term: Terminal) -> ColorMode:
    """Detect the color mode of the local terminal using blessed."""
    n = term.number_of_colors
    if n >= 1 << 24:
        return ColorMode.HAS_24_BIT_COLOR
    if n >= 256:
        return ColorMode.HAS_8_BIT_COLOR
    if n >= 16:
        return ColorMode.HAS_4_BIT_COLOR
    if n >= 4:
        return ColorMode.HAS_2_BIT_COLOR
    return ColorMode.COULD_NOT_DETECT


def main() -> None:
    """Entry point to test terminal capabilities."""

    if not sys.stdin.isatty():
        print("Stdin is not a tty")
        sys.exit(1)

    term = Terminal()
    color_mode = detect_local_color_mode(term)
    print(f"Color mode: {color_mode.name.lower()}")


if __name__ == "__main__":
    main()
