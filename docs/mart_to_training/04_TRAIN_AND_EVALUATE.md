# Phase 4 — Training, threshold selection và final evaluation

Phase này dùng train/validation để tạo model bundle. Test được evaluate bằng command riêng sau khi bundle đã khóa threshold.

## 1. Training implementation

Tạo `ml/src/fraudguard_ml/training.py`:

```python
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from numpy.typing import NDArray
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from fraudguard_ml.artifacts import ArtifactError, sha256_file, write_json_immutable
from fraudguard_ml.dataset_loader import DatasetSplits
from fraudguard_ml.dataset_manifest import DatasetManifest
from fraudguard_ml.experiment_config import ExperimentConfig


class TrainingError(RuntimeError):
    """Model training cannot produce a trustworthy artifact."""


def feature_groups(config: ExperimentConfig) -> tuple[list[str], list[str]]:
    categorical = [
        column
        for column in config.dataset.feature_columns
        if column == "transaction_type"
    ]
    numeric = [
        column for column in config.dataset.feature_columns if column not in categorical
    ]
    return categorical, numeric


def normalize_feature_types(
    frame: pd.DataFrame,
    config: ExperimentConfig,
) -> pd.DataFrame:
    normalized = frame.loc[:, list(config.dataset.feature_columns)].copy()
    categorical, numeric = feature_groups(config)
    for column in categorical:
        normalized[column] = normalized[column].astype("string")
    for column in numeric:
        normalized[column] = pd.to_numeric(normalized[column], errors="raise").astype(
            "float64"
        )
    return normalized


def build_pipeline(config: ExperimentConfig) -> Pipeline:
    categorical, numeric = feature_groups(config)
    categorical_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="most_frequent")),
            (
                "one_hot",
                OneHotEncoder(handle_unknown="ignore", sparse_output=True),
            ),
        ]
    )
    numeric_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]
    )
    transformers: list[tuple[str, Pipeline, list[str]]] = []
    if categorical:
        transformers.append(("categorical", categorical_pipeline, categorical))
    if numeric:
        transformers.append(("numeric", numeric_pipeline, numeric))
    preprocessing = ColumnTransformer(
        transformers=transformers,
        remainder="drop",
        verbose_feature_names_out=True,
    )
    estimator = LogisticRegression(
        C=config.model.regularization_c,
        class_weight=config.model.class_weight,
        max_iter=config.model.max_iter,
        random_state=config.runtime.random_seed,
        solver="lbfgs",
    )
    return Pipeline(
        steps=[
            ("preprocessing", preprocessing),
            ("estimator", estimator),
        ]
    )


def select_threshold(
    target: pd.Series,
    probability: NDArray[np.float64],
    *,
    min_precision: float,
) -> tuple[float, dict[str, float | str]]:
    precision, recall, thresholds = precision_recall_curve(target, probability)
    if len(thresholds) == 0:
        raise TrainingError("validation probabilities cannot produce a threshold")
    candidate_indices = np.flatnonzero(precision[:-1] >= min_precision)
    if len(candidate_indices):
        candidate_recalls = recall[:-1][candidate_indices]
        index = int(candidate_indices[np.argmax(candidate_recalls)])
        reason = "max_recall_at_min_precision"
    else:
        denominator = precision[:-1] + recall[:-1]
        f1_values = np.divide(
            2 * precision[:-1] * recall[:-1],
            denominator,
            out=np.zeros_like(denominator),
            where=denominator > 0,
        )
        index = int(np.argmax(f1_values))
        reason = "fallback_max_f1"
    return float(thresholds[index]), {
        "strategy_result": reason,
        "validation_precision": float(precision[index]),
        "validation_recall": float(recall[index]),
    }


def binary_metrics(
    target: pd.Series,
    probability: NDArray[np.float64],
    threshold: float,
) -> dict[str, Any]:
    prediction = (probability >= threshold).astype(np.uint8)
    tn, fp, fn, tp = confusion_matrix(target, prediction, labels=[0, 1]).ravel()
    return {
        "threshold": threshold,
        "pr_auc": float(average_precision_score(target, probability)),
        "roc_auc": float(roc_auc_score(target, probability)),
        "precision": float(precision_score(target, prediction, zero_division=0)),
        "recall": float(recall_score(target, prediction, zero_division=0)),
        "f1": float(f1_score(target, prediction, zero_division=0)),
        "confusion_matrix": {
            "true_negative": int(tn),
            "false_positive": int(fp),
            "false_negative": int(fn),
            "true_positive": int(tp),
        },
        "alert_rate": float(prediction.mean()),
        "fraud_capture_rate": float(tp / (tp + fn)) if tp + fn else 0.0,
    }


def write_joblib_immutable(destination: Path, payload: dict[str, Any]) -> None:
    if destination.exists():
        raise ArtifactError(f"refusing to overwrite model artifact: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=destination.parent,
            prefix=f".{destination.name}",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary_path = Path(stream.name)
        joblib.dump(payload, temporary_path)
        with temporary_path.open("rb+") as stream:
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, destination)
        temporary_path = None
    except OSError as exc:
        raise ArtifactError(f"cannot atomically write model: {destination}") from exc
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def train_and_select_threshold(
    *,
    splits: DatasetSplits,
    config: ExperimentConfig,
    manifest: DatasetManifest,
    manifest_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    model_path = output_dir / "model_bundle.joblib"
    metrics_path = output_dir / "validation_metrics.json"
    train_features = normalize_feature_types(splits.train.features, config)
    validation_features = normalize_feature_types(splits.validation.features, config)
    pipeline = build_pipeline(config)
    pipeline.fit(train_features, splits.train.target)
    probability = pipeline.predict_proba(validation_features)[:, 1]
    threshold, selection = select_threshold(
        splits.validation.target,
        probability,
        min_precision=config.evaluation.min_precision,
    )
    validation_metrics = {
        **binary_metrics(splits.validation.target, probability, threshold),
        "threshold_selection": selection,
        "dataset_manifest_sha256": sha256_file(manifest_path),
        "population_fingerprint": manifest.population_fingerprint,
    }
    bundle = {
        "bundle_schema_version": 1,
        "pipeline": pipeline,
        "threshold": threshold,
        "feature_list": list(config.dataset.feature_columns),
        "target_column": config.dataset.target_column,
        "prediction_point": config.dataset.prediction_point,
        "label_policy": manifest.label_policy,
        "experiment_name": config.experiment_name,
        "run_id": manifest.run_id,
        "dataset_manifest_sha256": sha256_file(manifest_path),
        "dataset_manifest_uri": manifest.snapshot_uri.rsplit("/", 1)[0]
        + "/dataset_manifest.json",
        "population_fingerprint": manifest.population_fingerprint,
        "config": config.model_dump(mode="json"),
        "validation_metrics": validation_metrics,
    }
    write_joblib_immutable(model_path, bundle)
    write_json_immutable(metrics_path, validation_metrics)
    return {
        "model_path": str(model_path),
        "model_sha256": sha256_file(model_path),
        "validation_metrics_path": str(metrics_path),
        "threshold": threshold,
    }
```

