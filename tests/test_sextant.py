from __future__ import annotations

import sys
from pathlib import Path
from subprocess import run as subprocess_run

import numpy as np
from wcwidth import strip_sequences

from gambaterm.sextant import SEXTANT, _display_cache, blit_sextant

TEST_ROM = Path(__file__).parent / "test_rom.gb"


def test_sextant_table() -> None:
    assert len(SEXTANT) == 64
    assert len(set(SEXTANT)) == 64
    assert SEXTANT[0] == " "
    assert SEXTANT[63] == "\u2588"
    assert SEXTANT[21] == "\u258c"
    assert SEXTANT[42] == "\u2590"
    for i in range(64):
        if i not in (0, 21, 42, 63):
            assert 0x1FB00 <= ord(SEXTANT[i]) <= 0x1FB3B


def test_blit_sextant() -> None:
    _display_cache.clear()
    image = np.full((144, 160), 0x00FF0000, np.uint32)
    result = blit_sextant(image, None, 1, 1, 80, 48, 4)
    assert isinstance(result, bytes)
    assert len(result) > 0

    second = blit_sextant(image, image, 1, 1, 80, 48, 4)
    assert len(second) < len(result)


def test_gambaterm_sextant() -> None:
    assert TEST_ROM.exists()
    gambaterm = (
        f"gambaterm {TEST_ROM} --break-after 10 --input-file /dev/null"
        " --disable-audio --color-mode 4"
    )
    command = f"stty cols 80 rows 50; {gambaterm}"
    result = subprocess_run(
        f"script -e -q -c '{command}' /dev/null",
        shell=True,
        check=True,
        text=True,
        capture_output=True,
    )
    assert result.stderr == ""
    assert "test_rom.gb" in result.stdout
    if sys.platform == "linux":
        stripped = strip_sequences(result.stdout)
        assert " " * 80 in stripped
        assert any(0x1FB00 <= ord(c) <= 0x1FB3B for c in stripped)
