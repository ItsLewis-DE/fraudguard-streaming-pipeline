
    
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select destination_amount_residual
from `fraudguard_ml`.`ml_training_candidates`
where destination_amount_residual is null



  
  
    ) dbt_internal_test