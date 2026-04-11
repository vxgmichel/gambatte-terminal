from __future__ import annotations

import time
import hashlib
import asyncio
import argparse
import traceback
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Coroutine, ContextManager
from concurrent.futures import ThreadPoolExecutor

if TYPE_CHECKING:
    from telnetlib3.stream_reader import TelnetReader
    from telnetlib3.stream_writer import TelnetWriter

from .run import run
from .colors import ColorMode
from .file_input import console_input_from_file_context
from .main import add_base_arguments, add_optional_arguments, AppConfig
from .console import Console, GameboyColor
from .input_getter import BaseInputGetter
from .keyboard_input import (
    MESSAGE_SUGGESTING_KITTY_SUPPORT,
    console_input_from_keyboard_protocol_context,
    is_kitty_keyboard_protocol_supported,
)
from .remote_terminal import RemoteTerminal
from .telnet_app_session import (
    set_tcp_nodelay,
    telnet_to_terminal,
)


def _save_dir_name(username: str | None) -> str:
    """Hash the username into a safe directory name.

    :param username: telnet-negotiated username, or ``None``
    :returns: hex digest suitable for use as a directory name
    """
    if username is None:
        return "_anonymous"
    return hashlib.sha256(username.encode("utf-8")).hexdigest()[:16]


def thread_target(
    terminal: RemoteTerminal,
    console_callback: Callable[[], Console],
    app_config: AppConfig,
    color_mode: ColorMode,
    username: str | None,
) -> int:
    """Run the emulator in a thread with the given RemoteTerminal."""
    console: Console = console_callback()

    console_input_context: ContextManager[BaseInputGetter]
    if app_config.input_file is not None:
        console_input_context = console_input_from_file_context(
            console, terminal, app_config.input_file, app_config.skip_inputs
        )
    elif is_kitty_keyboard_protocol_supported(terminal, timeout=3):
        console_input_context = console_input_from_keyboard_protocol_context(
            console,
            terminal,
        )
    else:
        message = MESSAGE_SUGGESTING_KITTY_SUPPORT
        terminal.stream.write(message)
        terminal.stream.flush()
        print(f"< User `{username}` did not support keyboard protocol")
        return 1

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
            )
    except (KeyboardInterrupt, OSError):
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


ShellCallback = Callable[["TelnetReader", "TelnetWriter"], Coroutine[Any, Any, None]]


def make_telnet_shell(
    app_config: argparse.Namespace, executor: ThreadPoolExecutor
) -> ShellCallback:
    """Create a telnet shell callback with app_config and executor bound."""

    async def telnet_shell(reader: TelnetReader, writer: TelnetWriter) -> None:
        try:
            await _telnet_shell(reader, writer, app_config, executor)
        except KeyboardInterrupt:
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
    writer: TelnetWriter,
    peer_host: str,
    peer_port: int,
    interval: float = 30.0,
    idle_timeout: float = 300.0,
) -> None:
    """Periodically log tx stats and idle time. Kick idle clients."""
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

            idle_str = (
                f" (idle {_fmt_idle(idle_duration)})" if idle_duration >= 1.0 else ""
            )

            print(
                f"[Stats {peer_host}:{peer_port}] "
                f"up {uptime}, "
                f"tx {tx:,}B ({tx_mbps:.3f}/{avg_tx_mbps:.3f} Mbit/s)"
                f"{idle_str}"
            )

            if idle_duration >= idle_timeout:
                print(
                    f"[Stats {peer_host}:{peer_port}] "
                    f"kicking idle client after {_fmt_idle(idle_duration)}"
                )
                try:
                    await writer.drain()
                    writer.write(b"\r\n\r\nConnection closed for idle client\r\n")
                    await writer.drain()
                except (ConnectionError, OSError):
                    pass
                writer.close()
                return

            prev_time = now
            prev_tx = tx
            prev_rx = rx
    except asyncio.CancelledError:
        now = time.monotonic()
        elapsed = now - start_time
        tx = getattr(protocol, "tx_bytes", 0)
        avg_tx_mbps = tx * 8 / elapsed / 1_000_000 if elapsed > 0 else 0.0
        print(
            f"[Stats {peer_host}:{peer_port}] "
            f"disconnected after {elapsed:.1f}s, "
            f"total tx {tx:,}B (avg {avg_tx_mbps:.3f} Mbit/s)"
        )


