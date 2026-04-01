from blessed.keyboard import Keystroke
from blessed.terminal import Terminal

from .console import Console


def pop_keystrokes_from_terminal(terminal: Terminal) -> list[Keystroke]:
    return list(iter(lambda: terminal.inkey(timeout=0), ""))


class BaseInputGetter:
    """Base class for input getters.

    This class reports both:
    - the currently pressed console buttons
    - the keystrokes that occurred since the last call

    The reason why those apparently separated responsibilities are combined in the same class
    is that some input sources (e.g. keyboard with kitty protocol) provide both information through the same API.

    It provides default implementation for pop_keystrokes() that reads from the terminal,
    which is useful for input sources that do not mess with the terminal input.

    More practically:
    - KittyInputGetter: reports pressed console buttons and keystrokes from the terminal using the kitty keyboard protocol
    - X11InputGetter: reports pressed console buttons from X11 events, and reports keystrokes from the terminal
    - PynputInputGetter: reports pressed console buttons from OS key hooks, and reports keystrokes from the terminal
    - FileInputGetter: reports pressed console buttons from a file, and reports keystrokes from the terminal
    """

    def __init__(self, console: Console, terminal: Terminal) -> None:
        self._console = console
        self._terminal = terminal

    @property
    def console(self) -> Console:
        return self._console

    @property
    def terminal(self) -> Terminal:
        return self._terminal

    def get_pressed(self) -> set[Console.Input]:
        """Get the currently pressed inputs."""
        raise NotImplementedError

    def pop_keystrokes(self) -> list[Keystroke]:
        """Get the keystrokes that occurred since the last call."""
        return pop_keystrokes_from_terminal(self.terminal)


class StackedInputGetter(BaseInputGetter):
    """
    BaseInputGetter that combines the pressed inputs of a base getter with extra pressed inputs from another callable.

    This is useful to combine multiple input sources, e.g. keyboard and controller.

    More pratically:
    - ControllerInputGetter: add console inputs from a controller on top of another input getter
    - WriteInputGetter: write the console inputs from another input getter to a file, without modifying them
    """

    def __init__(self, base_getter: BaseInputGetter) -> None:
        self.base_getter = base_getter

    @property
    def console(self) -> Console:
        return self.base_getter.console

    @property
    def terminal(self) -> Terminal:
        return self.base_getter.terminal

    def get_pressed(self) -> set[Console.Input]:
        return self.base_getter.get_pressed()

    def pop_keystrokes(self) -> list[Keystroke]:
        return self.base_getter.pop_keystrokes()
