
    
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select pipeline
from `fraudguard_intermediate`.`int_committed_ingestion_batches`
where pipeline is null



  
  
    ) dbt_internal_test