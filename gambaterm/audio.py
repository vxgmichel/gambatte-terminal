from __future__ import annotations

import atexit
import logging
import os
from typing import Any, Generator, Iterator, TYPE_CHECKING
from contextlib import contextmanager
from collections import deque

import numpy as np
import numpy.typing as npt

from .console import Console

# Late import of samplerate
if TYPE_CHECKING:
    import miniaudio
    import samplerate

logger = logging.getLogger(__name__)


class AudioOut:
    output_rate: float = 48000.0  # Hz
    audio_volume: float = 0.25

    # Delay configuration   | In frames  | At 0.5 speed | At 1x speed | At 2x speed |
    # ----------------------|------------|--------------|-------------|-------------|
    # Emulator push         | 1 frame    | 33 ms        | 17 ms       | 8 ms        |
    # Miniaudio poll        | 1.5 frames | 50 ms        | 25 ms       | 12 ms       |
    # Expected audio delay  | 3 frames   | 100 ms       | 50 ms       | 25 ms       |
    # Ring buffer size      | 6 frames   | 200 ms       | 100 ms      | 50 ms       |
    audio_delay_in_frames: int = 3

    # Controller configuration
    kp: float = 0.1
    ki: float = 0.001
    ma_length: int = 5
    ema_alpha: float = 0.1
    correction_clamp: float = 0.004

    def __init__(
        self,
        console: Console,
        resampler: samplerate.Resampler,
        speed: float = 1.0,
    ):
        self.resampler = resampler
        input_rate = console.FPS * console.TICKS_IN_FRAME
        self.nominal_sampling_ratio = self.output_rate / input_rate / speed
        self.audio_delay = self.audio_delay_in_frames / console.FPS / speed

        # Ring buffer state
        self.ring_size = int(self.output_rate * self.audio_delay * 2)
        self.ring_buffer = np.zeros((self.ring_size, 2), dtype=np.int16)

        # We implement a SPSC (Single Producer Single Consumer) ring buffer,
        # so we do not need synchronization primitives. The contract is:
        # - only the producer (the `send` method) can increment the write counter
        # - only the consumer (the `_audio_stream` generator) can increment the read counter
        # - the read counter can never surpass the write counter
        # - both the consumer and producer can read both counters to compute the fill level
        # Since this fill is not protected by a lock, it represents:
        # - a maximum fill level when it's read by the producer
        # - a minimum fill level when it's read by the consumer
        self.write_counter = 0
        self.read_counter = 0

        # Diagnostics variables
        self._underruns = 0
        self._overruns = 0
        self._frame_num = 0
        self._csv_enabled = bool(os.environ.get("GAMBATERM_AUDIO_CSV"))
        self._diag_fill_min = 1.0
        self._diag_ratio_min = self.nominal_sampling_ratio
        self._diag_ratio_max = self.nominal_sampling_ratio
        if self._csv_enabled:
            self._diag_frames: list[dict[str, Any]] = []
            atexit.register(self._dump_csv)
        atexit.register(self._log_summary)

        # Controller configuration
        self.correction_min = 1 - self.correction_clamp
        self.correction_max = 1 + self.correction_clamp

        # Batch the variable-length emulator audio output, avoids starving the ring buffer, runFor()
        # sometimes returns partial frames!
        self._acc_buf: npt.NDArray[np.float32] = np.empty((0, 2), dtype=np.float32)

        # Controller state
        self.last_buffer_levels = deque[float](maxlen=self.ma_length)
        self.moving_average = 0.5
        self.integral = 0.0
        self.sampling_ratio = self.nominal_sampling_ratio

    def start(self) -> miniaudio.PlaybackDevice:
        # Late import
        import miniaudio

        stream = self._audio_stream()
        next(stream)
        device = miniaudio.PlaybackDevice(
            output_format=miniaudio.SampleFormat.SIGNED16,
            nchannels=2,
            sample_rate=int(self.output_rate),
            buffersize_msec=int(round(self.audio_delay / 2 * 1000)),
        )
        device.start(stream)
        return device

    def _dump_csv(self) -> None:
        if diag_csv := os.environ.get("GAMBATERM_AUDIO_CSV"):
            with open(diag_csv, "w") as fout:
                fout.write("frame,input,acc,proc,output,fill\n")
                for _df in self._diag_frames:
                    fout.write(
                        f"{_df['frame']},{_df['input']},{_df['acc']},"
                        f"{_df['proc']},{_df['output']},{_df['fill']:.4f}\n"
                    )

    def _log_summary(self) -> None:
        logger.debug(
            "Audio stats: underruns=%d overruns=%d "
            "fill_min=%.4f ratio_min=%.8f ratio_max=%.8f "
            "ratio_range=%.8f",
            self._underruns,
            self._overruns,
            self._diag_fill_min,
            self._diag_ratio_min,
            self._diag_ratio_max,
            self._diag_ratio_max - self._diag_ratio_min,
        )

    @property
    def fill_fraction(self) -> float:
        # Ring buffer fill ratio (0-1.0)
        if self.ring_size == 0:
            return 0.0
        return max(0.0, (self.write_counter - self.read_counter) / self.ring_size)

    def adapt_sample_rate(self) -> None:
        # First perform a short moving average of the last 5 measurements
        self.last_buffer_levels.append(self.fill_fraction)
        buffer_level = sum(self.last_buffer_levels) / len(self.last_buffer_levels)

        # Then perform a longer exponential moving average
        self.moving_average += self.ema_alpha * (buffer_level - self.moving_average)

        # Compute the error (the target is 50% full)
        error = 0.5 - self.moving_average

        # Compute propertional and integral contributions
        proportional = self.kp * error
        self.integral += self.ki * error

        # Compute the correction factor
        correction = 1.0 + proportional + self.integral

        # Slew / Pitch clamp: Prevent the output from shifting pitch
        correction = max(self.correction_min, min(self.correction_max, correction))

        # Anti-Windup for the integral
        self.integral = correction - 1.0 - proportional

        # Return the adjusted sample rate
        self.sampling_ratio = self.nominal_sampling_ratio * correction
        self._diag_track_ratio()

    def _diag_record_skip(self, input_len: int, acc_len: int) -> None:
        fill = self.fill_fraction
        self._diag_fill_min = min(self._diag_fill_min, fill)
        frame = self._frame_num
        self._frame_num += 1
        if self._csv_enabled:
            self._diag_frames.append(
                {
                    "frame": frame,
                    "input": input_len,
                    "acc": acc_len,
                    "proc": 0,
                    "output": 0,
                    "fill": fill,
                }
            )

    def _diag_record_process(
        self,
        input_len: int,
        acc_len: int,
        output_len: int,
    ) -> None:
        fill = self.fill_fraction
        self._diag_fill_min = min(self._diag_fill_min, fill)
        frame = self._frame_num
        self._frame_num += 1
        if self._csv_enabled:
            self._diag_frames.append(
                {
                    "frame": frame,
                    "input": input_len,
                    "acc": acc_len,
                    "proc": 1,
                    "output": output_len,
                    "fill": fill,
                }
            )

    def _diag_track_fill(self) -> None:
        self._diag_fill_min = min(self._diag_fill_min, self.fill_fraction)

    def _diag_track_ratio(self) -> None:
        self._diag_ratio_min = min(self._diag_ratio_min, self.sampling_ratio)
        self._diag_ratio_max = max(self._diag_ratio_max, self.sampling_ratio)

    def send(self, console: Console, audio: npt.NDArray[np.int16]) -> None:
        # Scale and remove DC offset
        scaled = (
            audio.astype(np.float32) * self.audio_volume
            - console.AUDIO_OFFSET * self.audio_volume
        )

        # Accumulate input to batch variable-length emulator frames into consistent chunks for the
        # resampler.  The emulator's runFor() may produce anywhere from a few hundred to tens of
        # thousands of samples per call; tiny batches could otherwise starve the ring buffer when
        # under load.
        self._acc_buf = np.concatenate([self._acc_buf, scaled])
        input_len = len(scaled)
        acc_len = len(self._acc_buf)

        # Process when we have enough to produce ~5ms of output at 48 kHz,
        # or when we have accumulated more than 3 video frames (safety valve).
        min_output = 240
        min_input = max(1, int(min_output / self.sampling_ratio))
        max_input = console.TICKS_IN_FRAME * 3
        if acc_len < min_input and acc_len < max_input:
            self._diag_record_skip(input_len, acc_len)
            return

        chunk = self._acc_buf
        self._acc_buf = np.empty((0, 2), dtype=np.float32)
        resampled = self.resampler.process(chunk, self.sampling_ratio)
        resampled = np.clip(resampled, -32768, 32767).astype(np.int16)

        # Get the ring buffer
        ring_buffer = self.ring_buffer
        ring_size = self.ring_size

        # Get the counters
        read_counter = self.read_counter
        write_counter = self.write_counter

        frames = len(resampled)
        ring_fill = write_counter - read_counter
        space = ring_size - ring_fill

        # Drop excess frames if we're overrun
        if frames > space:
            self._overruns += 1
            logger.warning(
                "Audio overrun: dropping %d of %d frames (fill=%.2f)",
                frames - space,
                frames,
                self.fill_fraction,
            )
            resampled = resampled[:space]
            frames = space

        # Write audio to ring buffer with wrap-around
        start_write_pos = write_counter % ring_size
        stop_write_pos = (start_write_pos + frames) % ring_size

        # Single write (no wrap around)
        if stop_write_pos >= start_write_pos:
            ring_buffer[start_write_pos:stop_write_pos] = resampled

        # Wrap around the ring buffer
        else:
            first_part = ring_size - start_write_pos
            ring_buffer[start_write_pos:] = resampled[:first_part]
            ring_buffer[:stop_write_pos] = resampled[
                first_part : first_part + stop_write_pos
            ]

        # Update the write counter
        self.write_counter += frames
        self._diag_record_process(input_len, acc_len, frames)

    def _audio_stream(self) -> Generator[bytes, int, None]:
        # Get the ring buffer
        ring_buffer = self.ring_buffer
        ring_size = self.ring_size

        # Get first required frames
        required_frames = yield b""
        result = np.zeros((required_frames, 2), dtype=np.int16)

        # Wait until we have enough frames to fill the first request
        while self.write_counter < self.ring_size * 0.375:
            required_frames = yield result.tobytes()

        # Loop over audio requests
        while True:
            # Adapt sample rate
            self.adapt_sample_rate()

            # Prepare output buffer
            result = np.zeros((required_frames, 2), dtype=np.int16)

            # Read the counters
            read_counter = self.read_counter
            write_counter = self.write_counter

            # Compute read position
            ring_fill = write_counter - read_counter
            read_size = min(ring_fill, required_frames)
            start_read_pos = read_counter % ring_size
            stop_read_pos = (start_read_pos + read_size) % ring_size

            # Single read (no wrap around)
            if stop_read_pos >= start_read_pos:
                result[:read_size] = ring_buffer[start_read_pos:stop_read_pos]
            # Wrap around the ring buffer
            else:
                result[: ring_size - start_read_pos] = ring_buffer[start_read_pos:]
                result[ring_size - start_read_pos : read_size] = ring_buffer[
                    :stop_read_pos
                ]

            # Update the read counter
            self.read_counter += read_size
            self._diag_track_fill()

            # Log if we're underrunning
            if read_size < required_frames:
                self._underruns += 1
                logger.warning(
                    "Audio underrun: requested %d, got %d (fill=%.2f)",
                    required_frames,
                    read_size,
                    self.fill_fraction,
                )

            # Send audio to output and get next required frames
            required_frames = yield result.tobytes()


