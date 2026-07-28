# uses tests/frames/ files:
# - input.raw -- raw video frame
# - kitty-x?.golden: converted to kitty at integer scale
# - sixel-x?.golden: converted to sixel graphics at integer scale
#
# "cat" these files to see their graphics in a terminal that supports them.
#
# These mostly help reduce regressions in either graphics renderer, especially the individual byte
# colors, the RGB ordering is a bit tricky between the native emulator screen and the two graphics
# renderers, or any other misfiring, or as confirmation of adjustments to blitters.
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
    assert text.startswith("\033_Ga=T,i=2,q=1,f=32,s=4,v=4,o=z,N=1,z=1,X=3,Y=5;")
    assert text.endswith("\033\\")


def test_kitty_dirty_rect_delta():
    """Dirty-rect delta uses pixel-precise X/Y placement with cell-snapped cursor."""
    from gambaterm.graphics_scaler import FrameEncoder

    scaler = FrameEncoder(
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
    scaler.encode_kitty(baseline, None)

    changed = baseline.copy()
    changed[3, 4] = 0xFFFF0000
    result = scaler.encode_kitty(changed, baseline)

    text = result.decode("latin-1")
    assert "X=4" in text
    assert "Y=3" in text
    assert "a=T" in text
    assert "f=32" in text
    assert ",i=1," not in text


def test_kitty_rebaseline_deletes_delta():
    """A rebaseline deletes the old delta (i=100) and sends a new keyframe (i=1)."""
    from gambaterm.graphics_scaler import FrameEncoder

    scaler = FrameEncoder(
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
    scaler.encode_kitty(baseline, None)

    changed = baseline.copy()
    changed[0, 0] = 0xFFFF0000
    scaler.encode_kitty(changed, baseline)

    big_change = np.full((10, 10), 0xFF0000FF, dtype=np.uint32)
    result = scaler.encode_kitty(big_change, changed)
    text = result.decode("latin-1")
    assert "a=d,d=i,i=100" in text
    assert "a=T" in text
    assert "f=32" in text
    assert ",i=1," in text


def test_sixel_overlay_delta():
    """A small change produces a full-frame sixel overlay at refx,refy."""
    from gambaterm.graphics_scaler import FrameEncoder

    scaler = FrameEncoder(
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
    scaler.encode_sixel(baseline, None)

    changed = baseline.copy()
    changed[3, 4] = 0xFFFF0000
    result = scaler.encode_sixel(changed, baseline)

    text = result.decode("latin-1")
    assert text.startswith("\033[5;10H\033[0m")
    assert "\033P0;1;0q" in text
    assert "\033\\" in text


def test_sixel_skip_identical():
    """Identical frames return empty bytes."""
    from gambaterm.graphics_scaler import FrameEncoder

    scaler = FrameEncoder(
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
    scaler.encode_sixel(frame, None)
    result = scaler.encode_sixel(frame, frame)
    assert result == b""


def test_sixel_rebaseline_on_large_change():
    """A change exceeding the threshold produces a full-frame sixel at refx,refy."""
    from gambaterm.graphics_scaler import FrameEncoder

    scaler = FrameEncoder(
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
    scaler.encode_sixel(baseline, None)

    changed = np.full((10, 10), 0xFF0000FF, dtype=np.uint32)
    result = scaler.encode_sixel(changed, baseline)

    text = result.decode("latin-1")
    assert text.startswith("\033[2;3H\033[0m")
    assert "\033P0;1;0q" in text
    assert "\033\\" in text


class TestKittyFrameCache:
    @staticmethod
    def test_keyframe_cache_hit():
        """Single-slot cache replays an identical rebaseline via a=p."""
        import os
        from gambaterm.graphics_scaler import FrameEncoder

        os.environ["GAMBATERM_FORCE_REBASELINE"] = "1"
        try:
            scaler = FrameEncoder(1, 1, 1, 1, 1, 1, 24, 12)
            frame_a = np.full((10, 10), 0xFF00FF00, dtype=np.uint32)
            scaler.encode_kitty_frame(
                frame_a, lambda d, w, h, **kw: b"\033_Ga=T")
            result = scaler.encode_kitty_frame(
                frame_a, lambda d, w, h, **kw: b"\033_Ga=T")
            text = result.decode("latin-1")
            assert "a=p" in text
            assert "a=T" not in text
        finally:
            os.environ.pop("GAMBATERM_FORCE_REBASELINE", None)

    @staticmethod
    def test_keyframe_cache_eviction():
        """Single-slot cache: only the most recent keyframe is cached."""
        import os
        from gambaterm.graphics_scaler import FrameEncoder

        os.environ["GAMBATERM_FORCE_REBASELINE"] = "1"
        try:
            scaler = FrameEncoder(1, 1, 1, 1, 1, 1, 24, 12)

            frame_a = np.full((10, 10), 0xFF00FF00, dtype=np.uint32)
            frame_b = np.full((10, 10), 0xFF0000FF, dtype=np.uint32)

            scaler.encode_kitty_frame(
                frame_a, lambda d, w, h, **kw: b"\033_Ga=T")
            scaler.encode_kitty_frame(
                frame_b, lambda d, w, h, **kw: b"\033_Ga=T")

            result = scaler.encode_kitty_frame(
                frame_a, lambda d, w, h, **kw: b"\033_Ga=T")
            text = result.decode("latin-1")
            assert "a=T" in text
            assert "a=p" not in text
        finally:
            os.environ.pop("GAMBATERM_FORCE_REBASELINE", None)

    @staticmethod
    def test_delta_after_cache_hit_keyframe():
        """Delta after a cache-hit keyframe uses DELTA_ID=100 with pixel-precise X/Y."""
        from gambaterm.graphics_scaler import FrameEncoder

        scaler = FrameEncoder(1, 1, 1, 1, 1, 1, 2, 2)

        frame_a = np.full((10, 10), 0xFF00FF00, dtype=np.uint32)
        scaler.encode_kitty(frame_a, None)

        changed = frame_a.copy()
        changed[3, 4] = 0xFFFF0000
        result_delta = scaler.encode_kitty(changed, frame_a)
        text_delta = result_delta.decode("latin-1")
        assert "Y=1" in text_delta
        assert "a=T" in text_delta
        assert "i=100" in text_delta


class TestKittyFrameBanding:
    @staticmethod
    def test_band_encode_positioned_images():
        """Each band is placed at its own cell-snapped cursor row."""
        from gambaterm.graphics_scaler import FrameEncoder

        scaler = FrameEncoder(
            scale=1, kitty_scale=2, refx=1, refy=1,
            refx_kitty=1, refy_kitty=1, cell_h=24, cell_w=12,
            frame_banding=True,
        )
        scaler._V = 3
        scaler._v_current = 0
        scaler._v_row_height = 48
        scaler.kitty_frame_no = 0

        frame = np.full((144, 160), 0xFF00FF00, dtype=np.uint32)
        last_frame = np.zeros((144, 160), dtype=np.uint32)

        # Band 0: y0=0, row=1, off_y=0.  Includes delete of old band image.
        result0 = scaler._encode_kitty_band(frame, last_frame)
        text0 = result0.decode("latin-1")
        assert "a=d,d=i,i=1" in text0
        assert "a=T" in text0
        assert "i=1" in text0
        assert "f=32" in text0
        assert "\033[1;1H" in text0
        assert scaler._v_current == 1

        # Band 1: y0=48, py=96, row=1+96//24=5, off_y=96%24=0
        result1 = scaler._encode_kitty_band(frame, last_frame)
        text1 = result1.decode("latin-1")
        assert "i=2" in text1
        assert "\033[5;1H" in text1
        assert scaler._v_current == 2

        # Band 2: y0=96, py=192, row=1+192//24=9, off_y=192%24=0
        result2 = scaler._encode_kitty_band(frame, last_frame)
        text2 = result2.decode("latin-1")
        assert "i=3" in text2
        assert "\033[9;1H" in text2
        assert scaler._v_current == 0

    @staticmethod
    def test_band_skip_unchanged():
        """Unchanged band regions return empty bytes and do not advance v_current."""
        from gambaterm.graphics_scaler import FrameEncoder

        scaler = FrameEncoder(
            scale=1, kitty_scale=1, refx=1, refy=1,
            refx_kitty=1, refy_kitty=1, cell_h=24, cell_w=12,
            frame_banding=True,
        )
        scaler._V = 2
        scaler._v_current = 0
        scaler._v_row_height = 72
        scaler.kitty_frame_no = 0

        frame = np.full((144, 160), 0xFF00FF00, dtype=np.uint32)
        last_frame = frame.copy()

        result = scaler._encode_kitty_band(frame, last_frame)
        assert result == b""
        assert scaler._v_current == 1

    @staticmethod
    def test_is_banding_v1_noop():
        """V=1 means is_banding returns False (full frame fits in one band)."""
        from gambaterm.graphics_scaler import FrameEncoder

        scaler = FrameEncoder(
            scale=1, kitty_scale=1, refx=1, refy=1,
            refx_kitty=1, refy_kitty=1, cell_h=24, cell_w=12,
            frame_banding=True,
        )
        scaler._V = 1
        assert scaler.is_banding is False
        scaler._V = 2
        assert scaler.is_banding is True
