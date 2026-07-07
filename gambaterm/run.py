from __future__ import annotations

import os
import re
import sys
import time
import contextlib
from itertools import count
from collections import deque
from typing import Deque, Iterator

import numpy as np
from blessed import Terminal

from .termblit import blit
from .audio import MaybeAudioOut, DISABLED_AUDIO_OUT
from .console import Console
from .input_getter import BaseInputGetter
from .colors import ColorMode
from .graphics_scaler import GraphicsScaler, AutoScale, AutoScaleConfig, _SCALE_CEILING
from .remote_terminal import GraphicsProtocol

@contextlib.contextmanager
def timing(deltas: Deque[float]) -> Iterator[None]:
    start = time.perf_counter()
    try:
        yield
    finally:
        deltas.append(time.perf_counter() - start)


def get_ref(width: int, height: int, console: Console) -> tuple[int, int]:
    refx = 2 + max(0, (height - console.HEIGHT // 2) // 2)
    refy = 3 + max(0, (width - console.WIDTH) // 2)
    return refx, refy


# Terminals with corrupted unicode font rendering — always prefer graphics.
_BAD_TEXT = ("rio", "mlterm")
# Terminals needing full frames every frame (no dirty-rect / overlay deltas).
_FORCE_KITTY_BLITLESS = ("rio", "ghostty")


def _is_mlterm(term: Terminal) -> bool:
    """Return True if the terminal is mlterm (loses sixel on focus-out)."""
    try:
        sv = term.get_software_version(timeout=0.25)
        return sv is not None and "mlterm" in sv.name.lower()
    except Exception:
        return False


def write_frame(term: Terminal, frame_data: bytes) -> None:
    # Fix code page issue on windows:
    # `sys.stdout.buffer.raw` is a `WindowsConsoleIO` that always support UTF-8
    # regardless of the configured codepage
    if sys.platform == "win32" and term.stream.fileno() == sys.stdout.fileno():
        sys.stdout.buffer.write(frame_data)
        sys.stdout.buffer.flush()
    else:
        os.write(term.stream.fileno(), frame_data)


def run(
    console: Console,
    input_getter: BaseInputGetter,
    term: Terminal,
    audio_out: MaybeAudioOut = DISABLED_AUDIO_OUT,
    frame_advance: int = 1,
    color_mode: ColorMode = ColorMode.HAS_24_BIT_COLOR,
    break_after: int | None = None,
    speed: float = 1.0,
    use_cpr_sync: bool = False,
    graphics_protocol: GraphicsProtocol = GraphicsProtocol.TEXT,
    available_graphics_protocols: list[GraphicsProtocol] | None = None,
    autoscale: AutoScaleConfig | None = None,
    terminal_name: str = "",
    show_status: bool = False,
) -> None:
    assert color_mode > 0

    # Prepare buffers with invalid data
    video = np.full((console.HEIGHT, console.WIDTH), 0, np.uint32)
    audio = np.full((2 * console.TICKS_IN_FRAME, 2), 0, np.int16)
    # Force first diff: 0x00000000 has alpha=0 which never matches
    # real GB pixels (alpha always 0xFF).
    last_frame = np.full((console.HEIGHT, console.WIDTH), 0x00000000, np.uint32)

    # Print area (default to 24x80 if terminal reports zero)
    height = term.height or 24
    width = term.width or 80
    refx, refy = get_ref(width, height, console)

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

    # Prepare state
    new_frame = False
    screen_ready = True
    frame_start_time = None
    frame_data = bytearray()
    status_bar = b""
    scaler: GraphicsScaler | None = None
    force_clear = False
    show_status_bar = show_status
    force_status_update = False
    first_frame = True
    kitty_pending_delete = False
    auto_scale: AutoScale | None = (
        AutoScale(_SCALE_CEILING, autoscale.seconds)
        if autoscale is not None and autoscale.enabled
        and graphics_protocol is not GraphicsProtocol.TEXT
        else None
    )

    # Build cycle list from available protocols (detected before entering run).
    if available_graphics_protocols is None:
        available_graphics_protocols = [GraphicsProtocol.TEXT]
    graphics_cycle = available_graphics_protocols

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
            audio_out.send(console, audio[:samples, :])

        # Read keys for ctrl-c, ctrl-d, and CPR response.
        # If the kitty keyboard protocol is used, all inputs are sent as CSI sequences
        # (e.g. `\x1b[99;5u` rather than raw `\x03`), so we check blessed's
        # decoded `key_name` attribute, since it ends up being `KEY_CTRL_C` for ctrl+c
        # and `KEY_CTRL_D` for ctrl+d regardless of the underlying encoding.
        new_color_mode = color_mode
        new_graphics_protocol = graphics_protocol
        for key in input_getter.pop_keystrokes():
            if key.key_name == 'CPR_RESPONSE':
                screen_ready = True
            elif key.key_name == "KEY_CTRL_C":
                raise KeyboardInterrupt
            elif key.key_name == "KEY_CTRL_D":
                raise EOFError
            # debug text color modes
            elif key.key_name in ("KEY_TAB", "KEY_SHIFT_TAB"):
                if key.key_name.startswith("KEY_SHIFT"):
                    new_color_mode = color_mode.cycle_back()
                else:
                    new_color_mode = color_mode.cycle()
            # debug available graphics renders
            elif key.key_name and ("BACKSPACE" in key.key_name or "DELETE" in key.key_name):
                step = -1 if key.key_name.startswith("KEY_SHIFT") else 1
                cycle = [
                    p for p in graphics_cycle
                    if p is not GraphicsProtocol.TEXT or terminal_name not in _BAD_TEXT
                ]
                if cycle:
                    idx = cycle.index(graphics_protocol)
                    new_graphics_protocol = cycle[(idx + step) % len(cycle)]
            # debug runtime adjustment of --speed by 10%
            elif key.key_name in ("KEY_PGUP", "KEY_PGDOWN"):
                speed += 0.1 if key.key_name == "KEY_PGUP" else -0.1
                fps = console.FPS * speed
                average_over = int(round(fps))  # frames
                audio_out.update_speed(console, speed)
            elif key.key_name in ('FOCUS_IN', 'FOCUS_OUT'):
                if graphics_protocol is GraphicsProtocol.SIXEL and _is_mlterm(term):
                    if scaler is not None:
                        scaler._sixel_baseline = None
            elif key.key_name in ("KEY_GRAVE_ACCENT", "KEY_TILDE") or key in ("`", "~"):
                show_status_bar = not show_status_bar

        # Render video
        with timing(video_deltas):
            # Re-use the same buffer to accumulate frame data and avoid unnecessary allocations.
            frame_data.clear()

            # Detect if a shift is currently happening
            shift = shifting and shifting[-1] > 1 / fps

            # Render a new frame only if:
            # - it is the right time according to frame_advance
            # - a new frame is available from the emulator
            # - the screen is ready for a new frame (either CPR sync is disabled, or enabled and we received the CPR response)
            # - we are not currently shifting (to prevent flooding the terminal with new frames when the rendering is too slow)
            if i % frame_advance == 0 and new_frame and screen_ready and not shift:
                new_frame = False

                # Detect terminal resize, color mode, or graphics protocol change
                new_height = term.height or 24
                new_width = term.width or 80
                maybe_clear_sequence = b""
                resized = (new_height, new_width) != (height, width)
                changed = (
                    resized
                    or new_color_mode != color_mode
                    or new_graphics_protocol != graphics_protocol
                )
                if first_frame:
                    first_frame = False
                    if (new_width >= console.WIDTH
                            and new_height >= console.HEIGHT // 2
                            and not terminal_name.startswith(("rio", "mlterm"))):
                        new_graphics_protocol = GraphicsProtocol.TEXT
                        changed = True
                if changed:
                    if resized:
                        text_fits = (
                            new_width >= console.WIDTH
                            and new_height >= console.HEIGHT // 2
                        )
                        if (text_fits and graphics_protocol is not GraphicsProtocol.TEXT
                                and terminal_name not in _BAD_TEXT):
                            new_graphics_protocol = GraphicsProtocol.TEXT
                        elif not text_fits and graphics_protocol is GraphicsProtocol.TEXT:
                            for gp in reversed(graphics_cycle):
                                if gp is not GraphicsProtocol.TEXT:
                                    new_graphics_protocol = gp
                                    break
                    if new_graphics_protocol is GraphicsProtocol.TEXT:
                        auto_scale = None
                    elif auto_scale is None and autoscale is not None and autoscale.enabled:
                        auto_scale = AutoScale(_SCALE_CEILING, autoscale.seconds)
                    elif auto_scale is not None:
                        auto_scale.reset()
                    maybe_clear_sequence = b""
                    if (new_graphics_protocol != graphics_protocol
                            or new_color_mode != color_mode
                            or (resized and new_graphics_protocol is GraphicsProtocol.TEXT)):
                        maybe_clear_sequence = b"\033[H\033[2J"
                    if graphics_protocol is GraphicsProtocol.KITTY:
                        if terminal_name == "ghostty":
                            maybe_clear_sequence = (
                                b"\033_Ga=d,d=i,i=1\033\\"
                                b"\033_Ga=d,d=i,i=2\033\\"
                                + maybe_clear_sequence
                            )
                        else:
                            maybe_clear_sequence = (
                                b"\033_Ga=d,d=a\033\\" + maybe_clear_sequence
                            )
                    height, width = new_height, new_width
                    refx, refy = get_ref(width, height, console)
                    color_mode = new_color_mode
                    graphics_protocol = new_graphics_protocol
                    term.number_of_colors = new_color_mode.number_of_colors
                    last_frame.fill(0)
                    scaler = None
                    force_status_update = True

                # Render frame
                if graphics_protocol is GraphicsProtocol.TEXT:
                    frame_data += b"\033[?2026h"
                    frame_data += maybe_clear_sequence
                    frame_data += blit(
                        video, last_frame, refx, refy, width - 1, height, color_mode
                    )
                    frame_data += b"\033[?2026l"
                else:
                    sync_start = b""
                    sync_end = b""
                    if kitty_pending_delete:
                        sync_start = b"\033[?2026h"
                        frame_data[:0] = (
                            b"\033_Ga=d,d=i,i=1\033\\"
                            b"\033_Ga=d,d=i,i=2\033\\"
                        )
                        sync_end = b"\033[?2026l"
                        kitty_pending_delete = False
                    if scaler is None:
                        scaler = GraphicsScaler.recompute(
                            term, console, height, width, auto_scale,
                            terminal_name=terminal_name,
                        )
                        maybe_clear_sequence = b"\033[H\033[2J"
                    if force_clear and graphics_protocol in (
                        GraphicsProtocol.SIXEL, GraphicsProtocol.BLITLESS_SIXEL
                    ):
                        maybe_clear_sequence = b"\033[H\033[2J"
                    force_clear = False
                    frame_data += maybe_clear_sequence
                    if graphics_protocol is GraphicsProtocol.SIXEL:
                        frame_data += scaler.blit_sixel(
                            video, last_frame, width, height
                        )
                    elif graphics_protocol is GraphicsProtocol.BLITLESS_SIXEL:
                        frame_data += scaler.blit_sixel_blitless(
                            video, width, height
                        )
                    else:
                        frame_data += scaler.blit_kitty(
                            video, last_frame, width, height, color_mode
                        )
                        if terminal_name in _FORCE_KITTY_BLITLESS:
                            scaler._baseline = None
                    if sync_end:
                        frame_data += sync_end

                video, last_frame = last_frame, video

                # Update reporting
                data_length.append(len(frame_data))
                shown_frames.append(True)

            # Ignore this video frame
            else:
                data_length.append(0)
                shown_frames.append(False)

        # Feed auto-scale with output bandwidth; reduce cap if too high.
        if data_length and auto_scale is not None and autoscale is not None:
            data_rate_kb_s = sum(data_length) / len(data_length) * fps / 1000
            if auto_scale.feed_bandwidth(data_rate_kb_s, autoscale.bandwidth_mbits):
                scaler = GraphicsScaler.recompute(
                    term, console, height, width, auto_scale,
                )
                force_clear = True

        # Pacing and synchronization
        with timing(sync_deltas):
            # Video sync
            if frame_data:
                # Send CPR request
                if use_cpr_sync:
                    frame_data += b"\033[1;1H\033[6n"
                    screen_ready = False
                # Prepend status bar when enabled
                if show_status_bar and status_bar:
                    frame_data[:0] = status_bar
                # Write the entire frame in one go to avoid fragmentation
                write_frame(term, frame_data)
            # Timing sync
            increment = samples / console.TICKS_IN_FRAME
            deadline = start + increment / fps
            current = time.time()
            if current < deadline - 1e-3:
                time.sleep(deadline - current)
            # Use deadline as new reference to prevent shifting
            shifting.append(time.time() - deadline)
            start = deadline

        # Prepare status bar for the next frame
        if i % average_over == 1 or force_status_update:
            force_status_update = False
            tps = fps * console.TICKS_IN_FRAME
            emu_fps = tps * len(ticks) / sum(ticks)
            video_fps = emu_fps * sum(shown_frames) / len(shown_frames)
            total_fps = len(total_deltas) / sum(total_deltas)

            # Feed auto-scale with video FPS; reduce cap if too slow.
            # Wait until deques have enough data for a meaningful FPS reading.
            if auto_scale is not None and autoscale is not None and len(shown_frames) >= average_over // 2:
                if auto_scale.feed_fps(video_fps, autoscale.fps):
                    if (terminal_name == "ghostty"
                            and graphics_protocol is GraphicsProtocol.KITTY):
                        kitty_pending_delete = True
                    scaler = GraphicsScaler.recompute(
                        term, console, height, width, auto_scale,
                    )
                    if graphics_protocol is not GraphicsProtocol.KITTY:
                        force_clear = True

            emu_percent = sum(emu_deltas) / len(emu_deltas) * total_fps * 100
            audio_percent = sum(audio_deltas) / len(audio_deltas) * total_fps * 100
            video_percent = sum(video_deltas) / len(video_deltas) * total_fps * 100
            data_rate = sum(data_length) / len(data_length) * total_fps / 1000
            status = f" {terminal_name} " if terminal_name else " "
            status += f" {total_fps:.0f} FPS | "
            status += f"{os.path.basename(console.romfile)} | "
            status += (
                f"Emu {speed:.2f}x {emu_fps:.0f} FPS {emu_percent:.0f}% CPU | "
            )
            status += f"Video {video_fps:.0f} FPS {video_percent:.0f}% CPU "
            status += f"{data_rate:.0f} KB/s | "
            status += f"Audio {audio_percent:.0f}% CPU | "
            if graphics_protocol is GraphicsProtocol.TEXT:
                status += f"{color_mode.report()} textmode "
            elif graphics_protocol is GraphicsProtocol.SIXEL:
                status += "sixel "
            elif graphics_protocol is GraphicsProtocol.BLITLESS_SIXEL:
                status += "sixel-blitless "
            else:
                status += "kitty "
            if auto_scale is not None:
                status += f"scale{scaler.scale if scaler else '?'}"
            status_bar = (
                f"\033[1;1H\033[48;2;132;94;167m\033[38;2;216;208;200m"
                f"{term.center(status[:width])}"
                f"\033[0m"
            ).encode()
