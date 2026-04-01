"""
Provide an async context manager to create a blessed RemoteTerminal
from an AsyncSSH process.
"""
from __future__ import annotations

import os
import asyncio
import subprocess
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager, contextmanager
from typing import AsyncIterator, Iterator, TypeVar, Callable

from asyncssh import SSHServerProcess

from .remote_terminal import RemoteTerminal

T = TypeVar("T")


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
        try:
            os.close(read_fd)
        except OSError:
            pass
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
        # The write end may already be closed by asyncssh
        try:
            os.close(write_fd)
        except OSError:
            pass
        try:
            os.close(read_fd)
        except OSError:
            pass
        await process.redirect_stdin(subprocess.PIPE)
        await asyncio.sleep(0)


@contextmanager
def _bind_resize(
    process: SSHServerProcess[str], ssh_term: RemoteTerminal
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
    target: Callable[[RemoteTerminal], T],
) -> T:
    """Create a blessed RemoteTerminal from an SSH process.

    Once the redirections are set up, I/O become synchronous,
    so we run the target function in a thread executor to avoid blocking the event loop
    """
    width, height, _, _ = process.get_terminal_size()
    if width == height == 0:
        width, height = 80, 24

    def _target() -> T:
        with open(write_fd, "w", newline="\r\n") as stream:
            ssh_term = RemoteTerminal(
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
