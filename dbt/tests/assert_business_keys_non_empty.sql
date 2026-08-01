select
    'fct_transactions' as relation_name,
    source,
    event_id
from {{ ref('fct_transactions') }}
where trim(source) = '' or trim(event_id) = ''

union all

select
    'fct_transaction_labels' as relation_name,
    source,
    event_id
from {{ ref('fct_transaction_labels') }}
where trim(source) = '' or trim(event_id) = ''