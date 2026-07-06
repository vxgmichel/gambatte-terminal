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
