from __future__ import annotations

from datetime import timedelta

import pendulum
from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import dag

PROJECT = "/opt/airflow/project"
ARTIFACT_ROOT = "/opt/airflow/artifacts/training/{{ ts_nodash }}"
CONFIG = f"{PROJECT}/configs/training_baseline.yml"
CONTRACT = f"{PROJECT}/configs/training_data_contract.yml"
DBT_TARGET = f"{ARTIFACT_ROOT}/dbt_target"
CONTRACT_ARTIFACT = f"{ARTIFACT_ROOT}/artifact.json"
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
