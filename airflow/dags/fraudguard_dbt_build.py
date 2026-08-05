from __future__ import annotations

from datetime import timedelta

import pendulum
from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import dag


@dag(
    dag_id="fraudguard_dbt_build",
    description="Build and validate FraudGuard ClickHouse transformations",
    schedule="*/5 * * * *",
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(minutes=45),
    default_args={
        "owner": "fraud-platform",
        "retries": 1,
        "retry_delay": timedelta(minutes=2),
        "retry_exponential_backoff": True,
    },
    tags=["fraudguard", "dbt", "clickhouse"],
)
def fraudguard_dbt_build():
    BashOperator(
        task_id="dbt_build",
        bash_command="""
            set -euo pipefail 
            dbt build \\
                --project-dir /opt/airflow/dbt \\
                --profiles-dir /opt/airflow/dbt \\
                --target dev \\
                --fail-fast
        """,
        execution_timeout=timedelta(minutes=30),
        do_xcom_push=False,
    )


fraudguard_dbt_build()
