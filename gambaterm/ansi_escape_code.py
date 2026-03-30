from __future__ import annotations

import sys
from itertools import count
from enum import Enum, auto
from dataclasses import dataclass
from string import ascii_lowercase, ascii_uppercase
from typing import Callable, Generator, TypeAlias, TypeVar, cast

import asyncssh
from asyncssh import SSHServerProcess

T = TypeVar("T")


class SupportStatus(Enum):
    Supported = auto()
    Unsupported = auto()
    Undecided = auto()

    def is_supported(self) -> bool:
        return self == SupportStatus.Supported


@dataclass
class CSI:
    code: str
    payload: str

    CHAR = "["
    CODES = r"@[\]^_`{|}~"
    CODES += ascii_uppercase
    CODES += ascii_lowercase

    def raw(self) -> str:
        return f"\033{self.CHAR}{self.payload}{self.code}"


@dataclass
class OSC:
    payload: str

    CHAR = "]"
    BELL = "\x07"
    ESC_ST = "\x5c"
    SINGLE_ST = "\x9c"

    def raw(self) -> str:
        return f"\033{self.CHAR}{self.payload}{self.BELL}"


@dataclass
class DCS:
    payload: str

    CHAR = "P"
    ESC_ST = "\x5c"
    SINGLE_ST = "\x9c"

    def raw(self) -> str:
        return f"\033{self.CHAR}{self.payload}\033{self.ESC_ST}"


EscapeCode: TypeAlias = CSI | OSC | DCS
Ready: TypeAlias = list[EscapeCode | str]


def parse_ansi_escape_code() -> Generator[Ready, str, None]:
    # Initialize result list
    ready: Ready = []

    # Get first data
    data = yield ready

    # Loop over ansi escape code
    while True:
        # Wait for escape
        while "\033" not in data:
            if data:
                ready.append(data)
            data = yield ready
            ready = []

        # Split the data
        before, data = data.split("\033", maxsplit=1)
        if before:
            ready.append(before)

        # Wait for new data if necessary
        while not data:
            data = yield ready
            ready = []

        # Match code
        code = data[0]
        if code == CSI.CHAR:
            data, ready = yield from parse_csi(data, ready)
        elif code == OSC.CHAR:
            data, ready = yield from parse_osc(data, ready)
        elif code == DCS.CHAR:
            data, ready = yield from parse_dcs(data, ready)
        else:
            ready.append("\033")


def parse_csi(
    data: str, ready: list[EscapeCode | str]
) -> Generator[Ready, str, tuple[str, Ready]]:
    # Loop over characters
    for i in count(1):
        # Get more data if necessary
        if i == len(data):
            data += yield ready
            ready = []
        char = data[i]

        # Check for stop code
        if char in CSI.CODES:
            ready.append(CSI(char, data[1:i]))
            return data[i + 1 :], ready

    assert False


def parse_osc(
    data: str, ready: list[EscapeCode | str]
) -> Generator[Ready, str, tuple[str, Ready]]:
    # Loop over characters
    for i in count(1):
        # Get more data if necessary
        if i == len(data):
            data += yield ready
            ready = []
        before = data[i - 1]
        char = data[i]

        # Check for double character stop code
        if before == "\033" and char == OSC.ESC_ST:
            ready.append(OSC(data[1 : i - 1]))
            return data[i + 1 :], ready

        # Check for single character stop code
        if char in (OSC.BELL, OSC.SINGLE_ST):
            ready.append(OSC(data[1:i]))
            return data[i + 1 :], ready

    assert False


def parse_dcs(
    data: str, ready: list[EscapeCode | str]
) -> Generator[Ready, str, tuple[str, Ready]]:
    # Loop over characters
    for i in count(1):
        # Get more data if necessary
        if i == len(data):
            data += yield ready
            ready = []
        before = data[i - 1]
        char = data[i]

        # Check for double character stop code
        if before == "\033" and char == DCS.ESC_ST:
            ready.append(DCS(data[1 : i - 1]))
            return data[i + 1 :], ready

        # Check for single character stop code
        if char == DCS.SINGLE_ST:
            ready.append(DCS(data[1:i]))
            return data[i + 1 :], ready

    assert False


def detect_keyboard_protocol_support_parser() -> (
    Generator[str | None, str, SupportStatus]
):
    # Query the keyboard protocol flags
    command = "\033[?u"
    # Query primary device attributes
    command += "\033[c"
    # Send command
    data = yield command
    # Prepare coroutine
    coro = parse_ansi_escape_code()
    assert not next(coro)
    # Loop over characters
    result = SupportStatus.Unsupported
    while True:
        ready = coro.send(data)
        for item in ready:
            if isinstance(item, CSI):
                if item.code == "c":
                    return result
                if item.code == "u":
                    result = SupportStatus.Supported
        data = yield None


async def run_parser_in_ssh_server_process(
    process: SSHServerProcess[str],
    parser: Callable[[], Generator[str | None, str, T]],
) -> T:
    coro = parser()
    command = next(coro)
    assert isinstance(command, str)
    process.stdout.write(command)
    await process.stdout.drain()

    # Loop until stop iteration
    try:
        while True:
            try:
                char = await process.stdin.read(1)
            except asyncssh.TerminalSizeChanged:
                continue
            else:
                command = coro.send(char)
                if command is not None:
                    process.stdout.write(command)
                    await process.stdout.drain()

    # Get the result
    except StopIteration as exc:
        return cast("T", exc.value)


def main() -> None:
    """Entry point to test terminal capabilities."""
    from blessed import Terminal

    from .colors import detect_local_color_mode

    if not sys.stdin.isatty():
        print("Stdin is not a tty")
        sys.exit(1)

    term = Terminal()
    color_mode = detect_local_color_mode(term)
    kitty_state = term.get_kitty_keyboard_state()

    print(f"Color mode        : {color_mode.name.lower()}")
    print(f"Keyboard protocol : {'supported' if kitty_state is not None else 'unsupported'}")


if __name__ == "__main__":
    main()
