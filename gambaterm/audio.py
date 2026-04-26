from __future__ import annotations

from typing import Generator, Iterator, TYPE_CHECKING
from contextlib import contextmanager
from collections import deque

import numpy as np
import numpy.typing as npt

from .console import Console

# Late import of samplerate
if TYPE_CHECKING:
    import samplerate


class AudioOut:
    output_rate: float = 48000.0  # Hz
    audio_delay: float = 0.100  # seconds

    # Controller configuration
    kp: float = 0.1
    ki: float = 0.001
    ma_length: int = 5
    ema_alpha: float = 0.1
    correction_clamp: float = 0.004

    input_rate: float
    speed: float
    resampler: samplerate.Resampler

    def __init__(
        self,
        input_rate: float,
        resampler: samplerate.Resampler,
        speed: float = 1.0,
    ):
        self.input_rate = input_rate
        self.resampler = resampler
        self.speed = speed
        self.nominal_sampling_ratio = self.output_rate / self.input_rate / self.speed

        # Ring buffer state
        self.ring_size = int(self.output_rate * self.audio_delay * 2)
        self.ring_buffer = np.zeros((self.ring_size, 2), dtype=np.int16)

        # We implement a SPSC (Single Producer Single Consumer) ring buffer,
        # so we do not need synchonization primitives. The contract is:
        # - only the producer (the `send` method) can incremement the write counter
        # - only the consumer (the `_audio_stream` generator) can increment the read counter
        # - the read counter can never surpass the write counter
        # - both the consumer and producer can read both counters to compute the fill level
        # Since this this fill is not protected by a lock, it represents:
        # - a maximum fill level when it's read by the producer
        # - a minimum fill level when it's read by the consumer
        self.write_counter = 0
        self.read_counter = 0

        # Controller configuration
        self.correction_min = 1 - self.correction_clamp
        self.correction_max = 1 + self.correction_clamp

        # Controller state
        self.last_buffer_levels = deque[float](maxlen=self.ma_length)
        self.moving_average = 0.5
        self.integral = 0.0
        self.sampling_ratio = self.nominal_sampling_ratio

    def adapt_sample_rate(self) -> None:
        # First perform a short moving average of the last 5 measurements
        ring_fill = self.write_counter - self.read_counter
        self.last_buffer_levels.append(ring_fill / self.ring_size)
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

    @contextmanager
    def run(self) -> Iterator[AudioOut]:
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
        with device:
            yield self

    def send(self, audio: npt.NDArray[np.int16]) -> None:
        # Resample input audio to output rate with speed adjustment
        resampled = self.resampler.process(
            audio // 4,
            self.sampling_ratio,
        ).astype(np.int16)

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
            # TODO: Implement logging
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

            # Log if we're underrunning
            if read_size < required_frames:
                # TODO: Implement logging
                pass

            # Send audio to output and get next required frames
            required_frames = yield result.tobytes()


@contextmanager
def audio_player(console: Console, speed: float = 1.0) -> Iterator[AudioOut | None]:
    # Don't play audio if speed is too low or too high
    if not 0.5 <= speed <= 2.0:
        yield None
        return

    # Late import
    import samplerate

    input_rate = console.FPS * console.TICKS_IN_FRAME
    resampler = samplerate.Resampler("linear", channels=2)
    with AudioOut(input_rate, resampler, speed).run() as audio_out:
        yield audio_out


@contextmanager
def no_audio(console: Console, speed: float = 1.0) -> Iterator[AudioOut | None]:
    yield None
