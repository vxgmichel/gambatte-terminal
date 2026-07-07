"""Pixel scaler for sixel and kitty graphics protocols."""

from __future__ import annotations

import atexit
import os
import time
from typing import TYPE_CHECKING, NamedTuple

import numpy as np

from .graphicsblit import (
    to_rgb,
    to_rgba_u8,
    encode_sixel,
    encode_kitty_rgba,
    quantize_colors,
)

if TYPE_CHECKING:
    from blessed import Terminal
    from .console import Console
    from .colors import ColorMode

BASELINE_ID = 1
DELTA_ID = 2
SIXEL_REBASELINE_THRESHOLD = 0.35
_SCALE_CEILING = int(os.environ.get("GAMBATERM_SCALE_MAX", "32"))
_FALLBACK_SCALE_MAX = 8


class AutoScaleConfig(NamedTuple):
    """Parsed ``--graphics-autoscale`` configuration."""

    enabled: bool
    seconds: int
    fps: float
    bandwidth_mbits: float


def parse_autoscale(value: str) -> AutoScaleConfig:
    value = value.strip().lower()
    if value in ("off", "no", "disabled", ""):
        return AutoScaleConfig(enabled=False, seconds=0, fps=40.0, bandwidth_mbits=0.0)

    seconds = -1
    fps = 40.0
    bandwidth_mbits = 0.0
    saw_always = False
    saw_seconds = False
    saw_disable = False

    for token in value.split(","):
        token = token.strip()
        if token in ("off", "no", "disabled"):
            saw_disable = True
        elif token == "always":
            saw_always = True
        elif token.endswith("fps"):
            fps = float(token[:-3])
        elif token.endswith("kb"):
            bandwidth_mbits = float(token[:-2]) / 125.0
        elif token.endswith("mb"):
            bandwidth_mbits = float(token[:-2])
        elif token.endswith("s"):
            seconds = int(token[:-1])
            saw_seconds = True
        else:
            raise ValueError(f"Unknown autoscale token: {token!r}")

    if saw_disable:
        raise ValueError(
            "'off'/'no'/'disabled' is mutually exclusive with other tokens"
        )
    if saw_always and saw_seconds:
        raise ValueError("'always' is mutually exclusive with 'Ns'")

    return AutoScaleConfig(
        enabled=True, seconds=seconds, fps=fps, bandwidth_mbits=bandwidth_mbits
    )


