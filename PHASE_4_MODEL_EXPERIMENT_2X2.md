# Phase 4 — Chạy model experiment 2 × 2 hoàn chỉnh

Tài liệu này hướng dẫn triển khai Phase 4 trong
[`XGBOOST_EXPERIMENT_ROADMAP.md`](XGBOOST_EXPERIMENT_ROADMAP.md).

Mục tiêu của Phase 4 là chạy và so sánh công bằng bốn candidate trên validation:

| ID | Model | Feature set | Config |
| --- | --- | --- | --- |
| A | Logistic Regression | Baseline 4 features | `configs/training_baseline.yml` |
| B | XGBoost | Baseline 4 features | `configs/training_xgboost_baseline.yml` |
| C | Logistic Regression | Balance challenger | `configs/training_challenger_balance.yml` |
| D | XGBoost | Balance challenger | `configs/training_xgboost_balance.yml` |

Phase này chỉ dùng train và validation. Không chạy lệnh `evaluate`, không đọc
`evaluation.json` và không chọn lại model dựa trên test. Final winner và test
evaluation thuộc Phase 6.

## 1. Kết quả cuối Phase 4

Sau khi hoàn thành, repository cần có bằng chứng sau:

```text
airflow_ml_artifacts/model_experiments/<RUN_ID>/
├── shared/
│   ├── artifact.json
│   └── dbt_target/
│       └── manifest.json
├── candidates/
│   ├── A/
│   │   ├── experiment/dataset_manifest.json
│   │   └── model/validation_metrics.json
│   ├── B/
│   │   ├── experiment/dataset_manifest.json
│   │   └── model/validation_metrics.json
│   ├── C/
│   │   ├── experiment/dataset_manifest.json
│   │   └── model/validation_metrics.json
│   └── D/
│       ├── experiment/dataset_manifest.json
│       └── model/validation_metrics.json
└── comparison/
    ├── experiment_invariants.json
    └── validation_comparison.csv
```

`validation_comparison.csv` phải có đúng bốn row và tối thiểu các cột:

```text
candidate_id
model
feature_set
population_fingerprint
train_rows
train_fraud
best_iteration
scale_pos_weight
threshold
validation_pr_auc
validation_roc_auc
validation_precision
validation_recall
validation_f1
validation_alert_rate
training_seconds
```

## 2. Nguyên tắc bắt buộc

Mọi candidate phải có cùng:

- source relation;
- population fingerprint;
- temporal split boundaries;
- row count và fraud count của từng split;
- target;
- prediction point;
- label policy;
- random seed `42`;
- dbt manifest hash;
- threshold strategy và minimum precision.

Hai candidate cùng feature set phải có feature list giống hệt nhau:

- A và B dùng 4 baseline features;
- C và D dùng balance challenger features.

Khác biệt được phép chỉ gồm:

- model family;
- preprocessing dành riêng cho model;
- feature set baseline hoặc balance;
- hyperparameter đã khai báo trước trong config.

Không được:

- grid search sau khi xem validation result;
- sửa threshold bằng test;
- chạy candidate với snapshot cũ khác population;
- copy test metrics vào bảng Phase 4;
- chọn XGBoost chỉ vì model phức tạp hơn;
- bỏ candidate thất bại khỏi report mà không ghi lý do.

## 3. Pre-flight gate — chưa được chạy Phase 4 ngay

### 3.1. Trạng thái quan sát ngày 2026-08-25

Repository hiện chưa đạt điều kiện bắt đầu Phase 4:

- `import fraudguard_ml.training` fail vì `ModelingError` chưa tồn tại;
- `modeling.py` khai báo `FittedProbabilityModel` hai lần;
- `training.py` thiếu import `ArtifactError`, `sha256_file`, `DatasetSplits` và
  `DatasetManifest`;
- `training.py` còn stale imports từ implementation Logistic cũ;
- `cli.py` vẫn import `feature_groups` từ `training.py`, nhưng hàm đã bị xóa;
- Ruff báo 23 lỗi trong seam modeling/training/evaluation;
- Mypy báo 23 lỗi trong bốn file;
- chưa có `ml/tests/test_modeling.py` và `ml/tests/test_training.py`;
- `configs/training_data_contract.yml` không tồn tại, làm 15 contract tests lỗi;
- config tests riêng vẫn pass: `16 passed`.

