set -euo pipefail

if [ -f .env ]; then
  set -a
  source .env
  set +a
fi

RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_ROOT="airflow_ml_artifacts/model_experiments/${RUN_ID}"
SHARED_ROOT="${RUN_ROOT}/shared"
DBT_TARGET="$(pwd)/${SHARED_ROOT}/dbt_target"
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

echo "Shared DBT & Contract Artifact: READY"

while IFS='|' read -r CANDIDATE_ID MODEL_KIND FEATURE_SET CONFIG_PATH; do
    CANDIDATE_ROOT="${RUN_ROOT}/candidates/${CANDIDATE_ID}"
    EXPERIMENT_DIR="${CANDIDATE_ROOT}/experiment"
    MODEL_DIR="${CANDIDATE_ROOT}/model"

    mkdir -p "${EXPERIMENT_DIR}" "${MODEL_DIR}"

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

    printf 'Candidate %s finished successfully!\n' "${CANDIDATE_ID}"
done <<'EOF'
A|logistic_regression|baseline|configs/training_baseline.yml
B|xgboost|baseline|configs/training_xgboost_baseline.yml
C|logistic_regression|balance|configs/training_challenger_balance.yml
D|xgboost|balance|configs/training_xgboost_balance.yml
EOF