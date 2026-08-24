# Phase 2 — Mở rộng model configuration

Tài liệu này hướng dẫn triển khai đầy đủ Phase 2 trong
[`XGBOOST_EXPERIMENT_ROADMAP.md`](XGBOOST_EXPERIMENT_ROADMAP.md).

## 1. Mục tiêu

Sau Phase 2, `ExperimentConfig.model` là một discriminated union dùng trường
`kind` để nhận biết chính xác hai loại cấu hình:

```text
ExperimentConfig.model
├── kind: logistic_regression -> LogisticRegressionConfig
└── kind: xgboost             -> XGBoostConfig
```

Interface mà phần còn lại của dự án cần biết chỉ là:

```python
config.model.kind
```

Toàn bộ validation model-specific nằm trong `experiment_config.py`. Nhờ vậy,
YAML sai bị từ chối ngay khi load và không cần rải validation trong CLI, DAG hoặc
training task.

Phase này phải đạt được các kết quả sau:

- Logistic Regression config hiện tại vẫn load được;
- hai XGBoost config mới load được;
- mọi config demo dùng cùng temporal boundaries 2h/4h/6h;
- field của Logistic Regression không được xuất hiện trong XGBoost và ngược lại;
- các hyperparameter XGBoost cơ bản có giới hạn an toàn;
- training hiện tại báo lỗi rõ ràng nếu người dùng cố train XGBoost trước Phase 3;
- unit tests, Ruff và mypy đều pass.

Phase 2 chỉ xây dựng configuration seam. Phase này **không** tạo estimator
XGBoost, không sửa preprocessing, không chạy experiment và không đánh giá test.
Các phần đó thuộc Phase 3–6.

## 2. Trạng thái hiện tại

Đã xác nhận trong repository:

- [x] `xgboost>=3,<4` đã có trong `pyproject.toml`.
- [x] XGBoost đã được khóa trong `uv.lock`.
- [x] Airflow requirements đã có `xgboost>=3,<4`.
- [x] `ModelConfig` hiện chỉ hỗ trợ `logistic_regression`.
- [x] `training_baseline.yml` hiện dùng split 2h/4h/6h.
- [x] `training_challenger_balance.yml` vẫn dùng split dài và cần đồng bộ.
- [x] Chưa có hai XGBoost YAML.
- [x] Chưa có test cho `ExperimentConfig` và model union.

## 3. Phạm vi file

Phase 2 cần sửa hoặc tạo:

```text
ml/src/fraudguard_ml/experiment_config.py
ml/src/fraudguard_ml/training.py
ml/tests/test_config.py
configs/training_challenger_balance.yml
configs/training_xgboost_baseline.yml
configs/training_xgboost_balance.yml
```

`training.py` chỉ nhận một compatibility guard nhỏ để code hiện tại vẫn type-safe
sau khi `config.model` trở thành union. Không đưa implementation XGBoost vào file
này trong Phase 2.

Không sửa DAG, evaluation, snapshot logic, notebook hoặc model artifact trong
phase này.

## 4. Các bước triển khai

### 4.1. Pre-flight

- [ ] Kiểm tra working tree và giữ nguyên thay đổi đang có của người dùng.
- [ ] Xác nhận Phase 1 dependency đã tồn tại.
- [ ] Chạy test config hiện tại làm mốc trước thay đổi.

```bash
cd /home/phongthanh/ML_Fraud_Banking

git status --short
rg -n 'xgboost>=3,<4' pyproject.toml docker/airflow/requirements.txt
rg -n 'name = "xgboost"' uv.lock
uv run pytest ml/tests/test_config.py --no-cov
```

Không dùng `git checkout`, `git reset` hoặc ghi đè
`configs/training_baseline.yml`; file này đang có thay đổi phục vụ demo 2h/4h/6h.

### 4.2. Tạo discriminated union cho model config

- [ ] Thêm `Annotated` vào import từ `typing`.
- [ ] Đổi `ModelConfig` cũ thành `LogisticRegressionConfig`.
- [ ] Thêm `XGBoostConfig`.
- [ ] Tạo alias `ModelConfig` bằng discriminated union trên field `kind`.
- [ ] Giữ `ExperimentConfig.model: ModelConfig` để caller không đổi interface.