async def _telnet_shell(
    reader: TelnetReader,
    writer: TelnetWriter,
    app_config: argparse.Namespace,
    executor: ThreadPoolExecutor,
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

    terminal_type = writer.get_extra_info("TERM") or "unknown"
    username = writer.get_extra_info("USER") or None
    print(
        f"> Telnet client connected ({peer_host}:{peer_port})"
        + (f" user={username}" if username else "")
    )

    if terminal_type == "unknown":
        print("Warning: terminal type not negotiated, assuming xterm-256color.")
        terminal_type = "xterm-256color"

    # Kitty keyboard protocol implies 24-bit color support
    color_mode = app_config.color_mode or ColorMode.HAS_24_BIT_COLOR

    # Set TCP_NODELAY to disable Nagle's algorithm for paced output
    set_tcp_nodelay(writer)

    stats_task = asyncio.create_task(
        _log_connection_stats(writer, peer_host, peer_port)
    )

    cols = writer.get_extra_info("cols") or 80
    rows = writer.get_extra_info("rows") or 24
    print(
        f"[Terminal Info] {peer_host}: {terminal_type}, "
        f"{color_mode.name}, {cols}x{rows}"
    )

    try:
        # Copy namespace and set telnet-specific save directory
        namespace = argparse.Namespace(**vars(app_config))
        save_directory = (
            None
            if getattr(namespace, "input_file", None)
            else Path("telnet_save") / _save_dir_name(username)
        )
        namespace.save_directory = save_directory
        if save_directory is not None:
            save_directory.mkdir(parents=True, exist_ok=True)

        # Pop console-specific args and build console factory + AppConfig
        console_cls: type[Console] = namespace.__dict__.pop("console_cls")
        console_callback = console_cls.pop_console_arguments(namespace)
        config = AppConfig(**vars(namespace))

        def target(term: RemoteTerminal) -> int:
            return thread_target(term, console_callback, config, color_mode, username)

        return await telnet_to_terminal(
            reader,
            writer,
            executor,
            target,
        )
    finally:
        stats_task.cancel()
        try:
            await stats_task
        except asyncio.CancelledError:
            pass


async def run_server(
    bind: str,
    port: int,
    robot_check: bool,
    max_players: int,
    console_cls: type[Console],
    namespace: argparse.Namespace,
    executor: ThreadPoolExecutor,
) -> None:
    import telnetlib3

    shell = make_telnet_shell(namespace, executor)

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
    print(f"Running telnet server on {actual_bind}:{actual_port}...", flush=True)
    await asyncio.Future()


def main(
    parser_args: tuple[str, ...] | None = None,
    console_cls: type[Console] = GameboyColor,
) -> None:
    parser = argparse.ArgumentParser(
        description="Gambatte terminal front-end over telnet"
    )
    add_base_arguments(parser)
    add_optional_arguments(parser)
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

    namespace = parser.parse_args(parser_args)
    bind: str = namespace.__dict__.pop("bind")
    port: int = namespace.__dict__.pop("port")
    robot_check: bool = namespace.__dict__.pop("robot_check")
    max_players: int = namespace.__dict__.pop("max_players")
    namespace.console_cls = console_cls

    try:
        with ThreadPoolExecutor(max_workers=32) as executor:
            asyncio.run(
                run_server(
                    bind,
                    port,
                    robot_check,
                    max_players,
                    console_cls,
                    namespace,
                    executor,
                )
            )
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
