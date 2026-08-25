# Phase 3 — Tạo model interface chung

Tài liệu này hướng dẫn triển khai đầy đủ Phase 3 trong
[`XGBOOST_EXPERIMENT_ROADMAP.md`](XGBOOST_EXPERIMENT_ROADMAP.md).

## 1. Mục tiêu

Sau Phase 3, Logistic Regression và XGBoost phải dùng chung một modeling
interface:

```python
def fit_probability_model(
    config: ExperimentConfig,
    train: FrameSplit,
    validation: FrameSplit,
) -> FittedProbabilityModel:
    ...
```

Caller chỉ cần biết model đã fit hỗ trợ:

```python
probability = model.predict_proba(features)
metadata = model.metadata.to_dict()
```

Module `modeling.py` phải che giấu các khác biệt sau:

| Hành vi | Logistic Regression | XGBoost |
| --- | --- | --- |
| Categorical | Impute + one-hot | Impute + one-hot |
| Numeric missing | Median imputation | Median imputation |
| Numeric scaling | `StandardScaler` | Không scale |
| Imbalance | `class_weight="balanced"` | `scale_pos_weight` từ train |
| Validation khi fit | Không dùng | `eval_set` cho early stopping |
| CPU | Thread limits hiện tại | `tree_method="hist"`, `n_jobs` từ runtime |

`training.py` chịu trách nhiệm orchestration, threshold selection, metrics và ghi
artifact. `evaluation.py` chỉ load model rồi gọi `predict_proba`; không được chứa
nhánh `if model.kind == ...`.

Phase này **không** chạy ma trận experiment 2 × 2, không chọn winner và không dùng
test result để chỉnh hyperparameter. Những việc đó thuộc Phase 4–6.

## 2. Trạng thái trước Phase 3

Đã xác nhận trong repository tại thời điểm tạo tài liệu:

- [x] XGBoost 3.4.1 đang được khóa trong môi trường hiện tại.
- [x] `XGBClassifier.fit` hỗ trợ `eval_set` và `verbose`.
- [x] `LogisticRegressionConfig` và `XGBoostConfig` đã có.
- [x] Hai XGBoost YAML đã được tạo.
- [x] Bốn config đang dùng split 2h/4h/6h.
- [ ] Phase 2 config tests chưa được thêm vào `test_config.py`.
- [ ] `experiment_config.py` còn import Pydantic không dùng.
- [ ] `training.py` hiện tham chiếu `model_config` chưa được khai báo.
- [ ] Ruff và mypy chưa pass ở trạng thái hiện tại.

Trước khi đánh dấu Phase 3 hoàn thành, phải xử lý cả các lỗi kế thừa này. Không
được dùng Phase 3 để che việc Phase 2 chưa xanh.

## 3. Thiết kế module

### 3.1. Seam và adapters

Seam nằm tại `fraudguard_ml.modeling.fit_probability_model`:

```text
training.py
    |
    | fit_probability_model(config, train, validation)
    v
modeling.py
    ├── Logistic Regression adapter
    └── XGBoost adapter
            |
            v
    FittedProbabilityModel.predict_proba(features)
            |
            ├── training.py: validation probability
            └── evaluation.py: test probability
```

Đây là seam thật vì có hai adapters. Preprocessing, estimator construction,
early stopping và resolved metadata là implementation nội bộ của module.

### 3.2. Invariants của interface

`fit_probability_model` phải đảm bảo:

- chỉ fit preprocessor trên train features;
- chỉ tính `scale_pos_weight` từ train target;
- validation chỉ được transform, không được fit;
- validation chỉ phục vụ XGBoost early stopping;
- train và validation đều có hai class `0` và `1`;
- model kind không hỗ trợ bị reject bằng `ModelingError`;
- random seed và CPU threads lấy từ config;
- trả về model có thể serialize bằng joblib.

`FittedProbabilityModel.predict_proba` phải đảm bảo:

- giữ đúng feature order đã train;
- bỏ qua extra columns nhưng reject missing required columns;
- chuẩn hóa dtype giống lúc fit;
- trả array shape `(row_count, 2)`;
- probability hữu hạn và nằm trong `[0, 1]`.

## 4. Phạm vi file

Phase 3 cần tạo hoặc sửa:

```text
ml/src/fraudguard_ml/modeling.py
ml/src/fraudguard_ml/training.py
ml/src/fraudguard_ml/evaluation.py
ml/tests/test_modeling.py
ml/tests/test_training.py
ml/tests/test_config.py
ml/src/fraudguard_ml/experiment_config.py
```

Hai file cuối chỉ hoàn tất các phần còn thiếu của Phase 2. Không sửa DAG, snapshot,
temporal boundaries, notebook hoặc README trong phase này.

## 5. Thứ tự triển khai

### 5.1. Hoàn tất pre-flight Phase 2

- [ ] Thêm config tests từ tài liệu Phase 2.
- [ ] Xóa `PositiveFloat`, `PositiveInt` không còn dùng.
- [ ] Xác nhận cả bốn YAML load được.
- [ ] Ghi nhận lỗi `model_config` hiện tại trước khi refactor.

Import Pydantic đúng trong `experiment_config.py`:

```python
from pydantic import Field, field_validator, model_validator
```

Chạy:

```bash
cd /home/phongthanh/ML_Fraud_Banking

uv run pytest ml/tests/test_config.py --no-cov
uv run python - <<'PY'
from pathlib import Path

from fraudguard_ml.config import load_yaml_config
from fraudguard_ml.experiment_config import ExperimentConfig

for filename in (
    "training_baseline.yml",
    "training_challenger_balance.yml",
    "training_xgboost_baseline.yml",
    "training_xgboost_balance.yml",
):
    config = load_yaml_config(Path("configs") / filename, ExperimentConfig)
    print(filename, config.model.kind)
PY
```

### 5.2. Tạo `modeling.py`

- [ ] Tạo `ModelingError`.
- [ ] Tạo immutable `ModelMetadata`.
- [ ] Tạo `FittedProbabilityModel`.
- [ ] Tập trung feature normalization trong module này.
- [ ] Tạo Logistic Regression adapter.
- [ ] Tạo XGBoost adapter.
- [ ] Dispatch bằng discriminated config từ Phase 2.

