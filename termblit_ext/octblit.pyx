# cython: language_level=3

from cython import boundscheck
from libc.stdio cimport sprintf
from libc.stdlib cimport malloc, free
from libc.string cimport memset, memcpy
from libc.stdint cimport uint32_t, int64_t

cdef char* move_absolute(char* buff, int x, int y) noexcept nogil:
    buff += sprintf(buff, "\033[%d;%dH", x, y)
    return buff


cdef char* move_relative(char* buff, int dx, int dy) noexcept nogil:
    # Vertical move
    if dx < -1:
        buff += sprintf(buff, "\033[%dA", -dx)
    elif dx == -1:
        buff += sprintf(buff, "\033[A")
    elif dx == 1:
        buff += sprintf(buff, "\033[B")
    elif dx > 1:
        buff += sprintf(buff, "\033[%dB", dx)
    # Horizontal move
    if dy < -1:
        buff += sprintf(buff, "\033[%dD", -dy)
    elif dy == -1:
        buff += sprintf(buff, "\033[D")
    elif dy == 1:
        buff += sprintf(buff, "\033[C")
    elif dy > 1:
        buff += sprintf(buff, "\033[%dC", dy)
    return buff


cdef int scale_256_to_6_shift(int x) noexcept nogil:
    x >>= 5
    x -= x > 0
    x -= x > 1
    return x


cdef int scale_rgb_to_16_colors(int r, int g, int b) noexcept nogil:
    r >>= 6
    g >>= 6
    b >>= 6
    # Dark grey
    if r == g == b == 1:
        return 90
    # Light grey
    if r == g == b == 2:
        return 37
    # Standard colors
    if r < 2 and g < 2 and b < 2:
        return 30 + (b << 2 | g << 1 | r)
    # Lower resolution
    r >>= 1
    g >>= 1
    b >>= 1
    # Bright colors
    return 90 + (b << 2 | g << 1 | r)


cdef int scale_rgb_to_4_colors(int r, int g, int b) noexcept nogil:
    # Square the values
    r *= r
    g *= g
    b *= b
    # Divide the values by 8
    r >>= 3
    g >>= 3
    b >>= 3
    # Apply coefficients
    cdef int l = 2 * r + 5 * g + b
    # Black color
    if l <= (64 - 40) ** 2:
        return 30
    # Dark grey color
    if l <= (128 - 64) ** 2:
        return 90
    # Light grey color
    if l <= (64 + 128 - 42) ** 2:
        return 37
    # White color
    return 97

cdef char* set_color(char* buff, int n, int color_mode, int foreground) noexcept nogil:
    cdef int c
    # Extract RGB components
    cdef int b = n & 0xff
    cdef int g = (n >> 8) & 0xff
    cdef int r = (n >> 16) & 0xff
    # Standard colors
    if color_mode <= 2:
        if color_mode == 1:
            c = scale_rgb_to_4_colors(r, g, b)
        elif color_mode == 2:
            c = scale_rgb_to_16_colors(r, g, b)
        if not foreground:
            c += 10
        buff += sprintf(buff, "\033[%dm", c)
    # 256 colors
    elif color_mode == 3:
        b = scale_256_to_6_shift(b)
        g = scale_256_to_6_shift(g)
        r = scale_256_to_6_shift(r)
        c = 16 + 36 * r + 6 * g + b
        if foreground:
            buff += sprintf(buff, "\033[38;5;%dm", c)
        else:
            buff += sprintf(buff, "\033[48;5;%dm", c)
    # True colors
    elif color_mode == 4:
        if foreground:
            buff += sprintf(buff, "\033[38;2;%d;%d;%dm", r, g, b)
        else:
            buff += sprintf(buff, "\033[48;2;%d;%d;%dm", r, g, b)
    return buff


cdef char* set_background(char* buff, int n, int color_mode) noexcept nogil:
    return set_color(buff, n, color_mode, False)


cdef char* set_foreground(char* buff, int n, int color_mode) noexcept nogil:
    return set_color(buff, n, color_mode, True)


cdef char* move_from_to(
    char *buff, int from_x, int from_y, int to_x, int to_y
) noexcept nogil:
    return move_relative(buff, to_x - from_x, to_y - from_y)


