"""Strict configuration models and the shared YAML loading boundary.

Flow:
    1. Read UTF-8 YAML from disk.
    2. Require a mapping at the document root.
    3. Delegate semantic and type validation to the requested Pydantic model.

All models reject unknown keys and are frozen after creation, making typos
visible early and preventing configuration drift during a run.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, PositiveFloat, PositiveInt


class StrictModel(BaseModel):
    """Base model that forbids coercion, unknown fields, and mutation."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
    )


class RuntimeConfig(StrictModel):
    """Reproducibility and compute-resource limits shared by ML commands."""

    random_seed: int = Field(42, ge=0, le=4_294_967_295)
    max_cpu_threads: PositiveInt = 8
    memory_limit_gib: PositiveFloat = 6.0


def load_yaml_config[ConfigT: BaseModel](
    path: Path,
    model_type: type[ConfigT],
) -> ConfigT:
    """Load YAML and validate it as ``model_type``.

    Raises ``ValueError`` for filesystem, YAML-shape, or syntax failures;
    Pydantic reports field-level schema violations to the caller.
    """

    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Cannot read config file: {path}") from exc

    try:
        raw_data = yaml.safe_load(raw_text)  # Trả về dict
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML syntax: {path}") from exc

    if not isinstance(raw_data, dict):
        raise ValueError(
            f"Config root must be a mapping, got {type(raw_data).__name__}: {path}"
        )

    return model_type.model_validate(raw_data)  # Kiểm tra với pydatic
