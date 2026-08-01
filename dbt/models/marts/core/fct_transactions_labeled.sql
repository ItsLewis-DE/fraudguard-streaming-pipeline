select
    t.*,
    l.is_fraud,
    l.is_flagged_fraud,
    l.event_id != '' as has_final_label,
    ifNull(l.has_payload_conflict, false) as has_label_payload_conflict
from {{ ref('fct_transactions') }} as t  
left join {{ ref('fct_transaction_labels') }} l
    on t.source = l.source
   and t.event_id = l.event_id