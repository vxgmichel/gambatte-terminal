from __future__ import annotations

import os
import time
import hmac
import hashlib
import asyncio
import argparse
import traceback
from pathlib import Path
from dataclasses import dataclass
from typing import IO, Callable, TypeAlias, cast, ContextManager
from enum import Enum, auto
from concurrent.futures import ThreadPoolExecutor, CancelledError

import asyncssh
from asyncssh import SSHServerProcess
from blessed import Terminal

from .run import run
from .colors import ColorMode
from .file_input import console_input_from_file_context
from .input_getter import BaseInputGetter
from .keyboard_input import (
    console_input_from_x11_keyboard_context,
    console_input_from_keyboard_protocol_context,
    MESSAGE_SUGGESTING_KITTY_SUPPORT,
    is_kitty_keyboard_protocol_supported,
)
from .main import add_base_arguments, add_optional_arguments, AppConfig
from .console import Console, GameboyColor

from .ssh_app_session import SSHTerminal, process_to_terminal


def is_x11_display_functional(
    display: str,
    executor: ThreadPoolExecutor,
    timeout: float = 3.0,
) -> bool:
    from .x11_keyboard_input import is_x11_display_functional

    try:
        return executor.submit(is_x11_display_functional, display).result(
            timeout=timeout
        )
    except CancelledError:
        return False


class InputSource(Enum):
    INPUT_FILE = auto()
    KEYBOARD_PROTOCOL = auto()
    X11 = auto()


def detect_input_source(
    app_config: AppConfig,
    display: str | None,
    executor: ThreadPoolExecutor,
    term: Terminal,
    timeout: float = 3.0,
) -> InputSource | None:
    if app_config.input_file is not None:
        return InputSource.INPUT_FILE
    if is_kitty_keyboard_protocol_supported(term, timeout=timeout):
        return InputSource.KEYBOARD_PROTOCOL
    if display and is_x11_display_functional(display, executor, timeout=timeout):
        return InputSource.X11
    return None


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
    except BrokenPipeError:
        result = 1
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

    # Manage save directory — hash username to prevent path traversal
    if "save_directory" in namespace.__dict__:
        if getattr(namespace, "input_file", False):
            setattr(namespace, "save_directory", None)
        else:
            safe_name = hashlib.sha256(username.encode("utf-8")).hexdigest()[:16]
            save_directory = Path("ssh_save") / safe_name
            save_directory.mkdir(parents=True, exist_ok=True)
            (save_directory / "username").write_text(username)
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

    return await process_to_terminal(
        process,
        executor,
        lambda terminal: ssh_terminal_handler(
            terminal,
            console_callback,
            app_config,
            display,
            username,
            terminal_type,
            executor,
        ),
    )