class MaybeAudioOut:
    def __init__(self, disable_audio: bool = False):
        self.disable_audio = disable_audio
        self.audio_out: AudioOut | None = None
        self.device: miniaudio.PlaybackDevice | None = None

    def stop(self) -> None:
        if self.device is not None:
            self.device.close()
            self.device = None
        self.audio_out = None

    def update_speed(self, console: Console, speed: float) -> None:
        # Ignore if audio is disabled
        if self.disable_audio:
            return

        # Stop the current device if any
        self.stop()

        # Speed not supported, disable audio
        if not (0.499 < speed < 2.001):
            return

        # Late import
        import samplerate

        # Speed supported, enable audio
        self.audio_out = AudioOut(
            console,
            resampler=samplerate.Resampler("linear", channels=2),
            speed=speed,
        )
        self.device = self.audio_out.start()

    def send(self, console: Console, audio: npt.NDArray[np.int16]) -> None:
        if self.audio_out is not None:
            self.audio_out.send(console, audio)


@contextmanager
def audio_player(
    console: Console, speed: float = 1.0, disable_audio: bool = False
) -> Iterator[MaybeAudioOut]:
    maybe_audio_out = MaybeAudioOut(disable_audio=disable_audio)
    maybe_audio_out.update_speed(console, speed)
    try:
        yield maybe_audio_out
    finally:
        maybe_audio_out.stop()


DISABLED_AUDIO_OUT = MaybeAudioOut(disable_audio=True)
