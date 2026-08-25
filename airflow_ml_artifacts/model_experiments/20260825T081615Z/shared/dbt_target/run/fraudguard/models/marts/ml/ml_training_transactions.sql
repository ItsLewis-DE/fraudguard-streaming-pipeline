
  
    
    
    
        
         


        
  

  insert into `fraudguard_ml`.`ml_training_transactions__dbt_tmp`
        ("source", "event_id", "event_time", "event_date", "step", "transaction_type", "amount", "origin_balance_before", "origin_balance_after", "destination_balance_before", "destination_balance_after", "origin_balance_delta", "destination_balance_delta", "origin_amount_residual", "destination_amount_residual", "origin_balance_before_is_zero", "destination_balance_before_is_zero", "destination_balance_after_is_zero", "is_fraud")select
    source,
    event_id,
    event_time,
    event_date,
    step,
    transaction_type,
    amount,
    origin_balance_before,
    origin_balance_after,
    destination_balance_before,
    destination_balance_after,
    origin_balance_delta,
    destination_balance_delta,
    origin_amount_residual,
    destination_amount_residual,
    origin_balance_before_is_zero,
    destination_balance_before_is_zero,
    destination_balance_after_is_zero,
    is_fraud
from `fraudguard_ml`.`ml_training_candidates`
where is_training_eligible
  