# cython: language_level=3

from cython cimport boundscheck
from libc.stdlib cimport malloc, free
from libc.string cimport memcpy
from libc.stdint cimport uint32_t, uint8_t, int16_t
from cpython.bytes cimport PyBytes_FromStringAndSize

cimport numpy as cnp
import numpy as np
import zlib
import base64
import os

cnp.import_array()

ZLIB_LEVEL = int(os.environ.get("GAMBATERM_ZLIB_LEVEL", "3"))


SIXEL_BITS = np.array([1, 2, 4, 8, 16, 32], dtype=np.uint8)
DCS_START = b"\x1bP0;1;0q"
DCS_END = b"\x1b\\"
APC_START = b"\x1b_G"
APC_END = b"\x1b\\"


@boundscheck(False)
def to_rgb(uint32_t[:, ::1] video):
    """Convert uint32 (H,W) in 0xAARRGGBB to float32 (H,W,3) in [0,1]."""
    cdef int h = video.shape[0]
    cdef int w = video.shape[1]
    cdef int y, x
    cdef uint32_t p
    cdef float[:, :, ::1] out = np.empty((h, w, 3), dtype=np.float32)
    for y in range(h):
        for x in range(w):
            p = video[y, x]
            out[y, x, 0] = <float>((p >> 16) & 0xFF) / 255.0
            out[y, x, 1] = <float>((p >> 8) & 0xFF) / 255.0
            out[y, x, 2] = <float>(p & 0xFF) / 255.0
    return np.asarray(out)


@boundscheck(False)
def to_rgba_u8(uint32_t[:, ::1] video):
    """Convert uint32 (H,W) in 0xAARRGGBB to uint8 (H,W,4) RGBA."""
    cdef int h = video.shape[0]
    cdef int w = video.shape[1]
    cdef int y, x
    cdef uint32_t p
    cdef uint8_t[:, :, ::1] out = np.empty((h, w, 4), dtype=np.uint8)
    for y in range(h):
        for x in range(w):
            p = video[y, x]
            out[y, x, 0] = <uint8_t>((p >> 16) & 0xFF)
            out[y, x, 1] = <uint8_t>((p >> 8) & 0xFF)
            out[y, x, 2] = <uint8_t>(p & 0xFF)
            out[y, x, 3] = 255
    return np.asarray(out)