def ssh_terminal_handler(
    terminal: SSHTerminal,
    console_callback: Callable[[], Console],
    app_config: AppConfig,
    display: str | None,
    username: str,
    terminal_type: str,
    executor: ThreadPoolExecutor,
) -> int:
    # Now is a good time to instanciate the console
    # (it might fail if the ROM does not exist for instance)
    console = console_callback()

    input_source = detect_input_source(app_config, display, executor, terminal)
    console_input_context: ContextManager[BaseInputGetter]
    if input_source is None:
        message = (
            MESSAGE_SUGGESTING_KITTY_SUPPORT
            + "\n\n"
            + """\
Alternatively, X11 forwarding can be used in order to give the gambaterm-ssh
server access to your keyboard, eg. `ssh -Y -p 8022 localhost`.
===============================[ WARNING ]=====================================
Enabling X11 forwarding while connecting to an untrusted server can greatly
endanger your machine. Please only do so if you are running the X11 server in a
sandbox. More information here: https://security.stackexchange.com/a/7496
===============================[ WARNING ]=====================================
"""
        )
        terminal.stream.write(message)
        terminal.stream.flush()
        print(
            f"< User `{username}` did not support keyboard protocol nor enable X11 forwarding"
        )
        return 1
    elif input_source == InputSource.INPUT_FILE:
        assert app_config.input_file is not None
        console_input_context = console_input_from_file_context(
            console, terminal, app_config.input_file, app_config.skip_inputs
        )
    elif input_source == InputSource.KEYBOARD_PROTOCOL:
        console_input_context = console_input_from_keyboard_protocol_context(
            console,
            terminal,
        )
    elif input_source == InputSource.X11:
        console_input_context = console_input_from_x11_keyboard_context(
            console, terminal, display
        )
    else:
        assert False

    # Default to 24-bit color since the vast majority of modern terminals
    # support it.
    color_mode = (
        app_config.color_mode
        if app_config.color_mode is not None
        else ColorMode.HAS_24_BIT_COLOR
    )

    print(
        f"[Terminal Info] {username}: {terminal_type}, {input_source}, {terminal.width}x{terminal.height}"
    )

    try:
        # Prepare alternate screen
        terminal.stream.write(
            terminal.enter_fullscreen + terminal.clear + terminal.hide_cursor
        )
        terminal.stream.flush()

        with console_input_context as get_console_input:
            # Run the emulator
            run(
                console,
                input_getter=get_console_input,
                term=terminal,
                frame_advance=app_config.frame_advance,
                color_mode=color_mode,
                break_after=app_config.break_after,
                speed=app_config.speed,
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
        terminal.stream.write(
            terminal.clear + terminal.exit_fullscreen + terminal.normal_cursor
        )
        # Flush if the connection is still active
        try:
            terminal.stream.flush()
        except BrokenPipeError:
            pass


@dataclass
class PasswordAndPublicKeyAuthentication:
    password: str


@dataclass
class PublicKeyAuthentication:
    pass


@dataclass
class NoAuthentication:
    pass


AuthenticationMethod: TypeAlias = (
    PasswordAndPublicKeyAuthentication | PublicKeyAuthentication | NoAuthentication
)


class SSHServer(asyncssh.SSHServer):
    def __init__(
        self,
        authentication: AuthenticationMethod,
        console_cls: type[Console],
        namespace: argparse.Namespace,
        executor: ThreadPoolExecutor,
    ):
        self._gambaterm_console_cls = console_cls
        self._gambaterm_namespace = namespace
        self._gambaterm_executor = executor
        self._gambaterm_authentication = authentication

    def connection_made(self, conn: asyncssh.SSHServerConnection) -> None:
        conn.set_extra_info(console_cls=self._gambaterm_console_cls)
        conn.set_extra_info(executor=self._gambaterm_executor)
        conn.set_extra_info(namespace=self._gambaterm_namespace)

    def begin_auth(self, username: str) -> bool:
        return not isinstance(self._gambaterm_authentication, NoAuthentication)

    def session_requested(self) -> SSHServerProcess[str]:
        return asyncssh.SSHServerProcess(
            safe_ssh_process_handler, sftp_factory=None, sftp_version=3, allow_scp=False
        )

    def password_auth_supported(self) -> bool:
        return isinstance(
            self._gambaterm_authentication, (PasswordAndPublicKeyAuthentication,)
        )

    def validate_password(self, username: str, password: str) -> bool:
        assert isinstance(
            self._gambaterm_authentication, PasswordAndPublicKeyAuthentication
        )
        return hmac.compare_digest(password, self._gambaterm_authentication.password)


async def run_server(
    bind: str,
    port: int,
    authentication: AuthenticationMethod,
    console_cls: type[Console],
    namespace: argparse.Namespace,
    executor: ThreadPoolExecutor,
) -> None:
    # Gambaterm configuration
    gambaterm_config_dir = Path(
        os.environ.get("GAMBATERM_CONFIG_DIR", "~/.config/gambaterm")
    ).expanduser()
    server_host_key = gambaterm_config_dir / "ssh_host_key"
    config_authorized_keys = gambaterm_config_dir / "authorized_keys"

    # User SSH public keys (for authentication)
    user_ssh_dir = Path(os.environ.get("GAMBATERM_USER_SSH_DIR", "~/.ssh")).expanduser()
    user_authorized_keys = user_ssh_dir / "authorized_keys"

    # Generate host key if it does not exist
    if not server_host_key.exists():
        print(f"Generating SSH host key at {server_host_key}...")
        server_host_key.parent.mkdir(parents=True, exist_ok=True)
        key = asyncssh.generate_private_key("ssh-ed25519")
        server_host_key.write_bytes(key.export_private_key())
        server_host_key.chmod(0o600)
    server_host_keys = [str(server_host_key)]

    # Collect authorized client keys for public key authentication
    authorized_client_keys = []
    if isinstance(
        authentication, (PublicKeyAuthentication, PasswordAndPublicKeyAuthentication)
    ):
        for key_type in ["rsa", "ed25519", "ecdsa"]:
            user_public_key = user_ssh_dir / f"id_{key_type}.pub"
            if user_public_key.exists():
                authorized_client_keys.append(str(user_public_key))
        if user_authorized_keys.exists():
            authorized_client_keys.append(str(user_authorized_keys))
        if config_authorized_keys.exists():
            authorized_client_keys.append(str(config_authorized_keys))
    if not authorized_client_keys and isinstance(
        authentication, PublicKeyAuthentication
    ):
        raise SystemExit(
            f"Public key authentication is enabled, but no authorized keys were found.\n"
            f"Please add the public keys of allowed clients to {config_authorized_keys}."
        )

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
        lambda: SSHServer(authentication, console_cls, namespace, executor),
        bind,
        port,
        server_host_keys=server_host_keys,
        authorized_client_keys=authorized_client_keys,
        x11_forwarding=True,
        encryption_algs=encryption_algs,
        line_editor=False,
        reuse_address=True,
    )

    match authentication:
        case NoAuthentication():
            print("Authentication disabled (no password nor public key required)")
        case PasswordAndPublicKeyAuthentication():
            print("Authentication methods:")
            print("- Global password")
            for key_path in authorized_client_keys:
                print(f"- Public keys from: {key_path}")
        case PublicKeyAuthentication():
            print("Authentication methods:")
            for key_path in authorized_client_keys:
                print(f"- Public keys from: {key_path}")
    bind, port = server.sockets[0].getsockname()
    print(f"Running SSH server on {bind}:{port}...", flush=True)

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
    parser.add_argument(
        "--no-auth",
        action="store_true",
        help="Disable authentication altogether (no password nor public key required)",
    )

    # Parse arguments
    namespace = parser.parse_args(parser_args)
    bind: str = namespace.__dict__.pop("bind")
    port: int = namespace.__dict__.pop("port")
    password: str = namespace.__dict__.pop("password")
    no_auth: bool = namespace.__dict__.pop("no_auth")

    # Determine authentication method
    if no_auth and password is None:
        authentication: AuthenticationMethod = NoAuthentication()
    elif not no_auth and password is not None:
        authentication = PasswordAndPublicKeyAuthentication(password)
    elif not no_auth and password is None:
        authentication = PublicKeyAuthentication()
    else:
        raise SystemExit(
            "Both `--password` and `--no-auth` cannot be provided at the same time"
        )

    # Run an executor with no limit on the number of threads
    try:
        with ThreadPoolExecutor(max_workers=32) as executor:
            # Run the server in asyncio
            asyncio.run(
                run_server(bind, port, authentication, console_cls, namespace, executor)
            )
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
