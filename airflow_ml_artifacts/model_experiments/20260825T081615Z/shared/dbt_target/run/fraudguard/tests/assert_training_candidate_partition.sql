
    
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  -- Kiểm tra có sự bất hợp lí nào k trong table đó
select *
from `fraudguard_ml`.`ml_training_candidates`
where
    (is_training_eligible and training_exclusion_reason != 'eligible')
    or
    (not is_training_eligible and training_exclusion_reason = 'eligible')
    or training_exclusion_reason not in (
        'eligible',
        'missing_final_label',
        'transaction_payload_conflict',
        'label_payload_conflict',
        'invalid_amount',
        'invalid_balance'
    )
  
  
    ) dbt_internal_test