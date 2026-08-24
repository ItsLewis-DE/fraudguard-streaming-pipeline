
    
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select is_training_eligible
from `fraudguard_ml`.`ml_training_candidates`
where is_training_eligible is null



  
  
    ) dbt_internal_test