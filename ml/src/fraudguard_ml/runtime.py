"""Collect reproducibility-relevant CPU, memory, Python, and GPU metadata.

Flow:
    1. Measure logical and container-available CPUs plus host memory.
    4. Return an immutable metadata record for logs and artifacts.

Optional GPU discovery never makes CPU-only runs fail because of a broken or
partially installed CUDA stack.
"""

from __future__ import annotations

import os
import platform
import sys

import psutil
from pydantic import BaseModel, ConfigDict

from fraudguard_ml.config import RuntimeConfig


class RuntimeMetadata(BaseModel):
    """Environment facts needed to explain and reproduce an ML run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    random_seed: int
    python_version: str
    platform: str
    cpu_logical_count: int #tổng số luồng cpu của máy chủ
    cpu_available_count: int #số lượng cpi được cấp phép cho tiến trình hiện tại
    cpu_thread_limit: int
    host_memory_total_bytes: int
    host_memory_available_bytes: int
    configured_memory_limit_bytes: int


def _available_cpu_count() -> int:
    """Return CPUs available to this process, respecting affinity constraints."""

    if hasattr(os, "sched_getaffinity"):
        try:
            return max(1, len(os.sched_getaffinity(0)))
        except OSError:
            # Affinity may be unsupported by the current kernel/container.
            pass
    return os.cpu_count() or 1

"""
Khi sử dụng hàm này giúp cho việc đảm bảo tính tái lập.
Nếu chạy ra kết quả khác nhau giữa 2 máy thì dựa vào đây
ta có thể biết được là do đâu
"""
def collect_runtime_metadata(config: RuntimeConfig) -> RuntimeMetadata:
    """Collect runtime facts and enforce the configured GPU requirement."""

    memory = psutil.virtual_memory()

    return RuntimeMetadata(
        random_seed=config.random_seed,
        python_version=sys.version,
        platform=platform.platform(),
        cpu_logical_count=os.cpu_count() or 1,
        cpu_available_count=_available_cpu_count(),
        cpu_thread_limit=config.max_cpu_threads,
        host_memory_total_bytes=int(memory.total),
        host_memory_available_bytes=int(memory.available),
        configured_memory_limit_bytes=int(config.memory_limit_gib * 1024**3),
    )
    