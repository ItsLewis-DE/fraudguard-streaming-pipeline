
  
    
    
    
        
         


        
  

  insert into `fraudguard_core`.`fct_transactions_labeled__dbt_tmp`
        ("source", "event_id", "event_time", "event_date", "canonical_ingested_at", "step", "transaction_type", "amount", "origin_account", "origin_balance_before", "origin_balance_after", "destination_account", "destination_balance_before", "destination_balance_after", "schema_id", "canonical_kafka_topic", "canonical_kafka_partition", "canonical_kafka_offset", "canonical_minio_batch_id", "canonical_minio_object", "canonical_loaded_at", "transaction_payload_hash", "physical_row_count", "replay_row_count", "payload_version_count", "has_payload_conflict", "has_invalid_amount", "has_invalid_balance", "is_fraud", "is_flagged_fraud", "has_final_label", "has_label_payload_conflict")select
    t.*,
    l.is_fraud,
    l.is_flagged_fraud,
    l.event_id != '' as has_final_label,
    ifNull(l.has_payload_conflict, false) as has_label_payload_conflict
from `fraudguard_core`.`fct_transactions` as t  
left join `fraudguard_core`.`fct_transaction_labels` l
    on t.source = l.source
   and t.event_id = l.event_id
  