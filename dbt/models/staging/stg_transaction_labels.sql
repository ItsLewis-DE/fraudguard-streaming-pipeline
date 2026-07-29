with source_data as (
    {% if var('use_fixtures', false) %}
        select * from {{ ref('fixture_transaction_labels') }}
    {% else %}
        select * from {{ source('fraudguard', 'transaction_labels') }}
    {% endif %}
)

select
    toString(event_id) as event_id,
    toString(source) as source,
    toUInt8(is_fraud) as is_fraud,
    toUInt8(is_flagged_fraud) as is_flagged_fraud,
    toUInt32(schema_id) as schema_id,
    toString(kafka_topic) as kafka_topic,
    toUInt16(kafka_partition) as kafka_partition,
    toUInt64(kafka_offset) as kafka_offset,
    toDateTime64(kafka_timestamp, 3, 'UTC') as kafka_timestamp,
    toUInt64(minio_batch_id) as minio_batch_id,
    toString(minio_object) as minio_object,
    toDateTime64(loaded_at, 3, 'UTC') as loaded_at
from source_data