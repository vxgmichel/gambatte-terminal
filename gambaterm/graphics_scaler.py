"""Pixel scaler for sixel and kitty graphics protocols.

Queries terminal pixel dimensions and computes an integer nearest-neighbor
scale factor so the Game Boy frame fills the available pixel area while
preserving its 10:9 aspect ratio.
"""

from __future__ import annotations

import atexit
import os
import time
from typing import TYPE_CHECKING

import numpy as np

from .graphicsblit import (
    to_rgb,
    to_rgba_u8,
    encode_sixel,
    encode_kitty_rgba,
)

if TYPE_CHECKING:
    from blessed import Terminal
    from .console import Console
    from .colors import ColorMode

BASELINE_ID = 1
DELTA_ID = 2
KITTY_SCALE_MAX = int(os.environ.get("GAMBATERM_KITTY_SCALE_MAX", "4"))


class _Profile:
    """Collect frame-type counts and byte totals for bandwidth diagnosis."""
    __slots__ = ("keyframes", "deltas", "skipped", "bytes_out", "t0")

    def __init__(self) -> None:
        self.keyframes = 0
        self.deltas = 0
        self.skipped = 0
        self.bytes_out = 0
        self.t0 = time.monotonic()

    def dump(self, path: str) -> None:
        elapsed = time.monotonic() - self.t0
        if elapsed <= 0:
            return
        with open(path, "w") as f:
            f.write(
                f"elapsed_s={elapsed:.1f}\n"
                f"keyframes={self.keyframes}\n"
                f"deltas={self.deltas}\n"
                f"skipped={self.skipped}\n"
                f"total_bytes={self.bytes_out}\n"
                f"KB_s={self.bytes_out / elapsed / 1000:.0f}\n"
            )


