# Phase 7 — Tích hợp selected model vào Airflow

Tài liệu này giả định Phase 1–6 đã hoàn tất và kết quả lựa chọn model đã được
khóa trước khi bắt đầu Phase 7.

## 1. Kết quả đầu vào từ Phase 6

Winner được dùng trong tài liệu này là:

| Thuộc tính | Giá trị đã khóa |
| --- | --- |
| Candidate | D |
| Model | XGBoost |
| Feature set | Balance |
| Validation PR-AUC | 0.9556 |
| Validation recall | 100% (14/14 fraud) |
| Validation precision | 10.14% |
| Validation alert rate | 12.35% |
| Validation threshold | 0.2171 |
| Random seed | 42 |

Candidate C cũng đạt recall 100% nhưng PR-AUC thấp hơn D 0.1072, lớn hơn
`PR_AUC_TOLERANCE = 0.01`; vì vậy rule ưu tiên Logistic Regression đơn giản hơn
không được kích hoạt.

Phase 7 không chạy lại quá trình lựa chọn A/B/C/D và không chỉnh hyperparameter
dựa trên test result. Mục tiêu duy nhất là chứng minh selected configuration chạy
được end-to-end bằng DAG hiện tại.

> **Threshold:** `0.2171` là threshold nằm trong fitted model bundle của Phase 6.
> Schema hiện tại lưu threshold như một fitted artifact, không phải một field của
> YAML. Vì vậy config chính thức khóa model, feature set, random seed và threshold
> policy; không thêm một field `fixed_threshold` ngoài schema. Với cùng immutable
> population, split và seed, pipeline phải tái tạo kết quả. Nếu dữ liệu thay đổi,
> run mới được xem là một training run mới và không được so ngược lại để chỉnh
> winner dựa trên test.

## 2. Phạm vi thay đổi

Các file cần tạo hoặc sửa:

```text
configs/training_selected.yml                    # tạo mới
ml/tests/test_selected_model_config.py           # tạo mới
scripts/verify_selected_training_run.py          # tạo mới
airflow/dags/fraudguard_training.py               # thay nội dung
docker-compose.yml                                # thêm một environment variable
.env.example                                      # thêm default không chứa secret
```

Task graph sau thay thế DAG mang tên baseline:

```text
prepare_snapshot
      |
      v
split_diagnostics
      |
      v
    train
      |
      v
   evaluate
      |
      v
verify_artifacts
```

Không tạo DAG tuning, không đọc notebook từ Airflow và không tự động deploy
model. Notebook/Phase 6 là nơi ra quyết định; Airflow chỉ thực thi configuration
đã được phê duyệt.

## 3. Tạo config chính thức cho winner

Tạo `configs/training_selected.yml`:

```yaml
schema_version: 1
experiment_name: fraudguard_selected_xgboost_balance

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
  max_cpu_threads: 8
  memory_limit_gib: 6.0
```

Không sửa trực tiếp `configs/training_xgboost_balance.yml`. File đó tiếp tục là
candidate config của experiment. `training_selected.yml` là interface ổn định mà
DAG sử dụng; tên file không cần thay đổi nếu sau này có một quy trình selection
mới được phê duyệt.

## 4. Test chống selected config bị drift

Tạo `ml/tests/test_selected_model_config.py`:

```python
from pathlib import Path

import pytest

from fraudguard_ml.config import load_yaml_config
from fraudguard_ml.experiment_config import ExperimentConfig, XGBoostConfig

pytestmark = pytest.mark.smoke

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SELECTED_CONFIG_PATH = REPOSITORY_ROOT / "configs" / "training_selected.yml"
WINNER_CONFIG_PATH = (
    REPOSITORY_ROOT / "configs" / "training_xgboost_balance.yml"
)


def load_experiment(path: Path) -> ExperimentConfig:
    return load_yaml_config(path, ExperimentConfig)


def test_selected_config_is_candidate_d() -> None:
    selected = load_experiment(SELECTED_CONFIG_PATH)
    winner = load_experiment(WINNER_CONFIG_PATH)

    assert selected.experiment_name == "fraudguard_selected_xgboost_balance"
    assert isinstance(selected.model, XGBoostConfig)
    assert selected.model.kind == "xgboost"

    # Chỉ experiment_name được đổi. Dataset, split, model, threshold policy và
    # runtime phải khớp candidate D đã được Phase 6 phê duyệt.
    assert selected.dataset == winner.dataset
    assert selected.split == winner.split
    assert selected.snapshot == winner.snapshot
    assert selected.model == winner.model
    assert selected.evaluation == winner.evaluation
    assert selected.runtime == winner.runtime


def test_selected_config_keeps_frozen_selection_contract() -> None:
    selected = load_experiment(SELECTED_CONFIG_PATH)

    assert selected.dataset.prediction_point == "post_ledger_update"
    assert selected.split.strategy == "temporal"
    assert selected.evaluation.threshold_strategy == (
        "max_recall_at_min_precision"
    )
    assert selected.evaluation.min_precision == 0.10
    assert selected.runtime.random_seed == 42
    assert selected.dataset.feature_columns == (
        "transaction_type",
        "amount",
        "origin_balance_before",
        "origin_balance_after",
        "destination_balance_before",
        "destination_balance_after",
        "origin_balance_delta",
        "destination_balance_delta",
        "origin_amount_residual",
        "destination_amount_residual",
        "origin_balance_before_is_zero",
        "destination_balance_before_is_zero",
        "destination_balance_after_is_zero",
    )
```

Chạy test:

```bash
uv run pytest --no-cov ml/tests/test_selected_model_config.py
```

Test này cố ý so selected config với candidate D. Nếu muốn thay model sau một
experiment mới, phải cập nhật selection evidence, candidate config và test trong
cùng change; không được âm thầm sửa `training_selected.yml`.

## 5. Tạo script kiểm chứng output của DAG

`training.py` đã lưu `model_kind`, `resolved_hyperparameters`, `best_iteration`,
`scale_pos_weight`, threshold và lineage hash. Phase 7 chỉ cần thêm một gate đọc
lại các artifact và fail run nếu chúng không liên kết đúng.

Tạo `scripts/verify_selected_training_run.py`:

