# uses tests/frames/ files:
# - input.raw -- raw video frame
# - kitty-x?.golden: converted to kitty at integer scale
# - sixel-x?.golden: converted to sixel graphics at integer scale
#
# "cat" these files to see their graphics in a terminal.  These mostly help reduce regressions in
# either graphics renderer, especially the individual byte colors, the RGB ordering is a bit tricky
# between the native emulator screen and the two graphics renderers, ensuring byte-for-byte accuracy
# helps.
from pathlib import Path

import numpy as np
import pytest

from gambaterm.graphicsblit import (
    to_rgb,
    to_rgba_u8,
    encode_sixel,
    encode_kitty_rgba,
)

FRAMES_DIR = Path(__file__).parent / "frames"


def _load_frame():
    return np.fromfile(FRAMES_DIR / "input.raw", dtype=np.uint32).reshape(144, 160)


def _load_golden(name):
    return (FRAMES_DIR / name).read_bytes()


def test_encode_sixel_emits_raster_attributes():
    colors = np.zeros((6, 10, 3), dtype=np.float32)
    result = encode_sixel(colors, max_colors=256, scale=1).decode("latin-1")
    assert result.startswith("\033P0;1;0q")
    assert '"1;1;10;6' in result
    assert result.endswith("\033\\")


@pytest.mark.parametrize("scale", [1, 2, 3])
def test_encode_sixel_golden(scale):
    video = _load_frame()
    colors = to_rgb(video)
    result = encode_sixel(colors, max_colors=256, scale=scale)
    expected = _load_golden(f"sixel-x{scale}.golden")
    assert result == expected


@pytest.mark.parametrize("scale", [1, 2, 3])
def test_kitty_rgba_golden(scale):
    video = _load_frame()
    rgba = to_rgba_u8(video)
    if scale > 1:
        rgba = np.repeat(np.repeat(rgba, scale, axis=0), scale, axis=1)
    h, w = rgba.shape[:2]
    result = encode_kitty_rgba(rgba.tobytes(), w, h)
    expected = _load_golden(f"kitty-x{scale}.golden")
    assert result == expected


def test_encode_kitty_rgba_positioned():
    rgba = np.zeros((4, 4, 4), dtype=np.uint8)
    rgba[:, :, 3] = 255
    result = encode_kitty_rgba(rgba.tobytes(), 4, 4, image_id=2, X=3, Y=5, z=1)
    text = result.decode("latin-1")
    assert text.startswith("\033_Ga=T,i=2,q=2,f=32,s=4,v=4,o=z,z=1,X=3,Y=5;")
    assert text.endswith("\033\\")


def test_kitty_dirty_rect_delta():
    """Dirty-rect delta uses p=1 placement with cell-snapped cursor position."""
    from gambaterm.graphics_scaler import GraphicsScaler

    scaler = GraphicsScaler(
        scale=1,
        kitty_scale=1,
        refx=1,
        refy=1,
        refx_kitty=1,
        refy_kitty=1,
        cell_h=24,
        cell_w=12,
    )

    baseline = np.full((10, 10), 0xFF00FF00, dtype=np.uint32)
    scaler.blit_kitty(baseline, None)

    changed = baseline.copy()
    changed[3, 4] = 0xFFFF0000
    result = scaler.blit_kitty(changed, baseline)

    text = result.decode("latin-1")
    assert "i=2" in text
    assert "p=1" in text
    assert "z=" not in text
    assert "i=1" not in text


def test_kitty_rebaseline_deletes_delta():
    """A rebaseline sends a new i=1 and explicitly deletes i=2."""
    from gambaterm.graphics_scaler import GraphicsScaler

    scaler = GraphicsScaler(
        scale=1,
        kitty_scale=1,
        refx=1,
        refy=1,
        refx_kitty=1,
        refy_kitty=1,
        cell_h=24,
        cell_w=12,
    )

    baseline = np.full((10, 10), 0xFF00FF00, dtype=np.uint32)
    scaler.blit_kitty(baseline, None)

    changed = baseline.copy()
    changed[0, 0] = 0xFFFF0000
    scaler.blit_kitty(changed, baseline)

    big_change = np.full((10, 10), 0xFF0000FF, dtype=np.uint32)
    result = scaler.blit_kitty(big_change, changed)
    text = result.decode("latin-1")
    assert "i=1" in text
    assert "a=d,d=i,i=2" in text
    assert "z=1" not in text


def test_sixel_overlay_delta():
    """A small change produces a full-frame sixel overlay at refx,refy."""
    from gambaterm.graphics_scaler import GraphicsScaler

    scaler = GraphicsScaler(
        scale=1,
        kitty_scale=1,
        refx=5,
        refy=10,
        refx_kitty=1,
        refy_kitty=1,
        cell_h=2,
        cell_w=2,
    )

    baseline = np.full((10, 10), 0xFF00FF00, dtype=np.uint32)
    scaler.blit_sixel(baseline, None)

    changed = baseline.copy()
    changed[3, 4] = 0xFFFF0000
    result = scaler.blit_sixel(changed, baseline)

    text = result.decode("latin-1")
    assert text.startswith("\033[5;10H\033[0m")
    assert "\033P0;1;0q" in text
    assert "\033\\" in text


def test_sixel_skip_identical():
    """Identical frames return empty bytes."""
    from gambaterm.graphics_scaler import GraphicsScaler

    scaler = GraphicsScaler(
        scale=1,
        kitty_scale=1,
        refx=1,
        refy=1,
        refx_kitty=1,
        refy_kitty=1,
        cell_h=2,
        cell_w=2,
    )

    frame = np.full((10, 10), 0xFF00FF00, dtype=np.uint32)
    scaler.blit_sixel(frame, None)
    result = scaler.blit_sixel(frame, frame)
    assert result == b""


