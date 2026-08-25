
    
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  select
    'fct_transactions' as relation_name,
    source,
    event_id
from `fraudguard_core`.`fct_transactions`
where trim(source) = '' or trim(event_id) = ''

union all

select
    'fct_transaction_labels' as relation_name,
    source,
    event_id
from `fraudguard_core`.`fct_transaction_labels`
where trim(source) = '' or trim(event_id) = ''
  
  
    ) dbt_internal_test