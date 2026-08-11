# Phase 5 — CLI, Airflow, Docker/MinIO và tests

Phase cuối nối các module thành workflow chạy được local và trong Airflow.

## 1. Sửa command validation hiện tại

CLI hiện hard-code `poetry.lock` và `target/manifest.json`, nhưng repo dùng `uv.lock` và dbt output nằm dưới `dbt/target` (hoặc target path của Airflow run). Sửa parser:

```python
validate = subparsers.add_parser("validate-training-data")
validate.add_argument("--config", type=Path, required=True)
validate.add_argument("--dbt-manifest", type=Path, required=True)
validate.add_argument("--repository-root", type=Path, default=Path.cwd())
validate.add_argument(
    "--output",
    type=Path,
    default=Path("artifacts/ml/training_data_contract.json"),
)
```

Sửa function:

```python
def run_validate_training_data(
    config_path: Path,
    dbt_manifest_path: Path,
    repository_root: Path,
    output_path: Path,
) -> int:
    config = load_yaml_config(config_path, TrainingDataContractConfig)
    client = create_clickhouse_client(ClickHouseSettings.from_env())
    try:
        report = validate_training_data_contract(client, config)
    finally:
        client.close()
    artifact = build_artifact(
        report=asdict(report),
        repository_root=repository_root,
        contract_path=config_path,
        lock_path=repository_root / "uv.lock",
        dbt_manifest_path=dbt_manifest_path,
        relevant_paths=[
            repository_root / "ml" / "src",
            config_path,
        ],
    )
    write_json_immutable(output_path, artifact)
    print(output_path)
    return 0
```

Nếu config path đã absolute trong repository, `collect_git_provenance` hiện dùng được. Airflow phải mount cả project root gồm `.git` read-only; nếu production image không có `.git`, thay git shell call bằng build-time `FRAUDGUARD_GIT_SHA` và ghi SHA vào image metadata.

## 2. CLI subcommands

Thêm parser trong `build_parser()`:

```python
snapshot = subparsers.add_parser("snapshot-training-dataset")
snapshot.add_argument("--config", type=Path, required=True)
snapshot.add_argument("--contract-artifact", type=Path, required=True)
snapshot.add_argument("--dbt-manifest", type=Path, required=True)
snapshot.add_argument("--repository-root", type=Path, default=Path.cwd())
snapshot.add_argument("--run-id", required=True)
snapshot.add_argument("--output", type=Path, required=True)

diagnostics = subparsers.add_parser("diagnose-training-splits")
diagnostics.add_argument("--config", type=Path, required=True)
diagnostics.add_argument("--dataset-manifest", type=Path, required=True)
diagnostics.add_argument("--cache-dir", type=Path, required=True)
diagnostics.add_argument("--output", type=Path, required=True)

train = subparsers.add_parser("train")
train.add_argument("--config", type=Path, required=True)
train.add_argument("--dataset-manifest", type=Path, required=True)
train.add_argument("--cache-dir", type=Path, required=True)
train.add_argument("--output", type=Path, required=True)

evaluate = subparsers.add_parser("evaluate")
evaluate.add_argument("--config", type=Path, required=True)
evaluate.add_argument("--dataset-manifest", type=Path, required=True)
evaluate.add_argument("--cache-dir", type=Path, required=True)
evaluate.add_argument("--model", type=Path, required=True)
evaluate.add_argument("--output", type=Path, required=True)
```

Thêm helper/context:

```python
def load_snapshot_context(
    config_path: Path,
    manifest_path: Path,
    cache_dir: Path,
) -> tuple[ExperimentConfig, DatasetManifest, DatasetSplits]:
    config = load_yaml_config(config_path, ExperimentConfig)
    manifest = load_manifest(manifest_path)
    s3_client = create_s3_client(ObjectStorageSettings.from_env())
    snapshot_path = materialize_snapshot(
        s3_client=s3_client,
        manifest=manifest,
        cache_dir=cache_dir,
    )
    splits = load_dataset_splits(
        snapshot_path=snapshot_path,
        manifest=manifest,
        config=config,
    )
    return config, manifest, splits
```

Thêm run functions:

