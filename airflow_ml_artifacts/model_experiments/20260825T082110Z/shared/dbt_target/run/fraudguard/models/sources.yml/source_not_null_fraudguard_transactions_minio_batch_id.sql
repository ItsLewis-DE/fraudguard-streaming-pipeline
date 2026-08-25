
    
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select minio_batch_id
from `fraudguard`.`transactions`
where minio_batch_id is null



  
  
    ) dbt_internal_test