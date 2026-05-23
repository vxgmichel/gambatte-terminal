# cython: language_level=3

from cython cimport boundscheck
from libc.stdlib cimport malloc, free
from libc.stdint cimport uint32_t
from libc.string cimport memcmp, memcpy

cdef extern from "sixel.h":
    ctypedef unsigned char sixel_index_t
    ctypedef int SIXELSTATUS
    cdef int SIXEL_OK
    cdef int SIXEL_PALETTE_MAX
    cdef int SIXEL_PIXELFORMAT_RGBA8888
    cdef int SIXEL_LARGE_AUTO
    cdef int SIXEL_REP_AUTO
    cdef int SIXEL_QUALITY_AUTO
    cdef int SIXEL_DIFFUSE_AUTO
    cdef int SIXEL_ENCODEPOLICY_SIZE

    ctypedef void *(* sixel_malloc_t)(size_t)
    ctypedef void *(* sixel_calloc_t)(size_t, size_t)
    ctypedef void *(* sixel_realloc_t)(void *, size_t)
    ctypedef void (* sixel_free_t)(void *)

    cdef struct sixel_allocator:
        pass
    ctypedef sixel_allocator sixel_allocator_t

    SIXELSTATUS sixel_allocator_new(
        sixel_allocator_t **ppallocator,
        sixel_malloc_t fn_malloc,
        sixel_calloc_t fn_calloc,
        sixel_realloc_t fn_realloc,
        sixel_free_t fn_free,
    )
    void sixel_allocator_unref(sixel_allocator_t *allocator)

    cdef struct sixel_dither:
        pass
    ctypedef sixel_dither sixel_dither_t

    SIXELSTATUS sixel_dither_new(
        sixel_dither_t **ppdither,
        int ncolors,
        sixel_allocator_t *allocator,
    )
    void sixel_dither_unref(sixel_dither_t *dither)
    SIXELSTATUS sixel_dither_initialize(
        sixel_dither_t *dither,
        unsigned char *data,
        int width,
        int height,
        int pixelformat,
        int method_for_largest,
        int method_for_rep,
        int quality_mode,
    )
    void sixel_dither_set_diffusion_type(sixel_dither_t *dither, int method_for_diffuse)
    void sixel_dither_set_pixelformat(sixel_dither_t *dither, int pixelformat)

    cdef struct sixel_output:
        pass
    ctypedef sixel_output sixel_output_t
    ctypedef int (* sixel_write_function)(char *data, int size, void *priv)

    SIXELSTATUS sixel_output_new(
        sixel_output_t **output,
        sixel_write_function fn_write,
        void *priv,
        sixel_allocator_t *allocator,
    )
    void sixel_output_unref(sixel_output_t *output)
    void sixel_output_set_8bit_availability(sixel_output_t *output, int avail)
    void sixel_output_set_encode_policy(sixel_output_t *output, int policy)

    SIXELSTATUS sixel_encode(
        unsigned char *pixels,
        int width,
        int height,
        int depth,
        sixel_dither_t *dither,
        sixel_output_t *output,
    )


cdef extern from "stdio.h":
    int snprintf(char *buf, size_t size, const char *fmt, ...) nogil


cdef struct Buf:
    char *data
    size_t size
    size_t capacity


cdef int _buf_write(char *data, int size, void *priv) noexcept nogil:
    """Callback for libsixel: append data to a growable byte buffer."""
    cdef Buf *buf = <Buf *>priv
    cdef size_t new_cap
    cdef char *new_data
    cdef size_t usize = <size_t>size

    if buf.size + usize > buf.capacity:
        new_cap = buf.capacity * 2
        if new_cap < buf.size + usize:
            new_cap = buf.size + usize + 4096
        new_data = <char *>malloc(new_cap)
        if new_data == NULL:
            return -1
        if buf.data != NULL:
            memcpy(new_data, buf.data, buf.size)
            free(buf.data)
        buf.data = new_data
        buf.capacity = new_cap

    memcpy(buf.data + buf.size, data, usize)
    buf.size += usize
    return size


cdef int _check(SIXELSTATUS status) except -1:
    """Raise RuntimeError if libsixel call failed."""
    if status != SIXEL_OK:
        raise RuntimeError(f"libsixel error: 0x{status:04x}")
    return 0


