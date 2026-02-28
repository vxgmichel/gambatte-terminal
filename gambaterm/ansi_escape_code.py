import sys
from enum import StrEnum, auto
from dataclasses import dataclass
from string import ascii_lowercase, ascii_uppercase
from typing import Callable, Generator, TypeAlias, TypeVar, cast

from asyncssh import SSHServerProcess
import asyncssh
from prompt_toolkit.application import AppSession, create_app_session

T = TypeVar("T")


class SupportStatus(StrEnum):
    Supported = auto()
    Unsupported = auto()
    Undecided = auto()

    def is_supported(self) -> bool:
        return self == SupportStatus.Supported


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


@dataclass
class DCS:
    payload: str

    ST1 = "\x5c"
    ST2 = "\x9c"


EscapeCode: TypeAlias = CSI | OSC | DCS


def parse_ansi_escape_code() -> Generator[EscapeCode | None, str, None]:
    ready: EscapeCode | None = None
    while True:
        char = yield ready
        while char != "\033":
            char = yield None
        code = yield None
        if code == "[":
            ready = yield from parse_csi()
        elif code == "]":
            ready = yield from parse_osc()
        elif code == "P":
            ready = yield from parse_dcs()
        else:
            ready = None


def parse_csi() -> Generator[None, str, CSI]:
    payload = ""
    while True:
        char = yield None
        if char in CSI.CODES:
            break
        payload += char
    return CSI(char, payload)


def parse_osc() -> Generator[None, str, OSC]:
    payload = ""
    while True:
        char = yield None
        while char == "\033":
            extra = yield None
            if extra == OSC.ST1:
                return OSC(payload)
            payload += char
            char = extra
        if char in (OSC.BELL, OSC.ST2):
            return OSC(payload)
        payload += char


def parse_dcs() -> Generator[None, str, DCS]:
    payload = ""
    while True:
        char = yield None
        while char == "\033":
            extra = yield None
            if extra == OSC.ST1:
                return DCS(payload)
            payload += char
            char = extra
        if char == OSC.ST2:
            return DCS(payload)
        payload += char


def detect_true_color_support_with_DCS() -> Generator[str | None, str, SupportStatus]:
    """
    This detection is restrictive, i.e it has not known positive
    However, it falsely reports no support for gnome terminal
    """
    # Set unlikely RGB value
    command = "\033[48;2;1;2;3m"
    # Query current configuration
    command += "\033P$qm\033\\"
    # Reset
    command += "\033[m"
    # Query primary device attributes
    command += "\033[c"
    # Send command
    char = yield command
    # Prepare coroutine
    coro = parse_ansi_escape_code()
    assert next(coro) is None
    # Loop over characters
    result = SupportStatus.Undecided
    while True:
        item = coro.send(char)
        if isinstance(item, CSI):
            if item.code == "c":
                return result
        if isinstance(item, DCS):
            if item.payload.endswith(":1:2:3m"):
                result = SupportStatus.Supported
        char = yield None


def detect_true_color_support_with_OSC() -> Generator[str | None, str, SupportStatus]:
    """
    This detection is too permissive, i.e. it has no known false negative.
    However, it falsely reports support for rxvt-unicode
    """
    # Get color at slot 255
    command = "\033]4;255;?\033\\"
    # Query primary device attributes
    command += "\033[c"
    # Send command
    char = yield command
    # Prepare coroutine
    coro = parse_ansi_escape_code()
    assert next(coro) is None
    # Loop over characters
    result = SupportStatus.Unsupported
    while True:
        item = coro.send(char)
        if isinstance(item, CSI):
            if item.code == "c":
                return result
        if isinstance(item, OSC):
            if "rgb" in item.payload:
                result = SupportStatus.Undecided
        char = yield None


def detect_true_color_support_parser() -> Generator[str | None, str, SupportStatus]:
    permissive_status = yield from detect_true_color_support_with_OSC()
    if permissive_status == SupportStatus.Unsupported:
        return permissive_status
    restrictive_status = yield from detect_true_color_support_with_DCS()
    if restrictive_status == SupportStatus.Supported:
        return restrictive_status
    return SupportStatus.Undecided


def detect_keyboard_protocol_support_parser() -> (
    Generator[str | None, str, SupportStatus]
):
    # Query the keyboard protocol flags
    command = "\033[?u"
    # Query primary device attributes
    command += "\033[c"
    # Send command
    char = yield command
    # Prepare coroutine
    coro = parse_ansi_escape_code()
    assert next(coro) is None
    # Loop over characters
    result = SupportStatus.Unsupported
    while True:
        item = coro.send(char)
        if isinstance(item, CSI):
            if item.code == "c":
                return result
            if item.code == "u":
                result = SupportStatus.Supported
        char = yield None


def run_parser_in_app_session(
    app_session: AppSession, parser: Callable[[], Generator[str | None, str, T]]
) -> T:
    coro = parser()
    command = next(coro)
    assert isinstance(command, str)
    app_session.output.write_raw(command)
    app_session.output.flush()

    # Loop until stop iteration
    try:
        while True:
            # Get next key
            for key in app_session.input.read_keys():
                if key.key == "c-c":
                    raise KeyboardInterrupt

                # Send each char of the key into the coroutine
                for char in key.data:
                    command = coro.send(char)

                    # Send extra command
                    if command is not None:
                        app_session.output.write_raw(command)
                        app_session.output.flush()

    # Get the result
    except StopIteration as exc:
        return cast("T", exc.value)


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
    """Entry point to test terminal capabilites."""

    # Check that stdin is a tty
    if not sys.stdin.isatty():
        print("Stdin is not a tty")
        exit(1)

    # Use prompt-toolkit to enable raw mode
    with create_app_session() as app_session:
        with app_session.input.raw_mode():
            true_color_status = run_parser_in_app_session(
                app_session, detect_true_color_support_parser
            )
            keyboard_protocol_status = run_parser_in_app_session(
                app_session, detect_keyboard_protocol_support_parser
            )

    # Print the results
    print(f"True color mode   : {true_color_status.value}")
    print(f"Keyboard terminal : {keyboard_protocol_status.value}")


if __name__ == "__main__":
    main()
