# M1 — dbt canonical layer và data-quality gate

Tài liệu này là kế hoạch triển khai chi tiết cho FraudGuard trên stack hiện tại:
ClickHouse, dbt-clickhouse, Airflow, MinIO và dữ liệu PaySim synthetic. Mục tiêu
không chỉ là làm `dbt build` xanh, mà là tạo một ranh giới dữ liệu đủ rõ để ML
không vô tình học từ duplicate, label tương lai hoặc dữ liệu lỗi.

## 1. Kết quả cần đạt

Sau M1, pipeline phải có các tầng sau:

```text
ClickHouse ingestion tables
  transactions
  transaction_labels
  ingestion_batches
  ingestion_batch_quality       <- cần bổ sung để đếm quarantine đúng
          |
          v
dbt staging                     <- rename + cast, không có business logic
  stg_transactions
  stg_transaction_labels
  stg_ingestion_batches
  stg_ingestion_batch_quality
          |
          v
dbt canonical/intermediate
  int_transactions_ranked
  fct_transactions
  int_label_versions
  fct_transaction_labels_as_of  <- cutoff là input bắt buộc
  fct_transactions_labeled_as_of
          |
          v
dbt monitoring
  dq_reconciliation_daily
  dq_snapshot_gate
          |
          v
snapshot builder
  chạy critical dbt gate trước
  chỉ build snapshot khi gate pass
  ghi cutoff + dbt invocation/manifest vào metadata
```

### Grain bắt buộc

| Model | Grain | Khóa |
|---|---|---|
| `stg_transactions` | Một physical ingestion row | `(kafka_topic, kafka_partition, kafka_offset, minio_batch_id)` |
| `stg_transaction_labels` | Một physical label ingestion row | `(kafka_topic, kafka_partition, kafka_offset, minio_batch_id)` |
| `fct_transactions` | Đúng một transaction business event | `event_id` |
| `int_label_versions` | Một phiên bản label đã dedup | `(event_id, observed_at)` |
| `fct_transaction_labels_as_of` | Label mới nhất hợp lệ của event tại một cutoff | `event_id` |
| `fct_transactions_labeled_as_of` | Một transaction, có thể chưa có label | `event_id` |
| `dq_reconciliation_daily` | Một `event_date` và source | `(event_date, source)` |

`event_id` được xem là globally unique trong FraudGuard. Không âm thầm đổi grain
thành `(source, event_id)`: làm vậy có thể che lỗi producer tạo trùng ID giữa hai
source. `source` vẫn được giữ như dimension và dùng trong báo cáo.

## 2. Vì sao ML không train từ ingestion tables

Hai bảng `fraudguard.transactions` và `fraudguard.transaction_labels` dùng
`ReplacingMergeTree`. Engine này không đảm bảo query thường luôn thấy đúng một
row ngay sau insert; merge chạy bất đồng bộ. Dùng `FINAL` có thể ép merge khi
đọc nhưng tốn tài nguyên và vẫn không định nghĩa rõ row thắng khi version/tie
không đủ chặt.

Train trực tiếp từ raw ingestion còn có bốn rủi ro:

1. Retry hoặc replay làm một `event_id` xuất hiện nhiều lần, khiến một giao dịch
   có trọng số lớn hơn giao dịch khác trong training.
2. Join nhiều label version vào một transaction làm tăng grain.
3. Chọn label mới nhất toàn lịch sử đưa label tương lai vào snapshot quá khứ.
4. Dữ liệu amount/balance lỗi có thể bị cast hoặc lọc mà không để lại bằng chứng.

Canonical layer phải biến các quy tắc trên thành code, test và metadata có thể
audit; model training chỉ được đọc từ snapshot do layer này tạo.

## 3. Các quyết định thiết kế

### 3.1 Staging chỉ chuẩn hóa contract

Staging được phép:

- rename tên PaySim sang `snake_case`;
- cast về type ổn định;
- giữ nguyên lineage như topic/partition/offset, batch và object;
- thêm metadata kỹ thuật như `_dbt_loaded_at`.

Staging không được:

- dedup;
- join transaction với label;
- lọc row “xấu”;
- tính label maturity;
- sửa balance hoặc amount;
- chọn label version.

Quy tắc này giúp phân biệt lỗi source/ingestion với quyết định nghiệp vụ.

### 3.2 Dedup transaction phải deterministic

Row thắng cho mỗi `event_id` được chọn theo thứ tự giảm dần:

```text
ingested_at
minio_batch_id
loaded_at
kafka_topic
kafka_partition
kafka_offset
```

Kafka coordinates là tie-breaker cuối, không phải business freshness. Nếu hai row
cùng `event_id` nhưng payload nghiệp vụ khác nhau, canonical vẫn cần chọn đúng
một row để giữ grain, đồng thời gắn `has_conflicting_duplicate = true` và làm
critical test fail. Không được âm thầm coi conflict là retry vô hại.

### 3.3 Label là versioned fact và phải join as-of

Ba thời điểm phải được tách rõ:

- `event_time`: giao dịch xảy ra khi nào;
- `observed_at`: label trở nên có thể quan sát khi nào;
- `snapshot_cutoff`: dữ liệu nào được phép tồn tại trong snapshot.

