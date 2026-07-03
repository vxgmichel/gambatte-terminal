from __future__ import annotations

import time
import asyncio
import argparse
import traceback
from contextlib import asynccontextmanager
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Coroutine,
    ContextManager,
    Type,
    TypeAlias,
    AsyncIterator,
)
from concurrent.futures import ThreadPoolExecutor

import structlog

if TYPE_CHECKING:
    import telnetlib3
    from telnetlib3.stream_reader import TelnetReader
    from telnetlib3.stream_writer import TelnetWriter

from .run import run
from .colors import ColorMode
from .file_input import console_input_from_file_context
from .main import (
    add_base_arguments,
    add_input_file_arguments,
    add_tuning_arguments,
    AppConfig,
)
from .console import Console, GameboyColor
from .input_getter import BaseInputGetter
from .keyboard_input import (
    MESSAGE_SUGGESTING_KITTY_SUPPORT,
    console_input_from_keyboard_protocol_context,
)
from .remote_terminal import (
    KeyboardSupport,
    KeyboardSupportDetection,
    RemoteTerminal,
    make_graphics_frontend,
    user_directory_name,
    FrontendCallback,
)
from .telnet_app_session import (
    telnet_to_terminal,
)

logger = structlog.get_logger()


def thread_target(
    terminal: RemoteTerminal,
    console_cls: type[Console],
    app_config: AppConfig,
    username: str | None,
    users_directory: Path,
    session_logger: structlog.BoundLogger,
    frontend: FrontendCallback | None = None,
) -> int:
    """Run the emulator in a thread with the given RemoteTerminal."""
    keyboard_support_detection = KeyboardSupportDetection(terminal)
    if frontend is not None:
        try:
            app_config = frontend(terminal, app_config, keyboard_support_detection)
        except (KeyboardInterrupt, EOFError):
            return 0

    # Manage save directory
    app_config.save_directory = (
        None
        if app_config.input_file is not None
        else users_directory / user_directory_name(username)
    )
    if app_config.save_directory is not None:
        app_config.save_directory.mkdir(parents=True, exist_ok=True)

    console = console_cls.from_app_config(app_config)

    console_input_context: ContextManager[BaseInputGetter]
    if app_config.input_file is not None:
        console_input_context = console_input_from_file_context(
            console, terminal, app_config.input_file, app_config.skip_inputs
        )
    elif keyboard_support_detection.get() == KeyboardSupport.KEYBOARD_PROTOCOL:
        console_input_context = console_input_from_keyboard_protocol_context(
            console,
            terminal,
        )
    else:
        message = MESSAGE_SUGGESTING_KITTY_SUPPORT
        terminal.stream.write(message)
        terminal.stream.flush()
        session_logger.warning("User did not support keyboard protocol")
        return 1

    # It is possible, here, to probe XTGETTCAP which helps correct terminal.number_of_colors using
    # 'RGB' and 'colors', and some special attributes like blink, underline et al., but since they
    # are not used by gambaterm, it is not called unless we find better reason otherwise.
    # terminal.probe_xtgettcap(timeout=1.0)

    # In practice kitty keyboard protocol pretty well implies 24-bit color support already,
    color_mode = app_config.color_mode or ColorMode.HAS_24_BIT_COLOR

    try:
        terminal.stream.write(
            terminal.enter_fullscreen + terminal.clear + terminal.hide_cursor
        )
        terminal.stream.flush()
        with console_input_context as get_console_input:
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
    except (KeyboardInterrupt, EOFError):
        return 0
    else:
        return 0
    finally:
        time.sleep(0.1)
        terminal.stream.write(
            terminal.clear + terminal.exit_fullscreen + terminal.normal_cursor
        )
        try:
            terminal.stream.flush()
        except BrokenPipeError:
            pass


ShellCallback: TypeAlias = Callable[
    ["TelnetReader", "TelnetWriter"], Coroutine[Any, Any, None]
]


def make_telnet_shell(
    app_config: argparse.Namespace,
    console_cls: Type[Console],
    idle_timeout: float | None,
    users_directory: Path,
    executor: ThreadPoolExecutor,
    frontend: FrontendCallback | None = None,
) -> ShellCallback:
    """Create a telnet shell callback with app_config and executor bound."""

    async def telnet_shell(reader: TelnetReader, writer: TelnetWriter) -> None:
        try:
            await _telnet_shell(
                reader,
                writer,
                app_config,
                console_cls,
                idle_timeout,
                users_directory,
                executor,
                frontend=frontend,
            )
        except (KeyboardInterrupt, EOFError):
            pass
        except SystemExit:
            pass
        except BaseException:
            traceback.print_exc()
        if not writer.is_closing():
            writer.close()

    return telnet_shell


