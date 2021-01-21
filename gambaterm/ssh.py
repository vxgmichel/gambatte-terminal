import os
import asyncio
import argparse
import tempfile
import traceback
from pathlib import Path

import asyncssh

from .run import run
from .inputs import read_input_file
from .xinput import gb_input_context
from .main import add_base_arguments
from .colors import ColorMode, detect_color_mode


CSI = b"\033["


class SSHSession(asyncssh.SSHServerSession):
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def connection_made(self, chan):
        self._read_stdin_pipe, self._write_stdin_pipe = os.pipe()
        self._read_stdout_pipe, self._write_stdout_pipe = os.pipe()
        self._stdin = os.fdopen(self._read_stdin_pipe, "rb", buffering=0)
        self._stdout = os.fdopen(self._write_stdout_pipe, "wb", buffering=0)
        self._channel = chan
        self._size = 10, 10

        # True color detection state
        self._true_color = False
        self._true_color_data = b""
        self._true_color_event = asyncio.Event()

    def close_all_pipes(self):
        for pipe in (
            self._read_stdin_pipe,
            self._write_stdin_pipe,
            self._read_stdout_pipe,
            self._write_stdout_pipe,
        ):
            try:
                os.close(pipe)
            except OSError:
                pass

    def shell_requested(self):
        return True

    def exec_requested(self, command):
        return True

    def session_started(self):
        asyncio.get_event_loop().create_task(self.safe_interact())

    async def safe_interact(self):
        try:
            await self.interact()
        except KeyboardInterrupt:
            pass
        except SystemExit:
            pass
        except BaseException:
            traceback.print_exc()
        finally:
            self.close_all_pipes()
            self._channel.close()

    async def interact(self):
        display = self._channel.get_x11_display()
        command = self._channel.get_command()
        connection = self._channel.get_extra_info("connection")
        username = self._channel.get_extra_info("username")
        peername, port = connection._transport.get_extra_info("peername")
        print(f"> User `{username}` is connected ({peername}:{port})")

        if command:
            romfile, *_ = command.split()
            self.kwargs["romfile"] = command

        # X11 is required
        if not display and self.kwargs["input_file"] is None:
            message = "Please enable X11 forwarding using `-X` option.\r\n"
            self._channel.write(message.encode())
            print(f"< User `{username}` did not enable X11 forwarding")
            return

        # Detect true color support by interracting with the terminal
        if await self.detect_true_color_support():
            self._color_mode = ColorMode.HAS_24_BIT_COLOR
        else:
            env = self._channel.get_environment()
            env["TERM"] = self._channel.get_terminal_type()
            self._color_mode = detect_color_mode(env)

        if self._color_mode == ColorMode.NO_COLOR:
            term = self._channel.get_terminal_type()
            message = f"Your terminal `{term}` doesn't seem to support colors\r\n"
            self._channel.write(message.encode())
            print(f"< User `{username}` terminal `{term}` does not support colors")
            return

        # Force size changed handler
        size = self._channel.get_terminal_size()
        self.terminal_size_changed(*size)

        def _data_received():
            try:
                data = os.read(self._read_stdout_pipe, 2 * 1024 * 1024)
            except OSError:
                return
            self._channel.write(data)

        loop = asyncio.get_event_loop()
        try:
            # Hide cursor and clear screen
            self._channel.write(CSI + b"?25l" + CSI + b"2J")
            loop.add_reader(self._read_stdout_pipe, _data_received)
            await loop.run_in_executor(None, self.thread_target, display)
        finally:
            loop.remove_reader(self._read_stdout_pipe)
            # Show cursor, clear attributes and clear screen
            self._channel.write(CSI + b"?25h" + CSI + b"0m" + CSI + b"2J" + b"\r\n")
            print(f"< User `{username}` left ({peername}:{port})")

    def thread_target(self, display):

        kwargs = {
            "romfile": self.kwargs["romfile"],
            "stdin": self._stdin,
            "stdout": self._stdout,
            "get_size": lambda: self._size,
            "color_mode": int(self._color_mode),
            "frame_advance": self.kwargs["frame_advance"],
            "break_after": self.kwargs["break_after"],
            "speed_factor": self.kwargs["speed_factor"],
            "force_gameboy": self.kwargs["force_gameboy"],
        }
        if self.kwargs["input_file"] is not None:
            get_input = read_input_file(
                self.kwargs["input_file"], self.kwargs["skip_inputs"]
            )
            run(
                get_input=get_input,
                save_directory=tempfile.mkdtemp(),
                **kwargs,
            )
        else:
            username = self._channel.get_extra_info("username")
            save_directory = Path("ssh_save") / username
            save_directory.mkdir(parents=True, exist_ok=True)
            with gb_input_context(display=display) as get_gb_input:
                run(
                    get_input=get_gb_input,
                    save_directory=str(save_directory),
                    **kwargs,
                )

    def terminal_size_changed(self, width, height, pixwidth, pixheight):
        self._size = width, height
        term = self._channel.get_terminal_type()
        username = self._channel.get_extra_info("username")
        color = "True color" if self._true_color else "256 colors"
        print(f"[Terminal Info] {username}: {term}, {color}, {width}x{height}")

    def data_received(self, data, datatype):
        # Detect True color mode
        if not self._true_color_event.is_set():
            self._true_color_data += data
            if b"\033\\" not in self._true_color_data:
                return
            header, data = self._true_color_data.split(b"\033\\", maxsplit=1)
            self._true_color = b"P1$r0;48:2::1:2:3m" in header
            self._true_color_event.set()
        # Forward traffic
        try:
            os.write(self._write_stdin_pipe, data)
        except OSError:
            pass

    async def detect_true_color_support(self):
        # Set unlikely RGB value
        self._channel.write(CSI + b"48:2:1:2:3m")
        # Query current configuration
        self._channel.write(b"\033P$qm\033\\")
        # Reset
        self._channel.write(CSI + b"m")
        # Wait for reply
        try:
            await asyncio.wait_for(self._true_color_event.wait(), 0.5)
        except asyncio.TimeoutError:
            pass
        # Return whether true color is supported
        return self._true_color


