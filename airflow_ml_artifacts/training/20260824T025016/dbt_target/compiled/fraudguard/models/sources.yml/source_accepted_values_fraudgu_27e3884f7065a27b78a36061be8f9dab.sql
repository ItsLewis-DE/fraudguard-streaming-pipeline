
    
    

with all_values as (

    select
        status as value_field,
        count(*) as n_records

    from `fraudguard`.`ingestion_batches`
    group by status

)

select *
from all_values
where value_field not in (
    'success','failed'
)


