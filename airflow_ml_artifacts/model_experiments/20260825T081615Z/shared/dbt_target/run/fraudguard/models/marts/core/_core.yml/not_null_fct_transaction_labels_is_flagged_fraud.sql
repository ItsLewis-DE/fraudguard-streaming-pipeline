
    
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select is_flagged_fraud
from `fraudguard_core`.`fct_transaction_labels`
where is_flagged_fraud is null



  
  
    ) dbt_internal_test