class SSHServer(asyncssh.SSHServer):
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def begin_auth(self, username):
        return True

    def session_requested(self):
        return SSHSession(**self.kwargs)

    def password_auth_supported(self):
        return self.kwargs.get("password")

    def validate_password(self, username, password):
        return password == self.kwargs.get("password")


async def run_server(bind="localhost", port=8022, **kwargs):
    user_private_key = str(Path("~/.ssh/id_rsa").expanduser())
    user_public_key = str(Path("~/.ssh/id_rsa.pub").expanduser())

    server = await asyncssh.create_server(
        lambda: SSHServer(**kwargs),
        bind,
        port,
        server_host_keys=[user_private_key],
        authorized_client_keys=user_public_key,
        x11_forwarding=True,
        encoding=None,
    )
    bind, port = server.sockets[0].getsockname()
    print(f"Running ssh server on {bind}:{port}...")

    while True:
        await asyncio.sleep(60)


def main(args=None):
    parser = argparse.ArgumentParser(description="Gambatte terminal front-end over ssh")
    add_base_arguments(parser)
    parser.add_argument(
        "--bind",
        "-b",
        type=str,
        default="localhost",
        help="Bind adress of the SSH server, use `0.0.0.0` for all interfaces",
    )
    parser.add_argument(
        "--port",
        "-p",
        type=int,
        default=8022,
        help="Port of the SSH server, default to 8022",
    )
    parser.add_argument(
        "--password",
        "-pw",
        type=str,
        help="Enable password authentification with the given global password",
    )

    args = parser.parse_args(args)
    kwargs = dict(args._get_kwargs())
    asyncio.run(run_server(**kwargs))


if __name__ == "__main__":
    main()
