from __future__ import annotations

import random
from typing import Any


def rng_from_config(mock_config: dict[str, Any]) -> random.Random:
    seed = mock_config.get("seed")
    if seed is not None:
        return random.Random(int(seed))
    return random.Random()


def pick_float(rng: random.Random, spec: Any, default: tuple[float, float]) -> float:
    if isinstance(spec, (list, tuple)) and len(spec) == 2:
        lo, hi = float(spec[0]), float(spec[1])
        if lo > hi:
            lo, hi = hi, lo
        return rng.uniform(lo, hi)
    return rng.uniform(default[0], default[1])


def pick_int(rng: random.Random, spec: Any, default: tuple[int, int]) -> int:
    return int(round(pick_float(rng, spec, (float(default[0]), float(default[1])))))
