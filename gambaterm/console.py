from __future__ import annotations

import argparse
from pathlib import Path
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

    @classmethod
    def pop_console_arguments(
        cls, namespace: argparse.Namespace
    ) -> Callable[[], Console]:
        romfile: Path = namespace.romfile
        return lambda: cls(romfile)

    def __init__(self, romfile: Path):
        self.romfile = str(romfile.resolve())

    def set_input(self, input_set: set[Console.Input]) -> None:
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

    @classmethod
    def add_console_arguments(cls, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--force-gameboy",
            "--fg",
            action="store_true",
            help="Force the emulator to treat the rom as a GB file",
        )
        parser.add_argument(
            "--save-directory",
            "--sd",
            type=Path,
            default=None,
            help="Path to the save directory",
        )

    @classmethod
    def pop_console_arguments(
        cls, namespace: argparse.Namespace
    ) -> Callable[[], Console]:
        romfile: Path = namespace.romfile
        input_file: Path | None = namespace.input_file
        force_gameboy: bool = namespace.__dict__.pop("force_gameboy")
        save_directory: Path | None = namespace.__dict__.pop("save_directory")
        # Save directory defaults to the rom file directory (unless we read the input from a file)
        if input_file is None and save_directory is None:
            save_directory = romfile.parent
        return lambda: cls(romfile, save_directory, force_gameboy)

    def __init__(
        self,
        romfile: Path,
        save_directory: Path | None = None,
        force_gameboy: bool = False,
    ):
        super().__init__(romfile)

        self.gb = GB()
        self.force_gameboy = force_gameboy

        # Set save_directory
        if save_directory is not None:
            save_directory.mkdir(parents=True, exist_ok=True)
            self.gb.set_save_directory(str(save_directory.resolve()))
        # Use a temporary directory if the save directory is not explicitely provided
        else:
            self.gb.set_save_directory(tempfile.mkdtemp())

        # Load the rom
        return_code = self.gb.load(self.romfile, 0 if self.force_gameboy else 1)
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

    def set_current_state(self, state: int) -> None:
        self.gb.select_state(state % 10)

    def load_state(self) -> None:
        self.gb.load_state()

    def save_state(self) -> None:
        self.gb.save_state(self.last_video, self.WIDTH)
