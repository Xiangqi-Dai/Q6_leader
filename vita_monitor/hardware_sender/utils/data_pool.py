from __future__ import annotations

import multiprocessing as mp
from typing import Any


def create_info_pool(*, maxsize: int) -> mp.Queue[Any]:
    if maxsize <= 0:
        raise ValueError("info_pool maxsize must be > 0")
    return mp.Queue(maxsize=maxsize)
