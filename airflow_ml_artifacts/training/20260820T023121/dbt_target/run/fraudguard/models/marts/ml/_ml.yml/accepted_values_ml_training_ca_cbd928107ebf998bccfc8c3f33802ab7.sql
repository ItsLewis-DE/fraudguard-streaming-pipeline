
    
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    

with all_values as (

    select
        destination_balance_before_is_zero as value_field,
        count(*) as n_records

    from `fraudguard_ml`.`ml_training_candidates`
    group by destination_balance_before_is_zero

)

select *
from all_values
where value_field not in (
    '0','1'
)



  
  
    ) dbt_internal_test