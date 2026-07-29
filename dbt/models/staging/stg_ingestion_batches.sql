with source_data as (
    {% if var('use_fixtures', false) %}
        select * from {{ ref('fixture_ingestion_batches') }}
    {% else %}
        select * from {{ source('fraudguard', 'ingestion_batches') }}
    {% endif %}
)

select
    toString(pipeline) as pipeline,
    toUInt64(batch_id) as batch_id,
    toString(status) as status,
    toString(source_prefix) as source_prefix,
    toString(airflow_run_id) as airflow_run_id,
    toDateTime64(finished_at, 3, 'UTC') as finished_at,
    toString(error_message) as error_message
from source_data
