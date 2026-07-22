import json
import logging
import time
from dataclasses import dataclass
from functools import reduce
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from pyspark import StorageLevel
from pyspark.sql import Column, DataFrame, SparkSession
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

logger = logging.getLogger("kafka-minio-landing")

ValidationReasonBuilder = Callable[[Column], Column]


@dataclass(frozen=True)
class SchemaCatalog:
    subject: str
    reader_schema_id: int
    reader_schema: str
    writer_schemas: dict[int, str]


@dataclass(frozen=True)
class LandingConfig:
    kafka_topic: str
    kafka_bootstrap_servers: str
    schema_registry_url: str
    schema_subject: str
    app_name: str
    valid_path: str
    quarantine_path: str
    checkpoint_path: str
    record_column: str
    partition_timestamp_column: str
    partition_column: str
    validation_reason_builder: ValidationReasonBuilder
    trigger_interval: str = "10 seconds"
    starting_offset: str = "earliest"
    max_offsets_per_trigger: int = 100


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


def inspect_confluent_message(
    kafka_df: DataFrame,
    catalog: SchemaCatalog,
) -> DataFrame:
    supported_schema_ids = sorted(catalog.writer_schemas)

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
            lit(catalog.reader_schema_id),
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
                    *supported_schema_ids
                ),
                lit("UNSUPPORTED_SCHEMA_ID"),
            )
            .otherwise(lit(None).cast("string")),
        )
    )

    return inspected_df


def decode_supported_schemas(
    df: DataFrame,
    catalog: SchemaCatalog,
    record_column: str,
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
                record_column,
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


def build_process_batch(
    config: LandingConfig,
    catalog: SchemaCatalog,
) -> Callable[[DataFrame, int], None]:
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
                catalog,
                config.record_column,
            ).withColumn(
                "quarantine_reason",
                config.validation_reason_builder(col(config.record_column)),
            ).persist(StorageLevel.MEMORY_AND_DISK)

            decode_failed_df = prepare_quarantine(
                decoded_df.filter(
                    col("quarantine_reason").isNotNull()
                )
            )
            quarantine_df = header_quarantine_df.unionByName(
                decode_failed_df,
                allowMissingColumns=True,
            )

            valid_df = (
                decoded_df
                .filter(col("quarantine_reason").isNull())
                .select(
                    f"{config.record_column}.*",
                    "message_schema_id",
                    col("topic").alias("kafka_topic"),
                    col("partition").alias("kafka_partition"),
                    col("offset").alias("kafka_offset"),
                    col("timestamp").alias("kafka_timestamp"),
                )
                .withColumn(
                    config.partition_column,
                    to_date(col(config.partition_timestamp_column)),
                )
            )

            batch_partition = f"{batch_id:020d}"

            if not valid_df.isEmpty():
                (
                    valid_df.write
                    .mode("overwrite")
                    .partitionBy(config.partition_column)
                    .parquet(
                        f"{config.valid_path}/batch_id={batch_partition}"
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
                        f"{config.quarantine_path}/batch_id={batch_partition}"
                    )
                )

            logger.info(
                "Completed batch_id=%s reader_schema_id=%s",
                batch_id,
                catalog.reader_schema_id,
            )
        finally:
            if decoded_df is not None:
                decoded_df.unpersist()
            batch_df.unpersist()

    return process_batch


def run_landing(config: LandingConfig) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    catalog = load_schema_catalog(
        config.schema_registry_url,
        config.schema_subject,
    )

    spark = (
        SparkSession.builder
        .appName(config.app_name)
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")

    kafka_df = (
        spark.readStream
        .format("kafka")
        .option(
            "kafka.bootstrap.servers",
            config.kafka_bootstrap_servers,
        )
        .option("subscribe", config.kafka_topic)
        .option("startingOffsets", config.starting_offset)
        .option("failOnDataLoss", "true")
        .option(
            "maxOffsetsPerTrigger",
            str(config.max_offsets_per_trigger),
        )
        .load()
    )
    inspected_df = inspect_confluent_message(
        kafka_df,
        catalog,
    )

    logger.info(
        "Starting topic=%s valid_path=%s "
        "quarantine_path=%s checkpoint_path=%s",
        config.kafka_topic,
        config.valid_path,
        config.quarantine_path,
        config.checkpoint_path,
    )

    query = (
        inspected_df.writeStream
        .foreachBatch(build_process_batch(config, catalog))
        .option("checkpointLocation", config.checkpoint_path)
        .trigger(processingTime=config.trigger_interval)
        .start()
    )

    query.awaitTermination()
