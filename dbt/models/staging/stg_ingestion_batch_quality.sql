with source_data as (
    {% if var('use_fixtures', false) %}
        select * from {{ ref('fixture_ingestion_batch_quality') }}
    {% else %}
        select * from {{ source('fraudguard', 'ingestion_batch_quality') }}
    {% endif %}
)

select
    toString(pipeline) as pipeline,
    toUInt64(batch_id) as batch_id,
    toDate(event_date) as event_date,
    toString(source) as source,
    toUInt64(input_rows) as input_rows,
    toUInt64(valid_rows) as valid_rows,
    toUInt64(quarantine_rows) as quarantine_rows,
    toDateTime64(loaded_at, 3, 'UTC') as loaded_at
from source_data
