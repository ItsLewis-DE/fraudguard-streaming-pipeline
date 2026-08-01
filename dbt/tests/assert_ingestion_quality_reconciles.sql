-- Test này dùng để kiểm tra view stage xem có đúng logic k
select *
from {{ ref('stg_ingestion_batch_quality') }}
where input_rows != valid_rows + quarantine_rows