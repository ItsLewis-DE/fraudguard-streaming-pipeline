from __future__ import annotations

from pathlib import Path
from typing import Literal, TypeVar

import yaml
from pydantic import BaseModel, ConfigDict, Field, PositiveFloat, PositiveInt


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
    )


class RuntimeConfig(StrictModel):
    random_seed: int = Field(42, ge=0, le=4_294_967_295)
    max_cpu_threads: PositiveInt = 8
    memory_limit_gib: PositiveFloat = 6.0
    require_gpu: bool = False


class SmokeConfig(StrictModel):
    schema_version: Literal[1] = 1
    project_name: Literal["fraudguard"] = "fraudguard"
    runtime: RuntimeConfig


ConfigT = TypeVar("ConfigT", bound=BaseModel)


def load_yaml_config(path: Path, model_type: type[ConfigT]) -> ConfigT:
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Cannot read config file: {path}") from exc

    try:
        raw_data = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML syntax: {path}") from exc

    if not isinstance(raw_data, dict):
        raise ValueError(
            f"Config root must be a mapping, got "
            f"{type(raw_data).__name__}: {path}"
        )

    return model_type.model_validate(raw_data)