Đây là blocker, không phải lỗi của experiment runner. Chạy bốn candidate trong
trạng thái này chỉ tạo bốn failure giống nhau.

### 3.2. Điều kiện mở gate

Hoàn thành Phase 3 trước. Tối thiểu:

- [ ] `ModelingError` tồn tại đúng một lần;
- [ ] `FittedProbabilityModel` tồn tại đúng một lần và có `predict_proba`;
- [ ] `training.py` import đủ dependency, không còn stale imports;
- [ ] split diagnostics lấy feature groups từ seam hợp lệ, không import hàm đã xóa;
- [ ] `evaluation.py` load đúng bundle schema mới;
- [ ] `training_data_contract.yml` được phục hồi hoặc thay bằng contract đã duyệt;
- [ ] modeling tests và training tests tồn tại;
- [ ] cả bốn YAML config load thành công;
- [ ] import, Ruff, Mypy và targeted tests đều pass.

Chạy gate:

```bash
cd /home/phongthanh/ML_Fraud_Banking

uv run python -c \
  "import fraudguard_ml.modeling; import fraudguard_ml.training; import fraudguard_ml.evaluation"

uv run ruff check \
  ml/src/fraudguard_ml/modeling.py \
  ml/src/fraudguard_ml/training.py \
  ml/src/fraudguard_ml/evaluation.py \
  ml/src/fraudguard_ml/experiment_config.py \
  ml/tests

uv run mypy ml/src/fraudguard_ml ml/tests

uv run pytest \
  ml/tests/test_config.py \
  ml/tests/test_modeling.py \
  ml/tests/test_training.py \
  --no-cov
```

Nếu một lệnh fail, dừng Phase 4. Không dùng notebook để bypass package lỗi.

## 4. Bổ sung evidence còn thiếu trong training artifact

Roadmap yêu cầu `training_seconds`, `train_rows` và `train_fraud`. Implementation
hiện tại chưa lưu các trường này. Nên bổ sung tại seam
`train_and_select_threshold`, không đo toàn bộ CLI vì download/cache time không
phải model training time.

### 4.1. Định nghĩa `training_seconds`

Trong Phase 4:

```text
training_seconds = thời gian fit preprocessing + fit estimator
```

Không gồm:

- download snapshot;
- load Parquet;
- split diagnostics;
- threshold selection;
- ghi artifact;
- test evaluation.

Định nghĩa này giúp Logistic và XGBoost được đo trên cùng một đoạn code.

### 4.2. Thay đổi dự kiến trong `training.py`

Thêm import:

```python
from time import perf_counter
```

Bao quanh đúng lời gọi model fitting:

```python
started_at = perf_counter()
try:
    model = fit_probability_model(
        config,
        splits.train,
        splits.validation,
    )
except ModelingError as exc:
    raise TrainingError(str(exc)) from exc
training_seconds = perf_counter() - started_at
```

Tạo training summary từ train split:

```python
train_rows = len(splits.train.target)
train_fraud = int(splits.train.target.sum())
```

Thêm vào `validation_metrics`:

```python
validation_metrics = {
    **binary_metrics(splits.validation.target, probability, threshold),
    "threshold_selection": selection,
    "model_metadata": model_metadata,
    "training_seconds": training_seconds,
    "train_rows": train_rows,
    "train_fraud": train_fraud,
    "dataset_manifest_sha256": sha256_file(manifest_path),
    "population_fingerprint": manifest.population_fingerprint,
}
```

Thêm vào giá trị trả về để CLI log được:

```python
return {
    "model_path": str(model_path),
    "model_sha256": sha256_file(model_path),
    "validation_metrics_path": str(metrics_path),
    "model_kind": model.metadata.model_kind,
    "best_iteration": model.metadata.best_iteration,
    "scale_pos_weight": model.metadata.scale_pos_weight,
    "threshold": threshold,
    "training_seconds": training_seconds,
    "train_rows": train_rows,
    "train_fraud": train_fraud,
}
```