Tạo file `ml/src/fraudguard_ml/modeling.py` với nội dung:

```python
"""Fit probability models behind one shared modeling interface."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
import pandas as pd
from numpy.typing import NDArray
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from xgboost import XGBClassifier

from fraudguard_ml.dataset_loader import FrameSplit
from fraudguard_ml.experiment_config import (
    ExperimentConfig,
    LogisticRegressionConfig,
    XGBoostConfig,
)

type ModelKind = Literal["logistic_regression", "xgboost"]
type ProbabilityEstimator = LogisticRegression | XGBClassifier


class ModelingError(RuntimeError):
    """A probability model cannot be fit or used safely."""


@dataclass(frozen=True)
class ModelMetadata:
    """Resolved model and preprocessing facts persisted with the artifact."""

    model_kind: ModelKind
    resolved_hyperparameters: dict[str, Any]
    numeric_scaling: Literal["standard", "none"]
    scale_pos_weight: float | None
    best_iteration: int | None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable copy of the metadata."""

        return {
            "model_kind": self.model_kind,
            "resolved_hyperparameters": dict(self.resolved_hyperparameters),
            "numeric_scaling": self.numeric_scaling,
            "scale_pos_weight": self.scale_pos_weight,
            "best_iteration": self.best_iteration,
        }


@dataclass(frozen=True)
class FittedProbabilityModel:
    """A fitted preprocessor and estimator exposed through one interface."""

    feature_columns: tuple[str, ...]
    categorical_columns: tuple[str, ...]
    numeric_columns: tuple[str, ...]
    preprocessor: ColumnTransformer
    estimator: ProbabilityEstimator
    metadata: ModelMetadata

    def predict_proba(
        self,
        features: pd.DataFrame,
    ) -> NDArray[np.float64]:
        """Transform features and return validated two-class probabilities."""

        normalized = _normalize_feature_types(
            features,
            feature_columns=self.feature_columns,
            categorical_columns=self.categorical_columns,
            numeric_columns=self.numeric_columns,
        )
        matrix = self.preprocessor.transform(normalized)
        probability = np.asarray(
            self.estimator.predict_proba(matrix),
            dtype=np.float64,
        )
        expected_shape = (len(normalized), 2)
        if probability.shape != expected_shape:
            raise ModelingError(
                "predict_proba returned shape "
                f"{probability.shape}, expected {expected_shape}"
            )
        if not np.isfinite(probability).all():
            raise ModelingError("predict_proba returned non-finite values")
        if ((probability < 0.0) | (probability > 1.0)).any():
            raise ModelingError("predict_proba returned values outside [0, 1]")
        return probability


def _feature_groups(
    config: ExperimentConfig,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    categorical = tuple(
        column
        for column in config.dataset.feature_columns
        if column == "transaction_type"
    )
    numeric = tuple(
        column
        for column in config.dataset.feature_columns
        if column not in categorical
    )
    return categorical, numeric


def _normalize_feature_types(
    frame: pd.DataFrame,
    *,
    feature_columns: tuple[str, ...],
    categorical_columns: tuple[str, ...],
    numeric_columns: tuple[str, ...],
) -> pd.DataFrame:
    missing = [column for column in feature_columns if column not in frame.columns]
    if missing:
        raise ModelingError(f"missing required feature columns: {missing}")
    normalized = frame.loc[:, list(feature_columns)].copy()
    for column in categorical_columns:
        normalized[column] = normalized[column].astype("string")
    for column in numeric_columns:
        try:
            normalized[column] = pd.to_numeric(
                normalized[column],
                errors="raise",
            ).astype("float64")
        except (TypeError, ValueError) as exc:
            raise ModelingError(
                f"feature column {column!r} cannot be converted to float64"
            ) from exc
    return normalized


def _build_preprocessor(
    *,
    categorical_columns: tuple[str, ...],
    numeric_columns: tuple[str, ...],
    scale_numeric: bool,
) -> ColumnTransformer:
    transformers: list[tuple[str, Pipeline, list[str]]] = []
    if categorical_columns:
        categorical_pipeline = Pipeline(
            steps=[
                ("imputer", SimpleImputer(strategy="most_frequent")),
                (
                    "one_hot",
                    OneHotEncoder(handle_unknown="ignore", sparse_output=True),
                ),
            ]
        )
        transformers.append(
            ("categorical", categorical_pipeline, list(categorical_columns))
        )
    if numeric_columns:
        numeric_steps: list[tuple[str, Any]] = [
            ("imputer", SimpleImputer(strategy="median"))
        ]
        if scale_numeric:
            numeric_steps.append(("scaler", StandardScaler()))
        numeric_pipeline = Pipeline(steps=numeric_steps)
        transformers.append(("numeric", numeric_pipeline, list(numeric_columns)))
    if not transformers:
        raise ModelingError("at least one feature column is required")
    return ColumnTransformer(
        transformers=transformers,
        remainder="drop",
        verbose_feature_names_out=True,
    )


def _validate_binary_target(target: pd.Series, *, split_name: str) -> None:
    if target.isna().any():
        raise ModelingError(f"{split_name} target contains null values")
    values = {int(value) for value in pd.unique(target)}
    if values != {0, 1}:
        raise ModelingError(
            f"{split_name} target must contain both binary classes, got {values}"
        )


def _calculate_scale_pos_weight(target: pd.Series) -> float:
    positive_count = int((target == 1).sum())
    negative_count = int((target == 0).sum())
    if positive_count == 0 or negative_count == 0:
        raise ModelingError(
            "train target must contain positives and negatives for class weighting"
        )
    return float(negative_count / positive_count)


def _fit_logistic_regression(
    *,
    config: ExperimentConfig,
    model_config: LogisticRegressionConfig,
    train: FrameSplit,
) -> FittedProbabilityModel:
    categorical, numeric = _feature_groups(config)
    preprocessor = _build_preprocessor(
        categorical_columns=categorical,
        numeric_columns=numeric,
        scale_numeric=True,
    )
    train_features = _normalize_feature_types(
        train.features,
        feature_columns=config.dataset.feature_columns,
        categorical_columns=categorical,
        numeric_columns=numeric,
    )
    train_matrix = preprocessor.fit_transform(train_features)
    estimator = LogisticRegression(
        C=model_config.regularization_c,
        class_weight=model_config.class_weight,
        max_iter=model_config.max_iter,
        random_state=config.runtime.random_seed,
        solver="lbfgs",
    )
    estimator.fit(train_matrix, train.target)
    metadata = ModelMetadata(
        model_kind="logistic_regression",
        resolved_hyperparameters={
            **model_config.model_dump(mode="json"),
            "random_state": config.runtime.random_seed,
            "solver": "lbfgs",
        },
        numeric_scaling="standard",
        scale_pos_weight=None,
        best_iteration=None,
    )
    return FittedProbabilityModel(
        feature_columns=config.dataset.feature_columns,
        categorical_columns=categorical,
        numeric_columns=numeric,
        preprocessor=preprocessor,
        estimator=estimator,
        metadata=metadata,
    )


def _fit_xgboost(
    *,
    config: ExperimentConfig,
    model_config: XGBoostConfig,
    train: FrameSplit,
    validation: FrameSplit,
) -> FittedProbabilityModel:
    categorical, numeric = _feature_groups(config)
    preprocessor = _build_preprocessor(
        categorical_columns=categorical,
        numeric_columns=numeric,
        scale_numeric=False,
    )
    train_features = _normalize_feature_types(
        train.features,
        feature_columns=config.dataset.feature_columns,
        categorical_columns=categorical,
        numeric_columns=numeric,
    )
    validation_features = _normalize_feature_types(
        validation.features,
        feature_columns=config.dataset.feature_columns,
        categorical_columns=categorical,
        numeric_columns=numeric,
    )
    train_matrix = preprocessor.fit_transform(train_features)
    validation_matrix = preprocessor.transform(validation_features)
    scale_pos_weight = (
        _calculate_scale_pos_weight(train.target)
        if model_config.imbalance_strategy == "train_ratio"
        else 1.0
    )
    estimator = XGBClassifier(
        objective=model_config.objective,
        eval_metric=model_config.eval_metric,
        tree_method=model_config.tree_method,
        n_estimators=model_config.n_estimators,
        learning_rate=model_config.learning_rate,
        max_depth=model_config.max_depth,
        min_child_weight=model_config.min_child_weight,
        subsample=model_config.subsample,
        colsample_bytree=model_config.colsample_bytree,
        reg_alpha=model_config.reg_alpha,
        reg_lambda=model_config.reg_lambda,
        early_stopping_rounds=model_config.early_stopping_rounds,
        scale_pos_weight=scale_pos_weight,
        random_state=config.runtime.random_seed,
        n_jobs=config.runtime.max_cpu_threads,
        verbosity=0,
    )
    estimator.fit(
        train_matrix,
        train.target,
        eval_set=[(validation_matrix, validation.target)],
        verbose=False,
    )
    best_iteration = int(estimator.best_iteration)
    metadata = ModelMetadata(
        model_kind="xgboost",
        resolved_hyperparameters={
            **model_config.model_dump(mode="json"),
            "scale_pos_weight": scale_pos_weight,
            "random_state": config.runtime.random_seed,
            "n_jobs": config.runtime.max_cpu_threads,
        },
        numeric_scaling="none",
        scale_pos_weight=scale_pos_weight,
        best_iteration=best_iteration,
    )
    return FittedProbabilityModel(
        feature_columns=config.dataset.feature_columns,
        categorical_columns=categorical,
        numeric_columns=numeric,
        preprocessor=preprocessor,
        estimator=estimator,
        metadata=metadata,
    )


def fit_probability_model(
    config: ExperimentConfig,
    train: FrameSplit,
    validation: FrameSplit,
) -> FittedProbabilityModel:
    """Fit the configured model without leaking validation into preprocessing."""

    _validate_binary_target(train.target, split_name="train")
    _validate_binary_target(validation.target, split_name="validation")
    model_config = config.model
    if isinstance(model_config, LogisticRegressionConfig):
        return _fit_logistic_regression(
            config=config,
            model_config=model_config,
            train=train,
        )
    if isinstance(model_config, XGBoostConfig):
        return _fit_xgboost(
            config=config,
            model_config=model_config,
            train=train,
            validation=validation,
        )
    raise ModelingError(f"unsupported model config: {type(model_config).__name__}")
```

