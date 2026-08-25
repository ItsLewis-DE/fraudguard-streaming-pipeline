
    
    

with all_values as (

    select
        origin_balance_before_is_zero as value_field,
        count(*) as n_records

    from `fraudguard_ml`.`ml_training_transactions`
    group by origin_balance_before_is_zero

)

select *
from all_values
where value_field not in (
    '0','1'
)


