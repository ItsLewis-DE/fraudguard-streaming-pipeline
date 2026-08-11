# Phase 3 — Loader, temporal split và diagnostics

Phase này chứng minh trainer đang đọc đúng Parquet artifact, rồi tái tạo ba split bằng boundaries trong manifest.

## 1. Dataset loader

Tạo `ml/src/fraudguard_ml/dataset_loader.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet as pq
from botocore.client import BaseClient

from fraudguard_ml.artifacts import sha256_file
from fraudguard_ml.dataset_manifest import DatasetManifest, ManifestError
from fraudguard_ml.experiment_config import ExperimentConfig, parse_utc
from fraudguard_ml.object_storage import download_file


@dataclass(frozen=True)
class FrameSplit:
    features: pd.DataFrame
    target: pd.Series
    keys: pd.DataFrame
    event_time: pd.Series


@dataclass(frozen=True)
class DatasetSplits:
    train: FrameSplit
    validation: FrameSplit
    test: FrameSplit


def verify_manifest_config(
    manifest: DatasetManifest,
    config: ExperimentConfig,
) -> None:
    if manifest.source_relation != config.dataset.relation:
        raise ManifestError("manifest relation does not match config")
    if manifest.feature_list != config.dataset.feature_columns:
        raise ManifestError("manifest feature order does not match config")
    if manifest.target_column != config.dataset.target_column:
        raise ManifestError("manifest target does not match config")
    if manifest.label_policy != "static_final_labels":
        raise ManifestError("unsupported label policy")
    boundaries = (
        manifest.split.train_end,
        manifest.split.validation_end,
        manifest.split.test_end,
    )
    configured = (
        config.split.train_end,
        config.split.validation_end,
        config.split.test_end,
    )
    if boundaries != configured:
        raise ManifestError("manifest split boundaries do not match config")


def materialize_snapshot(
    *,
    s3_client: BaseClient,
    manifest: DatasetManifest,
    cache_dir: Path,
) -> Path:
    destination = (
        cache_dir / manifest.experiment_name / manifest.run_id / "data.parquet"
    )
    if destination.exists():
        if sha256_file(destination) != manifest.snapshot_sha256:
            raise ManifestError("cached snapshot hash does not match manifest")
        return destination
    download_file(s3_client, manifest.snapshot_uri, destination)
    if sha256_file(destination) != manifest.snapshot_sha256:
        destination.unlink(missing_ok=True)
        raise ManifestError("downloaded snapshot hash does not match manifest")
    if destination.stat().st_size != manifest.snapshot_size_bytes:
        destination.unlink(missing_ok=True)
        raise ManifestError("downloaded snapshot size does not match manifest")
    return destination


def read_one_split(
    *,
    snapshot_path: Path,
    config: ExperimentConfig,
    filters: list[tuple[str, str, Any]],
) -> FrameSplit:
    columns = list(
        dict.fromkeys(
            (
                *config.dataset.id_columns,
                "event_time",
                *config.dataset.feature_columns,
                config.dataset.target_column,
            )
        )
    )
    table = pq.read_table(snapshot_path, columns=columns, filters=filters)
    frame = table.to_pandas()
    if frame.empty:
        raise ManifestError("temporal split is empty")
    target = frame.pop(config.dataset.target_column).astype("uint8")
    keys = frame.loc[:, list(config.dataset.id_columns)].copy()
    event_time = pd.to_datetime(frame.pop("event_time"), utc=True)
    features = frame.loc[:, list(config.dataset.feature_columns)].copy()
    return FrameSplit(
        features=features,
        target=target,
        keys=keys,
        event_time=event_time,
    )


def load_dataset_splits(
    *,
    snapshot_path: Path,
    manifest: DatasetManifest,
    config: ExperimentConfig,
) -> DatasetSplits:
    verify_manifest_config(manifest, config)
    train_end = parse_utc(manifest.split.train_end)
    validation_end = parse_utc(manifest.split.validation_end)
    test_end = parse_utc(manifest.split.test_end)
    train = read_one_split(
        snapshot_path=snapshot_path,
        config=config,
        filters=[("event_time", "<=", train_end)],
    )
    validation = read_one_split(
        snapshot_path=snapshot_path,
        config=config,
        filters=[
            ("event_time", ">", train_end),
            ("event_time", "<=", validation_end),
        ],
    )
    test = read_one_split(
        snapshot_path=snapshot_path,
        config=config,
        filters=[
            ("event_time", ">", validation_end),
            ("event_time", "<=", test_end),
        ],
    )
    splits = DatasetSplits(train=train, validation=validation, test=test)
    verify_split_statistics(splits, manifest)
    return splits


def verify_split_statistics(
    splits: DatasetSplits,
    manifest: DatasetManifest,
) -> None:
    for name, frame_split in (
        ("train", splits.train),
        ("validation", splits.validation),
        ("test", splits.test),
    ):
        expected = getattr(manifest.split_statistics, name)
        actual_rows = len(frame_split.target)
        actual_fraud = int(frame_split.target.sum())
        if actual_rows != expected.row_count or actual_fraud != expected.fraud_count:
            raise ManifestError(f"{name} statistics do not match manifest")
        if frame_split.keys.duplicated().any():
            raise ManifestError(f"{name} contains duplicate business keys")
    key_sets = {
        name: set(map(tuple, value.keys.itertuples(index=False, name=None)))
        for name, value in (
            ("train", splits.train),
            ("validation", splits.validation),
            ("test", splits.test),
        )
    }
    if key_sets["train"] & key_sets["validation"]:
        raise ManifestError("train and validation keys overlap")
    if key_sets["train"] & key_sets["test"]:
        raise ManifestError("train and test keys overlap")
    if key_sets["validation"] & key_sets["test"]:
        raise ManifestError("validation and test keys overlap")
```