Trong `ml/src/fraudguard_ml/experiment_config.py`, đổi import:

```python
from typing import Annotated, Literal, Self
```

Sau đó thay class `ModelConfig` hiện tại bằng toàn bộ code sau:

```python
class LogisticRegressionConfig(StrictModel):
    """Bounded hyperparameters for the Logistic Regression baseline."""

    kind: Literal["logistic_regression"]
    class_weight: Literal["balanced"] = "balanced"
    regularization_c: float = Field(1.0, gt=0.0, le=1_000.0)
    max_iter: int = Field(500, ge=50, le=10_000)


class XGBoostConfig(StrictModel):
    """CPU-safe hyperparameters for the XGBoost fraud challenger."""

    kind: Literal["xgboost"]
    objective: Literal["binary:logistic"] = "binary:logistic"
    eval_metric: Literal["aucpr"] = "aucpr"
    tree_method: Literal["hist"] = "hist"
    n_estimators: int = Field(1_000, ge=1, le=10_000)
    learning_rate: float = Field(0.05, gt=0.0, le=1.0)
    max_depth: int = Field(4, ge=1, le=16)
    min_child_weight: float = Field(10.0, ge=0.0)
    subsample: float = Field(0.8, gt=0.0, le=1.0)
    colsample_bytree: float = Field(0.8, gt=0.0, le=1.0)
    reg_alpha: float = Field(0.0, ge=0.0)
    reg_lambda: float = Field(1.0, ge=0.0)
    early_stopping_rounds: int = Field(50, ge=1)
    imbalance_strategy: Literal["none", "train_ratio"] = "train_ratio"

    @model_validator(mode="after")
    def validate_early_stopping(self) -> Self:
        """Require at least one boosting round beyond early stopping patience."""

        if self.early_stopping_rounds >= self.n_estimators:
            raise ValueError(
                "early_stopping_rounds must be smaller than n_estimators"
            )
        return self


ModelConfig = Annotated[
    LogisticRegressionConfig | XGBoostConfig,
    Field(discriminator="kind"),
]
```

Không dùng một class chứa tất cả field Logistic và XGBoost dưới dạng optional.
Cách đó cho phép các tổ hợp cấu hình vô nghĩa và làm interface nông: mọi caller
phải tự biết field nào hợp lệ cho model nào.

Các giới hạn được chọn cho demo:

| Field | Giới hạn | Lý do |
| --- | --- | --- |
| `regularization_c` | `0 < C <= 1000` | Không chấp nhận regularization vô hiệu |
| `max_iter` | `50..10000` | Đủ hội tụ, tránh giá trị vô hạn |
| `n_estimators` | `1..10000` | Cho phép early stopping nhưng chặn cấu hình cực đoan |
| `learning_rate` | `0 < value <= 1` | Miền hợp lệ cho demo boosting |
| `max_depth` | `1..16` | Hạn chế overfit và RAM |
| `min_child_weight` | `>= 0` | Theo miền tham số XGBoost |
| `subsample` | `0 < value <= 1` | Tỷ lệ lấy mẫu hợp lệ |
| `colsample_bytree` | `0 < value <= 1` | Tỷ lệ feature hợp lệ |
| `reg_alpha`, `reg_lambda` | `>= 0` | Regularization không âm |
| `early_stopping_rounds` | `1..n_estimators-1` | Early stopping phải có ý nghĩa |

`objective`, `eval_metric` và `tree_method` cố ý dùng `Literal`. Portfolio này chỉ
cần binary fraud classification, PR-AUC và CPU `hist`; chưa cần mở interface cho
GPU hoặc objective khác.

### 4.3. Giữ Logistic training hiện tại type-safe

Khi `config.model` trở thành union, `training.py` không được truy cập trực tiếp
`regularization_c` trước khi xác định đúng nhánh.

- [ ] Import `LogisticRegressionConfig`.
- [ ] Narrow union trong `build_pipeline`.
- [ ] Báo lỗi có hướng dẫn nếu XGBoost được train trước Phase 3.

Đổi import trong `ml/src/fraudguard_ml/training.py`:

```python
from fraudguard_ml.experiment_config import (
    ExperimentConfig,
    LogisticRegressionConfig,
)
```

Thêm đoạn guard ở đầu `build_pipeline`, trước khi tạo preprocessor:

```python
def build_pipeline(config: ExperimentConfig) -> Pipeline:
    model_config = config.model
    if not isinstance(model_config, LogisticRegressionConfig):
        raise TrainingError(
            "xgboost training is not available until Phase 3 modeling is implemented"
        )

    categorical, numeric = feature_groups(config)
```

Sau đó đổi phần tạo Logistic estimator để chỉ đọc từ `model_config`:

```python
estimator = LogisticRegression(
    C=model_config.regularization_c,
    class_weight=model_config.class_weight,
    max_iter=model_config.max_iter,
    random_state=config.runtime.random_seed,
    solver="lbfgs",
)
```

Guard này là trạng thái chuyển tiếp có chủ đích. Nó cho phép snapshot và config
validation dùng XGBoost YAML, nhưng không giả vờ rằng training XGBoost đã được
triển khai. Phase 3 sẽ thay guard bằng model interface chung.

### 4.4. Đồng bộ temporal split cho Logistic configs

- [ ] Giữ nguyên `configs/training_baseline.yml` ở 2h/4h/6h.
- [ ] Sửa split của `configs/training_challenger_balance.yml` về cùng mốc.

Block chuẩn cho tất cả bốn config demo:

```yaml
split:
  strategy: temporal
  train_end: "2026-01-01T02:00:00Z"
  validation_end: "2026-01-01T04:00:00Z"
  test_end: "2026-01-01T06:00:00Z"
```

Không thay feature set của hai Logistic configs. `training_baseline.yml` giữ bốn
feature cơ bản; `training_challenger_balance.yml` giữ các balance-derived feature.

### 4.5. Tạo XGBoost baseline config

- [ ] Tạo `configs/training_xgboost_baseline.yml`.
- [ ] Dùng đúng bốn feature của Logistic baseline.
- [ ] Dùng split 2h/4h/6h và seed 42.

Nội dung đầy đủ:

```yaml
schema_version: 1
experiment_name: fraudguard_xgboost_baseline

dataset:
  relation: fraudguard_ml.ml_training_transactions
  prediction_point: post_ledger_update
  id_columns:
    - source
    - event_id
  split_columns:
    - event_time
    - event_date
    - step
  feature_columns:
    - transaction_type
    - amount
    - origin_balance_before
    - destination_balance_before
  target_column: is_fraud
  forbidden_feature_columns:
    - source
    - event_id
    - event_time
    - event_date
    - step
    - origin_account
    - destination_account
    - is_fraud
    - is_flagged_fraud

split:
  strategy: temporal
  train_end: "2026-01-01T02:00:00Z"
  validation_end: "2026-01-01T04:00:00Z"
  test_end: "2026-01-01T06:00:00Z"

snapshot:
  storage_uri: s3://fraud-training-snapshots
  format: parquet
  compression: zstd
  fingerprint_algorithm: clickhouse_cityhash64_xor_v1
  label_policy: static_final_labels

model:
  kind: xgboost
  objective: binary:logistic
  eval_metric: aucpr
  tree_method: hist
  n_estimators: 1000
  learning_rate: 0.05
  max_depth: 4
  min_child_weight: 10.0
  subsample: 0.8
  colsample_bytree: 0.8
  reg_alpha: 0.0
  reg_lambda: 1.0
  early_stopping_rounds: 50
  imbalance_strategy: train_ratio

evaluation:
  threshold_strategy: max_recall_at_min_precision
  min_precision: 0.10

runtime:
  random_seed: 42
```

### 4.6. Tạo XGBoost balance-feature config

- [ ] Tạo `configs/training_xgboost_balance.yml`.
- [ ] Dùng đúng feature set của `training_challenger_balance.yml`.
- [ ] Chỉ khác Logistic challenger ở `experiment_name` và `model`.

Nội dung đầy đủ:

```yaml
schema_version: 1
experiment_name: fraudguard_xgboost_balance

dataset:
  relation: fraudguard_ml.ml_training_transactions
  prediction_point: post_ledger_update
  id_columns:
    - source
    - event_id
  split_columns:
    - event_time
    - event_date
    - step
  feature_columns:
    - transaction_type
    - amount
    - origin_balance_before
    - origin_balance_after
    - destination_balance_before
    - destination_balance_after
    - origin_balance_delta
    - destination_balance_delta
    - origin_amount_residual
    - destination_amount_residual
    - origin_balance_before_is_zero
    - destination_balance_before_is_zero
    - destination_balance_after_is_zero
  target_column: is_fraud
  forbidden_feature_columns:
    - source
    - event_id
    - event_time
    - event_date
    - step
    - origin_account
    - destination_account
    - is_fraud
    - is_flagged_fraud

split:
  strategy: temporal
  train_end: "2026-01-01T02:00:00Z"
  validation_end: "2026-01-01T04:00:00Z"
  test_end: "2026-01-01T06:00:00Z"

snapshot:
  storage_uri: s3://fraud-training-snapshots
  format: parquet
  compression: zstd
  fingerprint_algorithm: clickhouse_cityhash64_xor_v1
  label_policy: static_final_labels

model:
  kind: xgboost
  objective: binary:logistic
  eval_metric: aucpr
  tree_method: hist
  n_estimators: 1000
  learning_rate: 0.05
  max_depth: 4
  min_child_weight: 10.0
  subsample: 0.8
  colsample_bytree: 0.8
  reg_alpha: 0.0
  reg_lambda: 1.0
  early_stopping_rounds: 50
  imbalance_strategy: train_ratio

evaluation:
  threshold_strategy: max_recall_at_min_precision
  min_precision: 0.10

runtime:
  random_seed: 42
```

`balance` trong tên config mô tả feature set có các balance/delta/residual feature.
Nó không có nghĩa là lấy mẫu lại dữ liệu. `imbalance_strategy: train_ratio` yêu
cầu Phase 3 tính `scale_pos_weight` chỉ từ train split.

### 4.7. Thêm test cho model configuration

Trong `ml/tests/test_config.py`, bổ sung import:

```python
from typing import Any, Literal, cast

from fraudguard_ml.experiment_config import (
    ExperimentConfig,
    LogisticRegressionConfig,
    XGBoostConfig,
)
```

Thêm các helper và test sau cuối file:

```python
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIRECTORY = REPOSITORY_ROOT / "configs"


def _load_experiment_mapping(filename: str) -> dict[str, Any]:
    raw = yaml.safe_load((CONFIG_DIRECTORY / filename).read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return cast(dict[str, Any], raw)


@pytest.mark.parametrize(
    ("filename", "expected_kind", "expected_feature_count"),
    [
        ("training_baseline.yml", "logistic_regression", 4),
        ("training_challenger_balance.yml", "logistic_regression", 13),
        ("training_xgboost_baseline.yml", "xgboost", 4),
        ("training_xgboost_balance.yml", "xgboost", 13),
    ],
)
def test_loads_all_demo_experiment_configs(
    filename: str,
    expected_kind: str,
    expected_feature_count: int,
) -> None:
    config = load_yaml_config(
        CONFIG_DIRECTORY / filename,
        ExperimentConfig,
    )

    assert config.model.kind == expected_kind
    assert len(config.dataset.feature_columns) == expected_feature_count
    assert config.split.train_end == "2026-01-01T02:00:00Z"
    assert config.split.validation_end == "2026-01-01T04:00:00Z"
    assert config.split.test_end == "2026-01-01T06:00:00Z"
    assert config.runtime.random_seed == 42


def test_discriminates_logistic_regression_config() -> None:
    data = _load_experiment_mapping("training_baseline.yml")

    config = ExperimentConfig.model_validate(data)

    assert isinstance(config.model, LogisticRegressionConfig)
    assert config.model.regularization_c == 1.0


def test_discriminates_xgboost_config() -> None:
    data = _load_experiment_mapping("training_xgboost_baseline.yml")

    config = ExperimentConfig.model_validate(data)

    assert isinstance(config.model, XGBoostConfig)
    assert config.model.tree_method == "hist"
    assert config.model.imbalance_strategy == "train_ratio"


@pytest.mark.parametrize(
    ("filename", "foreign_field", "foreign_value"),
    [
        ("training_baseline.yml", "n_estimators", 100),
        ("training_xgboost_baseline.yml", "regularization_c", 1.0),
    ],
    ids=["xgboost-field-in-logistic", "logistic-field-in-xgboost"],
)
def test_rejects_model_specific_field_from_other_kind(
    filename: str,
    foreign_field: str,
    foreign_value: object,
) -> None:
    data = _load_experiment_mapping(filename)
    model = cast(dict[str, Any], data["model"])
    model[foreign_field] = foreign_value

    with pytest.raises(ValidationError) as exc_info:
        ExperimentConfig.model_validate(data)

    assert any(
        item["type"] == "extra_forbidden"
        and tuple(item["loc"])[-1] == foreign_field
        for item in exc_info.value.errors()
    )


@pytest.mark.parametrize(
    ("field_name", "invalid_value", "error_type"),
    [
        ("n_estimators", 0, "greater_than_equal"),
        ("learning_rate", 0.0, "greater_than"),
        ("max_depth", 17, "less_than_equal"),
        ("min_child_weight", -1.0, "greater_than_equal"),
        ("subsample", 1.1, "less_than_equal"),
        ("colsample_bytree", 0.0, "greater_than"),
        ("reg_alpha", -0.1, "greater_than_equal"),
        ("reg_lambda", -0.1, "greater_than_equal"),
        ("early_stopping_rounds", 0, "greater_than_equal"),
    ],
)
def test_rejects_invalid_xgboost_hyperparameter(
    field_name: str,
    invalid_value: int | float,
    error_type: str,
) -> None:
    data = _load_experiment_mapping("training_xgboost_baseline.yml")
    model = cast(dict[str, Any], data["model"])
    model[field_name] = invalid_value

    with pytest.raises(ValidationError) as exc_info:
        ExperimentConfig.model_validate(data)

    assert any(
        item["type"] == error_type and tuple(item["loc"])[-1] == field_name
        for item in exc_info.value.errors()
    )


def test_rejects_early_stopping_not_smaller_than_estimators() -> None:
    data = _load_experiment_mapping("training_xgboost_baseline.yml")
    model = cast(dict[str, Any], data["model"])
    model["n_estimators"] = 50
    model["early_stopping_rounds"] = 50

    with pytest.raises(
        ValidationError,
        match="early_stopping_rounds must be smaller than n_estimators",
    ):
        ExperimentConfig.model_validate(data)


@pytest.mark.parametrize(
    ("kind", "error_type"),
    [
        ("unknown_model", "union_tag_invalid"),
        (None, "union_tag_not_found"),
    ],
)
def test_rejects_missing_or_unknown_model_kind(
    kind: str | None,
    error_type: str,
) -> None:
    data = _load_experiment_mapping("training_baseline.yml")
    model = cast(dict[str, Any], data["model"])
    if kind is None:
        model.pop("kind")
    else:
        model["kind"] = kind

    with pytest.raises(ValidationError) as exc_info:
        ExperimentConfig.model_validate(data)

    _assert_validation_error(
        exc_info.value,
        location=("model",),
        error_type=error_type,
    )


def test_xgboost_config_is_immutable() -> None:
    data = _load_experiment_mapping("training_xgboost_baseline.yml")
    config = ExperimentConfig.model_validate(data)
    assert isinstance(config.model, XGBoostConfig)

    with pytest.raises(ValidationError) as exc_info:
        setattr(config.model, "max_depth", 8)

    _assert_validation_error(
        exc_info.value,
        location=("max_depth",),
        error_type="frozen_instance",
    )
```

Các test đi qua interface `ExperimentConfig.model_validate` hoặc loader thật.
Không test implementation nội bộ của Pydantic.

### 4.8. Kiểm tra bốn YAML không cần service

- [ ] Load cả bốn config bằng loader thật.
- [ ] In resolved model config để review.
- [ ] Xác nhận split và feature count giống ma trận 2 × 2.