```python
"""Verify that one Airflow training run produced linked selected-model artifacts."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import joblib

from fraudguard_ml.artifacts import sha256_file
from fraudguard_ml.config import load_yaml_config
from fraudguard_ml.dataset_manifest import load_manifest
from fraudguard_ml.experiment_config import ExperimentConfig, XGBoostConfig
from fraudguard_ml.io_utils import write_json_immutable


class VerificationError(RuntimeError):
    """Training artifacts do not satisfy the selected-model contract."""


def load_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VerificationError(f"cannot read JSON artifact: {path}") from exc
    if not isinstance(payload, dict):
        raise VerificationError(f"JSON root must be an object: {path}")
    return payload


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def require_mapping(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise VerificationError(f"{key!r} must be an object")
    return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--dataset-manifest", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--validation-metrics", type=Path, required=True)
    parser.add_argument("--evaluation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_yaml_config(args.config, ExperimentConfig)
    manifest = load_manifest(args.dataset_manifest)
    validation_metrics = load_json_object(args.validation_metrics)
    evaluation = load_json_object(args.evaluation)

    # joblib/pickle chỉ được load từ artifact do chính pipeline tạo ra.
    raw_bundle = joblib.load(args.model)
    require(isinstance(raw_bundle, dict), "model bundle must be an object")
    bundle: dict[str, Any] = raw_bundle

    model_config = config.model
    manifest_sha256 = sha256_file(args.dataset_manifest)
    model_sha256 = sha256_file(args.model)

    require(
        manifest.experiment_name == config.experiment_name,
        "manifest/config experiment_name mismatch",
    )
    require(
        manifest.feature_list == config.dataset.feature_columns,
        "manifest/config feature list mismatch",
    )
    require(
        bundle.get("dataset_manifest_sha256") == manifest_sha256,
        "bundle/manifest hash mismatch",
    )
    require(
        bundle.get("population_fingerprint") == manifest.population_fingerprint,
        "bundle/manifest population mismatch",
    )
    require(
        tuple(bundle.get("feature_list", ())) == config.dataset.feature_columns,
        "bundle/config feature order mismatch",
    )
    require(
        bundle.get("config") == config.model_dump(mode="json"),
        "bundle does not contain the resolved selected config",
    )

    metadata = require_mapping(validation_metrics, "model_metadata")
    bundle_metadata = bundle.get("model_metadata")
    require(bundle_metadata == metadata, "bundle/metrics model metadata mismatch")
    require(
        metadata.get("model_kind") == model_config.kind,
        "metadata/config model_kind mismatch",
    )

    resolved = require_mapping(metadata, "resolved_hyperparameters")
    for key, expected in model_config.model_dump(mode="json").items():
        require(
            resolved.get(key) == expected,
            f"resolved hyperparameter mismatch: {key}",
        )
    require(
        resolved.get("random_state") == config.runtime.random_seed,
        "resolved random_state mismatch",
    )
    best_iteration = metadata.get("best_iteration")
    scale_pos_weight = metadata.get("scale_pos_weight")
    if isinstance(model_config, XGBoostConfig):
        require(
            resolved.get("n_jobs") == config.runtime.max_cpu_threads,
            "resolved n_jobs mismatch",
        )
        require(
            isinstance(best_iteration, int)
            and not isinstance(best_iteration, bool),
            "best_iteration must be an integer",
        )
        require(
            0 <= best_iteration < model_config.n_estimators,
            "best_iteration is outside configured boosting rounds",
        )

        train_rows = validation_metrics.get("train_rows")
        train_fraud = validation_metrics.get("train_fraud")
        require(
            isinstance(train_rows, int) and isinstance(train_fraud, int),
            "train counts must be integers",
        )
        require(0 < train_fraud < train_rows, "invalid train fraud count")
        require(
            isinstance(scale_pos_weight, (int, float))
            and not isinstance(scale_pos_weight, bool),
            "scale_pos_weight must be numeric",
        )
        expected_weight = (train_rows - train_fraud) / train_fraud
        require(
            math.isclose(
                float(scale_pos_weight),
                expected_weight,
                rel_tol=1e-12,
                abs_tol=0.0,
            ),
            "scale_pos_weight was not derived from train only",
        )
    else:
        require(best_iteration is None, "Logistic best_iteration must be null")
        require(
            scale_pos_weight is None,
            "Logistic scale_pos_weight must be null",
        )

    threshold = validation_metrics.get("threshold")
    require(
        isinstance(threshold, (int, float)) and not isinstance(threshold, bool),
        "validation threshold must be numeric",
    )
    require(bundle.get("threshold") == threshold, "bundle/metrics threshold mismatch")

    test_metrics = require_mapping(evaluation, "metrics")
    require(evaluation.get("split") == "test", "evaluation split must be test")
    require(
        evaluation.get("experiment_name") == config.experiment_name,
        "evaluation/config experiment mismatch",
    )
    require(
        evaluation.get("model_sha256") == model_sha256,
        "evaluation/model hash mismatch",
    )
    require(
        evaluation.get("dataset_manifest_sha256") == manifest_sha256,
        "evaluation/manifest hash mismatch",
    )
    require(
        evaluation.get("population_fingerprint")
        == manifest.population_fingerprint,
        "evaluation/manifest population mismatch",
    )
    require(
        test_metrics.get("threshold") == threshold,
        "test evaluation did not use the frozen bundle threshold",
    )

    write_json_immutable(
        args.output,
        {
            "verification_schema_version": 1,
            "status": "verified",
            "experiment_name": config.experiment_name,
            "run_id": manifest.run_id,
            "model_kind": metadata["model_kind"],
            "model_sha256": model_sha256,
            "dataset_manifest_sha256": manifest_sha256,
            "population_fingerprint": manifest.population_fingerprint,
            "best_iteration": best_iteration,
            "scale_pos_weight": scale_pos_weight,
            "threshold": float(threshold),
            "resolved_hyperparameters": resolved,
        },
    )
    print(args.output)


if __name__ == "__main__":
    main()
```

