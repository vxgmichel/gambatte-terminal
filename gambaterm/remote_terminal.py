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

    Overrides ``__init__streams`` to wire the remote pipe fds before
    the XTGETTCAP probe runs during ``super().__init__``, so blessed's
    native initialization handles terminal capability discovery
    (TN, RGB, colors, etc.) automatically.

    Stubs raw/cbreak mode (the remote connection is already raw) and
    overrides size detection to use values provided by the server.
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

    def __init__streams(self) -> None:
        """Set up stream fds for a remote pipe connection.

        Called by ``blessed.Terminal.__init__`` before the XTGETTCAP
        probe.  We set ``_keyboard_fd`` to the remote input pipe so
        blessed can probe the terminal's actual capabilities.
        """
        # Only UTF-8 encoding is supported. Our blitter writes raw
        # UTF-8 bytes directly to the fd, and modern terminals are
        # universally UTF-8.  Non-UTF-8 terminals (legacy Windows
        # console, legacy X11 with ISO 8859-1, real hardware terminals)
        # are not supported.
        assert self._stream is not None
        stream_fd = self._stream.fileno()
        self._init_descriptor = stream_fd  # type: ignore[assignment]
        self._is_a_tty = True
        self._keyboard_fd = self._remote_keyboard_fd  # type: ignore[assignment]
        self._encoding = "UTF-8"
        self._keyboard_decoder = codecs.getincrementaldecoder(self._encoding)()

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
