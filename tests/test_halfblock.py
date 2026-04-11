from __future__ import annotations

import sys
from pathlib import Path
from subprocess import run as subprocess_run

import numpy as np
import numpy.typing as npt
import pytest
from wcwidth import strip_sequences

from gambaterm.halfblock import blit_half, _display_cache

TEST_ROM = Path(__file__).parent / "test_rom.gb"

WHITE = int(np.uint32(0xFFFFFFFF))
BLACK = int(np.uint32(0xFF000000))
RED = int(np.uint32(0xFFFF0000))
GREEN = int(np.uint32(0xFF00FF00))


def _make_image(cell_pixels: list[list[int]]) -> npt.NDArray[np.uint32]:
    """Build a 144x160 image with one cell's 2x4 block set, rest white."""
    image = np.full((144, 160), WHITE, np.uint32)
    for row_idx, row in enumerate(cell_pixels):
        for col_idx, val in enumerate(row):
            image[row_idx, col_idx] = np.uint32(val)
    return image


def _blit_one(cell_pixels: list[list[int]]) -> str:
    """Blit and return stripped Unicode text for a single-cell image."""
    _display_cache.clear()
    image = _make_image(cell_pixels)
    raw = blit_half(image, None, 0, 0, 80, 36, 4)
    return strip_sequences(raw.decode("utf-8", errors="replace"))


def test_solid_white() -> None:
    pixels = [[WHITE, WHITE]] * 4
    text = _blit_one(pixels)
    assert " " in text


def test_solid_black() -> None:
    pixels = [[BLACK, BLACK]] * 4
    text = _blit_one(pixels)
    assert " " in text or "\u2588" in text


def test_horizontal_split_50() -> None:
    pixels = [
        [WHITE, WHITE],
        [WHITE, WHITE],
        [BLACK, BLACK],
        [BLACK, BLACK],
    ]
    text = _blit_one(pixels)
    assert "\u2584" in text or "\u2580" in text


def test_horizontal_split_25() -> None:
    pixels = [
        [WHITE, WHITE],
        [WHITE, WHITE],
        [WHITE, WHITE],
        [BLACK, BLACK],
    ]
    text = _blit_one(pixels)
    assert "\u2582" in text or "\U0001FB85" in text


def test_horizontal_split_75() -> None:
    pixels = [
        [WHITE, WHITE],
        [BLACK, BLACK],
        [BLACK, BLACK],
        [BLACK, BLACK],
    ]
    text = _blit_one(pixels)
    assert "\u2586" in text or "\U0001FB82" in text


def test_vertical_split() -> None:
    pixels = [
        [WHITE, BLACK],
        [WHITE, BLACK],
        [WHITE, BLACK],
        [WHITE, BLACK],
    ]
    text = _blit_one(pixels)
    assert "\u258c" in text or "\u2590" in text


def test_full_block() -> None:
    pixels = [[RED, RED]] * 4
    _display_cache.clear()
    image = _make_image(pixels)
    raw = blit_half(image, None, 0, 0, 80, 36, 4)
    text = strip_sequences(raw.decode("utf-8", errors="replace"))
    assert " " in text or "\u2588" in text


def test_diagonal_falls_back() -> None:
    pixels = [
        [WHITE, BLACK],
        [BLACK, WHITE],
        [WHITE, BLACK],
        [BLACK, WHITE],
    ]
    text = _blit_one(pixels)
    assert len(text.strip()) > 0


def test_no_change_skips_redraw() -> None:
    _display_cache.clear()
    image = np.full((144, 160), WHITE, np.uint32)
    first = blit_half(image, None, 0, 0, 80, 36, 4)
    assert len(first) > 20
    second = blit_half(image, image, 0, 0, 80, 36, 4)
    assert len(second) < len(first)


def test_blit_half_basic() -> None:
    _display_cache.clear()
    image = np.full((144, 160), 0x00FF0000, np.uint32)
    result = blit_half(image, None, 1, 1, 80, 36, 4)
    assert isinstance(result, bytes)
    assert len(result) > 0

    second = blit_half(image, image, 1, 1, 80, 36, 4)
    assert len(second) < len(result)


@pytest.mark.parametrize(
    "interactive", (False, True), ids=("non-interactive", "interactive")
)
def test_gambaterm_halfblock(interactive: bool) -> None:
    assert TEST_ROM.exists()
    command = (
        f"gambaterm {TEST_ROM} --break-after 10 --input-file /dev/null"
        " --disable-audio --color-mode 4"
    )
    result = subprocess_run(
        f"script -e -q -c '{command}' /dev/null" if interactive else command,
        shell=True,
        check=True,
        text=True,
        capture_output=True,
    )
    if interactive:
        assert result.stderr == ""
        assert "test_rom.gb" in result.stdout
    if sys.platform == "linux":
        stripped = strip_sequences(result.stdout)
        assert " " * 80 in stripped
        assert any(c in stripped for c in "\u2588\u2580\u2584")