### 5.3. Refactor `training.py`

- [ ] Xóa estimator/preprocessing imports khỏi `training.py`.
- [ ] Xóa `feature_groups`, `normalize_feature_types`, `build_pipeline`.
- [ ] Gọi duy nhất `fit_probability_model`.
- [ ] Giữ `select_threshold` và `binary_metrics` dùng chung.
- [ ] Bump model bundle schema từ 1 lên 2.
- [ ] Lưu model metadata trong metrics và bundle.

Các import ML còn lại ở `training.py`:

```python
import joblib
import numpy as np
import pandas as pd
from numpy.typing import NDArray
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
)

from fraudguard_ml.modeling import ModelingError, fit_probability_model
```

Thay phần đầu của `train_and_select_threshold` từ normalize/build pipeline bằng:

```python
try:
    model = fit_probability_model(
        config,
        splits.train,
        splits.validation,
    )
except ModelingError as exc:
    raise TrainingError(str(exc)) from exc

probability = model.predict_proba(splits.validation.features)[:, 1]
threshold, selection = select_threshold(
    splits.validation.target,
    probability,
    min_precision=config.evaluation.min_precision,
)
model_metadata = model.metadata.to_dict()
```

Thêm metadata vào validation metrics:

```python
validation_metrics = {
    **binary_metrics(splits.validation.target, probability, threshold),
    "threshold_selection": selection,
    "model_metadata": model_metadata,
    "dataset_manifest_sha256": sha256_file(manifest_path),
    "population_fingerprint": manifest.population_fingerprint,
}
```

Đổi model bundle sang schema 2:

