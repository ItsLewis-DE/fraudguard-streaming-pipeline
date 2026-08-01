from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, Protocol, Self

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
RELATION_PATTERN = re.compile(
    r"^(?P<database>[A-Za-z_][A-Za-z0-9_]*)"
    r"\.(?P<table>[A-Za-z_][A-Za-z0-9_]*)$"
)


class DataContractError(RuntimeError):
    """A safe, user-facing contract failure without credentials or SQL."""


class QueryResult(Protocol):
    column_names: Sequence[str]
    result_rows: Sequence[Sequence[str]]


class ClickHouseClient(Protocol):
    def query(
        self,
        query: str,
        parameters: Mapping[str, Any] | None = None,
    ) -> QueryResult: ...


class FrozenStrictModel(BaseModel):
    model_config = ConfigDict(
        strict=True,
        frozen=True,
        extra="forbid",
    )


# Kiểm tra độ hợp lệ của relation
@dataclass(frozen=True)
class RelationName:
    database: str
    table: str

    @classmethod
    def parse(cls, value: str) -> RelationName:
        match = RELATION_PATTERN.fullmatch(value)
        if match is None:
            raise DataContractError("relation must be database.table")
        return cls(**match.groupdict())

    def quoted(self) -> str:
        return f"`{self.database}`.`{self.table}`"


class ExpectedColumn(FrozenStrictModel):
    name: str
    clickhouse_type: str
    nullable: bool = False

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if IDENTIFIER_PATTERN.fullmatch(value) is None:
            raise ValueError(f"invalid ClickHouse identifier: {value}")
        return value

    @model_validator(mode="after")
    def validate_type_nullability(self) -> Self:
        actual_nullable = self.clickhouse_type.startswith("Nullable(")
        if actual_nullable != self.nullable:
            raise ValueError("nullable must match the Nullable(...) ClickHouse type")
        return self


