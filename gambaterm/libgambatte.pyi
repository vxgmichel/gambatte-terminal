import numpy as np
import numpy.typing as npt

class GB:
    def load(self, rom_file: str, flags: int = 0) -> int: ...
    def run_for(
        self,
        video: npt.NDArray[np.uint32],
        pitch: int,
        audio: npt.NDArray[np.int16],
        samples: int,
    ) -> tuple[int, int]: ...
    def set_input(self, value: int) -> None: ...
    def set_save_directory(self, path: str) -> None: ...