```python
bundle = {
    "bundle_schema_version": 2,
    "model": model,
    "model_metadata": model_metadata,
    "threshold": threshold,
    "feature_list": list(config.dataset.feature_columns),
    "target_column": config.dataset.target_column,
    "prediction_point": config.dataset.prediction_point,
    "label_policy": manifest.label_policy,
    "experiment_name": config.experiment_name,
    "run_id": manifest.run_id,
    "dataset_manifest_sha256": sha256_file(manifest_path),
    "dataset_manifest_uri": (
        manifest.snapshot_uri.rsplit("/", 1)[0] + "/dataset_manifest.json"
    ),
    "population_fingerprint": manifest.population_fingerprint,
    "config": config.model_dump(mode="json"),
    "validation_metrics": validation_metrics,
}
```

Mở rộng return value để Phase 4 thu thập được metadata mà không phải mở joblib:

```python
return {
    "model_path": str(model_path),
    "model_sha256": sha256_file(model_path),
    "validation_metrics_path": str(metrics_path),
    "model_kind": model.metadata.model_kind,
    "best_iteration": model.metadata.best_iteration,
    "scale_pos_weight": model.metadata.scale_pos_weight,
    "threshold": threshold,
}
```

Schema 1 artifacts cũ vẫn giữ nguyên trên disk để tham khảo nhưng không dùng với
evaluation code mới. DAG phải train lại để sinh schema 2 artifact trước khi
evaluate.

### 5.4. Refactor `evaluation.py`

- [ ] Không import normalization từ `training.py`.
- [ ] Validate artifact schema 2.
- [ ] Validate model kind, manifest hash, feature order và fingerprint.
- [ ] Gọi cùng `FittedProbabilityModel.predict_proba` như training.
- [ ] Không thêm nhánh Logistic/XGBoost.

Đổi import:

```python
from fraudguard_ml.modeling import FittedProbabilityModel, ModelingError
from fraudguard_ml.training import binary_metrics
```

Thay phần load bundle và predict bằng:

```python
payload = joblib.load(model_path)
if not isinstance(payload, dict):
    raise ManifestError("model artifact must contain a mapping bundle")
bundle: dict[str, Any] = payload
if bundle.get("bundle_schema_version") != 2:
    raise ManifestError("unsupported model bundle schema version")

manifest_sha256 = sha256_file(manifest_path)
if bundle.get("dataset_manifest_sha256") != manifest_sha256:
    raise ManifestError("model and evaluation manifest do not match")
if tuple(bundle.get("feature_list", ())) != config.dataset.feature_columns:
    raise ManifestError("model feature order does not match config")
if bundle.get("population_fingerprint") != manifest.population_fingerprint:
    raise ManifestError("model population fingerprint does not match manifest")

model = bundle.get("model")
if not isinstance(model, FittedProbabilityModel):
    raise ManifestError("model bundle does not contain a fitted probability model")
if model.feature_columns != config.dataset.feature_columns:
    raise ManifestError("fitted model feature order does not match config")
if model.metadata.model_kind != config.model.kind:
    raise ManifestError("fitted model kind does not match config")

try:
    probability = model.predict_proba(test.features)[:, 1]
except ModelingError as exc:
    raise ManifestError(f"model prediction failed: {exc}") from exc
```

Phần `binary_metrics`, result payload và immutable JSON writer giữ nguyên.

### 5.5. Viết `test_modeling.py`

Tests phải đi qua interface chung, không gọi trực tiếp hai adapter private.

