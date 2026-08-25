# Hướng dẫn chạy Ma trận Thực nghiệm 2 × 2 (Phase 4 CLI Runbook)

Tài liệu này tổng hợp toàn bộ các lệnh CLI để chạy tự động và xác minh ma trận 4 mô hình:

| ID | Model Kind | Feature Set | Config Path |
| :--- | :--- | :--- | :--- |
| **A** | `logistic_regression` | `baseline` (4 features) | `configs/training_baseline.yml` |
| **B** | `xgboost` | `baseline` (4 features) | `configs/training_xgboost_baseline.yml` |
| **C** | `logistic_regression` | `balance` (13 features) | `configs/training_challenger_balance.yml` |
| **D** | `xgboost` | `balance` (13 features) | `configs/training_xgboost_balance.yml` |

---

## 1. Chuẩn bị môi trường & Biến môi trường

Chuyển về thư mục gốc của project và load biến môi trường:

```bash
cd /home/phongthanh/ML_Fraud_Banking

set -a
source .env
set +a
```

---

## 2. Kiểm tra trước tính hợp lệ của 4 file Config (Pre-check Invariants)

Chạy script Python kiểm tra tính toàn vẹn và đồng nhất của 4 file YAML:

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
configs = [load_yaml_config(p, ExperimentConfig) for p in paths]

assert {c.dataset.relation for c in configs} == {"fraudguard_ml.ml_training_transactions"}
assert {c.dataset.target_column for c in configs} == {"is_fraud"}
assert {c.dataset.prediction_point for c in configs} == {"post_ledger_update"}
assert {c.snapshot.label_policy for c in configs} == {"static_final_labels"}
assert {c.runtime.random_seed for c in configs} == {42}
assert {
    (c.split.train_end, c.split.validation_end, c.split.test_end)
    for c in configs
} == {("2026-01-01T02:00:00Z", "2026-01-01T04:00:00Z", "2026-01-01T06:00:00Z")}
assert configs[0].dataset.feature_columns == configs[1].dataset.feature_columns
assert configs[2].dataset.feature_columns == configs[3].dataset.feature_columns
assert configs[0].dataset.feature_columns != configs[2].dataset.feature_columns

print("✅ Candidate config invariants: PASSED")
PY
```

---

## 3. Khởi tạo Run ID, Build DBT & Validate Data Contract

Chạy dbt build 1 lần duy nhất cho toàn bộ 4 candidate:

```bash
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_ROOT="airflow_ml_artifacts/model_experiments/${RUN_ID}"
SHARED_ROOT="${RUN_ROOT}/shared"
DBT_TARGET="${SHARED_ROOT}/dbt_target"
CONTRACT_ARTIFACT="${SHARED_ROOT}/artifact.json"
CACHE_ROOT="${RUN_ROOT}/cache"

mkdir -p "${DBT_TARGET}" "${CACHE_ROOT}"

# Build lineage dbt
uv run dbt build \
  --project-dir dbt \
  --profiles-dir dbt \
  --target dev \
  --target-path "${DBT_TARGET}" \
  --select +tag:training \
  --fail-fast

# Validate data contract
uv run python -m fraudguard_ml validate-training-data \
  --config configs/training_data_contract.yml \
  --dbt-manifest "${DBT_TARGET}/manifest.json" \
  --repository-root . \
  --output "${CONTRACT_ARTIFACT}"

echo "✅ Shared DBT & Contract Artifact: READY"
```

---

## 4. Chạy tuần tự 4 Candidate (Snapshot + Train)

Vòng lặp tự động tạo snapshot và huấn luyện từng candidate:

```bash
set -euo pipefail

while IFS='|' read -r CANDIDATE_ID MODEL_KIND FEATURE_SET CONFIG_PATH; do
  CANDIDATE_ROOT="${RUN_ROOT}/candidates/${CANDIDATE_ID}"
  EXPERIMENT_DIR="${CANDIDATE_ROOT}/experiment"
  MODEL_DIR="${CANDIDATE_ROOT}/model"

  mkdir -p "${EXPERIMENT_DIR}" "${MODEL_DIR}"

  printf '\n=======================================================\n'
  printf '🚀 Running Candidate %s | Model: %s | Feature: %s\n' \
    "${CANDIDATE_ID}" "${MODEL_KIND}" "${FEATURE_SET}"
  printf '=======================================================\n'

  # 1. Snapshot training dataset
  uv run python -m fraudguard_ml snapshot-training-dataset \
    --config "${CONFIG_PATH}" \
    --contract-artifact "${CONTRACT_ARTIFACT}" \
    --dbt-manifest "${DBT_TARGET}/manifest.json" \
    --repository-root . \
    --run-id "${RUN_ID}" \
    --output "${EXPERIMENT_DIR}"

  # 2. Train and select threshold
  uv run python -m fraudguard_ml train \
    --config "${CONFIG_PATH}" \
    --dataset-manifest "${EXPERIMENT_DIR}/dataset_manifest.json" \
    --cache-dir "${CACHE_ROOT}" \
    --output "${MODEL_DIR}"

  test -s "${EXPERIMENT_DIR}/dataset_manifest.json"
  test -s "${MODEL_DIR}/model_bundle.joblib"
  test -s "${MODEL_DIR}/validation_metrics.json"

  printf '✅ Candidate %s finished successfully!\n' "${CANDIDATE_ID}"
done <<'EOF'
A|logistic_regression|baseline|configs/training_baseline.yml
B|xgboost|baseline|configs/training_xgboost_baseline.yml
C|logistic_regression|balance|configs/training_challenger_balance.yml
D|xgboost|balance|configs/training_xgboost_balance.yml
EOF
```

---

## 5. Tổng hợp Kết quả Bảng So sánh Ma trận (Validation Comparison)

Chạy script tổng hợp để tạo báo cáo so sánh:

```bash
uv run python scripts/build_validation_comparison.py \
  --run-root "${RUN_ROOT}"
```

Xem bảng kết quả tổng hợp:

```bash
cat "${RUN_ROOT}/comparison/validation_comparison.csv"
```

