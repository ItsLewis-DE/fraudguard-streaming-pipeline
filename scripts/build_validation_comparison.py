"""Validate a Phase-4 matrix and build its validation comparison artifacts."""

from __future__ import annotations

import argparse
import json
import math
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from fraudguard_ml.artifacts import ArtifactError, sha256_file
from fraudguard_ml.config import load_yaml_config
from fraudguard_ml.dataset_manifest import DatasetManifest, load_manifest
from fraudguard_ml.experiment_config import ExperimentConfig
from fraudguard_ml.io_utils import write_json_immutable


@dataclass(frozen=True)
class CandidateSpec:
    candidate_id: str
    expected_model: str
    feature_set: str
    config_path: Path


CANDIDATES = (
    CandidateSpec(
        candidate_id="A",
        expected_model="logistic_regression",
        feature_set="baseline",
        config_path=Path("configs/training_baseline.yml"),
    ),
    CandidateSpec(
        candidate_id="B",
        expected_model="xgboost",
        feature_set="baseline",
        config_path=Path("configs/training_xgboost_baseline.yml"),
    ),
    CandidateSpec(
        candidate_id="C",
        expected_model="logistic_regression",
        feature_set="balance",
        config_path=Path("configs/training_challenger_balance.yml"),
    ),
    CandidateSpec(
        candidate_id="D",
        expected_model="xgboost",
        feature_set="balance",
        config_path=Path("configs/training_xgboost_balance.yml"),
    ),
)


