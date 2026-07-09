from __future__ import annotations

import os
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
from .graphics_scaler import AutoScaleConfig, GraphicsRenderer
from .remote_terminal import GraphicsProtocol, resolve_graphics_protocol

debug_input_fh = None
debug_input_path = os.environ.get("GAMBATERM_DEBUG_INPUT")
if debug_input_path:
    debug_input_fh = open(debug_input_path, "w")


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


def write_frame(term: Terminal, frame_data: bytes | bytearray) -> None:
    # Fix code page issue on windows:
    # `sys.stdout.buffer.raw` is a `WindowsConsoleIO` that always support UTF-8
    # regardless of the configured codepage
    if sys.platform == "win32" and term.stream.fileno() == sys.stdout.fileno():
        sys.stdout.buffer.write(frame_data)
        sys.stdout.buffer.flush()
    else:
        os.write(term.stream.fileno(), frame_data)


class StatusBar:
    """Terminal status bar: toggle, force-update, and ANSI encoding."""

    IDLE_INTERVAL = 0.25

    def __init__(self, term: Terminal, show: bool = False) -> None:
        self._term = term
        self.show = show
        self.force_update = False
        self.bar: bytes = b""
        self.needs_clear = False
        self.last_sent = 0.0

    def toggle(self) -> None:
        self.show = not self.show
        if not self.show:
            self.needs_clear = True

    def encode(self, text: str, width: int) -> bytes:
        return (
            f"\033[1;1H\033[48;2;132;94;167m\033[38;2;216;208;200m"
            f"{self._term.center(text[:width])}"
            f"\033[0m"
        ).encode()


