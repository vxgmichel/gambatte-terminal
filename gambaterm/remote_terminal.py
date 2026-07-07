"""
Provide common resources for both Telnet and SSH terminals.
"""

from __future__ import annotations

import codecs
from concurrent.futures import ThreadPoolExecutor, CancelledError
from enum import Enum, auto
import hashlib
import contextlib
from typing import IO, Callable, Generator, TypeAlias, TYPE_CHECKING

from blessed import Terminal as BlessedTerminal
from blessed.terminal import WINSZ

if TYPE_CHECKING:
    from .main import AppConfig
    from blessed.terminal import SoftwareVersion


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


class KeyboardSupport(Enum):
    BASIC = "basic"
    KEYBOARD_PROTOCOL = "keyboard_protocol"
    X11 = "x11"


class GraphicsProtocol(Enum):
    TEXT = auto()
    SIXEL = auto()
    KITTY = auto()
    BLITLESS_SIXEL = auto()


def does_sixel(
    term: BlessedTerminal, timeout: float = 1.0, sv: SoftwareVersion | None = None
) -> bool:
    """Check if the terminal supports sixel graphics.

    Includes workarounds for terminals that report sixel support in error.
    """
    if not term.does_sixel(timeout=timeout):
        return False
    if sv is None:
        sv = term.get_software_version(timeout=timeout)
    if sv is None:
        return True
    if sv.name.lower() == "rio" and version_in_range(sv.version, "0.3", "0.4.9"):
        # rio supported sixel, then broke it in 0.4 release (still reports
        # support via DA/XTGETTCAP), fixed in 0.4.9+.
        return False
    return True


def version_in_range(version: str, lo_excl: str, hi_excl: str) -> bool:
    """Return True if *version* is in (lo_excl, hi_excl)."""
    # Strip pre-release suffixes (e.g. "0.4.0-alpha") before numeric parse.
    _nums = __import__("re").split(r"[^\d]", version)
    v = tuple(int(p) for p in _nums if p)
    lo = tuple(int(p) for p in lo_excl.split("."))
    hi = tuple(int(p) for p in hi_excl.split("."))
    return lo < v < hi


class KeyboardSupportDetection:
    def __init__(
        self,
        terminal: RemoteTerminal,
        display: str | None = None,
        executor: ThreadPoolExecutor | None = None,
    ) -> None:
        self.terminal = terminal
        self.display = display
        self.executor = executor
        self._cache: KeyboardSupport | None = None

    def get(self, timeout: float = 3.0) -> KeyboardSupport:
        if self._cache is not None:
            return self._cache
        self._cache = self._detect(timeout)
        return self._cache

    def _detect(self, timeout: float = 3.0) -> KeyboardSupport:
        from .keyboard_input import is_kitty_keyboard_protocol_supported

        if is_kitty_keyboard_protocol_supported(self.terminal, timeout=timeout):
            return KeyboardSupport.KEYBOARD_PROTOCOL

        elif self.display and self.executor:
            from .x11_keyboard_input import is_x11_display_functional

            try:
                if self.executor.submit(is_x11_display_functional, self.display).result(
                    timeout=timeout
                ):
                    return KeyboardSupport.X11
            except CancelledError:
                pass

        return KeyboardSupport.BASIC


FORCE_SIXEL_BLITLESS = ("contour", "tabby", "konsole", "mlterm", "iterm2")
FORCE_KITTY_BLITLESS = ("rio", "ghostty")

# Terminals with corrupted unicode font rendering; always prefer graphics.
BAD_TEXT = ("rio", "mlterm")


def detect_graphics_frontend(
    terminal: RemoteTerminal,
    config: "AppConfig",
    keyboard_detection: KeyboardSupportDetection,
) -> "AppConfig":
    """Probe terminal graphics capabilities and set config.graphics_protocol.

    Detects both kitty and sixel support, preferring kitty for the
    initial protocol.  The runtime can later cycle through all
    available protocols.
    """
    has_kitty = keyboard_detection.get() == KeyboardSupport.KEYBOARD_PROTOCOL
    has_sixel = does_sixel(terminal)

    sv = terminal.get_software_version(timeout=1.0)
    blitless = sv is not None and sv.name.lower() in FORCE_SIXEL_BLITLESS
    config.available_graphics = [GraphicsProtocol.TEXT]
    if blitless:
        config.available_graphics.append(GraphicsProtocol.BLITLESS_SIXEL)
        config.graphics_protocol = GraphicsProtocol.TEXT
        return config
    if has_kitty:
        config.available_graphics.append(GraphicsProtocol.KITTY)
    if has_sixel:
        config.available_graphics.append(GraphicsProtocol.SIXEL)

    if has_sixel:
        config.graphics_protocol = GraphicsProtocol.SIXEL
    elif has_kitty:
        config.graphics_protocol = GraphicsProtocol.KITTY

    return config


FrontendCallback: TypeAlias = Callable[
    [RemoteTerminal, "AppConfig", KeyboardSupportDetection], "AppConfig"
]


def make_graphics_frontend(graphics_value: str) -> FrontendCallback | None:
    """Return a FrontendCallback for the given --graphics value, or None.

    ``"auto"`` returns :func:`detect_graphics_frontend`.  Explicit protocol
    names return a callback that forces that protocol.  ``"text"`` returns
    ``None`` (no frontend callback needed).
    """
    if graphics_value == "auto":
        return detect_graphics_frontend
    if graphics_value != "text":

        def force_graphics(
            term: RemoteTerminal,
            config: "AppConfig",
            kbd: KeyboardSupportDetection,
        ) -> "AppConfig":
            config.graphics_protocol = GraphicsProtocol[graphics_value.upper()]
            config.available_graphics = [
                GraphicsProtocol.TEXT,
                config.graphics_protocol,
            ]
            return config

        return force_graphics
    return None


def user_directory_name(username: str | None) -> str:
    """Hash the username into a safe directory name.

    :param username: telnet/ssh-negotiated username, or ``None``
    :returns: hex digest suitable for use as a directory name
    """
    if username is None:
        return "_anonymous"
    return hashlib.sha256(username.encode("utf-8")).hexdigest()[:16]
