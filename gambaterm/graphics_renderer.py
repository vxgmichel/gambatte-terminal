"""Sixel and Kitty graphics protocol encoders for gambatte-terminal.

Pure Python + numpy — no libsixel dependency.  Ported from telix.
"""

from __future__ import annotations

import io
import os
import zlib
import base64

import numpy as np

DCS_START = "\033P0;1;0q"
DCS_END = "\033\\"
APC_START = "\033_G"
APC_END = "\033\\"
SIXEL_BITS = np.array([1, 2, 4, 8, 16, 32], dtype=np.uint8)

# CPU vs. Bandwidth trade-off, levels 1-3 are comparable performance, but compression level 4 costs
# almost 2x of level 3 and begins to cut into framerate. I also tested PNG, which is slower+larger
# due to overhead of PNG header.
ZLIB_LEVEL = int(os.environ.get("GAMBATERM_ZLIB_LEVEL", "3"))

def quantize_colors(colors: np.ndarray, n_colors: int) -> tuple[np.ndarray, np.ndarray]:
    """Quantize RGB colors to a uniform cube palette.

    :param colors: (H, W, 3) float32 in [0, 1].
    :param n_colors: maximum palette size.
    :returns: (indexed, palette) — indexed (H, W) uint8, palette (N, 3) float32.
    """
    levels = 2
    while (levels + 1) ** 3 <= n_colors and levels < 6:
        levels += 1

    r = (colors[:, :, 0] * (levels - 0.001)).astype(np.uint8)
    g = (colors[:, :, 1] * (levels - 0.001)).astype(np.uint8)
    b = (colors[:, :, 2] * (levels - 0.001)).astype(np.uint8)
    indices = r * levels * levels + g * levels + b

    n_actual = levels**3
    palette = np.zeros((n_actual, 3), dtype=np.float32)
    for i in range(n_actual):
        ri = i // (levels * levels)
        gi = (i // levels) % levels
        bi = i % levels
        palette[i] = [
            ri / (levels - 1) if levels > 1 else 0,
            gi / (levels - 1) if levels > 1 else 0,
            bi / (levels - 1) if levels > 1 else 0,
        ]

    return indices.astype(np.uint8), palette


def encode_sixel(
    colors: np.ndarray,
    dest: io.TextIOBase,
    max_colors: int = 256,
    scale: int = 1,
) -> None:
    """Encode an RGB image as a sixel escape sequence and write to *dest*.

    :param colors: (H, W, 3) float32 in [0, 1].
    :param dest: text stream to write the escape sequence into.
    :param max_colors: maximum palette size.
    :param scale: integer pixel scale factor for cell-size compensation.
    """
    h, w = colors.shape[:2]

    if scale > 1:
        colors = np.repeat(np.repeat(colors, scale, axis=0), scale, axis=1)
        h, w = colors.shape[:2]

    pad_h = (6 - h % 6) % 6
    if pad_h > 0:
        colors = np.pad(colors, ((0, pad_h), (0, 0), (0, 0)), constant_values=0)
        h = colors.shape[0]

    indices, palette = quantize_colors(colors, max_colors)

    dest.write(DCS_START)
    dest.write(f'"1;1;{w};{h}')
    for i, (r, g, b) in enumerate(palette):
        dest.write(f"#{i};2;{int(r * 100)};{int(g * 100)};{int(b * 100)}")

    for band_y in range(0, h, 6):
        band = indices[band_y : band_y + 6, :]
        present = np.unique(band)
        for color_idx in present:
            mask = band == color_idx
            patterns = np.dot(mask.T.astype(np.uint8), SIXEL_BITS).astype(np.uint8)
            dest.write(f"#{color_idx}")
            if w == 0:
                continue
            changes = np.diff(patterns, prepend=np.uint8(~patterns[0]))
            run_starts = np.where(changes != 0)[0]
            run_lengths = np.diff(np.append(run_starts, w))
            for start, length in zip(run_starts, run_lengths):
                pat = int(patterns[start])
                char = chr(0x3F + pat)
                if length > 3:
                    dest.write(f"!{length}{char}")
                else:
                    dest.write(char * length)
            dest.write("$")
        dest.write("-")

    dest.write(DCS_END)


def kitty_blit_bytes(
    rgba_data: bytes,
    w: int,
    h: int,
) -> bytes:
    """Return a Kitty graphics escape sequence as raw bytes.

    Control data is raw ASCII per kitty spec. Payload is base64-encoded
    zlib-compressed RGBA data.

    :param rgba_data: raw uint8 RGBA bytes (w * h * 4).
    :param w: image width in pixels.
    :param h: image height in pixels.
    """
    control = f"a=T,q=2,f=32,s={w},v={h},o=z"
    compressed = zlib.compress(rgba_data, level=ZLIB_LEVEL)
    payload_b64 = base64.b64encode(compressed).decode()
    return f"{APC_START}{control};{payload_b64}{APC_END}".encode()
