
    
    

with all_values as (

    select
        transaction_type as value_field,
        count(*) as n_records

    from `fraudguard_ml`.`ml_training_candidates`
    group by transaction_type

)

select *
from all_values
where value_field not in (
    'CASH_IN','CASH_OUT','DEBIT','PAYMENT','TRANSFER'
)


