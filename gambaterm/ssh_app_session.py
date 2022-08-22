"""
Provide an async context manager to create a prompt-toolkit app session
from an AsyncSSH process.
"""

import os
import asyncio
import subprocess
from contextlib import asynccontextmanager, contextmanager

from prompt_toolkit.data_structures import Size
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output.vt100 import Vt100_Output
from prompt_toolkit.application.current import create_app_session


@asynccontextmanager
async def vt100_output_from_process(process):
    def get_size():
        width, height, _, _ = process.get_terminal_size()
        return Size(rows=height, columns=width)

    term = process.get_terminal_type()
    read_fd, write_fd = os.pipe()
    with open(write_fd, "w", newline="\r\n") as stdout:
        vt100_output = Vt100_Output(stdout, get_size, term=term)
        await process.redirect_stdout(read_fd)
        try:
            yield vt100_output
        finally:
            await process.redirect_stdout(subprocess.PIPE)
            await asyncio.sleep(0)  # Let the loop remove the file descriptor


@asynccontextmanager
async def vt100_input_from_process(process):
    with create_pipe_input() as vt100_input:
        await process.redirect_stdin(vt100_input.pipe.write_fd)
        try:
            yield vt100_input
        finally:
            # Prevent vt100_input.pipe.close from failing with an OSError
            # as the write end of the pipe has already been closed by asyncssh
            vt100_input.pipe._write_closed = True
            await process.redirect_stdin(subprocess.PIPE)
            await asyncio.sleep(0)  # Let the loop remove the file descriptor


@contextmanager
def disable_editor(process):
    process.channel.set_line_mode(False)
    original_editor = process.channel._editor
    process.channel._editor = None
    try:
        yield
    finally:
        process.channel._editor = original_editor


@contextmanager
def bind_resize_process_to_app_session(process, app_session):
    original_method = process.terminal_size_changed

    def terminal_size_changed(*args):
        if app_session.app is not None:
            app_session.app._on_resize()
        return original_method(*args)

    try:
        process.terminal_size_changed = terminal_size_changed
        yield
    finally:
        del process.terminal_size_changed


@asynccontextmanager
async def process_to_app_session(process):
    async with vt100_input_from_process(process) as vt100_input:
        async with vt100_output_from_process(process) as vt100_output:
            with disable_editor(process):
                with create_app_session(
                    input=vt100_input, output=vt100_output
                ) as app_session:
                    with bind_resize_process_to_app_session(process, app_session):
                        yield app_session