Gate này không so test metric với một target mong muốn và không dùng test để ra
quyết định model. Nó chỉ xác nhận evaluate đã dùng đúng model bundle, threshold,
manifest và population.

## 6. Cập nhật training DAG

Thay nội dung `airflow/dags/fraudguard_training.py` bằng:

```python
"""Train and evaluate the approved FraudGuard model configuration."""

from __future__ import annotations

import os
from datetime import timedelta

import pendulum
from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import Param, dag

PROJECT = "/opt/airflow/project"
ARTIFACT_ROOT = "/opt/airflow/artifacts/training/{{ ts_nodash }}"
CONTRACT = f"{PROJECT}/configs/training_data_contract.yml"
DBT_TARGET = f"{ARTIFACT_ROOT}/dbt_target"
CONTRACT_ARTIFACT = f"{ARTIFACT_ROOT}/artifact.json"
EXPERIMENT_DIR = f"{ARTIFACT_ROOT}/experiment"
MANIFEST = f"{EXPERIMENT_DIR}/dataset_manifest.json"
CACHE = f"{ARTIFACT_ROOT}/cache"
MODEL_DIR = f"{EXPERIMENT_DIR}/model"

# Không cho phép người trigger truyền arbitrary path vào BashOperator.
ALLOWED_CONFIG_FILES = (
    "training_selected.yml",
    "training_baseline.yml",
)
DEFAULT_CONFIG_FILE = os.getenv(
    "FRAUDGUARD_TRAINING_CONFIG_FILE",
    "training_selected.yml",
)
if DEFAULT_CONFIG_FILE not in ALLOWED_CONFIG_FILES:
    raise ValueError(
        "FRAUDGUARD_TRAINING_CONFIG_FILE must be one of "
        f"{ALLOWED_CONFIG_FILES}, got {DEFAULT_CONFIG_FILE!r}"
    )

# params được render lúc task chạy; environment variable chỉ đặt default lúc
# DAG được parse. Enum JSON Schema chặn path traversal và shell injection.
CONFIG = f"{PROJECT}/configs/{{{{ params.config_file }}}}"


@dag(
    dag_id="fraudguard_training_selected",
    description="Immutable snapshot -> diagnostics -> selected model -> test",
    schedule=None,
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(hours=3),
    default_args={"owner": "fraud-ml", "retries": 0},
    params={
        "config_file": Param(
            DEFAULT_CONFIG_FILE,
            type="string",
            enum=list(ALLOWED_CONFIG_FILES),
            title="Approved training configuration",
            description=(
                "Use training_selected.yml for the approved XGBoost winner. "
                "training_baseline.yml is retained only as an explicit rollback."
            ),
        )
    },
    tags=["fraudguard", "ml", "training", "selected-model"],
)
def fraudguard_training_selected():
    prepare_snapshot = BashOperator(
        task_id="prepare_snapshot",
        pool="dbt_clickhouse",
        bash_command=f"""
            set -euo pipefail
            mkdir -p {ARTIFACT_ROOT} {EXPERIMENT_DIR}
            test -f {CONFIG}

            dbt build \\
              --project-dir {PROJECT}/dbt \\
              --profiles-dir {PROJECT}/dbt \\
              --target dev \\
              --target-path {DBT_TARGET} \\
              --select +tag:training \\
              --fail-fast

            python -m fraudguard_ml validate-training-data \\
              --config {CONTRACT} \\
              --dbt-manifest {DBT_TARGET}/manifest.json \\
              --repository-root {PROJECT} \\
              --output {CONTRACT_ARTIFACT}

            python -m fraudguard_ml snapshot-training-dataset \\
              --config {CONFIG} \\
              --contract-artifact {CONTRACT_ARTIFACT} \\
              --dbt-manifest {DBT_TARGET}/manifest.json \\
              --repository-root {PROJECT} \\
              --run-id '{{{{ ts_nodash }}}}' \\
              --output {EXPERIMENT_DIR}
        """,
        execution_timeout=timedelta(minutes=60),
    )

    diagnostics = BashOperator(
        task_id="split_diagnostics",
        bash_command=f"""
            set -euo pipefail
            python -m fraudguard_ml diagnose-training-splits \\
              --config {CONFIG} \\
              --dataset-manifest {MANIFEST} \\
              --cache-dir {CACHE} \\
              --output {EXPERIMENT_DIR}/split_diagnostics.json
        """,
        execution_timeout=timedelta(minutes=30),
    )

    train = BashOperator(
        task_id="train",
        bash_command=f"""
            set -euo pipefail
            python -m fraudguard_ml train \\
              --config {CONFIG} \\
              --dataset-manifest {MANIFEST} \\
              --cache-dir {CACHE} \\
              --output {MODEL_DIR}
        """,
        execution_timeout=timedelta(hours=1),
    )

    evaluate = BashOperator(
        task_id="evaluate",
        bash_command=f"""
            set -euo pipefail
            python -m fraudguard_ml evaluate \\
              --config {CONFIG} \\
              --dataset-manifest {MANIFEST} \\
              --cache-dir {CACHE} \\
              --model {MODEL_DIR}/model_bundle.joblib \\
              --output {EXPERIMENT_DIR}/evaluation.json
        """,
        execution_timeout=timedelta(minutes=30),
    )

    verify_artifacts = BashOperator(
        task_id="verify_artifacts",
        bash_command=f"""
            set -euo pipefail
            python {PROJECT}/scripts/verify_selected_training_run.py \\
              --config {CONFIG} \\
              --dataset-manifest {MANIFEST} \\
              --model {MODEL_DIR}/model_bundle.joblib \\
              --validation-metrics {MODEL_DIR}/validation_metrics.json \\
              --evaluation {EXPERIMENT_DIR}/evaluation.json \\
              --output {EXPERIMENT_DIR}/integration_verification.json
        """,
        execution_timeout=timedelta(minutes=10),
    )

    prepare_snapshot >> diagnostics >> train >> evaluate >> verify_artifacts


fraudguard_training_selected()
```

