#!/usr/bin/env python3

import shutil
import tempfile
import argparse

from .run import run, purge
from .audio import audio_player
from .inputs import read_input_file
from .xinput import gb_input_context, cbreak_mode

CSI = b"\033["


def main(args=None):
    parser = argparse.ArgumentParser(description="Gambatte terminal frontend")
    parser.add_argument("romfile", metavar="ROM", type=str)
    parser.add_argument("--input-file", "-i", default=None)
    parser.add_argument("--true-color", "-c", action="store_true")
    parser.add_argument("--frame-advance", "-a", type=int, default=2)
    parser.add_argument("--frame-limit", "-l", type=int, default=None)
    parser.add_argument("--speed-factor", "-s", type=float, default=1.0)
    args = parser.parse_args(args)

    if args.input_file is not None:
        get_input_from_file = read_input_file(args.input_file)
        save_directory = tempfile.mkdtemp()
    else:
        get_input_from_file = None
        save_directory = None

    with audio_player() as audio_out:
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
                        true_color=args.true_color,
                        audio_out=audio_out,
                        frame_advance=args.frame_advance,
                        frame_limit=args.frame_limit,
                        speed_factor=args.speed_factor,
                        save_directory=save_directory,
                    )
            except KeyboardInterrupt:
                pass
            else:
                exit(return_code)
            finally:
                purge(stdin)
                stdout.write(CSI + b"0m" + CSI + b"2J" + b"\n")


if __name__ == "__main__":
    main()
