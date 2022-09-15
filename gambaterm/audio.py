from queue import Queue, Empty, Full
from contextlib import contextmanager

import numpy as np


class AudioOut:

    output_rate = 48000
    buffer_size = output_rate // 60

    def __init__(self, input_rate, resampler, speed=1.0):
        self.input_rate = input_rate
        self.speed = speed
        self.resampler = resampler
        self.queue = Queue(maxsize=6)  # 100 ms delay
        self.buffer = np.full((self.buffer_size, 2), 0.0, np.int16)
        self.offset = 0

    @property
    def ratio(self):
        return self.output_rate / self.input_rate / self.speed

    def send(self, audio):
        # Resample to output rate
        data = self.resampler.process(audio, self.ratio).astype(np.int16)
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

    def stream_callback(self, output_buffer, *args):
        try:
            output_buffer[:] = self.queue.get_nowait()
        except Empty:
            output_buffer.fill(0)


@contextmanager
def audio_player(console, speed_factor=1.0):
    # Perform late imports
    # Those can fail if a linux machine doesn't have portaudio or libsamplerate
    # installed
    import samplerate  # type: ignore
    import sounddevice  # type: ignore

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
def no_audio(console, speed_factor=1.0):
    yield None