Không load `joblib` từ nguồn không tin cậy; pickle/joblib có thể thực thi code khi deserialize.

## 2. Final evaluation

Tạo `ml/src/fraudguard_ml/evaluation.py`:

```python
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
```

Không gọi `select_threshold` trong `evaluation.py`. Threshold đã được khóa trong bundle.

## 3. Feature policy theo dự án

Baseline dùng các feature trước/sẵn tại prediction point:

```text
transaction_type
amount
origin_balance_before
destination_balance_before
```

Challenger hiện thêm after-balance/delta/residual. Vì prediction point là `post_ledger_update`, chúng có thể được thử nghiệm, nhưng report phải ghi rõ model chỉ áp dụng sau chốt sổ. Không được tái sử dụng bundle này cho pre-transaction authorization.

`step` là split/audit column và nằm trong forbidden feature list; không thêm vào estimator dù EDA có phân tích `step`.

## 4. So sánh baseline/challenger

Một comparison record nên lưu:

```json
{
  "baseline_run_id": "...",
  "challenger_run_id": "...",
  "same_population": true,
  "population_fingerprint": "xor64:...",
  "same_boundaries": true,
  "same_label_policy": true,
  "feature_change_is_intentional": true
}
```

Không yêu cầu manifest SHA giống nhau khi snapshot chứa feature list khác. Bắt buộc population fingerprint, row/fraud counts, boundaries và label policy giống nhau. Phương án tốt hơn là reuse một canonical snapshot có union feature columns cho cả hai run.

## 5. Tests phase 4

- Preprocessor chỉ fit train; unseen validation category không làm crash.
- `feature_list` order được bảo toàn.
- Threshold thỏa min precision khi có candidate.
- Không có candidate thì fallback max-F1 và ghi rõ reason.
- Model bundle ghi immutable, có manifest SHA/population fingerprint.
- Evaluation reject bundle từ manifest khác.
- Test evaluation không gọi threshold selector.
- Cùng snapshot/config/seed cho metric trong tolerance.
- `is_fraud`, ID, `event_time`, `step` không xuất hiện trong transformed feature inputs.

## Acceptance phase 4

- Train command không query ClickHouse.
- Test chưa được đụng tới trong training/threshold selection.
- Bundle đủ để inference lại với đúng feature order.
- Evaluation JSON truy ngược được model, manifest và snapshot.
