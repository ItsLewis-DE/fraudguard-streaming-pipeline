# Hướng dẫn triển khai dbt bằng Airflow cho FraudGuard

Tài liệu này hướng dẫn cấu hình dbt chạy trong Airflow dựa trên kiến trúc hiện
có của dự án FraudGuard.

## 1. Mục tiêu và kiến trúc

Luồng dữ liệu hiện tại là:

```text
Kafka
  -> Spark Structured Streaming (micro-batch 10 giây)
  -> MinIO (Parquet + quality manifest)
  -> Airflow: minio_to_clickhouse (mỗi phút)
  -> ClickHouse raw/audit tables
  -> Airflow: fraudguard_dbt_build (mỗi 5 phút)
  -> dbt staging -> intermediate -> core -> ml + tests
```

Tạo **DAG dbt riêng** thay vì gắn trực tiếp `dbt build` vào cuối mỗi lần chạy
`minio_to_clickhouse`.

Lý do:

- Spark có thể tạo batch mới mỗi 10 giây và ingestion DAG poll mỗi phút.
- Các mart `core` và `ml` hiện materialize dưới dạng `table`; chạy dbt mỗi phút
  sẽ rebuild chúng quá thường xuyên khi dữ liệu tăng.
- `int_committed_ingestion_batches` chỉ chọn batch có `status = 'success'`.
  Nhờ commit marker này, dbt không đọc một batch đang được loader ghi dở; batch
  vừa commit sẽ được lấy ở lần dbt kế tiếp.
- dbt đã có dependency graph, nên để dbt tự sắp xếp các models và tests sẽ đơn
  giản, rõ ràng, và dễ retry hơn việc biến từng model thành một Airflow task.

## 2. Quy ước vận hành được đề xuất

| Thành phần | Cấu hình |
| --- | --- |
| DAG ingestion | `minio_to_clickhouse`, mỗi phút (đã có) |
| DAG dbt | `fraudguard_dbt_build`, 5 phút cho dev; 15–30 phút cho production lúc đầu |
| Lệnh runtime | `dbt build --fail-fast` |
| Catchup | `False` |
| Concurrent DAG runs | `max_active_runs=1` |
| Retry dbt | 1 lần, sau 2 phút |
| Timeout dbt | 30 phút |
| dbt threads | 2 cho local stack |
| ClickHouse transformer | user `fraudguard_transformer` |

Với project hiện tại, dùng `dbt build` không selector là hợp lý: project nhỏ
nhưng có nhiều data tests. Lệnh này build cả 13 models và chạy tất cả tests theo
thứ tự dependency.

Lưu ý quan trọng: staging và intermediate hiện là `view`, nhưng 3 model core và
3 model ml là `table`. Mỗi lần build, 6 bảng này được tính lại từ toàn bộ query
nguồn. Adapter ClickHouse thường tạo bảng thay thế rồi `EXCHANGE`/rename với
bảng hiện tại và dọn bảng cũ; vì vậy không nhất thiết có khoảng trống do `DROP`
trước, nhưng chi phí đọc và ghi vẫn gần như full rebuild. Đây là lý do không nên
coi lịch 5 phút là mặc định cho production.

Chỉ giữ lịch 5 phút khi p95 thời gian `dbt build` nhỏ hơn đáng kể so với 5 phút
(thực tế nên dưới khoảng 2 phút). Nếu build tiến gần hoặc vượt thời gian
schedule, DAG sẽ tạo backlog và ClickHouse phải chịu các lần full rebuild chồng
nhau theo thời gian. Khi chưa benchmark, bắt đầu 15–30 phút là an toàn hơn.

Full rebuild hiện tại có một lợi ích về tính đúng: các model canonical hóa replay,
đếm payload conflict, và join final labels đều có thể thay đổi các row cũ khi
batch mới hoặc label đến muộn. Không nên đổi toàn bộ sang incremental chỉ để đạt
freshness 5 phút nếu chưa thiết kế watermark, upsert các business key bị ảnh
hưởng, và xử lý late-arriving labels.

Không chỉ chạy selector sau:

```bash
dbt build --select "+tag:training"
```

Selector này lấy lineage cho nhánh training, nhưng không bao gồm nhánh độc lập
`stg_ingestion_batch_quality` cùng test reconciliation của nó. Nếu sau này cần
giảm phạm vi chạy, hãy tạo `selectors.yml` bao gồm rõ cả nhánh quality, thay vì
chỉ dựa vào tag `training`.

## 3. Cài dbt vào Airflow image

Airflow image hiện chưa có dbt. Thêm các dependency sau vào
`docker/airflow/requirements.txt`:

