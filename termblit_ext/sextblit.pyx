# cython: language_level=3

from cython import boundscheck
from libc.stdio cimport sprintf
from libc.stdlib cimport malloc, free
from libc.string cimport memset, memcpy
from libc.stdint cimport uint32_t, int64_t

include "blitcommon.pxi"
include "bitonal.pxi"


# Sextant lookup table: 64 entries, each up to 4 UTF-8 bytes.
# Bit layout in the 2x3 cell grid:
#     bit0  bit1
#     bit2  bit3
#     bit4  bit5
# Patterns 0 (space), 21 (left half block), 42 (right half block), and
# 63 (full block) map to pre-existing block element characters; the
# remaining 60 patterns map to U+1FB00..U+1FB3B.
cdef extern from *:
    """
    static char _table[64][4] = {
        {0x20, 0x00, 0x00, 0x00},
        {0xf0, 0x9f, 0xac, 0x80},
        {0xf0, 0x9f, 0xac, 0x81},
        {0xf0, 0x9f, 0xac, 0x82},
        {0xf0, 0x9f, 0xac, 0x83},
        {0xf0, 0x9f, 0xac, 0x84},
        {0xf0, 0x9f, 0xac, 0x85},
        {0xf0, 0x9f, 0xac, 0x86},
        {0xf0, 0x9f, 0xac, 0x87},
        {0xf0, 0x9f, 0xac, 0x88},
        {0xf0, 0x9f, 0xac, 0x89},
        {0xf0, 0x9f, 0xac, 0x8a},
        {0xf0, 0x9f, 0xac, 0x8b},
        {0xf0, 0x9f, 0xac, 0x8c},
        {0xf0, 0x9f, 0xac, 0x8d},
        {0xf0, 0x9f, 0xac, 0x8e},
        {0xf0, 0x9f, 0xac, 0x8f},
        {0xf0, 0x9f, 0xac, 0x90},
        {0xf0, 0x9f, 0xac, 0x91},
        {0xf0, 0x9f, 0xac, 0x92},
        {0xf0, 0x9f, 0xac, 0x93},
        {0xe2, 0x96, 0x8c, 0x00},
        {0xf0, 0x9f, 0xac, 0x94},
        {0xf0, 0x9f, 0xac, 0x95},
        {0xf0, 0x9f, 0xac, 0x96},
        {0xf0, 0x9f, 0xac, 0x97},
        {0xf0, 0x9f, 0xac, 0x98},
        {0xf0, 0x9f, 0xac, 0x99},
        {0xf0, 0x9f, 0xac, 0x9a},
        {0xf0, 0x9f, 0xac, 0x9b},
        {0xf0, 0x9f, 0xac, 0x9c},
        {0xf0, 0x9f, 0xac, 0x9d},
        {0xf0, 0x9f, 0xac, 0x9e},
        {0xf0, 0x9f, 0xac, 0x9f},
        {0xf0, 0x9f, 0xac, 0xa0},
        {0xf0, 0x9f, 0xac, 0xa1},
        {0xf0, 0x9f, 0xac, 0xa2},
        {0xf0, 0x9f, 0xac, 0xa3},
        {0xf0, 0x9f, 0xac, 0xa4},
        {0xf0, 0x9f, 0xac, 0xa5},
        {0xf0, 0x9f, 0xac, 0xa6},
        {0xf0, 0x9f, 0xac, 0xa7},
        {0xe2, 0x96, 0x90, 0x00},
        {0xf0, 0x9f, 0xac, 0xa8},
        {0xf0, 0x9f, 0xac, 0xa9},
        {0xf0, 0x9f, 0xac, 0xaa},
        {0xf0, 0x9f, 0xac, 0xab},
        {0xf0, 0x9f, 0xac, 0xac},
        {0xf0, 0x9f, 0xac, 0xad},
        {0xf0, 0x9f, 0xac, 0xae},
        {0xf0, 0x9f, 0xac, 0xaf},
        {0xf0, 0x9f, 0xac, 0xb0},
        {0xf0, 0x9f, 0xac, 0xb1},
        {0xf0, 0x9f, 0xac, 0xb2},
        {0xf0, 0x9f, 0xac, 0xb3},
        {0xf0, 0x9f, 0xac, 0xb4},
        {0xf0, 0x9f, 0xac, 0xb5},
        {0xf0, 0x9f, 0xac, 0xb6},
        {0xf0, 0x9f, 0xac, 0xb7},
        {0xf0, 0x9f, 0xac, 0xb8},
        {0xf0, 0x9f, 0xac, 0xb9},
        {0xf0, 0x9f, 0xac, 0xba},
        {0xf0, 0x9f, 0xac, 0xbb},
        {0xe2, 0x96, 0x88, 0x00},
    };
    static int _table_len[64] = {
        1, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4,
        4, 4, 4, 4, 4, 3, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4,
        4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 3, 4, 4, 4, 4, 4,
        4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 3,
    };
    """
    char _table[64][4]
    int _table_len[64]