Tạo `ml/tests/test_modeling.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import joblib
import numpy as np
import pandas as pd
import pytest

from fraudguard_ml.config import load_yaml_config
from fraudguard_ml.dataset_loader import FrameSplit
from fraudguard_ml.experiment_config import ExperimentConfig
from fraudguard_ml.modeling import (
    FittedProbabilityModel,
    ModelingError,
    fit_probability_model,
)

pytestmark = pytest.mark.smoke
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _config(filename: str) -> ExperimentConfig:
    config = load_yaml_config(
        REPOSITORY_ROOT / "configs" / filename,
        ExperimentConfig,
    )
    if config.model.kind == "xgboost":
        payload = config.model_dump(mode="python")
        model = cast(dict[str, Any], payload["model"])
        model["n_estimators"] = 40
        model["early_stopping_rounds"] = 5
        return ExperimentConfig.model_validate(payload)
    return config


def _split(
    *,
    prefix: str,
    amounts: list[float],
    target: list[int],
    transaction_types: list[str] | None = None,
) -> FrameSplit:
    row_count = len(target)
    types = transaction_types or [
        "TRANSFER" if value else "PAYMENT" for value in target
    ]
    features = pd.DataFrame(
        {
            "transaction_type": types,
            "amount": amounts,
            "origin_balance_before": [2_000.0 - value for value in amounts],
            "destination_balance_before": [500.0 + value for value in amounts],
        }
    )
    return FrameSplit(
        features=features,
        target=pd.Series(target, dtype="uint8"),
        keys=pd.DataFrame(
            {
                "source": ["demo"] * row_count,
                "event_id": [f"{prefix}-{index}" for index in range(row_count)],
            }
        ),
        event_time=pd.Series(
            pd.date_range("2026-01-01", periods=row_count, freq="min", tz="UTC")
        ),
    )


@pytest.fixture
def train_split() -> FrameSplit:
    return _split(
        prefix="train",
        amounts=[10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0,
                 900.0, 1_000.0, 1_100.0, 1_200.0],
        target=[0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1],
    )


@pytest.fixture
def validation_split() -> FrameSplit:
    return _split(
        prefix="validation",
        amounts=[15.0, 25.0, 35.0, 45.0, 950.0, 1_150.0],
        target=[0, 0, 0, 0, 1, 1],
        transaction_types=[
            "CASH_IN",
            "PAYMENT",
            "PAYMENT",
            "PAYMENT",
            "TRANSFER",
            "TRANSFER",
        ],
    )


@pytest.mark.parametrize(
    ("filename", "expected_kind", "expected_scaling"),
    [
        ("training_baseline.yml", "logistic_regression", "standard"),
        ("training_xgboost_baseline.yml", "xgboost", "none"),
    ],
)
def test_shared_interface_returns_valid_probabilities(
    filename: str,
    expected_kind: str,
    expected_scaling: str,
    train_split: FrameSplit,
    validation_split: FrameSplit,
) -> None:
    model = fit_probability_model(
        _config(filename),
        train_split,
        validation_split,
    )

    probability = model.predict_proba(validation_split.features)

    assert probability.shape == (len(validation_split.target), 2)
    assert np.isfinite(probability).all()
    assert ((probability >= 0.0) & (probability <= 1.0)).all()
    assert model.metadata.model_kind == expected_kind
    assert model.metadata.numeric_scaling == expected_scaling


def test_xgboost_weight_uses_train_target_only(
    train_split: FrameSplit,
    validation_split: FrameSplit,
) -> None:
    model = fit_probability_model(
        _config("training_xgboost_baseline.yml"),
        train_split,
        validation_split,
    )

    assert model.metadata.scale_pos_weight == 2.0
    assert model.metadata.best_iteration is not None
    assert 0 <= model.metadata.best_iteration < 40


def test_unknown_category_is_supported(
    train_split: FrameSplit,
    validation_split: FrameSplit,
) -> None:
    model = fit_probability_model(
        _config("training_baseline.yml"),
        train_split,
        validation_split,
    )

    probability = model.predict_proba(validation_split.features)

    assert probability.shape == (6, 2)


def test_rejects_missing_feature(
    train_split: FrameSplit,
    validation_split: FrameSplit,
) -> None:
    model = fit_probability_model(
        _config("training_baseline.yml"),
        train_split,
        validation_split,
    )
    invalid = validation_split.features.drop(columns=["amount"])

    with pytest.raises(ModelingError, match="missing required feature"):
        model.predict_proba(invalid)


def test_rejects_single_class_train_target(
    train_split: FrameSplit,
    validation_split: FrameSplit,
) -> None:
    invalid_train = FrameSplit(
        features=train_split.features,
        target=pd.Series([0] * len(train_split.target), dtype="uint8"),
        keys=train_split.keys,
        event_time=train_split.event_time,
    )

    with pytest.raises(ModelingError, match="both binary classes"):
        fit_probability_model(
            _config("training_xgboost_baseline.yml"),
            invalid_train,
            validation_split,
        )


@pytest.mark.parametrize(
    "filename",
    ["training_baseline.yml", "training_xgboost_baseline.yml"],
)
def test_fitted_model_survives_joblib_round_trip(
    filename: str,
    tmp_path: Path,
    train_split: FrameSplit,
    validation_split: FrameSplit,
) -> None:
    model = fit_probability_model(
        _config(filename),
        train_split,
        validation_split,
    )
    expected = model.predict_proba(validation_split.features)
    path = tmp_path / "model.joblib"

    joblib.dump(model, path)
    restored = joblib.load(path)

    assert isinstance(restored, FittedProbabilityModel)
    np.testing.assert_allclose(
        restored.predict_proba(validation_split.features),
        expected,
    )
```

`scale_pos_weight == 2.0` vì train fixture có 8 negative và 4 positive. Validation
có tỷ lệ khác nhưng không được ảnh hưởng kết quả này.

### 5.6. Viết `test_training.py`

Test orchestration phải chứng minh cả hai model tạo schema 2 bundle và evaluation
dùng cùng interface. Tạo `ml/tests/test_training.py` với nội dung sau. Các helper
có thể chuyển sang `conftest.py` sau khi test pass; không import trực tiếp một test
module từ test module khác.

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import joblib
import pandas as pd
import pytest

from fraudguard_ml.config import load_yaml_config
from fraudguard_ml.dataset_loader import DatasetSplits, FrameSplit
from fraudguard_ml.dataset_manifest import (
    DatasetManifest,
    ManifestError,
)
from fraudguard_ml.evaluation import evaluate_test_split
from fraudguard_ml.experiment_config import ExperimentConfig
from fraudguard_ml.modeling import FittedProbabilityModel
from fraudguard_ml.training import train_and_select_threshold

pytestmark = pytest.mark.smoke
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class TrainedCase:
    config: ExperimentConfig
    splits: DatasetSplits
    manifest: DatasetManifest
    manifest_path: Path
    model_path: Path
    train_result: dict[str, Any]


def _config(filename: str) -> ExperimentConfig:
    config = load_yaml_config(
        REPOSITORY_ROOT / "configs" / filename,
        ExperimentConfig,
    )
    if config.model.kind == "xgboost":
        payload = config.model_dump(mode="python")
        model = cast(dict[str, Any], payload["model"])
        model["n_estimators"] = 40
        model["early_stopping_rounds"] = 5
        return ExperimentConfig.model_validate(payload)
    return config


def _frame_split(
    *,
    prefix: str,
    target: list[int],
    minute_offset: int,
) -> FrameSplit:
    amounts = [
        20.0 + index if value == 0 else 900.0 + index
        for index, value in enumerate(target)
    ]
    row_count = len(target)
    event_time = pd.date_range(
        pd.Timestamp("2026-01-01T00:00:00Z")
        + pd.Timedelta(minutes=minute_offset),
        periods=row_count,
        freq="min",
    )
    return FrameSplit(
        features=pd.DataFrame(
            {
                "transaction_type": [
                    "PAYMENT" if value == 0 else "TRANSFER" for value in target
                ],
                "amount": amounts,
                "origin_balance_before": [
                    2_000.0 - value for value in amounts
                ],
                "destination_balance_before": [
                    500.0 + value for value in amounts
                ],
            }
        ),
        target=pd.Series(target, dtype="uint8"),
        keys=pd.DataFrame(
            {
                "source": ["demo"] * row_count,
                "event_id": [f"{prefix}-{index}" for index in range(row_count)],
            }
        ),
        event_time=pd.Series(event_time),
    )


def _dataset_splits() -> DatasetSplits:
    return DatasetSplits(
        train=_frame_split(
            prefix="train",
            target=[0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1],
            minute_offset=0,
        ),
        validation=_frame_split(
            prefix="validation",
            target=[0, 0, 0, 0, 1, 1],
            minute_offset=120,
        ),
        test=_frame_split(
            prefix="test",
            target=[0, 0, 0, 0, 1, 1],
            minute_offset=240,
        ),
    )