Một label hợp lệ tại cutoff khi:

```text
observed_at >= event_time
AND observed_at <= snapshot_cutoff
AND is_fraud IN (0, 1)
```

Với mỗi `event_id`, chọn label có `observed_at` lớn nhất trong tập hợp hợp lệ.
Nếu có correction cùng `observed_at`, dùng lineage ingestion làm tie-breaker.

Không dùng `now()` làm cutoff. Cutoff phải được truyền rõ bằng dbt var ở UTC:

```bash
./scripts/dbt.sh build \
  --vars '{"snapshot_cutoff": "2026-02-01 00:00:00", "label_maturity_hours": 24}'
```

Nếu thiếu `snapshot_cutoff`, compile phải fail thay vì tự dùng thời gian hiện tại.

### 3.4 DQ flag không thay cho quarantine

Quarantine xử lý record không thể tin cậy hoặc không thể decode ở Spark. DQ flag
đánh dấu record đã qua ingest nhưng có giá trị đáng ngờ ở canonical. Hai khái
niệm này không được trộn:

- malformed Avro, schema ID sai, thiếu `event_time`: quarantine;
- amount âm hoặc balance âm nhưng record vẫn parse được: canonical row + DQ flag;
- duplicate payload giống nhau: dedup + count;
- duplicate payload xung đột: dedup để bảo toàn grain + critical failure.

## 4. Khoảng trống hiện tại cần xử lý trước

`fraudguard.ingestion_batches.source_rows` hiện được Airflow đếm từ bucket valid
và vì thế thực chất là `valid_rows`, không phải tổng input. Quarantine được Spark
ghi sang bucket riêng nhưng chưa có bảng audit trong ClickHouse. Do đó công thức:

```text
input_rows = valid_rows + quarantine_rows
```

chưa thể reconcile bằng dữ liệu hiện có.

### Thay đổi audit contract tối thiểu

Nên làm ngay trong M1: thêm một manifest append/replacing-safe, do Spark ghi cho
mỗi micro-batch và Airflow nạp vào ClickHouse.

```sql
CREATE TABLE IF NOT EXISTS fraudguard.ingestion_batch_quality
(
    pipeline          LowCardinality(String),
    batch_id          UInt64,
    event_date        Nullable(Date),
    source             LowCardinality(String),
    input_rows        UInt64,
    valid_rows        UInt64,
    quarantine_rows   UInt64,
    duplicate_rows    UInt64 DEFAULT 0,
    recorded_at       DateTime64(3, 'UTC')
)
ENGINE = ReplacingMergeTree(recorded_at)
ORDER BY (
    pipeline,
    batch_id,
    ifNull(event_date, toDate('1970-01-01')),
    source
);
```

Nếu một batch chứa nhiều `event_date`, ghi một row cho mỗi event date. Record
quarantine không thể xác định event time dùng `event_date = NULL` và được báo
cáo trong bucket `unknown_event_date`, không được gán processing date giả làm
business event date. Nếu cần breakdown theo `error_code`, tạo bảng phụ
`quarantine_reason_counts`; không lặp lại tổng `input_rows` ở mỗi error code vì
sẽ làm reconciliation double-count.

Invariant của manifest:

```text
sum(input_rows) = sum(valid_rows) + sum(quarantine_rows)
```

Migration an toàn:

1. Tạo bảng mới, không sửa nghĩa cột cũ.
2. Spark dual-write `_SUCCESS` và quality manifest.
3. Airflow nạp manifest idempotently theo `(pipeline, batch_id, event_date,
   source)`.
4. Reconcile vài batch local.
5. Sau đó mới bật critical gate dùng quarantine count.

Không rename `source_rows` ngay vì có thể phá code Airflow đang chạy. Có thể
deprecate cột này sau M1 khi mọi consumer đã chuyển sang manifest mới.

## 5. Cấu trúc file đề xuất

```text
dbt/
├── macros/
│   ├── require_snapshot_cutoff.sql
│   └── source_relation.sql
├── models/
│   ├── sources.yml
│   ├── staging/
│   │   ├── _staging.yml
│   │   ├── stg_transactions.sql
│   │   ├── stg_transaction_labels.sql
│   │   ├── stg_ingestion_batches.sql
│   │   └── stg_ingestion_batch_quality.sql
│   ├── intermediate/
│   │   ├── _intermediate.yml
│   │   ├── int_transactions_ranked.sql
│   │   └── int_label_versions.sql
│   ├── marts/
│   │   ├── _marts.yml
│   │   ├── fct_transactions.sql
│   │   ├── fct_transaction_labels_as_of.sql
│   │   └── fct_transactions_labeled_as_of.sql
│   └── monitoring/
│       ├── _monitoring.yml
│       ├── dq_reconciliation_daily.sql
│       └── dq_snapshot_gate.sql
├── seeds/
│   ├── fixture_transactions.csv
│   ├── fixture_transaction_labels.csv
│   ├── fixture_ingestion_batches.csv
│   └── fixture_ingestion_batch_quality.csv
└── tests/
    ├── assert_balance_or_flagged.sql
    ├── assert_duplicate_payload_consistent.sql
    ├── assert_join_preserves_transaction_grain.sql
    ├── assert_mature_transactions_have_label.sql
    ├── assert_no_future_label_at_cutoff.sql
    ├── assert_no_orphan_labels.sql
    ├── assert_observed_at_not_before_event.sql
    └── assert_reconciliation_balances.sql

ml/src/fraudguard_ml/
└── snapshot_builder.py
```

