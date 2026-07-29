from __future__ import annotations

import logging
import re
from datetime import timedelta
from typing import Any

import clickhouse_connect
import pendulum
from airflow.providers.amazon.aws.hooks.s3 import S3Hook
from airflow.sdk import dag, get_current_context, task

LOGGER = logging.getLogger(__name__)

MINIO_CONNECTION_ID = "minio_s3"
CLICKHOUSE_CONNECTION_ID = "clickhouse_http"
MAX_BATCHES_PER_RUN = 200

BATCH_MARKER_PATTERN = re.compile(r"^batch_id=(?P<batch_id>[0-9]{20})/_SUCCESS$")

PIPELINES = (
    {
        "pipeline": "transactions",
        "bucket": "fraud-transactions",
        "quality_bucket": "fraud-ingestion-quality",
        "quality_prefix": "pipeline=transactions",
    },
    {
        "pipeline": "labels",
        "bucket": "fraud-transaction-labels",
        "quality_bucket": "fraud-ingestion-quality",
        "quality_prefix": "pipeline=labels",
    },
)

TRANSACTION_SOURCE_STRUCTURE = """
event_id String, source String,
event_time DateTime64(3, 'UTC'), ingested_at DateTime64(3, 'UTC'),
step Int32, type String, amount Float64, nameOrig String,
oldbalanceOrg Float64, newbalanceOrig Float64, nameDest String,
oldbalanceDest Float64, newbalanceDest Float64,
message_schema_id Int64, kafka_topic String,
kafka_partition Int32, kafka_offset Int64,
kafka_timestamp DateTime64(3, 'UTC')
""".strip()

LABEL_SOURCE_STRUCTURE = """
event_id String, source String,
isFraud Int32, isFlaggedFraud Int32,
message_schema_id Int64, kafka_topic String,
kafka_partition Int32, kafka_offset Int64,
kafka_timestamp DateTime64(3, 'UTC')
""".strip()

QUALITY_SOURCE_STRUCTURE = """
pipeline String, batch_id Int64, event_date Nullable(Date), source String,
input_rows Int64, valid_rows Int64, quarantine_rows Int64
""".strip()

# Đếm số dòng hiện có trong một batch.
COUNT_SOURCE_SQL = """
    SELECT count()
    FROM s3(
        {source_url:String},
        {access_key:String},
        {secret_key:String},
        'Parquet',
        {source_structure:String}
    )
"""

QUALITY_SUMMARY_SQL = """
SELECT
    count() AS manifest_rows,
    countIf(
        manifest.pipeline != {pipeline:String}
        OR manifest.batch_id != {batch_id:UInt64}
    ) AS identity_error_rows,
    countIf(
        manifest.input_rows
            != manifest.valid_rows + manifest.quarantine_rows
    ) AS reconciliation_error_rows,
    countIf(
        manifest.input_rows < 0
        OR manifest.valid_rows < 0
        OR manifest.quarantine_rows < 0
    ) AS negative_count_rows,
    count()
        - uniqExact(tuple(manifest.event_date, manifest.source))
        AS duplicate_key_rows,
    sum(manifest.input_rows) AS total_input_rows,
    sum(manifest.valid_rows) AS total_valid_rows,
    sum(manifest.quarantine_rows) AS total_quarantine_rows
FROM s3(
    {quality_source_url:String},
    {access_key:String},
    {secret_key:String},
    'Parquet',
    {quality_source_structure:String}
) AS manifest
SETTINGS use_hive_partitioning = 0
"""

QUALITY_INSERT_SQL = """
INSERT INTO ingestion_batch_quality
(
    pipeline, batch_id, event_date, source,
    input_rows, valid_rows, quarantine_rows, duplicate_rows, loaded_at
)
SELECT
    pipeline,
    toUInt64(batch_id),
    event_date,
    source,
    toUInt64(input_rows),
    toUInt64(valid_rows),
    toUInt64(quarantine_rows),
    toUInt64(duplicate_rows),
    now64(3)
FROM s3(
    {quality_source_url:String},
    {access_key:String},
    {secret_key:String},
    'Parquet',
    {quality_source_structure:String}
)
WHERE
    pipeline = {pipeline:String}
    AND batch_id = {batch_id:UInt64}
SETTINGS use_hive_partitioning = 0
"""

