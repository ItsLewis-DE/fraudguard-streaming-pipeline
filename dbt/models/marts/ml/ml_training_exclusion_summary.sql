select
    training_exclusion_reason,
    toUInt64(count()) as row_count
from {{ ref('ml_training_candidates') }}
group by training_exclusion_reason