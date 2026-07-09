"""Auto-scale configuration and dynamic scale cap for graphics rendering."""

import os
import time
from typing import NamedTuple

SCALE_MAX = int(os.environ.get("GAMBATERM_SCALE_MAX", "12"))


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
            bandwidth_mbits = float(token[:-2]) * 8.0
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

    * :meth:`feed_fps` reduces when ``video_fps`` drops below a threshold.
    * :meth:`feed_bandwidth` reduces when output data rate exceeds a cap.

    Reductions are only allowed within *window_s* seconds of construction
    or the most recent :meth:`reset` call.
    """

    def __init__(self, ceiling: int, window_s: int) -> None:
        self._ceiling = ceiling
        self.window_s = window_s
        self.max_scale = ceiling
        self.deadline = self.compute_deadline()

    def compute_deadline(self) -> float:
        if self.window_s == 0:
            return 0.0
        if self.window_s == -1:
            return float("inf")
        return time.monotonic() + self.window_s

    def feed_fps(self, video_fps: float, threshold_fps: float) -> bool:
        """Return True if *max_scale* was reduced."""
        if threshold_fps <= 0:
            return False
        if time.monotonic() > self.deadline:
            return False
        if video_fps < threshold_fps and self.max_scale > 1:
            self.max_scale = max(1, self.max_scale - 2)
            return True
        return False

    def reset(self) -> None:
        """Restore *max_scale* to ceiling, reset deadline."""
        self.max_scale = self._ceiling
        self.deadline = self.compute_deadline()

    def feed_bandwidth(self, data_rate_kb_s: float, threshold_mbit_s: float) -> bool:
        """Return True if *max_scale* was reduced due to bandwidth."""
        if threshold_mbit_s <= 0:
            return False
        if time.monotonic() > self.deadline:
            return False
        if data_rate_kb_s > threshold_mbit_s * 125.0 and self.max_scale > 1:
            self.max_scale = max(1, self.max_scale - 2)
            return True
        return False
