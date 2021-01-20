#!/usr/bin/env python3

import shutil
import select
import tempfile
import argparse

from .run import run
from .inputs import read_input_file
from .audio import audio_player, no_audio
from .colors import detect_local_color_mode
from .xinput import gb_input_context, cbreak_mode

CSI = b"\033["


def purge(stdin):
    while True:
        r, _, _ = select.select([stdin], (), (), 0)
        if not r:
            return
        stdin.read(1024)


def add_base_arguments(parser):
    parser.add_argument("romfile", metavar="ROM", type=str)
    parser.add_argument("--input-file", "-i", default=None)
    parser.add_argument("--frame-advance", "-fa", type=int, default=2)
    parser.add_argument("--break-after", "-ba", type=int, default=None)
    parser.add_argument("--speed-factor", "-sf", type=float, default=1.0)
    parser.add_argument("--force-gameboy", "-fg", action="store_true")
    parser.add_argument("--skip-inputs", "-si", type=int, default=188)
    return parser


def main(args=None):
    parser = argparse.ArgumentParser(
        prog="gambaterm", description="Gambatte terminal front-end"
    )
    add_base_arguments(parser)
    parser.add_argument("--disable-audio", "-d", action="store_true")
    parser.add_argument("--color-mode", "-c", type=int, default=None)
    args = parser.parse_args(args)

    if args.color_mode is None:
        args.color_mode = detect_local_color_mode()

    if args.input_file is not None:
        get_input_from_file = read_input_file(args.input_file)
        save_directory = tempfile.mkdtemp()
    else:
        get_input_from_file = None
        save_directory = None

    if args.color_mode == 0:
        raise RuntimeError("No color mode seems to be supported")

    player = no_audio if args.disable_audio else audio_player
    with player(args.speed_factor) as audio_out:
        with cbreak_mode() as (stdin, stdout):
            try:
                stdout.write(CSI + b"2J")
                with gb_input_context() as get_gb_input:
                    return_code = run(
                        args.romfile,
                        get_input_from_file or get_gb_input,
                        stdin=stdin,
                        stdout=stdout,
                        get_size=shutil.get_terminal_size,
                        color_mode=args.color_mode,
                        audio_out=audio_out,
                        frame_advance=args.frame_advance,
                        break_after=args.break_after,
                        speed_factor=args.speed_factor,
                        save_directory=save_directory,
                        force_gameboy=args.force_gameboy,
                    )
            except (KeyboardInterrupt, EOFError):
                pass
            else:
                exit(return_code)
            finally:
                purge(stdin)
                stdout.write(CSI + b"0m" + CSI + b"2J" + b"\n")


if __name__ == "__main__":
    main()
