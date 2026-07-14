#!/usr/bin/env python3
from __future__ import annotations

import time
import os
import argparse
from pathlib import Path
from typing import ContextManager, TYPE_CHECKING
import dataclasses
from dataclasses import dataclass, field

from blessed import Terminal

from .run import run
from .console import GameboyColor, Console
from .audio import audio_player
from .colors import detect_local_color_mode, ColorMode
from .remote_terminal import (
    GraphicsProtocol,
    FORCE_SIXEL_BLITLESS,
    BAD_TEXT,
    does_sixel,
)
from .input_getter import BaseInputGetter
from .keyboard_input import console_input_from_keyboard_context
from .controller_input import combine_console_input_from_controller_context
from .file_input import console_input_from_file_context, write_input_context

# `typing.Self` is not available in python 3.10
if TYPE_CHECKING:
    from typing import Self
    from blessed.terminal import SoftwareVersion


@dataclass
class AppConfig:
    romfile: Path
    input_file: Path | None
    color_mode: ColorMode | None
    frame_advance: int
    break_after: int | None
    speed: float
    skip_inputs: int
    cpr_sync: int
    graphics_protocol: GraphicsProtocol = GraphicsProtocol.TEXT
    available_graphics: list[GraphicsProtocol] = field(
        default_factory=lambda: [GraphicsProtocol.TEXT]
    )
    save_directory: Path | None = None
    console_namespace: argparse.Namespace = field(default_factory=argparse.Namespace)

    @classmethod
    def from_namespace(cls, namespace: argparse.Namespace) -> Self:
        allowed_keys = {
            f.name for f in dataclasses.fields(cls) if f.name != "console_namespace"
        }
        kwargs = {k: v for k, v in vars(namespace).items() if k in allowed_keys}
        console_keys = {
            k: v for k, v in vars(namespace).items() if k not in allowed_keys
        }
        kwargs["console_namespace"] = argparse.Namespace(**console_keys)
        return cls(**kwargs)


@dataclass
class LocalAppConfig(AppConfig):
    enable_controller: bool = False
    write_input: Path | None = None
    load_state: int | None = None


@dataclass
class TerminalInfo:
    terminal: Terminal
    name: str
    force_transparent_offset: bool


def add_base_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("romfile", metavar="ROM", type=Path, help="Path to a rom file")


def add_input_file_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--input-file", "-i", type=Path, default=None, help="Path to a bizhawk BK2 file"
    )
    parser.add_argument(
        "--skip-inputs",
        "--si",
        type=int,
        default=188,
        help="Number of frame inputs to skip in order to compensate "
        "for the lack of BIOS",
    )


def add_tuning_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--color-mode",
        "-c",
        type=lambda x: ColorMode(int(x)),
        default=None,
        help="Force a color mode "
        "(1: 4 greyscale colors, 2: 16 colors, 3: 256 colors, 4: 24-bit colors). "
        "Note: the color mode can be cycled at runtime by pressing the Tab key, "
        "which is useful for testing the different color modes supported by the terminal.",
    )
    parser.add_argument(
        "--frame-advance",
        "--fa",
        type=int,
        default=1,
        help="Number of frames to run before displaying the next one",
    )
    parser.add_argument(
        "--break-after",
        "--ba",
        type=int,
        default=None,
        help="Number of frames to run before forcing the emulator to stop "
        "(doesn't stop by default)",
    )
    parser.add_argument(
        "--speed",
        "-s",
        type=float,
        default=1.0,
        help="Control the execution speed",
    )
    parser.add_argument(
        "--cpr-sync",
        "--cs",
        nargs="?",
        const=1,
        type=int,
        default=0,
        help="CPR sync window: 0=off, N=allow N unacknowledged frames "
        "(default: 1 if flag given without value)",
    )
    parser.add_argument(
        "--graphics",
        choices=["text", "sixel", "kitty", "auto"],
        default="auto",
        help="Graphics rendering mode "
        "(kitty, sixel, text, or auto-detect)",
    )