```python
def run_snapshot_training_dataset(args: argparse.Namespace) -> int:
    config = load_yaml_config(args.config, ExperimentConfig)
    clickhouse = create_clickhouse_client(ClickHouseSettings.from_env())
    s3_client = create_s3_client(ObjectStorageSettings.from_env())
    try:
        manifest = create_snapshot_and_manifest(
            client=clickhouse,
            s3_client=s3_client,
            config=config,
            config_path=args.config,
            contract_artifact_path=args.contract_artifact,
            dbt_manifest_path=args.dbt_manifest,
            repository_root=args.repository_root,
            run_id=args.run_id,
            output_dir=args.output,
        )
    finally:
        clickhouse.close()
    print(json.dumps(manifest.model_dump(mode="json"), sort_keys=True))
    return 0


def run_split_diagnostics(args: argparse.Namespace) -> int:
    config, _, splits = load_snapshot_context(
        args.config, args.dataset_manifest, args.cache_dir
    )
    categorical, numeric = feature_groups(config)
    report = build_split_diagnostics(
        splits,
        numeric_columns=tuple(numeric),
        categorical_columns=tuple(categorical),
    )
    assert_diagnostic_invariants(report)
    write_diagnostics(args.output, report)
    print(args.output)
    return 0


def run_train(args: argparse.Namespace) -> int:
    config, manifest, splits = load_snapshot_context(
        args.config, args.dataset_manifest, args.cache_dir
    )
    result = train_and_select_threshold(
        splits=splits,
        config=config,
        manifest=manifest,
        manifest_path=args.dataset_manifest,
        output_dir=args.output,
    )
    print(json.dumps(result, sort_keys=True))
    return 0


def run_evaluate(args: argparse.Namespace) -> int:
    config, manifest, splits = load_snapshot_context(
        args.config, args.dataset_manifest, args.cache_dir
    )
    result = evaluate_test_split(
        test=splits.test,
        config=config,
        manifest=manifest,
        manifest_path=args.dataset_manifest,
        model_path=args.model,
        output_path=args.output,
    )
    print(json.dumps(result, sort_keys=True))
    return 0
```

Trong `main()`, dispatch các command trên và catch thêm `ManifestError`, `SnapshotError`, `TrainingError`. Không in SQL, credentials hoặc raw row khi lỗi.

## 3. MinIO bucket

Sửa `minIO/init_bucket.sh`:

```sh
TRAINING_SNAPSHOT_PATH="s3a://fraud-training-snapshots"
```

Thêm `"$TRAINING_SNAPSHOT_PATH"` vào vòng `for s3a_path in ...`. User `fraudguard` hiện được attach policy `readwrite`, nên có thể upload/download bucket này. Production nên tách writer role và reader role, nhưng chưa cần cho local P0.

## 4. Airflow image và Compose

Thêm vào `docker/airflow/requirements.txt`:

```text
boto3>=1.40,<2
joblib>=1.5,<2
pandas>=3.0,<4
pyarrow>=21,<22
scikit-learn>=1.7,<2
pydantic>=2.12,<3
pyyaml>=6,<7
```

Trong `x-airflow-common.environment`:

```yaml
PYTHONPATH: /opt/airflow/project/ml/src
CLICKHOUSE_ML_HOST: clickhouse
CLICKHOUSE_ML_PORT: "8123"
CLICKHOUSE_ML_DATABASE: fraudguard
CLICKHOUSE_ML_USER: fraudguard_ml_reader
CLICKHOUSE_ML_PASSWORD: ${CLICKHOUSE_ML_PASSWORD:?CLICKHOUSE_ML_PASSWORD must be set}
CLICKHOUSE_ML_SECURE: "false"
MINIO_ENDPOINT: http://minio:9000
MINIO_ACCESS_KEY: ${MINIO_AIRFLOW_USER:-fraudguard}
MINIO_SECRET_KEY: ${MINIO_AIRFLOW_PASSWORD:-fraudguard-secret}
```

Trong `x-airflow-common.volumes`, dọn hai mount bị lặp rồi thêm:

```yaml
- ./:/opt/airflow/project:ro
- airflow_ml_artifacts:/opt/airflow/artifacts
```

Thêm volume cuối file:

```yaml
airflow_ml_artifacts:
```

Không ghi artifact vào project mount read-only. Mọi task dùng `/opt/airflow/artifacts/<run-key>`.

## 5. Airflow concurrency

Tạo Airflow pool một lần:

```bash
docker compose exec airflow-scheduler airflow pools set dbt_clickhouse 1 \
  "Serialize ClickHouse dbt table rebuilds and training snapshot preparation"
```