Tên model có thể điều chỉnh, nhưng grain và ranh giới trách nhiệm không nên đổi.

## 6. Source và freshness

Cập nhật `dbt/models/sources.yml`:

```yaml
version: 2

sources:
  - name: fraudguard
    description: >
      Physical ingestion tables loaded from completed MinIO batches. These
      relations are not safe as direct ML training inputs.
    schema: "{{ env_var('DBT_CLICKHOUSE_DATABASE', 'fraudguard') }}"
    config:
      freshness:
        warn_after: {count: 30, period: minute}
        error_after: {count: 2, period: hour}
      loaded_at_field: loaded_at
    meta:
      owner: fraud-platform
      contract_version: 1
    tables:
      - name: transactions
        description: Physical transaction ingestion rows; duplicates are allowed.
      - name: transaction_labels
        description: Versioned delayed-label ingestion rows.
      - name: ingestion_batches
        description: Airflow valid-batch load status.
        config:
          freshness: null
      - name: ingestion_batch_quality
        description: Spark batch reconciliation counts including quarantine.
        config:
          freshness: null
```

Lưu ý: `transaction_labels` hiện không có cột `loaded_at` trong Avro nhưng có ở
ClickHouse, nên freshness dùng được sau khi Airflow load. `ingestion_batches`
không cùng contract cột với event tables; kiểm tra freshness riêng bằng
`finished_at` nếu cần.

Mỗi model YAML phải có:

- description nêu grain;
- `meta.owner`;
- `meta.grain`;
- contract/version hoặc link tới Avro contract;
- ý nghĩa event time, observation time và cutoff;
- freshness SLA nếu model có vai trò vận hành;
- mô tả từng DQ flag.

## 7. Staging models

### `stg_transactions.sql`

Trong fixture mode dùng seed; bình thường dùng source. Cách này cho phép
`dbt build` chạy deterministic mà không cần replay toàn PaySim.

```sql
with source_rows as (
    {% if var('use_fixtures', false) %}
        select * from {{ ref('fixture_transactions') }}
    {% else %}
        select * from {{ source('fraudguard', 'transactions') }}
    {% endif %}
)

select
    toString(event_id) as event_id,
    toString(source) as source,
    toDateTime64(event_time, 3, 'UTC') as event_time,
    toDateTime64(ingested_at, 3, 'UTC') as ingested_at,
    toUInt16(step) as step,
    toString(transaction_type) as transaction_type,
    toDecimal64(amount, 2) as amount,
    toString(origin_account) as origin_account,
    toDecimal64(origin_balance_before, 2) as origin_balance_before,
    toDecimal64(origin_balance_after, 2) as origin_balance_after,
    toString(destination_account) as destination_account,
    toDecimal64(destination_balance_before, 2) as destination_balance_before,
    toDecimal64(destination_balance_after, 2) as destination_balance_after,
    toUInt32(schema_id) as schema_id,
    toString(kafka_topic) as kafka_topic,
    toUInt16(kafka_partition) as kafka_partition,
    toUInt64(kafka_offset) as kafka_offset,
    toDateTime64(kafka_timestamp, 3, 'UTC') as kafka_timestamp,
    toUInt64(minio_batch_id) as minio_batch_id,
    toString(minio_object) as minio_object,
    toDateTime64(loaded_at, 3, 'UTC') as loaded_at
from source_rows
```

Không dùng `FINAL` ở staging. Ta cần nhìn thấy physical duplicates để đo retry và
kiểm chứng dedup semantics.

### `stg_transaction_labels.sql`

```sql
with source_rows as (
    {% if var('use_fixtures', false) %}
        select * from {{ ref('fixture_transaction_labels') }}
    {% else %}
        select * from {{ source('fraudguard', 'transaction_labels') }}
    {% endif %}
)

select
    toString(event_id) as event_id,
    toString(source) as source,
    toDateTime64(observed_at, 3, 'UTC') as observed_at,
    toUInt8(is_fraud) as is_fraud,
    toUInt8(is_flagged_fraud) as is_flagged_fraud,
    toUInt32(schema_id) as schema_id,
    toString(kafka_topic) as kafka_topic,
    toUInt16(kafka_partition) as kafka_partition,
    toUInt64(kafka_offset) as kafka_offset,
    toDateTime64(kafka_timestamp, 3, 'UTC') as kafka_timestamp,
    toUInt64(minio_batch_id) as minio_batch_id,
    toString(minio_object) as minio_object,
    toDateTime64(loaded_at, 3, 'UTC') as loaded_at
from source_rows
```

