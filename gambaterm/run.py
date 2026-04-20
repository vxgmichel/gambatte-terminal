from __future__ import annotations

import os
import re
import sys
import time
import contextlib
from itertools import count
from collections import deque
from typing import Callable, Deque, Iterator, cast

import numpy as np
import numpy.typing as npt
from blessed import Terminal

from .termblit import blit
from .sextant import blit_sextant_streched, blit_sextant_compressed
from .octant import blit_octant
from .halfblock import blit_half
from .halfblit import set_cp437 as _half_set_cp437
from .audio import AudioOut
from .console import Console
from .input_getter import BaseInputGetter
from .colors import ColorMode

_CPR_RE = re.compile(r"\x1b\[\d+;\d+R")

_BLIT_NAMES = {
    blit: "fullres",
    blit_sextant_streched: "sextant_streched",
    blit_sextant_compressed: "sextant_compressed",
    blit_octant: "octant",
    blit_half: "halfres",
}


@contextlib.contextmanager
def timing(deltas: Deque[float]) -> Iterator[None]:
    start = time.perf_counter()
    try:
        yield
    finally:
        deltas.append(time.perf_counter() - start)


def get_ref(
    width: int,
    height: int,
    console: Console,
    octant: bool = False,
    halfblock: bool = False,
    sextant_streched: bool = False,
    sextant_compressed: bool = False,
) -> tuple[int, int]:
    if octant or halfblock or sextant_compressed:
        rows = console.HEIGHT // 4
        cols = console.WIDTH // 2
    elif sextant_streched:
        rows = console.HEIGHT // 3
        cols = console.WIDTH * 2 // 3
    else:
        rows = console.HEIGHT // 2
        cols = console.WIDTH
    margin_x = min(2, max(0, height - rows))
    refx = margin_x + max(0, (height - margin_x - rows) // 2)
    if width < cols:
        # Not wide enough: crop sides, no horizontal margin
        refy = 0
    else:
        margin_y = min(3, max(0, width - cols - 1))
        refy = margin_y + max(0, (width - margin_y - cols) // 2)
    return refx, refy


def _cycle_color(cycle: float) -> tuple[int, int, int]:
    """Map a 0–4 cycle position to an RGB color on the red→black→white→black ramp."""
    if cycle < 1.0:
        t = cycle
        return int(255 * t), 0, 0
    elif cycle < 2.0:
        t = 2.0 - cycle
        return int(255 * t), 0, 0
    elif cycle < 3.0:
        t = cycle - 2.0
        return int(255 * t), int(255 * t), int(255 * t)
    else:
        t = 4.0 - cycle
        return int(255 * t), int(255 * t), int(255 * t)


class Overlay:
    """Flashing text overlay with optional keep-alive.

    :param text: message to display
    :param duration: seconds to show before auto-dismiss
    :param keep_alive: optional callable returning True to hold the
        overlay beyond *duration* (re-checked each frame).  The
        overlay dismisses when *keep_alive* returns False **and**
        *duration* has elapsed.
    """

    def __init__(
        self,
        text: str,
        duration: float = 3.0,
        keep_alive: Callable[[], bool] | None = None,
    ) -> None:
        self.text = text
        self.duration = duration
        self.keep_alive = keep_alive
        self.start = time.perf_counter()
        self.active = True

    def render(self, width: int, height: int) -> bytes:
        """Return ANSI bytes for this frame, or b'' if dismissed."""
        if not self.active:
            return b""
        elapsed = time.perf_counter() - self.start
        alive = self.keep_alive() if self.keep_alive else False
        if elapsed >= self.duration and not alive:
            self.active = False
            row = max(1, height - 2)
            return f"\033[{row};1H\033[0m\033[K".encode()
        max_len = width - 2
        if max_len <= 0 or height < 3:
            return b""
        text = self.text[:max_len] if len(self.text) > max_len else self.text
        row = max(1, height - 2)
        col = max(1, (width - len(text)) // 2 + 1)
        cycle = (elapsed / 0.6) % 4.0
        ri, gi, bi = _cycle_color(cycle)
        bri, bgi, bbi = _cycle_color((cycle + 1.0) % 4.0)
        return (
            f"\033[{row};{col}H"
            f"\033[1;38;2;{ri};{gi};{bi};48;2;{bri};{bgi};{bbi}m{text}\033[0m"
        ).encode()


def write_bytes(term: Terminal, video_data: bytes) -> None:
    # Fix code page issue on windows:
    # `sys.stdout.buffer.raw` is a `WindowsConsoleIO` that always support UTF-8
    # regardless of the configured codepage
    if sys.platform == "win32" and term.stream.fileno() == sys.stdout.fileno():
        sys.stdout.buffer.write(video_data)
        sys.stdout.buffer.flush()
    else:
        os.write(term.stream.fileno(), video_data)


def run(
    console: Console,
    input_getter: BaseInputGetter,
    term: Terminal,
    audio_out: AudioOut | None = None,
    frame_advance: int = 1,
    color_mode: ColorMode = ColorMode.HAS_24_BIT_COLOR,
    break_after: int | None = None,
    speed: float = 1.0,
    use_cpr_sync: bool = False,
    no_sextants: bool = False,
    use_octants: bool = False,
    cp437: bool = False,
) -> None:
    assert color_mode > 0
    _half_set_cp437(1 if cp437 else 0)

    # Prepare buffers with invalid data
    video = np.full((console.HEIGHT, console.WIDTH), 0, np.uint32)
    audio = np.full((2 * console.TICKS_IN_FRAME, 2), -0x7FFF, np.int16)
    last_frame: npt.NDArray[np.uint32] | None = video.copy()

    # Determine rendering mode based on terminal size.
    # Pick the highest-resolution mode whose grid fits the terminal,
    # allowing horizontal cropping when the height fits but width doesn't.
    def select_blit(w: int, h: int) -> Callable[..., bytes]:
        if h >= console.HEIGHT // 2 and w >= console.WIDTH:
            return blit
        if not no_sextants and h >= console.HEIGHT // 3 and w >= console.WIDTH * 2 // 3:
            return cast(Callable[..., bytes], blit_sextant_streched)
        if use_octants:
            return cast(Callable[..., bytes], blit_octant)
        return cast(Callable[..., bytes], blit_sextant_compressed)

    # Print area (default to 24x80 if terminal reports zero)
    height = term.height or 24
    width = term.width or 80
    blit_fn = select_blit(width, height)
    refx, refy = get_ref(
        width,
        height,
        console,
        sextant_streched=blit_fn is blit_sextant_streched,
        octant=blit_fn is blit_octant,
        halfblock=blit_fn is blit_half,
        sextant_compressed=blit_fn is blit_sextant_compressed,
    )

    # Prepare reporting
    fps = console.FPS * speed
    average_over = int(round(fps))  # frames
    ticks: Deque[float] = deque(maxlen=average_over)
    emu_deltas: Deque[float] = deque(maxlen=average_over)
    audio_deltas: Deque[float] = deque(maxlen=average_over)
    video_deltas: Deque[float] = deque(maxlen=average_over)
    sync_deltas: Deque[float] = deque(maxlen=average_over)
    total_deltas: Deque[float] = deque(maxlen=average_over)
    shifting: Deque[float] = deque(maxlen=average_over)
    shown_frames: Deque[int] = deque(maxlen=average_over)
    data_length: Deque[int] = deque(maxlen=average_over)
    start = time.time()

    # Create a 100 ms time shift to fill up audio buffer
    if audio_out:
        start -= 0.1

    # Prepare state
    new_frame = False
    screen_ready = True
    frame_start_time = None

    # Overlay notification — resize hint at startup when not at full resolution
    _RESIZE_TEXT = " !! Resize window and font size for higher resolution graphics !! "
    overlay: Overlay | None = None
    if blit_fn in (blit_sextant_streched, blit_octant, blit_sextant_compressed):
        overlay = Overlay(_RESIZE_TEXT, duration=6.0)

    # Loop over emulator frames
    for i in count():
        # Add total deltas
        if frame_start_time is not None:
            total_deltas.append(time.perf_counter() - frame_start_time)
        frame_start_time = time.perf_counter()

        # Break when frame limit is reach
        if break_after is not None and i >= break_after:
            return

        # Tick the emulator
        with timing(emu_deltas):
            console.set_input(input_getter.get_pressed())
            offset, samples = console.advance_one_frame(video, audio)
            new_frame = new_frame or offset > 0
            ticks.append(samples)

        # Send audio
        with timing(audio_deltas):
            if audio_out:
                audio_out.send(audio[:samples, :])

        # Read keys for ctrl-c, ctrl-d, and CPR response.
        # If the kitty keyboard protocol is used, all inputs are sent as CSI sequences
        # (e.g. `\x1b[99;5u` rather than raw `\x03`), so we check blessed's
        # decoded `key_name` attribute, since it ends up being `KEY_CTRL_C` for ctrl+c
        # and `KEY_CTRL_D` for ctrl+d regardless of the underlying encoding.
        new_color_mode = color_mode
        force_redraw = False
        for key in input_getter.pop_keystrokes():
            if key.key_name == "KEY_CTRL_C":
                raise KeyboardInterrupt
            if key.key_name == "KEY_CTRL_D":
                raise EOFError
            if key.key_name == "KEY_TAB":
                new_color_mode = color_mode.cycle()
                force_redraw = True
                overlay = Overlay(f" {new_color_mode.report()} ", duration=2.0)
            if key.key_name in ("KEY_BTAB", "KEY_SHIFT_TAB"):
                new_color_mode = color_mode.cycle(reverse=True)
                force_redraw = True
                overlay = Overlay(f" {new_color_mode.report()} ", duration=2.0)
            if key.key_name == "KEY_CTRL_O":
                use_octants = not use_octants
                force_redraw = True
                state = "enabled" if use_octants else "disabled"
                overlay = Overlay(f" Octants {state} ", duration=2.0)
            if key.key_name == "KEY_CTRL_P":
                cp437 = not cp437
                _half_set_cp437(1 if cp437 else 0)
                force_redraw = True
                state = "enabled" if cp437 else "disabled"
                overlay = Overlay(f" CP437 mode {state} ", duration=2.0)
            if _CPR_RE.match(str(key)):
                screen_ready = True

        # Render video
        with timing(video_deltas):
            # Send the frame
            shift = shifting and shifting[-1] > 1 / fps
            if i % frame_advance == 0 and new_frame and screen_ready and not shift:
                new_frame = False
                # Check terminal size
                new_height = term.height or 24
                new_width = term.width or 80
                maybe_clear_seq = b""
                if (
                    (new_height, new_width)
                    != (
                        height,
                        width,
                    )
                    or new_color_mode != color_mode
                    or force_redraw
                ):
                    maybe_clear_seq = b"\033[0m\033[40m\033[H\033[2J"
                    height, width = new_height, new_width
                    blit_fn = select_blit(width, height)
                    refx, refy = get_ref(
                        width,
                        height,
                        console,
                        sextant_streched=blit_fn is blit_sextant_streched,
                        octant=blit_fn is blit_octant,
                        halfblock=blit_fn is blit_half,
                        sextant_compressed=blit_fn is blit_sextant_compressed,
                    )
                    color_mode = new_color_mode
                    # Screen cleared — pass None to force full redraw
                    # (clears sextant/octant _display_cache, and Cython
                    # blit skips its last-frame comparison when last=None)
                    last_frame = None
                # Render frame with synchronized output mode (DEC 2026) to prevent flickering
                # when the screen is cleared, or an artificial CRT-like "rolling band" side-effects
                # from fast "sprite blinking" meant to cause "transparency" effect on original HW,
                # https://zladx.github.io/posts/links-awakening-partial-translucency
                # When cropping, check if pixels beyond the crop boundary
                # changed — this detects horizontal scroll with repeating
                # patterns that would cause ghost artifacts.  If any
                # off-screen pixel changed, pass last=None to force full
                # redraw.  Otherwise the pixel cache is safe to use.
                blit_last = last_frame
                if (
                    refy == 0
                    and width < (console.WIDTH // 2)
                    and last_frame is not None
                ):
                    crop_px = width * 2
                    if (video[:, crop_px:] != last_frame[:, crop_px:]).any():
                        blit_last = None
                video_data = (
                    b"\033[?2026h"
                    + maybe_clear_seq
                    + blit_fn(
                        video,
                        blit_last,
                        refx,
                        refy,
                        width,
                        height,
                        color_mode,
                    )
                    + b"\033[?2026l"
                )
                last_frame = video.copy()

                # Render overlay notification if active
                if overlay is not None:
                    overlay_data = overlay.render(width, height)
                    if overlay_data:
                        video_data += overlay_data
                    if not overlay.active:
                        last_frame = None
                        overlay = None

                # Update reporting
                data_length.append(len(video_data))
                shown_frames.append(True)
            # Ignore this video frame
            else:
                video_data = None
                data_length.append(0)
                shown_frames.append(False)

        with timing(sync_deltas):
            # Video sync
            if video_data:
                write_bytes(term, video_data)
                # Send CPR request
                if use_cpr_sync:
                    term.stream.write("\033[1;1H\033[6n")
                    term.stream.flush()
                    screen_ready = False
            # Timing sync
            increment = samples / console.TICKS_IN_FRAME
            deadline = start + increment / fps
            current = time.time()
            if current < deadline - 1e-3:
                time.sleep(deadline - current)
            # Use deadline as new reference to prevent shifting
            shifting.append(time.time() - deadline)
            start = deadline

        # Reporting
        if i % average_over == 1:
            tps = fps * console.TICKS_IN_FRAME
            emu_fps = tps * len(ticks) / sum(ticks)
            video_fps = emu_fps * sum(shown_frames) / len(shown_frames)
            total_fps = len(total_deltas) / sum(total_deltas)
            emu_percent = sum(emu_deltas) / len(emu_deltas) * total_fps * 100
            audio_percent = sum(audio_deltas) / len(audio_deltas) * total_fps * 100
            video_percent = sum(video_deltas) / len(video_deltas) * total_fps * 100
            data_rate = sum(data_length) / len(data_length) * total_fps / 1000
            bname = _BLIT_NAMES.get(blit_fn, "?")
            rom = os.path.basename(console.romfile)
            title = (
                f"{rom} {video_fps:.0f}/{emu_fps:.0f}fps {bname} "
                f"{color_mode.report()} "
                f"{emu_percent:2.0f}%emu {video_percent:2.0f}%gfx "
                f"{audio_percent:2.0f}%snd {data_rate:4.0f}KB/s"
            )
            term.stream.write(term.set_window_title(title))
            term.stream.flush()