def test_sixel_rebaseline_on_large_change():
    """A change exceeding the threshold produces a full-frame sixel at refx,refy."""
    from gambaterm.graphics_scaler import GraphicsScaler

    scaler = GraphicsScaler(
        scale=1,
        kitty_scale=1,
        refx=2,
        refy=3,
        refx_kitty=1,
        refy_kitty=1,
        cell_h=2,
        cell_w=2,
    )

    baseline = np.full((10, 10), 0xFF00FF00, dtype=np.uint32)
    scaler.blit_sixel(baseline, None)

    changed = np.full((10, 10), 0xFF0000FF, dtype=np.uint32)
    result = scaler.blit_sixel(changed, baseline)

    text = result.decode("latin-1")
    assert text.startswith("\033[2;3H\033[0m")
    assert "\033P0;1;0q" in text
    assert "\033\\" in text

class TestAutoScale:
    @staticmethod
    def test_fps_below_threshold_reduces():
        from gambaterm.graphics_scaler import AutoScale

        autoscale = AutoScale(8, -1)
        result = autoscale.feed_fps(30.0, 40.0)
        assert result is True
        assert autoscale.max_scale == 6

    @staticmethod
    def test_fps_above_threshold_no_reduction():
        from gambaterm.graphics_scaler import AutoScale

        autoscale = AutoScale(8, -1)
        result = autoscale.feed_fps(50.0, 40.0)
        assert result is False
        assert autoscale.max_scale == 8

    @pytest.mark.parametrize("threshold,expected", [(0.0, False), (40.0, False)])
    def test_fps_check_respects(self, threshold, expected):
        from gambaterm.graphics_scaler import AutoScale

        autoscale = AutoScale(8, -1)
        if threshold == 0.0:
            result = autoscale.feed_fps(10.0, threshold)
            assert result is expected
        else:
            autoscale.deadline = 0
            result = autoscale.feed_fps(10.0, threshold)
            assert result is expected
        assert autoscale.max_scale == 8

    @staticmethod
    def test_reduces_to_floor_of_one():
        from gambaterm.graphics_scaler import AutoScale

        autoscale = AutoScale(4, -1)
        result = autoscale.feed_fps(30.0, 40.0)
        assert result is True
        assert autoscale.max_scale == 2
        result = autoscale.feed_fps(30.0, 40.0)
        assert result is True
        assert autoscale.max_scale == 1
        result = autoscale.feed_fps(30.0, 40.0)
        assert result is False
        assert autoscale.max_scale == 1

    @staticmethod
    def test_reset_restores_ceiling():
        from gambaterm.graphics_scaler import AutoScale

        autoscale = AutoScale(8, -1)
        autoscale.feed_fps(30.0, 40.0)
        assert autoscale.max_scale == 6
        autoscale.reset()
        assert autoscale.max_scale == 8

    @pytest.mark.parametrize("window_s", [0, -1])
    def test_window_modes(self, window_s):
        from gambaterm.graphics_scaler import AutoScale

        autoscale = AutoScale(8, window_s)
        if window_s == 0:
            result = autoscale.feed_fps(10.0, 40.0)
            assert result is False
            assert autoscale.max_scale == 8
        else:
            assert autoscale.deadline == float("inf")

    @staticmethod
    def test_bandwidth_over_threshold_reduces():
        from gambaterm.graphics_scaler import AutoScale

        autoscale = AutoScale(8, -1)
        result = autoscale.feed_bandwidth(300.0, 2.0)
        assert result is True
        assert autoscale.max_scale == 6

    @staticmethod
    def test_bandwidth_below_threshold_no_reduction():
        from gambaterm.graphics_scaler import AutoScale

        autoscale = AutoScale(8, -1)
        result = autoscale.feed_bandwidth(200.0, 2.0)
        assert result is False
        assert autoscale.max_scale == 8

    @pytest.mark.parametrize("threshold,expected", [(0.0, False), (1.0, False)])
    def test_bandwidth_check_respects(self, threshold, expected):
        from gambaterm.graphics_scaler import AutoScale

        autoscale = AutoScale(8, -1)
        if threshold == 0.0:
            result = autoscale.feed_bandwidth(9999.0, threshold)
        else:
            autoscale.deadline = 0
            result = autoscale.feed_bandwidth(9999.0, threshold)
        assert result is expected
        assert autoscale.max_scale == 8


class TestParseAutoscale:
    @pytest.mark.parametrize("value", ["off", "no", "disabled", ""])
    def test_disabled(self, value):
        from gambaterm.graphics_scaler import parse_autoscale

        assert parse_autoscale(value).enabled is False

    @pytest.mark.parametrize("value,seconds,fps,mbits", [
        ("30fps", -1, 30.0, 0.0),
        ("60s,30fps,10mb", 60, 30.0, 80.0),
        ("1500kb", -1, 40.0, 12.0),
        ("always,25fps", -1, 25.0, 0.0),
    ])
    def test_parse(self, value, seconds, fps, mbits):
        from gambaterm.graphics_scaler import parse_autoscale

        cfg = parse_autoscale(value)
        assert cfg.enabled is True
        assert cfg.seconds == seconds
        assert cfg.fps == fps
        assert cfg.bandwidth_mbits == mbits

    @pytest.mark.parametrize("value", [
        "always,90s,30fps",
        "disabled,90s,10mb",
        "off,30fps",
    ])
    def test_mutually_exclusive_errors(self, value):
        from gambaterm.graphics_scaler import parse_autoscale

        with pytest.raises(ValueError):
            parse_autoscale(value)
