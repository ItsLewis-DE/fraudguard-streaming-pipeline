"""Create immutable, temporally partitioned snapshots from validated mart data.

End-to-end flow:
    1. Verify that the training-data contract passed for the configured relation.
    2. Stream the bounded population from ClickHouse in Arrow record batches.
    3. Write Parquet incrementally while accumulating total/split statistics and
       a population fingerprint; atomically expose the file only when complete.
    4. Upload the immutable snapshot to S3/MinIO using SHA-256 verification.
    5. Build, validate, persist, and upload a provenance-rich dataset manifest.
    6. Upload the exact contract artifact alongside the snapshot and manifest.

The module avoids loading the entire dataset into memory and fails closed when a
split is empty, lacks fraud positives, or conflicts with an existing artifact.
"""

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
from numpy.typing import NDArray

from fraudguard_ml.artifacts import git_output, sha256_file
from fraudguard_ml.dataset_manifest import (
    DatasetManifest,
    PartitionStatistics,
    SplitBoundaries,
    SplitStatistics,
)
from fraudguard_ml.experiment_config import ExperimentConfig, parse_utc
from fraudguard_ml.io_utils import write_json_immutable
from fraudguard_ml.object_storage import upload_file_immutable
from fraudguard_ml.training_data_contract import DataContractError, RelationName

HELPER_HASH_COLUMN = "__population_hash"


class SnapshotError(RuntimeError):
    """Raised when a dataset snapshot cannot be created or trusted safely."""


@dataclass
class MutableStats:
    """Streaming accumulator converted to a validated partition summary later."""

    row_count: int = 0
    fraud_count: int = 0
    min_event_time: pd.Timestamp | None = None
    max_event_time: pd.Timestamp | None = None

    def update(self, event_time: pd.Series, target: NDArray[np.uint8]) -> None:
        """Merge one Arrow batch's timestamps and binary labels into the totals."""

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
        """Convert mutable counters into an immutable, self-validating model."""

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
    """Remove duplicate column names while preserving projection order."""

    return tuple(dict.fromkeys(columns))  # Ép về tuple là vì sẽ kh cho phép chỉnh sửa


def quote_identifier(value: str) -> str:
    """Quote a previously validated ClickHouse identifier."""

    return f"`{value}`"


def build_population_query(config: ExperimentConfig) -> tuple[str, dict[str, str]]:
    """Build the snapshot query and its separately bound temporal parameter.

    The helper hash is used only for a stable population fingerprint and is
    removed before rows are written to the training Parquet file.
    """

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
    # Hash để kiểm tra xem dữ liệu giữa bashline và challenger có thay đổi k
    query = f"""
        select
            {projection},
            cityHash64(source, event_id, event_time, is_fraud)
                as {HELPER_HASH_COLUMN} 
        from {relation.quoted()}
        where event_time <= {{test_end:DateTime64(3, 'UTC')}}
    """
    return query, {"test_end": config.split.test_end.strftime("%Y-%m-%d %H:%M:%S")}


def canonical_query_sha256(query: str, parameters: dict[str, str]) -> str:
    """Hash normalized SQL plus sorted parameters for query-level provenance."""

    payload = {
        "query": " ".join(query.split()),
        "parameters": dict(sorted(parameters.items())),
    }
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":")
    ).encode()  # encode chuyển string
    # thành bytes
    return hashlib.sha256(encoded).hexdigest() #Chỉ nhận bytes