### Memory note

`set` của hàng triệu key có thể tốn RAM. Data contract đã chứng minh key unique và temporal predicates vốn không overlap, nên production loader có thể thay block `key_sets` bằng một integration audit chạy ở ClickHouse/Arrow. Giữ check này cho smoke/subsample; không làm process vượt `memory_limit_gib`.

## 2. Diagnostics

Tạo `ml/src/fraudguard_ml/split_diagnostics.py`:

```python
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import ks_2samp

from fraudguard_ml.artifacts import write_json_immutable
from fraudguard_ml.dataset_loader import DatasetSplits, FrameSplit


EPSILON = 1e-6


def basic_split_summary(split: FrameSplit) -> dict[str, Any]:
    row_count = len(split.target)
    fraud_count = int(split.target.sum())
    return {
        "row_count": row_count,
        "fraud_count": fraud_count,
        "fraud_rate": fraud_count / row_count if row_count else 0.0,
        "min_event_time": split.event_time.min().isoformat(),
        "max_event_time": split.event_time.max().isoformat(),
        "missing_rate": {
            column: float(value)
            for column, value in split.features.isna().mean().items()
        },
    }


def numeric_summary(series: pd.Series) -> dict[str, float | None]:
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().sum() == 0:
        return {name: None for name in ("mean", "std", "p05", "p50", "p95")}
    return {
        "mean": float(numeric.mean()),
        "std": float(numeric.std()),
        "p05": float(numeric.quantile(0.05)),
        "p50": float(numeric.quantile(0.50)),
        "p95": float(numeric.quantile(0.95)),
    }


def categorical_distribution(series: pd.Series) -> dict[str, float]:
    normalized = series.fillna("<MISSING>").astype(str).value_counts(normalize=True)
    return {str(key): float(value) for key, value in normalized.items()}


def population_stability_index(
    reference: pd.Series,
    comparison: pd.Series,
    bins: int = 10,
) -> float | None:
    ref = pd.to_numeric(reference, errors="coerce").dropna().to_numpy()
    cmp = pd.to_numeric(comparison, errors="coerce").dropna().to_numpy()
    if len(ref) == 0 or len(cmp) == 0:
        return None
    edges = np.unique(np.quantile(ref, np.linspace(0.0, 1.0, bins + 1)))
    if len(edges) < 3:
        return 0.0
    edges[0], edges[-1] = -np.inf, np.inf
    ref_counts, _ = np.histogram(ref, bins=edges)
    cmp_counts, _ = np.histogram(cmp, bins=edges)
    ref_rate = np.maximum(ref_counts / ref_counts.sum(), EPSILON)
    cmp_rate = np.maximum(cmp_counts / cmp_counts.sum(), EPSILON)
    return float(np.sum((cmp_rate - ref_rate) * np.log(cmp_rate / ref_rate)))


def numeric_drift(
    reference: pd.Series, comparison: pd.Series
) -> dict[str, float | None]:
    ref = pd.to_numeric(reference, errors="coerce").dropna()
    cmp = pd.to_numeric(comparison, errors="coerce").dropna()
    if ref.empty or cmp.empty:
        return {"psi": None, "ks_statistic": None, "ks_pvalue": None}
    ks = ks_2samp(ref, cmp)
    return {
        "psi": population_stability_index(ref, cmp),
        "ks_statistic": float(ks.statistic),
        "ks_pvalue": float(ks.pvalue),
    }


def build_split_diagnostics(
    splits: DatasetSplits,
    *,
    numeric_columns: tuple[str, ...],
    categorical_columns: tuple[str, ...],
) -> dict[str, Any]:
    split_map: Mapping[str, FrameSplit] = {
        "train": splits.train,
        "validation": splits.validation,
        "test": splits.test,
    }
    report: dict[str, Any] = {
        "splits": {
            name: basic_split_summary(value) for name, value in split_map.items()
        },
        "numeric": {},
        "categorical": {},
    }
    for column in numeric_columns:
        report["numeric"][column] = {
            "summary": {
                name: numeric_summary(value.features[column])
                for name, value in split_map.items()
            },
            "drift_from_train": {
                "validation": numeric_drift(
                    splits.train.features[column],
                    splits.validation.features[column],
                ),
                "test": numeric_drift(
                    splits.train.features[column],
                    splits.test.features[column],
                ),
            },
        }
    for column in categorical_columns:
        report["categorical"][column] = {
            name: categorical_distribution(value.features[column])
            for name, value in split_map.items()
        }
    return report


def write_diagnostics(path: Path, report: dict[str, Any]) -> None:
    write_json_immutable(path, report)
```