Không thêm `feature_set` vào core model config chỉ để phục vụ report. Phase 4
runner có thể xác định feature set từ candidate registry và xác minh lại bằng
manifest feature list.

### 4.3. Test evidence mới

Trong `ml/tests/test_training.py`, test cần chứng minh:

- `training_seconds` tồn tại, hữu hạn và không âm;
- `train_rows` bằng số row train;
- `train_fraud` bằng số positive train;
- `model_metadata.model_kind` được lưu;
- Logistic có `best_iteration = null` và `scale_pos_weight = null`;
- XGBoost có `best_iteration` hợp lệ;
- XGBoost `scale_pos_weight` chỉ tính từ train;
- validation metrics không chứa test metrics.

Không assert thời gian chính xác theo wall clock. Có thể monkeypatch
`perf_counter` để test deterministic hoặc chỉ assert type/range.

## 5. Vì sao Phase 4 dùng bốn snapshot

Current manifest bind với:

- experiment config hash;
- feature list;
- experiment name;
- snapshot hash.

Baseline và balance feature sets tạo Parquet projection khác nhau. Dùng một
balance snapshot rồi âm thầm cắt còn bốn features sẽ làm manifest feature list
không khớp config baseline. Dùng Logistic manifest cho XGBoost config cũng làm
training config provenance sai.

Vì dataset hiện chỉ có 6.534 row, phương án rõ ràng nhất là tạo bốn snapshot,
mỗi snapshot bind đúng candidate config. Tất cả snapshot phải được tạo từ cùng
một dbt build, khi mart không thay đổi giữa các lần query.

`population_fingerprint` hiện hash business key, event time và target; nó chứng
minh population/label giống nhau, không tự chứng minh mọi feature value giống
nhau. Vì vậy:

1. chạy một dbt build duy nhất;
2. không chạy lại dbt hoặc ingestion trong lúc tạo bốn snapshot;
3. dùng cùng dbt manifest cho cả bốn;
4. so sánh population fingerprint và split statistics sau snapshot.

Với full dataset trong tương lai, nên tách dataset snapshot config khỏi model
config để tránh duplicate snapshot. Không cần refactor kiến trúc đó trong phiên
bản portfolio hiện tại.

## 6. Candidate registry

Phase 4 dùng registry cố định sau:

```text
A|logistic_regression|baseline|configs/training_baseline.yml
B|xgboost|baseline|configs/training_xgboost_baseline.yml
C|logistic_regression|balance|configs/training_challenger_balance.yml
D|xgboost|balance|configs/training_xgboost_balance.yml
```

Không sửa hyperparameter sau khi đã chạy candidate đầu tiên. Nếu config thay
đổi, toàn bộ matrix phải dùng `RUN_ID` mới.

## 7. Pre-run kiểm tra bốn config

Chạy trước khi tạo artifact:

```bash
uv run python - <<'PY'
from pathlib import Path

from fraudguard_ml.config import load_yaml_config
from fraudguard_ml.experiment_config import ExperimentConfig, XGBoostConfig

candidates = {
    "A": Path("configs/training_baseline.yml"),
    "B": Path("configs/training_xgboost_baseline.yml"),
    "C": Path("configs/training_challenger_balance.yml"),
    "D": Path("configs/training_xgboost_balance.yml"),
}

for candidate_id, path in candidates.items():
    config = load_yaml_config(path, ExperimentConfig)
    print(
        candidate_id,
        config.experiment_name,
        config.model.kind,
        len(config.dataset.feature_columns),
        config.split.train_end,
        config.split.validation_end,
        config.split.test_end,
        config.runtime.random_seed,
    )
PY
```

Kết quả mong đợi:

```text
A fraudguard_logistic_baseline logistic_regression 4 ... 42
B fraudguard_xgboost_baseline xgboost 4 ... 42
C fraudguard_balance_challenger logistic_regression 13 ... 42
D fraudguard_xgboost_balance xgboost 13 ... 42
```

Kiểm tra programmatic invariants trước khi chạy:

