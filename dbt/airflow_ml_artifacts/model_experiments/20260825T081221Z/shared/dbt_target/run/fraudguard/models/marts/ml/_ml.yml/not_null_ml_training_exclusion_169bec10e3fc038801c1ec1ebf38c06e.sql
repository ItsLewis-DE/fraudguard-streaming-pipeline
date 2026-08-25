
    
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select training_exclusion_reason
from `fraudguard_ml`.`ml_training_exclusion_summary`
where training_exclusion_reason is null



  
  
    ) dbt_internal_test