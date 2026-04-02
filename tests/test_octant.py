from __future__ import annotations

import sys
from pathlib import Path
from subprocess import run as subprocess_run

import numpy as np
import pytest
from wcwidth import strip_sequences

from gambaterm.octant import (
    OCTANT,
    _OCTANT_SPECIALS,
    _display_cache,
    blit_octant,
)

TEST_ROM = Path(__file__).parent / "test_rom.gb"


def test_octant_table() -> None:
    assert len(OCTANT) == 256
    assert len(set(OCTANT)) == 256
    assert OCTANT[0x00] == "\u00a0"
    assert OCTANT[0xFF] == "\u2588"
    assert OCTANT[0x55] == "\u258c"
    assert OCTANT[0xAA] == "\u2590"
    assert OCTANT[0x0F] == "\u2580"
    assert OCTANT[0xF0] == "\u2584"
    assert len(_OCTANT_SPECIALS) == 26
    codepoints = sorted(ord(OCTANT[i]) for i in range(256) if i not in _OCTANT_SPECIALS)
    assert len(codepoints) == 230
    assert codepoints[0] == 0x1CD00
    assert codepoints[-1] == 0x1CDE5
    for j in range(1, len(codepoints)):
        assert codepoints[j] == codepoints[j - 1] + 1


def test_blit_octant() -> None:
    _display_cache.clear()
    image = np.full((144, 160), 0x00FF0000, np.uint32)
    result = blit_octant(image, None, 1, 1, 80, 36, 4)
    assert isinstance(result, bytes)
    assert len(result) > 0

    second = blit_octant(image, image, 1, 1, 80, 36, 4)
    assert len(second) < len(result)


@pytest.mark.parametrize(
    "interactive", (False, True), ids=("non-interactive", "interactive")
)
def test_gambaterm_octant(interactive: bool) -> None:
    assert TEST_ROM.exists()
    command = (
        f"gambaterm {TEST_ROM} --break-after 10 --input-file /dev/null"
        " --disable-audio --color-mode 4 --octants"
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
        assert "\u00a0" * 80 in stripped or " " * 80 in stripped
        has_octant = any(0x1CD00 <= ord(c) <= 0x1CDE5 for c in stripped)
        has_block = any(c in stripped for c in "\u2588\u258c\u2590")
        assert has_octant or has_block