### Vì sao dùng `config_file` enum thay vì `config_path` tự do?

`bash_command` là templated field. Nếu cho phép một string path tùy ý, người
trigger có thể đưa ký tự shell hoặc path ngoài `configs/` vào command. `Param`
với `enum` chỉ cho phép hai tên file đã phê duyệt:

- `training_selected.yml`: mặc định và là winner;
- `training_baseline.yml`: rollback có chủ đích, không dùng để mở lại experiment.

Airflow Params được validate bằng JSON Schema và giá trị runtime được đọc trong
template qua `params`. Import `Param` từ `airflow.sdk` để dùng public interface
của Airflow 3.

## 7. Cho phép environment đặt default config

Trong `docker-compose.yml`, thêm biến sau vào
`x-airflow-common.environment`:

```yaml
    FRAUDGUARD_TRAINING_CONFIG_FILE: ${FRAUDGUARD_TRAINING_CONFIG_FILE:-training_selected.yml}
```

Vị trí đề xuất:

```yaml
    PYTHONPATH: /opt/airflow/project/ml/src
    FRAUDGUARD_TRAINING_CONFIG_FILE: ${FRAUDGUARD_TRAINING_CONFIG_FILE:-training_selected.yml}
    CLICKHOUSE_ML_HOST: clickhouse
```

Thêm vào `.env.example` dưới nhóm Airflow:

```dotenv
# Approved values: training_selected.yml, training_baseline.yml
FRAUDGUARD_TRAINING_CONFIG_FILE=training_selected.yml
```

Environment variable chỉ đặt default khi DAG được parse. Khi trigger thủ công,
Airflow UI/CLI có thể override qua Param nhưng vẫn phải thuộc allowlist.

## 8. Kiểm tra trước khi chạy end-to-end

### 8.1. Kiểm tra config và code local

