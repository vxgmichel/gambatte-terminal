"""Sextant block rendering for terminal display.

Encodes 2x3 pixel blocks into Unicode sextant characters (U+1FB00-U+1FB3B),
For up to 80x48 terminal cells for a 160x144 Game Boy display.
"""

from __future__ import annotations

__all__ = ["SEXTANT", "blit_sextant"]


def _build_sextant_table() -> list[str]:
    """Build lookup table mapping 6-bit pattern to Unicode sextant character.

    Bit positions correspond to the 2x3 cell grid::

        bit0  bit1
        bit2  bit3
        bit4  bit5

    Patterns 0 (empty), 21 (left half), 42 (right half), and 63 (full block)
    map to pre-existing block element characters; the remaining 60 patterns
    map to U+1FB00..U+1FB3B.
    """
    table = [""] * 64
    for i in range(64):
        if i == 0:
            table[i] = " "
        elif i == 21:
            table[i] = "\u258c"
        elif i == 42:
            table[i] = "\u2590"
        elif i == 63:
            table[i] = "\u2588"
        else:
            offset = i
            if i > 42:
                offset -= 3
            elif i > 21:
                offset -= 2
            else:
                offset -= 1
            table[i] = chr(0x1FB00 + offset)
    return table


SEXTANT = _build_sextant_table()

from .sextblit import (  # noqa: E402, F401
    blit_sextant,
    clear_cache as _clear_cache,
)


class _CacheProxy:
    """Proxy so tests can call _display_cache.clear() to reset the C cache."""

    def clear(self) -> None:
        _clear_cache()


_display_cache = _CacheProxy()