def validate_contract_artifact(path: Path, expected_relation: str) -> None:
    """Require a successful contract artifact for the experiment's relation."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SnapshotError(f"cannot read contract artifact: {path}") from exc
    relation = payload.get("validation", {}).get("relation")
    if payload.get("status") != "validated":
        raise SnapshotError("training-data contract did not pass")
    if relation != expected_relation:
        raise SnapshotError("contract relation does not match experiment relation")


def update_split_stats(
    stats: dict[str, MutableStats],
    event_time: pd.Series,
    target: NDArray[np.uint8],
    config: ExperimentConfig,
) -> None:
    """Assign a batch to temporal splits and update each split accumulator."""

    train_end = pd.Timestamp(parse_utc(config.split.train_end))
    validation_end = pd.Timestamp(parse_utc(config.split.validation_end))
    train_mask = event_time.le(train_end).to_numpy()
    validation_mask = (
        event_time.gt(train_end) & event_time.le(validation_end)
    ).to_numpy()
    test_mask = event_time.gt(validation_end).to_numpy()
    for name, mask in (
        ("train", train_mask),
        ("validation", validation_mask),
        ("test", test_mask),
    ):
        stats[name].update(event_time[mask], target[mask])


def stream_snapshot(
    client: Any,
    config: ExperimentConfig,
    destination: Path,
) -> tuple[PartitionStatistics, SplitStatistics, str, str]:
    """Stream ClickHouse rows into one atomic Parquet snapshot.

    Returns overall statistics, per-split statistics, the population fingerprint,
    and the canonical query hash. Temporary files are removed on every failure.
    """

    if destination.exists():
        raise SnapshotError(f"refusing to overwrite snapshot: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp")
    query, parameters = build_population_query(config)
    total = MutableStats()
    split = {name: MutableStats() for name in ("train", "validation", "test")}
    population_xor = 0
    writer: pq.ParquetWriter | None = None
    try:
        with client.query_arrow_stream(query, parameters=parameters) as stream:
            for block in stream:
                if block.num_rows == 0:
                    continue
                event_time = pd.to_datetime(block["event_time"].to_pandas(), utc=True)
                #Vì chỉ lấy 1 cột nên khi to_pandas sẽ chuyển qua series
                target = (
                    block[config.dataset.target_column]
                    .to_numpy(zero_copy_only=False)
                    .astype(np.uint8, copy=False)
                )
                total.update(event_time, target)
                update_split_stats(split, event_time, target, config)
                #Tạo một mã x_or cho từng chunk, cộng dồn lại với nhau
                for value in block[HELPER_HASH_COLUMN].to_pylist():
                    population_xor ^= int(value)
                output_block = block.drop([HELPER_HASH_COLUMN])
                if writer is None:
                    writer = pq.ParquetWriter(
                        temporary,
                        output_block.schema,
                        compression=config.snapshot.compression,
                    )
                writer.write_table(output_block)
        if writer is None:
            raise DataContractError("snapshot population is empty")
        writer.close()
        writer = None
        os.replace(temporary, destination)
    except Exception:
        if writer is not None:
            writer.close()
        temporary.unlink(missing_ok=True)
        raise
    total_stats = total.freeze()
    split_stats = SplitStatistics(
        train=split["train"].freeze(),
        validation=split["validation"].freeze(),
        test=split["test"].freeze(),
    )
    if any(
        item.row_count == 0 or item.fraud_count == 0
        for item in (split_stats.train, split_stats.validation, split_stats.test)
    ):
        raise SnapshotError("every split must contain rows and fraud positives")
    return (
        total_stats,
        split_stats,
        f"xor64:{population_xor:016x}",
        canonical_query_sha256(query, parameters),
    )


def join_s3_uri(root: str, *parts: str) -> str:
    """Join an S3 root and path components without duplicate separators."""

    return "/".join([root.rstrip("/"), *(part.strip("/") for part in parts)])


def create_snapshot_and_manifest(
    *,
    client: Any,
    s3_client: BaseClient,
    config: ExperimentConfig,
    config_path: Path,
    contract_artifact_path: Path,
    dbt_manifest_path: Path,
    repository_root: Path,
    run_id: str,
    output_dir: Path,
    now_utc: datetime | None = None,
) -> DatasetManifest:
    """Orchestrate contract verification, snapshot creation, and publication.

    The returned :class:`DatasetManifest` links the source relation, exact query,
    local inputs, Git revision, split quality statistics, and uploaded Parquet
    digest. All three published files use immutable object-storage semantics.
    """

    validate_contract_artifact(contract_artifact_path, config.dataset.relation)
    output_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = output_dir / "data.parquet"
    manifest_path = output_dir / "dataset_manifest.json"
    total, split, population_fingerprint, query_hash = stream_snapshot(
        client, config, parquet_path
    )
    snapshot_uri = join_s3_uri(
        config.snapshot.storage_uri,
        config.experiment_name,
        run_id,
        "data.parquet",
    )
    snapshot_sha256 = upload_file_immutable(s3_client, parquet_path, snapshot_uri)
    manifest = DatasetManifest(
        manifest_schema_version=1,
        experiment_name=config.experiment_name,
        run_id=run_id,
        created_at_utc=(now_utc or datetime.now(UTC)).astimezone(UTC).isoformat(),
        source_relation=config.dataset.relation,
        snapshot_uri=snapshot_uri,
        snapshot_format="parquet",
        snapshot_sha256=snapshot_sha256,
        data_fingerprint=f"sha256:{snapshot_sha256}",
        snapshot_size_bytes=parquet_path.stat().st_size,
        label_policy=config.snapshot.label_policy,
        row_count=total.row_count,
        fraud_count=total.fraud_count,
        fraud_rate=total.fraud_rate,
        min_event_time=total.min_event_time or "",
        max_event_time=total.max_event_time or "",
        split=SplitBoundaries(
            strategy="temporal",
            train_end=config.split.train_end,
            validation_end=config.split.validation_end,
            test_end=config.split.test_end,
        ),
        feature_list=config.dataset.feature_columns,
        target_column=config.dataset.target_column,
        dbt_manifest_sha256=sha256_file(dbt_manifest_path),
        training_config_sha256=sha256_file(config_path),
        population_query_sha256=query_hash,
        population_fingerprint=population_fingerprint,
        fingerprint_algorithm=config.snapshot.fingerprint_algorithm,
        quality_status="passed",
        contract_artifact_sha256=sha256_file(contract_artifact_path),
        git_sha=git_output(repository_root, ["rev-parse", "HEAD"]),
        split_statistics=split,
    )
    write_json_immutable(manifest_path, manifest.model_dump(mode="json"))
    manifest_uri = join_s3_uri(
        config.snapshot.storage_uri,
        config.experiment_name,
        run_id,
        "dataset_manifest.json",
    )
    upload_file_immutable(s3_client, manifest_path, manifest_uri)
    contract_uri = join_s3_uri(
        config.snapshot.storage_uri,
        config.experiment_name,
        run_id,
        "artifact.json",
    )
    upload_file_immutable(s3_client, contract_artifact_path, contract_uri)
    return manifest