Trong `fraudguard_dbt_build.py`, thêm `pool="dbt_clickhouse"` vào BashOperator. Training DAG cũng dùng pool này cho task kết hợp dbt + validate + snapshot. Việc kết hợp ba command giữ cùng pool slot, tránh scheduled dbt rebuild xen giữa contract và snapshot.

## 6. Training DAG

Tạo `airflow/dags/fraudguard_training.py`:

```python
from __future__ import annotations

from datetime import timedelta

import pendulum
from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import dag


PROJECT = "/opt/airflow/project"
ARTIFACT_ROOT = "/opt/airflow/artifacts/training/{{ ts_nodash }}"
CONFIG = f"{PROJECT}/configs/training_baseline.yaml"
CONTRACT = f"{PROJECT}/configs/training_data_contract.yml"
DBT_TARGET = f"{ARTIFACT_ROOT}/dbt_target"
CONTRACT_ARTIFACT = f"{ARTIFACT_ROOT}/training_data_contract.json"
EXPERIMENT_DIR = f"{ARTIFACT_ROOT}/experiment"
MANIFEST = f"{EXPERIMENT_DIR}/dataset_manifest.json"
CACHE = f"{ARTIFACT_ROOT}/cache"
MODEL_DIR = f"{EXPERIMENT_DIR}/model"


@dag(
    dag_id="fraudguard_training_baseline",
    description="Immutable mart snapshot -> temporal train/validation/test",
    schedule=None,
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(hours=3),
    default_args={"owner": "fraud-ml", "retries": 0},
    tags=["fraudguard", "ml", "training"],
)
def fraudguard_training_baseline():
    prepare_snapshot = BashOperator(
        task_id="prepare_snapshot",
        pool="dbt_clickhouse",
        bash_command=f"""
            set -euo pipefail
            mkdir -p {ARTIFACT_ROOT} {EXPERIMENT_DIR}
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

    prepare_snapshot >> diagnostics >> train >> evaluate


fraudguard_training_baseline()
```

Điểm cần kiểm tra khi copy: Jinja trong Python f-string phải dùng bốn dấu `{`/`}` như `{{{{ ts_nodash }}}}`. Chạy `airflow dags list-import-errors` sau khi thêm DAG.

## 7. Test matrix

### Service-free

```bash
uv run ruff check ml/src/fraudguard_ml ml/tests airflow/dags
uv run ruff format --check ml/src/fraudguard_ml ml/tests airflow/dags
uv run mypy
uv run pytest -m "not integration"
```

### dbt

```bash
./scripts/dbt.sh parse
./scripts/dbt.sh build --select +tag:training
```

### Integration local stack

```bash
docker compose config --quiet
docker compose build airflow-init
docker compose up -d clickhouse minio minio-init
uv run pytest -m integration ml/tests/test_snapshot_integration.py
```

Integration test bắt buộc chứng minh:

1. Snapshot A được tạo.
2. dbt mart refresh/rebuild lại.
3. Loader của run A vẫn trả cùng snapshot SHA/count/split.
4. Retry cùng run ID + cùng content được reuse.
5. Retry cùng run ID + content khác bị từ chối.

### Airflow

```bash
docker compose up -d airflow-init airflow-apiserver airflow-scheduler airflow-dag-processor
docker compose exec airflow-scheduler airflow dags list-import-errors
docker compose exec airflow-scheduler airflow dags test \
  fraudguard_training_baseline 2026-02-01T00:00:00+00:00
```

## 8. Rollout checklist

- [ ] Phase 1 config/manifest tests pass.
- [ ] Phase 2 snapshot hash và immutable upload pass.
- [ ] Phase 3 split diagnostics pass trên PaySim.
- [ ] Phase 4 baseline train/validation/test artifacts sinh đủ.
- [ ] Scheduled dbt DAG được gắn `dbt_clickhouse` pool.
- [ ] Training DAG manual chạy end-to-end.
- [ ] Baseline/challenger comparison kiểm population fingerprint + boundaries.
- [ ] Artifact retention policy được ghi trước khi xóa local cache.

Sau P0 mới thêm MLflow. Khi thêm, log `dataset_manifest.json`, `split_diagnostics.json`, validation/test metrics, model bundle, snapshot URI/SHA và population fingerprint vào cùng run.
