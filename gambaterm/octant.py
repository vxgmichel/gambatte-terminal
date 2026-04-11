"""Octant block rendering for terminal display.

Encodes 2x4 pixel blocks into Unicode octant characters (U+1CD00-U+1CDE5),
For display up to 80x36 terminal size for a 160x144 Game Boy display.

Requires a Unicode 17.0-capable font, like gnu's unifont 17.0 or later.
"""

from __future__ import annotations

__all__ = ["OCTANT", "blit_octant"]

from bisect import bisect_left

# 26 octant bit patterns that map to pre-existing block element characters
# rather than the U+1CD00 octant range.  Derived from the Unicode 17.0 chart
# and https://gist.github.com/Explorer09/1da382e4b1cf3bf2e8009e60836af70b
#
# Bit layout in the 2x4 cell grid:
#
#     bit0  bit1
#     bit2  bit3
#     bit4  bit5
#     bit6  bit7
_OCTANT_SPECIALS: dict[int, int] = {
    0x00: 0x00A0,  # NO-BREAK SPACE
    0x01: 0x1CEA8,  # LEFT HALF UPPER ONE QUARTER BLOCK
    0x02: 0x1CEAB,  # RIGHT HALF UPPER ONE QUARTER BLOCK
    0x03: 0x1FB82,  # UPPER ONE QUARTER BLOCK
    0x05: 0x2598,  # QUADRANT UPPER LEFT
    0x0A: 0x259D,  # QUADRANT UPPER RIGHT
    0x0F: 0x2580,  # UPPER HALF BLOCK
    0x14: 0x1FBE6,  # MIDDLE LEFT ONE QUARTER BLOCK
    0x28: 0x1FBE7,  # MIDDLE RIGHT ONE QUARTER BLOCK
    0x3F: 0x1FB85,  # UPPER THREE QUARTERS BLOCK
    0x40: 0x1CEA3,  # LEFT HALF LOWER ONE QUARTER BLOCK
    0x50: 0x2596,  # QUADRANT LOWER LEFT
    0x55: 0x258C,  # LEFT HALF BLOCK
    0x5A: 0x259E,  # QUADRANT UPPER RIGHT AND LOWER LEFT
    0x5F: 0x259B,  # QUADRANT UPPER LEFT AND UPPER RIGHT AND LOWER LEFT
    0x80: 0x1CEA0,  # RIGHT HALF LOWER ONE QUARTER BLOCK
    0xA0: 0x2597,  # QUADRANT LOWER RIGHT
    0xA5: 0x259A,  # QUADRANT UPPER LEFT AND LOWER RIGHT
    0xAA: 0x2590,  # RIGHT HALF BLOCK
    0xAF: 0x259C,  # QUADRANT UPPER LEFT AND UPPER RIGHT AND LOWER RIGHT
    0xC0: 0x2582,  # LOWER ONE QUARTER BLOCK
    0xF0: 0x2584,  # LOWER HALF BLOCK
    0xF5: 0x2599,  # QUADRANT UPPER LEFT AND LOWER LEFT AND LOWER RIGHT
    0xFA: 0x259F,  # QUADRANT UPPER RIGHT AND LOWER LEFT AND LOWER RIGHT
    0xFC: 0x2586,  # LOWER THREE QUARTERS BLOCK
    0xFF: 0x2588,  # FULL BLOCK
}

_SPECIAL_KEYS_SORTED: list[int] = sorted(_OCTANT_SPECIALS)


def _build_octant_table() -> list[str]:
    """Build lookup table mapping 8-bit pattern to Unicode octant character.

    Bit positions correspond to the 2x4 cell grid::

        bit0  bit1
        bit2  bit3
        bit4  bit5
        bit6  bit7

    26 patterns map to pre-existing block element characters; the remaining
    230 patterns map to U+1CD00..U+1CDE5.
    """
    table = [""] * 256
    for i in range(256):
        if i in _OCTANT_SPECIALS:
            table[i] = chr(_OCTANT_SPECIALS[i])
        else:
            offset = bisect_left(_SPECIAL_KEYS_SORTED, i)
            table[i] = chr(0x1CD00 + i - offset)
    return table


OCTANT = _build_octant_table()

from .octblit import (  # noqa: E402, F401
    blit_octant,
    clear_cache as _clear_cache,
)


class _CacheProxy:
    """Proxy so tests can call _display_cache.clear() to reset the C cache."""

    def clear(self) -> None:
        _clear_cache()


_display_cache = _CacheProxy()
