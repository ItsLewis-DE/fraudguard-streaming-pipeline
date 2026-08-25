
    
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select committed_at
from `fraudguard_intermediate`.`int_committed_ingestion_batches`
where committed_at is null



  
  
    ) dbt_internal_test