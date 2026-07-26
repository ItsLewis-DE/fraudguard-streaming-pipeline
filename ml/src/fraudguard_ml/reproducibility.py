from __future__ import annotations

import importlib
import importlib.util
import os
import random
from typing import Any


def configure_thread_limits(max_cpu_threads: int) -> None:
    value = str(max_cpu_threads)
    for variable in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    ):
        os.environ[variable] = value


def seed_everything(seed: int) -> dict[str, Any]:
    random.seed(seed)
    seeded: dict[str, Any] = {"python_random": True}

    if importlib.util.find_spec("numpy") is not None:
        np = importlib.import_module("numpy")
        np.random.seed(seed)
        seeded["numpy"] = True
    else:
        seeded["numpy"] = False

    if importlib.util.find_spec("torch") is not None:
        torch = importlib.import_module("torch")
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
        seeded["torch"] = True
    else:
        seeded["torch"] = False

    return seeded
