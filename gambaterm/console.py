from __future__ import annotations

import argparse
import tempfile
from enum import IntEnum
from typing import Callable, Set

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

    class Event(IntEnum):
        SELECT_STATE_0 = 0
        SELECT_STATE_1 = 1
        SELECT_STATE_2 = 2
        SELECT_STATE_3 = 3
        SELECT_STATE_4 = 4
        SELECT_STATE_5 = 5
        SELECT_STATE_6 = 6
        SELECT_STATE_7 = 7
        SELECT_STATE_8 = 8
        SELECT_STATE_9 = 9
        INCREMENT_STATE = 10
        DECREMENT_STATE = 11
        LOAD_STATE = 12
        SAVE_STATE = 13

    romfile: str
    last_video: npt.NDArray[np.uint32] | None

    @classmethod
    def add_console_arguments(cls, parser: argparse.ArgumentParser) -> None:
        pass

    def __init__(self, args: argparse.Namespace):
        self.romfile = args.romfile

    def set_input(self, value: set[Input]) -> None:
        pass

    def advance_one_frame(
        self, video: npt.NDArray[np.uint32], audio: npt.NDArray[np.int16]
    ) -> tuple[int, int]:
        raise NotImplementedError

    def get_current_state(self) -> int:
        raise NotImplementedError

    def set_current_state(self, state: int) -> None:
        raise NotImplementedError

    def load_state(self) -> None:
        raise NotImplementedError

    def save_state(self) -> None:
        raise NotImplementedError

    def handle_event(self, event: Event) -> None:
        if event.value < 10:
            self.set_current_state(event.value)
        elif event == event.INCREMENT_STATE:
            self.set_current_state(self.get_current_state() + 1)
        elif event == event.DECREMENT_STATE:
            self.set_current_state(self.get_current_state() - 1)
        elif event == event.LOAD_STATE:
            self.load_state()
        elif event == event.SAVE_STATE:
            self.save_state()
        else:
            assert False


# Type Alias
InputGetter = Callable[[], Set[Console.Input]]


class GameboyColor(Console):
    WIDTH: int = 160
    HEIGHT: int = 144
    FPS: float = 59.727500569606
    TICKS_IN_FRAME: int = 35112

    gb: GB
    force_gameboy: bool
    save_directory: str | None

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
        self.last_video = video
        return self.gb.run_for(video, self.WIDTH, audio, self.TICKS_IN_FRAME)

    def get_current_state(self) -> int:
        return self.gb.current_state() % 10

    def set_current_state(self, value: int) -> None:
        self.gb.select_state(value % 10)

    def load_state(self) -> None:
        self.gb.load_state()

    def save_state(self) -> None:
        self.gb.save_state(self.last_video, self.WIDTH)