Nếu seed CSV không suy luận đúng type, khai báo `column_types` trong
`dbt/seeds/properties.yml`. Không thêm `coalesce` để biến null thành giá trị hợp
lệ; null phải bị test bắt.

## 8. Canonical transaction

### `int_transactions_ranked.sql`

Tạo payload fingerprint để phân biệt exact retry và conflicting duplicate:

```sql
with prepared as (
    select
        *,
        cityHash64(
            source,
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
        ) as payload_hash
    from {{ ref('stg_transactions') }}
),
ranked as (
    select
        *,
        row_number() over (
            partition by event_id
            order by
                ingested_at desc,
                minio_batch_id desc,
                loaded_at desc,
                kafka_topic desc,
                kafka_partition desc,
                kafka_offset desc
        ) as canonical_rank,
        count() over (partition by event_id) as source_row_count,
        uniqExact(payload_hash) over (partition by event_id) as payload_version_count
    from prepared
)
select * from ranked
```

Nếu phiên bản ClickHouse không hỗ trợ `uniqExact(...) over`, tách phần count:

```sql
select
    event_id,
    count() as source_row_count,
    uniqExact(payload_hash) as payload_version_count
from prepared
group by event_id
```

rồi join lại vào ranked. Kiểm tra cú pháp bằng `./scripts/dbt.sh parse` và build
fixture trước khi dùng biến thể window.

### `fct_transactions.sql`

```sql
select
    event_id,
    source,
    event_time,
    toDate(event_time) as event_date,
    ingested_at,
    step,
    transaction_type,
    amount,
    origin_account,
    origin_balance_before,
    origin_balance_after,
    destination_account,
    destination_balance_before,
    destination_balance_after,
    schema_id,
    kafka_topic,
    kafka_partition,
    kafka_offset,
    minio_batch_id,
    minio_object,
    loaded_at,
    source_row_count,
    source_row_count - 1 as duplicate_row_count,
    payload_version_count > 1 as has_conflicting_duplicate,
    amount < 0 as has_invalid_amount,
    (
        origin_balance_before < 0
        or origin_balance_after < 0
        or destination_balance_before < 0
        or destination_balance_after < 0
    ) as has_invalid_balance,
    not (
        has_conflicting_duplicate
        or has_invalid_amount
        or has_invalid_balance
    ) as is_dq_valid
from {{ ref('int_transactions_ranked') }}
where canonical_rank = 1
```

Không áp đặt phương trình balance kiểu
`before - amount = after` như một critical rule cho mọi PaySim transaction.
Semantics thay đổi theo transaction type và PaySim có hành vi synthetic đặc thù.
Nếu muốn kiểm tra phương trình này, trước hết phân tích theo type và đưa thành
warning/monitor, không làm rơi row.

## 9. Canonical label version và as-of model

### `int_label_versions.sql`

Dedup exact replay tại cùng `(event_id, observed_at)` nhưng giữ các correction ở
thời điểm khác nhau:

```sql
with ranked as (
    select
        l.*,
        t.event_time,
        row_number() over (
            partition by l.event_id, l.observed_at
            order by
                l.minio_batch_id desc,
                l.loaded_at desc,
                l.kafka_topic desc,
                l.kafka_partition desc,
                l.kafka_offset desc
        ) as version_rank,
        count() over (
            partition by l.event_id, l.observed_at
        ) as source_row_count
    from {{ ref('stg_transaction_labels') }} l
    left join {{ ref('fct_transactions') }} t using (event_id)
)
select
    *,
    event_time is not null as has_transaction,
    observed_at >= event_time as is_temporally_valid,
    is_fraud in (0, 1) as is_value_valid
from ranked
where version_rank = 1
```

Nếu hai correction có cùng `observed_at` nhưng khác `is_fraud`, đó là conflict
contract và phải có test critical riêng; tie-breaker chỉ giữ grain, không biến
conflict thành dữ liệu đáng tin.

### Macro cutoff bắt buộc

`dbt/macros/require_snapshot_cutoff.sql`:

```sql
{% macro snapshot_cutoff_sql() %}
  {% set cutoff = var('snapshot_cutoff', none) %}
  {% if cutoff is none %}
    {{ exceptions.raise_compiler_error(
      "snapshot_cutoff is required; pass an explicit UTC timestamp"
    ) }}
  {% endif %}
  toDateTime64('{{ cutoff }}', 3, 'UTC')
{% endmacro %}
```

### `fct_transaction_labels_as_of.sql`

```sql
with eligible as (
    select *
    from {{ ref('int_label_versions') }}
    where
        has_transaction
        and is_temporally_valid
        and is_value_valid
        and observed_at <= {{ snapshot_cutoff_sql() }}
),
ranked as (
    select
        *,
        row_number() over (
            partition by event_id
            order by
                observed_at desc,
                minio_batch_id desc,
                loaded_at desc,
                kafka_partition desc,
                kafka_offset desc
        ) as as_of_rank
    from eligible
)
select
    event_id,
    observed_at,
    is_fraud,
    is_flagged_fraud,
    schema_id as label_schema_id,
    {{ snapshot_cutoff_sql() }} as snapshot_cutoff
from ranked
where as_of_rank = 1
```

