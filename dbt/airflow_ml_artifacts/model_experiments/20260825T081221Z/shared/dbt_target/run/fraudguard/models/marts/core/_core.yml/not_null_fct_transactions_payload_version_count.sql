
    
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select payload_version_count
from `fraudguard_core`.`fct_transactions`
where payload_version_count is null



  
  
    ) dbt_internal_test