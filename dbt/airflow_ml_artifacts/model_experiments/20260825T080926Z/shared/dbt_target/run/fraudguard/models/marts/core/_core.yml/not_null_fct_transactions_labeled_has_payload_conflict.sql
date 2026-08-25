
    
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select has_payload_conflict
from `fraudguard_core`.`fct_transactions_labeled`
where has_payload_conflict is null



  
  
    ) dbt_internal_test