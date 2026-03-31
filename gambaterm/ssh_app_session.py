"""
Provide an async context manager to create a blessed SSHTerminal
from an AsyncSSH process.
"""
from __future__ import annotations

import os
import codecs
import asyncio
import contextlib
import subprocess
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager, contextmanager
from typing import AsyncIterator, Generator, IO, Iterator, TypeVar, Callable

from blessed import Terminal as BlessedTerminal
from blessed.terminal import WINSZ

from asyncssh import SSHServerProcess

T = TypeVar("T")


# Python's curses.setupterm() can only be called once per process — subsequent
# calls with a different terminal type are silently ignored. Since the SSH
# server handles multiple concurrent connections in threads, all SSHTerminal
# instances share whatever terminal type was initialized first by the local
# Terminal(). We hardcode 'xterm-256color' as the kind since:
#   1. It's universally compatible with modern terminals
#   2. We use standard VT100/ANSI escape codes directly, not terminfo caps
#   3. It avoids issues where the first SSH client's TERM value differs
SSH_TERMINAL_TYPE = "xterm-256color"


class SSHTerminal(BlessedTerminal):
    """A blessed Terminal subclass for SSH streams.

    Following the pattern from x84 (x84/terminal.py), this stubs raw/cbreak
    mode (SSH is already raw) and overrides size detection to use values
    provided by the SSH server.
    """

    def __init__(
        self,
        stream: IO[str],
        keyboard_fd: int,
        rows: int,
        columns: int,
    ) -> None:
        self._rows = rows
        self._columns = columns
        super().__init__(kind=SSH_TERMINAL_TYPE, stream=stream, force_styling=True)
        # Blessed only sets _keyboard_fd when stream is sys.__stdout__, so
        # for SSH pipes we must set it and initialize the decoder manually
        self._keyboard_fd = keyboard_fd  # type: ignore[assignment]
        self._keyboard_decoder = codecs.getincrementaldecoder("UTF-8")()

    @property
    def is_a_tty(self) -> bool:
        return True

    @contextlib.contextmanager
    def raw(self) -> Generator[None, None, None]:
        yield

    @contextlib.contextmanager
    def cbreak(self) -> Generator[None, None, None]:
        yield

    def _height_and_width(self) -> WINSZ:
        return WINSZ(
            ws_row=self._rows,
            ws_col=self._columns,
            ws_xpixel=0,
            ws_ypixel=0,
        )

    def update_size(self, rows: int, columns: int) -> None:
        self._rows = rows
        self._columns = columns


@asynccontextmanager
async def _output_pipe_from_process(
    process: SSHServerProcess[str],
) -> AsyncIterator[int]:
    """Create a pipe and redirect SSH stdout to the read end.

    Yields the write fd. Data written to write_fd flows through
    the pipe to the SSH client.
    """
    read_fd, write_fd = os.pipe()
    await process.redirect_stdout(read_fd)
    try:
        yield write_fd
    finally:
        await process.redirect_stdout(subprocess.PIPE)
        await asyncio.sleep(0)


@asynccontextmanager
async def _input_pipe_from_process(
    process: SSHServerProcess[str],
) -> AsyncIterator[int]:
    """Create a pipe and redirect SSH stdin to the write end.

    Yields the read fd. Data from the SSH client flows through
    the pipe and can be read from read_fd.
    """
    read_fd, write_fd = os.pipe()
    await process.redirect_stdin(write_fd)
    try:
        yield read_fd
    finally:
        await process.redirect_stdin(subprocess.PIPE)
        await asyncio.sleep(0)


@contextmanager
def _bind_resize(
    process: SSHServerProcess[str], ssh_term: SSHTerminal
) -> Iterator[None]:
    original_method = process.terminal_size_changed

    def terminal_size_changed(
        width: int, height: int, pixwidth: int, pixheight: int
    ) -> None:
        ssh_term.update_size(rows=height, columns=width)
        return original_method(width, height, pixheight, pixwidth)

    try:
        process.terminal_size_changed = terminal_size_changed  # type: ignore[method-assign]
        yield
    finally:
        del process.terminal_size_changed


async def process_to_terminal(
    process: SSHServerProcess[str],
    executor: ThreadPoolExecutor,
    target: Callable[[SSHTerminal], T],
) -> T:
    """Create a blessed SSHTerminal from an SSH process.

    Once the redirections are set up, I/O become synchronous,
    so we run the target function in a thread executor to avoid blocking the event loop
    """
    width, height, _, _ = process.get_terminal_size()
    if width == height == 0:
        width, height = 80, 24

    def _target() -> T:
        with open(write_fd, "w", newline="\r\n") as stream:
            ssh_term = SSHTerminal(
                stream=stream,
                keyboard_fd=keyboard_fd,
                rows=height,
                columns=width,
            )
            with _bind_resize(process, ssh_term):
                return target(ssh_term)

    loop = asyncio.get_running_loop()

    async with _input_pipe_from_process(process) as keyboard_fd:
        async with _output_pipe_from_process(process) as write_fd:
            return await loop.run_in_executor(executor, _target)
