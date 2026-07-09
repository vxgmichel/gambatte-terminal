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
)

if TYPE_CHECKING:
    from blessed import Terminal
    from .console import Console

BASELINE_ID = 1
DELTA_ID = 2
SIXEL_REBASELINE_THRESHOLD = float(os.environ.get("GAMBATERM_SIXEL_REBASELINE", "0.35"))
KITTY_REBASELINE_THRESHOLD = float(os.environ.get("GAMBATERM_KITTY_REBASELINE", "0.35"))
SIXEL_FORCE_REFRESH_ON_FOCUS = ("mlterm", "xterm")


def blit_vis_channels(rgb: np.ndarray, mode: int) -> np.ndarray:
    """Apply channel permutation for blit visualization."""
    if mode == 1:
        return np.ascontiguousarray(rgb[..., [2, 1, 0]])
    if mode == 2:
        return np.ascontiguousarray(rgb[..., [1, 0, 2]])
    return rgb


class GraphicsScaler:
    """Pixel-dimension-aware scaler for sixel and kitty frame output.

    Query happens once via ``recompute`` (call on resize / first frame).
    Subsequent ``blit_sixel`` / ``blit_kitty`` calls use the cached scale
    and position.

    Kitty frames use a baseline image (i=1) with transparent delta updates
    (i=2) when only a fraction of the screen changes between frames.
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
        "had_delta",
        "kitty_frame_no",
        "dump_dir",
        "stats_fh",
        "blitter_vis",
        "_keyframes",
        "_deltas",
        "_skipped",
        "_bytes_out",
        "_t0",
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
        self.had_delta = False
        self.kitty_frame_no = 0
        self.sixel_frame_no = 0
        self.blitter_vis = 0
        self._keyframes = 0
        self._deltas = 0
        self._skipped = 0
        self._bytes_out = 0
        self._t0 = time.monotonic()
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

    def close(self) -> None:
        """Close the stats file handle if it is not /dev/null."""
        if self.stats_fh is not None and self.stats_fh.name != os.devnull:
            self.stats_fh.close()
        self.stats_fh = None  # type: ignore[assignment]

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

        # Reduce sixel scale if the image would fill the screen with less
        # than one cell of vertical margin, to avoid edge-to-edge crowding.
        sixel_scale = graphics_scale
        if terminal_name.startswith("xterm"):
            sixel_scale = min(sixel_scale, 6)  # xterm sixel capped at 1000x1000px
        if pixel_h - console.HEIGHT * sixel_scale < cell_h and sixel_scale > 1:
            sixel_scale -= 1

        # After sixel rendering the text cursor moves to the line below the
        # image.  If that line doesn't exist the terminal scrolls, creating a
        # shifting offset on every frame.  Reduce scale until the image plus
        # the trailing cursor line fit without scrolling.
        while sixel_scale > 1:
            img_h = console.HEIGHT * sixel_scale
            rows = (img_h + cell_h - 1) // cell_h
            refx = max(2, (pixel_h - img_h) // 2 // cell_h + 1)
            if refx + rows <= height:
                break
            sixel_scale -= 1

        kitty_scale = graphics_scale

        # Ensure kitty image fits with at least one empty row above for
        # the status bar.  Reduce scale until there is room.
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

    def _skip_if_identical(
        self, video: np.ndarray, last_frame: np.ndarray | None, frame_no_attr: str
    ) -> bool:
        """Return True (and log skip) if *video* is identical to *last_frame*."""
        if last_frame is None or video.shape != last_frame.shape:
            return False
        if not np.array_equal(video, last_frame):
            return False
        self._skipped += 1
        n = getattr(self, frame_no_attr) + 1
        setattr(self, frame_no_attr, n)
        self.stats_fh.write(f"{n},0.0,skip,0,0,,,,,,,,,,,,,\n")
        self.stats_fh.flush()
        return True

    def _upscale_rgba(self, video: np.ndarray) -> np.ndarray:
        """Convert *video* (uint32) to upscaled RGBA uint8 array."""
        rgba = to_rgba_u8(video)
        if self.kitty_scale > 1:
            rgba = np.repeat(
                np.repeat(rgba, self.kitty_scale, axis=0), self.kitty_scale, axis=1
            )
        return rgba

    def blit_sixel(
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
        if self._skip_if_identical(video, last_frame, "sixel_frame_no"):
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
            self._keyframes += 1
            self.sixel_baseline = video.copy()
            colors = to_rgb(video)
            result = encode_sixel(colors, max_colors=256, scale=self.scale)
            self._bytes_out += len(result)
            elapsed_us = int((time.perf_counter() - t0) * 1e6)
            self.stats_fh.write(
                f"{n},0.0,first_keyframe,{len(result)},{elapsed_us},"
                f"{self.refx},{self.refy},,,,,\n"
            )
            self.stats_fh.flush()
            return f"\033[{self.refx};{self.refy}H\033[0m".encode() + result  # type: ignore[no-any-return]

        total_pixels = video.size
        diff = video != self.sixel_baseline
        changed = diff.sum()
        changed_pct = changed / total_pixels

        if changed_pct > SIXEL_REBASELINE_THRESHOLD:
            self._keyframes += 1
            self.sixel_baseline = video.copy()
            colors = to_rgb(video)
            result = encode_sixel(colors, max_colors=256, scale=self.scale)
            self._bytes_out += len(result)
            elapsed_us = int((time.perf_counter() - t0) * 1e6)
            self.stats_fh.write(
                f"{n},{changed_pct:.2f},rebaseline,{len(result)},{elapsed_us},"
                f"{self.refx},{self.refy},,,,,\n"
            )
            self.stats_fh.flush()
            return f"\033[{self.refx};{self.refy}H\033[0m".encode() + result  # type: ignore[no-any-return]

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

        self.stats_fh.write(
            f"{n},{changed_pct:.2f},overlay_delta,{len(result)},{elapsed_us},"
            f"{self.refx},{self.refy},,,,,\n"
        )
        self.stats_fh.flush()

        return f"\033[{self.refx};{self.refy}H\033[0m".encode() + result  # type: ignore[no-any-return]

    def blit_sixel_blitless(
        self,
        video: np.ndarray,
        width: int,
        height: int,
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
        self.stats_fh.write(
            f"{self.sixel_frame_no},0.0,blitless_keyframe,{len(result)},{elapsed_us},"
            f"{self.refx},{self.refy},,,,,\n"
        )
        self.stats_fh.flush()
        return f"\033[{self.refx};{self.refy}H\033[0m".encode() + result  # type: ignore[no-any-return]

    def encode_kitty_frame(
        self,
        video: np.ndarray,
        encode_fn: Callable[..., bytes],
    ) -> bytes:
        """Encode kitty frame: keyframe on first call, dirty-rect delta otherwise.

        Deltas send the bounding box of changed pixels positioned via
        cell-snapped cursor move, using p=1 placement replacement.
        Rebaselines when either pixel-change count or bounding-box area
        exceeds ``KITTY_REBASELINE_THRESHOLD``, catching both genuine
        scene changes and scattered-but-small changes efficiently.
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
            rgba = self._upscale_rgba(video)
            h, w = rgba.shape[:2]
            parts: list[bytes] = [
                f"\033[{self.refx_kitty};{self.refy_kitty}H".encode(),
                encode_fn(rgba.tobytes(), w, h, image_id=BASELINE_ID),
            ]
            result = b"".join(parts)
            elapsed_us = int((time.perf_counter() - t0) * 1e6)
            self.stats_fh.write(
                f"{n},0.0,first_keyframe,{len(result)},{elapsed_us},,,,,,,,,,,,,,\n"
            )
            self.stats_fh.flush()
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

        # If the dirty rect covers most of the screen the delta payload
        # is as large as a keyframe (cell-snapped padding amplifies
        # scattered pixels).  Do a rebaseline instead to reset the
        # accumulation baseline.
        if (
            changed_pct > KITTY_REBASELINE_THRESHOLD
            or rect_w * rect_h > total_pixels * 0.80
        ):
            self._keyframes += 1
            self.baseline = video.copy()
            rgba = self._upscale_rgba(video)
            h, w = rgba.shape[:2]
            rebase_parts: list[bytes] = [
                f"\033[{self.refx_kitty};{self.refy_kitty}H".encode(),
            ]
            if self.had_delta:
                rebase_parts.append(f"\033_Ga=d,d=i,i={DELTA_ID}\033\\".encode())
            rebase_parts.append(encode_fn(rgba.tobytes(), w, h, image_id=BASELINE_ID))
            self.had_delta = False
            result = b"".join(rebase_parts)
            elapsed_us = int((time.perf_counter() - t0) * 1e6)
            self.stats_fh.write(
                f"{n},{changed_pct:.2f},rebaseline,{len(result)},{elapsed_us},,,,,,,,,,,,,,\n"
            )
            self.stats_fh.flush()
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

        result_parts = [
            f"\033[{row};{col}H".encode(),
            encode_fn(
                padded.tobytes(),
                padded_w,
                padded_h,
                image_id=DELTA_ID,
                placement_id=1,
            ),
        ]
        self.had_delta = True
        # Baseline NOT updated after delta: kitty p=1 rect replacement
        # diffs against the last keyframe, not the previous frame.  Each
        # p=1 replacement removes the prior delta at the target rect, so
        # keyframe-relative diffs avoid compounding residual artifacts.
        result = b"".join(result_parts)
        elapsed_us = int((time.perf_counter() - t0) * 1e6)
        self.stats_fh.write(
            f"{n},{changed_pct:.2f},dirty_rect,{len(result)},{elapsed_us},"
            f"{row},{col},{self.cell_h},{self.cell_w},{padded_w},{padded_h},"
            f"{x1},{y1},{rect_w},{rect_h},"
            f"{self.refx_kitty},{self.refy_kitty},{self.kitty_scale}\n"
        )
        self.stats_fh.flush()
        return result

    def blit_kitty(
        self,
        video: np.ndarray,
        last_frame: np.ndarray | None,
    ) -> bytes:
        """Encode ``video`` as a kitty RGBA escape sequence.

        Uses a baseline image (i=1) with dirty-rect delta updates (i=2)
        via p=1 placement replacement.  Returns empty bytes when unchanged.
        """
        if self._skip_if_identical(video, last_frame, "kitty_frame_no"):
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

    @property
    def blitter_vis(self) -> int:
        return self._blitter_vis

    @blitter_vis.setter
    def blitter_vis(self, vis: int) -> None:
        self._blitter_vis = vis
        if self.scaler is not None:
            self.scaler.blitter_vis = vis

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
        if self.scaler is not None:
            self.scaler.close()
        self.scaler = None

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
            if self._terminal_name == "ghostty":
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
            prefix = b"\033[?2026h" + KITTY_GFX_GHOSTTY_CLEAR
            suffix = b"\033[?2026l"
            self._ghostty_kitty_gfx_clear = False

        if self._force_keyframe:
            if self.scaler is not None:
                self.scaler.close()
            self.scaler = None
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
            self.scaler.blitter_vis = self._blitter_vis

        if self._force_clear and protocol in (
            GraphicsProtocol.SIXEL,
            GraphicsProtocol.BLITLESS_SIXEL,
        ):
            prefix = b"\033[H\033[2J" + prefix
        self._force_clear = False

        if protocol is GraphicsProtocol.SIXEL:
            result = self.scaler.blit_sixel(video, last_frame)
        elif protocol is GraphicsProtocol.BLITLESS_SIXEL:
            result = self.scaler.blit_sixel_blitless(video, width, height)
        else:
            result = self.scaler.blit_kitty(video, last_frame)
            if self._terminal_name.startswith(FORCE_KITTY_BLITLESS):
                self.scaler.baseline = None

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
            if self.scaler is not None:
                self.scaler.close()
            self.scaler = GraphicsScaler.recompute(
                self._term,
                self._console,
                height,
                width,
                self.autoscale,
            )
            self.scaler.blitter_vis = self._blitter_vis
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
                self._terminal_name == "ghostty"
                and protocol is GraphicsProtocol.KITTY
            ):
                # WIP: Verifying that, ghostty has trouble "clearing" graphics correctly,
                # it doesn't allow us to "clear all", so, we clear by individual ID
                self._ghostty_kitty_gfx_clear = True
            if self.scaler is not None:
                self.scaler.close()
            self.scaler = GraphicsScaler.recompute(
                self._term,
                self._console,
                height,
                width,
                self.autoscale,
            )
            self.scaler.blitter_vis = self._blitter_vis
            if protocol is not GraphicsProtocol.KITTY:
                self._force_clear = True

    def close(self) -> None:
        if self.scaler is not None:
            self.scaler.close()