```text
apache-airflow-providers-amazon==9.32.0
clickhouse-connect==1.5.0
dbt-core==1.11.12
dbt-clickhouse==1.10.1
```

Các version này khớp với lockfile hiện tại của project (`uv.lock`). Pin cả
`dbt-core` lẫn adapter để Docker image không vô tình cài một dbt-core khác khi
build lại image.

Sau đó build lại image Airflow:

```bash
docker compose build airflow-init airflow-apiserver airflow-scheduler airflow-dag-processor airflow-triggerer
```

## 4. Cấp source dbt và credentials cho Airflow

Thêm các biến môi trường và mount sau vào `x-airflow-common` trong
`docker-compose.yml`.

```yaml
x-airflow-common: &airflow-common
  environment: &airflow-common-environment
    # ... cấu hình Airflow hiện có ...

    # dbt profile: dbt/profiles.yml
    DBT_CLICKHOUSE_HOST: clickhouse
    DBT_CLICKHOUSE_PORT: "8123"
    DBT_CLICKHOUSE_DATABASE: fraudguard
    DBT_CLICKHOUSE_USER: fraudguard_transformer
    DBT_CLICKHOUSE_PASSWORD: ${DBT_CLICKHOUSE_PASSWORD:?DBT_CLICKHOUSE_PASSWORD must be set}
    DBT_CLICKHOUSE_THREADS: "2"

    # Không ghi target/logs vào source directory được mount read-only.
    DBT_TARGET_PATH: /opt/airflow/logs/dbt/target
    DBT_LOG_PATH: /opt/airflow/logs/dbt/logs

  volumes:
    - ./airflow/dags:/opt/airflow/dags:ro
    - ./airflow/plugins:/opt/airflow/plugins:ro
    - ./dbt:/opt/airflow/dbt:ro
    - airflow_logs:/opt/airflow/logs
```

Các biến trên tương thích trực tiếp với `dbt/profiles.yml`. User
`fraudguard_transformer` đã có quyền `SELECT` trên raw database và quyền tạo/
ghi trong các database `fraudguard_staging`, `fraudguard_intermediate`,
`fraudguard_core`, và `fraudguard_ml`.

Không đưa password vào Python DAG hoặc commit vào Git. Cung cấp
`DBT_CLICKHOUSE_PASSWORD` qua `.env` cục bộ, secret manager, hoặc secret của
deployment platform.

> `scripts/dbt.sh` chỉ phù hợp để chạy trên máy development vì nó gọi `uv` và
> dùng đường dẫn repo local. Trong Airflow, gọi binary `dbt` trực tiếp.

## 5. Tạo DAG dbt

Tạo file `airflow/dags/fraudguard_dbt_build.py` với nội dung sau:

```python
from __future__ import annotations

from datetime import timedelta

import pendulum
from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import dag


@dag(
    dag_id="fraudguard_dbt_build",
    description="Build and validate FraudGuard ClickHouse transformations",
    schedule="*/5 * * * *",
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(minutes=45),
    default_args={
        "owner": "fraud-platform",
        "retries": 1,
        "retry_delay": timedelta(minutes=2),
        "retry_exponential_backoff": True,
    },
    tags=["fraudguard", "dbt", "clickhouse"],
)
def fraudguard_dbt_build():
    BashOperator(
        task_id="dbt_build",
        bash_command="""
            set -euo pipefail
            dbt build \\
                --project-dir /opt/airflow/dbt \\
                --profiles-dir /opt/airflow/dbt \\
                --target dev \\
                --fail-fast
        """,
        execution_timeout=timedelta(minutes=30),
        do_xcom_push=False,
        # Sau khi tạo Airflow pool một slot, bỏ comment dòng này:
        # pool="clickhouse_transform",
    )


fraudguard_dbt_build()
```

`dbt build` thay cho chuỗi `dbt run` rồi `dbt test`: nó chạy model và test
trong cùng một graph. Nếu test của upstream model lỗi, dbt tự không chạy các
model phụ thuộc downstream; đây là hành vi mong muốn cho bảng training.

## 6. Tạo Airflow pool cho ClickHouse (khuyến nghị)

Để không có hai workload transform cùng ghi vào ClickHouse, tạo pool một slot:

```bash
docker compose exec airflow-scheduler \
  airflow pools set clickhouse_transform 1 "Serialize ClickHouse dbt transformations"
```

Sau đó bỏ comment `pool="clickhouse_transform"` trong DAG.

