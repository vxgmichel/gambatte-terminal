"""
Provide paced output forwarding and terminal setup for the telnet server.
"""
from __future__ import annotations

import os
import socket
import asyncio
from contextlib import contextmanager
from typing import TYPE_CHECKING, Callable, Iterator, TypeVar
from concurrent.futures import ThreadPoolExecutor

if TYPE_CHECKING:
    from telnetlib3.stream_writer import TelnetWriter
    from telnetlib3.stream_reader import TelnetReader

from .remote_terminal import RemoteTerminal

T = TypeVar("T")


def set_tcp_nodelay(writer: TelnetWriter) -> None:
    """Set TCP_NODELAY on the telnet socket to disable Nagle's algorithm."""
    transport = getattr(writer, "transport", None)
    if transport is None:
        return
    sock = transport.get_extra_info("socket")
    if sock is not None:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)


async def paced_forward_output(
    read_fd: int,
    writer: TelnetWriter,
    fps: float = 60.0,
) -> None:
    """Read from a pipe and forward to the telnet writer at a paced rate.

    Accumulates data written to *read_fd* over each ``1/fps`` interval,
    then writes the batch to *writer* and drains.  Combined with
    ``TCP_NODELAY``, this produces roughly one TCP packet per interval.

    :param read_fd: read end of the output pipe
    :param writer: telnetlib3 writer
    :param fps: target packets per second
    """
    loop = asyncio.get_event_loop()
    reader = asyncio.StreamReader()
    read_file = os.fdopen(read_fd, "rb")
    transport, _ = await loop.connect_read_pipe(
        lambda: asyncio.StreamReaderProtocol(reader),
        read_file,
    )
    interval = 1.0 / fps
    try:
        while not reader.at_eof():
            deadline = loop.time() + interval
            buf = bytearray()
            while True:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    break
                try:
                    chunk = await asyncio.wait_for(
                        reader.read(65536), timeout=remaining
                    )
                    if not chunk:
                        if buf:
                            writer.write(bytes(buf))
                            await writer.drain()
                        return
                    buf.extend(chunk)
                except asyncio.TimeoutError:
                    break
            if buf:
                writer.write(bytes(buf))
                await writer.drain()
    except (ConnectionResetError, BrokenPipeError, EOFError):
        pass
    finally:
        transport.close()


@contextmanager
def bind_resize_telnet(
    writer: TelnetWriter,
    term: RemoteTerminal,
) -> Iterator[None]:
    """Hook telnetlib3 NAWS callbacks to update RemoteTerminal size.

    telnetlib3 dispatches NAWS via a callback registry on the writer
    (``_ext_callback[NAWS]``), not through ``protocol.on_naws`` directly.
    We must use ``writer.set_ext_callback`` to intercept it.
    """
    from telnetlib3.telopt import NAWS

    original_on_naws = writer.protocol.on_naws

    def on_naws(rows: int, cols: int) -> None:
        original_on_naws(rows, cols)
        term.update_size(rows, cols)

    try:
        writer.set_ext_callback(NAWS, on_naws)
        yield
    finally:
        writer.set_ext_callback(NAWS, original_on_naws)


async def async_reader_to_sync_pipe(reader: TelnetReader, write_fd: int) -> None:
    loop = asyncio.get_running_loop()
    pipe_file = os.fdopen(write_fd, "wb", buffering=0)
    transport, protocol = await loop.connect_write_pipe(
        lambda: asyncio.streams.FlowControlMixin(), pipe_file
    )
    writer = asyncio.StreamWriter(transport, protocol, None, loop)

    try:
        while True:
            data = await reader.read(4096)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    finally:
        writer.close()


async def telnet_to_terminal(
    reader: TelnetReader,
    writer: TelnetWriter,
    executor: ThreadPoolExecutor,
    target: Callable[[RemoteTerminal], T],
) -> T:
    """Create a RemoteTerminal and run *target* in a thread executor.

    Sets up a pipe for output forwarding with paced delivery at 60 pps.

    :param writer: telnetlib3 writer
    :param executor: ThreadPoolExecutor for running the game thread
    :param target: callable receiving the RemoteTerminal, run in executor
    :param input_read_fd: read end of the input pipe (keyboard_fd for blessed)
    :returns: return value of *target*
    """
    cols = writer.get_extra_info("cols") or 80
    rows = writer.get_extra_info("rows") or 24

    forward_read_fd, forward_write_fd = os.pipe()
    forward_task: asyncio.Task[None] | None = None

    input_read_fd, input_write_fd = os.pipe()
    input_task: asyncio.Task[None] | None = None

    def _target() -> T:
        try:
            with open(forward_write_fd, "w", newline="\r\n") as stream:
                telnet_term = RemoteTerminal(
                    stream=stream,
                    keyboard_fd=input_read_fd,
                    rows=rows,
                    columns=cols,
                )
                with bind_resize_telnet(writer, telnet_term):
                    return target(telnet_term)
        finally:
            os.close(input_read_fd)

    loop = asyncio.get_running_loop()
    forward_task = asyncio.create_task(paced_forward_output(forward_read_fd, writer))
    input_task = asyncio.create_task(async_reader_to_sync_pipe(reader, input_write_fd))
    try:
        return await loop.run_in_executor(executor, _target)
    finally:
        # write_fd is closed by open(write_fd, "w").__exit__ in _target,
        # so forward_task will see EOF. Just wait for it to finish.
        try:
            await asyncio.wait_for(forward_task, timeout=2.0)
        except asyncio.TimeoutError:
            forward_task.cancel()
        try:
            input_task.cancel()
            await asyncio.wait_for(input_task, timeout=2.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            pass
