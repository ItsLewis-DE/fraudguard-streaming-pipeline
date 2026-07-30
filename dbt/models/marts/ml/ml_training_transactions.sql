select
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
    is_fraud
from {{ ref('ml_training_candidates') }}
where is_training_eligible