```bash
uv run python - <<'PY'
from pathlib import Path

from fraudguard_ml.config import load_yaml_config
from fraudguard_ml.experiment_config import ExperimentConfig

expected = {
    "training_baseline.yml": ("logistic_regression", 4),
    "training_challenger_balance.yml": ("logistic_regression", 13),
    "training_xgboost_baseline.yml": ("xgboost", 4),
    "training_xgboost_balance.yml": ("xgboost", 13),
}

for filename, (kind, feature_count) in expected.items():
    config = load_yaml_config(Path("configs") / filename, ExperimentConfig)
    assert config.model.kind == kind
    assert len(config.dataset.feature_columns) == feature_count
    assert config.split.train_end == "2026-01-01T02:00:00Z"
    assert config.split.validation_end == "2026-01-01T04:00:00Z"
    assert config.split.test_end == "2026-01-01T06:00:00Z"
    print(filename, config.model.model_dump(mode="json"))

print("PHASE 2 CONFIG MATRIX: PASS")
PY
```

Lệnh này không truy cập ClickHouse, MinIO, Airflow hoặc snapshot. Đây là test cấu
hình thuần in-process.

### 4.9. Chạy quality checks

- [ ] Test config pass.
- [ ] Toàn bộ unit assertions hiện tại pass.
- [ ] Ruff pass trên source và tests.
- [ ] mypy pass sau khi union được narrow trong `training.py`.

```bash
uv run pytest ml/tests/test_config.py --no-cov
uv run pytest --no-cov
uv run ruff check ml/src ml/tests
uv run mypy
```

Không dùng test training XGBoost làm điều kiện Phase 2. Phase này chỉ cần xác nhận
XGBoost YAML hợp lệ và training cũ từ chối nhánh chưa triển khai bằng lỗi rõ ràng.

### 4.10. Review diff

```bash
git diff --check
git diff -- \
  ml/src/fraudguard_ml/experiment_config.py \
  ml/src/fraudguard_ml/training.py \
  ml/tests/test_config.py \
  configs/training_challenger_balance.yml

git status --short -- \
  configs/training_xgboost_baseline.yml \
  configs/training_xgboost_balance.yml
```

Kiểm tra thủ công:

- bốn config có cùng relation, target, prediction point và split;
- baseline pair có đúng bốn feature giống nhau;
- balance pair có đúng 13 feature giống nhau;
- mỗi `experiment_name` là duy nhất;
- XGBoost config không chứa `regularization_c`, `max_iter`, `class_weight`;
- Logistic config không chứa XGBoost hyperparameters;
- không có credential hoặc endpoint mới trong diff.

## 5. Script xác nhận hoàn thành Phase 2

Chạy sau khi đã thực hiện toàn bộ thay đổi:

```bash
set -Eeuo pipefail

cd /home/phongthanh/ML_Fraud_Banking

uv lock --check

uv run python - <<'PY'
from pathlib import Path

from fraudguard_ml.config import load_yaml_config
from fraudguard_ml.experiment_config import (
    ExperimentConfig,
    LogisticRegressionConfig,
    XGBoostConfig,
)

matrix = {
    "training_baseline.yml": (LogisticRegressionConfig, 4),
    "training_challenger_balance.yml": (LogisticRegressionConfig, 13),
    "training_xgboost_baseline.yml": (XGBoostConfig, 4),
    "training_xgboost_balance.yml": (XGBoostConfig, 13),
}

for filename, (model_type, feature_count) in matrix.items():
    config = load_yaml_config(Path("configs") / filename, ExperimentConfig)
    assert isinstance(config.model, model_type)
    assert len(config.dataset.feature_columns) == feature_count
    assert (
        config.split.train_end,
        config.split.validation_end,
        config.split.test_end,
    ) == (
        "2026-01-01T02:00:00Z",
        "2026-01-01T04:00:00Z",
        "2026-01-01T06:00:00Z",
    )

print("config matrix: PASS")
PY

uv run pytest ml/tests/test_config.py --no-cov
uv run pytest --no-cov
uv run ruff check ml/src ml/tests
uv run mypy

git diff --check

printf '%s\n' 'PHASE 2: PASS'
```