## 3. Gate diagnostics

Không tự động fail chỉ vì KS p-value nhỏ: với hàng triệu row, chênh lệch nhỏ cũng có thể significant. P0 chỉ fail các invariant:

```python
def assert_diagnostic_invariants(report: dict[str, Any]) -> None:
    for name, summary in report["splits"].items():
        if summary["row_count"] == 0:
            raise ValueError(f"{name} split is empty")
        if summary["fraud_count"] == 0:
            raise ValueError(f"{name} split has no fraud positives")
        if any(rate > 0.0 for rate in summary["missing_rate"].values()):
            raise ValueError(f"{name} split contains missing model features")
```

PSI/KS là warning và review evidence. Không random split lại chỉ để làm distribution giống nhau.

## 4. Tests phase 3

- Manifest feature order khác config phải fail.
- Parquet SHA/size khác manifest phải fail và xóa download hỏng.
- Boundaries tạo đúng row ở cạnh `train_end`/`validation_end`/`test_end`.
- Duplicate/overlap key phải fail trong smoke test.
- Split statistics phải reconcile manifest.
- PSI bằng 0 cho hai distribution giống nhau, lớn hơn 0 khi shift.
- Diagnostics không dùng dataframe ngoài snapshot loader.

## Acceptance phase 3

- Cùng Parquet + manifest luôn tạo cùng split.
- Loader không có code query ClickHouse.
- Diagnostics JSON được ghi immutable.
- Không fit preprocessing hoặc chọn feature ở phase này.
