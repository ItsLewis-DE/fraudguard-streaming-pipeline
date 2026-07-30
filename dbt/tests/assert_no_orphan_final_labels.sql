select
    l.source,
    l.event_id
from {{ ref('fct_transaction_labels') }} as l
left join {{ ref('fct_transactions') }} as t
    on l.source = t.source
   and l.event_id = t.event_id
where t.event_id = ''