`PHASE 2: PASS` chỉ được in nếu mọi command trước đó thành công.

## 6. Lỗi thường gặp

### `extra_forbidden` khi load XGBoost YAML

Nguyên nhân thường là typo hoặc field Logistic bị copy sang XGBoost:

```bash
uv run python - <<'PY'
from pathlib import Path
from fraudguard_ml.config import load_yaml_config
from fraudguard_ml.experiment_config import ExperimentConfig

load_yaml_config(Path("configs/training_xgboost_baseline.yml"), ExperimentConfig)
PY
```

Đọc `loc` trong `ValidationError`; không đổi `extra="forbid"` thành `ignore`.

### `union_tag_invalid` hoặc `union_tag_not_found`

Kiểm tra field bắt buộc:

```yaml
model:
  kind: xgboost
```

Chỉ chấp nhận `logistic_regression` hoặc `xgboost`.

### mypy báo union không có `regularization_c`

Guard trong `build_pipeline` chưa được thêm hoặc estimator vẫn đọc
`config.model.regularization_c`. Narrow về `LogisticRegressionConfig`, rồi chỉ đọc
từ biến `model_config`.

Không dùng `cast(LogisticRegressionConfig, config.model)` để che lỗi vì nó cho
phép XGBoost config đi vào Logistic estimator lúc runtime.

### XGBoost YAML load được nhưng command `train` báo chưa hỗ trợ

Đây là hành vi đúng của Phase 2. Model config đã hợp lệ, nhưng XGBoost training
adapter chỉ được triển khai ở Phase 3.

### Snapshot báo split thiếu row hoặc fraud positive

Đây là vấn đề dữ liệu, không phải model config. Kiểm tra dữ liệu đã được ingest đủ
đến `2026-01-01T06:00:00Z`. Không tự mở rộng split của riêng một candidate vì sẽ
làm phép so sánh 2 × 2 không công bằng.

## 7. Rollback

Nếu cần quay lại Logistic-only configuration:

1. Khôi phục `ModelConfig` cũ trong `experiment_config.py`.
2. Gỡ compatibility guard khỏi `training.py`.
3. Gỡ test union mới.
4. Bỏ hai XGBoost YAML.
5. Khôi phục split challenger nếu thật sự cần.

Không rollback dependency XGBoost của Phase 1 và không xóa snapshot, Docker volume
hoặc model artifact.

## 8. Definition of Done

Phase 2 chỉ hoàn thành khi toàn bộ checklist sau đạt:

- [ ] Có `LogisticRegressionConfig` với bounded hyperparameters.
- [ ] Có `XGBoostConfig` với bounded hyperparameters.
- [ ] `ModelConfig` là discriminated union dùng `kind`.
- [ ] `ExperimentConfig.model` tiếp tục là interface duy nhất cho caller.
- [ ] Unknown hoặc missing `kind` bị reject.
- [ ] Logistic field trong XGBoost bị reject.
- [ ] XGBoost field trong Logistic bị reject.
- [ ] `early_stopping_rounds < n_estimators` được validate.
- [ ] `training.py` narrow union an toàn và vẫn chạy Logistic Regression.
- [ ] `training_baseline.yml` load thành công.
- [ ] `training_challenger_balance.yml` load thành công.
- [ ] `training_xgboost_baseline.yml` load thành công.
- [ ] `training_xgboost_balance.yml` load thành công.
- [ ] Bốn config đều dùng split 2h/4h/6h.
- [ ] Baseline pair có cùng bốn feature.
- [ ] Balance pair có cùng 13 feature.
- [ ] Test sai model-specific field pass.
- [ ] Test giới hạn XGBoost hyperparameter pass.
- [ ] Test config immutability pass.
- [ ] Toàn bộ unit assertions pass với `pytest --no-cov`.
- [ ] `ruff check ml/src ml/tests` pass.
- [ ] `mypy` pass.
- [ ] `git diff --check` pass.
- [ ] Không có thay đổi ngoài phạm vi hoặc credential trong diff.

Sau khi toàn bộ mục trên được tick, cập nhật Phase 2 trong roadmap và chuyển sang
Phase 3 — tạo model interface chung.
