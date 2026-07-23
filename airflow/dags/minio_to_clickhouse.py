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

BATCH_MARKER_PATTERN = re.compile(
    r"^batch_id=(?P<batch_id>[0-9]{20})/_SUCCESS$"
)

PIPELINES = (
    {
        "pipeline": "transactions",
        "bucket": "fraud-transactions",
    },
    {
        "pipeline": "labels",
        "bucket": "fraud-transaction-labels",
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
observed_at DateTime64(3, 'UTC'),
isFraud Int32, isFlaggedFraud Int32,
message_schema_id Int64, kafka_topic String,
kafka_partition Int32, kafka_offset Int64,
kafka_timestamp DateTime64(3, 'UTC')
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
    event_id, source, observed_at, is_fraud, is_flagged_fraud,
    schema_id, kafka_topic, kafka_partition, kafka_offset,
    kafka_timestamp, minio_batch_id, minio_object, loaded_at
)
SELECT
    event_id,
    source,
    observed_at,
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
# source_rows là số dòng dữ liệu được nạp.
# source_prefix là thư mục trên MinIO chứa lô dữ liệu này.
RECORD_RESULT_SQL = """
INSERT INTO ingestion_batches
(
    pipeline, batch_id, source_rows, status, source_prefix,
    airflow_run_id, finished_at, error_message
)
VALUES
(
    {pipeline:String},
    {batch_id:UInt64},
    {source_rows:UInt64},
    {status:String},
    {source_prefix:String},
    {airflow_run_id:String},
    now64(3),
    {error_message:String}
)
"""
# Khi triển khai lên server thật, chỉ cần cấu hình lại Airflow Connections.
def get_clickhouse_client():
    connection = get_current_context()["conn"].get(
        CLICKHOUSE_CONNECTION_ID
    )
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
                         'ingestion_batches')
            """
            )
            table_count = int(result.result_rows[0][0])
            if table_count !=3:
                raise RuntimeError(
                    "Run the DDL before enabling this DAG"
                )
        finally:
            client.close()

    @task
    def discover_batches() -> list[dict[str, Any]]:
        hook,_,_,_ = get_minio_runtime()
        client = get_clickhouse_client()
        try:
            loaded ={
                (str(pipeline),int(batch_id)) 
                for pipeline,batch_id in client.query(
                    """
                    SELECT pipeline,batch_id 
                    FROM ingestion_batches FINAL
                    WHERE status = 'success'
                    """
                ).result_rows
            }
            discovered: list[dict[str, Any]] = []
            for config in PIPELINES:
                keys = hook.list_keys(
                    bucket_name=config["bucket"],
                    prefix="batch_id=",
                ) or []

                for key in keys:
                    match = BATCH_MARKER_PATTERN.fullmatch(key)
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
                            "batch_id": batch_id,
                            "padded_batch_id": padded_batch_id,
                        }
                    )

            discovered.sort(
                key=lambda item: (item["pipeline"], item["batch_id"])
            )
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
        batch_id = int(batch["batch_id"])
        padded_batch_id = str(batch["padded_batch_id"])
        source_prefix = f"{bucket}/batch_id={padded_batch_id}"
        source_url = f"{endpoint_url}/{source_prefix}/**/*.parquet"

        if pipeline == "transactions":
            source_structure = TRANSACTION_SOURCE_STRUCTURE
            insert_sql = TRANSACTION_INSERT_SQL
        elif pipeline == "labels":
            source_structure = LABEL_SOURCE_STRUCTURE
            insert_sql = LABEL_INSERT_SQL
        else:
            raise ValueError(f"Unsupported pipeline: {pipeline}")

        query_parameters = {
            "source_url": source_url,
            "access_key": access_key,
            "secret_key": secret_key,
            "source_structure": source_structure,
            "batch_id": batch_id,
        }
        source_rows = 0

        try:
            count_result = client.query(
                COUNT_SOURCE_SQL,
                parameters=query_parameters,
            )
            source_rows = int(count_result.result_rows[0][0])
            if source_rows == 0:
                raise ValueError(f"Empty completed batch: {source_prefix}")

            client.command(insert_sql, parameters=query_parameters)
            client.command(
                RECORD_RESULT_SQL,
                parameters={
                    "pipeline": pipeline,
                    "batch_id": batch_id,
                    "source_rows": source_rows,
                    "status": "success",
                    "source_prefix": source_prefix,
                    "airflow_run_id": str(context["run_id"]),
                    "error_message": "",
                },
            )
            return {
                "pipeline": pipeline,
                "batch_id": batch_id,
                "source_rows": source_rows,
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
                        "source_rows": source_rows,
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
