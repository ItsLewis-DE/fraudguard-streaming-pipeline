
    
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select kafka_offset
from `fraudguard_staging`.`stg_transactions`
where kafka_offset is null



  
  
    ) dbt_internal_test