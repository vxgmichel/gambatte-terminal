from __future__ import annotations

import os
import time
import hmac
import asyncio
import argparse
import traceback
from pathlib import Path
from dataclasses import dataclass
from contextlib import asynccontextmanager
from typing import AnyStr, Callable, TypeAlias, ContextManager, AsyncIterator
from enum import Enum, auto
from concurrent.futures import ThreadPoolExecutor

import asyncssh
import structlog
from asyncssh import (
    SFTPServerFactory,
    SSHServerConnection,
    SSHServerProcess,
    SSHAcceptor,
    SSHServer,
    SSHServerProcessFactory,
)
from asyncssh.channel import SSHChannel

from .run import run
from .colors import ColorMode
from .file_input import console_input_from_file_context
from .input_getter import BaseInputGetter
from .keyboard_input import (
    console_input_from_x11_keyboard_context,
    console_input_from_keyboard_protocol_context,
    MESSAGE_SUGGESTING_KITTY_SUPPORT,
)
from .main import (
    add_base_arguments,
    add_input_file_arguments,
    add_tuning_arguments,
    AppConfig,
)
from .console import Console, GameboyColor

from .remote_terminal import (
    KeyboardSupport,
    KeyboardSupportDetection,
    RemoteTerminal,
    make_graphics_frontend,
    user_directory_name,
    FrontendCallback,
)
from .ssh_app_session import process_to_terminal

logger = structlog.get_logger()


Writer: TypeAlias = Callable[[str], None]
CommandParser: TypeAlias = Callable[
    [str, argparse.Namespace, Writer], argparse.Namespace
]


class InputSource(Enum):
    INPUT_FILE = auto()
    KEYBOARD_PROTOCOL = auto()
    X11 = auto()


def detect_input_source(
    app_config: AppConfig,
    keyboard_support_detection: KeyboardSupportDetection,
    timeout: float = 3.0,
) -> InputSource | None:
    if app_config.input_file is not None:
        return InputSource.INPUT_FILE
    keyboard_support = keyboard_support_detection.get(timeout)
    if keyboard_support == KeyboardSupport.KEYBOARD_PROTOCOL:
        return InputSource.KEYBOARD_PROTOCOL
    if keyboard_support == KeyboardSupport.X11:
        return InputSource.X11
    return None


async def safe_ssh_process_handler(process: SSHServerProcess[str]) -> None:
    try:
        result = await ssh_process_handler(process)
    except (KeyboardInterrupt, EOFError):
        result = 0
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
    command_parser: CommandParser = process.get_extra_info("command_parser")
    users_directory: Path = process.get_extra_info("users_directory")
    executor: ThreadPoolExecutor = process.get_extra_info("executor")
    display = process.channel.get_x11_display()
    command = process.channel.get_command()
    terminal_type = process.get_terminal_type()
    connection = process.get_extra_info("connection")
    username = process.get_extra_info("username")
    peername, port = connection.get_extra_info("peername")
    session_logger = logger.bind(username=username, peer=f"{peername}:{port}")
    session_logger.info("User connected")

    frontend = connection.get_extra_info("frontend")

    # Copy namespace before mutating
    namespace = argparse.Namespace(**vars(namespace))

    # Check command
    if command is not None:
        namespace = command_parser(
            command,
            namespace,
            lambda data: print(data.replace("\n", "\r\n"), end="", file=process.stdout),
        )

    # Convert namespace to AppConfig
    app_config = AppConfig.from_namespace(namespace)

    # Check terminal
    if terminal_type is None:
        print(
            "Please use a terminal to access the interactive interface.",
            "Use `-t` to force pseudo-terminal allocation if a command is provided.",
            sep="\r\n",
            file=process.stdout,
        )
        session_logger.warning("User did not use an interactive terminal")
        return 1

    return await process_to_terminal(
        process,
        executor,
        lambda terminal: ssh_terminal_handler(
            terminal,
            console_cls,
            app_config,
            display,
            username,
            terminal_type,
            executor,
            users_directory,
            session_logger,
            frontend=frontend,
        ),
        terminal_type=terminal_type,
    )


