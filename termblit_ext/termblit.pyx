# cython: language_level=3

from cython import boundscheck
from libc.stdio cimport sprintf
from libc.stdlib cimport malloc, free
from libc.stdint cimport uint32_t

include "blitcommon.pxi"


cdef int scale_256_to_6_closest(int x) noexcept nogil:
    if x < 48:
        return 0
    if x < 115:
        return 1
    return (x - 35) // 40

cdef int scale_256_to_6_spread(int x) noexcept nogil:
    return x // 43


@boundscheck(False)
cdef char* _blit(
    uint32_t[:, ::1] image,
    uint32_t[:, ::1] last,
    int refx, int refy, int width, int height,
    int color_mode,
    char* base,
) noexcept nogil:

    cdef int current_x = refx
    cdef int current_y = refy
    # Use 0x0 as "undrawn" sentinel: real GB pixels always have 0xFF
    # in the high byte, so 0x0 can never match
    cdef uint32_t current_fg = 0x0
    cdef uint32_t current_bg = 0x0
    cdef int row_index, column_index
    cdef uint32_t color1, color2
    cdef int new_x, new_y
    cdef int invert_print
    cdef int image_height = image.shape[0]
    cdef int image_width = image.shape[1]
    cdef char* result = base

    # Move at reference point
    result = move_absolute(result, refx, refy)

    # Loop over terminal cells
    for row_index in range(min(height - refx, image_height // 2)):
        for column_index in range(min(width - refy, image_width)):

            # Extract colors
            color1 = image[2 * row_index + 0, column_index]
            color2 = image[2 * row_index + 1, column_index]

            # Skip if identical to last printed frame
            if (
                last is not None and
                last[2 * row_index + 0, column_index] == color1 and
                last[2 * row_index + 1, column_index] == color2
            ):
                continue

            # Go to the new position
            new_x, new_y = row_index + refx, column_index + refy
            result = move_from_to(result, current_x, current_y, new_x, new_y)
            current_x, current_y = new_x, new_y

            # Print full block
            if color1 == color2 == current_fg != current_bg:
                result += sprintf(result, "\xe2\x96\x88")
                current_y += 1
                continue

            # Print empty block (space)
            if color1 == color2:
                if color1 != current_bg:
                    result = set_background(result, color1, color_mode)
                    current_bg = color1
                result += sprintf(result, " ")
                current_y += 1
                continue

            # Detect print type
            invert_print = (current_fg == color2 or current_bg == color1)

            # Inverted print
            if invert_print:
                color1, color2 = color2, color1

            # Set background and foreground colors if necessary
            if current_fg != color1:
                result = set_foreground(result, color1, color_mode)
                current_fg = color1
            if current_bg != color2:
                result = set_background(result, color2, color_mode)
                current_bg = color2

            # Print lower half block
            if invert_print:
                result += sprintf(result, "\xe2\x96\x84")
                current_y += 1

            # Print upper half block
            else:
                result += sprintf(result, "\xe2\x96\x80")
                current_y += 1

    return result


def blit(
    uint32_t[:, ::1] image,
    uint32_t[:, ::1] last,
    int refx, int refy, int width, int height,
    int color_mode,
):
    cdef char* base

    with nogil:
        base = <char *> malloc(image.shape[0] * image.shape[1] * 30)
        result = _blit(image, last, refx, refy, width, height, color_mode, base)

    try:
        return base[:result - base]
    finally:
        free(base)

