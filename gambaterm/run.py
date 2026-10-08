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
from .graphics_scaler import GraphicsRenderer
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


class FrameEmitter:
    """Writes frame data to terminal with CPR, status bar, and tracking.

    Owns the mutable per-frame state (pending_cpr, blitter_vis) that was
    previously scattered across run() locals.
    """

    CPR_SEQ = b"\033[1;1H\033[6n"
    CLEAR_SEQ = b"\033[1;1H\033[K"

    def __init__(
        self,
        term: Terminal,
        status_bar: StatusBar,
        renderer: "GraphicsRenderer",
        cpr_sync_window: int,
        blitter_vis: int,
    ) -> None:
        self._term = term
        self._status_bar = status_bar
        self._renderer = renderer
        self._cpr_sync_window = cpr_sync_window
        self.pending_cpr = 0
        self.blitter_vis = blitter_vis

    @property
    def cpr_ready(self) -> bool:
        return not self._cpr_sync_window or self.pending_cpr < self._cpr_sync_window

    def on_cpr_response(self) -> None:
        self.pending_cpr = max(0, self.pending_cpr - 1)

    def emit(
        self,
        frame_data: bytearray,
        data_length: "deque[int]",
        shown_frames: "deque[int]",
    ) -> bytearray:
        """Write *frame_data* and return a fresh empty bytearray."""
        if self._cpr_sync_window:
            frame_data += self.CPR_SEQ
            self.pending_cpr += 1
        if self._status_bar.show and self._status_bar.bar:
            frame_data[:0] = self._status_bar.bar
        if self._status_bar.needs_clear:
            self._status_bar.needs_clear = False
            frame_data[:0] = self.CLEAR_SEQ
        if self.blitter_vis:
            self.blitter_vis = 3 - self.blitter_vis
            self._renderer.blitter_vis = self.blitter_vis
        write_frame(self._term, frame_data)
        if self._status_bar.show:
            self._status_bar.last_sent = time.monotonic()
        data_length.append(len(frame_data))
        shown_frames.append(True)
        return bytearray()


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
    dropped_frames: int,
    graphics_protocol: GraphicsProtocol,
    color_mode: ColorMode,
    blitter_vis: bool,
    terminal_name: str,
    graphics_scale: int = 0,
    audio_buffer: float = 0.0,
) -> str:
    """Build the human-readable status line."""
    parts = [f" {terminal_name} " if terminal_name else " "]
    parts.append(f" {total_fps:.0f} FPS | ")
    parts.append(f"{os.path.basename(romfile)} | ")
    parts.append(
        f"Emu {speed:.2f}x {emu_fps:.0f} FPS {emu_percent:.0f}% CPU | "
    )
    maybe_dropped = f"-{dropped_frames}! " if dropped_frames else ""
    parts.append(
        f"Video {video_fps:.0f}{maybe_dropped}FPS {video_percent:.0f}% CPU "
        f"{data_rate:.0f} KB/s | "
    )
    parts.append(f"Audio {audio_percent:.0f}% CPU b:{audio_buffer*100:.0f}% | ")
    if graphics_protocol is GraphicsProtocol.TEXT:
        parts.append(f"{color_mode.report()} textmode ")
    elif graphics_protocol is GraphicsProtocol.SIXEL:
        parts.append(f"sixel{graphics_scale}x " if graphics_scale else "sixel ")
    elif graphics_protocol is GraphicsProtocol.BLITLESS_SIXEL:
        parts.append(f"sixel-blitless{graphics_scale}x " if graphics_scale else "sixel-blitless ")
    else:
        parts.append(f"kitty{graphics_scale}x " if graphics_scale else "kitty ")
    if blitter_vis:
        parts.append("(vis) ")
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
    use_cpr_sync: int = 0,
    graphics_protocol: GraphicsProtocol = GraphicsProtocol.TEXT,
    available_graphics_protocols: list[GraphicsProtocol] | None = None,
    terminal_name: str = "",
    force_transparent_offset: bool = False,
    show_status: bool = False,
    blit_visualizer: bool = False,
    frame_banding: bool = False,
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

    # TODO: these two sections are better extracted to some external class & obj ?

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
    buffer_levels: Deque[float] = deque(maxlen=average_over)
    start = time.time()

    # Prepare state
    new_frame = False
    frame_start_time = None
    frame_data = bytearray()

    # Graphics renderer
    renderer = GraphicsRenderer(
        term, console, terminal_name, graphics_protocol,
        force_transparent_offset=force_transparent_offset,
        frame_banding=frame_banding,
    )

    # Status bar
    status_bar = StatusBar(term, show=show_status)

    # Frame emitter: owns CPR sync state, blitter visualizer toggle, and output
    frame_emitter = FrameEmitter(
        term, status_bar, renderer,
        cpr_sync_window=use_cpr_sync,
        blitter_vis=1 if blit_visualizer else 0,
    )

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
            buffer_levels.append(audio_out.fill_fraction)

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
                frame_emitter.on_cpr_response()
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
                frame_emitter.blitter_vis = 0 if frame_emitter.blitter_vis else 1
                renderer.blitter_vis = frame_emitter.blitter_vis
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
            if (
                i % frame_advance == 0
                and new_frame
                and frame_emitter.cpr_ready
                and not shift
            ):
                new_frame = False
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
                    if clear_seq:
                        frame_data += clear_seq
                    frame_data += b"\033[?2026h"
                    frame_data += blit(
                        video, last_frame, refx, refy, width - 1, height, color_mode,
                        frame_emitter.blitter_vis,
                    )
                    frame_data += b"\033[?2026l"
                    frame_data = frame_emitter.emit(
                        frame_data, data_length, shown_frames,
                    )
                else:
                    if clear_seq:
                        frame_data += clear_seq
                    render_result = renderer.render(
                        video, last_frame,
                        graphics_protocol, height, width,
                    )
                    frame_data += render_result
                    frame_data = frame_emitter.emit(
                        frame_data, data_length, shown_frames,
                    )

                video, last_frame = last_frame, video

            # Ignore this video frame
            else:
                data_length.append(0)
                shown_frames.append(False)

        # Pacing and synchronization
        with timing(sync_deltas):
            # Idle status bar heartbeat
            if status_bar.show and status_bar.bar and not frame_data:
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
            emu_fps = tps * len(ticks) / sum(ticks) if ticks else 0
            if shown_frames:
                video_fps = emu_fps * sum(shown_frames) / len(shown_frames)
            else:
                video_fps = 0
            total_fps = len(total_deltas) / sum(total_deltas) if total_deltas else 0

            emu_percent = sum(emu_deltas) / len(emu_deltas) * total_fps * 100 if emu_deltas else 0
            audio_percent = sum(audio_deltas) / len(audio_deltas) * total_fps * 100 if audio_deltas else 0
            video_percent = sum(video_deltas) / len(video_deltas) * total_fps * 100 if video_deltas else 0
            data_rate = sum(data_length) / len(data_length) * total_fps / 1000 if data_length else 0
            dropped_frames = len(shown_frames) - sum(shown_frames)
            worst_buffer = min(buffer_levels) if buffer_levels else 1.0

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
                    dropped_frames=dropped_frames,
                    graphics_protocol=graphics_protocol,
                    color_mode=color_mode,
                    blitter_vis=frame_emitter.blitter_vis,
                    terminal_name=terminal_name,
                    graphics_scale=(
                        renderer.kitty_scale
                        if graphics_protocol is GraphicsProtocol.KITTY
                        else renderer.scale
                    ) or 0,
                    audio_buffer=worst_buffer,
                ),
                width,
            )