Model này không nên là một bảng dùng chung bị overwrite bởi nhiều cutoff đồng
thời. Cho M1 local, có hai hướng:

- đơn giản: materialize `ephemeral` hoặc `view` và snapshot builder chạy tuần tự;
- bền vững hơn: materialize snapshot theo `snapshot_id`/cutoff, không overwrite.

Khuyến nghị M1 là `ephemeral` để giảm state. Khi có concurrent training runs,
chuyển sang bảng versioned theo `snapshot_id`.

### `fct_transactions_labeled_as_of.sql`

Phải dùng left join để giữ transaction chưa mature/chưa có label:

```sql
select
    t.*,
    l.observed_at as label_observed_at,
    l.is_fraud,
    l.is_flagged_fraud,
    l.snapshot_cutoff,
    l.event_id is not null as has_observed_label
from {{ ref('fct_transactions') }} t
left join {{ ref('fct_transaction_labels_as_of') }} l using (event_id)
where t.event_time <= {{ snapshot_cutoff_sql() }}
```

Snapshot train sau đó chỉ chọn row đã mature và có label. Không biến missing
label thành `is_fraud = 0`. Điều kiện trên cũng ngăn transaction tương lai lọt
vào snapshot; chỉ chặn future label là chưa đủ để đảm bảo point-in-time
correctness.

## 10. Tests bắt buộc

Mọi test critical cần:

```yaml
config:
  severity: error
  tags: ["snapshot_gate", "critical_dq"]
```

### 10.1 Unique và not-null transaction

Trong `_marts.yml`:

```yaml
models:
  - name: fct_transactions
    description: Canonical transaction, exactly one row per event_id.
    meta:
      owner: fraud-platform
      grain: event_id
    columns:
      - name: event_id
        description: Globally unique immutable transaction identifier.
        data_tests:
          - not_null:
              config:
                tags: ["snapshot_gate", "critical_dq"]
          - unique:
              config:
                tags: ["snapshot_gate", "critical_dq"]
```

### 10.2 `is_fraud` chỉ nhận 0/1

```yaml
  - name: int_label_versions
    columns:
      - name: is_fraud
        data_tests:
          - not_null:
              config:
                tags: ["snapshot_gate", "critical_dq"]
          - accepted_values:
              arguments:
                values: [0, 1]
                quote: false
              config:
                tags: ["snapshot_gate", "critical_dq"]
```

Không chỉ test model as-of vì label lỗi có thể đã bị filter khỏi model đó và trở
thành “vô hình”.

### 10.3 `observed_at >= event_time`

`tests/assert_observed_at_not_before_event.sql`:

```sql
select
    event_id,
    event_time,
    observed_at
from {{ ref('int_label_versions') }}
where has_transaction and observed_at < event_time
```

Test singular pass khi query trả về 0 row.

### 10.4 Orphan label và mature transaction thiếu label

Hai failure mode khác nhau, nên tách hai test.

`tests/assert_no_orphan_labels.sql`:

```sql
select event_id, observed_at
from {{ ref('int_label_versions') }}
where not has_transaction
```

`tests/assert_mature_transactions_have_label.sql`:

```sql
select
    t.event_id,
    t.event_time
from {{ ref('fct_transactions') }} t
left join {{ ref('fct_transaction_labels_as_of') }} l using (event_id)
where
    t.event_time <= (
        {{ snapshot_cutoff_sql() }}
        - toIntervalHour({{ var('label_maturity_hours', 24) }})
    )
    and l.event_id is null
```

`label_maturity_hours = 24` là giả định local ban đầu, không phải sự thật phổ
quát. Đưa vào config, document owner và điều chỉnh dựa trên distribution thực tế
của `observed_at - event_time`.

### 10.5 Amount/balance hợp lệ hoặc được flag

`tests/assert_balance_or_flagged.sql`:

```sql
select event_id
from {{ ref('fct_transactions') }}
where
    (amount < 0 and not has_invalid_amount)
    or (
        (
            origin_balance_before < 0
            or origin_balance_after < 0
            or destination_balance_before < 0
            or destination_balance_after < 0
        )
        and not has_invalid_balance
    )
```

Thêm test đối xứng để tránh flag sai:

```sql
select event_id
from {{ ref('fct_transactions') }}
where
    (amount >= 0 and has_invalid_amount)
    or (
        origin_balance_before >= 0
        and origin_balance_after >= 0
        and destination_balance_before >= 0
        and destination_balance_after >= 0
        and has_invalid_balance
    )
```

### 10.6 Join không tăng transaction grain

`tests/assert_join_preserves_transaction_grain.sql`:

```sql
with counts as (
    select
        (
            select count()
            from {{ ref('fct_transactions') }}
            where event_time <= {{ snapshot_cutoff_sql() }}
        ) as transaction_rows,
        (
            select count()
            from {{ ref('fct_transactions_labeled_as_of') }}
        ) as joined_rows,
        (
            select uniqExact(event_id)
            from {{ ref('fct_transactions_labeled_as_of') }}
        ) as joined_event_ids
)
select *
from counts
where
    joined_rows != transaction_rows
    or joined_event_ids != transaction_rows
```

