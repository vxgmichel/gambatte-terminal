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


cdef int _cube_idx(int x) noexcept nogil:
    """Map 0-255 to 6x6x6 cube index (0-5) using proper boundaries."""
    if x < 48:
        return 0
    if x < 115:
        return 1
    if x < 155:
        return 2
    if x < 195:
        return 3
    if x < 235:
        return 4
    return 5


# 6x6x6 cube levels: 0, 95, 135, 175, 215, 255
cdef int _cube_val[6]
_cube_val[0] = 0
_cube_val[1] = 95
_cube_val[2] = 135
_cube_val[3] = 175
_cube_val[4] = 215
_cube_val[5] = 255


cdef int _color_dist_sq(int r1, int g1, int b1, int r2, int g2, int b2) noexcept nogil:
    """Squared Euclidean distance, weighted by perceptual sensitivity."""
    cdef int dr = r1 - r2
    cdef int dg = g1 - g2
    cdef int db = b1 - b2
    return 2 * dr * dr + 4 * dg * dg + db * db


cdef int _rgb_to_xterm256_uncached(int r, int g, int b) noexcept nogil:
    """Map RGB to xterm 256-color index, skipping theme colors 0-15."""
    # Cube candidate (16-231)
    cdef int ri = _cube_idx(r)
    cdef int gi = _cube_idx(g)
    cdef int bi = _cube_idx(b)
    cdef int cube_idx = 16 + 36 * ri + 6 * gi + bi
    cdef int cr = _cube_val[ri]
    cdef int cg = _cube_val[gi]
    cdef int cb = _cube_val[bi]
    cdef int cube_dist = _color_dist_sq(r, g, b, cr, cg, cb)

    # Grayscale candidate (232-255): values 8, 18, 28, ..., 238
    cdef int brightness = (r + g + b) // 3
    cdef int gray_offset = (brightness - 8) // 10
    if gray_offset < 0:
        gray_offset = 0
    if gray_offset > 23:
        gray_offset = 23
    cdef int gray_val = 8 + 10 * gray_offset
    cdef int gray_dist = _color_dist_sq(r, g, b, gray_val, gray_val, gray_val)

    if gray_dist < cube_dist:
        return 232 + gray_offset
    return cube_idx


cdef int rgb_to_xterm256(int r, int g, int b) noexcept nogil:
    """Cached 256-color lookup."""
    global _color_cache_init
    if not _color_cache_init:
        _init_color_caches()
        _color_cache_init = 1
    cdef int key = _color_cache_key(r, g, b)
    cdef int cached = _cache_256col[key]
    if cached >= 0:
        return cached
    cdef int result = _rgb_to_xterm256_uncached(r, g, b)
    _cache_256col[key] = result
    return result


# Standard ANSI 16-color palette RGB values and SGR codes.
# Colors 0-7 are normal (30-37), 8-15 are bright (90-97).
cdef int _ansi16_r[16]
cdef int _ansi16_g[16]
cdef int _ansi16_b[16]
cdef int _ansi16_sgr[16]
# 0=black 1=red 2=green 3=yellow 4=blue 5=magenta 6=cyan 7=white
_ansi16_r[:] = [0, 128, 0, 128, 0, 128, 0, 192, 128, 255, 0, 255, 0, 255, 0, 255]
_ansi16_g[:] = [0, 0, 128, 128, 0, 0, 128, 192, 128, 0, 255, 255, 0, 0, 255, 255]
_ansi16_b[:] = [0, 0, 0, 0, 128, 128, 128, 192, 128, 0, 0, 0, 255, 255, 255, 255]
_ansi16_sgr[:] = [30, 31, 32, 33, 34, 35, 36, 37, 90, 91, 92, 93, 94, 95, 96, 97]


# Color lookup caches: index by (r>>3, g>>3, b>>3) = 32K entries.
# -1 = not cached.  GB/GBC palette is small so this hits almost always.
DEF _COLOR_CACHE_SIZE = 32768
cdef int _cache_16col[_COLOR_CACHE_SIZE]
cdef int _cache_256col[_COLOR_CACHE_SIZE]
cdef int _color_cache_init = 0


cdef void _init_color_caches() noexcept nogil:
    cdef int i
    for i in range(_COLOR_CACHE_SIZE):
        _cache_16col[i] = -1
        _cache_256col[i] = -1


cdef int _color_cache_key(int r, int g, int b) noexcept nogil:
    return ((r >> 3) << 10) | ((g >> 3) << 5) | (b >> 3)


cdef int scale_rgb_to_16_colors(int r, int g, int b) noexcept nogil:
    """Find nearest ANSI 16-color by perceptual distance, with cache."""
    global _color_cache_init
    if not _color_cache_init:
        _init_color_caches()
        _color_cache_init = 1
    cdef int key = _color_cache_key(r, g, b)
    cdef int cached = _cache_16col[key]
    if cached >= 0:
        return cached
    cdef int i, best_idx, dist, best_dist
    best_idx = 0
    best_dist = 0x7FFFFFFF
    for i in range(16):
        dist = _color_dist_sq(r, g, b, _ansi16_r[i], _ansi16_g[i], _ansi16_b[i])
        if dist < best_dist:
            best_dist = dist
            best_idx = i
    _cache_16col[key] = _ansi16_sgr[best_idx]
    return _ansi16_sgr[best_idx]


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
        c = rgb_to_xterm256(r, g, b)
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
