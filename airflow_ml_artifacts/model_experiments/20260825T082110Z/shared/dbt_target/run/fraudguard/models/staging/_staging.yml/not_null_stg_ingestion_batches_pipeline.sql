
    
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select pipeline
from `fraudguard_staging`.`stg_ingestion_batches`
where pipeline is null



  
  
    ) dbt_internal_test