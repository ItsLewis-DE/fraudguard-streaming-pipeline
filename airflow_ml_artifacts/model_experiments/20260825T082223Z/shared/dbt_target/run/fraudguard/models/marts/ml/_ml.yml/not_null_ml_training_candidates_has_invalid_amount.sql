
    
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select has_invalid_amount
from `fraudguard_ml`.`ml_training_candidates`
where has_invalid_amount is null



  
  
    ) dbt_internal_test