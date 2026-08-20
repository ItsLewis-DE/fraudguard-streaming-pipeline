
    
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select event_time
from `fraudguard_core`.`fct_transactions_labeled`
where event_time is null



  
  
    ) dbt_internal_test