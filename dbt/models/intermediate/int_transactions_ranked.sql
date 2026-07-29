--Tìm ra bản ghi chuẩn nhất (canonical) cho mỗi sự kiện (event), 
--đồng thời đếm xem sự kiện đó bị lặp lại bao nhiêu lần và có bao nhiêu phiên bản nội dung khác nhau
with committed_rows as ( --Để lấy bản ghi chuẩn nhất, trước tiên cần lọc ra các bản ghi đã được commit (committed) từ các batch ingestion thành công 
    select t.*
    from {{ ref('stg_transactions') }} t
    inner join {{ ref('int_committed_ingestion_batches') }} b
        on b.pipeline = 'transactions'
       and b.batch_id = t.minio_batch_id
),
prepared as (
    select
        *,
        cityHash64(
            event_time,
            step,
            transaction_type,
            amount,
            origin_account,
            origin_balance_before,
            origin_balance_after,
            destination_account,
            destination_balance_before,
            destination_balance_after
        ) as transaction_payload_hash
    from committed_rows
),
key_stats as (
    select
        source,
        event_id,
        count() as physical_row_count, --Đếm số bản ghi vật lý (physical) cho mỗi sự kiện (event)
        uniqExact(transaction_payload_hash) as payload_version_count --Đếm số phiên bản nội dung khác nhau (unique payload versions) cho mỗi sự kiện (event)
    from prepared
    group by source, event_id
),
--Bảng này để tìm rank cho mỗi source,event_id 
ranked as (
    select
        p.*,
        row_number() over (
            partition by p.source, p.event_id
            order by
                p.kafka_topic asc,
                p.kafka_partition asc,
                p.kafka_offset asc,
                p.minio_batch_id asc,
                p.minio_object asc,
                p.loaded_at asc,
                p.transaction_payload_hash asc
        ) as canonical_rank
    from prepared p
)

select
    r.*,
    s.physical_row_count,
    s.payload_version_count
from ranked r
inner join key_stats s
    on r.source = s.source
   and r.event_id = s.event_id