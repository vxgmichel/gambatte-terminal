from io import TextIOWrapper
from contextlib import contextmanager
from zipfile import ZipFile, BadZipFile


def get_inputs_ref(console):
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


def value_to_line(console, value):
    result = "|"
    for key in get_inputs_ref(console):
        result += key.name[0].upper() if key & value else "."
    result += "|"
    return result


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
def console_input_from_file_context(console, path, skip_first_frames=188):
    inputs_ref = get_inputs_ref(console)
    with open_input_log_file(path) as f:

        def gen():
            for i, line in enumerate(f):
                if not line.startswith("|"):
                    continue
                if i < skip_first_frames:
                    continue
                c = sum(v for c, v in zip(line[1:9], inputs_ref) if c != ".")
                yield c
            while True:
                yield 0

        input_generator = gen()
        yield lambda: next(input_generator)


@contextmanager
def write_input_context(console, context, path):
    with open(path, "w") as f:
        with context as getter:

            def new_getter():
                value = getter()
                print(value_to_line(console, value), file=f)
                return value

            yield new_getter
