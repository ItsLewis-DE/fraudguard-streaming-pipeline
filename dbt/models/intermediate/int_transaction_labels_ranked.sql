with committed_rows as (
    select l.*
    from {{ ref('stg_transaction_labels') }} l
    inner join {{ ref('int_committed_ingestion_batches') }} b
        on b.pipeline = 'labels'
       and b.batch_id = l.minio_batch_id
),
prepared as (
    select
        *,
        cityHash64(is_fraud, is_flagged_fraud) as label_payload_hash
    from committed_rows
),
key_stats as (
    select
        source,
        event_id,
        count() as physical_row_count,
        uniqExact(label_payload_hash) as payload_version_count
    from prepared
    group by source, event_id
),
ranked as (
    select
        p.*,
        row_number() over (
            partition by p.source, p.event_id
            order by
                p.kafka_topic asc,
                p.kafka_partition asc,
                p.kafka_offset asc,
                p.minio_batch_id asc,
                p.minio_object asc,
                p.loaded_at asc,
                p.label_payload_hash asc
        ) as canonical_rank
    from prepared p
)

select
    r.*,
    s.physical_row_count,
    s.payload_version_count
from ranked r
inner join key_stats s
    on r.source = s.source
   and r.event_id = s.event_id