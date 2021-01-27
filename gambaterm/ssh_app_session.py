"""
Provide an async context manager to create a prompt-toolkit app session
from an AsyncSSH process.
"""

import os
from contextlib import asynccontextmanager, contextmanager

from prompt_toolkit.data_structures import Size
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output.vt100 import Vt100_Output
from prompt_toolkit.application.current import create_app_session


class StdoutFromProcess:
    def __init__(self, process):
        self._r, self._w = os.pipe()
        self.process = process

    def write(self, data):
        os.write(self._w, data.replace(b"\n", b"\r\n"))

    def isatty(self) -> bool:
        return True

    def flush(self):
        pass

    def get_size(self):
        width, height, _, _ = self.process.get_terminal_size()
        return Size(rows=height, columns=width)

    def fileno(self):
        return self._w

    @property
    def encoding(self):
        return self.process._encoding


async def vt100_output_from_process(process):
    stdout = StdoutFromProcess(process)
    term = process.get_terminal_type()
    vt100_output = Vt100_Output(stdout, stdout.get_size, term=term, write_binary=True)
    await process.redirect_stdout(stdout._r)
    return vt100_output


async def vt100_input_from_process(process):
    vt100_input = create_pipe_input()
    await process.redirect_stdin(vt100_input._w)
    return vt100_input


@contextmanager
def disable_line_mode(process):
    line_mode_enabled = (
        hasattr(process._chan, "set_line_mode") and process._chan._editor is not None
    )
    if line_mode_enabled:
        process._chan.set_line_mode(False)
    try:
        yield
    finally:
        if line_mode_enabled:
            process._chan.set_line_mode(True)


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
    vt100_input = await vt100_input_from_process(process)
    vt100_output = await vt100_output_from_process(process)
    with disable_line_mode(process):
        with create_app_session(input=vt100_input, output=vt100_output) as app_session:
            with bind_resize_process_to_app_session(process, app_session):
                yield app_session
