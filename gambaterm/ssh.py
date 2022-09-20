from __future__ import annotations

import os
import time
import asyncio
import argparse
import tempfile
import traceback
from pathlib import Path
from typing import IO, cast
from concurrent.futures import ThreadPoolExecutor

import asyncssh
from asyncssh import SSHServerProcess
from prompt_toolkit.application import AppSession

from .run import run
from .colors import ColorMode, detect_color_mode
from .file_input import console_input_from_file_context
from .keyboard_input import console_input_from_keyboard_context
from .main import add_base_arguments, add_optional_arguments
from .console import Console, GameboyColor

from .ssh_app_session import process_to_app_session


async def detect_true_color_support(
    process: SSHServerProcess, timeout: float = 0.5
) -> bool:
    # Set unlikely RGB value
    process.stdout.write("\033[48:2:1:2:3m")
    # Query current configuration
    process.stdout.write("\033P$qm\033\\")
    # Reset
    process.stdout.write("\033[m")
    # Wait for reply
    while True:
        try:
            header = await asyncio.wait_for(process.stdin.readuntil("\033\\"), timeout)
        except asyncssh.TerminalSizeChanged:
            pass
        except (asyncio.TimeoutError, asyncio.IncompleteReadError):
            return False
        else:
            break
    # Return whether true color is supported
    return "P1$r" in header and "48:2" in header and "1:2:3m" in header


async def safe_ssh_process_handler(process: SSHServerProcess) -> None:
    try:
        result = await ssh_process_handler(process)
    except KeyboardInterrupt:
        result = 1
    except SystemExit as e:
        result = e.code or 0
    except BaseException:
        traceback.print_exc()
        result = 1
    return process.exit(result or 0)


async def ssh_process_handler(process: SSHServerProcess) -> int:
    executor = process.get_extra_info("executor")
    app_config = process.get_extra_info("app_config")
    display = process.channel.get_x11_display()
    command = process.channel.get_command()
    environment = dict(process.channel.get_environment())
    terminal_type = process.get_terminal_type()
    connection = process.get_extra_info("connection")
    username = process.get_extra_info("username")
    peername, port = connection.get_extra_info("peername")
    print(f"> User `{username}` is connected ({peername}:{port})")

    # Check command
    if command is not None:
        parser = argparse.ArgumentParser()
        parser._print_message = lambda message, file=None: type(parser)._print_message(  # type: ignore[assignment]
            parser, message, file=cast(IO[str], process.stdout)
        )
        add_optional_arguments(parser)
        app_config.console_cls.add_console_arguments(parser)
        parser.parse_args(command.split(), app_config)

    # Check terminal
    if terminal_type is None:
        print(
            "Please use a terminal to access the interactive interface.",
            "Use `-t` to force pseudo-terminal allocation if a command is provided.",
            sep="\n",
            file=process.stdout,
        )
        print(f"< User `{username}` did not use an interactive terminal")
        return 1

    # X11 is required
    if not display and app_config.input_file is None:
        print(
            """\
X11 forwarding is required and can be enabled using the `-X` option.

===============================[ WARNING ]=====================================
Enabling X11 forwarding while connecting to an untrusted server can greatly
endanger your machine. Please only do so if you are running the X11 server in a
sandbox. More information here: https://security.stackexchange.com/a/7496
===============================[ WARNING ]=====================================""",
            file=process.stdout,
        )
        print(f"< User `{username}` did not enable X11 forwarding")
        return 1

    # Detect true color support by interracting with the terminal
    if app_config.color_mode is not None:
        color_mode = app_config.color_mode
    elif await detect_true_color_support(process):
        color_mode = ColorMode.HAS_24_BIT_COLOR
    else:
        environment["TERM"] = terminal_type
        color_mode = detect_color_mode(environment)

    if color_mode == ColorMode.NO_COLOR:
        print(
            "Your terminal `{terminal_type}` doesn't seem to support colors.",
            file=process.stdout,
        )
        print(f"< User `{username}`terminal `{terminal_type}` does not support colors")
        return 1

    async with process_to_app_session(process) as app_session:
        loop = asyncio.get_event_loop()
        height, width = app_session.output.get_size()
        print(
            "[Terminal Info] "
            f"{username}: {terminal_type}, {color_mode}, {width}x{height}"
        )
        return await loop.run_in_executor(
            executor,
            thread_target,
            app_session,
            app_config,
            username,
            display,
            color_mode,
        )


def thread_target(
    app_session: AppSession,
    app_config: argparse.Namespace,
    username: str,
    display: str,
    color_mode: ColorMode,
) -> int:
    console = app_config.console_cls(app_config)
    if app_config.input_file is not None:
        console_input_context = console_input_from_file_context(
            console, app_config.input_file, app_config.skip_inputs
        )
        save_directory = Path(tempfile.mkdtemp())
    else:
        console_input_context = console_input_from_keyboard_context(
            console, display=display
        )
        save_directory = Path("ssh_save") / username
        save_directory.mkdir(parents=True, exist_ok=True)

    with console_input_context as get_console_input:
        try:
            # Prepare alternate screen
            app_session.output.enter_alternate_screen()
            app_session.output.erase_screen()
            app_session.output.hide_cursor()
            app_session.output.flush()

            # Run the emulator
            run(
                console,
                get_input=get_console_input,
                app_session=app_session,
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
            app_session.input.read_keys()
            app_session.output.erase_screen()
            app_session.output.quit_alternate_screen()
            app_session.output.show_cursor()
            # Flush if the connection is still active
            try:
                app_session.output.flush()
            except BrokenPipeError:
                pass


class SSHServer(asyncssh.SSHServer):
    def __init__(self, app_config: argparse.Namespace, executor: ThreadPoolExecutor):
        # Copy app config so we can mutate it later if necessary
        self._app_config = argparse.Namespace(**vars(app_config))
        self._executor = executor

    def connection_made(self, conn: asyncssh.SSHServerConnection) -> None:
        conn.set_extra_info(executor=self._executor)
        conn.set_extra_info(app_config=self._app_config)

    def begin_auth(self, username: str) -> bool:
        return True

    def session_requested(self) -> SSHServerProcess:
        return asyncssh.SSHServerProcess(
            safe_ssh_process_handler, sftp_factory=None, sftp_version=3, allow_scp=False  # type: ignore[arg-type]
        )

    def password_auth_supported(self) -> bool:
        return bool(self._app_config.password)

    def validate_password(self, username: str, password: str) -> bool:
        expected: str = self._app_config.password
        return password == expected


async def run_server(
    app_config: argparse.Namespace, executor: ThreadPoolExecutor
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
        lambda: SSHServer(app_config, executor),
        app_config.bind,
        app_config.port,
        server_host_keys=server_host_keys,
        authorized_client_keys=authorized_client_keys,
        x11_forwarding=True,
        encryption_algs=encryption_algs,
        line_editor=False,
    )
    bind, port = server.sockets[0].getsockname()
    print(f"Running ssh server on {bind}:{port}...", flush=True)

    await server.wait_closed()


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
        help="Enable password authentification with the given global password",
    )

    # Parse arguments
    app_config = parser.parse_args(parser_args)
    app_config.console_cls = console_cls

    # Run an executor with no limit on the number of threads
    with ThreadPoolExecutor(max_workers=32) as executor:

        # Run the server in asyncio
        asyncio.run(run_server(app_config, executor))


if __name__ == "__main__":
    main()
