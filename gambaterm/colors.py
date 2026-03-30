from __future__ import annotations

import os
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