class AutoScale:
    """Dynamic scale cap that decreases when rendering can't keep up.

    Starts at *ceiling* and only ever decreases.  The floor (50% of
    natural screen scale) is enforced by :meth:`GraphicsScaler.recompute`,
    not by this class.

    Two independent reduction triggers:

    * :meth:`feed_fps` — reduce when ``video_fps`` drops below a threshold.
    * :meth:`feed_bandwidth` — reduce when output data rate exceeds a cap.

    Reductions are only allowed within *window_s* seconds of construction
    or the most recent :meth:`reset` call.
    """

    def __init__(self, ceiling: int, window_s: int) -> None:
        self._ceiling = ceiling
        self._window_s = window_s
        self.max_scale = ceiling
        self._deadline = self._compute_deadline()

    def _compute_deadline(self) -> float:
        if self._window_s == 0:
            return 0.0
        if self._window_s == -1:
            return float("inf")
        return time.monotonic() + self._window_s

    def feed_fps(self, video_fps: float, threshold_fps: float) -> bool:
        """Return True if *max_scale* was reduced."""
        if threshold_fps <= 0:
            return False
        if time.monotonic() > self._deadline:
            return False
        if video_fps < threshold_fps and self.max_scale > 1:
            self.max_scale = max(1, self.max_scale - 2)
            return True
        return False

    def reset(self) -> None:
        """Restore *max_scale* to ceiling, reset deadline."""
        self.max_scale = self._ceiling
        self._deadline = self._compute_deadline()

    def feed_bandwidth(self, data_rate_kb_s: float, threshold_mbit_s: float) -> bool:
        """Return True if *max_scale* was reduced due to bandwidth."""
        if threshold_mbit_s <= 0:
            return False
        if time.monotonic() > self._deadline:
            return False
        if data_rate_kb_s > threshold_mbit_s * 125.0 and self.max_scale > 1:
            self.max_scale = max(1, self.max_scale - 2)
            return True
        return False


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

    __slots__ = (
        "scale",
        "kitty_scale",
        "refx",
        "refy",
        "refx_kitty",
        "refy_kitty",
        "_cell_h",
        "_cell_w",
        "_baseline",
        "_sixel_baseline",
        "_sixel_frame_no",
        "_had_delta",
        "_profile",
        "_frame_no",
        "_stats_fh",
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
        self._cell_h = cell_h
        self._cell_w = cell_w
        self._baseline: np.ndarray | None = None
        self._sixel_baseline: np.ndarray | None = None
        self._sixel_frame_no = 0
        self._had_delta = False
        self._profile = _Profile()
        self._frame_no = 0
        profile_dir = os.environ.get("GAMBATERM_PROFILE_DIR")
        if profile_dir is not None:
            os.makedirs(profile_dir, exist_ok=True)
            csv_path = f"{profile_dir}/gambatterm-frame-stats.csv"
            is_new = not os.path.exists(csv_path) or os.path.getsize(csv_path) == 0
            self._stats_fh = open(csv_path, "a")
            if is_new:
                self._stats_fh.write(
                    "frame_no,changed_pct,action,bytes,time_us,"
                    "row,col,cell_h,cell_w,padded_w,padded_h,"
                    "x1,y1,rect_w,rect_h,"
                    "refx_kitty,refy_kitty,scale\n"
                )
            atexit.register(
                self._profile.dump, f"{profile_dir}/gambaterm-profile.txt"
            )
        else:
            self._stats_fh = open(os.devnull, "w")

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
        auto_scale: AutoScale | None = None,
        terminal_name: str = "",
    ) -> GraphicsScaler:
        """Query terminal pixel geometry and return a new GraphicsScaler."""
        pixel_h, pixel_w = term.get_sixel_height_and_width(force=True)
        if pixel_h <= 0 or pixel_w <= 0:
            return cls(1, 1, 1, 1, 1, 1, 1, 1)
        natural_scale = max(1, min(pixel_w // console.WIDTH, pixel_h // console.HEIGHT))
        if auto_scale is not None:
            if auto_scale.max_scale > natural_scale:
                auto_scale.max_scale = natural_scale
            effective_cap = auto_scale.max_scale
        else:
            effective_cap = min(natural_scale, _FALLBACK_SCALE_MAX)
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

        def _pos(img_h, img_w):
            rx = max(2, (pixel_h - img_h) // 2 // cell_h + 1)
            ry = max(1, (pixel_w - img_w) // 2 // cell_w + 1)
            return rx, ry

        refx, refy = _pos(console.HEIGHT * sixel_scale, console.WIDTH * sixel_scale)
        refx_kitty, refy_kitty = _pos(
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

    def blit_sixel(
        self,
        video: np.ndarray,
        last_frame: np.ndarray | None,
        width: int,
        height: int,
    ) -> bytes:
        """Encode ``video`` as a sixel escape sequence.

        Uses a baseline frame with dirty-rect delta updates for bandwidth
        savings, falling back to a full keyframe when more than
        ``SIXEL_REBASELINE_THRESHOLD`` of pixels change.

        Returns empty bytes if the frame is unchanged from *last_frame*.
        """
        if last_frame is not None and video.shape == last_frame.shape:
            if np.array_equal(video, last_frame):
                self._profile.skipped += 1
                self._sixel_frame_no += 1
                return b""

        self._sixel_frame_no += 1
        n = self._sixel_frame_no
        t0 = time.perf_counter()

        dump_dir = os.environ.get("GAMBATERM_DUMP_FRAMES")
        if dump_dir:
            os.makedirs(dump_dir, exist_ok=True)
            np.save(f"{dump_dir}/{n:05d}.npy", video, allow_pickle=False)
            scaler_json = f"{dump_dir}/scaler.json"
            if not os.path.exists(scaler_json):
                import json

                with open(scaler_json, "w") as jf:
                    json.dump(
                        {
                            "cell_h": self._cell_h,
                            "cell_w": self._cell_w,
                            "scale": self.scale,
                            "refx": self.refx,
                            "refy": self.refy,
                            "kitty_scale": self.kitty_scale,
                            "refx_kitty": self.refx_kitty,
                            "refy_kitty": self.refy_kitty,
                        },
                        jf,
                    )

        if self._sixel_baseline is None:
            self._profile.keyframes += 1
            self._sixel_baseline = video.copy()
            colors = to_rgb(video)
            result = encode_sixel(colors, max_colors=256, scale=self.scale)
            self._profile.bytes_out += len(result)
            elapsed_us = int((time.perf_counter() - t0) * 1e6)
            self._stats_fh.write(
                f"{n},0.0,first_keyframe,{len(result)},{elapsed_us},"
                f"{self.refx},{self.refy},,,,,\n"
            )
            self._stats_fh.flush()
            return f"\033[{self.refx};{self.refy}H\033[0m".encode() + result

        total_pixels = video.size
        diff = video != self._sixel_baseline
        changed = diff.sum()
        changed_pct = changed / total_pixels

        if changed_pct > SIXEL_REBASELINE_THRESHOLD:
            self._profile.keyframes += 1
            self._sixel_baseline = video.copy()
            colors = to_rgb(video)
            result = encode_sixel(colors, max_colors=256, scale=self.scale)
            self._profile.bytes_out += len(result)
            elapsed_us = int((time.perf_counter() - t0) * 1e6)
            self._stats_fh.write(
                f"{n},{changed_pct:.2f},rebaseline,{len(result)},{elapsed_us},"
                f"{self.refx},{self.refy},,,,,\n"
            )
            self._stats_fh.flush()
            return f"\033[{self.refx};{self.refy}H\033[0m".encode() + result

        self._profile.deltas += 1

        colors = to_rgb(video)
        indices, palette = quantize_colors(colors, 256)
        indices = np.asarray(indices)
        palette = np.asarray(palette)
        indices[~diff] = 255

        result = encode_sixel(
            colors,
            max_colors=256,
            scale=self.scale,
            indices=indices,
            palette=palette,
            skip_index=255,
        )
        self._sixel_baseline = video.copy()
        self._profile.bytes_out += len(result)
        elapsed_us = int((time.perf_counter() - t0) * 1e6)

        self._stats_fh.write(
            f"{n},{changed_pct:.2f},overlay_delta,{len(result)},{elapsed_us},"
            f"{self.refx},{self.refy},,,,,\n"
        )
        self._stats_fh.flush()

        return f"\033[{self.refx};{self.refy}H\033[0m".encode() + result

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
        self._sixel_frame_no += 1
        t0 = time.perf_counter()
        colors = to_rgb(video)
        result = encode_sixel(colors, max_colors=256, scale=self.scale)
        self._profile.keyframes += 1
        self._profile.bytes_out += len(result)
        elapsed_us = int((time.perf_counter() - t0) * 1e6)
        self._stats_fh.write(
            f"{self._sixel_frame_no},0.0,blitless_keyframe,{len(result)},{elapsed_us},"
            f"{self.refx},{self.refy},,,,,\n"
        )
        self._stats_fh.flush()
        return f"\033[{self.refx};{self.refy}H\033[0m".encode() + result

    def _encode_kitty(self, video, encode_fn):
        """Encode kitty frame: keyframe on first call, dirty-rect delta otherwise.

        Deltas send the bounding box of changed pixels positioned via
        cell-snapped cursor move, using p=1 placement replacement.
        Rebaselines when either pixel-change count exceeds 35% OR the
        bounding box exceeds 35% of the frame — catching both genuine
        scene changes and scattered-but-small changes efficiently.
        """
        t0 = time.perf_counter()
        self._frame_no += 1
        n = self._frame_no
        total_pixels = video.size

        dump_dir = os.environ.get("GAMBATERM_DUMP_FRAMES")
        if dump_dir:
            os.makedirs(dump_dir, exist_ok=True)
            np.save(f"{dump_dir}/{n:05d}.npy", video, allow_pickle=False)
            scaler_json = f"{dump_dir}/scaler.json"
            if not os.path.exists(scaler_json):
                import json

                with open(scaler_json, "w") as jf:
                    json.dump(
                        {
                            "cell_h": self._cell_h,
                            "cell_w": self._cell_w,
                            "kitty_scale": self.kitty_scale,
                            "refx_kitty": self.refx_kitty,
                            "refy_kitty": self.refy_kitty,
                        },
                        jf,
                    )
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
            rx = self.refx_kitty
            ry = self.refy_kitty
            result = [
                f"\033[{rx};{ry}H".encode(),
                encode_fn(rgba.tobytes(), w, h, image_id=BASELINE_ID),
            ]
            result = b"".join(result)
            elapsed_us = int((time.perf_counter() - t0) * 1e6)
            self._stats_fh.write(
                f"{n},0.0,first_keyframe,{len(result)},{elapsed_us},,,,,,,,,,,,,,\n"
            )
            self._stats_fh.flush()
            return result

        diff = video != self._baseline
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
        rect_area = rect_w * rect_h

        if changed_pct > SIXEL_REBASELINE_THRESHOLD or rect_area > total_pixels * 0.35:
            self._profile.keyframes += 1
            self._baseline = video.copy()
            rgba = to_rgba_u8(video)
            if self.kitty_scale > 1:
                rgba = np.repeat(
                    np.repeat(rgba, self.kitty_scale, axis=0), self.kitty_scale, axis=1
                )
            h, w = rgba.shape[:2]
            result = [
                f"\033[{self.refx_kitty};{self.refy_kitty}H".encode(),
            ]
            if self._had_delta:
                result.append(f"\033_Ga=d,d=i,i={DELTA_ID}\033\\".encode())
            result.append(encode_fn(rgba.tobytes(), w, h, image_id=BASELINE_ID))
            self._had_delta = False
            result = b"".join(result)
            elapsed_us = int((time.perf_counter() - t0) * 1e6)
            self._stats_fh.write(
                f"{n},{changed_pct:.2f},rebaseline,{len(result)},{elapsed_us},,,,,,,,,,,,,,\n"
            )
            self._stats_fh.flush()
            return result

        self._profile.deltas += 1

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
        row = self.refx_kitty + py // self._cell_h
        col = self.refy_kitty + px // self._cell_w

        px2 = px + scaled_w
        py2 = py + scaled_h
        col2 = self.refy_kitty + (px2 - 1) // self._cell_w + 1
        row2 = self.refx_kitty + (py2 - 1) // self._cell_h + 1
        padded_w = (col2 - col) * self._cell_w
        padded_h = (row2 - row) * self._cell_h

        padded = np.zeros((padded_h, padded_w, 4), dtype=np.uint8)
        off_y = py % self._cell_h
        off_x = px % self._cell_w
        padded[off_y : off_y + scaled_h, off_x : off_x + scaled_w] = rect_rgba

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
        self._had_delta = True
        result = b"".join(result_parts)
        elapsed_us = int((time.perf_counter() - t0) * 1e6)
        self._stats_fh.write(
            f"{n},{changed_pct:.2f},dirty_rect,{len(result)},{elapsed_us},"
            f"{row},{col},{self._cell_h},{self._cell_w},{padded_w},{padded_h},"
            f"{x1},{y1},{rect_w},{rect_h},"
            f"{self.refx_kitty},{self.refy_kitty},{self.kitty_scale}\n"
        )
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

        Uses a baseline image (i=1) with dirty-rect delta updates (i=2)
        via p=1 placement replacement.  Returns empty bytes when unchanged.
        """
        if last_frame is not None and video.shape == last_frame.shape:
            if np.array_equal(video, last_frame):
                self._profile.skipped += 1
                self._frame_no += 1
                n = self._frame_no
                self._stats_fh.write(f"{n},0.0,skip,0,0,,,,,,,,,,,,,\n")
                self._stats_fh.flush()
                return b""
        result = self._encode_kitty(video, encode_kitty_rgba)
        self._profile.bytes_out += len(result)
        return result
