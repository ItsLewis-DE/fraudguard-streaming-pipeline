from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from botocore.client import BaseClient
from numpy.typing import NDArray #Dùng để typehint

from fraudguard_ml.artifacts import (
    git_output,
    sha256_file,
    write_json_immutable,
)
from fraudguard_ml.dataset_manifest import (
    DatasetManifest,
    PartitionStatistics,
    SplitBoundaries,
    SplitStatistics,
)
from fraudguard_ml.experiment_config import ExperimentConfig, parse_utc
from fraudguard_ml.object_storage import upload_file_immutable
from fraudguard_ml.training_data_contract import DataContractError, RelationName

HELPER_HASH_COLUMN = "__population_hash"


class SnapshotError(RuntimeError):
    """A dataset snapshot could not be created safely."""

@dataclass
class MutableStats:
    row_count: int = 0
    fraud_count: int = 0
    min_event_time: pd.Timestamp | None = None
    max_event_time: pd.Timestamp | None = None

    def update(self, event_time: pd.Series, target: NDArray[np.uint8]) -> None:
        if len(event_time) == 0:
            return
        self.row_count += len(event_time)
        self.fraud_count += int(target.sum())
        current_min = event_time.min()
        current_max = event_time.max()
        if self.min_event_time is None or current_min < self.min_event_time:
            self.min_event_time = current_min
        if self.max_event_time is None or current_max > self.max_event_time:
            self.max_event_time = current_max

    def freeze(self) -> PartitionStatistics:
        rate = self.fraud_count / self.row_count if self.row_count else 0.0
        return PartitionStatistics(
            row_count=self.row_count,
            fraud_count=self.fraud_count,
            fraud_rate=rate,
            min_event_time=(
                self.min_event_time.isoformat()
                if self.min_event_time is not None
                else None
            ),
            max_event_time=(
                self.max_event_time.isoformat()
                if self.max_event_time is not None
                else None
            ),
        )

def unique_in_order(columns: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(columns)) #Ép về tuple là vì sẽ kh cho phép chỉnh sửa

def quote_identifier(value: str) -> str:
    return f"`{value}`"

def build_population_query(config: ExperimentConfig) -> tuple[str, dict[str, str]]:
    relation = RelationName.parse(config.dataset.relation)
    columns = unique_in_order(
        (
            *config.dataset.id_columns,
            *config.dataset.split_columns,
            *config.dataset.feature_columns,
            config.dataset.target_column,
        )
    )
    projection = ",\n            ".join(quote_identifier(name) for name in columns)
    #Hash để kiểm tra xem dữ liệu giữa bashline và challenger có thay đổi k
    query = f"""
        select
            {projection},
            cityHash64(source, event_id, event_time, is_fraud)
                as {HELPER_HASH_COLUMN} 
        from {relation.quoted()}
        where event_time <= {{test_end:DateTime64(3, 'UTC')}}
    """
    return query, {"test_end": config.split.test_end}

def canonical_query_sha256(query: str, parameters: dict[str, str]) -> str:
    payload = {
        "query": " ".join(query.split()),
        "parameters": dict(sorted(parameters.items())),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode() #encode chuyển string
    #thành bytes
    return hashlib.sha256(encoded).hexdigest()
