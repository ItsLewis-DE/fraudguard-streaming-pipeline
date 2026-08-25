
    
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select transaction_type
from `fraudguard_core`.`fct_transactions_labeled`
where transaction_type is null



  
  
    ) dbt_internal_test