Test row count một mình chưa đủ; một duplicate cộng với một missing row có thể
làm tổng count không đổi. Phải kiểm cả `uniqExact(event_id)`.

### 10.7 Không có future label tại cutoff

`tests/assert_no_future_label_at_cutoff.sql`:

```sql
select event_id, observed_at, snapshot_cutoff
from {{ ref('fct_transaction_labels_as_of') }}
where observed_at > snapshot_cutoff
```

Fixture phải có ít nhất một event với hai label:

- version `0` quan sát trước cutoff;
- correction `1` quan sát sau cutoff.

Expected as-of label ở cutoff quá khứ phải là `0`, không phải `1`.

### 10.8 Duplicate payload conflict

`tests/assert_duplicate_payload_consistent.sql`:

```sql
select event_id, source_row_count, payload_version_count
from {{ ref('fct_transactions') }}
where has_conflicting_duplicate
```

Exact retry được phép và được báo cáo; conflicting duplicate là critical vì chưa
thể biết transaction nào đúng.

### 10.9 Reconciliation cân bằng

`tests/assert_reconciliation_balances.sql`:

```sql
select *
from {{ ref('dq_reconciliation_daily') }}
where
    input_rows != valid_rows + quarantine_rows
    or canonical_rows > valid_rows
    or duplicate_rows != valid_rows - canonical_rows
```

Nếu manifest chưa có, test phải fail hoặc model phải được đánh dấu blocked.
Không dùng `coalesce(quarantine_rows, 0)` để giả vờ pipeline không có quarantine.

## 11. Reconciliation và DQ summary

`dq_reconciliation_daily` cần tối thiểu các cột:

```text
event_date
source
input_rows
valid_rows
quarantine_rows
canonical_rows
duplicate_rows
null_event_id_rows
conflicting_duplicate_events
invalid_amount_rows
invalid_balance_rows
label_observed_rows
mature_transaction_rows
mature_labeled_rows
label_coverage_rate
snapshot_cutoff
calculated_at
```

Định nghĩa:

```text
duplicate_rows = valid transaction rows - canonical transaction rows
label_coverage_rate =
    mature_labeled_rows / nullIf(mature_transaction_rows, 0)
```

`label_coverage_rate` phải tính theo event-time cohort và maturity, không lấy tất
cả transaction gần cutoff vào mẫu số. Nếu không, dashboard sẽ báo coverage thấp
chỉ vì label chưa đủ thời gian đến.

Skeleton:

```sql
with raw_tx as (
    select
        toDate(event_time) as event_date,
        source,
        count() as valid_rows,
        countIf(event_id = '') as null_event_id_rows
    from {{ ref('stg_transactions') }}
    group by event_date, source
),
canonical_tx as (
    select
        event_date,
        source,
        count() as canonical_rows,
        sum(duplicate_row_count) as duplicate_rows,
        countIf(has_conflicting_duplicate) as conflicting_duplicate_events,
        countIf(has_invalid_amount) as invalid_amount_rows,
        countIf(has_invalid_balance) as invalid_balance_rows
    from {{ ref('fct_transactions') }}
    group by event_date, source
),
quality_manifest as (
    select
        event_date,
        sum(input_rows) as input_rows,
        sum(valid_rows) as manifest_valid_rows,
        sum(quarantine_rows) as quarantine_rows
    from {{ ref('stg_ingestion_batch_quality') }}
    where pipeline = 'transactions'
    group by event_date
)
select
    r.event_date,
    r.source,
    q.input_rows,
    r.valid_rows,
    q.quarantine_rows,
    c.canonical_rows,
    c.duplicate_rows,
    r.null_event_id_rows,
    c.conflicting_duplicate_events,
    c.invalid_amount_rows,
    c.invalid_balance_rows
    -- Join thêm mature label aggregates ở đây.
from raw_tx r
left join canonical_tx c using (event_date, source)
left join quality_manifest q using (event_date)
```

Nếu quality manifest không có `source`, cần đảm bảo mỗi pipeline chỉ có một
source hoặc bổ sung `source` vào contract. Với dự án có nhiều source, khuyến nghị
bổ sung ngay để reconciliation không phân bổ sai count.

`dq_snapshot_gate` là summary một row cho cutoff hiện tại:

```text
critical_failure_count
reconciliation_gap_rows
conflicting_duplicate_events
orphan_label_rows
future_label_rows
mature_unlabeled_rows
is_snapshot_safe
```

`is_snapshot_safe` chỉ true khi mọi critical count bằng 0. Model này phục vụ
quan sát; dbt tests mới là cơ chế khiến command trả exit code khác 0.

## 12. Fixture tối thiểu

Fixture phải nhỏ nhưng chứa đủ failure mode, không chỉ happy path.

