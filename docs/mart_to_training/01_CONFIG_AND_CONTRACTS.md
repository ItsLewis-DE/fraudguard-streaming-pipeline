# Phase 1 — Config và dataset contract

Mục tiêu phase này là khóa schema của experiment và manifest trước khi đụng vào ClickHouse/MinIO.

## 1. Dependency

Sửa `pyproject.toml`:

```toml
[project]
dependencies = [
    "boto3>=1.40,<2",
    "clickhouse-connect>=1.5.0",
    "confluent-kafka[avro]>=2.15.0",
    "joblib>=1.5,<2",
    "pandas>=3.0.5",
    "psutil>=7,<8",
    "pyarrow>=21,<22",
    "pydantic>=2.12,<3",
    "pyyaml>=6,<7",
    "scikit-learn>=1.7,<2",
    "seaborn>=0.13.2",
]
```

Sau khi sửa, chạy `uv lock` và commit `uv.lock`. Không thêm MLflow trong P0.

## 2. Experiment config

Tạo `ml/src/fraudguard_ml/experiment_config.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, Self

from pydantic import Field, PositiveFloat, PositiveInt
from pydantic import field_validator, model_validator

from fraudguard_ml.config import RuntimeConfig, StrictModel
from fraudguard_ml.training_data_contract import (
    DataContractError,
    IDENTIFIER_PATTERN,
    RelationName,
)


def parse_utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("timestamp must be ISO-8601") from exc
    if parsed.utcoffset() != UTC.utcoffset(parsed):
        raise ValueError("timestamp must be UTC")
    return parsed.astimezone(UTC)


def validate_identifiers(values: tuple[str, ...], field_name: str) -> None:
    if not values:
        raise ValueError(f"{field_name} must not be empty")
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} contains duplicates")
    invalid = [value for value in values if IDENTIFIER_PATTERN.fullmatch(value) is None]
    if invalid:
        raise ValueError(f"{field_name} contains invalid identifiers: {invalid}")


class DatasetConfig(StrictModel):
    relation: str
    prediction_point: Literal["post_ledger_update"]
    id_columns: tuple[str, ...]
    split_columns: tuple[str, ...]
    feature_columns: tuple[str, ...]
    target_column: Literal["is_fraud"]
    forbidden_feature_columns: tuple[str, ...]

    @field_validator(
        "id_columns",
        "split_columns",
        "feature_columns",
        "forbidden_feature_columns",
        mode="before",
    )
    @classmethod
    def freeze_sequences(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @model_validator(mode="after")
    def validate_dataset(self) -> Self:
        try:
            RelationName.parse(self.relation)
        except DataContractError as exc:
            raise ValueError(str(exc)) from exc
        validate_identifiers(self.id_columns, "id_columns")
        validate_identifiers(self.split_columns, "split_columns")
        validate_identifiers(self.feature_columns, "feature_columns")
        validate_identifiers(
            self.forbidden_feature_columns,
            "forbidden_feature_columns",
        )
        features = set(self.feature_columns)
        forbidden = set(self.forbidden_feature_columns)
        if self.target_column in features:
            raise ValueError("target_column must not be a feature")
        overlap = sorted(features & forbidden)
        if overlap:
            raise ValueError(f"feature_columns contain forbidden columns: {overlap}")
        required_ids = {"source", "event_id"}
        if set(self.id_columns) != required_ids:
            raise ValueError("id_columns must be exactly source,event_id")
        if "event_time" not in self.split_columns:
            raise ValueError("split_columns must contain event_time")
        return self


class SplitConfig(StrictModel):
    strategy: Literal["temporal"]
    train_end: str
    validation_end: str
    test_end: str

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        train_end = parse_utc(self.train_end)
        validation_end = parse_utc(self.validation_end)
        test_end = parse_utc(self.test_end)
        if not train_end < validation_end < test_end:
            raise ValueError("split boundaries must be strictly increasing")
        return self


class SnapshotConfig(StrictModel):
    storage_uri: str
    format: Literal["parquet"] = "parquet"
    compression: Literal["zstd"] = "zstd"
    fingerprint_algorithm: Literal["clickhouse_cityhash64_xor_v1"]
    label_policy: Literal["static_final_labels"]

    @field_validator("storage_uri")
    @classmethod
    def validate_storage_uri(cls, value: str) -> str:
        if not value.startswith("s3://"):
            raise ValueError("snapshot.storage_uri must start with s3://")
        if value.endswith("/"):
            return value.rstrip("/")
        return value


class ModelConfig(StrictModel):
    kind: Literal["logistic_regression"]
    class_weight: Literal["balanced"] = "balanced"
    regularization_c: PositiveFloat = 1.0
    max_iter: PositiveInt = 500


class EvaluationConfig(StrictModel):
    threshold_strategy: Literal["max_recall_at_min_precision"]
    min_precision: float = Field(0.10, gt=0.0, le=1.0)


class ExperimentConfig(StrictModel):
    schema_version: Literal[1]
    experiment_name: str
    dataset: DatasetConfig
    split: SplitConfig
    snapshot: SnapshotConfig
    model: ModelConfig
    evaluation: EvaluationConfig
    runtime: RuntimeConfig

    @field_validator("experiment_name")
    @classmethod
    def validate_experiment_name(cls, value: str) -> str:
        if IDENTIFIER_PATTERN.fullmatch(value) is None:
            raise ValueError("experiment_name must be a safe identifier")
        return value
```