```bash
uv run python - <<'PY'
from pathlib import Path

from fraudguard_ml.config import load_yaml_config
from fraudguard_ml.experiment_config import ExperimentConfig

paths = (
    Path("configs/training_baseline.yml"),
    Path("configs/training_xgboost_baseline.yml"),
    Path("configs/training_challenger_balance.yml"),
    Path("configs/training_xgboost_balance.yml"),
)
configs = [load_yaml_config(path, ExperimentConfig) for path in paths]

assert {config.dataset.relation for config in configs} == {
    "fraudguard_ml.ml_training_transactions"
}
assert {config.dataset.target_column for config in configs} == {"is_fraud"}
assert {config.dataset.prediction_point for config in configs} == {
    "post_ledger_update"
}
assert {config.snapshot.label_policy for config in configs} == {
    "static_final_labels"
}
assert {config.runtime.random_seed for config in configs} == {42}
assert {
    (
        config.split.train_end,
        config.split.validation_end,
        config.split.test_end,
    )
    for config in configs
} == {
    (
        "2026-01-01T02:00:00Z",
        "2026-01-01T04:00:00Z",
        "2026-01-01T06:00:00Z",
    )
}
assert configs[0].dataset.feature_columns == configs[1].dataset.feature_columns
assert configs[2].dataset.feature_columns == configs[3].dataset.feature_columns
assert configs[0].dataset.feature_columns != configs[2].dataset.feature_columns

print("candidate config invariants: passed")
PY
```

## 8. Chuẩn bị environment

Không ghi secret vào command history hoặc artifact. Dùng `.env` local đã được
Git ignore:

```bash
cd /home/phongthanh/ML_Fraud_Banking

set -a
source .env
set +a
```

Cần tối thiểu:

```text
DBT_CLICKHOUSE_HOST
DBT_CLICKHOUSE_PORT
DBT_CLICKHOUSE_DATABASE
DBT_CLICKHOUSE_USER
DBT_CLICKHOUSE_PASSWORD

CLICKHOUSE_ML_HOST
CLICKHOUSE_ML_PORT
CLICKHOUSE_ML_DATABASE
CLICKHOUSE_ML_USER
CLICKHOUSE_ML_PASSWORD
CLICKHOUSE_ML_SECURE

MINIO_ENDPOINT
MINIO_ACCESS_KEY hoặc MINIO_AIRFLOW_USER
MINIO_SECRET_KEY hoặc MINIO_AIRFLOW_PASSWORD
```

Không in toàn bộ environment để debug. Chỉ kiểm tra tên biến thiếu.

## 9. Tạo shared dbt build và contract artifact

Tạo một `RUN_ID` UTC cho toàn bộ matrix:

```bash
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_ROOT="airflow_ml_artifacts/model_experiments/${RUN_ID}"
SHARED_ROOT="${RUN_ROOT}/shared"
DBT_TARGET="${SHARED_ROOT}/dbt_target"
CONTRACT_ARTIFACT="${SHARED_ROOT}/artifact.json"
CACHE_ROOT="${RUN_ROOT}/cache"

mkdir -p "${DBT_TARGET}" "${CACHE_ROOT}"
```

Build đúng training lineage một lần:

```bash
uv run dbt build \
  --project-dir dbt \
  --profiles-dir dbt \
  --target dev \
  --target-path "${DBT_TARGET}" \
  --select +tag:training \
  --fail-fast
```

Validate training relation một lần:

```bash
uv run python -m fraudguard_ml validate-training-data \
  --config configs/training_data_contract.yml \
  --dbt-manifest "${DBT_TARGET}/manifest.json" \
  --repository-root . \
  --output "${CONTRACT_ARTIFACT}"
```

Gate:

```bash
test -s "${DBT_TARGET}/manifest.json"
test -s "${CONTRACT_ARTIFACT}"

uv run python - <<PY
import json
from pathlib import Path

artifact = json.loads(Path("${CONTRACT_ARTIFACT}").read_text("utf-8"))
assert artifact["status"] == "validated"
assert artifact["validation"]["relation"] == (
    "fraudguard_ml.ml_training_transactions"
)
print("shared contract artifact: passed")
PY
```

Trong lúc tạo bốn snapshot, không chạy lại dbt build và không trigger ingestion
làm thay đổi mart.

## 10. Chạy bốn candidate tuần tự

