"""Pixel scaler for sixel and kitty graphics protocols.

Queries terminal pixel dimensions and computes an integer nearest-neighbor
scale factor so the Game Boy frame fills the available pixel area while
preserving its 10:9 aspect ratio.  Scaling and encoding are composed into
``blit_sixel`` and ``blit_kitty`` methods.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from .sixelblit import sixel_blit as _sixel_blit
from .kittyblit import kitty_blit as _kitty_blit

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
        refx = (pixel_h - scaled_h) // 2 // cell_h + 1
        refy = (pixel_w - scaled_w) // 2 // cell_w + 1
        return cls(scale, refx, refy)

    def _scaled(
        self,
        video: np.ndarray,
        last_frame: np.ndarray | None,
    ) -> tuple[np.ndarray, np.ndarray | None]:
        """Return (video, last) scaled to ``self._scale``, or originals."""
        if self._scale <= 1:
            return video, last_frame
        scaled_video = np.repeat(
            np.repeat(video, self._scale, axis=0),
            self._scale, axis=1,
        )
        scaled_last: np.ndarray | None = None
        if last_frame is not None:
            scaled_last = np.repeat(
                np.repeat(last_frame, self._scale, axis=0),
                self._scale, axis=1,
            )
        return scaled_video, scaled_last

    def blit_sixel(
        self,
        video: np.ndarray,
        last_frame: np.ndarray | None,
        width: int,
        height: int,
        color_mode: ColorMode,
    ) -> bytes:
        """Scale ``video`` and encode as a sixel escape sequence."""
        scaled_video, scaled_last = self._scaled(video, last_frame)
        return _sixel_blit(
            scaled_video, scaled_last,
            self._refx, self._refy, width - 1, height, color_mode,
        )

    def blit_kitty(
        self,
        video: np.ndarray,
        last_frame: np.ndarray | None,
        width: int,
        height: int,
        color_mode: ColorMode,
    ) -> bytes:
        """Scale ``video`` and encode as a kitty graphics escape sequence."""
        scaled_video, scaled_last = self._scaled(video, last_frame)
        return _kitty_blit(
            scaled_video, scaled_last,
            self._refx, self._refy, width - 1, height, color_mode,
        )
