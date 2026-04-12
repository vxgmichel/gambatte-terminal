"""
Provide a blessed Terminal subclass for remote (SSH/telnet) streams.
"""

from __future__ import annotations

import codecs
import contextlib
from typing import IO, Generator

from blessed import Terminal as BlessedTerminal
from blessed.terminal import WINSZ

# Python's curses.setupterm() can only be called once per process — subsequent
# calls with a different terminal type are silently ignored. Since the SSH
# server handles multiple concurrent connections in threads, all RemoteTerminal
# instances share whatever terminal type was initialized first by the local
# Terminal(). We hardcode 'xterm-256color' as the kind since:
#   1. It's universally compatible with modern terminals
#   2. We use standard VT100/ANSI escape codes directly, not terminfo caps
#   3. It avoids issues where the first client's TERM value differs from subsequent
REMOTE_TERMINAL_TYPE = "xterm-256color"


class RemoteTerminal(BlessedTerminal):
    """A blessed Terminal subclass for remote streams (SSH, telnet).

    Stubs raw/cbreak mode (the remote connection is already raw) and
    overrides size detection to use values provided by the server.
    """

    def __init__(
        self,
        stream: IO[str],
        keyboard_fd: int,
        rows: int,
        columns: int,
    ) -> None:
        self._rows = rows
        self._columns = columns
        super().__init__(kind=REMOTE_TERMINAL_TYPE, stream=stream, force_styling=True)
        # Blessed only sets _keyboard_fd when stream is sys.__stdout__, so
        # for remote pipes we must set it and initialize the decoder manually
        self._keyboard_fd = keyboard_fd  # type: ignore[assignment]
        self._keyboard_decoder = codecs.getincrementaldecoder("UTF-8")()

    @property
    def is_a_tty(self) -> bool:
        return True

    @contextlib.contextmanager
    def raw(self) -> Generator[None, None, None]:
        yield

    @contextlib.contextmanager
    def cbreak(self) -> Generator[None, None, None]:
        yield

    def _height_and_width(self) -> WINSZ:
        return WINSZ(
            ws_row=self._rows,
            ws_col=self._columns,
            ws_xpixel=0,
            ws_ypixel=0,
        )

    def update_size(self, rows: int, columns: int) -> None:
        self._rows = rows
        self._columns = columns
