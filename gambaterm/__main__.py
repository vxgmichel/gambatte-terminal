#!/usr/bin/env python3

import shutil
import argparse

from .run import run, purge
from .xinput import gb_input_context, cbreak_mode

CSI = b"\033["


def main(args=None):
    parser = argparse.ArgumentParser(description='Gambatte terminal frontend')
    parser.add_argument('romfile', metavar='ROM', type=str)
    parser.add_argument('--test', '-t', action='store_true')
    parser.add_argument('--fast', '-f', action='store_true')
    args = parser.parse_args(args)

    with cbreak_mode() as (stdin, stdout):
        try:
            stdout.write(CSI + b"2J")
            with gb_input_context() as get_gb_input:
                return_code = run(
                    args.romfile,
                    get_gb_input,
                    stdin=stdin,
                    stdout=stdout,
                    get_size=shutil.get_terminal_size,
                    test=args.test,
                    fast=args.fast,
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
