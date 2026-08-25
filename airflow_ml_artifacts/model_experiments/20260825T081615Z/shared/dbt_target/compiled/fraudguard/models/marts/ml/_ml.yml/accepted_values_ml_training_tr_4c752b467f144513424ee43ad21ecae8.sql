
    
    

with all_values as (

    select
        destination_balance_after_is_zero as value_field,
        count(*) as n_records

    from `fraudguard_ml`.`ml_training_transactions`
    group by destination_balance_after_is_zero

)

select *
from all_values
where value_field not in (
    '0','1'
)


