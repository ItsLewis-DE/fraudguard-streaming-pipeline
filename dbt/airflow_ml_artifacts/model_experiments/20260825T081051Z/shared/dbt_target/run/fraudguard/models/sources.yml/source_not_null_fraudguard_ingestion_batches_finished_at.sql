
    
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select finished_at
from `fraudguard`.`ingestion_batches`
where finished_at is null



  
  
    ) dbt_internal_test