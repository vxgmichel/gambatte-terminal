#!/usr/bin/env python3
from __future__ import annotations

import time
import argparse
from pathlib import Path
from typing import ContextManager
from dataclasses import dataclass

from blessed import Terminal

from .run import run
from .console import GameboyColor, Console
from .audio import audio_player, no_audio
from .colors import detect_local_color_mode, ColorMode
from .input_getter import BaseInputGetter
from .keyboard_input import console_input_from_keyboard_context
from .controller_input import combine_console_input_from_controller_context
from .file_input import console_input_from_file_context, write_input_context


@dataclass
class AppConfig:
    romfile: Path
    input_file: Path | None
    color_mode: ColorMode | None
    frame_advance: int
    break_after: int | None
    speed: float
    skip_inputs: int
    cpr_sync: bool
    enable_controller: bool
    write_input: Path | None
    no_sextants: bool
    octants: bool
    cp437: bool


def add_base_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("romfile", metavar="ROM", type=Path, help="Path to a rom file")
    parser.add_argument(
        "--input-file", "-i", type=Path, default=None, help="Path to a bizhawk BK2 file"
    )


def add_optional_arguments(parser: argparse.ArgumentParser) -> None:
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
        help="Number of frames to run before displaying the next one (default is 1)",
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
        help="Control the execution speed (default is 1.0)",
    )
    parser.add_argument(
        "--skip-inputs",
        "--si",
        type=int,
        default=188,
        help="Number of frame inputs to skip in order to compensate "
        "for the lack of BIOS (default is 188)",
    )
    parser.add_argument(
        "--cpr-sync",
        "--cs",
        action="store_true",
        help="Use CPR synchronization to prevent video buffering",
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
        "--no-sextants",
        action="store_true",
        default=False,
        help="Disable sextant block rendering",
    )
    parser.add_argument(
        "--octants",
        action="store_true",
        default=False,
        help="Enable octant block rendering, requires a Unicode 16.0 or newer font",
    )
    parser.add_argument(
        "--cp437",
        action="store_true",
        default=False,
        help="Restrict to CP437 block characters only, "
        "disabling sextants, octants, and eighth-height blocks",
    )


def main(
    parser_args: tuple[str, ...] | None = None,
    console_cls: type[Console] = GameboyColor,
) -> None:
    parser = argparse.ArgumentParser(
        prog="gambaterm", description="Gambatte terminal front-end"
    )
    add_base_arguments(parser)
    add_optional_arguments(parser)
    console_cls.add_console_arguments(parser)
    parser.add_argument(
        "--disable-audio", "--da", action="store_true", help="Disable audio entirely"
    )
    namespace = parser.parse_args(parser_args)
    disable_audio: bool = namespace.__dict__.pop("disable_audio")
    console_callback = console_cls.pop_console_arguments(namespace)
    console = console_callback()
    args = AppConfig(**vars(namespace))

    terminal = Terminal()

    input_context: ContextManager[BaseInputGetter]
    if args.input_file is not None:
        input_context = console_input_from_file_context(
            console, terminal, args.input_file, args.skip_inputs
        )
    else:
        input_context = console_input_from_keyboard_context(console, terminal)
        if args.enable_controller:
            input_context = combine_console_input_from_controller_context(input_context)

    if args.write_input:
        input_context = write_input_context(input_context, args.write_input)

    if args.color_mode not in [None, 1, 2, 3, 4]:
        exit(
            f"Invalid color mode `{args.color_mode}`: the value must be between 1 and 4"
        )

    # Enter terminal raw mode
    with terminal.raw():
        try:
            # Detect color mode
            if args.color_mode is None:
                args.color_mode = detect_local_color_mode(terminal)
                if args.color_mode == ColorMode.COULD_NOT_DETECT:
                    # TODO: add a prompt to ask the user to choose a color mode
                    # instead of silently falling back to 8-bit
                    args.color_mode = ColorMode.HAS_8_BIT_COLOR

            # Prepare alternate screen
            terminal.stream.write(
                terminal.enter_fullscreen + terminal.clear + terminal.hide_cursor
            )
            terminal.stream.flush()

            # Enter input and audio contexts
            with input_context as get_gb_input:
                player = no_audio if disable_audio else audio_player
                with player(console, args.speed) as audio_out:
                    # Run the emulator
                    run(
                        console,
                        get_gb_input,
                        term=terminal,
                        audio_out=audio_out,
                        frame_advance=args.frame_advance,
                        color_mode=args.color_mode,
                        break_after=args.break_after,
                        speed=args.speed,
                        use_cpr_sync=args.cpr_sync,
                        no_sextants=args.no_sextants or args.cp437,
                        use_octants=args.octants and not args.cp437,
                        cp437=args.cp437,
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
            terminal.stream.write(
                terminal.clear + terminal.exit_fullscreen + terminal.normal_cursor
            )
            terminal.stream.flush()


if __name__ == "__main__":
    main()
