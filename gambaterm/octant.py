"""Octant block rendering for terminal display.

Encodes 2x4 pixel blocks into Unicode octant characters (U+1CD00-U+1CDE5),
For display up to 80x36 terminal size for a 160x144 Game Boy display.

Requires a Unicode 17.0-capable font, like gnu's unifont 17.0 or later.
"""
from __future__ import annotations

from bisect import bisect_left
from itertools import combinations

import numpy as np
import numpy.typing as npt

from .sextant import (
    _COLOR_PAIR_HYSTERESIS,
    _color_distance,
    _move_relative,
    _set_color,
)

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
    0x00: 0x00A0,   # NO-BREAK SPACE
    0x01: 0x1CEA8,  # LEFT HALF UPPER ONE QUARTER BLOCK
    0x02: 0x1CEAB,  # RIGHT HALF UPPER ONE QUARTER BLOCK
    0x03: 0x1FB82,  # UPPER ONE QUARTER BLOCK
    0x05: 0x2598,   # QUADRANT UPPER LEFT
    0x0A: 0x259D,   # QUADRANT UPPER RIGHT
    0x0F: 0x2580,   # UPPER HALF BLOCK
    0x14: 0x1FBE6,  # MIDDLE LEFT ONE QUARTER BLOCK
    0x28: 0x1FBE7,  # MIDDLE RIGHT ONE QUARTER BLOCK
    0x3F: 0x1FB85,  # UPPER THREE QUARTERS BLOCK
    0x40: 0x1CEA3,  # LEFT HALF LOWER ONE QUARTER BLOCK
    0x50: 0x2596,   # QUADRANT LOWER LEFT
    0x55: 0x258C,   # LEFT HALF BLOCK
    0x5A: 0x259E,   # QUADRANT UPPER RIGHT AND LOWER LEFT
    0x5F: 0x259B,   # QUADRANT UPPER LEFT AND UPPER RIGHT AND LOWER LEFT
    0x80: 0x1CEA0,  # RIGHT HALF LOWER ONE QUARTER BLOCK
    0xA0: 0x2597,   # QUADRANT LOWER RIGHT
    0xA5: 0x259A,   # QUADRANT UPPER LEFT AND LOWER RIGHT
    0xAA: 0x2590,   # RIGHT HALF BLOCK
    0xAF: 0x259C,   # QUADRANT UPPER LEFT AND UPPER RIGHT AND LOWER RIGHT
    0xC0: 0x2582,   # LOWER ONE QUARTER BLOCK
    0xF0: 0x2584,   # LOWER HALF BLOCK
    0xF5: 0x2599,   # QUADRANT UPPER LEFT AND LOWER LEFT AND LOWER RIGHT
    0xFA: 0x259F,   # QUADRANT UPPER RIGHT AND LOWER LEFT AND LOWER RIGHT
    0xFC: 0x2586,   # LOWER THREE QUARTERS BLOCK
    0xFF: 0x2588,   # FULL BLOCK
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
    table = [''] * 256
    for i in range(256):
        if i in _OCTANT_SPECIALS:
            table[i] = chr(_OCTANT_SPECIALS[i])
        else:
            # Count how many special patterns are below this value
            offset = bisect_left(_SPECIAL_KEYS_SORTED, i)
            table[i] = chr(0x1CD00 + i - offset)
    return table


OCTANT = _build_octant_table()
OCTANT_BYTES = [ch.encode('utf-8') for ch in OCTANT]


def _select_bitonal_pair(pixels: list[int]) -> tuple[int, int, int]:
    """Select best 2-color representation for a 2x4 cell.

    :param pixels: 8 packed RGB values in grid order
        [top-left, top-right, mid-upper-left, mid-upper-right,
         mid-lower-left, mid-lower-right, bot-left, bot-right]
    :returns: ``(bg_color, fg_color, octant_index)``
    """
    unique = list(set(pixels))

    if len(unique) == 1:
        return unique[0], unique[0], 0

    if len(unique) == 2:
        c0, c1 = unique
    else:
        max_dist = max(_color_distance(a, b) for a, b in combinations(unique, 2))
        if max_dist == 0:
            max_dist = 1.0
        best_score = -1.0
        c0, c1 = unique[0], unique[1]
        for a, b in combinations(unique, 2):
            freq = sum(1 for p in pixels if p == a or p == b)
            score = 0.85 * (freq / 8) + 0.15 * (_color_distance(a, b) / max_dist)
            if score > best_score:
                best_score = score
                c0, c1 = a, b

    # Build octant index: bit=0 -> c0 (bg), bit=1 -> c1 (fg)
    index = 0
    fg_count = 0
    for bit, p in enumerate(pixels):
        if p == c1:
            index |= (1 << bit)
            fg_count += 1
        elif p != c0:
            if _color_distance(p, c1) < _color_distance(p, c0):
                index |= (1 << bit)
                fg_count += 1

    # Prefer the more frequent color as background
    if fg_count > 4:
        c0, c1 = c1, c0
        index = (~index) & 0xFF

    if index == 0:
        return c0, c0, 0
    if index == 255:
        return c1, c1, 0
    return c0, c1, index


