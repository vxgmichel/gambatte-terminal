from __future__ import annotations

from dataclasses import dataclass
import os
from enum import IntEnum
from typing import Generator
from string import ascii_lowercase, ascii_uppercase
from prompt_toolkit.application import AppSession
from .ansi_escape_code import (
    run_parser_in_app_session,
    detect_true_color_support_parser,
)

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
) -> ColorMode:
    if run_parser_in_app_session(
        app_session, detect_true_color_support_parser
    ).is_supported():
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


@dataclass
class CSI:
    code: str
    payload: str

    CODES = r"@[\]^_`{|}~"
    CODES += ascii_uppercase
    CODES += ascii_lowercase


@dataclass
class OSC:
    payload: str

    BELL = "\x07"
    ST1 = "\x5c"
    ST2 = "\x9c"


def parse_ansi_escape_code() -> Generator[CSI | OSC | None, str, None]:
    while True:
        while (yield None) == "\033":
            pass
        code = yield None
        if code == "[":
            yield from parse_csi()
        if code == "]":
            yield from parse_osc()


def parse_csi() -> Generator[CSI | OSC | None, str, None]:
    payload = ""
    while True:
        char = yield None
        if char in CSI.CODES:
            break
        payload += char
    yield CSI(char, payload)


def parse_osc() -> Generator[CSI | OSC | None, str, None]:
    payload = ""
    while True:
        char = yield None
        while char == "\033":
            extra = yield None
            if extra == OSC.ST1:
                break
            payload += char
            char = extra
        if char in (OSC.BELL, OSC.ST2):
            break
        payload += char
    yield OSC(payload)
