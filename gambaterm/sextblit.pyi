import numpy as np
import numpy.typing as npt

def clear_cache() -> None: ...
def set_hysteresis(value: int) -> None: ...
def get_hysteresis() -> int: ...
def blit_sextant_streched(
    image: npt.NDArray[np.uint32],
    last: npt.NDArray[np.uint32] | None,
    refx: int,
    refy: int,
    width: int,
    height: int,
    color_mode: int,
) -> bytes: ...
def blit_sextant_compressed(
    image: npt.NDArray[np.uint32],
    last: npt.NDArray[np.uint32] | None,
    refx: int,
    refy: int,
    width: int,
    height: int,
    color_mode: int,
) -> bytes: ...
