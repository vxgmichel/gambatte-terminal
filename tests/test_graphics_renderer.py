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
    assert result.startswith("\033Pq")
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
    """A small change produces a cell-snapped positioned delta (no X/Y offsets)."""
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
    scaler.blit_kitty(baseline, None, 10, 10, None)

    # One pixel changed at (4,3) → padded to 12×24 cell at (1,1), no X/Y
    changed = baseline.copy()
    changed[3, 4] = 0xFFFF0000
    result = scaler.blit_kitty(changed, baseline, 10, 10, None)

    text = result.decode("latin-1")
    assert text.startswith("\033[1;1H")
    assert "i=2" in text
    assert "p=1" in text
    assert "z=" not in text  # not needed; i=2 > i=1 ensures stacking
    assert "s=12" in text
    assert "v=24" in text
    assert "X=" not in text
    assert "Y=" not in text
    assert "i=1" not in text


def test_kitty_rebaseline_deletes_delta():
    """A rebaseline sends a new i=1; i=2 is orphaned (no explicit delete)."""
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
    scaler.blit_kitty(baseline, None, 10, 10, None)

    changed = baseline.copy()
    changed[0, 0] = 0xFFFF0000
    scaler.blit_kitty(changed, baseline, 10, 10, None)

    big_change = np.full((10, 10), 0xFF0000FF, dtype=np.uint32)
    result = scaler.blit_kitty(big_change, changed, 10, 10, None)
    text = result.decode("latin-1")
    assert "i=1" in text
    assert "a=d,d=i,i=2" in text


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
    scaler.blit_sixel(baseline, None, 10, 10)

    changed = baseline.copy()
    changed[3, 4] = 0xFFFF0000
    result = scaler.blit_sixel(changed, baseline, 10, 10)

    text = result.decode("latin-1")
    assert text.startswith("\033[5;10H\033[0m")
    assert "\033Pq" in text
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
    scaler.blit_sixel(frame, None, 10, 10)
    result = scaler.blit_sixel(frame, frame, 10, 10)
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
    scaler.blit_sixel(baseline, None, 10, 10)

    changed = np.full((10, 10), 0xFF0000FF, dtype=np.uint32)
    result = scaler.blit_sixel(changed, baseline, 10, 10)

    text = result.decode("latin-1")
    assert text.startswith("\033[2;3H\033[0m")
    assert "\033Pq" in text
    assert "\033\\" in text