def add_local_only_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--disable-audio", "--da", action="store_true", help="Disable audio entirely"
    )
    parser.add_argument(
        "--enable-controller",
        "--ec",
        action="store_true",
        help="Enable game controller support",
    )
    parser.add_argument(
        "--write-input",
        "--wi",
        type=Path,
        help="Record inputs into a file",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Enable the status bar (toggle with backtick/~ key)",
    )
    parser.add_argument(
        "--blit-visualizer",
        action="store_true",
        help="Enable blit visualizer (toggle with F12 key)",
    )
    parser.add_argument(
        "--load-state",
        "--ls",
        type=int,
        default=None,
        help="Load save state N at startup (e.g. --load-state 8 loads ROM_8.gqs)",
    )
    parser.add_argument(
        "--save-directory",
        "--sd",
        type=Path,
        default=None,
        help="Save directory path (defaults to the ROM directory when unspecified)",
    )


def detect_graphics_local(
    terminal: Terminal,
    sv: "SoftwareVersion | None" = None,
) -> tuple[GraphicsProtocol, list[GraphicsProtocol]]:
    """Detect available graphics protocols on a local terminal.

    Returns (selected, available) where selected is the preferred protocol
    and available lists all supported protocols.
    """
    if os.environ.get("GAMBATERM_FORCE_SIXEL"):
        return GraphicsProtocol.SIXEL, [GraphicsProtocol.TEXT, GraphicsProtocol.SIXEL]
    if os.environ.get("GAMBATERM_FORCE_KITTY"):
        return GraphicsProtocol.KITTY, [GraphicsProtocol.TEXT, GraphicsProtocol.KITTY]

    available = [GraphicsProtocol.TEXT]
    if sv is None:
        sv = terminal.get_software_version()
    blitless = sv is not None and sv.name.lower() in FORCE_SIXEL_BLITLESS
    if blitless:
        available.append(GraphicsProtocol.BLITLESS_SIXEL)
        return GraphicsProtocol.BLITLESS_SIXEL, available
    if does_sixel(terminal, sv=sv):
        available.append(GraphicsProtocol.SIXEL)
    if terminal.does_kitty_graphics():
        available.append(GraphicsProtocol.KITTY)
    # Prefer sixel, then kitty, then text
    if GraphicsProtocol.SIXEL in available:
        return GraphicsProtocol.SIXEL, available
    return available[-1], available


def resolve_terminal_and_graphics(
    graphics_value: str,
    console: Console,
) -> tuple[TerminalInfo, GraphicsProtocol, list[GraphicsProtocol]]:
    """Set up terminal, detect capabilities, and resolve the graphics protocol.

    Returns (terminal_info, protocol, available_protocols).
    """
    terminal = Terminal()
    sv = terminal.get_software_version()
    terminal_name = sv.name.lower() if sv is not None else ""
    force_transparent_offset = (
        sv is not None
        and sv.name == "kitty"
        and tuple(int(x) for x in sv.version.split(".")) <= (0, 47, 4)
    )
    tinfo = TerminalInfo(terminal, terminal_name, force_transparent_offset)

    available_graphics: list[GraphicsProtocol] = [GraphicsProtocol.TEXT]
    if graphics_value == "auto":
        protocol, available_graphics = detect_graphics_local(terminal, sv=sv)
    elif graphics_value != "text":
        protocol = GraphicsProtocol[graphics_value.upper()]
        available_graphics = [GraphicsProtocol.TEXT, protocol]
    else:
        protocol = GraphicsProtocol.TEXT

    # Unknown terminals may have broken sixel transparency; force blitless.
    if not terminal_name and protocol is GraphicsProtocol.SIXEL:
        protocol = GraphicsProtocol.BLITLESS_SIXEL

    # Prefer text mode when it fits the terminal, unless the terminal has
    # poor unicode rendering (Rio, mlterm).
    term_height = terminal.height or 24
    term_width = terminal.width or 80
    if (
        term_width >= console.WIDTH
        and term_height >= console.HEIGHT // 2
        and not terminal_name.startswith(BAD_TEXT)
    ):
        protocol = GraphicsProtocol.TEXT

    return tinfo, protocol, available_graphics


