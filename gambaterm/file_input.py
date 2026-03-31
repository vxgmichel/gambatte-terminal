from __future__ import annotations

from pathlib import Path
from io import TextIOWrapper
from contextlib import contextmanager
from zipfile import ZipFile, BadZipFile
from typing import ContextManager, Iterator

from blessed import Terminal

from .console import Console
from .input_getter import BaseInputGetter, StackedInputGetter


class FileInputGetter(BaseInputGetter):
    def __init__(
        self,
        console: Console,
        terminal: Terminal,
        input_generator: Iterator[set[Console.Input]],
    ) -> None:
        super().__init__(console, terminal)
        self._generator = input_generator

    def get_pressed(self) -> set[Console.Input]:
        return next(self._generator)


def get_inputs_ref(console: Console) -> list[Console.Input]:
    return [
        console.Input.UP,
        console.Input.DOWN,
        console.Input.LEFT,
        console.Input.RIGHT,
        console.Input.START,
        console.Input.SELECT,
        console.Input.B,
        console.Input.A,
    ]


def value_to_line(console: Console, input_set: set[Console.Input]) -> str:
    result = "|"
    for key in get_inputs_ref(console):
        result += key.name[0].upper() if key in input_set else "."
    result += "|"
    return result


@contextmanager
def open_input_log_file(path: Path) -> Iterator[TextIOWrapper]:
    try:
        with ZipFile(path) as myzip:
            with myzip.open("Input Log.txt") as myfile:
                yield TextIOWrapper(myfile, "utf-8")
        return
    except BadZipFile:
        pass
    with open(path) as myfile:
        yield myfile


@contextmanager
def console_input_from_file_context(
    console: Console, terminal: Terminal, path: Path, skip_first_frames: int = 188
) -> Iterator[FileInputGetter]:
    inputs_ref = get_inputs_ref(console)
    with open_input_log_file(path) as f:

        def gen() -> Iterator[set[Console.Input]]:
            for i, line in enumerate(f):
                if not line.startswith("|"):
                    continue
                if i < skip_first_frames:
                    continue
                c = set(v for c, v in zip(line[1:9], inputs_ref) if c != ".")
                yield c
            while True:
                yield set()

        input_generator = gen()
        yield FileInputGetter(console, terminal, input_generator)


class WriteInputGetter(StackedInputGetter):
    def __init__(self, base_getter: BaseInputGetter, file: TextIOWrapper) -> None:
        super().__init__(base_getter)
        self._file = file

    def get_pressed(self) -> set[Console.Input]:
        value = super().get_pressed()
        print(value_to_line(self.console, value), file=self._file)
        return value


@contextmanager
def write_input_context(
    context: ContextManager[BaseInputGetter], path: Path
) -> Iterator[WriteInputGetter]:
    with open(path, "w") as f:
        with context as base_getter:
            yield WriteInputGetter(base_getter, f)