```bash
uv run python - <<'PY'
from pathlib import Path

from fraudguard_ml.config import load_yaml_config
from fraudguard_ml.experiment_config import ExperimentConfig, XGBoostConfig

path = Path("configs/training_selected.yml")
config = load_yaml_config(path, ExperimentConfig)

assert config.experiment_name == "fraudguard_selected_xgboost_balance"
assert isinstance(config.model, XGBoostConfig)
assert config.model.kind == "xgboost"
assert config.runtime.random_seed == 42
assert config.evaluation.min_precision == 0.10
assert len(config.dataset.feature_columns) == 13

print(config.model.model_dump(mode="json"))
PY

uv run pytest --no-cov ml/tests/test_selected_model_config.py
uv run ruff check \
  airflow/dags/fraudguard_training.py \
  scripts/verify_selected_training_run.py \
  ml/tests/test_selected_model_config.py
```

### 8.2. Rebuild và kiểm tra DAG import

Config và source repository đã được mount read-only vào Airflow, nhưng image vẫn
nên được rebuild để chắc chắn dependency XGBoost trong container đúng với lock:

```bash
docker compose build airflow-init
docker compose up -d --force-recreate airflow-init
docker compose up -d --force-recreate \
  airflow-apiserver \
  airflow-scheduler \
  airflow-dag-processor \
  airflow-triggerer
```

Kiểm tra import và default config mà không in secrets:

```bash
docker compose exec airflow-scheduler python - <<'PY'
import os
from pathlib import Path

import xgboost

config_file = os.environ["FRAUDGUARD_TRAINING_CONFIG_FILE"]
assert config_file == "training_selected.yml"
assert Path("/opt/airflow/project/configs", config_file).is_file()
print("xgboost", xgboost.__version__)
print("config", config_file)
PY

docker compose exec airflow-scheduler \
  airflow dags list-import-errors

docker compose exec airflow-scheduler \
  airflow dags list | grep fraudguard_training_selected
```

`airflow dags list-import-errors` phải không có lỗi liên quan tới
`fraudguard_training.py`.

## 9. Trigger selected model

Unpause và trigger bằng default:

```bash
docker compose exec airflow-scheduler \
  airflow dags unpause fraudguard_training_selected

docker compose exec airflow-scheduler \
  airflow dags trigger fraudguard_training_selected
```

Hoặc truyền Param tường minh:

```bash
docker compose exec airflow-scheduler \
  airflow dags trigger \
  --conf '{"config_file":"training_selected.yml"}' \
  fraudguard_training_selected
```

Không truyền các experiment config khác. Giá trị ngoài enum phải bị Airflow từ
chối trước khi tạo DagRun:

```bash
docker compose exec airflow-scheduler \
  airflow dags trigger \
  --conf '{"config_file":"../../tmp/untrusted.yml"}' \
  fraudguard_training_selected
```

Lệnh cuối là negative test; DagRun không được tạo thành công.

## 10. Kiểm tra output sau khi DAG thành công

Mỗi run tạo cây artifact:

```text
airflow_ml_artifacts/training/<AIRFLOW_TS_NODASH>/
├── artifact.json
├── dbt_target/
│   ├── manifest.json
│   └── run_results.json
├── cache/
└── experiment/
    ├── data.parquet
    ├── dataset_manifest.json
    ├── split_diagnostics.json
    ├── evaluation.json
    ├── integration_verification.json
    └── model/
        ├── model_bundle.joblib
        └── validation_metrics.json
```

Lấy run gần nhất bằng read-only command, sau đó kiểm tra file:

```bash
RUN_ROOT="$(find airflow_ml_artifacts/training -mindepth 1 -maxdepth 1 \
  -type d -printf '%T@ %p\n' | sort -nr | head -n 1 | cut -d' ' -f2-)"

test -n "${RUN_ROOT}"
test -s "${RUN_ROOT}/artifact.json"
test -s "${RUN_ROOT}/experiment/dataset_manifest.json"
test -s "${RUN_ROOT}/experiment/split_diagnostics.json"
test -s "${RUN_ROOT}/experiment/model/model_bundle.joblib"
test -s "${RUN_ROOT}/experiment/model/validation_metrics.json"
test -s "${RUN_ROOT}/experiment/evaluation.json"
test -s "${RUN_ROOT}/experiment/integration_verification.json"
```