Chạy tuần tự giúp `training_seconds` dễ so sánh hơn chạy song song và tránh bốn
process tranh CPU/RAM.

```bash
set -euo pipefail

while IFS='|' read -r CANDIDATE_ID MODEL_KIND FEATURE_SET CONFIG_PATH; do
  CANDIDATE_ROOT="${RUN_ROOT}/candidates/${CANDIDATE_ID}"
  EXPERIMENT_DIR="${CANDIDATE_ROOT}/experiment"
  MODEL_DIR="${CANDIDATE_ROOT}/model"

  mkdir -p "${EXPERIMENT_DIR}" "${MODEL_DIR}"

  printf 'candidate=%s model=%s feature_set=%s config=%s\n' \
    "${CANDIDATE_ID}" \
    "${MODEL_KIND}" \
    "${FEATURE_SET}" \
    "${CONFIG_PATH}"

  uv run python -m fraudguard_ml snapshot-training-dataset \
    --config "${CONFIG_PATH}" \
    --contract-artifact "${CONTRACT_ARTIFACT}" \
    --dbt-manifest "${DBT_TARGET}/manifest.json" \
    --repository-root . \
    --run-id "${RUN_ID}" \
    --output "${EXPERIMENT_DIR}"

  uv run python -m fraudguard_ml train \
    --config "${CONFIG_PATH}" \
    --dataset-manifest "${EXPERIMENT_DIR}/dataset_manifest.json" \
    --cache-dir "${CACHE_ROOT}" \
    --output "${MODEL_DIR}"

  test -s "${EXPERIMENT_DIR}/dataset_manifest.json"
  test -s "${MODEL_DIR}/model_bundle.joblib"
  test -s "${MODEL_DIR}/validation_metrics.json"
done <<'EOF'
A|logistic_regression|baseline|configs/training_baseline.yml
B|xgboost|baseline|configs/training_xgboost_baseline.yml
C|logistic_regression|balance|configs/training_challenger_balance.yml
D|xgboost|balance|configs/training_xgboost_balance.yml
EOF
```

Không thêm lệnh sau trong Phase 4:

```bash
# Không chạy trong Phase 4.
uv run python -m fraudguard_ml evaluate ...
```

### Rerun policy

Artifact local và object storage là immutable. Nếu matrix fail giữa chừng:

- không xóa hoặc overwrite candidate đã chạy để che failure;
- ghi lại failure reason;
- sửa code bằng change request riêng;
- dùng `RUN_ID` mới để chạy lại toàn bộ matrix.

Không tái sử dụng ba candidate cũ rồi chỉ chạy lại candidate vừa sửa. Code version
và runtime state khi đó khác nhau.

## 11. Script tổng hợp và xác minh comparison

Tạo file `scripts/build_validation_comparison.py`. Script chỉ đọc manifest và
validation metrics; nó không load model, không load Parquet và không chạm test.

```python
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
```

### Lưu ý cho script

`config.model.n_estimators` chỉ được truy cập trong nhánh XGBoost sau khi model
kind đã được kiểm tra. Mypy có thể cần narrowing rõ hơn bằng
`isinstance(config.model, XGBoostConfig)` tùy implementation cuối Phase 3. Nếu
Mypy báo union attribute error, import `XGBoostConfig`, kiểm tra `isinstance` rồi
mới đọc `n_estimators`.

`scale_pos_weight` check phía trên áp dụng khi cả hai XGBoost config dùng
`imbalance_strategy: train_ratio`. Nếu config chuyển sang `none`, expected value
phải là `1.0`; không được giữ công thức ratio một cách âm thầm.

## 12. Test cho comparison script

Tạo `ml/tests/test_validation_comparison.py` hoặc
`scripts/tests/test_build_validation_comparison.py`, tùy test layout được duyệt.

Test matrix tối thiểu:

| Case | Kết quả |
| --- | --- |
| Đủ A/B/C/D và invariants khớp | Pass, ghi hai artifacts |
| Thiếu candidate D | Fail |
| Population fingerprint khác | Fail |
| Split boundary khác | Fail |
| dbt manifest hash khác | Fail |
| Metrics manifest hash sai | Fail |
| Model kind sai config | Fail |
| Feature list sai config | Fail |
| Seed khác 42 | Fail |
| `train_rows` hoặc `train_fraud` sai | Fail |
| XGBoost thiếu `best_iteration` | Fail |
| `scale_pos_weight` không tính từ train | Fail |
| Metric NaN/Infinity/ngoài domain | Fail |
| Output đã tồn tại | Fail, không overwrite |

