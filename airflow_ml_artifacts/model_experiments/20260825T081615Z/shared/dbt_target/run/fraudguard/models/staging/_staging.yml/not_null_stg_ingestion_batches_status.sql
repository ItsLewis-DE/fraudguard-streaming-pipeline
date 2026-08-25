
    
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select status
from `fraudguard_staging`.`stg_ingestion_batches`
where status is null



  
  
    ) dbt_internal_test