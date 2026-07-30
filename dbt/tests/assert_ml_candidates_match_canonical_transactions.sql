with candidate_keys as (
    select source, event_id
    from {{ ref('ml_training_candidates') }}
),
canonical_keys as (
    select source, event_id
    from {{ ref('fct_transactions') }}
),
missing_candidate as (
    select c.source, c.event_id, 'missing_candidate' as contract_error
    from canonical_keys as c
    left join candidate_keys as m using (source, event_id)
    where m.event_id = ''
),
unexpected_candidate as (
    select m.source, m.event_id, 'unexpected_candidate' as contract_error
    from candidate_keys as m
    left join canonical_keys as c using (source, event_id)
    where c.event_id = ''
)

select * from missing_candidate
union all
select * from unexpected_candidate