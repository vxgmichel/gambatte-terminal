from __future__ import annotations

import os
import time
import asyncio
import argparse
import traceback
from pathlib import Path
from typing import IO, cast
from enum import Enum, auto
from concurrent.futures import ThreadPoolExecutor

import asyncssh
from asyncssh import SSHServerProcess
from blessed import Terminal

from .run import run
from .colors import ColorMode
from .file_input import console_input_from_file_context
from .keyboard_input import (
    console_input_from_x11_keyboard_context,
    console_input_from_keyboard_protocol_context,
    MESSAGE_SUGGESTING_KITTY_SUPPORT,
)
from .main import add_base_arguments, add_optional_arguments, AppConfig
from .console import Console, GameboyColor

from .ssh_app_session import process_to_terminal
from .ansi_escape_code import (
    detect_keyboard_protocol_support_parser,
    run_parser_in_ssh_server_process,
)


async def is_x11_display_functional(
    display: str,
    executor: ThreadPoolExecutor,
    timeout: float = 3.0,
) -> bool:
    from .x11_keyboard_input import is_x11_display_functional

    try:
        return await asyncio.wait_for(
            asyncio.get_running_loop().run_in_executor(
                executor, is_x11_display_functional, display
            ),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        return False


class InputSource(Enum):
    INPUT_FILE = auto()
    KEYBOARD_PROTOCOL = auto()
    X11 = auto()

    @classmethod
    async def detect(
        cls,
        app_config: AppConfig,
        process: SSHServerProcess[str],
        display: str | None,
        executor: ThreadPoolExecutor,
    ) -> InputSource | None:
        if app_config.input_file is not None:
            return InputSource.INPUT_FILE
        if await detect_keyboard_protocol_support(process):
            return InputSource.KEYBOARD_PROTOCOL
        if display and await is_x11_display_functional(display, executor):
            return InputSource.X11
        return None


async def detect_keyboard_protocol_support(
    process: SSHServerProcess[str],
    timeout: float = 1.0,
) -> bool:
    try:
        status = await asyncio.wait_for(
            run_parser_in_ssh_server_process(
                process, detect_keyboard_protocol_support_parser
            ),
            timeout,
        )
    except TimeoutError:
        return False
    else:
        return status.is_supported()


async def safe_ssh_process_handler(process: SSHServerProcess[str]) -> None:
    try:
        result = await ssh_process_handler(process)
    except KeyboardInterrupt:
        result = 1
    except SystemExit as e:
        if isinstance(e.code, int):
            result = e.code
        else:
            result = 1 if e.code else 0
    except BaseException:
        traceback.print_exc()
        result = 1
    return process.exit(result or 0)


async def ssh_process_handler(process: SSHServerProcess[str]) -> int:
    console_cls: type[Console] = process.get_extra_info("console_cls")
    namespace: argparse.Namespace = process.get_extra_info("namespace")
    executor: ThreadPoolExecutor = process.get_extra_info("executor")
    display = process.channel.get_x11_display()
    command = process.channel.get_command()
    terminal_type = process.get_terminal_type()
    connection = process.get_extra_info("connection")
    username = process.get_extra_info("username")
    peername, port = connection.get_extra_info("peername")
    print(f"> User `{username}` is connected ({peername}:{port})")

    # Copy namespace before mutating
    namespace = argparse.Namespace(**vars(namespace))

    # Check command
    if command is not None:
        parser = argparse.ArgumentParser()
        parser._print_message = lambda message, file=None: type(parser)._print_message(  # type: ignore[method-assign]
            parser, message, file=cast(IO[str], process.stdout)
        )
        add_optional_arguments(parser)
        console_cls.add_console_arguments(parser)
        namespace = parser.parse_args(command.split(), namespace)

    # Manage save directory
    if "save_directory" in namespace.__dict__:
        save_directory = (
            None
            if getattr(namespace, "input_file", False)
            else Path("ssh_save") / username
        )
        setattr(namespace, "save_directory", save_directory)

    # Pop console arguments and extract configuration
    console_callback = console_cls.pop_console_arguments(namespace)
    app_config = AppConfig(**vars(namespace))

    # Check terminal
    if terminal_type is None:
        print(
            "Please use a terminal to access the interactive interface.",
            "Use `-t` to force pseudo-terminal allocation if a command is provided.",
            sep="\r\n",
            file=process.stdout,
        )
        print(f"< User `{username}` did not use an interactive terminal")
        return 1

    # X11 or Kitty keyboard protocol is required
    input_source = await InputSource.detect(app_config, process, display, executor)
    if input_source is None:
        message = MESSAGE_SUGGESTING_KITTY_SUPPORT + '\n\n' + """\
Alternatively, X11 forwarding can be used in order to give the gambaterm-ssh
server access to your keyboard, eg. `ssh -Y -p 8022 localhost`.
===============================[ WARNING ]=====================================
Enabling X11 forwarding while connecting to an untrusted server can greatly
endanger your machine. Please only do so if you are running the X11 server in a
sandbox. More information here: https://security.stackexchange.com/a/7496
===============================[ WARNING ]=====================================
"""
        process.stdout.write(message.replace("\n", "\r\n"))
        print(
            f"< User `{username}` did not support keyboard protocol nor enable X11 forwarding"
        )
        return 1

    # Detect color support
    # Default to 24-bit color since the vast majority of modern terminals
    # support it. Check COLORTERM if forwarded (recommend SendEnv COLORTERM
    # in SSH client config), and fall back to env-based detection otherwise.
    if app_config.color_mode is not None:
        color_mode = app_config.color_mode
    else:
        color_mode = ColorMode.HAS_24_BIT_COLOR

    # Now is a good time to instanciate the console
    # (it might fail if the ROM does not exist for instance)
    console = console_callback()

    async with process_to_terminal(process) as term:
        loop = asyncio.get_event_loop()
        print(
            f"[Terminal Info] {username}: {terminal_type}, {input_source},"
            f" {color_mode}, {term.width}x{term.height}"
        )
        return await loop.run_in_executor(
            executor,
            thread_target,
            term,
            console,
            app_config,
            display,
            input_source,
            color_mode,
        )


def thread_target(
    term: Terminal,
    console: Console,
    app_config: AppConfig,
    display: str | None,
    input_source: InputSource,
    color_mode: ColorMode,
) -> int:
    if input_source == InputSource.INPUT_FILE:
        assert app_config.input_file is not None
        console_input_context = console_input_from_file_context(
            console, app_config.input_file, app_config.skip_inputs
        )
    elif input_source == InputSource.KEYBOARD_PROTOCOL:
        console_input_context = console_input_from_keyboard_protocol_context(
            console,
            term,
        )
    elif input_source == InputSource.X11:
        console_input_context = console_input_from_x11_keyboard_context(
            console, display
        )
    else:
        assert False

    try:
        # Prepare alternate screen
        term.stream.write(
            term.enter_fullscreen + term.clear + term.hide_cursor
        )
        term.stream.flush()

        with console_input_context as get_console_input:
            # Run the emulator
            run(
                console,
                get_input=get_console_input,
                term=term,
                frame_advance=app_config.frame_advance,
                color_mode=color_mode,
                break_after=app_config.break_after,
                speed_factor=app_config.speed_factor,
                use_cpr_sync=app_config.cpr_sync,
            )

    except (KeyboardInterrupt, OSError):
        return 0
    else:
        return 0
    finally:
        # Wait for CPR
        time.sleep(0.1)
        # Clear alternate screen
        term.stream.write(
            term.clear + term.exit_fullscreen + term.normal_cursor
        )
        # Flush if the connection is still active
        try:
            term.stream.flush()
        except BrokenPipeError:
            pass


class SSHServer(asyncssh.SSHServer):
    def __init__(
        self,
        password: str | None,
        console_cls: type[Console],
        namespace: argparse.Namespace,
        executor: ThreadPoolExecutor,
    ):
        self._gambaterm_console_cls = console_cls
        self._gambaterm_namespace = namespace
        self._gambaterm_executor = executor
        self._gambaterm_password = password

    def connection_made(self, conn: asyncssh.SSHServerConnection) -> None:
        conn.set_extra_info(console_cls=self._gambaterm_console_cls)
        conn.set_extra_info(executor=self._gambaterm_executor)
        conn.set_extra_info(namespace=self._gambaterm_namespace)

    def begin_auth(self, username: str) -> bool:
        return True

    def session_requested(self) -> SSHServerProcess[str]:
        return asyncssh.SSHServerProcess(
            safe_ssh_process_handler, sftp_factory=None, sftp_version=3, allow_scp=False
        )

    def password_auth_supported(self) -> bool:
        return bool(self._gambaterm_password)

    def validate_password(self, username: str, password: str) -> bool:
        assert self._gambaterm_password is not None
        return password == self._gambaterm_password


async def run_server(
    bind: str,
    port: int,
    password: str | None,
    console_cls: type[Console],
    namespace: argparse.Namespace,
    executor: ThreadPoolExecutor,
) -> None:
    ssh_key_dir = Path(os.environ.get("GAMBATERM_SSH_KEY_DIR", "~/.ssh"))
    user_private_key = (ssh_key_dir / "id_rsa").expanduser()
    user_public_key = (ssh_key_dir / "id_rsa.pub").expanduser()
    if not user_private_key.exists():
        raise SystemExit(
            f"The server requires a private RSA key to use as a host hey.\n"
            f"You may generate one by running the following command:\n\n"
            f"    ssh-keygen -f {ssh_key_dir / 'id_rsa'} -P ''\n"
        )
    server_host_keys = [str(user_private_key)]
    authorized_client_keys = []
    if user_public_key.exists():
        authorized_client_keys = [str(user_public_key)]

    # Remove chacha20 from encryption_algs because it's a bit too expensive
    encryption_algs = [
        # "chacha20-poly1305@openssh.com",
        "aes256-gcm@openssh.com",
        "aes128-gcm@openssh.com",
        "aes256-ctr",
        "aes192-ctr",
        "aes128-ctr",
    ]

    server = await asyncssh.create_server(
        lambda: SSHServer(password, console_cls, namespace, executor),
        bind,
        port,
        server_host_keys=server_host_keys,
        authorized_client_keys=authorized_client_keys,
        x11_forwarding=True,
        encryption_algs=encryption_algs,
        line_editor=False,
        reuse_address=True,
    )
    bind, port = server.sockets[0].getsockname()
    print(f"Running ssh server on {bind}:{port}...", flush=True)
    async with server:
        # Sleep forever
        await asyncio.Future()


def main(
    parser_args: tuple[str, ...] | None = None,
    console_cls: type[Console] = GameboyColor,
) -> None:
    parser = argparse.ArgumentParser(description="Gambatte terminal front-end over ssh")
    add_base_arguments(parser)
    add_optional_arguments(parser)
    console_cls.add_console_arguments(parser)
    parser.add_argument(
        "--bind",
        "-b",
        type=str,
        default="127.0.0.1",
        help="Bind adress of the SSH server, "
        "use `0.0.0.0` for all interfaces (default is localhost)",
    )
    parser.add_argument(
        "--port",
        "-p",
        type=int,
        default=8022,
        help="Port of the SSH server (default is 8022)",
    )
    parser.add_argument(
        "--password",
        "--pw",
        type=str,
        default=None,
        help="Enable password authentification with the given global password",
    )

    # Parse arguments
    namespace = parser.parse_args(parser_args)
    bind: str = namespace.__dict__.pop("bind")
    port: int = namespace.__dict__.pop("port")
    password: str = namespace.__dict__.pop("password")

    # Run an executor with no limit on the number of threads
    try:
        with ThreadPoolExecutor(max_workers=32) as executor:
            # Run the server in asyncio
            asyncio.run(
                run_server(bind, port, password, console_cls, namespace, executor)
            )
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
