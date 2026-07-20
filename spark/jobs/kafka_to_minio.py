import json
import logging
import os
import time
from dataclasses import dataclass
from functools import reduce
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from pyspark import StorageLevel
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.avro.functions import from_avro
from pyspark.sql.functions import (
    base64,
    col,
    current_timestamp,
    expr,
    length,
    lit,
    to_date,
    when,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger("kafka-to-minio")

KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "fraud.transaction")
KAFKA_BOOTSTRAP_SERVERS = os.getenv(
    "KAFKA_BOOTSTRAP_SERVERS",
    "kafka:19092",
)

SCHEMA_REGISTRY_URL = os.getenv(
    "SCHEMA_REGISTRY_URL",
    "http://schema-registry:8081",
)
SCHEMA_SUBJECT = f"{KAFKA_TOPIC}-value"

BRONZE_PATH = "s3a://fraud-lake/bronze/fraud_transactions"
QUARANTINE_PATH = (
    "s3a://fraud-lake/quarantine/fraud_transactions"
)
CHECKPOINT_PATH = (
    "s3a://fraud-lake/checkpoints/fraud_transactions_router"
)


@dataclass(frozen=True)
class SchemaCatalog:
    subject: str
    reader_schema_id: int
    reader_schema: str
    writer_schemas: dict[int, str]


def registry_get(registry_url: str, path: str) -> dict | list:
    request = Request(
        f"{registry_url.rstrip('/')}{path}",
        headers={
            "Accept": "application/vnd.schemaregistry.v1+json",
        },
    )

    with urlopen(request, timeout=10) as response:
        return json.load(response)


def load_schema_catalog_once(
    registry_url: str,
    subject: str,
) -> SchemaCatalog:
    encoded_subject = quote(subject, safe="")
    versions = registry_get(
        registry_url,
        f"/subjects/{encoded_subject}/versions",
    )

    if not versions:
        raise RuntimeError(
            f"Subject chua co schema version: {subject}"
        )

    entries = [
        registry_get(
            registry_url,
            f"/subjects/{encoded_subject}/versions/{version}",
        )
        for version in versions
    ]

    latest = max(
        entries,
        key=lambda entry: int(entry["version"]),
    )
    writer_schemas = {
        int(entry["id"]): entry["schema"]
        for entry in entries
    }

    return SchemaCatalog(
        subject=subject,
        reader_schema_id=int(latest["id"]),
        reader_schema=latest["schema"],
        writer_schemas=writer_schemas,
    )


def load_schema_catalog(
    registry_url: str,
    subject: str,
    max_attempts: int = 12,
    retry_seconds: int = 5,
) -> SchemaCatalog:
    last_error = None

    for attempt in range(1, max_attempts + 1):
        try:
            catalog = load_schema_catalog_once(
                registry_url,
                subject,
            )
            logger.info(
                "Loaded Schema Registry catalog: "
                "subject=%s reader_schema_id=%s writer_ids=%s",
                catalog.subject,
                catalog.reader_schema_id,
                sorted(catalog.writer_schemas),
            )
            return catalog
        except (HTTPError, URLError, TimeoutError, RuntimeError) as error:
            last_error = error

            if attempt == max_attempts:
                break

            logger.warning(
                "Schema catalog is not ready; attempt=%s/%s error=%s",
                attempt,
                max_attempts,
                error,
            )
            time.sleep(retry_seconds)

    raise RuntimeError(
        f"Cannot load schema catalog for {subject}"
    ) from last_error


SCHEMA_CATALOG = load_schema_catalog(
    SCHEMA_REGISTRY_URL,
    SCHEMA_SUBJECT,
)
SUPPORTED_SCHEMA_IDS = sorted(
    SCHEMA_CATALOG.writer_schemas
)

spark = (
    SparkSession.builder
    .appName("KafkaToMinio")
    .getOrCreate()
)
spark.sparkContext.setLogLevel("WARN")

kafka_df = (
    spark.readStream
    .format("kafka")
    .option(
        "kafka.bootstrap.servers",
        KAFKA_BOOTSTRAP_SERVERS,
    )
    .option("subscribe", KAFKA_TOPIC)
    .option("startingOffsets", "earliest")
    .option("failOnDataLoss", "true")
    .option("maxOffsetsPerTrigger", "100000")
    .load()
)

