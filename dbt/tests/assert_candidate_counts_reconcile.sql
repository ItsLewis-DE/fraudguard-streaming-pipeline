with totals as (
    select
        count() as candidate_count,
        countIf(is_training_eligible) as eligible_count,
        countIf(not is_training_eligible) as excluded_count
    from {{ ref('ml_training_candidates') }}
)
select *
from totals
where candidate_count != eligible_count + excluded_count