select *
from {{ ref('stg_ingestion_batch_quality') }}
where input_rows != valid_rows + quarantine_rows