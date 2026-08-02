from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from conftest import ROUTES, FakeClient, FakeResult, metric_result

from fraudguard_ml.training_data_contract import (
    DataContractError,
    TrainingDataContractConfig,
    validate_training_data_contract,
)


def test_happy_path(
    canonical_contract: TrainingDataContractConfig,
    valid_schema_rows: tuple[tuple[str, str], ...],
) -> None:
    fake_client = FakeClient(
        routes=ROUTES,
        responses={
            "schema": [FakeResult(("name", "type"), valid_schema_rows)],
            "metrics": [metric_result()],
        },
    )
    fixed_now = datetime(2026, 2, 3, 4, 5, tzinfo=UTC)
    report = validate_training_data_contract(
        fake_client,  # type: ignore
        canonical_contract,
        now_utc=fixed_now,
    )
    assert report.relation == canonical_contract.relation
    assert report.schema == valid_schema_rows
    assert report.validated_at_utc == "2026-02-03T04:05:00+00:00"
    assert len(fake_client.calls) == 2


@pytest.mark.parametrize(
    "mutation_func",
    [
        lambda rows: (),
        lambda rows: rows[:-1],
        lambda rows: (*rows, ("unexpected", "String")),
        lambda rows: (rows[1], rows[0], *rows[2:]),
        lambda rows: (("bad_name", rows[0][1]), *rows[1:]),
    ],
)
def test_exact_schema_mismatch(
    canonical_contract: TrainingDataContractConfig,
    valid_schema_rows: tuple[tuple[str, str], ...],
    mutation_func: Callable[[tuple[tuple[str, str], ...]], tuple[tuple[str, str], ...]],
) -> None:
    fake_client = FakeClient(
        routes=ROUTES,
        responses={
            "schema": [FakeResult(("name", "type"), mutation_func(valid_schema_rows))],
        },
    )
    with pytest.raises(DataContractError, match="schema"):
        validate_training_data_contract(
            fake_client,  # type: ignore
            canonical_contract,
        )


@pytest.mark.parametrize(
    "overrides, expected_key",
    [
        ({"row_count": 0, "distinct_key_count": 0}, "row_count"),
        ({"row_count": 3, "distinct_key_count": 2}, "duplicate_key_count"),
        ({"empty_key_count": 1}, "empty_key_count"),
        ({"null_count": 1}, "null_count"),
        ({"invalid_source_count": 1}, "invalid_source_count"),
        ({"invalid_type_count": 1}, "invalid_type_count"),
        ({"invalid_target_count": 1}, "invalid_target_count"),
        ({"invalid_formula_count": 1}, "invalid_formula_count"),
        ({"missing_lineage_count": 1}, "missing_lineage_count"),
    ],
)
def test_violations(
    canonical_contract: TrainingDataContractConfig,
    valid_schema_rows: tuple[tuple[str, str], ...],
    overrides: dict[str, int],
    expected_key: str,
) -> None:
    fake_client = FakeClient(
        routes=ROUTES,
        responses={
            "schema": [FakeResult(("name", "type"), valid_schema_rows)],
            "metrics": [metric_result(**overrides)],
        },
    )
    with pytest.raises(DataContractError, match=expected_key):
        validate_training_data_contract(
            fake_client,  # type: ignore
            canonical_contract,
        )


@pytest.mark.parametrize(
    ("formula_name", "required_fragment"),
    [
        ("origin_delta", "origin_balance_before - origin_balance_after"),
        ("destination_delta", "destination_balance_after - destination_balance_before"),
        ("origin_residual", "abs(origin_balance_delta - amount)"),
        ("destination_residual", "abs(destination_balance_delta - amount)"),
        ("lineage_join", "left join"),
    ],
)
def test_sql_fragments(
    canonical_contract: TrainingDataContractConfig,
    valid_schema_rows: tuple[tuple[str, str], ...],
    formula_name: str,
    required_fragment: str,
) -> None:
    fake_client = FakeClient(
        routes=ROUTES,
        responses={
            "schema": [FakeResult(("name", "type"), valid_schema_rows)],
            "metrics": [metric_result()],
        },
    )
    validate_training_data_contract(fake_client, canonical_contract)  # type: ignore
    metrics_call = fake_client.calls[1]
    normalized = " ".join(metrics_call.query.lower().split())
    assert required_fragment.lower() in normalized


def test_sql_identifiers_quoted_and_values_parameterized(
    canonical_contract: TrainingDataContractConfig,
    valid_schema_rows: tuple[tuple[str, str], ...],
) -> None:
    fake_client = FakeClient(
        routes=ROUTES,
        responses={
            "schema": [FakeResult(("name", "type"), valid_schema_rows)],
            "metrics": [metric_result()],
        },
    )
    validate_training_data_contract(fake_client, canonical_contract)  # type: ignore

    schema_call = fake_client.calls[0]
    assert schema_call.parameters == {
        "database": "fraudguard_ml",
        "table": "ml_training_transactions",
    }

    metrics_call = fake_client.calls[1]
    normalized = " ".join(metrics_call.query.split())
    assert "`fraudguard_ml`.`ml_training_transactions`" in normalized
    assert canonical_contract.expected_source not in metrics_call.query
    assert metrics_call.parameters is not None
    assert metrics_call.parameters["expected_source"] == "paysim"
