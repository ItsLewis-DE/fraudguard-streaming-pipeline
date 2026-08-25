
    
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select event_id
from `fraudguard_staging`.`stg_transactions`
where event_id is null



  
  
    ) dbt_internal_test