from typing import Optional

import numpy as np
import numpy.typing as npt

def blit(
    image: npt.NDArray[np.uint32],
    last: Optional[npt.NDArray[np.uint32]],
    refx: int,
    refy: int,
    width: int,
    height: int,
    color_mode: int,
) -> bytes: ...
