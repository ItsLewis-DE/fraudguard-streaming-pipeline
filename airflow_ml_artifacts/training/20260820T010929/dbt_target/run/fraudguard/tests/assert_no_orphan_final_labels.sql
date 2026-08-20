
    
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  --Kiểm tra việc có trong label nhưng lại k có transaction
select
    l.source,
    l.event_id
from `fraudguard_core`.`fct_transaction_labels` as l
left join `fraudguard_core`.`fct_transactions` as t
    on l.source = t.source
   and l.event_id = t.event_id
where t.event_id = ''
  
  
    ) dbt_internal_test