Unit tests dùng temporary artifacts nhỏ; không cần ClickHouse, MinIO hoặc train
XGBoost thật.

## 13. Chạy comparison builder

Sau khi bốn candidate thành công:

```bash
uv run python scripts/build_validation_comparison.py \
  --repository-root . \
  --run-root "${RUN_ROOT}"
```

Xem bảng:

```bash
uv run python - <<PY
import pandas as pd

path = "${RUN_ROOT}/comparison/validation_comparison.csv"
frame = pd.read_csv(path)
print(frame.to_string(index=False))
PY
```

Kiểm tra không có test artifact trong run root:

```bash
if find "${RUN_ROOT}" -type f \
  \( -name 'evaluation.json' -o -name '*test*metrics*' \) \
  -print -quit | grep -q .; then
  printf '%s\n' "Phase 4 must not contain test evaluation artifacts" >&2
  exit 1
fi
```

## 14. Cách đọc validation comparison

### 14.1. Bắt đầu bằng invariants

Không nhìn metric trước khi các invariant pass. Nếu fingerprint hoặc split khác,
bảng không hợp lệ dù model score cao.

### 14.2. Kiểm tra threshold strategy

Vì cả bốn candidate chọn `max_recall_at_min_precision` với minimum precision
`10%`, nhiều candidate có thể đạt precision đúng gần `0.10`. Đây không phải bug;
threshold đang tìm recall cao nhất dưới constraint đó.

### 14.3. So sánh theo thứ tự

Trong Phase 4, dùng thứ tự phân tích:

1. candidate có đạt validation precision tối thiểu không;
2. validation recall;
3. PR-AUC;
4. alert rate;
5. stability/độ hợp lý của threshold;
6. training time;
7. XGBoost best iteration;
8. complexity và explainability.

Phase 4 có thể tạo shortlist và nhận xét. Quyết định winner chính thức thuộc
Phase 6 sau khi selection record được đóng băng.

### 14.4. Ý nghĩa bốn phép so sánh

| So sánh | Câu hỏi |
| --- | --- |
| B so với A | XGBoost có hơn Logistic trên cùng baseline features không? |
| D so với C | XGBoost có hơn Logistic trên cùng balance features không? |
| C so với A | Balance features có giúp Logistic không? |
| D so với B | Balance features có giúp XGBoost không? |

Không chỉ so D với A. Nếu D tốt hơn A, cần biết improvement đến từ model,
feature set hay cả hai.

### 14.5. Dữ liệu nhỏ làm metric không ổn định

Validation hiện chỉ có 14 fraud. Một fraud thay đổi recall khoảng:

```text
1 / 14 = 7,14 percentage points
```

Do đó chênh lệch recall nhỏ có thể chỉ là một transaction. Không dùng các cụm
từ như “XGBoost vượt trội” nếu bằng chứng chỉ khác một positive case.

Nên report:

- số TP/FP/FN/TN, không chỉ tỷ lệ;
- PR-AUC;
- alert count và alert rate;
- chênh lệch tuyệt đối;
- giới hạn do sample nhỏ.

## 15. Early stopping và validation reuse

Thiết kế Phase 3 dùng validation làm XGBoost `eval_set` cho early stopping. Sau
đó cùng validation được dùng để:

- chọn threshold;
- tính metrics;
- so sánh candidate.

Điều này làm XGBoost thích nghi với validation nhiều hơn Logistic Regression và
có thể tạo optimistic bias. Với portfolio nhỏ, có thể chấp nhận nếu:

- không tuning thêm dựa trên validation;
- ghi rõ limitation;
- test chỉ dùng sau khi winner đã khóa;
- không tuyên bố performance production.

Thiết kế chặt hơn trong tương lai:

```text
train_fit -> fit model
train_early_stop -> XGBoost early stopping
validation -> threshold + candidate comparison
test -> final evaluation
```