cdef int64_t color_distance(int rgb_a, int rgb_b) noexcept nogil:
    """Redmean weighted Euclidean color distance.

    See https://www.compuphase.com/cmetric.htm
    """
    cdef int r1 = (rgb_a >> 16) & 0xFF
    cdef int g1 = (rgb_a >> 8) & 0xFF
    cdef int b1 = rgb_a & 0xFF
    cdef int r2 = (rgb_b >> 16) & 0xFF
    cdef int g2 = (rgb_b >> 8) & 0xFF
    cdef int b2 = rgb_b & 0xFF
    cdef int rmean = (r1 + r2) >> 1
    cdef int dr = r1 - r2
    cdef int dg = g1 - g2
    cdef int db = b1 - b2
    return (
        ((<int64_t>(512 + rmean) * dr * dr) >> 8)
        + 4 * dg * dg
        + ((<int64_t>(767 - rmean) * db * db) >> 8)
    )


cdef void select_bitonal_pair(
    int* pixels, int n_pixels, int full_mask,
    int* out_bg, int* out_fg, int* out_idx,
) noexcept nogil:
    """Select best 2-color pair for a cell of n_pixels pixel values."""
    cdef int unique[8]
    cdef int n_unique = 0
    cdef int i, j, k, found
    cdef int c0, c1, a, b, freq
    cdef int64_t max_dist, dist, best_score, score

    # Collect unique colors
    for i in range(n_pixels):
        found = 0
        for j in range(n_unique):
            if unique[j] == pixels[i]:
                found = 1
                break
        if not found:
            unique[n_unique] = pixels[i]
            n_unique += 1

    # Single color: solid block
    if n_unique == 1:
        out_bg[0] = unique[0]
        out_fg[0] = unique[0]
        out_idx[0] = 0
        return

    if n_unique == 2:
        c0 = unique[0]
        c1 = unique[1]
    else:
        # Find max distance among all unique pairs
        max_dist = 0
        for i in range(n_unique):
            for j in range(i + 1, n_unique):
                dist = color_distance(unique[i], unique[j])
                if dist > max_dist:
                    max_dist = dist
        if max_dist == 0:
            max_dist = 1

        # Find best pair by score = 0.85*(freq/n) + 0.15*(dist/max_dist)
        # Integer form: 85*freq*max_dist + 15*dist*n_pixels
        best_score = -1
        c0 = unique[0]
        c1 = unique[1]
        for i in range(n_unique):
            for j in range(i + 1, n_unique):
                a = unique[i]
                b = unique[j]
                freq = 0
                for k in range(n_pixels):
                    if pixels[k] == a or pixels[k] == b:
                        freq += 1
                dist = color_distance(a, b)
                score = 85 * freq * max_dist + 15 * dist * n_pixels
                if score > best_score:
                    best_score = score
                    c0 = a
                    c1 = b

    # Build index: bit=1 means fg (c1)
    cdef int index = 0
    cdef int fg_count = 0
    for i in range(n_pixels):
        if pixels[i] == c1:
            index |= (1 << i)
            fg_count += 1
        elif pixels[i] != c0:
            if color_distance(pixels[i], c1) < color_distance(pixels[i], c0):
                index |= (1 << i)
                fg_count += 1

    # Prefer more frequent color as background
    if fg_count > n_pixels // 2:
        c0, c1 = c1, c0
        index = (~index) & full_mask

    if index == 0:
        out_bg[0] = c0
        out_fg[0] = c0
        out_idx[0] = 0
    elif index == full_mask:
        out_bg[0] = c1
        out_fg[0] = c1
        out_idx[0] = 0
    else:
        out_bg[0] = c0
        out_fg[0] = c1
        out_idx[0] = index


cdef int remap_index(int* pixels, int n_pixels, int bg, int fg) noexcept nogil:
    cdef int idx = 0
    cdef int i
    for i in range(n_pixels):
        if color_distance(pixels[i], fg) < color_distance(pixels[i], bg):
            idx |= (1 << i)
    return idx


cdef int visual_pixel_diff(
    int bg1, int fg1, int idx1,
    int bg2, int fg2, int idx2,
    int n_bits,
) noexcept nogil:
    cdef int diff = 0
    cdef int b, old_color, new_color
    for b in range(n_bits):
        old_color = fg1 if (idx1 >> b) & 1 else bg1
        new_color = fg2 if (idx2 >> b) & 1 else bg2
        if old_color != new_color:
            diff += 1
    return diff


# Octant lookup table: 256 entries, each up to 4 UTF-8 bytes
cdef char _table[256][4]
cdef int _table_len[256]

# Display cache: flat arrays indexed by row * max_cols + col
DEF MAX_CELLS = 2880  # 80 * 36
DEF HYSTERESIS = 100