@boundscheck(False)
def quantize_colors(float[:, :, ::1] colors, int n_colors):
    """Quantize RGB colors to a uniform cube palette.

    Returns (indices (H,W) uint8, palette (N,3) float32).
    """
    cdef int levels = 2
    while (levels + 1) * (levels + 1) * (levels + 1) <= n_colors and levels < 6:
        levels += 1

    cdef int h = colors.shape[0]
    cdef int w = colors.shape[1]
    cdef int y, x, i
    cdef int ri, gi, bi
    cdef int n_actual = levels * levels * levels
    cdef float scale = <float>(levels - 0.001)

    cdef uint8_t[:, ::1] indices = np.empty((h, w), dtype=np.uint8)
    for y in range(h):
        for x in range(w):
            ri = <int>(colors[y, x, 0] * scale)
            gi = <int>(colors[y, x, 1] * scale)
            bi = <int>(colors[y, x, 2] * scale)
            indices[y, x] = <uint8_t>(ri * levels * levels + gi * levels + bi)

    cdef float[:, ::1] palette = np.zeros((n_actual, 3), dtype=np.float32)
    for i in range(n_actual):
        ri = i // (levels * levels)
        gi = (i // levels) % levels
        bi = i % levels
        palette[i, 0] = <float>ri / <float>(levels - 1) if levels > 1 else 0.0
        palette[i, 1] = <float>gi / <float>(levels - 1) if levels > 1 else 0.0
        palette[i, 2] = <float>bi / <float>(levels - 1) if levels > 1 else 0.0

    return np.asarray(indices), np.asarray(palette)


@boundscheck(False)
def encode_sixel(float[:, :, ::1] colors, int max_colors=256, int scale=1,
                 uint8_t[:, ::1] indices=None, float[:, ::1] palette=None,
                 int skip_index=-1):
    """Encode an RGB image as a sixel escape sequence.

    Returns bytes (the full escape sequence).

    If *indices* and *palette* are provided, internal quantization is
    skipped and the pre-computed values are used.  *skip_index* is a
    colour index that is never emitted to the sixel stream, producing
    transparent pixels when P2=1.
    """
    cdef int h = colors.shape[0]
    cdef int w = colors.shape[1]

    # Scale via numpy (already fast C)
    cdef float[:, :, ::1] scaled_colors
    cdef int use_precomputed = indices is not None and palette is not None
    if scale > 1:
        arr = np.asarray(colors)
        arr = np.repeat(np.repeat(arr, scale, axis=0), scale, axis=1)
        scaled_colors = arr
        h = scaled_colors.shape[0]
        w = scaled_colors.shape[1]
        if use_precomputed:
            indices = np.ascontiguousarray(
                np.repeat(np.repeat(np.asarray(indices), scale, axis=0),
                          scale, axis=1),
                dtype=np.uint8)
    else:
        scaled_colors = colors

    # Pad to multiple of 6
    cdef int pad_h = (6 - h % 6) % 6
    if pad_h > 0:
        arr = np.asarray(scaled_colors)
        arr = np.pad(arr, ((0, pad_h), (0, 0), (0, 0)), constant_values=0)
        scaled_colors = arr
        h = scaled_colors.shape[0]
        if use_precomputed:
            indices_padded = np.zeros((h, w), dtype=np.uint8)
            indices_padded[:indices.shape[0], :] = np.asarray(indices)
            indices = indices_padded

    cdef uint8_t[:, ::1] _indices
    cdef float[:, ::1] _palette
    if use_precomputed:
        _indices = indices
        _palette = palette
    else:
        indices, palette = quantize_colors(scaled_colors, max_colors)
        _indices = indices
        _palette = palette

    cdef int n_colors = _palette.shape[0]
    cdef int i, band_y, x, start, length
    cdef int color_idx
    cdef uint8_t pat_byte
    cdef int found

    parts = []

    # DCS header
    parts.append(DCS_START)
    parts.append(f'"1;1;{w};{h}'.encode())

    # Palette
    for i in range(n_colors):
        parts.append(
            f"#{i};2;{<int>(_palette[i, 0] * 100)};"
            f"{<int>(_palette[i, 1] * 100)};{<int>(_palette[i, 2] * 100)}".encode()
        )

    # Encode bands
    cdef uint8_t[:, ::1] band
    cdef uint8_t[:] sixel_bits = SIXEL_BITS
    cdef uint8_t[:] row_patterns
    cdef int[256] seen

    for band_y in range(0, h, 6):
        band = _indices[band_y:band_y + 6, :]
        for i in range(256):
            seen[i] = 0
        for y in range(band.shape[0]):
            for x in range(w):
                seen[band[y, x]] = 1

        for color_idx in range(256):
            if color_idx == skip_index:
                continue
            if seen[color_idx] == 0:
                continue
            parts.append(f"#{color_idx}".encode())

            if w == 0:
                continue

            # Compute sixel patterns for this color
            row_patterns = np.zeros(w, dtype=np.uint8)
            for y in range(band.shape[0]):
                for x in range(w):
                    if band[y, x] == color_idx:
                        row_patterns[x] |= sixel_bits[y]

            # Run-length encode
            parts.append(_sixel_rle(row_patterns, w))

            parts.append(b"$")
        parts.append(b"-")

    parts.append(DCS_END)
    return b"".join(parts)


cdef bytes _sixel_rle(uint8_t[:] patterns, int w):
    """Run-length encode a row of sixel patterns."""
    cdef list runs = []
    cdef int start = 0
    cdef int i
    cdef uint8_t cur = patterns[0]

    for i in range(1, w):
        if patterns[i] != cur:
            runs.append((cur, i - start))
            cur = patterns[i]
            start = i
    runs.append((cur, w - start))

    parts = []
    for pat, length in runs:
        char = chr(0x3F + pat)
        if length > 3:
            parts.append(f"!{length}{char}".encode())
        else:
            parts.append(char.encode() * length)
    return b"".join(parts)


def encode_kitty_rgba(const unsigned char[:] rgba_data, int w, int h,
                      int image_id=1, int X=0, int Y=0, int z=0,
                      int placement_id=0):
    """Encode RGBA bytes as kitty f=32 escape sequence.

    *image_id* sets the kitty image ID for placement/stacking control.
    *X*, *Y* set intra-cell pixel offsets for positioned placement.
    *z* sets z-index (0=default, 1=above baseline for deltas).
    *placement_id* sets the p= key for placement replacement (0=none).
    """
    cdef bytes raw
    if isinstance(rgba_data, memoryview):
        raw = bytes(rgba_data)
    else:
        raw = bytes(rgba_data)
    compressed = zlib.compress(raw, ZLIB_LEVEL)
    payload_b64 = base64.b64encode(compressed).decode()
    cdef str control = f"a=T,i={image_id},q=2,f=32,s={w},v={h},o=z"
    if z:
        control += f",z={z}"
    if X or Y:
        control += f",X={X},Y={Y}"
    if placement_id:
        control += f",p={placement_id}"
    return f"{APC_START.decode()}{control};{payload_b64}{APC_END.decode()}".encode()
