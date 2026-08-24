
    
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select source
from `fraudguard_ml`.`ml_training_transactions`
where source is null



  
  
    ) dbt_internal_test