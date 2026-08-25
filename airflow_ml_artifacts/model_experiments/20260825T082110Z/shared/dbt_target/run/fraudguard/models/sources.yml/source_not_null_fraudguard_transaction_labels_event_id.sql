
    
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select event_id
from `fraudguard`.`transaction_labels`
where event_id is null



  
  
    ) dbt_internal_test