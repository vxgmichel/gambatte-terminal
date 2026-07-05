"""Pixel scaler for sixel and kitty graphics protocols.

Queries terminal pixel dimensions and computes an integer nearest-neighbor
scale factor so the Game Boy frame fills the available pixel area while
preserving its 10:9 aspect ratio.
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

import numpy as np

from .graphics_renderer import encode_sixel, kitty_blit_bytes

if TYPE_CHECKING:
    from blessed import Terminal
    from .console import Console
    from .colors import ColorMode


class SixelScaler:
    """Pixel-dimension-aware scaler for sixel and kitty frame output.

    Query happens once via ``recompute`` (call on resize / first frame).
    Subsequent ``blit_sixel`` / ``blit_kitty`` calls use the cached scale
    and position.
    """

    __slots__ = ("_scale", "_refx", "_refy")

    def __init__(self, scale: int, refx: int, refy: int) -> None:
        self._scale = scale
        self._refx = refx
        self._refy = refy

    @property
    def scale(self) -> int:
        return self._scale

    @property
    def position(self) -> tuple[int, int]:
        return self._refx, self._refy

    @classmethod
    def recompute(
        cls,
        term: Terminal,
        console: Console,
        height: int,
        width: int,
    ) -> SixelScaler:
        """Query terminal pixel geometry and return a new SixelScaler."""
        pixel_h, pixel_w = term.get_sixel_height_and_width(force=True)
        if pixel_h <= 0 or pixel_w <= 0:
            return cls(1, 1, 1)
        scale = max(1, min(pixel_w // console.WIDTH, pixel_h // console.HEIGHT))
        scaled_h = console.HEIGHT * scale
        scaled_w = console.WIDTH * scale
        cell_h = max(1, pixel_h // height)
        cell_w = max(1, pixel_w // width)
        refx = max(1, (pixel_h - scaled_h) // 2 // cell_h + 1)
        refy = max(1, (pixel_w - scaled_w) // 2 // cell_w + 1)
        return cls(scale, refx, refy)

    def to_rgb(self, video: np.ndarray) -> np.ndarray:
        """Convert uint32 RGBA (H, W) to float32 RGB (H, W, 3) in [0, 1].

        gambatte-core stores pixels as 0xAARRGGBB; little-endian memory
        layout is [BB, GG, RR, AA].  Extract [RR, GG, BB].
        """
        img_h, img_w = video.shape[:2]
        rgba = video.view(np.uint8).reshape(img_h, img_w, 4)
        return rgba[:, :, 2::-1].astype(np.float32) / 255.0

    def to_rgba_u8(self, video: np.ndarray) -> np.ndarray:
        """Convert uint32 RGBA (H, W) to uint8 RGBA (H, W, 4).

        gambatte-core stores pixels as 0xAARRGGBB; little-endian memory
        layout is [BB, GG, RR, AA].  Kitty f=32 expects RGBA order.
        """
        img_h, img_w = video.shape[:2]
        rgba = video.view(np.uint8).reshape(img_h, img_w, 4)
        out = np.empty((img_h, img_w, 4), dtype=np.uint8)
        out[:, :, 0] = rgba[:, :, 2]  # R
        out[:, :, 1] = rgba[:, :, 1]  # G
        out[:, :, 2] = rgba[:, :, 0]  # B
        out[:, :, 3] = 255
        return out

    def blit_sixel(
        self,
        video: np.ndarray,
        last_frame: np.ndarray | None,
        width: int,
        height: int,
        color_mode: ColorMode,
    ) -> bytes:
        """Encode ``video`` as a sixel escape sequence.

        Returns empty bytes if the frame is unchanged from *last_frame*.
        """
        if last_frame is not None and video.shape == last_frame.shape:
            if np.array_equal(video, last_frame):
                return b""

        colors = self.to_rgb(video)
        max_colors = min(color_mode.number_of_colors, 256)
        buf = io.StringIO()
        encode_sixel(colors, buf, max_colors=max_colors, scale=self._scale)
        return buf.getvalue().encode("latin-1")

    def blit_kitty(
        self,
        video: np.ndarray,
        last_frame: np.ndarray | None,
        width: int,
        height: int,
        color_mode: ColorMode,
    ) -> bytes:
        """Encode ``video`` as a kitty graphics escape sequence.

        Returns empty bytes if the frame is unchanged from *last_frame*.
        """
        if last_frame is not None and video.shape == last_frame.shape:
            if np.array_equal(video, last_frame):
                return b""

        # Convert to uint8 RGBA first (at native 160×144), then scale
        rgba_u8 = self.to_rgba_u8(video).copy()
        if self._scale > 1:
            rgba_u8 = np.repeat(
                np.repeat(rgba_u8, self._scale, axis=0),
                self._scale, axis=1,
            )
        img_h, img_w = rgba_u8.shape[:2]
        return kitty_blit_bytes(rgba_u8.tobytes(), img_w, img_h)