def format_status(
    *,
    total_fps: float,
    romfile: str,
    speed: float,
    emu_fps: float,
    emu_percent: float,
    video_fps: float,
    video_percent: float,
    data_rate: float,
    audio_percent: float,
    graphics_protocol: GraphicsProtocol,
    color_mode: ColorMode,
    blitter_vis: bool,
    autoscale_scale: int | None,
    terminal_name: str,
) -> str:
    """Build the human-readable status line."""
    parts = [f" {terminal_name} " if terminal_name else " "]
    parts.append(f" {total_fps:.0f} FPS | ")
    parts.append(f"{os.path.basename(romfile)} | ")
    parts.append(
        f"Emu {speed:.2f}x {emu_fps:.0f} FPS {emu_percent:.0f}% CPU | "
    )
    parts.append(
        f"Video {video_fps:.0f} FPS {video_percent:.0f}% CPU "
        f"{data_rate:.0f} KB/s | "
    )
    parts.append(f"Audio {audio_percent:.0f}% CPU | ")
    if graphics_protocol is GraphicsProtocol.TEXT:
        parts.append(f"{color_mode.report()} textmode ")
    elif graphics_protocol is GraphicsProtocol.SIXEL:
        parts.append("sixel ")
    elif graphics_protocol is GraphicsProtocol.BLITLESS_SIXEL:
        parts.append("sixel-blitless ")
    else:
        parts.append("kitty ")
    if blitter_vis:
        parts.append("(vis) ")
    if autoscale_scale is not None:
        parts.append(f"scale{autoscale_scale}")
    return "".join(parts)


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
    autoscale_config: AutoScaleConfig | None = None,
    terminal_name: str = "",
    show_status: bool = False,
    blit_visualizer: bool = False,
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
    blitter_vis = 1 if blit_visualizer else 0

    # Graphics renderer (owns scaler, autoscale, kitty workarounds)
    renderer = GraphicsRenderer(
        term, console, autoscale_config, terminal_name, graphics_protocol,
    )

    # Status bar
    status_bar = StatusBar(term, show=show_status)

    # Guard against missing available-protocols list.
    if available_graphics_protocols is None:
        available_graphics_protocols = [GraphicsProtocol.TEXT]

    # Loop over emulator frames
    for i in count():
        # Add total deltas
        if frame_start_time is not None:
            total_deltas.append(time.perf_counter() - frame_start_time)
        frame_start_time = time.perf_counter()

        # Break when frame limit is reach
        if break_after is not None and i >= break_after:
            renderer.close()
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
            if debug_input_fh is not None:
                debug_input_fh.write(
                    f"{time.monotonic():.4f} {key.key_name or key} {key!r}\n"
                )
            if key.key_name == "CPR_RESPONSE":
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
            # debug runtime adjustment of --speed by 10%
            elif key.key_name in ("KEY_PGUP", "KEY_PGDOWN"):
                speed += 0.1 if key.key_name == "KEY_PGUP" else -0.1
                fps = console.FPS * speed
                average_over = int(round(fps))  # frames
                audio_out.update_speed(console, speed)
            elif key.key_name in ("FOCUS_IN", "FOCUS_OUT"):
                renderer.on_focus_change(graphics_protocol)
            elif key.key_name in ("KEY_GRAVE_ACCENT", "KEY_TILDE") or key in ("`", "~"):
                status_bar.toggle()
            elif key.key_name == "KEY_F12":
                blitter_vis = 0 if blitter_vis else 1
                renderer.blitter_vis = blitter_vis
            elif key.key_name == "KEY_CTRL_L" or key in ("\x0c",):
                renderer.request_keyframe()

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
                resized = (new_height, new_width) != (height, width)

                # Resolve protocol for resize
                new_graphics_protocol = resolve_graphics_protocol(
                    resized=resized,
                    current=graphics_protocol,
                    new_height=new_height,
                    new_width=new_width,
                    console_width=console.WIDTH,
                    console_height=console.HEIGHT,
                    available=available_graphics_protocols,
                    terminal_name=terminal_name,
                )

                changed = (
                    resized
                    or new_color_mode != color_mode
                    or new_graphics_protocol != graphics_protocol
                )

                clear_seq = b""
                if changed:
                    clear_seq = renderer.on_state_change(
                        old_protocol=graphics_protocol,
                        new_protocol=new_graphics_protocol,
                        old_color=color_mode,
                        new_color=new_color_mode,
                        resized=resized,
                    )
                    height, width = new_height, new_width
                    refx, refy = get_ref(width, height, console)
                    color_mode = new_color_mode
                    graphics_protocol = new_graphics_protocol
                    term.number_of_colors = new_color_mode.number_of_colors
                    last_frame.fill(0)
                    status_bar.force_update = True

                # Render frame
                if graphics_protocol is GraphicsProtocol.TEXT:
                    frame_data += clear_seq
                    frame_data += b"\033[?2026h"
                    frame_data += blit(
                        video, last_frame, refx, refy, width - 1, height, color_mode,
                        blitter_vis,
                    )
                    frame_data += b"\033[?2026l"
                else:
                    frame_data += clear_seq
                    frame_data += renderer.render(
                        video, last_frame, graphics_protocol, height, width,
                    )

                video, last_frame = last_frame, video

                # Cycle blitter vis mode 1/2 on each rendered frame
                if blitter_vis and frame_data:
                    blitter_vis = 3 - blitter_vis
                    renderer.blitter_vis = blitter_vis

                # Update reporting
                data_length.append(len(frame_data))
                shown_frames.append(True)

            # Ignore this video frame
            else:
                data_length.append(0)
                shown_frames.append(False)

        # Feed auto-scale with output bandwidth; reduce cap if too high.
        if data_length:
            data_rate_kb_s = sum(data_length) / len(data_length) * fps / 1000
            renderer.feed_bandwidth(data_rate_kb_s, height, width)

        # Pacing and synchronization
        with timing(sync_deltas):
            # Video sync
            if frame_data:
                # Send CPR request
                if use_cpr_sync:
                    frame_data += b"\033[1;1H\033[6n"
                    screen_ready = False
                # Prepend status bar when enabled
                if status_bar.show and status_bar.bar:
                    frame_data[:0] = status_bar.bar
                # Clear status bar line when just hidden
                if status_bar.needs_clear:
                    status_bar.needs_clear = False
                    frame_data[:0] = b"\033[1;1H\033[K"
                # Write the entire frame in one go to avoid fragmentation
                write_frame(term, frame_data)
                if status_bar.show:
                    status_bar.last_sent = time.monotonic()
            elif status_bar.show and status_bar.bar:
                now = time.monotonic()
                if now - status_bar.last_sent >= StatusBar.IDLE_INTERVAL:
                    write_frame(term, status_bar.bar)
                    status_bar.last_sent = now
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
        if i % average_over == 1 or status_bar.force_update:
            status_bar.force_update = False
            tps = fps * console.TICKS_IN_FRAME
            emu_fps = tps * len(ticks) / sum(ticks)
            video_fps = emu_fps * sum(shown_frames) / len(shown_frames)
            total_fps = len(total_deltas) / sum(total_deltas)

            # Feed auto-scale with video FPS; reduce cap if too slow.
            # Wait until deques have enough data for a meaningful FPS reading.
            if len(shown_frames) >= average_over // 2:
                renderer.feed_fps(video_fps, graphics_protocol, height, width)

            emu_percent = sum(emu_deltas) / len(emu_deltas) * total_fps * 100
            audio_percent = sum(audio_deltas) / len(audio_deltas) * total_fps * 100
            video_percent = sum(video_deltas) / len(video_deltas) * total_fps * 100
            data_rate = sum(data_length) / len(data_length) * total_fps / 1000

            status_bar.bar = status_bar.encode(
                format_status(
                    total_fps=total_fps,
                    romfile=str(console.romfile),
                    speed=speed,
                    emu_fps=emu_fps,
                    emu_percent=emu_percent,
                    video_fps=video_fps,
                    video_percent=video_percent,
                    data_rate=data_rate,
                    audio_percent=audio_percent,
                    graphics_protocol=graphics_protocol,
                    color_mode=color_mode,
                    blitter_vis=blitter_vis,
                    autoscale_scale=renderer.scale if renderer.has_autoscale else None,
                    terminal_name=terminal_name,
                ),
                width,
            )