def _partition(split: FrameSplit) -> dict[str, Any]:
    row_count = len(split.target)
    fraud_count = int(split.target.sum())
    return {
        "row_count": row_count,
        "fraud_count": fraud_count,
        "fraud_rate": float(fraud_count / row_count),
        "min_event_time": split.event_time.min().isoformat(),
        "max_event_time": split.event_time.max().isoformat(),
    }


def _manifest(
    config: ExperimentConfig,
    splits: DatasetSplits,
) -> DatasetManifest:
    row_count = sum(
        len(split.target)
        for split in (splits.train, splits.validation, splits.test)
    )
    fraud_count = sum(
        int(split.target.sum())
        for split in (splits.train, splits.validation, splits.test)
    )
    return DatasetManifest.model_validate(
        {
            "manifest_schema_version": 1,
            "experiment_name": config.experiment_name,
            "run_id": "phase3-test",
            "created_at_utc": "2026-01-01T06:01:00+00:00",
            "source_relation": config.dataset.relation,
            "snapshot_uri": (
                "s3://fraud-training-snapshots/phase3-test/data.parquet"
            ),
            "snapshot_format": "parquet",
            "snapshot_sha256": "a" * 64,
            "data_fingerprint": f"sha256:{'a' * 64}",
            "snapshot_size_bytes": 1,
            "label_policy": "static_final_labels",
            "row_count": row_count,
            "fraud_count": fraud_count,
            "fraud_rate": float(fraud_count / row_count),
            "min_event_time": splits.train.event_time.min().isoformat(),
            "max_event_time": splits.test.event_time.max().isoformat(),
            "split": {
                "strategy": "temporal",
                "train_end": config.split.train_end,
                "validation_end": config.split.validation_end,
                "test_end": config.split.test_end,
            },
            "feature_list": list(config.dataset.feature_columns),
            "target_column": config.dataset.target_column,
            "dbt_manifest_sha256": "b" * 64,
            "training_config_sha256": "c" * 64,
            "population_query_sha256": "d" * 64,
            "population_fingerprint": "xor64:0000000000000001",
            "fingerprint_algorithm": "clickhouse_cityhash64_xor_v1",
            "quality_status": "passed",
            "contract_artifact_sha256": "e" * 64,
            "git_sha": "f" * 40,
            "split_statistics": {
                "train": _partition(splits.train),
                "validation": _partition(splits.validation),
                "test": _partition(splits.test),
            },
        }
    )


def _train_case(
    tmp_path: Path,
    filename: str,
) -> TrainedCase:
    config = _config(filename)
    splits = _dataset_splits()
    manifest = _manifest(config, splits)
    manifest_path = tmp_path / "dataset_manifest.json"
    manifest_path.write_text(
        manifest.model_dump_json(indent=2),
        encoding="utf-8",
    )
    model_directory = tmp_path / "model"
    train_result = train_and_select_threshold(
        splits=splits,
        config=config,
        manifest=manifest,
        manifest_path=manifest_path,
        output_dir=model_directory,
    )
    return TrainedCase(
        config=config,
        splits=splits,
        manifest=manifest,
        manifest_path=manifest_path,
        model_path=model_directory / "model_bundle.joblib",
        train_result=train_result,
    )


@pytest.mark.parametrize(
    ("filename", "expected_kind"),
    [
        ("training_baseline.yml", "logistic_regression"),
        ("training_xgboost_baseline.yml", "xgboost"),
    ],
)
def test_train_and_evaluate_share_probability_model(
    filename: str,
    expected_kind: str,
    tmp_path: Path,
) -> None:
    case = _train_case(tmp_path, filename)

    bundle = joblib.load(case.model_path)
    assert bundle["bundle_schema_version"] == 2
    assert isinstance(bundle["model"], FittedProbabilityModel)
    assert bundle["model_metadata"]["model_kind"] == expected_kind
    assert bundle["feature_list"] == list(
        case.config.dataset.feature_columns
    )
    assert (
        bundle["population_fingerprint"]
        == case.manifest.population_fingerprint
    )
    assert case.train_result["model_kind"] == expected_kind

    output_path = tmp_path / "evaluation.json"
    result = evaluate_test_split(
        test=case.splits.test,
        config=case.config,
        manifest=case.manifest,
        manifest_path=case.manifest_path,
        model_path=case.model_path,
        output_path=output_path,
    )

    assert result["split"] == "test"
    assert (
        result["population_fingerprint"]
        == case.manifest.population_fingerprint
    )
    assert 0.0 <= result["metrics"]["pr_auc"] <= 1.0
    assert 0.0 <= result["metrics"]["roc_auc"] <= 1.0


def test_evaluation_rejects_wrong_manifest_hash(tmp_path: Path) -> None:
    case = _train_case(tmp_path, "training_baseline.yml")
    changed_manifest_path = tmp_path / "changed_manifest.json"
    changed_manifest_path.write_text(
        case.manifest.model_dump_json(),
        encoding="utf-8",
    )

    with pytest.raises(ManifestError, match="manifest do not match"):
        evaluate_test_split(
            test=case.splits.test,
            config=case.config,
            manifest=case.manifest,
            manifest_path=changed_manifest_path,
            model_path=case.model_path,
            output_path=tmp_path / "wrong-manifest.json",
        )


def test_evaluation_rejects_wrong_feature_order(tmp_path: Path) -> None:
    case = _train_case(tmp_path, "training_baseline.yml")
    wrong_dataset = case.config.dataset.model_copy(
        update={
            "feature_columns": tuple(
                reversed(case.config.dataset.feature_columns)
            )
        }
    )
    wrong_config = case.config.model_copy(update={"dataset": wrong_dataset})

    with pytest.raises(ManifestError, match="feature order"):
        evaluate_test_split(
            test=case.splits.test,
            config=wrong_config,
            manifest=case.manifest,
            manifest_path=case.manifest_path,
            model_path=case.model_path,
            output_path=tmp_path / "wrong-features.json",
        )