`max_active_runs=1` bảo vệ riêng DAG dbt; pool hữu ích nếu sau này có thêm DAG
backfill, data-quality, hoặc training cùng dùng ClickHouse transformer.

## 7. Kiểm tra trước khi bật DAG

### 7.1. Kiểm tra trên máy development

```bash
./scripts/dbt.sh parse
./scripts/dbt.sh debug
./scripts/dbt.sh build --fail-fast
```

`parse` không cần warehouse và phù hợp cho CI. `debug` và `build` cần
ClickHouse chạy cùng credentials trong `.env.dbt`.

### 7.2. Kiểm tra trong Airflow container

Sau khi build image và khởi động stack:

```bash
docker compose up -d
docker compose exec airflow-scheduler \
  dbt debug --project-dir /opt/airflow/dbt --profiles-dir /opt/airflow/dbt
```

Sau khi lệnh `debug` thành công, mở Airflow UI, unpause
`fraudguard_dbt_build`, rồi trigger một run thủ công đầu tiên. Quan sát log
task `dbt_build` và xác nhận các relation xuất hiện tại:

```text
fraudguard_staging
fraudguard_intermediate
fraudguard_core
fraudguard_ml
```

## 8. Xử lý lỗi và retry

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `dbt debug` không kết nối được | Sai host/user/password hoặc ClickHouse chưa healthy | Kiểm tra `DBT_CLICKHOUSE_*` và service `clickhouse` |
| dbt không tạo được bảng | Airflow đang dùng loader user thay transformer user | Phải dùng `fraudguard_transformer` |
| dbt ghi `target` hoặc `logs` thất bại | thư mục dbt được mount read-only | Giữ `DBT_TARGET_PATH` và `DBT_LOG_PATH` trong `/opt/airflow/logs` |
| data test fail | Dữ liệu raw/quality không thỏa contract | Xem test lỗi, sửa ingestion hoặc dữ liệu; không tăng retry |
| DAG dbt chồng run | schedule quá dày hoặc build chậm | Giữ `max_active_runs=1`; tăng schedule lên 10/15 phút nếu cần |

Lỗi data test là lỗi chất lượng dữ liệu, không phải lỗi tạm thời. Một lần retry
chỉ phục vụ lỗi mạng hoặc lỗi service ngắn hạn; sau đó cần xử lý nguyên nhân
trước khi rerun.

## 9. Khi nào dùng Asset-aware scheduling?

Airflow Assets phù hợp khi ingestion không liên tục, hoặc khi muốn dbt chạy
ngay sau một commit cụ thể. Khi đó, thêm một asset ở cuối ingestion DAG và dùng
asset làm `schedule` cho DAG dbt.

Không chọn cách này làm mặc định cho stack hiện tại, vì ingestion DAG poll mỗi
phút và Spark tạo micro-batch mỗi 10 giây. Với các mart dạng `table`, asset
event có thể kích hoạt dbt quá thường xuyên và tạo backlog. Cron 5 phút cùng
commit barrier trong `ingestion_batches` là điểm cân bằng tốt hơn ở giai đoạn
hiện tại.

## 10. Bước tiếp theo cho ML

Sau `dbt_build` thành công, có thể thêm task validate training contract trước
khi training model. Tuy nhiên chưa nên nối task này ngay vì CLI hiện có hai
đường dẫn cần thống nhất:

- `ml/src/fraudguard_ml/cli.py` đang tìm `poetry.lock`, trong khi repo dùng
  `uv.lock`.
- CLI đang tìm `target/manifest.json` ở repository root, trong khi dbt project
  hiện ghi manifest vào `dbt/target` (và Airflow sẽ ghi vào
  `/opt/airflow/logs/dbt/target`).

Sửa contract-artifact path trước, rồi mới thêm luồng:

```text
dbt_build -> validate_training_data -> train_model
```

## 11. Gợi ý cải tiến khi dữ liệu lớn hơn

- Giữ full rebuild hiện tại cho đến khi yêu cầu về replay/conflict lineage được
  mô tả rõ cho incremental models. Chuyển sang incremental quá sớm có thể làm
  sai `physical_row_count` hoặc `payload_version_count` khi có replay.
- Thêm source freshness chỉ khi đã chốt SLA cho từng nguồn; hiện sources chưa
  khai báo freshness policy nên không nên suy đoán threshold.
- Khi dbt cần chạy riêng với nhiều dependency hệ thống hơn, tách thành image
  dbt độc lập hoặc Kubernetes pod thay vì cài thêm packages vào Airflow image.
- Đưa `dbt parse` vào CI để phát hiện lỗi Jinja, ref, source và selector trước
  khi deploy DAG.
