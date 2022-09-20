from __future__ import annotations

from io import TextIOWrapper
from contextlib import contextmanager
from zipfile import ZipFile, BadZipFile
from typing import ContextManager, Iterator

from .console import Console, InputGetter


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
def open_input_log_file(path: str) -> Iterator[TextIOWrapper]:
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
    console: Console, path: str, skip_first_frames: int = 188
) -> Iterator[InputGetter]:
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
        yield lambda: next(input_generator)


@contextmanager
def write_input_context(
    console: Console, context: ContextManager[InputGetter], path: str
) -> Iterator[InputGetter]:
    with open(path, "w") as f:
        with context as getter:

            def new_getter() -> set[Console.Input]:
                value = getter()
                print(value_to_line(console, value), file=f)
                return value

            yield new_getter
