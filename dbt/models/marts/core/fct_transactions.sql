select
    source,
    event_id,
    event_time,
    toDate(event_time) as event_date,
    ingested_at as canonical_ingested_at,
    step,
    transaction_type,
    amount,
    origin_account,
    origin_balance_before,
    origin_balance_after,
    destination_account,
    destination_balance_before,
    destination_balance_after,
    schema_id,
    kafka_topic as canonical_kafka_topic,
    kafka_partition as canonical_kafka_partition,
    kafka_offset as canonical_kafka_offset,
    minio_batch_id as canonical_minio_batch_id,
    minio_object as canonical_minio_object,
    loaded_at as canonical_loaded_at,
    transaction_payload_hash,
    physical_row_count,
    physical_row_count - 1 as replay_row_count,
    payload_version_count,
    payload_version_count > 1 as has_payload_conflict,
    amount < 0 as has_invalid_amount,
    (
        origin_balance_before < 0
        or origin_balance_after < 0
        or destination_balance_before < 0
        or destination_balance_after < 0
    ) as has_invalid_balance
from {{ ref('int_transactions_ranked') }}
where canonical_rank = 1