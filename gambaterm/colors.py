from __future__ import annotations

import os
import sys
from enum import IntEnum

from blessed import Terminal

# Terminals that support at least 16 colors but may not be detected
# correctly by curses/terminfo.
BASIC_TERMINALS = [
    "screen",
    "vt100",
    "vt220",
    "rxvt",
    "color",
    "ansi",
    "cygwin",
    "linux",
]


class ColorMode(IntEnum):
    NO_COLOR = 0
    HAS_2_BIT_COLOR = 1
    HAS_4_BIT_COLOR = 2
    HAS_8_BIT_COLOR = 3
    HAS_24_BIT_COLOR = 4


def detect_color_mode(env: dict[str, str]) -> ColorMode:
    """Detect color support from environment variables.

    Assumes 24-bit color for all terminals except TERM='ansi' which
    gets 16 colors.

    :param env: environment dict with keys like TERM
    :returns: detected :class:`ColorMode`
    """
    term_val = env.get("TERM", "").lower()
    if term_val == "ansi":
        return ColorMode.HAS_4_BIT_COLOR
    return ColorMode.HAS_24_BIT_COLOR


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
    # Fallback for terminals that curses/terminfo under-reports
    term_env = os.environ.get("TERM", "").lower()
    if any(x in term_env for x in BASIC_TERMINALS):
        return ColorMode.HAS_4_BIT_COLOR
    return ColorMode.NO_COLOR


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
