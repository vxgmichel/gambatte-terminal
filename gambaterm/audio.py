from __future__ import annotations

from typing import Iterator, TYPE_CHECKING
from queue import Queue, Empty, Full
from contextlib import contextmanager

import numpy as np
import numpy.typing as npt

from .console import Console

# Late import of samplerate
if TYPE_CHECKING:
    import samplerate


class AudioOut:
    output_rate: float = 48000.0
    buffer_size: int = int(output_rate // 60)

    input_rate: float
    speed: float
    resampler: samplerate.Resampler
    queue: Queue[npt.NDArray[np.int16]]
    buffer: npt.NDArray[np.int16]
    offset: int

    def __init__(
        self, input_rate: float, resampler: samplerate.Resampler, speed: float = 1.0
    ):
        self.input_rate = input_rate
        self.speed = speed
        self.resampler = resampler
        self.queue = Queue(maxsize=6)  # 100 ms delay
        self.buffer = np.full((self.buffer_size, 2), 0.0, np.int16)
        self.offset = 0

    @property
    def ratio(self) -> float:
        return self.output_rate / self.input_rate / self.speed

    def send(self, audio: npt.NDArray[np.int16]) -> None:
        # Resample to output rate
        data = self.resampler.process(audio, self.ratio)
        # Loop over data blocks
        while True:
            # Write the current buffer
            stop = min(self.buffer_size, self.offset + len(data))
            self.buffer[self.offset : stop] = data[: stop - self.offset]
            # Current buffer is not complete
            if stop != self.buffer_size:
                self.offset = stop
                return
            # Current buffer is complete, decrease volume
            self.buffer //= 4
            # Send without blocking if possible
            try:
                self.queue.put_nowait(self.buffer)
            # Synchronization issue, let it regulate itself
            except Full:
                pass
            # Create new buffer
            self.buffer = np.full((self.buffer_size, 2), 0.0, np.int16)
            # Process remaining data
            data = data[stop - self.offset :]
            self.offset = 0

    def stream_callback(self, output_buffer: npt.NDArray[np.int16], *_: object) -> None:
        try:
            output_buffer[:] = self.queue.get_nowait()
        except Empty:
            output_buffer.fill(0)


@contextmanager
def audio_player(
    console: Console, speed_factor: float = 1.0
) -> Iterator[AudioOut | None]:
    # Perform late imports
    # Those can fail if a linux machine doesn't have portaudio or libsamplerate
    # installed
    import samplerate
    import sounddevice

    input_rate = console.FPS * console.TICKS_IN_FRAME
    resampler = samplerate.Resampler("linear", channels=2)
    audio_out = AudioOut(input_rate, resampler, speed_factor)
    with sounddevice.OutputStream(
        samplerate=audio_out.output_rate,
        dtype="int16",
        channels=2,
        latency="low",
        blocksize=audio_out.buffer_size,
        callback=audio_out.stream_callback,
    ):
        yield audio_out


@contextmanager
def no_audio(console: Console, speed_factor: float = 1.0) -> Iterator[AudioOut | None]:
    yield None
