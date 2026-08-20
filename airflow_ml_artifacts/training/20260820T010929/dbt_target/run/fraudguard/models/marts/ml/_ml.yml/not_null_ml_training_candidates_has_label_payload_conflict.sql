
    
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select has_label_payload_conflict
from `fraudguard_ml`.`ml_training_candidates`
where has_label_payload_conflict is null



  
  
    ) dbt_internal_test