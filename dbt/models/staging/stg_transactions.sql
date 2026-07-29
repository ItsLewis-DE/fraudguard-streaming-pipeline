with source_data as (
    {% if var('use_fixtures', false) %}
        select * from {{ ref('fixture_transactions') }}
    {% else %}
        select * from {{ source('fraudguard', 'transactions') }}
    {% endif %}
)

select
    toString(event_id) as event_id,
    toString(source) as source,
    toDateTime64(event_time, 3, 'UTC') as event_time,
    toDateTime64(ingested_at, 3, 'UTC') as ingested_at,
    toUInt16(step) as step,
    toString(transaction_type) as transaction_type,
    toDecimal64(amount, 2) as amount,
    toString(origin_account) as origin_account,
    toDecimal64(origin_balance_before, 2) as origin_balance_before,
    toDecimal64(origin_balance_after, 2) as origin_balance_after,
    toString(destination_account) as destination_account,
    toDecimal64(destination_balance_before, 2) as destination_balance_before,
    toDecimal64(destination_balance_after, 2) as destination_balance_after,
    toUInt32(schema_id) as schema_id,
    toString(kafka_topic) as kafka_topic,
    toUInt16(kafka_partition) as kafka_partition,
    toUInt64(kafka_offset) as kafka_offset,
    toDateTime64(kafka_timestamp, 3, 'UTC') as kafka_timestamp,
    toUInt64(minio_batch_id) as minio_batch_id,
    toString(minio_object) as minio_object,
    toDateTime64(loaded_at, 3, 'UTC') as loaded_at
from source_data
