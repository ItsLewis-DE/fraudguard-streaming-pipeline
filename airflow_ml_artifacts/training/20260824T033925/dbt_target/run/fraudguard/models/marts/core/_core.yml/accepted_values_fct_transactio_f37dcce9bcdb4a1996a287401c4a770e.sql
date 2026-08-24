
    
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    

with all_values as (

    select
        transaction_type as value_field,
        count(*) as n_records

    from `fraudguard_core`.`fct_transactions_labeled`
    group by transaction_type

)

select *
from all_values
where value_field not in (
    'CASH_IN','CASH_OUT','DEBIT','PAYMENT','TRANSFER'
)



  
  
    ) dbt_internal_test