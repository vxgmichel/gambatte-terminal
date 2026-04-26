from __future__ import annotations

from typing import Generator, Iterator, TYPE_CHECKING
from queue import Queue, Empty, Full
from contextlib import contextmanager

import numpy as np
import numpy.typing as npt

from .console import Console

# Late import of samplerate
if TYPE_CHECKING:
    import samplerate


class AudioOut:
    output_rate: float = 48000.0  # Hz
    buffersize: float = 0.05  # seconds

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
        self.queue = Queue(maxsize=100)
        self.offset = 0

    @property
    def ratio(self) -> float:
        return self.output_rate / self.input_rate / self.speed

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
        try:
            yield self
        finally:
            device.stop()

    def send(self, audio: npt.NDArray[np.int16]) -> None:
        # Resample to output rate
        data = self.resampler.process(audio, self.ratio)
        # Reshape
        data = data.astype(np.int16).reshape(-1, 2)
        # Reduce volume
        data //= 4
        # Send without blocking if possible
        try:
            self.queue.put_nowait(data)
        # Synchronization issue, let it regulate itself
        except Full:
            pass

    def _audio_stream(self) -> Generator[bytes, int, None]:
        # Get first required frames
        extra_frames_start = 0
        buffer = np.empty((0, 2), dtype=np.int16)
        required_frames = yield b""

        # Loop over requested frames
        while True:
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
                        buffer = self.queue.get_nowait()
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
