# Phase 2 — Snapshot Parquet và manifest

Mục tiêu là biến live mart thành một artifact bất biến bằng đúng một query ClickHouse. Statistics được tính trong lúc stream và SHA-256 được tính trên file Parquet đã đóng.

## 1. MinIO adapter

Tạo `ml/src/fraudguard_ml/object_storage.py`:

```python
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import boto3
from botocore.client import BaseClient
from botocore.config import Config
from botocore.exceptions import ClientError

from fraudguard_ml.artifacts import ArtifactError, sha256_file


@dataclass(frozen=True)
class S3Location:
    bucket: str
    key: str

    @classmethod
    def parse(cls, uri: str) -> "S3Location":
        parsed = urlparse(uri)
        if parsed.scheme != "s3" or not parsed.netloc or not parsed.path.strip("/"):
            raise ValueError("S3 URI must be s3://bucket/key")
        return cls(bucket=parsed.netloc, key=parsed.path.lstrip("/"))


@dataclass(frozen=True)
class ObjectStorageSettings:
    endpoint_url: str
    access_key: str
    secret_key: str
    region_name: str = "us-east-1"

    @classmethod
    def from_env(cls) -> "ObjectStorageSettings":
        access_key = os.getenv("MINIO_ACCESS_KEY") or os.getenv("MINIO_AIRFLOW_USER")
        secret_key = os.getenv("MINIO_SECRET_KEY") or os.getenv(
            "MINIO_AIRFLOW_PASSWORD"
        )
        if not access_key or not secret_key:
            raise ValueError("MinIO credentials must be configured")
        return cls(
            endpoint_url=os.getenv("MINIO_ENDPOINT", "http://localhost:9000"),
            access_key=access_key,
            secret_key=secret_key,
        )


def create_s3_client(settings: ObjectStorageSettings) -> BaseClient:
    return boto3.client(
        "s3",
        endpoint_url=settings.endpoint_url,
        aws_access_key_id=settings.access_key,
        aws_secret_access_key=settings.secret_key,
        region_name=settings.region_name,
        config=Config(s3={"addressing_style": "path"}),
    )


def object_sha256(client: BaseClient, location: S3Location) -> str | None:
    try:
        response = client.head_object(Bucket=location.bucket, Key=location.key)
    except ClientError as exc:
        status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if status == 404:
            return None
        raise ArtifactError(
            f"cannot inspect object: s3://{location.bucket}/{location.key}"
        ) from exc
    metadata = response.get("Metadata", {})
    value = metadata.get("sha256")
    return str(value) if value else ""


def upload_file_immutable(client: BaseClient, source: Path, uri: str) -> str:
    location = S3Location.parse(uri)
    local_sha256 = sha256_file(source)
    existing_sha256 = object_sha256(client, location)
    if existing_sha256 is not None:
        if existing_sha256 == local_sha256:
            return local_sha256
        raise ArtifactError(f"refusing to overwrite immutable object: {uri}")
    try:
        client.upload_file(
            str(source),
            location.bucket,
            location.key,
            ExtraArgs={"Metadata": {"sha256": local_sha256}},
        )
    except ClientError as exc:
        raise ArtifactError(f"cannot upload object: {uri}") from exc
    remote_sha256 = object_sha256(client, location)
    if remote_sha256 != local_sha256:
        raise ArtifactError(f"object hash verification failed: {uri}")
    return local_sha256


def download_file(client: BaseClient, uri: str, destination: Path) -> None:
    location = S3Location.parse(uri)
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        client.download_file(location.bucket, location.key, str(destination))
    except ClientError as exc:
        raise ArtifactError(f"cannot download object: {uri}") from exc
```

Không log access key/secret. Test adapter bằng fake/mocked client; integration test dùng MinIO local.

## 2. Snapshot implementation

Tạo `ml/src/fraudguard_ml/dataset_snapshot.py`:

```python
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
    return tuple(dict.fromkeys(columns))


def quote_identifier(value: str) -> str:
    # All values have already passed ExperimentConfig identifier validation.
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
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def validate_contract_artifact(path: Path, expected_relation: str) -> None:
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
                target = (
                    block[config.dataset.target_column]
                    .to_numpy(zero_copy_only=False)
                    .astype(np.uint8, copy=False)
                )
                total.update(event_time, target)
                update_split_stats(split, event_time, target, config)
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
        "training_data_contract.json",
    )
    upload_file_immutable(s3_client, contract_artifact_path, contract_uri)
    return manifest
```

### Vì sao chỉ query một lần?

Nếu query counts trước rồi query export sau, dbt có thể refresh giữa hai query. Code trên stream đúng một result set; counts/fingerprint được tính từ các block đã ghi. ClickHouse giữ snapshot đọc cho query đang chạy, còn file Parquet trở thành source of truth của run.

## 3. Giới hạn memory/disk

- `query_arrow_stream` đọc block, không load 5 triệu row vào RAM cùng lúc.
- File tạm nằm trong run output directory; cần đủ disk cho một Parquet snapshot.
- `max_rows_to_read=10_000_000` của `fraudguard_ml_reader_role` hiện đủ PaySim nhưng phải được theo dõi nếu dataset tăng.
- P0 dùng một file. Khi file quá lớn, chuyển sang `ParquetWriter` rotation theo `event_date`; manifest chứa danh sách object + SHA từng object.

## 4. Tests phase 2

Tối thiểu test:

```python
def test_population_query_is_bounded_and_parameterized(config):
    query, parameters = build_population_query(config)
    assert "event_time <= {test_end:DateTime64(3, 'UTC')}" in query
    assert config.split.test_end not in query
    assert parameters == {"test_end": config.split.test_end}


def test_snapshot_rejects_existing_destination(tmp_path, config):
    destination = tmp_path / "data.parquet"
    destination.write_bytes(b"existing")
    with pytest.raises(SnapshotError, match="overwrite"):
        stream_snapshot(fake_client, config, destination)


def test_immutable_upload_reuses_same_hash(s3_client, tmp_path):
    source = tmp_path / "data.parquet"
    source.write_bytes(b"same")
    first = upload_file_immutable(s3_client, source, TEST_URI)
    second = upload_file_immutable(s3_client, source, TEST_URI)
    assert first == second


def test_immutable_upload_rejects_different_content(s3_client, tmp_path):
    source = tmp_path / "data.parquet"
    source.write_bytes(b"first")
    upload_file_immutable(s3_client, source, TEST_URI)
    source.write_bytes(b"second")
    with pytest.raises(ArtifactError, match="overwrite"):
        upload_file_immutable(s3_client, source, TEST_URI)
```

Mock Arrow stream phải có ít nhất một row/fraud cho mỗi split. Test manifest reconcile count và xác minh `snapshot_sha256 == sha256_file(data.parquet)`.

## Acceptance phase 2

- Contract fail thì không query/export.
- Một snapshot chỉ thực hiện một population query.
- Không có object overwrite im lặng.
- Local và MinIO SHA giống nhau.
- Manifest có static label policy, không có label cutoff.
- Tổng count bằng tổng ba split.