Snapshot hiện chỉ có 24 fraud trong train, nên chia thêm early-stop set có thể
làm estimate còn nhiễu hơn. Không mở rộng scope này trong Phase 4 nếu chưa tăng
dữ liệu.

## 16. Training time fairness

Để timing có ý nghĩa:

- chạy candidate tuần tự;
- dùng cùng máy/container;
- giữ `max_cpu_threads` giống nhau;
- không chạy workload nặng song song;
- đo đúng preprocessing + estimator fit;
- ghi version Python, sklearn, XGBoost và CPU metadata;
- không dùng timing là tiêu chí duy nhất trên snapshot chỉ 6.534 row.

XGBoost import và native runtime warm-up có thể tạo first-run overhead. Nếu cần
timing ổn định hơn, chạy một smoke fit ngoài experiment trước khi tạo `RUN_ID`,
nhưng không dùng warm-up score.

## 17. Báo cáo nhận xét cho từng candidate

Mỗi candidate cần một đoạn nhận xét theo template:

```markdown
### Candidate <ID> — <model> / <feature set>

- Population fingerprint:
- Train rows/fraud:
- Validation PR-AUC:
- Validation precision/recall:
- Alert rate:
- Threshold:
- Training seconds:
- Best iteration/scale_pos_weight:
- Điểm mạnh:
- Failure mode:
- Có đạt minimum precision không:
- Có được vào shortlist không:
- Giới hạn của kết luận:
```

Ví dụ cách viết đúng:

> Candidate D có validation PR-AUC cao hơn B nhưng recall chỉ khác một fraud
> case. Alert rate cũng cao hơn. Với 14 fraud trong validation, bằng chứng chưa
> đủ để kết luận balance features cải thiện ổn định.

Ví dụ không nên viết:

> XGBoost balance là model tốt nhất và sẵn sàng production.

## 18. Failure policy

Nếu một candidate fail:

1. lưu error category và log ngắn nhất đủ chẩn đoán;
2. xác định lỗi code, config, data hay infrastructure;
3. không thay hyperparameter chỉ để làm candidate pass nếu thay đổi không được
   duyệt trước;
4. sửa qua phase/change request liên quan;
5. tạo `RUN_ID` mới;
6. chạy lại đủ bốn candidate.

Không điền metric `0` cho candidate fail. `0` là một giá trị metric hợp lệ, không
phải missing/failure marker.

## 19. Các lệnh kiểm tra sau experiment

### Package quality

```bash
uv run ruff check \
  ml/src/fraudguard_ml \
  ml/tests \
  scripts/build_validation_comparison.py

uv run ruff format --check \
  ml/src/fraudguard_ml \
  ml/tests \
  scripts/build_validation_comparison.py

uv run mypy ml/src/fraudguard_ml ml/tests
```

Nếu script nằm ngoài Mypy `files`, chạy thêm:

```bash
uv run mypy scripts/build_validation_comparison.py
```

### Tests

```bash
uv run pytest \
  ml/tests/test_config.py \
  ml/tests/test_modeling.py \
  ml/tests/test_training.py \
  ml/tests/test_validation_comparison.py \
  --no-cov
```

Sau khi targeted tests xanh, chạy full suite:

```bash
uv run pytest --no-cov
```

Nếu full suite fail do file contract bị thiếu, đó vẫn là blocker. Không tuyên bố
Phase 4 hoàn thành chỉ vì targeted tests pass.

### Artifact checks

```bash
test "$(find "${RUN_ROOT}/candidates" -name validation_metrics.json | wc -l)" -eq 4
test "$(find "${RUN_ROOT}/candidates" -name dataset_manifest.json | wc -l)" -eq 4
test -s "${RUN_ROOT}/comparison/validation_comparison.csv"
test -s "${RUN_ROOT}/comparison/experiment_invariants.json"
```