TRANSACTION_INSERT_SQL = """
INSERT INTO transactions
(
    event_id, source, event_time, ingested_at, step,
    transaction_type, amount, origin_account,
    origin_balance_before, origin_balance_after,
    destination_account, destination_balance_before,
    destination_balance_after, schema_id, kafka_topic,
    kafka_partition, kafka_offset, kafka_timestamp,
    minio_batch_id, minio_object, loaded_at
)
SELECT
    event_id,
    source,
    event_time,
    ingested_at,
    toUInt16(step),
    type,
    toDecimal64(toString(amount), 2),
    nameOrig,
    toDecimal64(toString(oldbalanceOrg), 2),
    toDecimal64(toString(newbalanceOrig), 2),
    nameDest,
    toDecimal64(toString(oldbalanceDest), 2),
    toDecimal64(toString(newbalanceDest), 2),
    toUInt32(message_schema_id),
    kafka_topic,
    toUInt16(kafka_partition),
    toUInt64(kafka_offset),
    kafka_timestamp,
    {batch_id:UInt64},
    _path,
    now64(3)
FROM s3(
    {source_url:String},
    {access_key:String},
    {secret_key:String},
    'Parquet',
    {source_structure:String}
)
"""
LABEL_INSERT_SQL = """
INSERT INTO transaction_labels
(
    event_id, source, is_fraud, is_flagged_fraud,
    schema_id, kafka_topic, kafka_partition, kafka_offset,
    kafka_timestamp, minio_batch_id, minio_object, loaded_at
)
SELECT
    event_id,
    source,
    toUInt8(isFraud),
    toUInt8(isFlaggedFraud),
    toUInt32(message_schema_id),
    kafka_topic,
    toUInt16(kafka_partition),
    toUInt64(kafka_offset),
    kafka_timestamp,
    {batch_id:UInt64},
    _path,
    now64(3)
FROM s3(
    {source_url:String},
    {access_key:String},
    {secret_key:String},
    'Parquet',
    {source_structure:String}
)
"""
# source_prefix là thư mục trên MinIO chứa lô dữ liệu này.
RECORD_RESULT_SQL = """
INSERT INTO ingestion_batches
(
    pipeline, batch_id, status, source_prefix,
    airflow_run_id, finished_at, error_message
)
VALUES
(
    {pipeline:String},
    {batch_id:UInt64},
    {status:String},
    {source_prefix:String},
    {airflow_run_id:String},
    now64(3),
    {error_message:String}
)
"""


# Khi triển khai lên server thật, chỉ cần cấu hình lại Airflow Connections.
def get_clickhouse_client():
    connection = get_current_context()["conn"].get(CLICKHOUSE_CONNECTION_ID)
    if not connection.host or not connection.login:
        raise ValueError("ClickHouse connection is incomplete")
    return clickhouse_connect.get_client(
        host=connection.host,
        port=connection.port or 8123,
        username=connection.login,
        password=connection.password or "",
        database=connection.schema or "fraudguard",
        secure=connection.conn_type == "https",
    )


# Hàm này trả về các thông tin runtime cần thiết của MinIO.
def get_minio_runtime() -> tuple[S3Hook, str, str, str]:
    hook = S3Hook(aws_conn_id=MINIO_CONNECTION_ID)
    s3_client = hook.get_conn()
    credentials = hook.get_session().get_credentials()
    if credentials is None:
        raise ValueError("MinIO credentials are missing")
    frozen = credentials.get_frozen_credentials()
    endpoint_url = s3_client.meta.endpoint_url
    if not endpoint_url:
        raise ValueError("MinIO endpoint_url is missing")
    return (
        hook,
        endpoint_url.rstrip("/"),
        frozen.access_key,
        frozen.secret_key,
    )


