"""Pixel scaler for sixel and kitty graphics protocols."""

from __future__ import annotations

import atexit
import os
import time
import json
from typing import TYPE_CHECKING, Callable

import numpy as np

from .graphicsblit import (
    to_rgb,
    to_rgba_u8,
    encode_sixel,
    encode_kitty_rgba,
    quantize_colors,
)
from .graphics_autoscaler import (
    AutoScale,
    AutoScaleConfig,
    SCALE_MAX,
)
from .remote_terminal import (
    GraphicsProtocol,
    FORCE_KITTY_BLITLESS,
    KITTY_GFX_CLEAR,
    KITTY_GFX_GHOSTTY_CLEAR,
    TEXT_HOME_CLEAR,
    SIXEL_FORCE_REFRESH_ON_FOCUS,
    XTERM_SIXEL_SCALE_CAP,
    FORCE_KITTY_INDIVIDUAL_DELETES,
)

if TYPE_CHECKING:
    from blessed import Terminal
    from .console import Console

BASELINE_ID = 1
DELTA_ID = 100
SIXEL_REBASELINE_THRESHOLD = float(os.environ.get("GAMBATERM_SIXEL_REBASELINE", "0.35"))
KITTY_REBASELINE_THRESHOLD = float(os.environ.get("GAMBATERM_KITTY_REBASELINE", "0.35"))
KITTY_REBASELINE_RECT = float(os.environ.get("GAMBATERM_KITTY_REBASELINE_RECT", "0.60"))


def blit_vis_channels(rgb: np.ndarray, mode: int) -> np.ndarray:
    """Apply channel permutation for blit visualization."""
    if mode == 1:
        return np.ascontiguousarray(rgb[..., [2, 1, 0]])
    if mode == 2:
        return np.ascontiguousarray(rgb[..., [1, 0, 2]])
    return rgb


