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
    origin_balance_before - origin_balance_after as origin_balance_delta,
    destination_balance_after - destination_balance_before
        as destination_balance_delta,
    abs(
        (origin_balance_before - origin_balance_after) - amount
    ) as origin_amount_residual,
    abs(
        (destination_balance_after - destination_balance_before) - amount
    ) as destination_amount_residual,
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
    ) as training_exclusion_reason
from {{ ref('fct_transactions_labeled') }}