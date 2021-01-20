from enum import IntEnum
from pathlib import Path
from zipfile import ZipFile, BadZipFile


class GBInput(IntEnum):
    A = 0x01
    B = 0x02
    SELECT = 0x04
    START = 0x08
    RIGHT = 0x10
    LEFT = 0x20
    UP = 0x40
    DOWN = 0x80


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


def read_input_file(path, skip_first_frames=188):
    try:
        with ZipFile(path) as myzip:
            with myzip.open("Input Log.txt") as myfile:
                data = myfile.read().decode("utf-8")
    except BadZipFile:
        data = Path(path).read_text()

    def gen():
        for i, line in enumerate(data.splitlines()):
            if not line.startswith("|"):
                continue
            if i < skip_first_frames:
                continue
            c = sum(v for c, v in zip(line[1:9], INPUTS) if c != ".")
            yield c
        while True:
            yield 0

    return gen().__next__
