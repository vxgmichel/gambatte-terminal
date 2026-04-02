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
