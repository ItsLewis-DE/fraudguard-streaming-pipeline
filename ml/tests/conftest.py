from collections import deque
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import yaml

from fraudguard_ml.config import load_yaml_config
from fraudguard_ml.training_data_contract import (
    METRIC_COLUMNS,
    TrainingDataContractConfig,
)

REPO_DIR = Path(__file__).resolve().parents[2]
CANONICAL_CONTRACT_PATH = REPO_DIR / "configs" / "training_data_contract.yml"


@pytest.fixture
def canonical_contract_path() -> Path:
    return CANONICAL_CONTRACT_PATH


@pytest.fixture
def canonical_contract(canonical_contract_path: Path) -> TrainingDataContractConfig:
    return load_yaml_config(canonical_contract_path, TrainingDataContractConfig)


@pytest.fixture
def canonical_contract_data(canonical_contract_path: Path) -> dict[str, Any]:
    loaded = yaml.safe_load(canonical_contract_path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return deepcopy(loaded)


@dataclass(frozen=True)
class FakeResult:
    column_names: Sequence[str]
    result_rows: Sequence[Sequence[str]]


@dataclass(frozen=True)
class QueryCall:
    query: str
    parameters: Mapping[str, Any] | None


@dataclass(frozen=True)
class QueryRoute:
    name: str
    matches: Callable[[str], bool]


ROUTES = (
    QueryRoute("schema", lambda sql: "from system.columns" in sql),
    QueryRoute(
        "metrics",
        lambda sql: "as row_count" in sql and "as invalid_formula_count" in sql,
    ),
)


# Vì không dùng vòng lặp ở hàm init và class này thường xuyên thay đổi nên ta k
# nên dùng dataclass ở đây
class FakeClient:
    def __init__(
        self,
        routes: tuple[QueryRoute, ...],
        responses: Mapping[str, list[FakeResult | Exception]],
    ) -> None:
        self.routes = routes
        self.responses = {name: deque(items) for name, items in responses.items()}
        self.calls: list[QueryCall] = []  # Lịch sử query
        self.closed = False

    def query(
        self, query: str, parameters: Mapping[str, Any] | None = None
    ) -> FakeResult:
        self.calls.append(QueryCall(query, parameters))
        normalized = " ".join(query.lower().split())
        matched = [route for route in self.routes if route.matches(normalized)]
        if len(matched) != 1:
            raise AssertionError(
                f"expected exactly one fake route, got {[r.name for r in matched]}"
            )

        route_name = matched[0].name  # Loại của câu query
        queue = self.responses.get(route_name)
        if not queue:
            raise AssertionError(f"no scripted response left for {route_name}")

        result = queue.popleft()
        if isinstance(result, Exception):
            raise result
        return result

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def valid_schema_rows(
    canonical_contract: TrainingDataContractConfig,
) -> tuple[tuple[str, str], ...]:
    return tuple(
        (column.name, column.clickhouse_type)
        for column in canonical_contract.expected_columns
    )


def metric_result(**overrides: int) -> FakeResult:
    columns = METRIC_COLUMNS
    values = dict.fromkeys(columns, 0)
    values.update(row_count=3, distinct_key_count=3)
    unknown = set(overrides) - set(values)
    assert not unknown, f"unknown metrics: {sorted(unknown)}"
    values.update(overrides)
    return FakeResult(
        column_names=columns,
        result_rows=[tuple(str(values[name]) for name in columns)],
    )
