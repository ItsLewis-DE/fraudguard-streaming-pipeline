select *
from {{ ref('ml_training_candidates') }}
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