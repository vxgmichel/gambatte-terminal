import argparse
import tempfile
from enum import IntEnum
from typing import Optional, Callable

import numpy as np
import numpy.typing as npt

from .libgambatte import GB


class Console:
    WIDTH: int = NotImplemented
    HEIGHT: int = NotImplemented
    FPS: float = NotImplemented
    TICKS_IN_FRAME: int = NotImplemented

    class Input(IntEnum):
        A = 0x01
        B = 0x02
        SELECT = 0x04
        START = 0x08
        RIGHT = 0x10
        LEFT = 0x20
        UP = 0x40
        DOWN = 0x80

    romfile: str

    @classmethod
    def add_console_arguments(cls, parser: argparse.ArgumentParser) -> None:
        pass

    def __init__(self, args: argparse.Namespace):
        self.romfile = args.romfile

    def set_input(self, value: set["Console.Input"]) -> None:
        pass

    def advance_one_frame(
        self, video: npt.NDArray[np.uint32], audio: npt.NDArray[np.int16]
    ) -> tuple[int, int]:
        raise NotImplementedError


# Type Alias
InputGetter = Callable[[], set[Console.Input]]


class GameboyColor(Console):
    WIDTH: int = 160
    HEIGHT: int = 144
    FPS: float = 59.727500569606
    TICKS_IN_FRAME: int = 35112

    gb: GB
    force_gameboy: bool
    save_directory: Optional[str]

    @classmethod
    def add_console_arguments(cls, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--force-gameboy",
            "--fg",
            action="store_true",
            help="Force the emulator to treat the rom as a GB file",
        )

    def __init__(self, args: argparse.Namespace):
        super().__init__(args)
        self.gb = GB()
        self.force_gameboy = args.force_gameboy
        self.save_directory = (
            tempfile.mkdtemp() if args.input_file is not None else None
        )

        # Set save_directory
        if self.save_directory:
            self.gb.set_save_directory(self.save_directory)

        # Load the rom
        return_code = self.gb.load(self.romfile, 1 if self.force_gameboy else 0)
        if return_code != 0:
            # Make sure it exists
            open(self.romfile).close()
            raise RuntimeError(return_code)

    def set_input(self, input_set: set[Console.Input]) -> None:
        self.gb.set_input(sum(input_set))

    def advance_one_frame(
        self, video: npt.NDArray[np.uint32], audio: npt.NDArray[np.int16]
    ) -> tuple[int, int]:
        return self.gb.run_for(video, self.WIDTH, audio, self.TICKS_IN_FRAME)
