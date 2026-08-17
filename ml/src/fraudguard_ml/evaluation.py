from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib

from fraudguard_ml.artifacts import sha256_file, write_json_immutable
from fraudguard_ml.dataset_loader import FrameSplit
from fraudguard_ml.dataset_manifest import DatasetManifest, ManifestError
from fraudguard_ml.experiment_config import ExperimentConfig
from fraudguard_ml.training import binary_metrics, normalize_feature_types


def evaluate_test_split(
    *,
    test: FrameSplit,
    config: ExperimentConfig,
    manifest: DatasetManifest,
    manifest_path: Path,
    model_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    bundle = joblib.load(model_path)
    manifest_sha256 = sha256_file(manifest_path)
    if bundle.get("dataset_manifest_sha256") != manifest_sha256:
        raise ManifestError("model and evaluation manifest do not match")
    if tuple(bundle.get("feature_list", ())) != config.dataset.feature_columns:
        raise ManifestError("model feature order does not match config")
    if bundle.get("population_fingerprint") != manifest.population_fingerprint:
        raise ManifestError("model population fingerprint does not match manifest")
    features = normalize_feature_types(test.features, config)
    probability = bundle["pipeline"].predict_proba(features)[:, 1]
    metrics = binary_metrics(test.target, probability, float(bundle["threshold"]))
    result = {
        "evaluation_schema_version": 1,
        "experiment_name": config.experiment_name,
        "run_id": manifest.run_id,
        "split": "test",
        "metrics": metrics,
        "model_sha256": sha256_file(model_path),
        "dataset_manifest_sha256": manifest_sha256,
        "snapshot_sha256": manifest.snapshot_sha256,
        "population_fingerprint": manifest.population_fingerprint,
        "label_policy": manifest.label_policy,
    }
    write_json_immutable(output_path, result)
    return result