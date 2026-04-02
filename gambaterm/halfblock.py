"""Half-size halfblock rendering for terminal display.

Downscales the 160x144 Game Boy image by 2x in each dimension via 2x2
majority-vote, then renders using half-block characters (U+2580, U+2584,
U+2588) for up to 80x36 terminal cells.
"""

from __future__ import annotations

__all__ = ["blit_half"]

from .halfblit import (  # noqa: E402, F401
    blit_half,
    clear_cache as _clear_cache,
)


class _CacheProxy:
    """Proxy so tests can call _display_cache.clear() to reset the C cache."""

    def clear(self) -> None:
        _clear_cache()


_display_cache = _CacheProxy()
