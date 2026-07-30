select pipeline, batch_id, count() as row_count
from {{ ref('int_committed_ingestion_batches') }}
group by pipeline, batch_id
having count() != 1