# Display cache: flat arrays indexed by row * max_cols + col
DEF MAX_CELLS = 3840  # 80 * 48

# Color snapping threshold, in redmean color distance units (see
# color_distance).  When a cell's new bg/fg pair is closer than this
# to the previously rendered pair, the old colors are reused and the
# sextant pattern index is recomputed against them.  This stops the
# output from flickering when select_bitonal_pair picks a slightly
# different pair each frame for what is visually the same content.
# A value of 100 is roughly a just-noticeable RGB shift.
#
# Tuning: lower (e.g. 25) means less snapping, more flicker on
# static content.  Higher (e.g. 400) snaps harder, smoother output
# but may hide small color changes during animation.  0 turns
# snapping off entirely.
cdef int _hysteresis = 700

cdef int _cache_bg[MAX_CELLS]
cdef int _cache_fg[MAX_CELLS]
cdef int _cache_idx[MAX_CELLS]
cdef int _cache_pixels[MAX_CELLS * 6]
cdef int _cache_valid[MAX_CELLS]
cdef int _last_refx, _last_refy, _last_max_rows, _last_max_cols
_last_refx = _last_refy = _last_max_rows = _last_max_cols = -1


@boundscheck(False)
cdef char* _blit_sextant(
    uint32_t[:, ::1] image,
    uint32_t[:, ::1] last,
    int has_last,
    int refx, int refy, int width, int height,
    int color_mode, char* base,
    int max_rows, int max_cols,
    int hysteresis,
) noexcept nogil:

    cdef int current_x = refx
    cdef int current_y = refy
    cdef int current_fg = -1
    cdef int current_bg = -2
    cdef int row, col, py, px
    cdef int pixels[6]
    cdef int bg, fg, sxt_idx
    cdef int orig_bg, orig_fg, orig_idx
    cdef int new_x, new_y, cell
    cdef int prev_bg, prev_fg, prev_idx
    cdef int64_t direct_dist, swapped_dist, best_dist
    cdef int use_bg, use_fg
    cdef char* result = base

    # Move at reference point
    result = move_absolute(result, refx, refy)

    # Loop over terminal cells
    for row in range(max_rows):
        py = row * 3
        for col in range(max_cols):
            px = col * 2

            # Extract 6 pixels (masked to RGB)
            pixels[0] = image[py, px] & 0xFFFFFF
            pixels[1] = image[py, px + 1] & 0xFFFFFF
            pixels[2] = image[py + 1, px] & 0xFFFFFF
            pixels[3] = image[py + 1, px + 1] & 0xFFFFFF
            pixels[4] = image[py + 2, px] & 0xFFFFFF
            pixels[5] = image[py + 2, px + 1] & 0xFFFFFF

            select_bitonal_pair(pixels, 6, 0x3F, &bg, &fg, &sxt_idx)

            # Color snapping and skip-if-unchanged check.
            #
            # Each cell caches its last-rendered (bg, fg, idx).  If
            # the new colors are close to the cached ones, snap to
            # the cached colors and recompute the pattern index.
            #
            # The skip check uses the original (pre-snap) values so
            # real pixel changes (e.g. scrolling) are still detected.
            cell = row * max_cols + col
            if _cache_valid[cell]:
                prev_bg = _cache_bg[cell]
                prev_fg = _cache_fg[cell]
                prev_idx = _cache_idx[cell]
                # Save pre-snap values for change detection
                orig_bg = bg
                orig_fg = fg
                orig_idx = sxt_idx
                direct_dist = color_distance(bg, prev_bg) + color_distance(fg, prev_fg)
                swapped_dist = color_distance(bg, prev_fg) + color_distance(fg, prev_bg)
                best_dist = direct_dist if direct_dist < swapped_dist else swapped_dist
                # Snap: reuse cached colors when close enough, and the
                # cell is not transitioning to/from a solid fill.
                if best_dist < hysteresis and prev_bg != prev_fg and sxt_idx != 0:
                    if direct_dist <= swapped_dist:
                        use_bg = prev_bg
                        use_fg = prev_fg
                    else:
                        use_bg = prev_fg
                        use_fg = prev_bg
                    bg = use_bg
                    fg = use_fg
                    sxt_idx = remap_index(pixels, 6, use_bg, use_fg)
                # Skip when source pixels match both the pixel cache
                # AND the previous video frame.  The dual check prevents
                # false hits from repeating patterns during scroll when
                # the image is horizontally cropped.
                if (
                    pixels[0] == _cache_pixels[cell * 6]
                    and pixels[1] == _cache_pixels[cell * 6 + 1]
                    and pixels[2] == _cache_pixels[cell * 6 + 2]
                    and pixels[3] == _cache_pixels[cell * 6 + 3]
                    and pixels[4] == _cache_pixels[cell * 6 + 4]
                    and pixels[5] == _cache_pixels[cell * 6 + 5]
                    and has_last
                    and <int>(last[py, px] & 0xFFFFFF) == pixels[0]
                    and <int>(last[py, px + 1] & 0xFFFFFF) == pixels[1]
                    and <int>(last[py + 1, px] & 0xFFFFFF) == pixels[2]
                    and <int>(last[py + 1, px + 1] & 0xFFFFFF) == pixels[3]
                    and <int>(last[py + 2, px] & 0xFFFFFF) == pixels[4]
                    and <int>(last[py + 2, px + 1] & 0xFFFFFF) == pixels[5]
                ):
                    continue

            _cache_bg[cell] = bg
            _cache_fg[cell] = fg
            _cache_idx[cell] = sxt_idx
            _cache_pixels[cell * 6] = pixels[0]
            _cache_pixels[cell * 6 + 1] = pixels[1]
            _cache_pixels[cell * 6 + 2] = pixels[2]
            _cache_pixels[cell * 6 + 3] = pixels[3]
            _cache_pixels[cell * 6 + 4] = pixels[4]
            _cache_pixels[cell * 6 + 5] = pixels[5]
            _cache_valid[cell] = 1

            # Go to the new position
            new_x = row + refx
            new_y = col + refy
            if new_x != current_x or new_y != current_y:
                result = move_from_to(result, current_x, current_y, new_x, new_y)
            current_x = new_x
            current_y = new_y

            # Set background and foreground colors if necessary
            if bg != current_bg:
                result = set_background(result, bg, color_mode)
                current_bg = bg
            if sxt_idx != 0 and fg != current_fg:
                result = set_foreground(result, fg, color_mode)
                current_fg = fg

            # Print sextant character
            memcpy(result, &_table[sxt_idx][0], _table_len[sxt_idx])
            result += _table_len[sxt_idx]
            current_y += 1

    return result