def ssh_terminal_handler(
    terminal: RemoteTerminal,
    console_cls: type[Console],
    app_config: AppConfig,
    display: str | None,
    username: str,
    terminal_type: str,
    executor: ThreadPoolExecutor,
    users_directory: Path,
    session_logger: structlog.BoundLogger,
    frontend: FrontendCallback | None = None,
) -> int:
    keyboard_support_detection = KeyboardSupportDetection(terminal, display, executor)

    if frontend is not None:
        try:
            app_config = frontend(terminal, app_config, keyboard_support_detection)
        except (KeyboardInterrupt, EOFError):
            return 0

    # Manage save directory — hash username to prevent path traversal
    app_config.save_directory = (
        None
        if app_config.input_file is not None
        else users_directory / user_directory_name(username)
    )

    if app_config.save_directory is not None:
        app_config.save_directory.mkdir(parents=True, exist_ok=True)
        (app_config.save_directory / "username").write_text(username)

    # Now is a good time to instantiate the console
    # (it might fail if the ROM does not exist for instance)
    console = console_cls.from_app_config(app_config)

    input_source = detect_input_source(app_config, keyboard_support_detection)
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
        session_logger.warning(
            "User did not support keyboard protocol nor enable X11 forwarding"
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

    # It is possible, here, to probe XTGETTCAP which helps correct terminal.number_of_colors using
    # 'RGB' and 'colors', and some special attributes like blink, underline et al., but since they
    # are not used by gambaterm, it is not called unless we find better reason otherwise.
    # terminal.probe_xtgettcap(timeout=1.0)

    # In practice kitty keyboard protocol pretty well implies 24-bit color support already,
    color_mode = app_config.color_mode or ColorMode.HAS_24_BIT_COLOR

    session_logger.info(
        "Terminal info",
        term=terminal_type,
        input_source=str(input_source),
        cols=terminal.width,
        rows=terminal.height,
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
                graphics_protocol=app_config.graphics_protocol,
                available_graphics_protocols=app_config.available_graphics,
            )
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


class GambatermSSHServerProcess(SSHServerProcess[str]):
    def __init__(
        self,
        process_factory: SSHServerProcessFactory[str],
        sftp_factory: SFTPServerFactory | None,
        sftp_version: int,
        allow_scp: bool,
        active_sessions: set[GambatermSSHServerProcess],
    ):
        super().__init__(process_factory, sftp_factory, sftp_version, allow_scp)
        self._gambaterm_active_sessions = active_sessions

    def connection_made(self, chan: SSHChannel[AnyStr]) -> None:
        self._gambaterm_active_sessions.add(self)
        return super().connection_made(chan)

    def connection_lost(self, exc: Exception | None) -> None:
        self._gambaterm_active_sessions.discard(self)
        return super().connection_lost(exc)


class GambatermSSHServer(SSHServer):
    def __init__(
        self,
        authentication: AuthenticationMethod,
        console_cls: type[Console],
        namespace: argparse.Namespace,
        command_parser: CommandParser,
        users_directory: Path,
        executor: ThreadPoolExecutor,
        active_connections: dict[GambatermSSHServer, SSHServerConnection],
        frontend: Callable[
            [RemoteTerminal, AppConfig, KeyboardSupportDetection], AppConfig
        ]
        | None = None,
    ):
        self._gambaterm_console_cls = console_cls
        self._gambaterm_namespace = namespace
        self._gambaterm_command_parser = command_parser
        self._gambaterm_users_directory = users_directory
        self._gambaterm_executor = executor
        self._gambaterm_authentication = authentication
        self._gambaterm_active_connections = active_connections
        self._gambaterm_active_sessions: set[GambatermSSHServerProcess] = set()
        self._gambaterm_frontend = frontend

    def connection_made(self, conn: SSHServerConnection) -> None:
        self._conn = conn
        conn.set_extra_info(console_cls=self._gambaterm_console_cls)
        conn.set_extra_info(executor=self._gambaterm_executor)
        conn.set_extra_info(namespace=self._gambaterm_namespace)
        conn.set_extra_info(command_parser=self._gambaterm_command_parser)
        conn.set_extra_info(users_directory=self._gambaterm_users_directory)
        conn.set_extra_info(frontend=self._gambaterm_frontend)
        self._gambaterm_active_connections[self] = conn

    def connection_lost(self, exc: Exception | None) -> None:
        self._gambaterm_active_connections.pop(self)

    def begin_auth(self, username: str) -> bool:
        return not isinstance(self._gambaterm_authentication, NoAuthentication)

    def session_requested(self) -> SSHServerProcess[str]:
        return GambatermSSHServerProcess(
            safe_ssh_process_handler,
            sftp_factory=None,
            sftp_version=3,
            allow_scp=False,
            active_sessions=self._gambaterm_active_sessions,
        )

    def password_auth_supported(self) -> bool:
        return isinstance(
            self._gambaterm_authentication, (PasswordAndPublicKeyAuthentication,)
        )

    def validate_password(self, username: str, password: str) -> bool:
        assert isinstance(
            self._gambaterm_authentication, PasswordAndPublicKeyAuthentication
        )
        is_valid = hmac.compare_digest(
            password, self._gambaterm_authentication.password
        )
        if not is_valid:
            conn = getattr(self, "_conn", None)
            peername = conn.get_extra_info("peername") if conn else None
            logger.warning(
                "Failed password authentication",
                username=username,
                password=password,
                peer=f"{peername[0]}:{peername[1]}" if peername else None,
            )
        return is_valid


@asynccontextmanager
async def run_ssh_server(
    bind: str,
    port: int,
    authentication: AuthenticationMethod,
    console_cls: type[Console],
    namespace: argparse.Namespace,
    command_parser: CommandParser,
    users_directory: Path,
    executor: ThreadPoolExecutor,
    frontend: FrontendCallback | None = None,
) -> AsyncIterator[SSHAcceptor]:
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
        logger.info("Generating SSH host key", path=str(server_host_key))
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

    active_connections: dict[GambatermSSHServer, SSHServerConnection] = {}
    server = await asyncssh.create_server(
        lambda: GambatermSSHServer(
            authentication,
            console_cls,
            namespace,
            command_parser,
            users_directory,
            executor,
            active_connections,
            frontend,
        ),
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
            logger.info("Authentication disabled (no password nor public key required)")
        case PasswordAndPublicKeyAuthentication():
            logger.info(
                "Authentication methods configured",
                password=True,
                keys=[str(kp) for kp in authorized_client_keys],
            )
        case PublicKeyAuthentication():
            logger.info(
                "Authentication methods configured",
                password=False,
                keys=[str(kp) for kp in authorized_client_keys],
            )
    bind, port = server.sockets[0].getsockname()
    logger.info("Running SSH server", bind=bind, port=port)

    try:
        yield server
    finally:
        # Stop listening for new connections
        server.close()

        # Freeze active connections
        for ssh_server, connection in list(active_connections.items()):
            # Freeze active sessions
            for session in list(ssh_server._gambaterm_active_sessions):
                # Graceful teardown
                # This is important to make sure the client receives the cleanup data
                session.eof_received()
                await session.wait_closed()

            # Close the connection
            # This is important for clients stuck in authentication phase for instance
            connection.close()

        # Now nothing should keep the server from closing
        await server.wait_closed()


def main(
    parser_args: tuple[str, ...] | None = None,
    console_cls: type[Console] = GameboyColor,
) -> None:
    parser = argparse.ArgumentParser(
        prog="gambaterm-ssh",
        description="Gambatte terminal front-end over ssh",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    add_base_arguments(parser)
    add_input_file_arguments(parser)
    add_tuning_arguments(parser)
    console_cls.add_console_arguments(parser)
    parser.add_argument(
        "--bind",
        "-b",
        type=str,
        default="127.0.0.1",
        help="Bind address of the SSH server, "
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
        help="Enable password authentication with the given global password",
    )
    parser.add_argument(
        "--no-auth",
        action="store_true",
        help="Disable authentication altogether (no password nor public key required)",
    )
    parser.add_argument(
        "--users-directory",
        type=Path,
        default=Path("users_save"),
        help="Directory containing one save directory per user (default is ./users_save)",
    )

    # Parse arguments
    namespace = parser.parse_args(parser_args)
    bind: str = namespace.__dict__.pop("bind")
    port: int = namespace.__dict__.pop("port")
    password: str = namespace.__dict__.pop("password")
    no_auth: bool = namespace.__dict__.pop("no_auth")
    users_directory: Path = namespace.__dict__.pop("users_directory")
    graphics_value: str = namespace.__dict__.pop("graphics")

    # Determine frontend callback for graphics
    frontend: FrontendCallback | None = make_graphics_frontend(graphics_value)

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

    # Make sure that the ROM file exists before starting the server
    rom_path: Path = namespace.romfile
    if not rom_path.exists():
        raise SystemExit(f"ROM file `{rom_path}` does not exist")

    # Define a command parser for SSH clients
    def command_parser(
        command: str, namespace: argparse.Namespace, write: Writer
    ) -> argparse.Namespace:
        parser = argparse.ArgumentParser()
        parser._print_message = lambda message, file=None: write(message)  # type: ignore[method-assign]
        add_tuning_arguments(parser)
        console_cls.add_console_arguments(parser)
        return parser.parse_args(command.split(), namespace)

    # Run an executor with no limit on the number of threads
    try:
        with ThreadPoolExecutor(max_workers=32) as executor:
            # Run the server in asyncio
            async def async_main() -> None:
                async with run_ssh_server(
                    bind,
                    port,
                    authentication,
                    console_cls,
                    namespace,
                    command_parser,
                    users_directory,
                    executor,
                    frontend=frontend,
                ):
                    await asyncio.Future()

            asyncio.run(async_main())

    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