cdef int _cache_bg[MAX_CELLS]
cdef int _cache_fg[MAX_CELLS]
cdef int _cache_idx[MAX_CELLS]
cdef int _cache_valid[MAX_CELLS]
cdef int _last_refx, _last_refy, _last_max_rows, _last_max_cols
_last_refx = _last_refy = _last_max_rows = _last_max_cols = -1


@boundscheck(False)
cdef char* _blit_octant(
    uint32_t[:, ::1] image,
    int refx, int refy, int width, int height,
    int color_mode, char* base,
    int max_rows, int max_cols,
) noexcept nogil:

    cdef int current_x = refx
    cdef int current_y = refy
    cdef int current_fg = -1
    cdef int current_bg = -2
    cdef int row, col, py, px
    cdef int pixels[8]
    cdef int bg, fg, oct_idx
    cdef int new_x, new_y, cell
    cdef int prev_bg, prev_fg, prev_idx
    cdef int64_t direct_dist, swapped_dist, best_dist
    cdef int use_bg, use_fg
    cdef char* result = base

    # Move at reference point
    result = move_absolute(result, refx, refy)

    # Loop over terminal cells
    for row in range(max_rows):
        py = row * 4
        for col in range(max_cols):
            px = col * 2

            # Extract 8 pixels (masked to RGB)
            pixels[0] = image[py, px] & 0xFFFFFF
            pixels[1] = image[py, px + 1] & 0xFFFFFF
            pixels[2] = image[py + 1, px] & 0xFFFFFF
            pixels[3] = image[py + 1, px + 1] & 0xFFFFFF
            pixels[4] = image[py + 2, px] & 0xFFFFFF
            pixels[5] = image[py + 2, px + 1] & 0xFFFFFF
            pixels[6] = image[py + 3, px] & 0xFFFFFF
            pixels[7] = image[py + 3, px + 1] & 0xFFFFFF

            select_bitonal_pair(pixels, 8, 0xFF, &bg, &fg, &oct_idx)

            # Hysteresis: skip if cell unchanged from cached display
            cell = row * max_cols + col
            if _cache_valid[cell]:
                prev_bg = _cache_bg[cell]
                prev_fg = _cache_fg[cell]
                prev_idx = _cache_idx[cell]
                direct_dist = color_distance(bg, prev_bg) + color_distance(fg, prev_fg)
                swapped_dist = color_distance(bg, prev_fg) + color_distance(fg, prev_bg)
                best_dist = direct_dist if direct_dist < swapped_dist else swapped_dist
                if best_dist < HYSTERESIS and prev_bg != prev_fg and oct_idx != 0:
                    if direct_dist <= swapped_dist:
                        use_bg = prev_bg
                        use_fg = prev_fg
                    else:
                        use_bg = prev_fg
                        use_fg = prev_bg
                    bg = use_bg
                    fg = use_fg
                    oct_idx = remap_index(pixels, 8, use_bg, use_fg)
                if visual_pixel_diff(prev_bg, prev_fg, prev_idx, bg, fg, oct_idx, 8) == 0:
                    continue

            _cache_bg[cell] = bg
            _cache_fg[cell] = fg
            _cache_idx[cell] = oct_idx
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
            if oct_idx != 0 and fg != current_fg:
                result = set_foreground(result, fg, color_mode)
                current_fg = fg

            # Print octant character
            memcpy(result, &_table[oct_idx][0], _table_len[oct_idx])
            result += _table_len[oct_idx]
            current_y += 1

    # Reset attributes before returning the buffer
    result += sprintf(result, "\033[0m")
    return result


def init_table(list table_bytes):
    """Populate the C lookup table from Python-generated UTF-8 bytes."""
    cdef bytes b
    cdef int i, n
    for i in range(256):
        b = table_bytes[i]
        n = len(b)
        _table_len[i] = n
        memcpy(&_table[i][0], <char*>b, n)


def clear_cache():
    """Clear the display cache and invalidate stored params."""
    global _last_refx, _last_refy, _last_max_rows, _last_max_cols
    with nogil:
        memset(_cache_valid, 0, MAX_CELLS * sizeof(int))
    _last_refx = _last_refy = _last_max_rows = _last_max_cols = -1


def blit_octant(
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
        result = _blit_octant(
            image, refx, refy, width, height, color_mode,
            base, max_rows, max_cols,
        )

    try:
        return base[:result - base]
    finally:
        free(base)
