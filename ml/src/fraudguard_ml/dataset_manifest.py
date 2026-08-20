"""Schema and trust checks for immutable dataset snapshot manifests.

Flow:
    1. Snapshot creation records source, hashes, temporal boundaries, and counts.
    2. Pydantic validates field types and rejects unknown or mutable state.
    3. Model validators reconcile fraud rates and split totals.
    4. Consumers call :func:`load_manifest` before using a snapshot for training.

The manifest is the hand-off contract between snapshotting and model training.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator


class ManifestError(RuntimeError):
    """Raised when a snapshot manifest cannot be trusted for training."""


class FrozenModel(BaseModel):
    """Strict immutable base class for every manifest section."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class SplitBoundaries(FrozenModel):
    """UTC boundaries used to derive temporal train, validation, and test sets."""

    strategy: Literal["temporal"]
    train_end: str
    validation_end: str
    test_end: str


class PartitionStatistics(FrozenModel):
    """Row, label, and event-time statistics for one dataset partition."""

    row_count: int = Field(ge=0)
    fraud_count: int = Field(ge=0)
    fraud_rate: float = Field(ge=0.0, le=1.0)
    min_event_time: str | None
    max_event_time: str | None

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        """Reconcile the recorded fraud rate with row and fraud counts."""

        if self.fraud_count > self.row_count:
            raise ValueError("fraud_count cannot exceed row_count")
        expected = self.fraud_count / self.row_count if self.row_count else 0.0
        if abs(self.fraud_rate - expected) > 1e-12:
            raise ValueError("fraud_rate does not match counts")
        return self


class SplitStatistics(FrozenModel):
    """Statistics for all three temporal partitions."""

    train: PartitionStatistics
    validation: PartitionStatistics
    test: PartitionStatistics


class DatasetManifest(FrozenModel):
    """Complete provenance and quality contract for one immutable snapshot."""

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

    @field_validator("feature_list",mode="before")
    @classmethod
    def freeze_feature_list(cls,value:object) -> object:
        return tuple(value) if isinstance(value,list) else value
    @model_validator(mode="after")
    def validate_totals(self) -> DatasetManifest:
        """Ensure split totals and the overall fraud rate are internally consistent."""

        partitions = (
            self.split_statistics.train,
            self.split_statistics.validation,
            self.split_statistics.test,
        )
        if sum(item.row_count for item in partitions) != self.row_count:
            raise ValueError("split row counts do not reconcile")
        if sum(item.fraud_count for item in partitions) != self.fraud_count:
            raise ValueError("split fraud counts do not reconcile")
        expected = self.fraud_count / self.row_count if self.row_count else 0.0
        if abs(self.fraud_rate - expected) > 1e-12:
            raise ValueError("fraud_rate does not match counts")
        return self


def load_manifest(path: Path) -> DatasetManifest:
    """Read a JSON manifest and return its fully validated immutable model."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"cannot read dataset manifest: {path}") from exc
    return DatasetManifest.model_validate(payload)