def clear_cache():
    """Clear the display cache and invalidate stored params."""
    global _last_refx, _last_refy, _last_max_rows, _last_max_cols
    with nogil:
        memset(_cache_valid, 0, MAX_CELLS * sizeof(int))
    _last_refx = _last_refy = _last_max_rows = _last_max_cols = -1


def set_hysteresis(int value):
    global _hysteresis
    _hysteresis = max(0, value)


def get_hysteresis() -> int:
    return _hysteresis


def blit_sextant(
    uint32_t[:, ::1] image,
    uint32_t[:, ::1] last,
    int refx, int refy, int width, int height,
    int color_mode,
):
    cdef int img_h = image.shape[0]
    cdef int img_w = image.shape[1]
    cdef int max_rows = min(height - refx, img_h // 3)
    cdef int max_cols = min(width - refy, img_w // 2)
    cdef char* base
    cdef char* result
    cdef int has_last = 0 if last is None else 1

    if max_rows <= 0 or max_cols <= 0:
        return b''

    global _last_refx, _last_refy, _last_max_rows, _last_max_cols
    if (not has_last or refx != _last_refx or refy != _last_refy
            or max_rows != _last_max_rows or max_cols != _last_max_cols):
        memset(_cache_valid, 0, MAX_CELLS * sizeof(int))
    _last_refx = refx
    _last_refy = refy
    _last_max_rows = max_rows
    _last_max_cols = max_cols

    with nogil:
        base = <char*>malloc(max_rows * max_cols * 60)
        result = _blit_sextant(
            image, last, has_last,
            refx, refy, width, height, color_mode,
            base, max_rows, max_cols, _hysteresis,
        )

    try:
        return base[:result - base]
    finally:
        free(base)