class ComparisonError(RuntimeError):
    """Phase-4 artifacts cannot support a fair comparison."""


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text("utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ComparisonError(f"cannot read JSON artifact: {path}") from exc
    if not isinstance(payload, dict):
        raise ComparisonError(f"JSON artifact must contain an object: {path}")
    return payload


def require_number(payload: dict[str, Any], key: str) -> float:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ComparisonError(f"metric {key!r} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ComparisonError(f"metric {key!r} must be finite")
    return number


def split_contract(manifest: DatasetManifest) -> dict[str, Any]:
    return {
        "source_relation": manifest.source_relation,
        "label_policy": manifest.label_policy,
        "target_column": manifest.target_column,
        "split": manifest.split.model_dump(mode="json"),
        "split_statistics": manifest.split_statistics.model_dump(mode="json"),
        "dbt_manifest_sha256": manifest.dbt_manifest_sha256,
        "contract_artifact_sha256": manifest.contract_artifact_sha256,
    }


def write_csv_immutable(path: Path, frame: pd.DataFrame) -> None:
    if path.exists():
        raise ArtifactError(f"refusing to overwrite comparison artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary_path = Path(stream.name)
            frame.to_csv(stream, index=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    except OSError as exc:
        raise ArtifactError(f"cannot write comparison artifact: {path}") from exc
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def build_candidate_row(
    *,
    repository_root: Path,
    run_root: Path,
    spec: CandidateSpec,
) -> tuple[dict[str, Any], DatasetManifest, ExperimentConfig]:
    config_path = repository_root / spec.config_path
    config = load_yaml_config(config_path, ExperimentConfig)
    candidate_root = run_root / "candidates" / spec.candidate_id
    manifest_path = candidate_root / "experiment" / "dataset_manifest.json"
    metrics_path = candidate_root / "model" / "validation_metrics.json"

    manifest = load_manifest(manifest_path)
    metrics = load_json(metrics_path)
    metadata = metrics.get("model_metadata")
    if not isinstance(metadata, dict):
        raise ComparisonError(
            f"candidate {spec.candidate_id}: model_metadata must be an object"
        )

    model_kind = metadata.get("model_kind")
    if config.model.kind != spec.expected_model or model_kind != spec.expected_model:
        raise ComparisonError(
            f"candidate {spec.candidate_id}: unexpected model kind"
        )
    if manifest.feature_list != config.dataset.feature_columns:
        raise ComparisonError(
            f"candidate {spec.candidate_id}: manifest/config feature mismatch"
        )
    if manifest.experiment_name != config.experiment_name:
        raise ComparisonError(
            f"candidate {spec.candidate_id}: experiment name mismatch"
        )
    if manifest.source_relation != config.dataset.relation:
        raise ComparisonError(
            f"candidate {spec.candidate_id}: source relation mismatch"
        )
    if manifest.label_policy != config.snapshot.label_policy:
        raise ComparisonError(
            f"candidate {spec.candidate_id}: label policy mismatch"
        )
    if manifest.training_config_sha256 != sha256_file(config_path):
        raise ComparisonError(
            f"candidate {spec.candidate_id}: training config hash mismatch"
        )
    if metrics.get("population_fingerprint") != manifest.population_fingerprint:
        raise ComparisonError(
            f"candidate {spec.candidate_id}: metrics population mismatch"
        )
    if metrics.get("dataset_manifest_sha256") != sha256_file(manifest_path):
        raise ComparisonError(
            f"candidate {spec.candidate_id}: metrics manifest hash mismatch"
        )
    if config.runtime.random_seed != 42:
        raise ComparisonError(
            f"candidate {spec.candidate_id}: random seed must be 42"
        )

    train_rows = int(require_number(metrics, "train_rows"))
    train_fraud = int(require_number(metrics, "train_fraud"))
    training_seconds = require_number(metrics, "training_seconds")
    if train_rows != manifest.split_statistics.train.row_count:
        raise ComparisonError(
            f"candidate {spec.candidate_id}: train row count mismatch"
        )
    if train_fraud != manifest.split_statistics.train.fraud_count:
        raise ComparisonError(
            f"candidate {spec.candidate_id}: train fraud count mismatch"
        )
    if training_seconds < 0.0:
        raise ComparisonError(
            f"candidate {spec.candidate_id}: negative training duration"
        )

    best_iteration = metadata.get("best_iteration")
    scale_pos_weight = metadata.get("scale_pos_weight")
    if spec.expected_model == "logistic_regression":
        if best_iteration is not None or scale_pos_weight is not None:
            raise ComparisonError(
                f"candidate {spec.candidate_id}: invalid Logistic metadata"
            )
    else:
        if not isinstance(config.model, XGBoostConfig):
            raise ComparisonError(
                f"candidate {spec.candidate_id}: XGBoost config required"
            )
        if isinstance(best_iteration, bool) or not isinstance(best_iteration, int):
            raise ComparisonError(
                f"candidate {spec.candidate_id}: best_iteration must be int"
            )
        if not 0 <= best_iteration < config.model.n_estimators:
            raise ComparisonError(
                f"candidate {spec.candidate_id}: best_iteration outside range"
            )
        if isinstance(scale_pos_weight, bool) or not isinstance(
            scale_pos_weight,
            (int, float),
        ):
            raise ComparisonError(
                f"candidate {spec.candidate_id}: scale_pos_weight must be numeric"
            )
        if train_fraud <= 0:
            raise ComparisonError(
                f"candidate {spec.candidate_id}: train fraud must be positive"
            )
        expected_weight = (
            (train_rows - train_fraud) / train_fraud
            if config.model.imbalance_strategy == "train_ratio"
            else 1.0
        )
        if not math.isclose(
            float(scale_pos_weight),
            expected_weight,
            rel_tol=1e-12,
            abs_tol=0.0,
        ):
            raise ComparisonError(
                f"candidate {spec.candidate_id}: scale_pos_weight mismatch"
            )

    threshold = require_number(metrics, "threshold")
    pr_auc = require_number(metrics, "pr_auc")
    roc_auc = require_number(metrics, "roc_auc")
    precision = require_number(metrics, "precision")
    recall = require_number(metrics, "recall")
    f1 = require_number(metrics, "f1")
    alert_rate = require_number(metrics, "alert_rate")
    threshold_selection = metrics.get("threshold_selection")
    if not isinstance(threshold_selection, dict):
        raise ComparisonError(
            f"candidate {spec.candidate_id}: threshold_selection must be an object"
        )
    strategy_result = threshold_selection.get("strategy_result")
    if strategy_result not in {
        "max_recall_at_min_precision",
        "fallback_max_f1",
    }:
        raise ComparisonError(
            f"candidate {spec.candidate_id}: invalid threshold strategy result"
        )
    selected_precision = require_number(
        threshold_selection,
        "validation_precision",
    )
    selected_recall = require_number(
        threshold_selection,
        "validation_recall",
    )
    if not math.isclose(
        selected_precision,
        precision,
        rel_tol=1e-12,
        abs_tol=1e-12,
    ):
        raise ComparisonError(
            f"candidate {spec.candidate_id}: selected precision mismatch"
        )
    if not math.isclose(
        selected_recall,
        recall,
        rel_tol=1e-12,
        abs_tol=1e-12,
    ):
        raise ComparisonError(
            f"candidate {spec.candidate_id}: selected recall mismatch"
        )
    for name, value in (
        ("threshold", threshold),
        ("pr_auc", pr_auc),
        ("roc_auc", roc_auc),
        ("precision", precision),
        ("recall", recall),
        ("f1", f1),
        ("alert_rate", alert_rate),
    ):
        if not 0.0 <= value <= 1.0:
            raise ComparisonError(
                f"candidate {spec.candidate_id}: {name} outside [0, 1]"
            )

    row = {
        "candidate_id": spec.candidate_id,
        "model": spec.expected_model,
        "feature_set": spec.feature_set,
        "population_fingerprint": manifest.population_fingerprint,
        "train_rows": train_rows,
        "train_fraud": train_fraud,
        "best_iteration": best_iteration,
        "scale_pos_weight": scale_pos_weight,
        "threshold": threshold,
        "threshold_strategy_result": strategy_result,
        "validation_pr_auc": pr_auc,
        "validation_roc_auc": roc_auc,
        "validation_precision": precision,
        "validation_recall": recall,
        "validation_f1": f1,
        "validation_alert_rate": alert_rate,
        "training_seconds": training_seconds,
        "eligible_min_precision": (
            strategy_result == "max_recall_at_min_precision"
            and precision >= config.evaluation.min_precision
        ),
    }
    return row, manifest, config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--run-root", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repository_root = args.repository_root.resolve()
    run_root = args.run_root.resolve()

    rows: list[dict[str, Any]] = []
    manifests: list[DatasetManifest] = []
    configs: list[ExperimentConfig] = []
    for spec in CANDIDATES:
        row, manifest, config = build_candidate_row(
            repository_root=repository_root,
            run_root=run_root,
            spec=spec,
        )
        rows.append(row)
        manifests.append(manifest)
        configs.append(config)

    fingerprints = {manifest.population_fingerprint for manifest in manifests}
    if len(fingerprints) != 1:
        raise ComparisonError(f"population fingerprints differ: {fingerprints}")

    run_ids = {manifest.run_id for manifest in manifests}
    if len(run_ids) != 1:
        raise ComparisonError(f"candidate run IDs differ: {run_ids}")

    contracts = [split_contract(manifest) for manifest in manifests]
    if any(contract != contracts[0] for contract in contracts[1:]):
        raise ComparisonError("candidate split/lineage contracts differ")

    prediction_points = {config.dataset.prediction_point for config in configs}
    threshold_policies = {
        (
            config.evaluation.threshold_strategy,
            config.evaluation.min_precision,
        )
        for config in configs
    }
    if prediction_points != {"post_ledger_update"}:
        raise ComparisonError("candidate prediction points differ")
    if threshold_policies != {("max_recall_at_min_precision", 0.10)}:
        raise ComparisonError("candidate threshold policies differ")

    frame = pd.DataFrame(rows).sort_values("candidate_id").reset_index(drop=True)
    if frame["candidate_id"].tolist() != ["A", "B", "C", "D"]:
        raise ComparisonError("comparison must contain candidates A, B, C, D")

    comparison_root = run_root / "comparison"
    write_csv_immutable(
        comparison_root / "validation_comparison.csv",
        frame,
    )
    write_json_immutable(
        comparison_root / "experiment_invariants.json",
        {
            "experiment_invariants_schema_version": 1,
            "candidate_ids": ["A", "B", "C", "D"],
            "run_id": next(iter(run_ids)),
            "population_fingerprint": next(iter(fingerprints)),
            "shared_contract": contracts[0],
            "prediction_point": "post_ledger_update",
            "threshold_strategy": "max_recall_at_min_precision",
            "minimum_precision": 0.10,
            "random_seed": 42,
            "test_accessed": False,
        },
    )
    print(frame.to_string(index=False))


if __name__ == "__main__":
    main()
