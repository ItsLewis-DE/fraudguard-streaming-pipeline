
    
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select has_invalid_balance
from `fraudguard_core`.`fct_transactions`
where has_invalid_balance is null



  
  
    ) dbt_internal_test