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