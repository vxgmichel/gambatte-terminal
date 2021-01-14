import os
from enum import IntEnum

BASIC_TERMINALS = [
    "screen",
    "xterm",
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


def detect_local_color_mode():
    return detect_color_mode(os.environ)


def detect_color_mode(env):
    # Extract interesting variables
    term = env.get("TERM", "").lower()
    colorterm = env.get("COLORTERM", "").lower()
    term_program = env.get("TERM_PROGRAM", "").lower()
    term_program_version = env.get("TERM_PROGRAM_VERSION", "").lower()
    # True color, says $COLORTERM
    if "truecolor" in colorterm or "24bit" in colorterm:
        return ColorMode.HAS_24_BIT_COLOR
    # Apple terminal
    if term_program == "apple_terminal":
        return ColorMode.HAS_8_BIT_COLOR
    # iTerm app terminal
    if term_program == "iterm.app":
        try:
            version = int(term_program_version.split(".")[0])
        except ValueError:
            return ColorMode.HAS_8_BIT_COLOR
        return ColorMode.HAS_8_BIT_COLOR if version < 3 else ColorMode.HAS_24_BIT_COLOR
    # 256 colors, says $TERM or $COLORTERM
    if "256" in term or "256" in colorterm:
        return ColorMode.HAS_8_BIT_COLOR
    # Basic terminal, says $TERM
    if any(x in term for x in BASIC_TERMINALS):
        return ColorMode.HAS_4_BIT_COLOR
    # Basic color, says $COLORTERM
    if colorterm:
        return ColorMode.HAS_4_BIT_COLOR
    # Does not support color apparently
    return ColorMode.NO_COLOR
