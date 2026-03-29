"""Sextant block rendering for terminal display.

Encodes 2x3 pixel blocks into Unicode sextant characters (U+1FB00-U+1FB3B),
For up to 80x48 terminal cells for a 160x144 Game Boy display.
"""
from __future__ import annotations

from functools import lru_cache
from itertools import combinations

import numpy as np
import numpy.typing as npt


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
    table = [''] * 64
    for i in range(64):
        if i == 0:
            table[i] = ' '
        elif i == 21:
            table[i] = '\u258c'
        elif i == 42:
            table[i] = '\u2590'
        elif i == 63:
            table[i] = '\u2588'
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
SEXTANT_BYTES = [ch.encode('utf-8') for ch in SEXTANT]


def _color_distance(rgb_a: int, rgb_b: int) -> float:
    """Perceptual color distance using redmean weighted Euclidean.

    Weighs green highest (human peak sensitivity), adjusts red/blue
    weighting by average red level to model cone response shift.
    See https://www.compuphase.com/cmetric.htm
    """
    r1 = (rgb_a >> 16) & 0xFF
    g1 = (rgb_a >> 8) & 0xFF
    b1 = rgb_a & 0xFF
    r2 = (rgb_b >> 16) & 0xFF
    g2 = (rgb_b >> 8) & 0xFF
    b2 = rgb_b & 0xFF
    rmean = (r1 + r2) >> 1
    dr = r1 - r2
    dg = g1 - g2
    db = b1 - b2
    return (((512 + rmean) * dr * dr) >> 8) + 4 * dg * dg + (((767 - rmean) * db * db) >> 8)





def _scale_256_to_6_shift(x: int) -> int:
    x >>= 5
    x -= x > 0
    x -= x > 1
    return x


def _scale_rgb_to_16_colors(r: int, g: int, b: int) -> int:
    r >>= 6
    g >>= 6
    b >>= 6
    if r == g == b == 1:
        return 90
    if r == g == b == 2:
        return 37
    if r < 2 and g < 2 and b < 2:
        return 30 + (b << 2 | g << 1 | r)
    r >>= 1
    g >>= 1
    b >>= 1
    return 90 + (b << 2 | g << 1 | r)


def _scale_rgb_to_4_colors(r: int, g: int, b: int) -> int:
    r *= r
    g *= g
    b *= b
    r >>= 3
    g >>= 3
    b >>= 3
    luma = 2 * r + 5 * g + b
    if luma <= (64 - 40) ** 2:
        return 30
    if luma <= (128 - 64) ** 2:
        return 90
    if luma <= (64 + 128 - 42) ** 2:
        return 37
    return 97


@lru_cache(maxsize=65536)
def _set_color(n: int, color_mode: int, foreground: bool) -> bytes:
    """Return ANSI escape bytes to set foreground or background color."""
    b_val = n & 0xFF
    g_val = (n >> 8) & 0xFF
    r_val = (n >> 16) & 0xFF
    if color_mode <= 2:
        if color_mode == 1:
            c = _scale_rgb_to_4_colors(r_val, g_val, b_val)
        else:
            c = _scale_rgb_to_16_colors(r_val, g_val, b_val)
        if not foreground:
            c += 10
        return f'\033[{c}m'.encode()
    if color_mode == 3:
        br = _scale_256_to_6_shift(b_val)
        gr = _scale_256_to_6_shift(g_val)
        rr = _scale_256_to_6_shift(r_val)
        c = 16 + 36 * rr + 6 * gr + br
        if foreground:
            return f'\033[38;5;{c}m'.encode()
        return f'\033[48;5;{c}m'.encode()
    if foreground:
        return f'\033[38;2;{r_val};{g_val};{b_val}m'.encode()
    return f'\033[48;2;{r_val};{g_val};{b_val}m'.encode()





def _move_relative(dx: int, dy: int) -> bytes:
    parts: list[str] = []
    if dx < -1:
        parts.append(f'\033[{-dx}A')
    elif dx == -1:
        parts.append('\033[A')
    elif dx == 1:
        parts.append('\033[B')
    elif dx > 1:
        parts.append(f'\033[{dx}B')
    if dy < -1:
        parts.append(f'\033[{-dy}D')
    elif dy == -1:
        parts.append('\033[D')
    elif dy == 1:
        parts.append('\033[C')
    elif dy > 1:
        parts.append(f'\033[{dy}C')
    return ''.join(parts).encode()





