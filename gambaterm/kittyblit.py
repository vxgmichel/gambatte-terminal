"""Kitty graphics protocol blitter for gambatte-terminal.

Encodes GameBoy frames as ``APC G ... ST`` escape sequences using raw
RGBA pixels with zlib compression.  The Kitty graphics protocol is
supported by ~5 terminals (ghostty, kitty, konsole, wezterm, iTerm2).
"""

from __future__ import annotations

import base64
import zlib

import numpy as np


def kitty_blit(
    image: np.ndarray,
    last: np.ndarray | None,
    refx: int,
    refy: int,
    width: int,
    height: int,
    color_mode: int,
) -> bytes:
    """Convert a GameBoy frame to a Kitty graphics escape sequence.

    Ttransmits raw RGBA pixels (``f=32``) with zlib compression (``o=z``).
    The image is placed at the text cursor, so a CUP sequence is prepended.

    Args:
        image: uint32 RGBA pixel buffer (H×W native GameBoy resolution,
               or scaled).
        last: previous frame buffer for diff optimization, or None.
        refx, refy: cursor position (1-based row, column).
        width, height: terminal character dimensions (unused).
        color_mode: ColorMode value (unused; Kitty always receives RGB).

    Returns:
        bytes: Kitty graphics escape sequence, or empty bytes if frame
               unchanged.
    """
    if last is not None and image.shape == last.shape:
        if np.array_equal(image, last):
            return b""

    img_h, img_w = image.shape[:2]

    # uint32 RGBA -> R,G,B,A bytes (native byte order)
    rgba = image.view(np.uint8).reshape(img_h, img_w, 4)

    # Zlib-compress the raw pixel data
    payload = zlib.compress(rgba.tobytes())

    # Build control data (key=value pairs, comma-separated, base64-encoded)
    control = (
        f"a=T,q=2,f=32,s={img_w},{img_h},"
        f"c={img_w},{img_h},o=z"
    )
    control_b64 = base64.b64encode(control.encode()).decode().rstrip("=")

    cup = f"\033[{refx};{refy}H".encode()
    return cup + f"\033_G{control_b64};".encode() + payload + b"\033\\"
