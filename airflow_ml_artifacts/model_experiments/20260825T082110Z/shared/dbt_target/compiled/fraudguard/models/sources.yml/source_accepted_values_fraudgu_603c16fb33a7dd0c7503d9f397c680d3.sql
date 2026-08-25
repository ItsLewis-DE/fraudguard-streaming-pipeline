
    
    

with all_values as (

    select
        pipeline as value_field,
        count(*) as n_records

    from `fraudguard`.`ingestion_batches`
    group by pipeline

)

select *
from all_values
where value_field not in (
    'transactions','labels'
)