def _select_bitonal_pair(pixels: list[int]) -> tuple[int, int, int]:
    """Select best 2-color representation for a 2x3 cell.

    :param pixels: 6 packed RGB values in grid order
        [top-left, top-right, mid-left, mid-right, bot-left, bot-right]
    :returns: ``(bg_color, fg_color, sextant_index)``
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
            score = 0.85 * (freq / 6) + 0.15 * (_color_distance(a, b) / max_dist)
            if score > best_score:
                best_score = score
                c0, c1 = a, b

    # Build sextant index: bit=0 -> c0 (bg), bit=1 -> c1 (fg)
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
    if fg_count > 3:
        c0, c1 = c1, c0
        index = (~index) & 0x3F

    if index == 0:
        return c0, c0, 0
    if index == 63:
        return c1, c1, 0
    return c0, c1, index





_COLOR_PAIR_HYSTERESIS: int = 100

_display_cache: dict[tuple[int, int], tuple[int, int, int]] = {}
_last_params: list[int] = []


def _remap_index(pixels: list[int], bg: int, fg: int) -> int:
    """Assign each pixel to bg or fg by nearest color distance, return sextant index.

    :param pixels: 6 packed RGB values.
    :param bg: Background color to assign bit=0.
    :param fg: Foreground color to assign bit=1.
    :returns: 6-bit sextant index.
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

    Each sextant cell has 6 pixel positions (bits 0-5). For each position,
    the displayed color is fg if the bit is set, bg otherwise. Returns the
    number of positions (0-6) where the old and new displayed colors differ.

    :param bg1: Previous background color.
    :param fg1: Previous foreground color.
    :param idx1: Previous sextant index.
    :param bg2: New background color.
    :param fg2: New foreground color.
    :param idx2: New sextant index.
    :returns: Number of pixel positions with different displayed colors.
    """
    diff = 0
    for b in range(6):
        old_color = fg1 if (idx1 >> b) & 1 else bg1
        new_color = fg2 if (idx2 >> b) & 1 else bg2
        if old_color != new_color:
            diff += 1
    return diff





def blit_sextant(
    image: npt.NDArray[np.uint32],
    last: npt.NDArray[np.uint32] | None,
    refx: int,
    refy: int,
    width: int,
    height: int,
    color_mode: int,
) -> bytes:
    """Render a frame using sextant block characters.

    Same signature as :func:`gambaterm.termblit.blit`.
    """
    img_h, img_w = image.shape
    max_rows = min(height - refx, img_h // 3)
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
        py = row * 3
        for col in range(max_cols):
            px = col * 2

            # Extract 6 pixels (masked to RGB)
            pixels = [
                int(image[py, px]) & 0xFFFFFF,
                int(image[py, px + 1]) & 0xFFFFFF,
                int(image[py + 1, px]) & 0xFFFFFF,
                int(image[py + 1, px + 1]) & 0xFFFFFF,
                int(image[py + 2, px]) & 0xFFFFFF,
                int(image[py + 2, px + 1]) & 0xFFFFFF,
            ]

            bg, fg, sextant_idx = _select_bitonal_pair(pixels)

            # Color-pair hysteresis: if previous colors are close, remap to them to
            # avoid flicker from small quantization shifts during scrolling.
            cell_key = (row, col)
            prev = _display_cache.get(cell_key)
            if prev is not None:
                prev_bg, prev_fg, prev_idx = prev
                direct_dist = _color_distance(bg, prev_bg) + _color_distance(fg, prev_fg)
                swapped_dist = _color_distance(bg, prev_fg) + _color_distance(fg, prev_bg)
                best_dist = min(direct_dist, swapped_dist)
                if best_dist < _COLOR_PAIR_HYSTERESIS and prev_bg != prev_fg and sextant_idx != 0:
                    if direct_dist <= swapped_dist:
                        use_bg, use_fg = prev_bg, prev_fg
                    else:
                        use_bg, use_fg = prev_fg, prev_bg
                    bg, fg, sextant_idx = use_bg, use_fg, _remap_index(pixels, use_bg, use_fg)
                if _visual_pixel_diff(prev_bg, prev_fg, prev_idx, bg, fg, sextant_idx) == 0:
                    continue
            _display_cache[cell_key] = (bg, fg, sextant_idx)

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
            if sextant_idx != 0 and fg != cur_fg:
                parts.append(_set_color(fg, color_mode, True))
                cur_fg = fg

            # Emit sextant character
            parts.append(SEXTANT_BYTES[sextant_idx])
            cur_y += 1

    # Reset attributes
    parts.append(b'\033[0m')
    return b''.join(parts)