def test_evaluation_rejects_wrong_population_fingerprint(
    tmp_path: Path,
) -> None:
    case = _train_case(tmp_path, "training_baseline.yml")
    wrong_manifest = case.manifest.model_copy(
        update={"population_fingerprint": "xor64:ffffffffffffffff"}
    )

    with pytest.raises(ManifestError, match="population fingerprint"):
        evaluate_test_split(
            test=case.splits.test,
            config=case.config,
            manifest=wrong_manifest,
            manifest_path=case.manifest_path,
            model_path=case.model_path,
            output_path=tmp_path / "wrong-population.json",
        )


def test_evaluation_rejects_legacy_bundle_schema(tmp_path: Path) -> None:
    case = _train_case(tmp_path, "training_baseline.yml")
    bundle = joblib.load(case.model_path)
    bundle["bundle_schema_version"] = 1
    legacy_path = tmp_path / "legacy.joblib"
    joblib.dump(bundle, legacy_path)

    with pytest.raises(ManifestError, match="bundle schema"):
        evaluate_test_split(
            test=case.splits.test,
            config=case.config,
            manifest=case.manifest,
            manifest_path=case.manifest_path,
            model_path=legacy_path,
            output_path=tmp_path / "legacy-evaluation.json",
        )
```

Không mock Logistic Regression hoặc XGBoost trong happy-path tests. Dataset nhỏ
giúp hai adapters chạy in-process và test đúng interface thật.

## 6. Kiểm tra không có leakage

### 6.1. Preprocessor chỉ fit train

- `fit_transform` chỉ xuất hiện với `train_features`;
- validation chỉ đi qua `transform`;
- `FittedProbabilityModel.predict_proba` chỉ gọi `transform`;
- test split chỉ xuất hiện trong `evaluate_test_split` sau khi artifact đã khóa.

Kiểm tra source:

```bash
rg -n 'fit_transform|\.fit\(|\.transform\(' \
  ml/src/fraudguard_ml/modeling.py \
  ml/src/fraudguard_ml/training.py \
  ml/src/fraudguard_ml/evaluation.py
```

Kết quả đúng phải thể hiện:

```text
train -> preprocessor.fit_transform
validation -> preprocessor.transform
test -> FittedProbabilityModel.predict_proba -> preprocessor.transform
```

### 6.2. Class weight chỉ từ train

Chỉ cho phép:

```python
_calculate_scale_pos_weight(train.target)
```

Không cho phép:

```python
_calculate_scale_pos_weight(validation.target)
_calculate_scale_pos_weight(test.target)
_calculate_scale_pos_weight(pd.concat(...))
```

### 6.3. Early stopping chỉ dùng validation

XGBoost fit phải có đúng:

```python
eval_set=[(validation_matrix, validation.target)]
```

Không truyền test vào `fit_probability_model`; interface cố ý không nhận test.

## 7. Smoke test hai adapters

Sau unit tests, chạy smoke test không cần ClickHouse, MinIO hoặc Airflow:

```bash
uv run pytest ml/tests/test_modeling.py --no-cov -q
uv run pytest ml/tests/test_training.py --no-cov -q
```

Kiểm tra XGBoost metadata thủ công:

```bash
uv run python - <<'PY'
from pathlib import Path

import pandas as pd

from fraudguard_ml.config import load_yaml_config
from fraudguard_ml.dataset_loader import FrameSplit
from fraudguard_ml.experiment_config import ExperimentConfig
from fraudguard_ml.modeling import fit_probability_model

config = load_yaml_config(
    Path("configs/training_xgboost_baseline.yml"),
    ExperimentConfig,
)
payload = config.model_dump(mode="python")
payload["model"]["n_estimators"] = 40
payload["model"]["early_stopping_rounds"] = 5
config = ExperimentConfig.model_validate(payload)


def split(name: str, target: list[int]) -> FrameSplit:
    amount = [20.0 + index if value == 0 else 900.0 + index
              for index, value in enumerate(target)]
    rows = len(target)
    return FrameSplit(
        features=pd.DataFrame(
            {
                "transaction_type": [
                    "PAYMENT" if value == 0 else "TRANSFER" for value in target
                ],
                "amount": amount,
                "origin_balance_before": [2_000.0 - value for value in amount],
                "destination_balance_before": [500.0 + value for value in amount],
            }
        ),
        target=pd.Series(target, dtype="uint8"),
        keys=pd.DataFrame(
            {
                "source": ["demo"] * rows,
                "event_id": [f"{name}-{index}" for index in range(rows)],
            }
        ),
        event_time=pd.Series(
            pd.date_range("2026-01-01", periods=rows, freq="min", tz="UTC")
        ),
    )


train = split("train", [0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1])
validation = split("validation", [0, 0, 0, 0, 1, 1])
model = fit_probability_model(config, train, validation)
probability = model.predict_proba(validation.features)

assert probability.shape == (6, 2)
assert model.metadata.scale_pos_weight == 2.0
assert model.metadata.best_iteration is not None
print(model.metadata.to_dict())
print("PHASE 3 XGBOOST SMOKE: PASS")
PY
```

## 8. Quality checks

```bash
uv lock --check
uv run pytest ml/tests/test_config.py --no-cov
uv run pytest ml/tests/test_modeling.py --no-cov
uv run pytest ml/tests/test_training.py --no-cov
uv run pytest --no-cov
uv run ruff check ml/src ml/tests
uv run mypy
git diff --check
```

Không chạy full Airflow DAG như điều kiện bắt buộc của Phase 3. Module và
orchestration tests đã chạy in-process; Airflow integration của selected candidate
thuộc Phase 7.

## 9. Script xác nhận hoàn thành Phase 3

```bash
set -Eeuo pipefail

cd /home/phongthanh/ML_Fraud_Banking

test -f ml/src/fraudguard_ml/modeling.py
test -f ml/tests/test_modeling.py
test -f ml/tests/test_training.py

rg -q '^class FittedProbabilityModel' ml/src/fraudguard_ml/modeling.py
rg -q '^def fit_probability_model' ml/src/fraudguard_ml/modeling.py
rg -q '"bundle_schema_version": 2' ml/src/fraudguard_ml/training.py
rg -q '"model": model' ml/src/fraudguard_ml/training.py