| Event | Nội dung | Mục đích |
|---|---|---|
| `evt-001` | Một transaction, label trước cutoff | Happy path |
| `evt-002` | Hai physical rows payload giống nhau | Exact retry/dedup |
| `evt-003` | Label `0` trước cutoff, correction `1` sau cutoff | As-of leakage guard |
| `evt-004` | Transaction mới, chưa mature, chưa có label | Không fail maturity test |
| `evt-005` | Amount âm và flag tương ứng | DQ flag |
| `evt-006` | Hai duplicate payload khác nhau | Negative fixture cho critical test |
| `evt-orphan` | Label không có transaction | Negative fixture cho orphan test |

Nên tách:

- `fixture_*_valid.csv`: build phải pass;
- `fixture_*_invalid.csv`: dùng trong test riêng và phải chứng minh gate fail.

Không để invalid fixture trong default `dbt build` nếu mục tiêu command đó là
green. Có thể dùng biến `fixture_scenario: valid|invalid_future|invalid_orphan`
hoặc các CI job riêng.

Acceptance test quan trọng nhất cho leakage:

```text
cutoff A trước correction  -> evt-003.is_fraud = 0
cutoff B sau correction    -> evt-003.is_fraud = 1
```

## 13. Snapshot quality gate

Chỉ đặt dbt trước snapshot trong một shell script là chưa đủ vì người dùng có
thể gọi Python builder trực tiếp. Builder phải tự chạy gate hoặc yêu cầu một gate
artifact mới, khớp đúng cutoff và dataset identity.

Khuyến nghị đơn giản cho M1: builder tự gọi dbt.

```python
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class DataQualityGateError(RuntimeError):
    """Raised when canonical data is unsafe for snapshot creation."""


@dataclass(frozen=True)
class DbtGateResult:
    invocation_id: str
    manifest_path: Path
    run_results_path: Path


def run_dbt_quality_gate(
    *,
    project_root: Path,
    snapshot_cutoff: datetime,
    label_maturity_hours: int,
) -> DbtGateResult:
    if snapshot_cutoff.tzinfo is None:
        raise ValueError("snapshot_cutoff must be timezone-aware")

    cutoff_utc = snapshot_cutoff.astimezone(timezone.utc)
    dbt_vars = json.dumps(
        {
            "snapshot_cutoff": cutoff_utc.strftime("%Y-%m-%d %H:%M:%S"),
            "label_maturity_hours": label_maturity_hours,
        }
    )
    command = [
        str(project_root / "scripts" / "dbt.sh"),
        "build",
        "--select",
        "+tag:snapshot_gate",
        "--vars",
        dbt_vars,
    ]
    completed = subprocess.run(
        command,
        cwd=project_root,
        check=False,
        text=True,
        capture_output=True,
    )
    if completed.returncode != 0:
        raise DataQualityGateError(
            "Critical dbt data-quality gate failed; snapshot was not created.\n"
            f"{completed.stdout[-4000:]}\n{completed.stderr[-4000:]}"
        )

    target = project_root / "dbt" / "target"
    run_results_path = target / "run_results.json"
    manifest_path = target / "manifest.json"
    run_results: dict[str, Any] = json.loads(
        run_results_path.read_text(encoding="utf-8")
    )
    return DbtGateResult(
        invocation_id=str(run_results["metadata"]["invocation_id"]),
        manifest_path=manifest_path,
        run_results_path=run_results_path,
    )
```

Sau gate, builder:

1. Query canonical model với đúng `snapshot_cutoff`.
2. Ghi data ra temporary path.
3. Validate row count, unique `event_id`, schema và cutoff một lần nữa.
4. Atomic rename/move sang snapshot path cuối.
5. Ghi metadata:
   - snapshot ID;
   - cutoff UTC;
   - label maturity;
   - source batch IDs/hash;
   - dbt invocation ID;
   - hash của `manifest.json`;
   - Git SHA;
   - row count và label distribution.

Nếu bước nào fail, không publish partial snapshot. Temporary output phải được
cleanup hoặc quarantine để debug.

Không log credential ClickHouse. `capture_output` chỉ được đưa phần đuôi lỗi vào
exception; kiểm tra để dbt log không in secret.

## 14. Tags và model selection

Trong `dbt_project.yml`, bổ sung tags theo trách nhiệm:

```yaml
models:
  fraudguard:
    staging:
      +schema: staging
      +materialized: view
      +tags: ["staging"]
    intermediate:
      +schema: intermediate
      +materialized: view
      +tags: ["canonical", "snapshot_gate"]
    marts:
      +schema: mart
      +materialized: table
      +tags: ["canonical", "snapshot_gate"]
    monitoring:
      +schema: monitoring
      +materialized: table
      +tags: ["monitoring", "snapshot_gate"]
```

Không tag mọi test là critical. Ví dụ freshness warning hoặc balance heuristic
có thể là warning. Các test liên quan grain, future label, invalid label,
conflicting duplicate và reconciliation phải là error.

## 15. Trình tự triển khai đề xuất

### Bước 1 — Chốt contract và audit gap

1. Document grain của ba bảng hiện tại.
2. Thêm `ingestion_batch_quality`.
3. Spark tạo batch quality manifest.
4. Airflow load manifest idempotently.
5. Reconcile `input = valid + quarantine` trên 2–3 local batches.

**Done khi:** retry cùng batch không tăng count logic và quarantine count không
còn phải suy đoán.

