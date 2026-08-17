"""Configure the fraud-label Kafka-to-MinIO Spark landing job.

Flow:
    1. Resolve label-specific Kafka, Schema Registry, MinIO, and checkpoint paths.
    2. Validate decoded fraud flags against their binary domains.
    3. Delegate shared Confluent framing, schema evolution, quarantine, quality,
       and Parquet writing behavior to :func:`run_landing`.

Labels do not carry the business timestamp used by transaction partitioning, so
this pipeline explicitly disables event-date partition derivation.
"""

import os

from kafka_minio_landing import LandingConfig, run_landing
from pyspark.sql import Column
from pyspark.sql.functions import lit, when


def label_validation_reason(record: Column) -> Column:
    """Return the first label-domain violation as a Spark column expression.

    A null reason means the decoded label is valid; otherwise the stable reason
    code determines its quarantine partition and operational diagnostics.
    """

    return (
        when(
            record["event_id"].isNull(),
            lit("AVRO_DECODE_FAILED"),
        )
        .when(
            ~record["isFraud"].isin(0, 1),
            lit("INVALID_IS_FRAUD"),
        )
        .when(
            ~record["isFlaggedFraud"].isin(0, 1),
            lit("INVALID_IS_FLAGGED_FRAUD"),
        )
        .otherwise(lit(None).cast("string"))
    )


def main() -> None:
    """Build label landing configuration from the environment and start the job."""

    kafka_topic = os.getenv(
        "LABEL_KAFKA_TOPIC",
        "fraud.transaction.label",
    )
    run_landing(
        LandingConfig(
            pipeline="labels",
            app_name="KafkaLabelsToMinio",
            kafka_topic=kafka_topic,
            kafka_bootstrap_servers=os.getenv(
                "KAFKA_BOOTSTRAP_SERVERS",
                "kafka:19092",
            ),
            schema_registry_url=os.getenv(
                "SCHEMA_REGISTRY_URL",
                "http://schema-registry:8081",
            ),
            schema_subject=os.getenv(
                "LABEL_SCHEMA_SUBJECT",
                f"{kafka_topic}-value",
            ),
            valid_path=os.getenv(
                "LABEL_VALID_PATH",
                "s3a://fraud-transaction-labels",
            ),
            quarantine_path=os.getenv(
                "LABEL_QUARANTINE_PATH",
                "s3a://fraud-transaction-labels-quarantine",
            ),
            quality_path=os.getenv(
                "LABEL_QUALITY_PATH",
                "s3a://fraud-ingestion-quality/pipeline=labels",
            ),
            checkpoint_path=os.getenv(
                "LABEL_CHECKPOINT_PATH",
                "s3a://fraud-transaction-labels-checkpoint/checkpoint",
            ),
            record_column="label",
            partition_timestamp_column=None,
            partition_column=None,
            validation_reason_builder=label_validation_reason,
        )
    )


if __name__ == "__main__":
    main()
