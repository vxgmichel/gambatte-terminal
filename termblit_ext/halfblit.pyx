# cython: language_level=3

from cython import boundscheck
from libc.stdio cimport sprintf
from libc.stdlib cimport malloc, free
from libc.string cimport memset
from libc.stdint cimport uint32_t, int64_t
cdef uint32_t* NULL_PTR = <uint32_t*>0

include "blitcommon.pxi"
include "bitonal.pxi"

# Display cache: flat arrays indexed by row * max_cols + col
DEF MAX_CELLS = 2880  # 80 * 36

# Color snapping threshold — same units as sextant/octant HYSTERESIS.
cdef int _hysteresis = 700
cdef int _cp437_only = 0

cdef int _cache_c1[MAX_CELLS]
cdef int _cache_c2[MAX_CELLS]
cdef int _cache_split[MAX_CELLS]
cdef int _cache_pixels[MAX_CELLS * 8]
cdef int _cache_valid[MAX_CELLS]
cdef int _last_refx, _last_refy, _last_max_rows, _last_max_cols
_last_refx = _last_refy = _last_max_rows = _last_max_cols = -1


# Split codes:
#   H0 = solid (all one color)
#   H1 = horizontal, 1 top row / 3 bottom rows  (▂ / U+1FB82)
#   H2 = horizontal, 2 top / 2 bottom            (▄ / ▀)
#   H3 = horizontal, 3 top / 1 bottom            (▆ / U+1FB85)
#   H4 = solid (all one color)
#   V1 = vertical, left half / right half         (▌ / ▐)
DEF SPLIT_H0 = 0
DEF SPLIT_H1 = 1
DEF SPLIT_H2 = 2
DEF SPLIT_H3 = 3
DEF SPLIT_H4 = 4
DEF SPLIT_V1 = 5


cdef int resplit_cell(
    uint32_t* img, int stride, int py, int px,
    int c1, int c2, int prev_split,
) noexcept nogil:
    """Find best split for two given colors against the 2x4 pixel block."""
    cdef int pixels[8]
    cdef int cls[8]
    cdef int i, err, best_err, best_split, penalty
    cdef int best_first_is_fg = 0

    pixels[0] = img[py * stride + px] & 0xFFFFFF
    pixels[1] = img[py * stride + px + 1] & 0xFFFFFF
    pixels[2] = img[(py + 1) * stride + px] & 0xFFFFFF
    pixels[3] = img[(py + 1) * stride + px + 1] & 0xFFFFFF
    pixels[4] = img[(py + 2) * stride + px] & 0xFFFFFF
    pixels[5] = img[(py + 2) * stride + px + 1] & 0xFFFFFF
    pixels[6] = img[(py + 3) * stride + px] & 0xFFFFFF
    pixels[7] = img[(py + 3) * stride + px + 1] & 0xFFFFFF

    # Classify against c1 (bg) and c2 (fg)
    for i in range(8):
        if color_distance(pixels[i], c2) < color_distance(pixels[i], c1):
            cls[i] = 1
        else:
            cls[i] = 0

    best_err = 8
    best_split = SPLIT_H2

    penalty = 0 if prev_split == SPLIT_H1 else 1
    err = cls[0] + cls[1] + (1 - cls[2]) + (1 - cls[3]) + (1 - cls[4]) + (1 - cls[5]) + (1 - cls[6]) + (1 - cls[7]) + penalty
    if err < best_err:
        best_err = err
        best_split = SPLIT_H1
    err = (1 - cls[0]) + (1 - cls[1]) + cls[2] + cls[3] + cls[4] + cls[5] + cls[6] + cls[7] + penalty
    if err < best_err:
        best_err = err
        best_split = SPLIT_H1

    penalty = 0 if prev_split == SPLIT_H2 else 1
    err = cls[0] + cls[1] + cls[2] + cls[3] + (1 - cls[4]) + (1 - cls[5]) + (1 - cls[6]) + (1 - cls[7]) + penalty
    if err < best_err:
        best_err = err
        best_split = SPLIT_H2
    err = (1 - cls[0]) + (1 - cls[1]) + (1 - cls[2]) + (1 - cls[3]) + cls[4] + cls[5] + cls[6] + cls[7] + penalty
    if err < best_err:
        best_err = err
        best_split = SPLIT_H2

    penalty = 0 if prev_split == SPLIT_H3 else 1
    err = cls[0] + cls[1] + cls[2] + cls[3] + cls[4] + cls[5] + (1 - cls[6]) + (1 - cls[7]) + penalty
    if err < best_err:
        best_err = err
        best_split = SPLIT_H3
    err = (1 - cls[0]) + (1 - cls[1]) + (1 - cls[2]) + (1 - cls[3]) + (1 - cls[4]) + (1 - cls[5]) + cls[6] + cls[7] + penalty
    if err < best_err:
        best_err = err
        best_split = SPLIT_H3

    penalty = 0 if prev_split == SPLIT_V1 else 1
    err = cls[0] + (1 - cls[1]) + cls[2] + (1 - cls[3]) + cls[4] + (1 - cls[5]) + cls[6] + (1 - cls[7]) + penalty
    if err < best_err:
        best_err = err
        best_split = SPLIT_V1
    err = (1 - cls[0]) + cls[1] + (1 - cls[2]) + cls[3] + (1 - cls[4]) + cls[5] + (1 - cls[6]) + cls[7] + penalty
    if err < best_err:
        best_err = err
        best_split = SPLIT_V1

    return best_split


