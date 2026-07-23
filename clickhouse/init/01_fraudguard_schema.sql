CREATE DATABASE IF NOT EXISTS fraudguard;

CREATE TABLE IF NOT EXISTS fraudguard.transactions
(
    event_id                    String,
    source                      LowCardinality(String),
    event_time                  DateTime64(3, 'UTC'),
    event_date                  Date MATERIALIZED toDate(event_time),
    ingested_at                 DateTime64(3, 'UTC'),
    step                        UInt16,
    transaction_type            LowCardinality(String),
    amount                      Decimal64(2),
    origin_account              String,
    origin_balance_before       Decimal64(2),
    origin_balance_after        Decimal64(2),
    destination_account         String,
    destination_balance_before  Decimal64(2),
    destination_balance_after   Decimal64(2),
    schema_id                   UInt32,
    kafka_topic                 LowCardinality(String),
    kafka_partition             UInt16,
    kafka_offset                UInt64,
    kafka_timestamp             DateTime64(3, 'UTC'),
    minio_batch_id              UInt64,
    minio_object                String,
    loaded_at                   DateTime64(3, 'UTC') DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(event_time)
ORDER BY (source, event_id)
SETTINGS index_granularity = 8192;

CREATE TABLE IF NOT EXISTS fraudguard.transaction_labels
(
    event_id          String,
    source            LowCardinality(String),
    observed_at       DateTime64(3, 'UTC'),
    observed_date     Date MATERIALIZED toDate(observed_at),
    is_fraud          UInt8,
    is_flagged_fraud  UInt8,
    schema_id         UInt32,
    kafka_topic       LowCardinality(String),
    kafka_partition   UInt16,
    kafka_offset      UInt64,
    kafka_timestamp   DateTime64(3, 'UTC'),
    minio_batch_id    UInt64,
    minio_object      String,
    loaded_at         DateTime64(3, 'UTC') DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(observed_at)
PARTITION BY cityHash64(event_id) % 32
ORDER BY (source, event_id)
SETTINGS index_granularity = 8192;

CREATE TABLE IF NOT EXISTS fraudguard.ingestion_batches
(
    pipeline       LowCardinality(String),
    batch_id       UInt64,
    source_rows    UInt64,
    status         Enum8('success' = 1, 'failed' = 2),
    source_prefix  String,
    airflow_run_id String DEFAULT '',
    finished_at    DateTime64(3, 'UTC'),
    error_message  String DEFAULT ''
)
ENGINE = ReplacingMergeTree(finished_at)
ORDER BY (pipeline, batch_id);
