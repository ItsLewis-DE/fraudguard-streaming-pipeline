import os

from pyspark.sql import Column
from pyspark.sql.functions import lit, when

from kafka_minio_landing import LandingConfig, run_landing


def transaction_validation_reason(record: Column) -> Column:
    return (
        when(
            record["event_id"].isNull(),
            lit("AVRO_DECODE_FAILED"),
        )
        .when(
            record["event_time"].isNull(),
            lit("MISSING_EVENT_TIME"),
        )
        .when(
            record["ingested_at"].isNull(),
            lit("MISSING_INGESTED_AT"),
        )
        .when(
            record["event_time"] > record["ingested_at"],
            lit("EVENT_TIME_AFTER_INGESTED_AT"),
        )
        .when(
            record["step"] < 1,
            lit("INVALID_STEP"),
        )
        .otherwise(lit(None).cast("string"))
    )


def main() -> None:
    kafka_topic = os.getenv("KAFKA_TOPIC", "fraud.transaction")
    run_landing(
        LandingConfig(
            app_name="KafkaTransactionsToMinio",
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
                "SCHEMA_SUBJECT",
                f"{kafka_topic}-value",
            ),
            valid_path=os.getenv(
                "VALID_PATH",
                "s3a://fraud-transactions",
            ),
            quarantine_path=os.getenv(
                "QUARANTINE_PATH",
                "s3a://fraud-transactions-quarantine",
            ),
            checkpoint_path=os.getenv(
                "CHECKPOINT_PATH",
                "s3a://fraud-transactions-checkpoint/checkpoint",
            ),
            record_column="transaction",
            partition_timestamp_column="event_time",
            partition_column="event_date",
            validation_reason_builder=transaction_validation_reason,
        )
    )


if __name__ == "__main__":
    main()
