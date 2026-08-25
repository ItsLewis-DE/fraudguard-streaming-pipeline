
    
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select success_attempt_count
from `fraudguard_intermediate`.`int_committed_ingestion_batches`
where success_attempt_count is null



  
  
    ) dbt_internal_test