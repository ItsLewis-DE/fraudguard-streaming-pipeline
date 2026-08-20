
    
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select destination_balance_after_is_zero
from `fraudguard_ml`.`ml_training_candidates`
where destination_balance_after_is_zero is null



  
  
    ) dbt_internal_test