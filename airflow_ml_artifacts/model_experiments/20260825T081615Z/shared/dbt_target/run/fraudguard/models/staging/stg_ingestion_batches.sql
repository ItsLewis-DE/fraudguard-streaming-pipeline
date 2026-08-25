

  create or replace view `fraudguard_staging`.`stg_ingestion_batches` 
  
    
  
  
    
    
  as (
    with source_data as (
    
        select * from `fraudguard`.`ingestion_batches`
    
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
    
  )
      
      
                    -- end_of_sql
                    
                    