class GraphicsScaler:
    """Pixel-dimension-aware scaler for sixel and kitty frame output.

    Query happens once via ``recompute`` (call on resize / first frame).
    Subsequent ``blit_sixel`` / ``blit_kitty`` calls use the cached scale
    and position.

    Kitty frames use a baseline image (i=1) with transparent delta updates
    (i=2) when only a fraction of the screen changes between frames.
    """

    __slots__ = ("scale", "kitty_scale", "refx", "refy", "refx_kitty", "refy_kitty",
                 "_baseline", "_had_delta", "_profile", "_frame_no", "_stats_fh")

    def __init__(self, scale: int, kitty_scale: int,
                 refx: int, refy: int,
                 refx_kitty: int, refy_kitty: int) -> None:
        self.scale = scale
        self.kitty_scale = kitty_scale
        self.refx = refx
        self.refy = refy
        self.refx_kitty = refx_kitty
        self.refy_kitty = refy_kitty
        self._baseline: np.ndarray | None = None
        self._had_delta = False
        self._profile = _Profile()
        self._frame_no = 0
        profile_dir = os.environ.get("GAMBATERM_PROFILE_DIR", "/tmp")
        self._stats_fh = open(f"{profile_dir}/gambatterm-frame-stats.csv", "w")
        self._stats_fh.write("frame_no,changed_pct,action,bytes,time_us\n")
        atexit.register(self._profile.dump, f"{profile_dir}/gambaterm-profile.txt")

    @property
    def position(self) -> tuple[int, int]:
        return self.refx_kitty, self.refy_kitty

    @classmethod
    def recompute(
        cls,
        term: Terminal,
        console: Console,
        height: int,
        width: int,
    ) -> GraphicsScaler:
        """Query terminal pixel geometry and return a new GraphicsScaler."""
        pixel_h, pixel_w = term.get_sixel_height_and_width(force=True)
        if pixel_h <= 0 or pixel_w <= 0:
            return cls(1, 1, 1, 1, 1, 1)
        scale = max(1, min(pixel_w // console.WIDTH, pixel_h // console.HEIGHT))
        kitty_scale = min(scale, KITTY_SCALE_MAX)
        cell_h = max(1, pixel_h // height)
        cell_w = max(1, pixel_w // width)

        def _pos(img_h, img_w):
            rx = max(1, (pixel_h - img_h) // 2 // cell_h + 1)
            ry = max(1, (pixel_w - img_w) // 2 // cell_w + 1)
            return rx, ry

        refx, refy = _pos(console.HEIGHT * scale, console.WIDTH * scale)
        refx_kitty, refy_kitty = _pos(
            console.HEIGHT * kitty_scale,
            console.WIDTH * kitty_scale,
        )
        return cls(scale, kitty_scale, refx, refy, refx_kitty, refy_kitty)

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
                self._profile.skipped += 1
                return b""

        self._profile.keyframes += 1
        colors = to_rgb(video)
        max_colors = min(color_mode.number_of_colors, 256)
        result = encode_sixel(colors, max_colors=max_colors, scale=self.scale)
        self._profile.bytes_out += len(result)
        return result

    def _encode_kitty(self, video, encode_fn):
        """Encode kitty frame: full keyframe on first call, delta otherwise."""
        t0 = time.perf_counter()
        self._frame_no += 1
        n = self._frame_no
        if self._baseline is None:
            self._profile.keyframes += 1
            self._baseline = video.copy()
            self._had_delta = False
            rgba = to_rgba_u8(video)
            if self.kitty_scale > 1:
                rgba = np.repeat(
                    np.repeat(rgba, self.kitty_scale, axis=0), self.kitty_scale, axis=1
                )
            h, w = rgba.shape[:2]
            result = encode_fn(rgba.tobytes(), w, h, image_id=BASELINE_ID)
            elapsed_us = int((time.perf_counter() - t0) * 1e6)
            self._stats_fh.write(f"{n},0.0,first_keyframe,{len(result)},{elapsed_us}\n")
            self._stats_fh.flush()
            return result

        diff = video != self._baseline
        changed = diff.sum()
        changed_pct = changed / video.size * 100
        if changed > video.size * 0.35:
            self._profile.keyframes += 1
            self._baseline = video.copy()
            rgba = to_rgba_u8(video)
            if self.kitty_scale > 1:
                rgba = np.repeat(
                    np.repeat(rgba, self.kitty_scale, axis=0), self.kitty_scale, axis=1
                )
            h, w = rgba.shape[:2]
            result = [encode_fn(rgba.tobytes(), w, h, image_id=BASELINE_ID)]
            if self._had_delta:
                result.append(f"\033[{self.refx_kitty};{self.refy_kitty}H".encode())
                result.append(encode_fn(
                    b"\x00" * (w * h * 4), w, h, image_id=DELTA_ID,
                ))
            self._had_delta = False
            result = b"".join(result)
            elapsed_us = int((time.perf_counter() - t0) * 1e6)
            self._stats_fh.write(
                f"{n},{changed_pct:.2f},rebaseline,{len(result)},{elapsed_us}\n")
            self._stats_fh.flush()
            return result

        self._had_delta = True
        self._profile.deltas += 1
        rgba = to_rgba_u8(video)
        rgba[~diff] = 0
        if self.kitty_scale > 1:
            rgba = np.repeat(
                np.repeat(rgba, self.kitty_scale, axis=0), self.kitty_scale, axis=1
            )
        h, w = rgba.shape[:2]
        result = encode_fn(rgba.tobytes(), w, h, image_id=DELTA_ID)
        elapsed_us = int((time.perf_counter() - t0) * 1e6)
        self._stats_fh.write(f"{n},{changed_pct:.2f},delta,{len(result)},{elapsed_us}\n")
        self._stats_fh.flush()
        return result

    def blit_kitty(
        self,
        video: np.ndarray,
        last_frame: np.ndarray | None,
        width: int,
        height: int,
        color_mode: ColorMode,
    ) -> bytes:
        """Encode ``video`` as a kitty RGBA escape sequence.

        Uses a baseline image (i=1) with transparent delta layers (i=2)
        for incremental updates.  Returns empty bytes when unchanged.
        """
        if last_frame is not None and video.shape == last_frame.shape:
            if np.array_equal(video, last_frame):
                self._profile.skipped += 1
                self._frame_no += 1
                n = self._frame_no
                self._stats_fh.write(f"{n},0.0,skip,0,0\n")
                self._stats_fh.flush()
                return b""
        result = self._encode_kitty(video, encode_kitty_rgba)
        self._profile.bytes_out += len(result)
        return result
