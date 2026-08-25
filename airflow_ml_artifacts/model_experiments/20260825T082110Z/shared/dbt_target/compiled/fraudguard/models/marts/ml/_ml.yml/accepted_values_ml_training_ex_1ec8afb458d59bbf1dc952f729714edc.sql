
    
    

with all_values as (

    select
        training_exclusion_reason as value_field,
        count(*) as n_records

    from `fraudguard_ml`.`ml_training_exclusion_summary`
    group by training_exclusion_reason

)

select *
from all_values
where value_field not in (
    'eligible','missing_final_label','transaction_payload_conflict','label_payload_conflict','invalid_amount','invalid_balance'
)


