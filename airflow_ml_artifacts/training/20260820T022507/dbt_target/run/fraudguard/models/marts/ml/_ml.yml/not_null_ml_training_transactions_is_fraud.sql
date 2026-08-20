
    
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select is_fraud
from `fraudguard_ml`.`ml_training_transactions`
where is_fraud is null



  
  
    ) dbt_internal_test