Chỉ in các field không nhạy cảm:

```bash
RUN_ROOT="${RUN_ROOT}" uv run python - <<'PY'
import json
import os
from pathlib import Path

root = Path(os.environ["RUN_ROOT"])
verification = json.loads(
    (root / "experiment" / "integration_verification.json").read_text("utf-8")
)
evaluation = json.loads(
    (root / "experiment" / "evaluation.json").read_text("utf-8")
)

assert verification["status"] == "verified"
assert verification["model_kind"] == "xgboost"
assert verification["resolved_hyperparameters"]["tree_method"] == "hist"
assert evaluation["split"] == "test"

print("run_id:", verification["run_id"])
print("model_kind:", verification["model_kind"])
print("best_iteration:", verification["best_iteration"])
print("threshold:", verification["threshold"])
print("test_metrics:", evaluation["metrics"])
PY
```

Kết quả test của Phase 7 được báo cáo đúng một lần như bằng chứng integration.
Không dùng metric này để quay lại đổi depth, learning rate, feature hoặc threshold
policy. Thay đổi model cần một experiment/version selection mới.

## 11. Chụp bằng chứng Airflow

Mở Airflow UI tại `http://localhost:8084`, chọn
`fraudguard_training_selected` và chụp hai ảnh:

1. **Graph view:** đủ năm task, tất cả ở trạng thái success.
2. **Run details/Grid view:** hiển thị `run_id`, thời gian chạy và Param
   `config_file=training_selected.yml`.

Lưu ảnh theo tên ổn định:

```text
images/airflow/training_selected_graph_success.png
images/airflow/training_selected_run_details.png
```

Không chụp màn hình có connection password, environment dump hoặc secret.

## 12. Rerun và rollback policy

### Rerun

Artifact writer từ chối overwrite. Khi một run fail:

- giữ nguyên artifact lỗi để điều tra;
- sửa nguyên nhân bằng change riêng;
- trigger một DagRun mới để có `ts_nodash` và artifact root mới;
- không xóa output cũ chỉ để rerun cùng định danh.

### Rollback

Rollback local có thể trigger config baseline đã nằm trong allowlist:

```bash
docker compose exec airflow-scheduler \
  airflow dags trigger \
  --conf '{"config_file":"training_baseline.yml"}' \
  fraudguard_training_selected
```

Đây chỉ là khả năng phục hồi kỹ thuật. Nó không thay đổi winner đã ghi trong
Phase 6. Muốn baseline trở lại selected model chính thức phải có một model
selection decision mới và cập nhật `training_selected.yml` qua review.

## 13. Definition of Done

Phase 7 hoàn thành khi:

- [ ] `training_selected.yml` load thành công và khớp candidate D.
- [ ] Test chống selected config drift chạy pass.
- [ ] Airflow mặc định dùng `training_selected.yml`.
- [ ] Param chỉ chấp nhận các config trong allowlist.
- [ ] DAG giữ đủ snapshot, diagnostics, train và evaluate.
- [ ] DAG có thêm gate `verify_artifacts` và gate chạy success.
- [ ] `model_bundle.joblib` ghi `model_kind=xgboost`.
- [ ] Artifact ghi đủ resolved hyperparameters, `best_iteration` và
      `scale_pos_weight` tính từ train.
- [ ] Evaluation dùng đúng threshold trong model bundle.
- [ ] Manifest, model và evaluation liên kết bằng SHA-256/population fingerprint.
- [ ] Có ảnh Graph view và Run details của DagRun thành công.
- [ ] Không có tuning, deployment hoặc test-driven model revision trong Phase 7.

## 14. Tài liệu tham khảo Airflow

- [Airflow Params](https://airflow.apache.org/docs/apache-airflow/stable/core-concepts/params.html)
- [Airflow 3 public interface](https://airflow.apache.org/docs/apache-airflow/stable/public-airflow-interface.html)
- [Airflow CLI reference](https://airflow.apache.org/docs/apache-airflow/stable/cli-and-env-variables-ref.html)