class TrainingDataContractConfig(FrozenStrictModel):
    schema_version: Literal[1]
    dataset_name: Literal["paysim_training_transactions_v1"]
    relation: str
    source_column: Literal["source"]
    expected_source: Literal["paysim"]
    prediction_point: Literal["post_ledger_update"]
    primary_key: tuple[str, ...]
    event_time_column: Literal["event_time"]
    step_column: Literal["step"]
    target_column: Literal["is_fraud"]
    transaction_type_column: Literal["transaction_type"]
    replay_epoch_utc: str
    expected_columns: tuple[ExpectedColumn, ...]
    prohibited_relation_columns: tuple[str, ...]
    non_feature_columns: tuple[str, ...]
    audit_candidate_columns: tuple[str, ...]
    transaction_type_domain: tuple[
        Literal["CASH_IN", "CASH_OUT", "DEBIT", "PAYMENT", "TRANSFER"],
        ...,
    ]

    @field_validator(
        "primary_key",
        "expected_columns",
        "prohibited_relation_columns",
        "non_feature_columns",
        "audit_candidate_columns",
        "transaction_type_domain",
        mode="before",
    )
    @classmethod
    def freeze_yaml_sequences(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @field_validator(
        "primary_key",
        "prohibited_relation_columns",
        "non_feature_columns",
        "audit_candidate_columns",
        mode="before",
    )
    @classmethod
    def validate_identifier_sequence(cls, value: object) -> object:
        sequence = tuple(value) if isinstance(value, (list, tuple)) else ()
        for item in sequence:
            if not isinstance(item, str):
                raise ValueError("column sequences must contain strings")
            if IDENTIFIER_PATTERN.fullmatch(item) is None:
                raise ValueError(f"invalid ClickHouse identifier: {item}")
        return value

    @field_validator("relation")
    @classmethod
    def validate_relation(cls, value: str) -> str:
        if RELATION_PATTERN.fullmatch(value) is None:
            raise ValueError("relation must be database.table")
        return value

    @field_validator("replay_epoch_utc")
    @classmethod
    def validate_replay_epoch(cls, value: str) -> str:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.utcoffset() != UTC.utcoffset(parsed):
            raise ValueError("replay_epoch_utc must be UTC")
        return value

    @model_validator(mode="after")
    def validate_column_contract(self) -> Self:
        names = tuple(column.name for column in self.expected_columns)
        expected = set(names)
        primary_key = set(self.primary_key)
        prohibited = set(self.prohibited_relation_columns)
        non_features = set(self.non_feature_columns)
        audit_candidates = set(self.audit_candidate_columns)

        def require_unique(name: str, values: tuple[str, ...]) -> None:
            if len(values) != len(set(values)):
                raise ValueError(f"{name} contains duplicates")

        if not names:
            raise ValueError("expected_columns must not be empty")
        require_unique("expected_columns", names)
        require_unique("primary_key", self.primary_key)
        require_unique(
            "prohibited_relation_columns",
            self.prohibited_relation_columns,
        )
        require_unique("non_feature_columns", self.non_feature_columns)
        require_unique("audit_candidate_columns", self.audit_candidate_columns)
        require_unique(
            "transaction_type_domain",
            self.transaction_type_domain,
        )

        if not primary_key:
            raise ValueError("primary_key must not be empty")
        if not primary_key <= expected:
            raise ValueError("primary_key must be a subset of expected columns")
        if not non_features <= expected:
            raise ValueError("non_feature_columns must be a subset of expected columns")
        if not audit_candidates <= expected:
            raise ValueError(
                "audit_candidate_columns must be a subset of expected columns"
            )
        if expected & prohibited:
            raise ValueError("expected and prohibited relation columns overlap")
        if prohibited & non_features:
            raise ValueError("prohibited and non-feature sequences overlap")
        if non_features & audit_candidates:
            raise ValueError("non-feature and audit-candidate sequences overlap")

        required_structural = {
            self.source_column,
            self.event_time_column,
            self.step_column,
            self.target_column,
            self.transaction_type_column,
        }
        if not required_structural <= expected:
            raise ValueError("structural columns are missing from schema")
        if not primary_key <= non_features:
            raise ValueError("primary-key columns must be non-features")
        if self.target_column not in non_features:
            raise ValueError("target must be a non-feature")
        return self


@dataclass(frozen=True)
class ContractMetrics:
    row_count: int
    distinct_key_count: int
    empty_key_count: int
    null_count: int
    invalid_source_count: int
    invalid_target_count: int
    invalid_type_count: int
    invalid_formula_count: int


@dataclass(frozen=True)
class ValidationReport:
    dataset_name: str
    relation: str
    validated_at_utc: str
    schema: tuple[tuple[str, str], ...]
    metrics: ContractMetrics


def parse_one_metrics_row(
    result: QueryResult,
    expected_columns: tuple[str, ...],
) -> tuple[int, ...]:
    if tuple(result.column_names) != expected_columns:
        raise DataContractError("metrics query returned unexpected columns")
    if len(result.result_rows) != 1:
        raise DataContractError("metrics query must return exactly one row")
    return tuple(int(value) for value in result.result_rows[0])


# Kiểm tra schema và trả về schema trong clickhouse
def read_exact_schema(
    client: ClickHouseClient,
    relation: RelationName,
) -> tuple[tuple[str, str], ...]:
    result = client.query(
        """
        select name, type
        from system.columns
        where database = {database:String}
          and table = {table:String}
        order by position 
        """,
        {"database": relation.database, "table": relation.table},
    )
    if tuple(result.column_names) != ("name", "type"):
        raise DataContractError("schema query returned unexpected columns")
    return tuple((str(row[0]), str(row[1])) for row in result.result_rows)


METRIC_COLUMNS = (
    "row_count",
    "distinct_key_count",
    "empty_key_count",
    "null_count",
    "invalid_source_count",
    "invalid_type_count",
    "invalid_target_count",
    "invalid_formula_count",
)


def validate_training_data_contract(
    client: ClickHouseClient,
    config: TrainingDataContractConfig,
    *,
    now_utc: datetime | None = None,
) -> ValidationReport:
    relation = RelationName.parse(config.relation)  # Kiểm tra relation có hợp lệ k
    actual_schema = read_exact_schema(client, relation)
    expected_schema = tuple(
        (column.name, column.clickhouse_type) for column in config.expected_columns
    )
    if not actual_schema:
        raise DataContractError("training relation does not exist")
    if actual_schema != expected_schema:
        raise DataContractError(
            f"exact schema mismatch: expected={expected_schema}, actual={actual_schema}"
        )
    metrics_result = client.query(
        f"""
        select 
            count() as row_count,
            uniqExact(tuple(source,event_id)) as distinct_key_count,
            countIf(trim(source)='' or trim(event_id) = '') as empty_key_count,
            countIf(
                source is null
                or event_id is null
                or event_time is null
                or event_date is null
                or step is null
                or transaction_type is null
                or amount is null
                or origin_balance_before is null
                or origin_balance_after is null
                or destination_balance_before is null
                or destination_balance_after is null
                or is_fraud is null
            ) as null_count, 
            countIf(t.source != {{expected_source:String}})
                    as invalid_source_count,
            countIf(
                not has({{types:Array(String)}}, t.transaction_type)
            ) as invalid_type_count,
            countIf(t.is_fraud not in (0, 1))
                    as invalid_target_count,
            countIf(
                origin_balance_delta
                    != origin_balance_before - origin_balance_after
                or destination_balance_delta
                    != destination_balance_after
                       - destination_balance_before
                or origin_amount_residual
                    != abs(origin_balance_delta - amount)
                or destination_amount_residual
                    != abs(destination_balance_delta - amount)
            ) as invalid_formula_count
        from {relation.quoted()}
        """,
        {
            "expected_source": config.expected_source,
            "types": list(config.transaction_type_domain),
        },
    )
    values = parse_one_metrics_row(metrics_result, METRIC_COLUMNS)
    metrics = ContractMetrics(*values)

    violations = {
        "duplicate_key_count": (metrics.row_count - metrics.distinct_key_count),
        "empty_key_count": metrics.empty_key_count,
        "null_count": metrics.null_count,
        "invalid_source_count": metrics.invalid_source_count,
        "invalid_type_count": metrics.invalid_type_count,
        "invalid_target_count": metrics.invalid_target_count,
        "invalid_formula_count": metrics.invalid_formula_count,
    }
    failed = {name: value for name, value in violations.items() if value != 0}
    if metrics.row_count == 0:
        failed["row_count"] = 0
    if failed:
        raise DataContractError(f"contract violations: {failed}")

    validated_at = (now_utc or datetime.now(UTC)).astimezone(UTC)
    return ValidationReport(
        dataset_name=config.dataset_name,
        relation=config.relation,
        validated_at_utc=validated_at.isoformat(),
        schema=actual_schema,
        metrics=metrics,
    )
