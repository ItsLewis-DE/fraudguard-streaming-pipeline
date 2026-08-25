
  
    
    
    
        
         


        
  

  insert into `fraudguard_ml`.`ml_training_candidates__dbt_tmp`
        ("source", "event_id", "event_time", "event_date", "step", "transaction_type", "amount", "origin_balance_before", "origin_balance_after", "destination_balance_before", "destination_balance_after", "is_fraud", "has_final_label", "has_payload_conflict", "has_label_payload_conflict", "has_invalid_amount", "has_invalid_balance", "is_training_eligible", "training_exclusion_reason", "origin_balance_delta", "destination_balance_delta", "origin_amount_residual", "destination_amount_residual", "origin_balance_before_is_zero", "destination_balance_before_is_zero", "destination_balance_after_is_zero")select
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
    is_fraud,
    has_final_label,
    has_payload_conflict,
    has_label_payload_conflict,
    has_invalid_amount,
    has_invalid_balance,
    (
        has_final_label
        and not has_payload_conflict
        and not has_label_payload_conflict
        and not has_invalid_amount
        and not has_invalid_balance
    ) as is_training_eligible,
    multiIf(
        not has_final_label, 'missing_final_label',
        has_payload_conflict, 'transaction_payload_conflict',
        has_label_payload_conflict, 'label_payload_conflict',
        has_invalid_amount, 'invalid_amount',
        has_invalid_balance, 'invalid_balance',
        'eligible'
    ) as training_exclusion_reason,
    origin_balance_before - origin_balance_after as origin_balance_delta,
    destination_balance_after - destination_balance_before as destination_balance_delta,
    abs(
        (origin_balance_before - origin_balance_after) - amount
    ) as origin_amount_residual,
    abs(
        (destination_balance_after - destination_balance_before) - amount
    ) as destination_amount_residual,
    origin_balance_before = 0 as origin_balance_before_is_zero,
    destination_balance_before = 0 as destination_balance_before_is_zero,
    destination_balance_after = 0 as destination_balance_after_is_zero
from `fraudguard_core`.`fct_transactions_labeled`
  