def _fmt_idle(seconds: float) -> str:
    """Format idle duration as 'Xm' or 'X.Xs'."""
    if seconds >= 60:
        return f"{seconds / 60:.0f}m"
    return f"{seconds:.1f}s"


async def _log_connection_stats(
    reader: TelnetReader,
    writer: TelnetWriter,
    peer_host: str,
    peer_port: int,
    idle_timeout: float,
    interval: float = 10.0,
    logger: structlog.BoundLogger = logger,
) -> None:
    """Periodically log tx stats and idle time. Kick idle clients."""
    conn_logger = logger
    protocol = writer.protocol
    if protocol is None:
        return

    start_time = time.monotonic()
    prev_time = start_time
    prev_tx: int = getattr(protocol, "tx_bytes", 0)
    prev_rx: int = getattr(protocol, "rx_bytes", 0)
    last_active_time = start_time

    try:
        while True:
            await asyncio.sleep(interval)
            now = time.monotonic()
            elapsed = now - start_time
            dt = now - prev_time

            rx: int = getattr(protocol, "rx_bytes", 0)
            tx: int = getattr(protocol, "tx_bytes", 0)

            if rx != prev_rx:
                last_active_time = now

            idle_duration = now - last_active_time

            tx_mbps = (tx - prev_tx) * 8 / dt / 1_000_000 if dt > 0 else 0.0
            avg_tx_mbps = tx * 8 / elapsed / 1_000_000 if elapsed > 0 else 0.0

            minutes, secs = divmod(int(elapsed), 60)
            hours, minutes = divmod(minutes, 60)
            uptime = (
                f"{hours}h{minutes:02d}m{secs:02d}s"
                if hours
                else f"{minutes}m{secs:02d}s"
            )

            conn_logger.info(
                "Connection stats",
                uptime=uptime,
                tx_bytes=tx,
                tx_rate_mbps=tx_mbps,
                avg_tx_rate_mbps=avg_tx_mbps,
                idle=idle_duration,
            )

            if idle_duration >= idle_timeout:
                conn_logger.warning(
                    "Kicking idle client",
                    idle=idle_duration,
                )
                # Send an EOF to the emulator thread to trigger a graceful shutdown.
                reader.feed_eof()
                return

            prev_time = now
            prev_tx = tx
            prev_rx = rx
    except asyncio.CancelledError:
        now = time.monotonic()
        elapsed = now - start_time
        tx = getattr(protocol, "tx_bytes", 0)
        avg_tx_mbps = tx * 8 / elapsed / 1_000_000 if elapsed > 0 else 0.0
        conn_logger.info(
            "Client disconnected",
            duration=elapsed,
            total_tx_bytes=tx,
            avg_tx_rate_mbps=avg_tx_mbps,
        )


async def _telnet_shell(
    reader: TelnetReader,
    writer: TelnetWriter,
    app_config: argparse.Namespace,
    console_cls: type[Console],
    idle_timeout: float | None,
    users_directory: Path,
    executor: ThreadPoolExecutor,
    frontend: FrontendCallback | None = None,
) -> int:
    peername = writer.get_extra_info("peername")
    peer_host = peername[0] if peername else "unknown"
    peer_port = peername[1] if peername else 0

    # Wait for TTYPE and NEW_ENVIRON negotiation to settle
    try:
        await asyncio.wait_for(
            writer.wait_for(pending={"TTYPE": False, "NEW_ENVIRON": False}),
            timeout=1.0,
        )
    except (asyncio.TimeoutError, KeyError):
        pass

    terminal_type = writer.get_extra_info("TERM") or None
    username = writer.get_extra_info("USER") or None
    session_logger = logger.bind(
        peer=f"{peer_host}:{peer_port}",
        term=terminal_type,
        username=username,
    )
    session_logger.info("Telnet client connected")

    if idle_timeout is not None:
        stats_task = asyncio.create_task(
            _log_connection_stats(
                reader,
                writer,
                peer_host,
                peer_port,
                idle_timeout,
                logger=session_logger,
            )
        )
    else:
        stats_task = None

    cols = writer.get_extra_info("cols") or 80
    rows = writer.get_extra_info("rows") or 24
    session_logger.info(
        "Terminal info",
        cols=cols,
        rows=rows,
    )

    try:
        # Convert namespace to AppConfig
        config = AppConfig.from_namespace(app_config)

        def target(term: RemoteTerminal) -> int:
            return thread_target(
                term,
                console_cls,
                config,
                username,
                users_directory,
                session_logger,
                frontend=frontend,
            )

        return await telnet_to_terminal(
            reader,
            writer,
            executor,
            target,
            terminal_type=terminal_type,
        )
    finally:
        if stats_task is not None:
            stats_task.cancel()
            try:
                await stats_task
            except asyncio.CancelledError:
                pass


