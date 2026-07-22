import os

from pyspark.sql import Column
from pyspark.sql.functions import lit, when

from kafka_minio_landing import LandingConfig, run_landing


def label_validation_reason(record: Column) -> Column:
    return (
        when(
            record["event_id"].isNull(),
            lit("AVRO_DECODE_FAILED"),
        )
        .when(
            record["observed_at"].isNull(),
            lit("MISSING_OBSERVED_AT"),
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
    kafka_topic = os.getenv(
        "LABEL_KAFKA_TOPIC",
        "fraud.transaction.label",
    )
    run_landing(
        LandingConfig(
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
            checkpoint_path=os.getenv(
                "LABEL_CHECKPOINT_PATH",
                "s3a://fraud-transaction-labels-checkpoint/checkpoint",
            ),
            record_column="label",
            partition_timestamp_column="observed_at",
            partition_column="observed_date",
            validation_reason_builder=label_validation_reason,
        )
    )


if __name__ == "__main__":
    main()
