
    
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select physical_row_count
from `fraudguard_core`.`fct_transactions`
where physical_row_count is null



  
  
    ) dbt_internal_test