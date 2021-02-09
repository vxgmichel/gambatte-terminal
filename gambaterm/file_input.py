from io import TextIOWrapper
from contextlib import contextmanager
from zipfile import ZipFile, BadZipFile

from .constants import GBInput


INPUTS = [
    GBInput.UP,
    GBInput.DOWN,
    GBInput.LEFT,
    GBInput.RIGHT,
    GBInput.START,
    GBInput.SELECT,
    GBInput.B,
    GBInput.A,
]


@contextmanager
def open_input_log_file(path):
    try:
        with ZipFile(path) as myzip:
            with myzip.open("Input Log.txt") as myfile:
                yield TextIOWrapper(myfile, "utf-8")
    except BadZipFile:
        with open(path) as myfile:
            yield myfile


@contextmanager
def gb_input_from_file_context(path, skip_first_frames=188):
    with open_input_log_file(path) as f:

        def gen():
            for i, line in enumerate(f):
                if not line.startswith("|"):
                    continue
                if i < skip_first_frames:
                    continue
                c = sum(v for c, v in zip(line[1:9], INPUTS) if c != ".")
                yield c
            while True:
                yield 0

        input_generator = gen()
        yield lambda: next(input_generator)