@asynccontextmanager
async def run_telnet_server(
    bind: str,
    port: int,
    robot_check: bool,
    max_players: int,
    idle_timeout: float | None,
    console_cls: type[Console],
    namespace: argparse.Namespace,
    users_directory: Path,
    executor: ThreadPoolExecutor,
    frontend: FrontendCallback | None = None,
) -> AsyncIterator[telnetlib3.Server]:
    import telnetlib3

    shell = make_telnet_shell(
        namespace,
        console_cls,
        idle_timeout,
        users_directory,
        executor,
        frontend=frontend,
    )

    if robot_check or max_players > 0:
        from telnetlib3.guard_shells import ConnectionCounter, busy_shell
        from telnetlib3.guard_shells import robot_check as do_robot_check
        from telnetlib3.guard_shells import robot_shell

        counter = ConnectionCounter(max_players) if max_players > 0 else None
        inner_shell = shell

        async def guarded_shell(reader: TelnetReader, writer: TelnetWriter) -> None:
            if counter is not None and not counter.try_acquire():
                try:
                    await busy_shell(reader, writer)
                finally:
                    if not writer.is_closing():
                        writer.close()
                return
            try:
                if robot_check:
                    passed = await do_robot_check(reader, writer)
                    if not passed:
                        peername = writer.get_extra_info("peername")
                        logger.warning(
                            "Rejected telnet client which failed robot check",
                            peer=f"{peername[0]}:{peername[1]}" if peername else None,
                        )
                        await robot_shell(reader, writer)
                        if not writer.is_closing():
                            writer.close()
                        return
                await inner_shell(reader, writer)
            finally:
                if counter is not None:
                    counter.release()

        shell = guarded_shell

    server = await telnetlib3.create_server(
        host=bind,
        port=port,
        shell=shell,
        encoding=False,
        force_binary=True,
        connect_maxwait=4.0,
        timeout=0,
    )
    sockets = server.sockets
    assert sockets is not None
    actual_bind, actual_port = sockets[0].getsockname()[:2]
    logger.info("Running telnet server", bind=actual_bind, port=actual_port)
    try:
        yield server
    finally:
        assert server._server is not None
        server._server.close()
        for client in server.clients:
            if client.reader is not None:
                client.reader.feed_eof()
        await server.wait_closed()


def main(
    parser_args: tuple[str, ...] | None = None,
    console_cls: type[Console] = GameboyColor,
) -> None:
    parser = argparse.ArgumentParser(
        description="Gambatte terminal front-end over telnet"
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
        help="Bind address of the telnet server, "
        "use `0.0.0.0` for all interfaces (default is localhost)",
    )
    parser.add_argument(
        "--max-players",
        type=int,
        default=0,
        metavar="N",
        help="maximum concurrent players (0 = unlimited)",
    )
    parser.add_argument(
        "--robot-check",
        action="store_true",
        default=False,
        help="reject bots by checking if client responds to "
        "cursor position requests",
    )
    parser.add_argument(
        "--port",
        "-p",
        type=int,
        default=8023,
        help="Port of the telnet server (default is 8023)",
    )
    parser.add_argument(
        "--idle-timeout",
        type=float,
        default=None,
        help="Idle timeout in seconds (default is disabled)",
    )
    parser.add_argument(
        "--users-directory",
        type=Path,
        default=Path("users_save"),
        help="Directory containing one save directory per user (default is ./users_save)",
    )

    namespace = parser.parse_args(parser_args)
    bind: str = namespace.__dict__.pop("bind")
    port: int = namespace.__dict__.pop("port")
    robot_check: bool = namespace.__dict__.pop("robot_check")
    max_players: int = namespace.__dict__.pop("max_players")
    idle_timeout: float | None = namespace.__dict__.pop("idle_timeout")
    users_directory: Path = namespace.__dict__.pop("users_directory")
    graphics_value: str = namespace.__dict__.pop("graphics")
    frontend = make_graphics_frontend(graphics_value)

    try:
        with ThreadPoolExecutor(max_workers=32) as executor:

            async def async_main() -> None:
                async with run_telnet_server(
                    bind,
                    port,
                    robot_check,
                    max_players,
                    idle_timeout,
                    console_cls,
                    namespace,
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