## 3. Manifest models

Tạo `ml/src/fraudguard_ml/dataset_manifest.py`:

```python
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ManifestError(RuntimeError):
    """Snapshot or manifest cannot be trusted for training."""


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class SplitBoundaries(FrozenModel):
    strategy: Literal["temporal"]
    train_end: str
    validation_end: str
    test_end: str


class PartitionStatistics(FrozenModel):
    row_count: int = Field(ge=0)
    fraud_count: int = Field(ge=0)
    fraud_rate: float = Field(ge=0.0, le=1.0)
    min_event_time: str | None
    max_event_time: str | None

    @model_validator(mode="after")
    def validate_counts(self) -> "PartitionStatistics":
        if self.fraud_count > self.row_count:
            raise ValueError("fraud_count cannot exceed row_count")
        expected = self.fraud_count / self.row_count if self.row_count else 0.0
        if abs(self.fraud_rate - expected) > 1e-12:
            raise ValueError("fraud_rate does not match counts")
        return self


class SplitStatistics(FrozenModel):
    train: PartitionStatistics
    validation: PartitionStatistics
    test: PartitionStatistics


class DatasetManifest(FrozenModel):
    manifest_schema_version: Literal[1]
    experiment_name: str
    run_id: str
    created_at_utc: str
    source_relation: str
    snapshot_uri: str
    snapshot_format: Literal["parquet"]
    snapshot_sha256: str
    data_fingerprint: str
    snapshot_size_bytes: int = Field(gt=0)
    label_policy: Literal["static_final_labels"]
    row_count: int = Field(gt=0)
    fraud_count: int = Field(ge=0)
    fraud_rate: float = Field(ge=0.0, le=1.0)
    min_event_time: str
    max_event_time: str
    split: SplitBoundaries
    feature_list: tuple[str, ...]
    target_column: Literal["is_fraud"]
    dbt_manifest_sha256: str
    training_config_sha256: str
    population_query_sha256: str
    population_fingerprint: str
    fingerprint_algorithm: Literal["clickhouse_cityhash64_xor_v1"]
    quality_status: Literal["passed"]
    contract_artifact_sha256: str
    git_sha: str
    split_statistics: SplitStatistics

    @model_validator(mode="after")
    def validate_totals(self) -> "DatasetManifest":
        partitions = (
            self.split_statistics.train,
            self.split_statistics.validation,
            self.split_statistics.test,
        )
        if sum(item.row_count for item in partitions) != self.row_count:
            raise ValueError("split row counts do not reconcile")
        if sum(item.fraud_count for item in partitions) != self.fraud_count:
            raise ValueError("split fraud counts do not reconcile")
        expected = self.fraud_count / self.row_count
        if abs(self.fraud_rate - expected) > 1e-12:
            raise ValueError("fraud_rate does not match counts")
        return self


def load_manifest(path: Path) -> DatasetManifest:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"cannot read dataset manifest: {path}") from exc
    return DatasetManifest.model_validate(payload)
```

Trong code thật, bỏ dấu quote ở return annotation nếu Ruff `UP037` yêu cầu; tài liệu dùng quote để đoạn class tự chứa dễ copy.

## 4. Atomic immutable artifact

Giữ `write_json_atomic` hiện có và thêm vào `artifacts.py`:

```python
def write_json_immutable(destination: Path, payload: Mapping[str, Any]) -> None:
    if destination.exists():
        raise ArtifactError(f"refusing to overwrite immutable artifact: {destination}")
    write_json_atomic(destination, payload)


def canonical_json_sha256(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
```

## 5. YAML hoàn chỉnh

Thêm vào `configs/training_baseline.yaml` sau block `split`:

```yaml
snapshot:
  storage_uri: s3://fraud-training-snapshots
  format: parquet
  compression: zstd
  fingerprint_algorithm: clickhouse_cityhash64_xor_v1
  label_policy: static_final_labels

model:
  kind: logistic_regression
  class_weight: balanced
  regularization_c: 1.0
  max_iter: 500

evaluation:
  threshold_strategy: max_recall_at_min_precision
  min_precision: 0.10
```

Thêm cùng block vào challenger; chỉ `feature_columns` khác baseline. `runtime` hiện tại giữ nguyên.

Lưu ý bucket dùng `s3://fraud-training-snapshots`, không phải path chứa thêm bucket giả. `storage_uri` có thể thêm prefix nếu muốn, ví dụ `s3://fraud-training-snapshots/experiments`.

## 6. Tests phase 1

Tạo `ml/tests/test_experiment_config.py`, tối thiểu bao phủ:

```python
from copy import deepcopy

import pytest
from pydantic import ValidationError

from fraudguard_ml.experiment_config import ExperimentConfig


def valid_config() -> dict[str, object]:
    return {
        "schema_version": 1,
        "experiment_name": "fraudguard_logistic_baseline",
        "dataset": {
            "relation": "fraudguard_ml.ml_training_transactions",
            "prediction_point": "post_ledger_update",
            "id_columns": ["source", "event_id"],
            "split_columns": ["event_time", "event_date", "step"],
            "feature_columns": ["transaction_type", "amount"],
            "target_column": "is_fraud",
            "forbidden_feature_columns": ["event_time", "is_fraud"],
        },
        "split": {
            "strategy": "temporal",
            "train_end": "2026-01-21T20:00:00Z",
            "validation_end": "2026-01-26T20:00:00Z",
            "test_end": "2026-01-31T23:00:00Z",
        },
        "snapshot": {
            "storage_uri": "s3://fraud-training-snapshots",
            "format": "parquet",
            "compression": "zstd",
            "fingerprint_algorithm": "clickhouse_cityhash64_xor_v1",
            "label_policy": "static_final_labels",
        },
        "model": {
            "kind": "logistic_regression",
            "class_weight": "balanced",
            "regularization_c": 1.0,
            "max_iter": 500,
        },
        "evaluation": {
            "threshold_strategy": "max_recall_at_min_precision",
            "min_precision": 0.10,
        },
        "runtime": {
            "random_seed": 42,
            "max_cpu_threads": 8,
            "memory_limit_gib": 6.0,
            "require_gpu": False,
        },
    }


def test_accepts_static_label_config() -> None:
    config = ExperimentConfig.model_validate(valid_config())
    assert config.snapshot.label_policy == "static_final_labels"


def test_rejects_label_cutoff() -> None:
    payload = deepcopy(valid_config())
    payload["label_cutoff_utc"] = "2026-01-31T23:00:00Z"
    with pytest.raises(ValidationError, match="label_cutoff_utc"):
        ExperimentConfig.model_validate(payload)


def test_rejects_forbidden_feature() -> None:
    payload = deepcopy(valid_config())
    payload["dataset"]["feature_columns"].append("is_fraud")
    with pytest.raises(ValidationError, match="forbidden"):
        ExperimentConfig.model_validate(payload)


def test_rejects_unordered_boundaries() -> None:
    payload = deepcopy(valid_config())
    payload["split"]["validation_end"] = "2026-01-01T00:00:00Z"
    with pytest.raises(ValidationError, match="strictly increasing"):
        ExperimentConfig.model_validate(payload)
```

Các indexing expression trong test có thể cần `cast(dict[str, Any], ...)` để pass mypy strict; không tắt mypy toàn file.

## Acceptance phase 1

- Hai YAML load bằng `load_yaml_config(..., ExperimentConfig)`.
- Config không chấp nhận label cutoff hoặc unknown fields.
- Feature order được giữ nguyên.
- Manifest model reconcile tổng count với ba split.
- `ruff`, `mypy`, `pytest` pass trước phase 2.
