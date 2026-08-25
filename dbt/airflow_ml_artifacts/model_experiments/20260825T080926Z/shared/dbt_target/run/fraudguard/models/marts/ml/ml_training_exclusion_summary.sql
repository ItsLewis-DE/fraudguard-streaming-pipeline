
  
    
    
    
        
         


        
  

  insert into `fraudguard_ml`.`ml_training_exclusion_summary__dbt_backup`
        ("training_exclusion_reason", "row_count")select
    training_exclusion_reason,
    toUInt64(count()) as row_count
from `fraudguard_ml`.`ml_training_candidates`
group by training_exclusion_reason
  