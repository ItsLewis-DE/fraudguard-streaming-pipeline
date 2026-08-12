from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, Self

from pydantic import Field, PositiveFloat, PositiveInt, field_validator, model_validator

from fraudguard_ml.config import RuntimeConfig, StrictModel
from fraudguard_ml.training_data_contract import (
    IDENTIFIER_PATTERN,
    DataContractError,
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
