from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, Self

from pydantic import field_validator, model_validator

from fraudguard_ml.config import StrictModel
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
