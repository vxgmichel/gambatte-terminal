from __future__ import annotations

import time
from typing import Generator, Iterator, TYPE_CHECKING
from queue import Queue, Empty
from contextlib import contextmanager
from threading import Lock
from collections import deque

import numpy as np
import numpy.typing as npt

from .console import Console

# Late import of samplerate
if TYPE_CHECKING:
    import samplerate


class AudioOut:
    output_rate: float = 48000.0  # Hz
    buffersize: float = 0.05  # seconds
    pi_kp: float = 0.002
    pi_ki: float = 0.003
    pi_deadband: float = 0.01
    pi_i_clamp: float = 0.005

    input_rate: float
    speed: float
    resampler: samplerate.Resampler
    queue: Queue[npt.NDArray[np.int16]]
    offset: int

    def __init__(
        self, input_rate: float, resampler: samplerate.Resampler, speed: float = 1.0
    ):
        self.input_rate = input_rate
        self.speed = speed
        self.resampler = resampler
        self.queue = Queue()
        self.queued_frames = 0
        self.offset = 0
        self.lock = Lock()

        # Record last time `self.send()` was called
        self.last_send = time.perf_counter()

        # Calculate initial ratio and target frames in buffer
        self.base_ratio = self.output_rate / self.input_rate / self.speed
        self.pi_ratio = self.base_ratio
        self.pi_target = int(round(self.output_rate * self.buffersize * 2))
        self.pi_integral = 0.0
        self.pi_deque = deque[int](maxlen=3)

    def adapt_ratio(self, extra_frames: int) -> None:
        # Get consistent view of time and queued frames
        with self.lock:
            delta = time.perf_counter() - self.last_send
            queued_frames = self.queued_frames

        # Compute pending frames
        frames_predicted = int(round(delta * self.output_rate))
        pending_frames = extra_frames + queued_frames + frames_predicted

        # Average pending frames over last few calls to smooth out noise
        self.pi_deque.appendleft(pending_frames)
        pending_frames = sum(self.pi_deque) // len(self.pi_deque)

        # Compute PI correction
        error = self.pi_target - pending_frames
        normalized_error = error / self.pi_target
        if abs(normalized_error) >= self.pi_deadband:
            self.pi_integral += normalized_error
        p_term = self.pi_kp * normalized_error
        i_term = np.clip(
            self.pi_ki * self.pi_integral, -self.pi_i_clamp, self.pi_i_clamp
        )
        self.pi_integral = i_term / self.pi_ki
        correction = p_term + i_term

        # Update ratio
        self.pi_ratio = self.base_ratio * (1.0 + correction)

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
            buffersize_msec=int(round(self.buffersize * 1000)),
        )
        device.start(stream)
        with device:
            yield self

    def send(self, audio: npt.NDArray[np.int16]) -> None:
        # Resample to output rate
        data = self.resampler.process(audio, self.pi_ratio)
        # Reshape
        data = data.astype(np.int16).reshape(-1, 2)
        # Reduce volume
        data //= 4
        # Send without blocking
        with self.lock:
            self.queue.put_nowait(data)
            self.queued_frames += len(data)
            self.last_send = time.perf_counter()

    def _audio_stream(self) -> Generator[bytes, int, None]:
        # Initialize state
        extra_frames_start = 0
        buffer = np.empty((0, 2), dtype=np.int16)

        # Get first required frames
        required_frames = yield b""
        result = np.zeros((required_frames, 2), dtype=np.int16)

        # Wait until we have enough frames to fill the first request
        while self.queued_frames < 1.5 * required_frames:
            required_frames = yield result.tobytes()

        # Loop over requested frames
        while True:
            # Adapt ratio
            self.adapt_ratio(len(buffer) - extra_frames_start)

            # Initialize result buffer
            result = np.zeros((required_frames, 2), dtype=np.int16)

            # We have more frames than required, use them and update the buffer
            if len(buffer) - extra_frames_start >= required_frames:
                result[:] = buffer[
                    extra_frames_start : extra_frames_start + required_frames
                ]
                extra_frames_start += required_frames

            # We have less frames than required, use them and get more from the queue
            else:
                frames = len(buffer) - extra_frames_start
                result[:frames] = buffer[extra_frames_start:]

                # Get more frames until we have enough
                while True:
                    try:
                        with self.lock:
                            buffer = self.queue.get_nowait()
                            self.queued_frames -= len(buffer)
                    except Empty:
                        extra_frames_start = len(buffer)
                        break

                    if frames + len(buffer) >= required_frames:
                        result[frames:required_frames] = buffer[
                            : required_frames - frames
                        ]
                        extra_frames_start = required_frames - frames
                        break
                    else:
                        result[frames : frames + len(buffer)] = buffer
                        frames += len(buffer)

            # Send the result and get the next required frames
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