def main(
    parser_args: tuple[str, ...] | None = None,
    console_cls: type[Console] = GameboyColor,
) -> None:
    # Create parser
    parser = argparse.ArgumentParser(
        prog="gambaterm",
        description="Gambatte terminal front-end",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    add_base_arguments(parser)
    add_input_file_arguments(parser)
    add_tuning_arguments(parser)
    add_local_only_arguments(parser)
    console_cls.add_console_arguments(parser)

    # Parse arguments
    namespace = parser.parse_args(parser_args)
    disable_audio = getattr(namespace, "disable_audio", False)
    show_status = namespace.__dict__.pop("status")
    blit_visualizer = namespace.__dict__.pop("blit_visualizer")
    graphics_value: str = namespace.__dict__.pop("graphics")
    args = LocalAppConfig.from_namespace(namespace)

    # Check that the ROM file exists
    if not args.romfile.exists():
        raise SystemExit(f"ROM file `{args.romfile}` does not exist")

    # Instantiate the console
    console = console_cls.from_app_config(args)
    if args.load_state is not None:
        console.gb.select_state(args.load_state % 10)
        console.gb.load_state()

    # Detect terminal and resolve graphics protocol
    tinfo, args.graphics_protocol, available_graphics = (
        resolve_terminal_and_graphics(graphics_value, console)
    )

    # Prepare input context
    input_context: ContextManager[BaseInputGetter]
    if args.input_file is not None:
        input_context = console_input_from_file_context(
            console, tinfo.terminal, args.input_file, args.skip_inputs
        )
    else:
        input_context = console_input_from_keyboard_context(console, tinfo.terminal)
        if args.enable_controller:
            input_context = combine_console_input_from_controller_context(input_context)

    if args.write_input:
        input_context = write_input_context(input_context, args.write_input)

    if args.color_mode not in [None, 1, 2, 3, 4]:
        exit(
            f"Invalid color mode `{args.color_mode}`: the value must be between 1 and 4"
        )

    # Enter terminal raw mode
    with tinfo.terminal.raw(), tinfo.terminal.focus_events():
        try:
            # Detect color mode
            if args.color_mode is None:
                args.color_mode = detect_local_color_mode(tinfo.terminal)
                if args.color_mode == ColorMode.COULD_NOT_DETECT:
                    # TODO: add a prompt to ask the user to choose a color mode
                    # instead of silently falling back to 8-bit
                    args.color_mode = ColorMode.HAS_8_BIT_COLOR

            # Prepare alternate screen
            tinfo.terminal.stream.write(
                tinfo.terminal.enter_fullscreen + tinfo.terminal.clear
                + tinfo.terminal.hide_cursor
                + "\033[?7l"  # disable line wrap
            )
            tinfo.terminal.stream.flush()

            # Enter input and audio contexts
            with input_context as get_gb_input:
                with audio_player(console, args.speed, disable_audio) as audio_out:
                    run(
                        console,
                        get_gb_input,
                        term=tinfo.terminal,
                        audio_out=audio_out,
                        frame_advance=args.frame_advance,
                        color_mode=args.color_mode,
                        break_after=args.break_after,
                        speed=args.speed,
                        use_cpr_sync=args.cpr_sync,
                        graphics_protocol=args.graphics_protocol,
                        available_graphics_protocols=available_graphics,
                        terminal_name=tinfo.name,
                        force_transparent_offset=tinfo.force_transparent_offset,
                        show_status=show_status,
                        blit_visualizer=blit_visualizer,
                    )

        # Deal with ctrl+c and ctrl+d exceptions
        except (KeyboardInterrupt, EOFError):
            pass

        # Report runtime error without a stacktrace
        except RuntimeError as error:
            exit(str(error))

        # Exit normally
        else:
            exit()

        # Restore terminal to its initial state
        finally:
            # Wait for a possible CPR
            time.sleep(0.1)
            # Clear alternate screen
            restore = (
                tinfo.terminal.clear + tinfo.terminal.exit_fullscreen
                + tinfo.terminal.normal_cursor
            )
            if args.graphics_protocol is GraphicsProtocol.KITTY:
                restore = b"\033_Ga=d,d=a,q=1\033\\".decode() + restore
            restore = "\033[?7h" + restore  # re-enable line wrap
            tinfo.terminal.stream.write(restore)
            tinfo.terminal.stream.flush()


if __name__ == "__main__":
    main()
