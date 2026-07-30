with eligible as (
    select source, event_id
    from {{ ref('ml_training_candidates') }}
    where is_training_eligible
),
training as (
    select source, event_id
    from {{ ref('ml_training_transactions') }}
),
missing_training as (
    select e.source, e.event_id, 'eligible_missing' as contract_error
    from eligible as e
    left join training as t using (source, event_id)
    where t.event_id = ''
),
unexpected_training as (
    select t.source, t.event_id, 'ineligible_present' as contract_error
    from training as t
    left join eligible as e using (source, event_id)
    where e.event_id = ''
)
select * from missing_training
union all
select * from unexpected_training