## 20. Các lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `ImportError: cannot import name 'ModelingError'` | Phase 3 chưa hoàn tất | Sửa seam và test Phase 3 trước |
| `feature_groups` không tồn tại | CLI còn phụ thuộc API cũ | Chuyển helper sang modeling seam hoặc module dùng chung |
| `training_data_contract.yml` không tồn tại | Contract file bị xóa/đổi tên | Phục hồi hoặc migrate có phê duyệt; không bỏ validation |
| `relevant source/config paths must be committed and clean` | Provenance path chưa clean | Review và commit đúng code/config dùng cho run |
| `manifest feature order does not match config` | Dùng manifest candidate khác | Mỗi candidate dùng đúng manifest của nó |
| `refusing to overwrite immutable object` | Reuse `RUN_ID` với nội dung khác | Tạo `RUN_ID` mới |
| Population fingerprint khác | Mart thay đổi giữa snapshots | Dừng, rebuild shared state, chạy lại toàn matrix |
| XGBoost không có `best_iteration` | Early stopping/eval set sai | Sửa Phase 3; không tự điền `n_estimators - 1` |
| `scale_pos_weight` khác expected | Tính từ validation/toàn data | Tính lại chỉ từ train target |
| Precision dưới 10% | Fallback threshold hoặc model yếu | Ghi failure; không hạ constraint sau khi xem kết quả |
| Training time khác thường | Resource contention/warm-up | Kiểm tra runtime; không xóa metric bất lợi |

## 21. Không làm trong Phase 4

- Không tạo notebook visualization; thuộc Phase 5.
- Không chọn final winner và chạy test; thuộc Phase 6.
- Không sửa Airflow DAG; thuộc Phase 7.
- Không cập nhật README bằng kết quả cuối; thuộc Phase 8.
- Không thêm Optuna, MLflow hoặc grid search.
- Không load thêm model family thứ ba.
- Không thay feature engineering trong dbt mart.
- Không dùng test để giải quyết tie trên validation.

## 22. Definition of Done

Phase 4 hoàn thành khi tất cả điều kiện sau đúng:

### Pre-flight

- [ ] Phase 3 import gate pass.
- [ ] Ruff pass.
- [ ] Mypy pass.
- [ ] Modeling/training/config tests pass.
- [ ] Full test suite không còn lỗi contract file thiếu.

### Experiment execution

- [ ] Shared dbt build pass.
- [ ] Shared training data contract có status `validated`.
- [ ] Bốn candidate dùng seed `42`.
- [ ] Bốn candidate dùng cùng split boundaries.
- [ ] Bốn candidate có cùng population fingerprint.
- [ ] Bốn candidate có cùng split row/fraud statistics.
- [ ] A/B có cùng baseline feature list.
- [ ] C/D có cùng balance feature list.
- [ ] Mỗi candidate có manifest, model bundle và validation metrics.
- [ ] XGBoost metadata có `best_iteration` và `scale_pos_weight` hợp lệ.
- [ ] Mọi candidate có `training_seconds`.

### Comparison evidence

- [ ] `validation_comparison.csv` có đúng bốn row A/B/C/D.
- [ ] `experiment_invariants.json` được ghi bất biến.
- [ ] Không có test evaluation artifact trong Phase 4 run root.
- [ ] Mỗi candidate có nhận xét và failure-mode analysis.
- [ ] Kết luận ghi rõ uncertainty do chỉ có 14 validation fraud.
- [ ] Không tuyên bố XGBoost tốt hơn nếu improvement không rõ ràng.

## 23. Handoff sang Phase 5

Phase 5 notebook chỉ đọc:

- bốn validation metrics;
- bốn manifests;
- `validation_comparison.csv`;
- `experiment_invariants.json`;
- model artifacts khi cần coefficient/feature importance.

Notebook không được:

- copy lại training implementation;
- fit lại model với hyperparameter khác;
- chạy test evaluation;
- chỉnh threshold;
- bỏ candidate khỏi bảng.

Handoff note nên ghi:

```markdown
Phase 4 run ID: <RUN_ID>
Population fingerprint: <fingerprint>
Candidate matrix complete: yes/no
Validation fraud count: 14
Test accessed: no
Known limitation: XGBoost early stopping reused validation
Comparison artifact: <path>/validation_comparison.csv
```

Khi handoff này đầy đủ, Phase 5 có thể tập trung vào visualization và giải thích
thay vì âm thầm thay đổi experiment protocol.
