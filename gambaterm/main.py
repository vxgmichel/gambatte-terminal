#!/usr/bin/env python3
from __future__ import annotations

import time
import argparse
from pathlib import Path
from dataclasses import dataclass

from blessed import Terminal

from .run import run
from .console import GameboyColor, Console
from .audio import audio_player, no_audio
from .colors import detect_local_color_mode, ColorMode
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
    speed_factor: float
    skip_inputs: int
    cpr_sync: bool
    enable_controller: bool
    write_input: Path | None


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
        "(1: 4 greyscale colors, 2: 16 colors, 3: 256 colors, 4: 24-bit colors)",
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
        "--speed-factor",
        "--sf",
        type=float,
        default=1.0,
        help="Speed factor to apply to the emulation "
        "(default is 1.0 corresponding to 60 FPS)",
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

    term = Terminal()

    if args.input_file is not None:
        input_context = console_input_from_file_context(
            console, args.input_file, args.skip_inputs
        )
    else:
        input_context = console_input_from_keyboard_context(console, term)
        if args.enable_controller:
            input_context = combine_console_input_from_controller_context(
                console, input_context
            )

    if args.write_input:
        input_context = write_input_context(console, input_context, args.write_input)

    if args.color_mode not in [None, 1, 2, 3, 4]:
        exit(
            f"Invalid color mode `{args.color_mode}`: the value must be between 1 and 4"
        )

    # Enter terminal raw mode
    with term.raw():
        try:
            # Detect color mode
            if args.color_mode is None:
                args.color_mode = detect_local_color_mode(term)
                if args.color_mode == ColorMode.NO_COLOR:
                    raise exit(
                        """\
The ANSI color support for your terminal could not be detected from your environment.
Try to force a color mode using the `--color-mode` option with a value between 1 and 4."""
                    )

            # Prepare alternate screen
            term.stream.write(term.enter_fullscreen + term.clear + term.hide_cursor)
            term.stream.flush()

            # Enter input and audio contexts
            with input_context as get_gb_input:
                player = no_audio if disable_audio else audio_player
                with player(console, args.speed_factor) as audio_out:
                    # Run the emulator
                    run(
                        console,
                        get_gb_input,
                        term=term,
                        audio_out=audio_out,
                        frame_advance=args.frame_advance,
                        color_mode=args.color_mode,
                        break_after=args.break_after,
                        speed_factor=args.speed_factor,
                        use_cpr_sync=args.cpr_sync,
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
            term.stream.write(term.clear + term.exit_fullscreen + term.normal_cursor)
            term.stream.flush()


if __name__ == "__main__":
    main()