if rg -n 'LogisticRegression|XGBClassifier' \
  ml/src/fraudguard_ml/training.py \
  ml/src/fraudguard_ml/evaluation.py; then
    printf '%s\n' 'Model-specific estimator leaked outside modeling.py' >&2
    exit 1
fi

uv lock --check
uv run pytest ml/tests/test_config.py --no-cov
uv run pytest ml/tests/test_modeling.py --no-cov
uv run pytest ml/tests/test_training.py --no-cov
uv run pytest --no-cov
uv run ruff check ml/src ml/tests
uv run mypy
git diff --check

printf '%s\n' 'PHASE 3: PASS'
```

`PHASE 3: PASS` chỉ được in nếu mọi command trước đó thành công.

## 10. Lỗi thường gặp

### `NameError: model_config is not defined`

Đây là lỗi trạng thái chuyển tiếp hiện tại. Sau Phase 3, `build_pipeline` cũ bị
xóa và `training.py` gọi `fit_probability_model`; không khai báo tạm một global
`model_config`.

### XGBoost báo không có `best_iteration`

Kiểm tra `early_stopping_rounds` được truyền vào constructor và `eval_set` được
truyền vào `fit`. Với XGBoost 3.4.1 trong repository hiện tại:

```python
estimator = XGBClassifier(
    early_stopping_rounds=50,
    # Các hyperparameter còn lại lấy từ XGBoostConfig.
)
estimator.fit(
    train_matrix,
    train.target,
    eval_set=[(validation_matrix, validation.target)],
)
```

Không lấy `best_iteration` trước khi `fit` hoàn tất.

### XGBoost lỗi feature type hoặc object dtype

Không đưa raw DataFrame trực tiếp vào estimator. Cả hai adapters phải đi qua
`_normalize_feature_types` và fitted `ColumnTransformer`.

### Validation có category chưa xuất hiện trong train

`OneHotEncoder(handle_unknown="ignore")` phải được giữ nguyên. Không fit lại
encoder trên validation.

### `scale_pos_weight` thay đổi theo validation

Đây là leakage. Weight phải bằng `negative_train / positive_train` và test fixture
phải cố ý dùng validation ratio khác để phát hiện lỗi.

### Joblib load thất bại sau khi refactor

`FittedProbabilityModel` phải nằm ở module importable
`fraudguard_ml.modeling`, không định nghĩa trong CLI, notebook hoặc function local.

### Evaluation báo legacy bundle schema

Artifact schema 1 cũ không có `FittedProbabilityModel`. Giữ artifact cũ để tham
khảo metrics, nhưng train lại candidate để tạo schema 2 trước khi evaluate bằng
code Phase 3.

### XGBoost chạy quá nhiều CPU trên WSL

Xác nhận:

```python
n_jobs=config.runtime.max_cpu_threads
```

Giảm `runtime.max_cpu_threads` trong config khi cần. Không hardcode toàn bộ logical
CPUs của máy vào estimator.

## 11. Rollback

Nếu Phase 3 chưa pass:

1. Giữ nguyên Phase 1 dependencies và Phase 2 configs.
2. Không xóa model artifact hoặc snapshot cũ.
3. Khôi phục `training.py` về Logistic-only implementation đã pass của Phase 2.
4. Gỡ import `FittedProbabilityModel` khỏi evaluation nếu modeling module bị bỏ.
5. Chạy lại config tests, Ruff và mypy.

Không dùng `git reset --hard`, không xóa Docker volumes và không overwrite
immutable artifacts.

## 12. Definition of Done

Phase 3 chỉ hoàn thành khi toàn bộ checklist sau đạt:

- [ ] Phase 2 config tests đã được thêm và pass.
- [ ] `experiment_config.py` không còn unused imports.
- [ ] Có module `fraudguard_ml.modeling`.
- [ ] Có interface `fit_probability_model(config, train, validation)`.
- [ ] Có `FittedProbabilityModel.predict_proba(features)`.
- [ ] Có Logistic Regression adapter.
- [ ] Có XGBoost adapter.
- [ ] `transaction_type` được one-hot ở cả hai adapters.
- [ ] Numeric được scale cho Logistic Regression.
- [ ] Numeric không được scale cho XGBoost.
- [ ] Preprocessor chỉ fit trên train.
- [ ] Validation chỉ được transform.
- [ ] XGBoost dùng validation làm `eval_set` cho early stopping.
- [ ] Test split không xuất hiện trong modeling interface.
- [ ] `scale_pos_weight` chỉ tính từ train target.
- [ ] `scale_pos_weight` được lưu trong metadata.
- [ ] `best_iteration` được lưu trong metadata.
- [ ] Resolved hyperparameters được lưu trong metadata.
- [ ] Random seed và CPU thread limit lấy từ config.
- [ ] Cả hai models trả probability shape `(n, 2)` trong `[0, 1]`.
- [ ] Missing feature bị reject rõ ràng.
- [ ] Unknown categorical value không làm prediction lỗi.
- [ ] Model sống qua joblib round trip.
- [ ] `training.py` không import estimator cụ thể.
- [ ] `evaluation.py` không có model-specific branch.
- [ ] Bundle schema 2 chứa model và metadata.
- [ ] Manifest hash vẫn được kiểm tra.
- [ ] Feature order vẫn được kiểm tra.
- [ ] Population fingerprint vẫn được kiểm tra.
- [ ] Threshold selection và `binary_metrics` vẫn dùng chung.
- [ ] Logistic training/evaluation test pass.
- [ ] XGBoost training/evaluation test pass.
- [ ] Toàn bộ unit assertions pass với `pytest --no-cov`.
- [ ] `ruff check ml/src ml/tests` pass.
- [ ] `mypy` pass.
- [ ] `git diff --check` pass.
- [ ] Chưa dùng test metrics để tune hoặc chọn model.

Sau khi toàn bộ mục trên được tick, cập nhật Phase 3 trong roadmap và chuyển sang
Phase 4 — chạy experiment 2 × 2 trên validation.