def _remap_index(pixels: list[int], bg: int, fg: int) -> int:
    """Assign each pixel to bg or fg by nearest color distance, return octant index.

    :param pixels: 8 packed RGB values.
    :param bg: Background color to assign bit=0.
    :param fg: Foreground color to assign bit=1.
    :returns: 8-bit octant index.
    """
    idx = 0
    for b, pixel in enumerate(pixels):
        if _color_distance(pixel, fg) < _color_distance(pixel, bg):
            idx |= (1 << b)
    return idx


def _visual_pixel_diff(
    bg1: int, fg1: int, idx1: int,
    bg2: int, fg2: int, idx2: int,
) -> int:
    """Count pixel positions where the displayed color differs.

    Each octant cell has 8 pixel positions (bits 0-7).

    :returns: Number of positions (0-8) with different displayed colors.
    """
    diff = 0
    for b in range(8):
        old_color = fg1 if (idx1 >> b) & 1 else bg1
        new_color = fg2 if (idx2 >> b) & 1 else bg2
        if old_color != new_color:
            diff += 1
    return diff


# Module-level display cache (separate from sextant's)
_display_cache: dict[tuple[int, int], tuple[int, int, int]] = {}
_last_params: list[int] = []


def blit_octant(
    image: npt.NDArray[np.uint32],
    last: npt.NDArray[np.uint32] | None,
    refx: int,
    refy: int,
    width: int,
    height: int,
    color_mode: int,
) -> bytes:
    """Render a frame using octant block characters.

    Same signature as :func:`gambaterm.termblit.blit`.
    """
    img_h, img_w = image.shape
    max_rows = min(height - refx, img_h // 4)
    max_cols = min(width - refy, img_w // 2)

    if max_rows <= 0 or max_cols <= 0:
        return b''

    params = [refx, refy, max_rows, max_cols]
    if last is None or params != _last_params:
        _display_cache.clear()
        _last_params[:] = params

    parts: list[bytes] = []
    cur_x = refx
    cur_y = refy
    cur_fg: int = -1
    cur_bg: int = -2

    # Initial cursor position
    parts.append(f'\033[{refx};{refy}H'.encode())

    for row in range(max_rows):
        py = row * 4
        for col in range(max_cols):
            px = col * 2

            # Extract 8 pixels (masked to RGB)
            pixels = [
                int(image[py, px]) & 0xFFFFFF,
                int(image[py, px + 1]) & 0xFFFFFF,
                int(image[py + 1, px]) & 0xFFFFFF,
                int(image[py + 1, px + 1]) & 0xFFFFFF,
                int(image[py + 2, px]) & 0xFFFFFF,
                int(image[py + 2, px + 1]) & 0xFFFFFF,
                int(image[py + 3, px]) & 0xFFFFFF,
                int(image[py + 3, px + 1]) & 0xFFFFFF,
            ]

            bg, fg, octant_idx = _select_bitonal_pair(pixels)

            # Color-pair hysteresis
            cell_key = (row, col)
            prev = _display_cache.get(cell_key)
            if prev is not None:
                prev_bg, prev_fg, prev_idx = prev
                direct_dist = (
                    _color_distance(bg, prev_bg) + _color_distance(fg, prev_fg)
                )
                swapped_dist = (
                    _color_distance(bg, prev_fg) + _color_distance(fg, prev_bg)
                )
                best_dist = min(direct_dist, swapped_dist)
                if (
                    best_dist < _COLOR_PAIR_HYSTERESIS
                    and prev_bg != prev_fg
                    and octant_idx != 0
                ):
                    if direct_dist <= swapped_dist:
                        use_bg, use_fg = prev_bg, prev_fg
                    else:
                        use_bg, use_fg = prev_fg, prev_bg
                    bg, fg, octant_idx = (
                        use_bg, use_fg, _remap_index(pixels, use_bg, use_fg)
                    )
                if _visual_pixel_diff(
                    prev_bg, prev_fg, prev_idx, bg, fg, octant_idx
                ) == 0:
                    continue
            _display_cache[cell_key] = (bg, fg, octant_idx)

            # Move cursor to cell position
            new_x = row + refx
            new_y = col + refy
            if new_x != cur_x or new_y != cur_y:
                parts.append(_move_relative(new_x - cur_x, new_y - cur_y))
            cur_x = new_x
            cur_y = new_y

            # Emit color escapes (minimize changes)
            if bg != cur_bg:
                parts.append(_set_color(bg, color_mode, False))
                cur_bg = bg
            if octant_idx != 0 and fg != cur_fg:
                parts.append(_set_color(fg, color_mode, True))
                cur_fg = fg

            # Emit octant character
            parts.append(OCTANT_BYTES[octant_idx])
            cur_y += 1

    # Reset attributes
    parts.append(b'\033[0m')
    return b''.join(parts)