cdef int analyze_cell(
    uint32_t* img, int stride, int py, int px,
    uint32_t* out_c1, uint32_t* out_c2, int* out_split,
    int prev_split,
) noexcept nogil:
    """Analyze a 2x4 pixel block and find the best 2-color split.

    Tries horizontal splits at each row boundary and a vertical
    left/right split, picking whichever has the fewest mismatched
    pixels.  Sets out_c1, out_c2 (the two colors) and out_split
    (split code).  Returns the error count of the best split.
    """
    cdef int pixels[8]
    cdef int bg, fg, idx
    cdef int i, row, err, best_err, best_split
    cdef int left_fg, right_fg, top_fg, bot_fg

    # Read 8 pixels (2 cols x 4 rows), masked to RGB
    pixels[0] = img[py * stride + px] & 0xFFFFFF
    pixels[1] = img[py * stride + px + 1] & 0xFFFFFF
    pixels[2] = img[(py + 1) * stride + px] & 0xFFFFFF
    pixels[3] = img[(py + 1) * stride + px + 1] & 0xFFFFFF
    pixels[4] = img[(py + 2) * stride + px] & 0xFFFFFF
    pixels[5] = img[(py + 2) * stride + px + 1] & 0xFFFFFF
    pixels[6] = img[(py + 3) * stride + px] & 0xFFFFFF
    pixels[7] = img[(py + 3) * stride + px + 1] & 0xFFFFFF

    # Find best 2-color pair across all 8 pixels
    select_bitonal_pair(pixels, 8, 0xFF, &bg, &fg, &idx)

    out_c1[0] = bg
    out_c2[0] = fg

    # If solid, done
    if bg == fg or idx == 0 or idx == 0xFF:
        out_c1[0] = bg
        out_c2[0] = bg
        out_split[0] = SPLIT_H0
        return 0

    # Classify each pixel: 1 = fg, 0 = bg
    cdef int cls[8]
    for i in range(8):
        if (idx >> i) & 1:
            cls[i] = 1
        else:
            cls[i] = 0

    # Pixel layout in the 2x4 grid:
    #   cls[0] cls[1]   row 0
    #   cls[2] cls[3]   row 1
    #   cls[4] cls[5]   row 2
    #   cls[6] cls[7]   row 3

    # Try each split in both orientations.  Track best error and
    # whether the "first" region (top/left) is bg or fg.
    # first_is_fg=0: c1=bg (top/left), c2=fg (bottom/right)
    # first_is_fg=1: c1=fg (top/left), c2=bg (bottom/right)
    #
    # Stability: a new split must beat the previous by >1 error to
    # win.  This prevents oscillation when two splits tie during
    # scrolling.  The penalty variable is 0 for the previous split
    # type and 1 for any other.
    best_err = 8
    best_split = SPLIT_H2
    cdef int best_first_is_fg = 0
    cdef int penalty

    # H1: 1 top row / 3 bottom rows
    penalty = 0 if prev_split == SPLIT_H1 else 1
    err = cls[0] + cls[1] + (1 - cls[2]) + (1 - cls[3]) + (1 - cls[4]) + (1 - cls[5]) + (1 - cls[6]) + (1 - cls[7]) + penalty
    if err < best_err:
        best_err = err
        best_split = SPLIT_H1
        best_first_is_fg = 0  # top = bg
    err = (1 - cls[0]) + (1 - cls[1]) + cls[2] + cls[3] + cls[4] + cls[5] + cls[6] + cls[7] + penalty
    if err < best_err:
        best_err = err
        best_split = SPLIT_H1
        best_first_is_fg = 1  # top = fg

    # H2: 2 top rows / 2 bottom rows
    penalty = 0 if prev_split == SPLIT_H2 else 1
    err = cls[0] + cls[1] + cls[2] + cls[3] + (1 - cls[4]) + (1 - cls[5]) + (1 - cls[6]) + (1 - cls[7]) + penalty
    if err < best_err:
        best_err = err
        best_split = SPLIT_H2
        best_first_is_fg = 0
    err = (1 - cls[0]) + (1 - cls[1]) + (1 - cls[2]) + (1 - cls[3]) + cls[4] + cls[5] + cls[6] + cls[7] + penalty
    if err < best_err:
        best_err = err
        best_split = SPLIT_H2
        best_first_is_fg = 1

    # H3: 3 top rows / 1 bottom row
    penalty = 0 if prev_split == SPLIT_H3 else 1
    err = cls[0] + cls[1] + cls[2] + cls[3] + cls[4] + cls[5] + (1 - cls[6]) + (1 - cls[7]) + penalty
    if err < best_err:
        best_err = err
        best_split = SPLIT_H3
        best_first_is_fg = 0
    err = (1 - cls[0]) + (1 - cls[1]) + (1 - cls[2]) + (1 - cls[3]) + (1 - cls[4]) + (1 - cls[5]) + cls[6] + cls[7] + penalty
    if err < best_err:
        best_err = err
        best_split = SPLIT_H3
        best_first_is_fg = 1

    # V1: left col / right col
    penalty = 0 if prev_split == SPLIT_V1 else 1
    err = cls[0] + (1 - cls[1]) + cls[2] + (1 - cls[3]) + cls[4] + (1 - cls[5]) + cls[6] + (1 - cls[7]) + penalty
    if err < best_err:
        best_err = err
        best_split = SPLIT_V1
        best_first_is_fg = 0  # left = bg
    err = (1 - cls[0]) + cls[1] + (1 - cls[2]) + cls[3] + (1 - cls[4]) + cls[5] + (1 - cls[6]) + cls[7] + penalty
    if err < best_err:
        best_err = err
        best_split = SPLIT_V1
        best_first_is_fg = 1  # left = fg

    # Assign colors: c1 = first region (top/left), c2 = second (bottom/right)
    if best_first_is_fg:
        out_c1[0] = fg
        out_c2[0] = bg
    else:
        out_c1[0] = bg
        out_c2[0] = fg

    out_split[0] = best_split
    return best_err