class GraphicsScaler:
    """Geometry-only: pixel scale, cell size, and positioning for terminal graphics."""

    __slots__ = (
        "scale",
        "kitty_scale",
        "refx",
        "refy",
        "refx_kitty",
        "refy_kitty",
        "cell_h",
        "cell_w",
    )

    def __init__(
        self,
        scale: int,
        kitty_scale: int,
        refx: int,
        refy: int,
        refx_kitty: int,
        refy_kitty: int,
        cell_h: int,
        cell_w: int,
    ) -> None:
        self.scale = scale
        self.kitty_scale = kitty_scale
        self.refx = refx
        self.refy = refy
        self.refx_kitty = refx_kitty
        self.refy_kitty = refy_kitty
        self.cell_h = cell_h
        self.cell_w = cell_w

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
        autoscale: AutoScale | None = None,
        terminal_name: str = "",
    ) -> GraphicsScaler:
        """Query terminal pixel geometry and return a new GraphicsScaler."""
        pixel_h, pixel_w = term.get_sixel_height_and_width(force=True)
        if pixel_h <= 0 or pixel_w <= 0:
            return cls(1, 1, 1, 1, 1, 1, 1, 1)
        natural_scale = max(1, min(pixel_w // console.WIDTH, pixel_h // console.HEIGHT))
        if autoscale is not None:
            if autoscale.max_scale > natural_scale:
                autoscale.max_scale = natural_scale
            effective_cap = autoscale.max_scale
        else:
            effective_cap = min(natural_scale, SCALE_MAX)
        floor = max(1, natural_scale // 2)
        graphics_scale = max(floor, effective_cap)
        cell_h = max(1, pixel_h // height)
        cell_w = max(1, pixel_w // width)

        sixel_scale = graphics_scale
        if terminal_name.startswith(XTERM_SIXEL_SCALE_CAP):
            sixel_scale = min(sixel_scale, 6)
        if pixel_h - console.HEIGHT * sixel_scale < cell_h and sixel_scale > 1:
            sixel_scale -= 1

        while sixel_scale > 1:
            img_h = console.HEIGHT * sixel_scale
            rows = (img_h + cell_h - 1) // cell_h
            refx = max(2, (pixel_h - img_h) // 2 // cell_h + 1)
            if refx + rows <= height:
                break
            sixel_scale -= 1

        kitty_scale = graphics_scale

        while kitty_scale > 1:
            img_h = console.HEIGHT * kitty_scale
            rows = (img_h + cell_h - 1) // cell_h
            if 2 + rows <= height:
                break
            kitty_scale -= 1

        def pos(img_h: int, img_w: int) -> tuple[int, int]:
            rx = max(2, (pixel_h - img_h) // 2 // cell_h + 1)
            ry = max(1, (pixel_w - img_w) // 2 // cell_w + 1)
            return rx, ry

        refx, refy = pos(console.HEIGHT * sixel_scale, console.WIDTH * sixel_scale)
        refx_kitty, refy_kitty = pos(
            console.HEIGHT * kitty_scale,
            console.WIDTH * kitty_scale,
        )
        return cls(
            sixel_scale,
            kitty_scale,
            refx,
            refy,
            refx_kitty,
            refy_kitty,
            cell_h,
            cell_w,
        )


class FrameEncoder:
    """Pixel-dimension-aware scaler for sixel and kitty frame output.

    Query happens once via ``recompute`` (call on resize / first frame).
    Subsequent ``encode_sixel`` / ``encode_kitty`` calls use the cached scale
    and position.

    Kitty frames use a baseline image with transparent delta updates
    when only a fraction of the screen changes between frames.  A
    single-slot keyframe hash cache replays an identical keyframe via
    ``a=p``, avoiding re-transmission of pixel data.
    """

    __slots__ = (
        "scale",
        "kitty_scale",
        "refx",
        "refy",
        "refx_kitty",
        "refy_kitty",
        "cell_h",
        "cell_w",
        "baseline",
        "sixel_baseline",
        "sixel_frame_no",
        "_delta_is_placed",
        "kitty_frame_no",
        "dump_dir",
        "stats_fh",
        "blitter_vis",
        "_keyframes",
        "_deltas",
        "_skipped",
        "_bytes_out",
        "_t0",
        "_last_keyframe_hash",
        "_cached_hits",
        "_frames_since_rebaseline",
        "_force_rebaseline_every",
    )

    def __init__(
        self,
        scale: int,
        kitty_scale: int,
        refx: int,
        refy: int,
        refx_kitty: int,
        refy_kitty: int,
        cell_h: int,
        cell_w: int,
    ) -> None:
        self.scale = scale
        self.kitty_scale = kitty_scale
        self.refx = refx
        self.refy = refy
        self.refx_kitty = refx_kitty
        self.refy_kitty = refy_kitty
        self.cell_h = cell_h
        self.cell_w = cell_w
        self.baseline: np.ndarray | None = None
        self.sixel_baseline: np.ndarray | None = None
        self._delta_is_placed = False
        self.kitty_frame_no = 0
        self.sixel_frame_no = 0
        self.blitter_vis = 0
        self._keyframes = 0
        self._deltas = 0
        self._skipped = 0
        self._bytes_out = 0
        self._t0 = time.monotonic()
        self._last_keyframe_hash: int | None = None
        self._cached_hits = 0
        self._frames_since_rebaseline = 0
        self._force_rebaseline_every = int(os.environ.get(
            "GAMBATERM_FORCE_REBASELINE", "0"
        ))
        self.dump_dir = os.environ.get("GAMBATERM_DUMP_FRAMES")
        if self.dump_dir is not None:
            os.makedirs(self.dump_dir, exist_ok=True)
        csv_path = os.environ.get("GAMBATERM_PROFILE")
        if csv_path is None:
            self.stats_fh = open(os.devnull, "w")
        else:
            os.makedirs(os.path.dirname(csv_path) or ".", exist_ok=True)
            self.stats_fh = open(csv_path, "w")
            self.stats_fh.write(
                "frame_no,changed_pct,action,bytes,time_us,"
                "row,col,cell_h,cell_w,padded_w,padded_h,"
                "x1,y1,rect_w,rect_h,"
                "refx_kitty,refy_kitty,scale\n"
            )
            stem, _ = os.path.splitext(csv_path)
            atexit.register(self._dump_profile, f"{stem}-summary.txt")

    def _dump_profile(self, path: str) -> None:
        elapsed = time.monotonic() - self._t0
        if elapsed <= 0:
            return
        with open(path, "w") as f:
            f.write(
                f"elapsed_s={elapsed:.1f}\n"
                f"keyframes={self._keyframes}\n"
                f"deltas={self._deltas}\n"
                f"skipped={self._skipped}\n"
                f"cache_hits={self._cached_hits}\n"
                f"total_bytes={self._bytes_out}\n"
                f"KB_s={self._bytes_out / elapsed / 1000:.0f}\n"
            )

    @property
    def position(self) -> tuple[int, int]:
        return self.refx_kitty, self.refy_kitty

    def dump_frame(self, video: np.ndarray, n: int, **extra: object) -> None:
        """Write frame NPY and scaler metadata when GAMBATERM_DUMP_FRAMES is set."""
        if self.dump_dir is None:
            return
        np.save(f"{self.dump_dir}/{n:05d}.npy", video, allow_pickle=False)
        scaler_json = f"{self.dump_dir}/scaler.json"
        if not os.path.exists(scaler_json):
            with open(scaler_json, "w") as jf:
                json.dump(extra, jf)

    def _log_frame(
        self,
        n: int,
        pct_str: str,
        action: str,
        result_len: int,
        elapsed_us: int,
        extra: str = "",
    ) -> None:
        self.stats_fh.write(
            f"{n},{pct_str},{action},{result_len},{elapsed_us},{extra}\n"
        )
        self.stats_fh.flush()

    def close(self) -> None:
        """Close the stats file handle if it is not /dev/null."""
        if self.stats_fh is not None and self.stats_fh.name != os.devnull:
            self.stats_fh.close()
        self.stats_fh = None  # type: ignore[assignment]

    def _upscale_rgba(self, video: np.ndarray) -> np.ndarray:
        """Convert *video* (uint32) to upscaled RGBA uint8 array."""
        rgba = to_rgba_u8(video)
        if self.kitty_scale > 1:
            rgba = np.repeat(
                np.repeat(rgba, self.kitty_scale, axis=0), self.kitty_scale, axis=1
            )
        return rgba

    def _encode_sixel_keyframe(
        self, video: np.ndarray, t0: float, n: int, pct_str: str, action: str,
    ) -> bytes:
        self._keyframes += 1
        self.sixel_baseline = video.copy()
        colors = to_rgb(video)
        result = encode_sixel(colors, max_colors=256, scale=self.scale)
        self._bytes_out += len(result)
        elapsed_us = int((time.perf_counter() - t0) * 1e6)
        self._log_frame(
            n, pct_str, action, len(result), elapsed_us,
            f"{self.refx},{self.refy},,,,,",
        )
        return f"\033[{self.refx};{self.refy}H\033[0m".encode() + result

    def encode_sixel(
        self,
        video: np.ndarray,
        last_frame: np.ndarray | None,
    ) -> bytes:
        """Encode ``video`` as a sixel escape sequence.

        Uses a baseline frame with overlay delta updates for bandwidth
        savings, falling back to a full keyframe when more than
        ``SIXEL_REBASELINE_THRESHOLD`` of pixels change.

        Returns empty bytes if the frame is unchanged from *last_frame*.
        """
        if (
            last_frame is not None
            and video.shape == last_frame.shape
            and np.array_equal(video, last_frame)
        ):
            self.sixel_frame_no += 1
            self._skipped += 1
            self._log_frame(self.sixel_frame_no, "0.0", "skip", 0, 0)
            return b""

        self.sixel_frame_no += 1
        n = self.sixel_frame_no
        t0 = time.perf_counter()

        self.dump_frame(
            video,
            n,
            cell_h=self.cell_h,
            cell_w=self.cell_w,
            scale=self.scale,
            refx=self.refx,
            refy=self.refy,
        )

        if self.sixel_baseline is None:
            return self._encode_sixel_keyframe(video, t0, n, "0.0", "first_keyframe")

        total_pixels = video.size
        diff = video != self.sixel_baseline
        changed = diff.sum()
        changed_pct = changed / total_pixels

        if changed_pct > SIXEL_REBASELINE_THRESHOLD:
            return self._encode_sixel_keyframe(
                video, t0, n, f"{changed_pct:.2f}", "rebaseline",
            )

        self._deltas += 1

        # Quantize only changed pixels for the overlay delta; unchanged
        # pixels are transparent (skip_index=255) and already on screen
        # from the prior frame via P2=1 mode.
        changed_pixels = video[diff].reshape(-1, 1)
        changed_colors = to_rgb(changed_pixels)
        max_colors = min(256, changed_colors.shape[0])
        indices_delta, palette = quantize_colors(changed_colors, max_colors)
        palette = np.asarray(palette)
        palette = blit_vis_channels(palette, self.blitter_vis)
        indices = np.full(video.shape, 255, dtype=np.uint8)
        indices[diff] = np.asarray(indices_delta).ravel()

        result = encode_sixel(
            to_rgb(video),
            max_colors=256,
            scale=self.scale,
            indices=indices,
            palette=palette,
            skip_index=255,
        )
        # Baseline updated every overlay: sixel P2=1 transparency requires
        # frame-to-frame diffs so unchanged pixels aren't double-rendered.
        self.sixel_baseline = video.copy()
        self._bytes_out += len(result)
        elapsed_us = int((time.perf_counter() - t0) * 1e6)

        self._log_frame(
            n, f"{changed_pct:.2f}", "overlay_delta", len(result), elapsed_us,
            f"{self.refx},{self.refy},,,,,",
        )

        return f"\033[{self.refx};{self.refy}H\033[0m".encode() + result  # type: ignore[no-any-return]

    def encode_sixel_full(
        self,
        video: np.ndarray,
    ) -> bytes:
        """Encode ``video`` as a full opaque sixel keyframe.

        No baseline tracking, no delta encoding, no P2=1 transparency.
        Every frame is a standalone keyframe.  Used for Contour which
        does not support sixel blitting.
        """
        self.sixel_frame_no += 1
        t0 = time.perf_counter()
        colors = to_rgb(video)
        result = encode_sixel(colors, max_colors=256, scale=self.scale)
        self._keyframes += 1
        self._bytes_out += len(result)
        elapsed_us = int((time.perf_counter() - t0) * 1e6)
        self._log_frame(
            self.sixel_frame_no, "0.0", "blitless_keyframe", len(result), elapsed_us,
            f"{self.refx},{self.refy},,,,,",
        )
        return f"\033[{self.refx};{self.refy}H\033[0m".encode() + result  # type: ignore[no-any-return]

    def encode_kitty_frame(
        self,
        video: np.ndarray,
        encode_fn: Callable[..., bytes],
    ) -> bytes:
        """Encode kitty frame with single-slot keyframe cache.

        Deltas send the bounding box of changed pixels positioned via
        cell-snapped cursor move, using p=1 placement replacement.
        Rebaselines when either pixel-change count or bounding-box area
        exceeds thresholds.  Keyframes are compared against the prior
        cached keyframe hash; a match replays via ``a=p``.
        """
        t0 = time.perf_counter()
        self.kitty_frame_no += 1
        n = self.kitty_frame_no
        total_pixels = video.size

        self.dump_frame(
            video,
            n,
            cell_h=self.cell_h,
            cell_w=self.cell_w,
            kitty_scale=self.kitty_scale,
            refx_kitty=self.refx_kitty,
            refy_kitty=self.refy_kitty,
        )

        if self.baseline is None:
            self._keyframes += 1
            self.baseline = video.copy()
            self._last_keyframe_hash = hash(video.tobytes())
            rgba = self._upscale_rgba(video)
            h, w = rgba.shape[:2]
            parts: list[bytes] = [
                f"\033[{self.refx_kitty};{self.refy_kitty}H".encode(),
                encode_fn(rgba.tobytes(), w, h, image_id=BASELINE_ID),
            ]
            self._delta_is_placed = False
            result = b"".join(parts)
            elapsed_us = int((time.perf_counter() - t0) * 1e6)
            self._log_frame(
                n, "0.0", "first_keyframe", len(result), elapsed_us,
                ",,,,,,,,,,,,,",
            )
            return result

        diff = video != self.baseline
        changed = diff.sum()
        changed_pct = changed / total_pixels

        rows = diff.any(axis=1)
        cols = diff.any(axis=0)
        y1 = int(rows.argmax())
        y2 = int(rows.shape[0] - rows[::-1].argmax())
        x1 = int(cols.argmax())
        x2 = int(cols.shape[0] - cols[::-1].argmax())
        rect_w = x2 - x1
        rect_h = y2 - y1

        self._frames_since_rebaseline += 1
        force = (
            self._force_rebaseline_every > 0
            and self._frames_since_rebaseline >= self._force_rebaseline_every
        )
        if (
            force
            or changed_pct > KITTY_REBASELINE_THRESHOLD
            or rect_w * rect_h > total_pixels * KITTY_REBASELINE_RECT
        ):
            self._keyframes += 1
            self._frames_since_rebaseline = 0
            self.baseline = video.copy()

            khash = hash(video.tobytes())
            if self._last_keyframe_hash == khash:
                self._cached_hits += 1
                self._delta_is_placed = False
                result = (
                    b"\033_Ga=d,d=a,q=1\033\\"
                    + f"\033[{self.refx_kitty};{self.refy_kitty}H".encode()
                    + f"\033_Ga=p,i={BASELINE_ID},q=1\033\\".encode()
                )
                elapsed_us = int((time.perf_counter() - t0) * 1e6)
                self._log_frame(
                    n, f"{changed_pct:.2f}", "cache_hit_rebaseline",
                    len(result), elapsed_us,
                    ",,,,,,,,,,,,,",
                )
                return result
            self._last_keyframe_hash = khash

            rgba = self._upscale_rgba(video)
            h, w = rgba.shape[:2]
            prefix = b""
            if self._delta_is_placed:
                prefix = f"\033_Ga=d,d=i,i={DELTA_ID}\033\\".encode()
            rebase_parts: list[bytes] = [
                prefix,
                f"\033[{self.refx_kitty};{self.refy_kitty}H".encode(),
                encode_fn(rgba.tobytes(), w, h, image_id=BASELINE_ID),
            ]
            self._delta_is_placed = False
            result = b"".join(rebase_parts)
            elapsed_us = int((time.perf_counter() - t0) * 1e6)
            self._log_frame(
                n, f"{changed_pct:.2f}", "rebaseline",
                len(result), elapsed_us,
                ",,,,,,,,,,,,,",
            )
            return result

        self._deltas += 1

        rect_video = np.ascontiguousarray(video[y1:y2, x1:x2])
        rect_rgba = to_rgba_u8(rect_video)
        if self.kitty_scale > 1:
            rect_rgba = np.repeat(
                np.repeat(rect_rgba, self.kitty_scale, axis=0),
                self.kitty_scale,
                axis=1,
            )
        scaled_w = rect_w * self.kitty_scale
        scaled_h = rect_h * self.kitty_scale

        px = x1 * self.kitty_scale
        py = y1 * self.kitty_scale
        row = self.refx_kitty + py // self.cell_h
        col = self.refy_kitty + px // self.cell_w

        px2 = px + scaled_w
        py2 = py + scaled_h
        col2 = self.refy_kitty + (px2 - 1) // self.cell_w + 1
        row2 = self.refx_kitty + (py2 - 1) // self.cell_h + 1
        padded_w = (col2 - col) * self.cell_w
        padded_h = (row2 - row) * self.cell_h

        padded = np.zeros((padded_h, padded_w, 4), dtype=np.uint8)
        off_y = py % self.cell_h
        off_x = px % self.cell_w
        padded[off_y : off_y + scaled_h, off_x : off_x + scaled_w] = rect_rgba

        if self.blitter_vis:
            mask = padded[:, :, 3] != 0
            padded[mask, :3] = blit_vis_channels(padded[mask, :3], self.blitter_vis)

        result_parts: list[bytes] = [
            f"\033[{row};{col}H".encode(),
            encode_fn(
                padded.tobytes(),
                padded_w,
                padded_h,
                image_id=DELTA_ID,
                placement_id=1,
            ),
        ]
        self._delta_is_placed = True
        result = b"".join(result_parts)
        elapsed_us = int((time.perf_counter() - t0) * 1e6)
        self._log_frame(
            n, f"{changed_pct:.2f}", "dirty_rect",
            len(result), elapsed_us,
            f"{row},{col},{self.cell_h},{self.cell_w},{padded_w},{padded_h},"
            f"{x1},{y1},{rect_w},{rect_h},"
            f"{self.refx_kitty},{self.refy_kitty},{self.kitty_scale}",
        )
        return result

    def encode_kitty(
        self,
        video: np.ndarray,
        last_frame: np.ndarray | None,
    ) -> bytes:
        """Encode ``video`` as a kitty RGBA escape sequence.

        Uses a baseline image with dirty-rect delta updates via p=1
        placement replacement.  Returns empty bytes when unchanged.
        """
        if (
            last_frame is not None
            and video.shape == last_frame.shape
            and np.array_equal(video, last_frame)
        ):
            self.kitty_frame_no += 1
            self._skipped += 1
            self._log_frame(self.kitty_frame_no, "0.0", "skip", 0, 0)
            return b""
        result = self.encode_kitty_frame(video, encode_kitty_rgba)
        self._bytes_out += len(result)
        return result


class GraphicsRenderer:
    """Owns runtime graphics state: scaler lifecycle, autoscale, frame encoding.

    Instantiated once per ``run()`` session.  ``on_state_change``, ``render``,
    ``feed_bandwidth``, and ``feed_fps`` are called from the main loop.
    """

    def __init__(
        self,
        term: Terminal,
        console: Console,
        autoscale_config: AutoScaleConfig | None,
        terminal_name: str,
        protocol: GraphicsProtocol,
    ) -> None:
        self._term = term
        self._console = console
        self._autoscale_config = autoscale_config
        self._terminal_name = terminal_name

        self.scaler: GraphicsScaler | None = None
        self.encoder: FrameEncoder | None = None
        self.autoscale: AutoScale | None = (
            AutoScale(SCALE_MAX, autoscale_config.seconds)
            if autoscale_config is not None
            and autoscale_config.enabled
            and protocol is not GraphicsProtocol.TEXT
            else None
        )
        self._blitter_vis = 0
        self._force_clear = False
        self._force_keyframe = False
        self._ghostty_kitty_gfx_clear = False

    def _make_encoder(self) -> None:
        assert self.scaler is not None
        self.encoder = FrameEncoder(
            self.scaler.scale,
            self.scaler.kitty_scale,
            self.scaler.refx,
            self.scaler.refy,
            self.scaler.refx_kitty,
            self.scaler.refy_kitty,
            self.scaler.cell_h,
            self.scaler.cell_w,
        )
        self.encoder.blitter_vis = self._blitter_vis

    @property
    def blitter_vis(self) -> int:
        return self._blitter_vis

    @blitter_vis.setter
    def blitter_vis(self, vis: int) -> None:
        self._blitter_vis = vis
        if self.encoder is not None:
            self.encoder.blitter_vis = vis

    @property
    def has_autoscale(self) -> bool:
        return self.autoscale is not None

    @property
    def scale(self) -> int | None:
        if self.scaler is None:
            return None
        return self.scaler.scale

    def request_keyframe(self) -> None:
        self._force_keyframe = True

    def on_focus_change(self, protocol: GraphicsProtocol) -> None:
        """Force a keyframe when terminal regains focus.

        mlterm and xterm drop sixel content on focus loss; a keyframe
        redraws the full image without relying on stale baseline data.
        """
        if (
            protocol is GraphicsProtocol.SIXEL
            and self._terminal_name.startswith(SIXEL_FORCE_REFRESH_ON_FOCUS)
        ):
            self.request_keyframe()

    def on_state_change(
        self,
        old_protocol: GraphicsProtocol,
        new_protocol: GraphicsProtocol,
        old_color: object,
        new_color: object,
        resized: bool,
    ) -> bytes:
        """Handle protocol/color/resize change.

        Tears down the current scaler, manages the autoscale lifecycle,
        and returns the clear/delete escape sequence to emit before the
        next frame.
        """
        # Autoscale lifecycle
        if new_protocol is GraphicsProtocol.TEXT:
            self.autoscale = None
        elif (
            self.autoscale is None
            and self._autoscale_config is not None
            and self._autoscale_config.enabled
        ):
            self.autoscale = AutoScale(
                SCALE_MAX, self._autoscale_config.seconds
            )
        elif self.autoscale is not None:
            self.autoscale.reset()

        # Scaler teardown
        if self.encoder is not None:
            self.encoder.close()
        self.scaler = None
        self.encoder = None

        # Clear / delete sequence
        clear = b""
        if (
            new_protocol != old_protocol
            or new_color != old_color
            or resized
        ):
            clear = TEXT_HOME_CLEAR
        if GraphicsProtocol.KITTY in (old_protocol, new_protocol):
            clear += KITTY_GFX_CLEAR
            if self._terminal_name.startswith(FORCE_KITTY_INDIVIDUAL_DELETES):
                clear += KITTY_GFX_GHOSTTY_CLEAR
        return clear

    def render(
        self,
        video: np.ndarray,
        last_frame: np.ndarray | None,
        protocol: GraphicsProtocol,
        height: int,
        width: int,
    ) -> bytes:
        prefix, suffix = b"", b""

        if self._ghostty_kitty_gfx_clear:
            clear_cmd = KITTY_GFX_GHOSTTY_CLEAR
            prefix = b"\033[?2026h" + clear_cmd
            suffix = b"\033[?2026l"
            self._ghostty_kitty_gfx_clear = False

        if self._force_keyframe:
            if self.encoder is not None:
                self.encoder.close()
            self.scaler = None
            self.encoder = None
            self._force_keyframe = False

        if self.scaler is None:
            self.scaler = GraphicsScaler.recompute(
                self._term,
                self._console,
                height,
                width,
                self.autoscale,
                terminal_name=self._terminal_name,
            )
            self._make_encoder()

        if self._force_clear:
            if protocol in (GraphicsProtocol.SIXEL, GraphicsProtocol.BLITLESS_SIXEL):
                prefix = b"\033[H\033[2J" + prefix
            elif protocol is GraphicsProtocol.KITTY:
                prefix = KITTY_GFX_CLEAR + prefix
        self._force_clear = False

        if protocol is GraphicsProtocol.SIXEL:
            result = self.encoder.encode_sixel(video, last_frame)
        elif protocol is GraphicsProtocol.BLITLESS_SIXEL:
            result = self.encoder.encode_sixel_full(video)
        else:
            result = self.encoder.encode_kitty(video, last_frame)
            if self._terminal_name.startswith(FORCE_KITTY_BLITLESS):
                self.encoder.baseline = None

        if not result:
            return b""
        return prefix + result + suffix

    def feed_bandwidth(
        self,
        data_rate_kb_s: float,
        height: int,
        width: int,
    ) -> None:
        """Feed autoscale with output bandwidth; reduce scale cap if too high."""
        if self.autoscale is None or self._autoscale_config is None:
            return
        if self.autoscale.feed_bandwidth(
            data_rate_kb_s, self._autoscale_config.bandwidth_mbits
        ):
            if self.encoder is not None:
                self.encoder.close()
            self.scaler = GraphicsScaler.recompute(
                self._term,
                self._console,
                height,
                width,
                self.autoscale,
                terminal_name=self._terminal_name,
            )
            self._make_encoder()
            self._force_clear = True

    def feed_fps(
        self,
        video_fps: float,
        protocol: GraphicsProtocol,
        height: int,
        width: int,
    ) -> None:
        """Feed autoscale with video FPS; reduce scale cap if too slow."""
        if self.autoscale is None or self._autoscale_config is None:
            return
        if self.autoscale.feed_fps(video_fps, self._autoscale_config.fps):
            if (
                self._terminal_name.startswith(FORCE_KITTY_INDIVIDUAL_DELETES)
                and protocol is GraphicsProtocol.KITTY
            ):
                # WIP: Verifying that, ghostty has trouble "clearing" graphics correctly,
                # it doesn't allow us to "clear all", so, we clear by individual ID
                self._ghostty_kitty_gfx_clear = True
            if self.encoder is not None:
                self.encoder.close()
            self.scaler = GraphicsScaler.recompute(
                self._term,
                self._console,
                height,
                width,
                self.autoscale,
                terminal_name=self._terminal_name,
            )
            self._make_encoder()
            self._force_clear = True

    def close(self) -> None:
        if self.encoder is not None:
            self.encoder.close()
