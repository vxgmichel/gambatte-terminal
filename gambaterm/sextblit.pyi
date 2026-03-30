import numpy as np
import numpy.typing as npt

def init_table(table_bytes: list[bytes]) -> None: ...
def clear_cache() -> None: ...
def blit_sextant(
    image: npt.NDArray[np.uint32],
    last: npt.NDArray[np.uint32] | None,
    refx: int,
    refy: int,
    width: int,
    height: int,
    color_mode: int,
) -> bytes: ...
