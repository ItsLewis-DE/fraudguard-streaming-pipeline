from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from fraudguard_ml.config import SmokeConfig, load_yaml_config


def _valid_config_data(
    *,
    runtime_overrides: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    runtime: dict[str, Any] = {
        "random_seed": 42,
        "max_cpu_threads": 8,
        "memory_limit_gib": 6.0,
        "require_gpu": False,
    }
    if runtime_overrides is not None:
        runtime.update(runtime_overrides)

    return {
        "schema_version": 1,
        "project_name": "fraudguard",
        "runtime": runtime,
    }

def _write_yaml(tmp_path: Path, data: Any) -> Path:
    config_path = tmp_path / "smoke.yaml"
    config_path.write_text(
        yaml.safe_dump(data, sort_keys=False),
        encoding="utf-8",
    )
    return config_path

#Nếu pass nghĩa là một file YMAL hợp lệ đi qua load thì nó không bị thay đổi 
def test_loads_valid_yaml(tmp_path: Path) -> None:
    config_path = _write_yaml(tmp_path, _valid_config_data())

    config = load_yaml_config(config_path, SmokeConfig)

    assert isinstance(config, SmokeConfig)
    assert config.schema_version == 1
    assert config.project_name == "fraudguard"
    assert config.runtime.random_seed == 42
    assert config.runtime.max_cpu_threads == 8
    assert config.runtime.memory_limit_gib == 6.0
    assert config.runtime.require_gpu is False


def test_rejects_missing_config_file(tmp_path: Path) -> None:
    missing_path = tmp_path / "does-not-exist.yaml"

    with pytest.raises(
        ValueError,
        match=r"Cannot read config file:",
    ) as exc_info:
        load_yaml_config(missing_path, SmokeConfig)

    assert isinstance(exc_info.value.__cause__, FileNotFoundError)

def test_rejects_malformed_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / "smoke.yaml"
    config_path.write_text(
        "runtime: [\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match=r"Invalid YAML syntax:",
    ) as exc_info:
        load_yaml_config(config_path, SmokeConfig)

    assert isinstance(exc_info.value.__cause__, yaml.YAMLError)

@pytest.mark.parametrize(
    ("raw_yaml","root_type"),
    [
        ("- first\n- second\n","list"),
        ("42\n","int"),
        ("null\n","NoneType")
    ],
    ids=["list","scalar","null"],
)

def test_rejects_non_mapping_yaml_root(
    tmp_path:Path,
    raw_yaml:str,
    root_type:str
) ->None:
    config_path = tmp_path / "smoke.yaml"
    config_path.write_text(raw_yaml,encoding="utf-8")

    with pytest.raises(
        ValueError,
        match=rf"Config root must be a mapping, got {root_type}:"
    ):
        load_yaml_config(config_path,SmokeConfig)

def _assert_validation_error(
    error: ValidationError,
    *,
    location: tuple[str | int, ...],
    error_type: str,
) -> None:
    assert any(
        tuple(item["loc"]) == location and item["type"] == error_type
        for item in error.errors()
    ), error.errors()

def test_rejects_unknown_field(tmp_path: Path) -> None:
    data = _valid_config_data(
        runtime_overrides={"random_sead": 7},
    )
    config_path = _write_yaml(tmp_path, data)

    with pytest.raises(ValidationError) as exc_info:
        load_yaml_config(config_path, SmokeConfig)

    _assert_validation_error(
        exc_info.value,
        location=("runtime", "random_sead"),
        error_type="extra_forbidden",
    )

@pytest.mark.parametrize(
    ("seed", "error_type"),
    [
        (-1, "greater_than_equal"),
        (4_294_967_296, "less_than_equal"),
    ],
    ids=["negative", "above-uint32"],
)
def test_rejects_seed_outside_supported_range(
    tmp_path: Path,
    seed: int,
    error_type: str,
) -> None:
    config_path = _write_yaml(
        tmp_path,
        _valid_config_data(runtime_overrides={"random_seed": seed}),
    )

    with pytest.raises(ValidationError) as exc_info:
        load_yaml_config(config_path, SmokeConfig)

    _assert_validation_error(
        exc_info.value,
        location=("runtime", "random_seed"),
        error_type=error_type,
    )

def test_rejects_string_for_integer_in_strict_mode(tmp_path: Path) -> None:
    config_path = _write_yaml(
        tmp_path,
        _valid_config_data(runtime_overrides={"random_seed": "42"}),
    )

    with pytest.raises(ValidationError) as exc_info:
        load_yaml_config(config_path, SmokeConfig)

    _assert_validation_error(
        exc_info.value,
        location=("runtime", "random_seed"),
        error_type="int_type",
    )

@pytest.mark.parametrize(
    ("field_name", "invalid_value", "error_type"),
    [
        ("max_cpu_threads", 0, "greater_than"),
        ("max_cpu_threads", -1, "greater_than"),
        ("memory_limit_gib", 0.0, "greater_than"),
        ("memory_limit_gib", -0.5, "greater_than"),
    ],
    ids=[
        "zero-cpu",
        "negative-cpu",
        "zero-memory",
        "negative-memory",
    ],
)
def test_rejects_non_positive_resource_limit(
    tmp_path: Path,
    field_name: str,
    invalid_value: int | float,
    error_type: str,
) -> None:
    config_path = _write_yaml(
        tmp_path,
        _valid_config_data(
            runtime_overrides={field_name: invalid_value},
        ),
    )

    with pytest.raises(ValidationError) as exc_info:
        load_yaml_config(config_path, SmokeConfig)

    _assert_validation_error(
        exc_info.value,
        location=("runtime", field_name),
        error_type=error_type,
    )

@pytest.mark.parametrize(
    ("target_name", "field_name", "new_value"),
    [
        ("config", "project_name", "other-project"),
        ("runtime", "random_seed", 7),
    ],
    ids=["top-level", "nested-runtime"],
)
def test_loaded_config_is_immutable(
    tmp_path: Path,
    target_name: str,
    field_name: str,
    new_value: object,
) -> None:
    config_path = _write_yaml(tmp_path, _valid_config_data())
    config = load_yaml_config(config_path, SmokeConfig)
    target = config if target_name == "config" else config.runtime

    with pytest.raises(ValidationError) as exc_info:
        setattr(target, field_name, new_value)

    _assert_validation_error(
        exc_info.value,
        location=(field_name,),
        error_type="frozen_instance",
    )