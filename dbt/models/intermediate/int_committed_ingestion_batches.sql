select
    pipeline,
    batch_id,
    max(finished_at) as committed_at,
    count() as success_attempt_count
from {{ ref('stg_ingestion_batches') }}
where status = 'success'
group by pipeline, batch_id