@boundscheck(False)
def sixel_blit(
    uint32_t[:, ::1] image,
    uint32_t[:, ::1] last,
    int refx, int refy, int width, int height,
    int color_mode,
):
    """Convert a GameBoy frame to a sixel escape sequence.

    Args:
        image: uint32 RGBA pixel buffer (native GameBoy resolution).
        last: previous frame buffer for diff optimization, or None.
        refx, refy: cursor position (1-based row, column).
        width, height: terminal dimensions (unused in sixel mode).
        color_mode: ColorMode value (1=4color, 2=16color, 3=256color, 4=true).

    Returns:
        bytes: sixel escape sequence, or empty bytes if frame unchanged.
    """
    cdef int img_height = image.shape[0]
    cdef int img_width = image.shape[1]
    cdef int npixels = img_height * img_width
    cdef int i, idx, ncolors
    cdef uint32_t p
    cdef unsigned char *pixels = NULL
    cdef sixel_allocator_t *allocator = NULL
    cdef sixel_dither_t *dither = NULL
    cdef sixel_output_t *output = NULL
    cdef Buf buf
    cdef char pos_buf[32]
    cdef int n

    buf.data = NULL
    buf.size = 0
    buf.capacity = 0

    # Diff check: return empty if frame unchanged
    if last is not None:
        if img_height == last.shape[0] and img_width == last.shape[1]:
            if memcmp(&image[0, 0], &last[0, 0], npixels * sizeof(uint32_t)) == 0:
                return b""

    # Convert uint32 RGBA (native byte order) to R,G,B,A per pixel
    pixels = <unsigned char *>malloc(npixels * 4)
    if pixels == NULL:
        raise MemoryError("failed to allocate pixel buffer")

    try:
        idx = 0
        for i in range(npixels):
            p = image[i // img_width, i % img_width]
            pixels[idx + 0] = <unsigned char>((p >> 16) & 0xff)  # R
            pixels[idx + 1] = <unsigned char>((p >> 8) & 0xff)   # G
            pixels[idx + 2] = <unsigned char>(p & 0xff)          # B
            pixels[idx + 3] = <unsigned char>((p >> 24) & 0xff)  # A
            idx += 4

        # Number of colors for palette
        if color_mode <= 1:
            ncolors = 4
        elif color_mode == 2:
            ncolors = 16
        elif color_mode == 3:
            ncolors = 256
        else:
            ncolors = 256

        # Create allocator (NULL = use system malloc/free)
        _check(sixel_allocator_new(&allocator, NULL, NULL, NULL, NULL))

        # Create dither context and load palette from pixels
        _check(sixel_dither_new(&dither, ncolors, allocator))
        sixel_dither_set_pixelformat(dither, SIXEL_PIXELFORMAT_RGBA8888)
        sixel_dither_set_diffusion_type(dither, SIXEL_DIFFUSE_AUTO)
        _check(sixel_dither_initialize(
            dither, pixels, img_width, img_height,
            SIXEL_PIXELFORMAT_RGBA8888,
            SIXEL_LARGE_AUTO, SIXEL_REP_AUTO, SIXEL_QUALITY_AUTO,
        ))

        # Output buffer
        buf.capacity = img_width * img_height // 2  # initial estimate
        buf.data = <char *>malloc(buf.capacity)
        if buf.data == NULL:
            raise MemoryError("failed to allocate output buffer")

        _check(sixel_output_new(&output, _buf_write, &buf, allocator))
        sixel_output_set_8bit_availability(output, 0)
        sixel_output_set_encode_policy(output, SIXEL_ENCODEPOLICY_SIZE)

        # Encode to sixel
        _check(sixel_encode(pixels, img_width, img_height, 0, dither, output))

        # Position cursor; libsixel already produces DCS ... ST envelope
        n = snprintf(pos_buf, 32, "\033[%d;%dH", refx + 1, refy + 1)
        return pos_buf[:n] + buf.data[:buf.size]

    finally:
        free(pixels)
        if output != NULL:
            sixel_output_unref(output)
        if dither != NULL:
            sixel_dither_unref(dither)
        if allocator != NULL:
            sixel_allocator_unref(allocator)
        if buf.data != NULL:
            free(buf.data)
