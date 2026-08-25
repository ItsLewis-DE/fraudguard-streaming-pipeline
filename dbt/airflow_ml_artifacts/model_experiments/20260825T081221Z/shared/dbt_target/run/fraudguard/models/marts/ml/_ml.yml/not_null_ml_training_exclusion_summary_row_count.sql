
    
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select row_count
from `fraudguard_ml`.`ml_training_exclusion_summary`
where row_count is null



  
  
    ) dbt_internal_test