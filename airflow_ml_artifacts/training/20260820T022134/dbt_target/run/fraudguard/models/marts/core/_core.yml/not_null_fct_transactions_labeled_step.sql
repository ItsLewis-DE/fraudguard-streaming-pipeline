
    
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select step
from `fraudguard_core`.`fct_transactions_labeled`
where step is null



  
  
    ) dbt_internal_test