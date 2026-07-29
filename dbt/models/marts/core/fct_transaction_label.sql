select
    source,
    event_id,
    is_fraud,
    is_flagged_fraud,
    schema_id,
    kafka_topic as canonical_kafka_topic,
    kafka_partition as canonical_kafka_partition,
    kafka_offset as canonical_kafka_offset,
    minio_batch_id as canonical_minio_batch_id,
    minio_object as canonical_minio_object,
    loaded_at as canonical_loaded_at,
    label_payload_hash,
    physical_row_count,
    physical_row_count - 1 as replay_row_count,
    payload_version_count,
    payload_version_count > 1 as has_payload_conflict
from {{ ref('int_transaction_labels_ranked') }}
where canonical_rank = 1