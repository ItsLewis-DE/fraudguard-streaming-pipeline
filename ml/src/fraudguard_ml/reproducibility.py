"""Apply deterministic seeds and CPU-thread limits before ML libraries run.

Flow:
    1. Export common BLAS/OpenMP thread-limit variables.
    2. Seed Python's standard random generator.
    3. Seed NumPy and PyTorch when those optional dependencies are installed.
    4. Return a record of which random-number generators were configured.
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import random
from typing import Any


def configure_thread_limits(max_cpu_threads: int) -> None:
    """Set common numerical-library thread limits for child computations."""

    value = str(max_cpu_threads)
    for variable in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    ):
        os.environ[variable] = value


def seed_everything(seed: int) -> dict[str, Any]:
    """Seed available random backends and report which ones were configured."""

    random.seed(seed)
    seeded: dict[str, Any] = {"python_random": True}

    if importlib.util.find_spec("numpy") is not None:
        np = importlib.import_module("numpy")
        np.random.seed(seed)
        seeded["numpy"] = True
    else:
        seeded["numpy"] = False

    return seeded
