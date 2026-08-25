
    
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    

with all_values as (

    select
        is_fraud as value_field,
        count(*) as n_records

    from `fraudguard_ml`.`ml_training_transactions`
    group by is_fraud

)

select *
from all_values
where value_field not in (
    '0','1'
)



  
  
    ) dbt_internal_test