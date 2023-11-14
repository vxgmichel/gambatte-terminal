from __future__ import annotations

import os
import time
from enum import IntEnum

from prompt_toolkit.application import AppSession

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


def detect_local_color_mode(
    app_session: AppSession,
    environ: dict[str, str] | None = None,
    timeout: float = 0.1,
) -> ColorMode:
    if detect_true_color_support(app_session, timeout):
        return ColorMode.HAS_24_BIT_COLOR
    if environ is None:
        environ = dict(os.environ)
    return detect_color_mode(environ)


def detect_color_mode(env: dict[str, str]) -> ColorMode:
    # Extract interesting variables
    term = env.get("TERM", "").lower()
    colorterm = env.get("COLORTERM", "").lower()
    term_program = env.get("TERM_PROGRAM", "").lower()
    term_program_version = env.get("TERM_PROGRAM_VERSION", "").lower()
    con_emu_ansi = env.get("ConEmuANSI", "").lower()
    # True color, says $COLORTERM
    if "truecolor" in colorterm or "24bit" in colorterm:
        return ColorMode.HAS_24_BIT_COLOR
    # Windows
    if con_emu_ansi == "on":
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


def detect_true_color_support(app_session: AppSession, timeout: float = 0.1) -> bool:
    # Set unlikely RGB value
    app_session.output.write_raw("\033[48:2:1:2:3m")
    # Query current configuration using a DECRQSS request
    app_session.output.write_raw("\033P$qm\033\\")
    # Reset
    app_session.output.write_raw("\033[m")
    # Flush
    app_session.output.flush()
    # Wait for reply
    data = ""
    deadline = time.time() + timeout
    while "\033\\" not in data and time.time() < deadline:
        keys = app_session.input.read_keys()
        data += "".join(x.data for x in keys)
        time.sleep(0.01)
    # Return whether true color is supported
    return "P1$r" in data and "48:2" in data and "1:2:3m" in data