@boundscheck(False)
cdef char* _blit_half(
    uint32_t* img, uint32_t* lst,
    int img_stride, int has_last,
    int refx, int refy, int width, int height,
    int max_rows, int max_cols,
    int color_mode,
    int hysteresis,
    int cp437_only,
    char* base,
) noexcept nogil:
    """Half-size halfblock blitter with sub-cell precision.

    Downscales the 160x144 Game Boy image by 2x in each dimension.
    Each terminal cell covers a 2x4 block of original pixels (2 wide,
    4 tall) producing an 80x36 terminal grid.

    Analyzes all 8 pixels per cell to find the best 2-color split —
    horizontal (at 1/4, 1/2, 3/4 boundaries using eighth-height
    blocks) or vertical (left/right half blocks).  Picks whichever
    orientation has the fewest mismatched pixels.
    """
    cdef int current_x = refx
    cdef int current_y = refy
    cdef uint32_t current_fg = 0x0
    cdef uint32_t current_bg = 0x0
    cdef int row_index, column_index
    cdef uint32_t color1, color2
    cdef uint32_t orig_c1, orig_c2
    cdef int new_x, new_y, py, px, cell
    cdef int split, orig_split
    cdef int prev_c1, prev_c2, prev_split
    cdef int64_t direct_dist, swapped_dist, best_dist
    cdef int invert_print
    cdef int cpx[8]
    cdef char* result = base

    result = move_absolute(result, refx, refy)

    for row_index in range(max_rows):
        for column_index in range(max_cols):
            py = 4 * row_index
            px = 2 * column_index

            # Read source pixels for cache comparison
            cell = row_index * max_cols + column_index
            cpx[0] = img[py * img_stride + px] & 0xFFFFFF
            cpx[1] = img[py * img_stride + px + 1] & 0xFFFFFF
            cpx[2] = img[(py + 1) * img_stride + px] & 0xFFFFFF
            cpx[3] = img[(py + 1) * img_stride + px + 1] & 0xFFFFFF
            cpx[4] = img[(py + 2) * img_stride + px] & 0xFFFFFF
            cpx[5] = img[(py + 2) * img_stride + px + 1] & 0xFFFFFF
            cpx[6] = img[(py + 3) * img_stride + px] & 0xFFFFFF
            cpx[7] = img[(py + 3) * img_stride + px + 1] & 0xFFFFFF

            # Skip when source pixels match both the pixel cache
            # AND the previous video frame.
            if _cache_valid[cell] and has_last:
                if (
                    cpx[0] == _cache_pixels[cell * 8]
                    and cpx[1] == _cache_pixels[cell * 8 + 1]
                    and cpx[2] == _cache_pixels[cell * 8 + 2]
                    and cpx[3] == _cache_pixels[cell * 8 + 3]
                    and cpx[4] == _cache_pixels[cell * 8 + 4]
                    and cpx[5] == _cache_pixels[cell * 8 + 5]
                    and cpx[6] == _cache_pixels[cell * 8 + 6]
                    and cpx[7] == _cache_pixels[cell * 8 + 7]
                    and cpx[0] == <int>(lst[py * img_stride + px] & 0xFFFFFF)
                    and cpx[1] == <int>(lst[py * img_stride + px + 1] & 0xFFFFFF)
                    and cpx[2] == <int>(lst[(py + 1) * img_stride + px] & 0xFFFFFF)
                    and cpx[3] == <int>(lst[(py + 1) * img_stride + px + 1] & 0xFFFFFF)
                    and cpx[4] == <int>(lst[(py + 2) * img_stride + px] & 0xFFFFFF)
                    and cpx[5] == <int>(lst[(py + 2) * img_stride + px + 1] & 0xFFFFFF)
                    and cpx[6] == <int>(lst[(py + 3) * img_stride + px] & 0xFFFFFF)
                    and cpx[7] == <int>(lst[(py + 3) * img_stride + px + 1] & 0xFFFFFF)
                ):
                    continue

            # Analyze full 2x4 block, biased toward previous split
            analyze_cell(
                img, img_stride, py, px, &color1, &color2, &split,
                _cache_split[cell] if _cache_valid[cell] else -1,
            )

            # CP437 mode: only allow H2 (▀▄) and V1 (▌▐), no eighths
            if cp437_only and (split == SPLIT_H1 or split == SPLIT_H3):
                split = SPLIT_H2

            # Color snapping
            if _cache_valid[cell]:
                prev_c1 = _cache_c1[cell]
                prev_c2 = _cache_c2[cell]
                prev_split = _cache_split[cell]
                direct_dist = (
                    color_distance(color1, prev_c1)
                    + color_distance(color2, prev_c2)
                )
                swapped_dist = (
                    color_distance(color1, prev_c2)
                    + color_distance(color2, prev_c1)
                )
                best_dist = direct_dist if direct_dist < swapped_dist else swapped_dist
                if (
                    best_dist < hysteresis
                    and prev_c1 != prev_c2
                    and color1 != color2
                ):
                    if direct_dist <= swapped_dist:
                        color1 = prev_c1
                        color2 = prev_c2
                    else:
                        color1 = prev_c2
                        color2 = prev_c1
                    split = resplit_cell(
                        img, img_stride, py, px,
                        color1, color2, prev_split,
                    )

            _cache_c1[cell] = color1
            _cache_c2[cell] = color2
            _cache_split[cell] = split
            _cache_pixels[cell * 8] = cpx[0]
            _cache_pixels[cell * 8 + 1] = cpx[1]
            _cache_pixels[cell * 8 + 2] = cpx[2]
            _cache_pixels[cell * 8 + 3] = cpx[3]
            _cache_pixels[cell * 8 + 4] = cpx[4]
            _cache_pixels[cell * 8 + 5] = cpx[5]
            _cache_pixels[cell * 8 + 6] = cpx[6]
            _cache_pixels[cell * 8 + 7] = cpx[7]
            _cache_valid[cell] = 1

            # Move cursor
            new_x = row_index + refx
            new_y = column_index + refy
            if new_x != current_x or new_y != current_y:
                result = move_from_to(result, current_x, current_y, new_x, new_y)
            current_x = new_x
            current_y = new_y

            # === Solid cell ===
            if color1 == color2:
                if color1 == current_fg and color1 != current_bg:
                    result += sprintf(result, "\xe2\x96\x88")  # █
                else:
                    if color1 != current_bg:
                        result = set_background(result, color1, color_mode)
                        current_bg = color1
                    result += sprintf(result, " ")
                current_y += 1
                continue

            # === Horizontal splits ===
            # Convention: color1 = top region, color2 = bottom region.
            # "Inverted" means fg = bottom color (lower-filled blocks).
            # "Normal" means fg = top color (upper-filled blocks).
            if split <= SPLIT_H4:
                invert_print = (current_fg == color2 or current_bg == color1)

                if invert_print:
                    if current_fg != color2:
                        result = set_foreground(result, color2, color_mode)
                        current_fg = color2
                    if current_bg != color1:
                        result = set_background(result, color1, color_mode)
                        current_bg = color1
                    if split == SPLIT_H1:
                        result += sprintf(result, "\xe2\x96\x86")  # ▆ lower 6/8
                    elif split == SPLIT_H3:
                        result += sprintf(result, "\xe2\x96\x82")  # ▂ lower 2/8
                    else:
                        result += sprintf(result, "\xe2\x96\x84")  # ▄ lower 4/8
                else:
                    if current_fg != color1:
                        result = set_foreground(result, color1, color_mode)
                        current_fg = color1
                    if current_bg != color2:
                        result = set_background(result, color2, color_mode)
                        current_bg = color2
                    if split == SPLIT_H1:
                        result += sprintf(result, "\xf0\x9f\xae\x82")  # upper 2/8
                    elif split == SPLIT_H3:
                        result += sprintf(result, "\xf0\x9f\xae\x85")  # upper 6/8
                    else:
                        result += sprintf(result, "\xe2\x96\x80")  # ▀ upper 4/8

            # === Vertical split ===
            # Convention: color1 = left, color2 = right.
            elif split == SPLIT_V1:
                invert_print = (current_fg == color2 or current_bg == color1)

                if invert_print:
                    # fg = right (color2), bg = left (color1) → ▐ right half
                    if current_fg != color2:
                        result = set_foreground(result, color2, color_mode)
                        current_fg = color2
                    if current_bg != color1:
                        result = set_background(result, color1, color_mode)
                        current_bg = color1
                    result += sprintf(result, "\xe2\x96\x90")  # ▐
                else:
                    # fg = left (color1), bg = right (color2) → ▌ left half
                    if current_fg != color1:
                        result = set_foreground(result, color1, color_mode)
                        current_fg = color1
                    if current_bg != color2:
                        result = set_background(result, color2, color_mode)
                        current_bg = color2
                    result += sprintf(result, "\xe2\x96\x8c")  # ▌

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


def set_cp437(int value):
    global _cp437_only
    _cp437_only = value


def blit_half(
    uint32_t[:, ::1] image,
    uint32_t[:, ::1] last,
    int refx, int refy, int width, int height,
    int color_mode,
):
    cdef int img_h = image.shape[0]
    cdef int img_w = image.shape[1]
    cdef int max_rows = min(height - refx, img_h // 4)
    cdef int max_cols = min(width - refy, img_w // 2)
    cdef char* base
    cdef char* result
    cdef int has_last = 0 if last is None else 1
    cdef uint32_t* img_ptr = &image[0, 0]
    cdef uint32_t* lst_ptr = NULL_PTR
    if has_last:
        lst_ptr = &last[0, 0]

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
        result = _blit_half(
            img_ptr, lst_ptr, img_w, has_last,
            refx, refy, width, height,
            max_rows, max_cols,
            color_mode, _hysteresis, _cp437_only, base,
        )

    try:
        return base[:result - base]
    finally:
        free(base)
