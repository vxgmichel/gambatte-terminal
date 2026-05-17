"""
Provide a blessed Terminal subclass for remote (SSH/telnet) streams.
"""

from __future__ import annotations

import codecs
import hashlib
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
        """
        Probe terminal capabilities via XTGETTCAP and apply results.

        This allows to improved 'number_of_colors' detection, and, to "overlay" capabilities not
        found in jinxed terminfo database but detected by XTGETTCAP: 'blink', 'sitm', 'ritm',
        'cvvis', 'Smulx', 'Setulc', 'Ms', the same way that blessed.Terminal() would have but we
        is_a_tty was detected False when we initialized it.

        This method is not called or used by gambaterm-ssh or gambaterm-telnet, because the above
        capabilities are not used and kitty keyboard support pretty reliably suggests 24-bit color
        support.
        """
        self._xtgettcap_cache = self._Terminal__init__xtgettcap()  # type: ignore[assignment]
        self.number_of_colors = self._Terminal__init__color_capabilities()  # type: ignore[assignment]
        if self._xtgettcap_cache.supported and self.does_styling:
            self._jinxed_term.overlay_capabilities(
                **self._xtgettcap_cache.make_jinxed_capabilities()
            )

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


def user_directory_name(username: str | None) -> str:
    """Hash the username into a safe directory name.

    :param username: telnet/ssh-negotiated username, or ``None``
    :returns: hex digest suitable for use as a directory name
    """
    if username is None:
        return "_anonymous"
    return hashlib.sha256(username.encode("utf-8")).hexdigest()[:16]
