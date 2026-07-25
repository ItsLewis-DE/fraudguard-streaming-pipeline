from __future__ import annotations

import importlib
import os
import platform
import sys
from typing import Any

import psutil
from pydantic import BaseModel, ConfigDict

from fraudguard_ml.config import RuntimeConfig


class GpuDevice(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    index: int
    name: str
    memory_total_bytes: int | None


class RuntimeMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    random_seed: int
    python_version: str
    platform: str
    cpu_logical_count: int
    cpu_available_count: int
    cpu_thread_limit: int
    host_memory_total_bytes: int
    host_memory_available_bytes: int
    configured_memory_limit_bytes: int
    gpu_available: bool
    gpu_backend: str | None
    gpu_devices: tuple[GpuDevice, ...]


class GpuRequiredError(RuntimeError):
    """Raised when a run requires GPU but no usable CUDA backend is available."""


def _available_cpu_count() -> int:
    if hasattr(os, "sched_getaffinity"):
        try:
            return max(1, len(os.sched_getaffinity(0)))
        except OSError:
            # Affinity may be unsupported by the current kernel/container.
            pass
    return os.cpu_count() or 1


def _load_torch() -> Any | None:
    try:
        return importlib.import_module("torch")
    except (ImportError, OSError):
        # An optional probe must tolerate missing or broken native dependencies.
        return None


def _detect_torch_cuda() -> tuple[bool, str | None, tuple[GpuDevice, ...]]:
    torch = _load_torch()
    if torch is None:
        return False, None, ()

    try:
        cuda = torch.cuda
        if not cuda.is_available():
            return False, None, ()

        devices = tuple(
            GpuDevice(
                index=index,
                name=str(cuda.get_device_name(index)),
                memory_total_bytes=int(cuda.get_device_properties(index).total_memory),
            )
            for index in range(cuda.device_count())
        )
    except (AssertionError, AttributeError, RuntimeError, OSError):
        # A partially installed or incompatible CUDA stack is not usable.
        return False, None, ()

    if not devices:
        return False, None, ()
    return True, "torch-cuda", devices


def collect_runtime_metadata(config: RuntimeConfig) -> RuntimeMetadata:
    memory = psutil.virtual_memory()
    gpu_available, gpu_backend, gpu_devices = _detect_torch_cuda()

    if config.require_gpu and not gpu_available:
        raise GpuRequiredError(
            "runtime.require_gpu=true, but no usable PyTorch CUDA backend "
            "was detected. Install a CUDA-compatible PyTorch build and verify "
            "that torch.cuda.is_available() returns True."
        )

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
        gpu_available=gpu_available,
        gpu_backend=gpu_backend,
        gpu_devices=gpu_devices,
    )
