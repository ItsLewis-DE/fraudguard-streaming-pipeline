
    
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select step
from `fraudguard_ml`.`ml_training_candidates`
where step is null



  
  
    ) dbt_internal_test