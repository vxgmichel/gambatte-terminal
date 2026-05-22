"""
Provide a blessed Terminal subclass for remote (SSH/telnet) streams.
"""

from __future__ import annotations

import codecs
import contextlib
from typing import IO, Generator

from blessed import Terminal as BlessedTerminal
from blessed.terminal import WINSZ


class RemoteTerminal(BlessedTerminal):
    """A blessed Terminal subclass for remote streams (SSH, telnet).

    Stubs raw/cbreak mode (the remote connection is already raw) and
    overrides size detection to use server protocol-negotiated values.

    Callers should invoke ``get_xtgettcap()`` after initialization
    to probe the terminal's true capabilities once the connection
    is fully established.
    """
    def __init__(
        self,
        stream: IO[str],
        keyboard_fd: int,
        rows: int,
        columns: int,
        kind: str | None = None,
    ) -> None:
        self._rows = rows
        self._columns = columns
        self._remote_keyboard_fd = keyboard_fd
        super().__init__(
            kind=kind,
            stream=stream,
            force_styling=True,
            kind_fallback="xterm-256color",
        )
        # wire `_keyboard_fd` and enable `_is_a_tty` *after* class initialization.
        self._keyboard_fd = self._remote_keyboard_fd  # type: ignore[assignment]
        self._is_a_tty = True
        self._keyboard_decoder = codecs.getincrementaldecoder("UTF-8")()

    def probe_xtgettcap(self, timeout: float = 1.0) -> None:
        """Probe terminal capabilities via XTGETTCAP and apply results.

        Must be called after the remote connection is established and after kitty keyboard detection
        to prevent interference.  Uses ``force=True`` because blessed thought we were not a terminal
        when first initialized.
        """
        self._xtgettcap_cache = self._Terminal__init__xtgettcap()  # type: ignore[assignment]
        self.number_of_colors = self._Terminal__init__color_capabilities()  # type: ignore[assignment]

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