### Bước 2 — Staging

1. Tạo bốn staging model.
2. Giữ toàn bộ lineage.
3. Thêm YAML descriptions/owner/grain.
4. Chạy `dbt parse` và staging build.

**Done khi:** staging row count bằng source physical row count.

### Bước 3 — Canonical transaction

1. Payload hash.
2. Deterministic ranking.
3. Exact duplicate count.
4. Conflict và amount/balance flags.
5. Unique/not-null/conflict tests.

**Done khi:** đúng một row/event và duplicate có thể trace về source rows.

### Bước 4 — Delayed labels

1. Dedupe label versions.
2. Join event time để đánh temporal validity.
3. Tạo cutoff macro bắt buộc.
4. Tạo label as-of và left join transaction-label.
5. Test hai cutoff trên correction fixture.

**Done khi:** cutoff quá khứ không bao giờ thấy correction tương lai.

### Bước 5 — Reconciliation và maturity

1. Aggregate theo event date.
2. Thêm label coverage chỉ trên mature cohort.
3. Tách orphan label và mature-unlabeled.
4. Tạo `dq_snapshot_gate`.

**Done khi:** report giải thích được source, canonical, duplicate, quarantine,
null và label coverage.

### Bước 6 — Snapshot builder gate

1. Builder chạy `dbt build --select +tag:snapshot_gate`.
2. Fail closed nếu dbt exit khác 0.
3. Không publish partial snapshot.
4. Ghi dbt/Git/data lineage vào metadata.
5. Regression test mock dbt failure và xác nhận writer không được gọi.

**Done khi:** không có đường code nào publish snapshot sau critical failure.

## 16. Lệnh kiểm chứng

Không cần service:

```bash
./scripts/dbt.sh parse
```

Với ClickHouse local và valid fixture:

```bash
./scripts/dbt.sh seed --full-refresh

./scripts/dbt.sh build \
  --vars '{
    "use_fixtures": true,
    "fixture_scenario": "valid",
    "snapshot_cutoff": "2026-02-01 00:00:00",
    "label_maturity_hours": 24
  }'
```

Data-quality gate:

```bash
./scripts/dbt.sh build \
  --select '+tag:snapshot_gate' \
  --vars '{
    "use_fixtures": true,
    "snapshot_cutoff": "2026-02-01 00:00:00",
    "label_maturity_hours": 24
  }'
```

Source freshness:

```bash
./scripts/dbt.sh source freshness
```

Local data:

```bash
./scripts/dbt.sh build \
  --vars '{
    "use_fixtures": false,
    "snapshot_cutoff": "2026-02-01 00:00:00",
    "label_maturity_hours": 24
  }'
```

Các lệnh cần service chỉ chạy sau khi ClickHouse healthy. Nếu Docker CLI chưa
có trong WSL, sửa Docker Desktop WSL integration trước; đó là prerequisite môi
trường, không nên sửa SQL để né lỗi kết nối.

## 17. Checklist review

### Correctness

- [ ] `fct_transactions` unique và not null theo `event_id`.
- [ ] Dedup order có tie-breaker deterministic.
- [ ] Conflicting duplicate làm gate fail.
- [ ] `is_fraud` chỉ là 0/1 và không coalesce missing label thành 0.
- [ ] `observed_at >= event_time`.
- [ ] Mọi as-of query có `observed_at <= snapshot_cutoff`.
- [ ] Join giữ cả row count lẫn distinct `event_id`.
- [ ] Maturity window là config, có owner và định nghĩa.

### Reconciliation

- [ ] Có `input_rows`, `valid_rows`, `quarantine_rows`.
- [ ] `input = valid + quarantine`.
- [ ] `duplicate = valid - canonical`.
- [ ] Report theo `event_date`, không theo processing date.
- [ ] Label coverage chỉ dùng mature event-time cohort.

### Reproducibility và vận hành

- [ ] Fixture valid build pass.
- [ ] Negative fixture chứng minh từng critical test fail.
- [ ] Snapshot builder fail closed khi dbt fail.
- [ ] Snapshot metadata chứa cutoff, maturity, dbt invocation, manifest hash,
      Git SHA và source batch lineage.
- [ ] Không dùng test set để chọn cutoff, feature hoặc threshold.
- [ ] Không đưa secret, dbt target/log hoặc generated snapshot vào Git.

## 18. Definition of Done cho M1

M1 chỉ hoàn thành khi có bằng chứng cho cả bốn nhóm:

1. `dbt build` pass trên valid fixture.
2. `dbt build` pass trên local dataset với cutoff cố định.
3. Báo cáo theo event date reconcile được raw/valid, canonical, duplicate,
   quarantine, null và mature-label coverage.
4. Một critical negative fixture làm dbt fail và snapshot builder xác nhận không
   tạo/publish snapshot.

Nếu chưa có `ingestion_batch_quality`, có thể hoàn thành staging và canonical
logic, nhưng chưa được đánh dấu hoàn thành reconciliation/exit criteria. Đây là
giới hạn dữ liệu thật, không phải vấn đề có thể giải quyết bằng một phép
`coalesce` trong dbt.
