select
    t.*,
    l.is_fraud,
    l.is_flagged_fraud,
    l.event_id != '' as has_final_label,
    ifNull(l.has_payload_conflict, false) as has_label_payload_conflict
from `fraudguard_core`.`fct_transactions` as t  
left join `fraudguard_core`.`fct_transaction_labels` l
    on t.source = l.source
   and t.event_id = l.event_id