inspected_df = (
    kafka_df
    .withColumn(
        "magic_byte",
        expr(
            "CAST(conv(hex(substring(value, 1, 1)), 16, 10) AS INT)"
        ),
    )
    .withColumn(
        "message_schema_id",
        expr(
            "CAST(conv(hex(substring(value, 2, 4)), 16, 10) AS BIGINT)"
        ),
    )
    .withColumn("value_size", length(col("value")))
    .withColumn("avro_payload", expr("substring(value, 6)"))
    .withColumn(
        "reader_schema_id",
        lit(SCHEMA_CATALOG.reader_schema_id),
    )
    .withColumn(
        "quarantine_reason",
        when(
            col("value").isNull(),
            lit("NULL_KAFKA_VALUE"),
        )
        .when(
            col("value_size") < 6,
            lit("CONFLUENT_MESSAGE_TOO_SHORT"),
        )
        .when(
            col("magic_byte") != 0,
            lit("INVALID_CONFLUENT_MAGIC_BYTE"),
        )
        .when(
            ~col("message_schema_id").isin(
                *SUPPORTED_SCHEMA_IDS
            ),
            lit("UNSUPPORTED_SCHEMA_ID"),
        )
        .otherwise(lit(None).cast("string")),
    )
)


def decode_supported_schemas(
    df: DataFrame,
    catalog: SchemaCatalog,
) -> DataFrame:
    branches = []

    for schema_id, writer_schema in sorted(
        catalog.writer_schemas.items()
    ):
        branch = (
            df
            .filter(
                col("message_schema_id") == lit(schema_id)
            )
            .withColumn(
                "transaction",
                from_avro(
                    col("avro_payload"),
                    writer_schema,
                    {
                        "mode": "PERMISSIVE",
                        "avroSchema": catalog.reader_schema,
                    },
                ),
            )
        )
        branches.append(branch)

    if not branches:
        raise RuntimeError("No supported writer schema")

    return reduce(
        lambda left, right: left.unionByName(
            right,
            allowMissingColumns=True,
        ),
        branches,
    )


def prepare_quarantine(df: DataFrame) -> DataFrame:
    """Keep the original Kafka bytes so failed messages can be replayed."""

    return (
        df
        .select(
            "quarantine_reason",
            "reader_schema_id",
            "message_schema_id",
            "magic_byte",
            "value_size",
            col("topic").alias("kafka_topic"),
            col("partition").alias("kafka_partition"),
            col("offset").alias("kafka_offset"),
            col("timestamp").alias("kafka_timestamp"),
            base64(col("key")).alias("kafka_key_base64"),
            base64(col("value")).alias(
                "kafka_value_base64"
            ),
        )
        .withColumn(
            "quarantined_at",
            current_timestamp(),
        )
        .withColumn(
            "kafka_date",
            to_date(col("kafka_timestamp")),
        )
    )


def process_batch(batch_df: DataFrame, batch_id: int) -> None:
    if batch_df.isEmpty():
        return

    batch_df.persist(StorageLevel.MEMORY_AND_DISK)
    decoded_df = None

    try:
        header_quarantine_df = prepare_quarantine(
            batch_df.filter(
                col("quarantine_reason").isNotNull()
            )
        )

        supported_df = batch_df.filter(
            col("quarantine_reason").isNull()
        )

        decoded_df = decode_supported_schemas(
            supported_df,
            SCHEMA_CATALOG,
        ).persist(StorageLevel.MEMORY_AND_DISK)

        decode_failed_df = (
            decoded_df
            .filter(col("transaction.event_id").isNull())
            .withColumn(
                "quarantine_reason",
                lit("AVRO_DECODE_FAILED"),
            )
        )

        quarantine_df = header_quarantine_df.unionByName(
            prepare_quarantine(decode_failed_df),
            allowMissingColumns=True,
        )

        bronze_df = (
            decoded_df
            .filter(col("transaction.event_id").isNotNull())
            .select(
                "transaction.*",
                "message_schema_id",
                col("topic").alias("kafka_topic"),
                col("partition").alias("kafka_partition"),
                col("offset").alias("kafka_offset"),
                col("timestamp").alias("kafka_timestamp"),
            )
            .withColumn(
                "event_date",
                to_date(col("ingested_at")),
            )
        )

        batch_partition = f"{batch_id:020d}"

        if not bronze_df.isEmpty():
            (
                bronze_df.write
                .mode("overwrite")
                .partitionBy("event_date")
                .parquet(
                    f"{BRONZE_PATH}/batch_id={batch_partition}"
                )
            )

        if not quarantine_df.isEmpty():
            (
                quarantine_df.write
                .mode("overwrite")
                .partitionBy(
                    "quarantine_reason",
                    "kafka_date",
                )
                .parquet(
                    f"{QUARANTINE_PATH}/batch_id={batch_partition}"
                )
            )

        logger.info(
            "Completed batch_id=%s reader_schema_id=%s",
            batch_id,
            SCHEMA_CATALOG.reader_schema_id,
        )
    finally:
        if decoded_df is not None:
            decoded_df.unpersist()
        batch_df.unpersist()


query = (
    inspected_df.writeStream
    .foreachBatch(process_batch)
    .option("checkpointLocation", CHECKPOINT_PATH)
    .trigger(processingTime="10 seconds")
    .start()
)

query.awaitTermination()
