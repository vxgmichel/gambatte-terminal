#!/usr/bin/env python3
from __future__ import annotations

import time
import logging
import argparse
from pathlib import Path
from typing import Any, ContextManager, Optional, TYPE_CHECKING
import dataclasses
from dataclasses import dataclass, field

from blessed import Terminal

from .run import run
from .console import GameboyColor, Console
from .audio import audio_player
from .colors import detect_local_color_mode, ColorMode
from .input_getter import BaseInputGetter
from .keyboard_input import console_input_from_keyboard_context
from .controller_input import combine_console_input_from_controller_context
from .file_input import console_input_from_file_context, write_input_context

# `typing.Self` is not available in python 3.10
if TYPE_CHECKING:
    from typing import Self

_DEFAULT_LOGFMT = " ".join(("%(levelname)s", "%(filename)s:%(lineno)d", "%(message)s"))


def make_logger(
    name: str,
    loglevel: str = "info",
    logfile: Optional[str] = None,
    logfmt: str = _DEFAULT_LOGFMT,
    filemode: str = "a",
) -> logging.Logger:
    """Create and return a configured logger (following telnetlib3 pattern)."""
    lvl = getattr(logging, loglevel.upper(), None)
    if lvl is None:
        lvl = logging.getLevelName(loglevel.upper())
    _cfg: dict[str, Any] = {"format": logfmt}
    if logfile:
        _cfg["filename"] = logfile
        _cfg["filemode"] = filemode
    logging.basicConfig(**_cfg)
    logging.getLogger().setLevel(lvl)
    logging.getLogger(name).setLevel(lvl)
    return logging.getLogger(name)


def add_logging_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--logfile", default=None, help="File path for log output (default: stderr)"
    )
    parser.add_argument(
        "--loglevel",
        default="warn",
        help="Logging level: debug, info, warn, error (default: warn)",
    )
    parser.add_argument(
        "--logfmt",
        default=_DEFAULT_LOGFMT,
        help="Log format string (default: LEVEL file:lineno message)",
    )


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
        "for the lack of BIOS (default is 188)",
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
        "--cpr-sync",
        "--cs",
        action="store_true",
        help="Use CPR synchronization to prevent video buffering",
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
        "--save-directory",
        "--sd",
        type=Path,
        default=None,
        help="Path to the save directory (default to the ROM directory)",
    )


def main(
    parser_args: tuple[str, ...] | None = None,
    console_cls: type[Console] = GameboyColor,
) -> None:
    # Create parser
    parser = argparse.ArgumentParser(
        prog="gambaterm", description="Gambatte terminal front-end"
    )
    add_base_arguments(parser)
    add_input_file_arguments(parser)
    add_tuning_arguments(parser)
    add_logging_arguments(parser)
    add_local_only_arguments(parser)
    console_cls.add_console_arguments(parser)

    # Parse arguments
    namespace = parser.parse_args(parser_args)
    make_logger(
        __name__,
        loglevel=getattr(namespace, "loglevel", "warn"),
        logfile=getattr(namespace, "logfile", None),
        logfmt=getattr(namespace, "logfmt", _DEFAULT_LOGFMT),
    )
    disable_audio = getattr(namespace, "disable_audio", False)
    args = LocalAppConfig.from_namespace(namespace)

    # Check that the ROM file exists
    if not args.romfile.exists():
        raise SystemExit(f"ROM file `{args.romfile}` does not exist")

    # Instantiate the console and terminal
    console = console_cls.from_app_config(args)
    terminal = Terminal()

    # Prepare input context
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
                with audio_player(console, args.speed, disable_audio) as audio_out:
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