@dag(
    dag_id="minio_to_clickhouse",
    description="Load completed FraudGuard Parquet batches into ClickHouse",
    schedule="*/1 * * * *",
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "fraud-platform",
        "retries": 3,
        "retry_delay": timedelta(seconds=30),
    },
    tags=["fraudguard", "minio", "clickhouse"],
)
def minio_to_clickhouse():
    @task
    def check_dependencies() -> None:
        client = get_clickhouse_client()
        try:
            result = client.query(
                """
                SELECT count()
                FROM system.tables
                WHERE database = currentDatabase()
                    AND name IN
                        ('transactions', 'transaction_labels',
                         'ingestion_batches', 'ingestion_batch_quality')
            """
            )
            table_count = int(result.result_rows[0][0])
            if table_count != 4:
                raise RuntimeError("Run the DDL before enabling this DAG")
        finally:
            client.close()

    @task
    def discover_batches() -> list[dict[str, Any]]:
        hook, _, _, _ = get_minio_runtime()
        client = get_clickhouse_client()
        try:
            loaded = {
                (str(pipeline), int(batch_id))
                for pipeline, batch_id in client.query(
                    """
                    SELECT pipeline, batch_id
                    FROM ingestion_batches
                    GROUP BY pipeline, batch_id
                    HAVING countIf(status = 'success') > 0
                    """
                ).result_rows
            }
            discovered: list[dict[str, Any]] = []
            for config in PIPELINES:
                keys = (
                    hook.list_keys(
                        bucket_name=config["quality_bucket"],
                        prefix=f"{config['quality_prefix']}/batch_id=",
                    )
                    or []
                )

                for key in keys:
                    relative_key = key.removeprefix(f"{config['quality_prefix']}/")
                    match = BATCH_MARKER_PATTERN.fullmatch(relative_key)
                    if match is None:
                        continue

                    padded_batch_id = match.group("batch_id")
                    batch_id = int(padded_batch_id)
                    identity = (config["pipeline"], batch_id)
                    if identity in loaded:
                        continue

                    discovered.append(
                        {
                            "pipeline": config["pipeline"],
                            "bucket": config["bucket"],
                            "quality_bucket": config["quality_bucket"],
                            "quality_prefix": config["quality_prefix"],
                            "batch_id": batch_id,
                            "padded_batch_id": padded_batch_id,
                        }
                    )

            discovered.sort(key=lambda item: (item["pipeline"], item["batch_id"]))
            selected = discovered[:MAX_BATCHES_PER_RUN]
            LOGGER.info(
                "Discovered %s pending batches; selected %s",
                len(discovered),
                len(selected),
            )
            return selected
        finally:
            client.close()

    @task(max_active_tis_per_dag=4)
    def load_batch(batch: dict[str, Any]) -> dict[str, Any]:
        _, endpoint_url, access_key, secret_key = get_minio_runtime()
        client = get_clickhouse_client()
        context = get_current_context()

        pipeline = str(batch["pipeline"])
        bucket = str(batch["bucket"])
        quality_bucket = str(batch["quality_bucket"])
        quality_prefix = str(batch["quality_prefix"])
        batch_id = int(batch["batch_id"])
        padded_batch_id = str(batch["padded_batch_id"])
        source_prefix = f"{bucket}/batch_id={padded_batch_id}"
        quality_source_prefix = (
            f"{quality_bucket}/{quality_prefix}/batch_id={padded_batch_id}"
        )
        quality_source_url = f"{endpoint_url}/{quality_source_prefix}/*.parquet"

        if pipeline == "transactions":
            source_structure = TRANSACTION_SOURCE_STRUCTURE
            insert_sql = TRANSACTION_INSERT_SQL
            source_glob = "**/*.parquet"
        elif pipeline == "labels":
            source_structure = LABEL_SOURCE_STRUCTURE
            insert_sql = LABEL_INSERT_SQL
            source_glob = "*.parquet"
        else:
            raise ValueError(f"Unsupported pipeline: {pipeline}")
        source_url = f"{endpoint_url}/{source_prefix}/{source_glob}"

        query_parameters = {
            "source_url": source_url,
            "access_key": access_key,
            "secret_key": secret_key,
            "source_structure": source_structure,
            "batch_id": batch_id,
        }
        quality_query_parameters = {
            "quality_source_url": quality_source_url,
            "access_key": access_key,
            "secret_key": secret_key,
            "quality_source_structure": QUALITY_SOURCE_STRUCTURE,
            "pipeline": pipeline,
            "batch_id": batch_id,
        }
        try:
            quality_result = client.query(
                QUALITY_SUMMARY_SQL,
                parameters=quality_query_parameters,
            )
            (
                manifest_rows,  # Tổng số dòng metadata
                identity_error_rows,
                reconciliation_error_rows,
                negative_count_rows,
                duplicate_key_rows,
                input_rows,
                valid_rows,
                quarantine_rows,
            ) = (int(value) for value in quality_result.result_rows[0])
            if manifest_rows == 0 or input_rows == 0:
                raise ValueError(f"Empty quality manifest: {quality_source_prefix}")
            if identity_error_rows:
                raise ValueError(
                    "Quality manifest identity does not match "
                    f"pipeline={pipeline} batch_id={batch_id}"
                )
            if reconciliation_error_rows:
                raise ValueError(
                    "Quality manifest does not reconcile: "
                    f"pipeline={pipeline} batch_id={batch_id}"
                )
            if negative_count_rows:
                raise ValueError(
                    "Quality manifest contains negative counts: "
                    f"pipeline={pipeline} batch_id={batch_id}"
                )
            if duplicate_key_rows:
                raise ValueError(
                    "Quality manifest contains duplicate date/source keys: "
                    f"pipeline={pipeline} batch_id={batch_id}"
                )
            if input_rows != valid_rows + quarantine_rows:
                raise ValueError(
                    "Quality manifest totals do not reconcile: "
                    f"input={input_rows} valid={valid_rows} "
                    f"quarantine={quarantine_rows}"
                )

            if valid_rows:
                count_result = client.query(
                    COUNT_SOURCE_SQL,
                    parameters=query_parameters,
                )
                parquet_rows = int(count_result.result_rows[0][0])
                if parquet_rows != valid_rows:
                    raise ValueError(
                        "Valid Parquet count does not match quality manifest: "
                        f"pipeline={pipeline} batch_id={batch_id} "
                        f"parquet={parquet_rows} manifest={valid_rows}"
                    )
                client.command(insert_sql, parameters=query_parameters)

            client.command(
                QUALITY_INSERT_SQL,
                parameters=quality_query_parameters,
            )
            client.command(
                RECORD_RESULT_SQL,
                parameters={
                    "pipeline": pipeline,
                    "batch_id": batch_id,
                    "status": "success",
                    "source_prefix": source_prefix,
                    "airflow_run_id": str(context["run_id"]),
                    "error_message": "",
                },
            )
            return {
                "pipeline": pipeline,
                "batch_id": batch_id,
                "valid_rows": valid_rows,
                "input_rows": input_rows,
                "quarantine_rows": quarantine_rows,
            }
        except Exception as error:
            LOGGER.exception(
                "Failed pipeline=%s batch_id=%s",
                pipeline,
                batch_id,
            )
            try:
                client.command(
                    RECORD_RESULT_SQL,
                    parameters={
                        "pipeline": pipeline,
                        "batch_id": batch_id,
                        "status": "failed",
                        "source_prefix": source_prefix,
                        "airflow_run_id": str(context["run_id"]),
                        "error_message": str(error)[:2000],
                    },
                )
            except Exception:
                LOGGER.exception("Could not record failed manifest row")
            raise
        finally:
            client.close()

    dependencies_ready = check_dependencies()
    pending_batches = discover_batches()
    dependencies_ready >> pending_batches
    load_batch.expand(batch=pending_batches)


minio_to_clickhouse()
