
    
    

with all_values as (

    select
        is_flagged_fraud as value_field,
        count(*) as n_records

    from `fraudguard_core`.`fct_transaction_labels`
    group by is_flagged_fraud

)

select *
from all_values
where value_field not in (
    '0','1'
)


