# ML

## 1. Các hàm và tác dụng

### `config.py`

- `RuntimeConfig`: đối tượng lưu cấu hình chạy, bao gồm `random_seed`, `max_cpu_threads` và `memory_limit_gib`.
- `SmokeConfig`: đối tượng lưu cấu hình cho quá trình chạy smoke.
- `load_yaml_config`: nhận cấu hình và sử dụng Pydantic để kiểm tra tính hợp lệ. Nếu cấu hình không đúng, hàm sẽ phát sinh `ValueError`.

### `reproducibility.py`

File này dùng để thiết lập các cấu hình chung, chẳng hạn như giới hạn số thread và cố định seed.

- `configure_thread_limits(max_cpu_threads)`: cấu hình số thread tối đa được sử dụng.
- `seed_everything(seed)`: thiết lập seed cố định.

### `runtime.py`

- `RuntimeMetadata`: lưu thông tin về môi trường chạy.
- `collect_runtime_metadata(RuntimeConfig)`: trả về các thông số trong `RuntimeConfig` cùng những thông tin liên quan như phiên bản Python và hệ điều hành.

### `training_data_contract.py`

- `RelationName`: kiểm tra tên relation nhằm hạn chế hai rủi ro:
  - Ngăn chặn các lệnh độc hại.
  - Bọc tên bằng dấu backtick để tránh trùng với từ khóa của cơ sở dữ liệu.
- `ExpectedColumn`: kiểm tra tên của từng cột có khớp với định nghĩa hay không.
- `TrainingDataContractConfig`: lưu nội dung file YAML `data_contract` dưới dạng đối tượng.
- `ContractMetrics`: chứa các thông tin như số dòng, số dòng null và số dòng bị thiếu.
- `ValidationReport`: chứa các thông tin như relation, tên dataset và các metrics đi kèm.
- `validate_training_data_contract`: chạy truy vấn để lấy metrics, sau đó kiểm tra các metrics có xung đột hay không. Nếu có xung đột, hàm sẽ phát sinh lỗi. Mục đích của hàm là kiểm tra chất lượng dữ liệu của mart.

Các hàm trong file này đều được sử dụng trong chính file.

### `clickhouse.py`

- `ClickHouseSettings.from_env`: lấy các biến từ môi trường và trả về một đối tượng `ClickHouseSettings`.
- `create_clickhouse_client`: sử dụng các giá trị trong `ClickHouseSettings` và trả về kết quả từ `clickhouse_connect.get_client()`.

### `object_storage.py`

- `S3Location`: phân tích URI để lấy bucket và key, sau đó lưu các giá trị này trong đối tượng.
- `ObjectStorageSettings.from_env`: lấy các biến từ môi trường và trả về một đối tượng `ObjectStorageSettings`.
- `create_s3_client`: sử dụng thông tin trong `ObjectStorageSettings` để tạo và trả về client.
- `object_sha256`: lấy mã SHA-256 của một location trên S3; trả về `None` nếu không có dữ liệu.
- `upload_file_immutable`: nhận đường dẫn của file trên máy, tính mã SHA-256, tải file lên S3 và trả về mã SHA-256 của file.
- `download_file`: tải file từ S3 về đường dẫn `destination` trên máy.

### `artifacts.py`

- `sha256_file`: tạo mã hash SHA-256 cho file đầu vào.
- `git_output`: nhận lệnh Git, thực thi bằng subprocess và trả về kết quả.
- `collect_git_provenance`: kiểm tra các file liên quan đã được commit hay chưa. Nếu chưa, hàm sẽ phát sinh lỗi; nếu đã commit, hàm trả về mã hash của commit mới nhất để phục vụ việc truy vết khi cần xem xét lại.
- `build_artifact`: trả về các trường thông tin sau khi file YAML được kiểm tra thành công, bao gồm cả thông tin từ các hàm phía trên như mã hash của commit mới nhất.

### `io_utils.py`

- `write_json_atomic`: ghi dữ liệu JSON theo cơ chế atomic.
- `write_json_immutable`: ghi file JSON một lần.
- `canonical_json_sha256`: tạo mã hash SHA-256 cho đối tượng kiểu dictionary.

### `dataset_manifest.py`

File này chủ yếu dùng để đọc cấu hình nên sử dụng Pydantic.

- `SplitBoundaries`: chứa các mốc `train_end`, `validation_end` và `test_end`.
- `PartitionStatistics`: chứa thông tin của từng phần dữ liệu được chia, gồm train, validation và test.
- `SplitStatistics`: chứa ba đối tượng `PartitionStatistics` tương ứng với train, validation và test.
- `DatasetManifest`: chứa các thông tin của file manifest. Các class nhỏ trong file chủ yếu phục vụ cho class lớn này.
- `load_manifest`: đọc manifest từ một đường dẫn, kiểm tra tính hợp lệ và trả về dữ liệu kiểu `DatasetManifest`.

### `dataset_snapshot.py`

- `MutableStats`: cập nhật các thông tin như `row_count` hoặc `fraud_count` cho từng split.
  - `update`: cập nhật số liệu thống kê.
  - `freeze`: trả về một đối tượng `PartitionStatistics`.
- `unique_in_order`: loại bỏ phần tử trùng lặp nhưng vẫn giữ nguyên thứ tự.
- `quote_identifier`: quote một giá trị được truyền vào.
- `build_population_query`: trả về câu truy vấn và các tham số. Câu truy vấn tạo thêm một cột hash để hỗ trợ kiểm tra hai tập dữ liệu có giống nhau hay không.
- `canonical_query_sha256`: tạo mã SHA-256 cho câu truy vấn và các tham số.
- `validate_contract_artifact`: kiểm tra file contract đã được xử lý hay chưa. Nếu kiểm tra thất bại, quá trình sẽ dừng lại, qua đó tránh chạy snapshot khi chưa thực hiện validate.
- `update_split_stats`: cập nhật `MutableStats` cho từng split.
- `stream_snapshot`: truy vấn dữ liệu từ ClickHouse theo từng batch. Với mỗi batch, hàm lấy `event_time`, cập nhật một biến tổng kiểu `MutableStats` và cập nhật thống kê cho từng split. Mỗi split là một `MutableStats`; mã hash của từng chunk được cộng dồn bằng phép XOR. Hàm trả về một đối tượng chứa thông tin của ba split và một đối tượng chứa thông tin tổng của cả ba, đồng thời ghi dữ liệu truy vấn ra file trên máy.
- `create_snapshot_and_manifest`: kiểm tra artifact đã được xuất, tải file snapshot trên máy lên S3, đồng thời ghi file manifest và file `training_data_contract` trên máy.
- `join_s3_uri`: nối các thành phần đường dẫn với `root_` để tạo URI S3.

Một manifest gồm các trường:

- `manifest_schema_version`
- `experiment_name`
- `run_id`
- `created_at_utc`
- `source_relation`
- `snapshot_uri`
- `snapshot_format`
- `snapshot_sha256`
- `data_fingerprint`
- `snapshot_size_bytes`
- `label_policy`
- `row_count`
- `fraud_count`
- `fraud_rate`
- `min_event_time`
- `max_event_time`
- `split`, là một `SplitBoundaries` gồm:
  - `strategy="temporal"`
  - `train_end=config.split.train_end`
  - `validation_end=config.split.validation_end`
  - `test_end=config.split.test_end`
- `feature_list`
- `target_column`
- `dbt_manifest_sha256`
- `training_config_sha256`
- `population_query_sha256`
- `population_fingerprint`
- `fingerprint_algorithm`
- `quality_status="passed"`
- `contract_artifact_sha256`
- `git_sha`
- `split_statistics`

### `dataset_loader.py`

File này chịu trách nhiệm tải file snapshot từ S3 về máy.

- `FrameSplit`: chứa `features`, `target`, `keys` và `event_time`.
- `DatasetSplits`: chứa ba `FrameSplit` tương ứng với train, validation và test.
- `verify_manifest_config`: kiểm tra trước khi nạp dữ liệu vào model, bảo đảm cấu hình huấn luyện khớp với metadata của dataset.
- `materialize_snapshot`: trả về `destination` dưới dạng đường dẫn `Path`.
- `read_one_split`: đọc từng `snapshot_path` và trả về một đối tượng `FrameSplit`.
- `load_dataset_splits`: kiểm tra sự khác nhau giữa config và manifest. Từ manifest, hàm dùng `parse_utc` để lấy `train_end`, `validation_end` và `test_end`; các tham số này được dùng để tạo các đối tượng train, validation và test. Cuối cùng, hàm tập hợp chúng thành một `DatasetSplits` và trả về đối tượng đó.

### `experiment_config.py`

- `parse_utc`: phân tích giá trị thời gian UTC.
- `validate_identifiers`: kiểm tra các identifier.
- `DatasetConfig`: lưu cấu hình dataset.
- `SplitConfig`: lưu cấu hình chia dữ liệu.

### `cli.py`

#### `build_parser`

Các tham số cần truyền cho từng lệnh:

| Lệnh | Tham số |
| --- | --- |
| `validate-training-data` | `--config`, `--dbt-manifest`, `--repository-root`, `--output` |
| `snapshot-training-dataset` | `--config`, `--contract-artifact`, `--repository-root`, `--dbt-manifest`, `--run-id`, `--output` |
| `diagnose-training-splits` | `--config`, `--dataset-manifest`, `--cache-dir`, `--output` |
| `train` | `--config`, `--dataset-manifest`, `--cache-dir`, `--output` |
| `evaluate` | `--config`, `--dataset-manifest`, `--cache-dir`, `--model`, `--output` |

#### Các hàm thực thi

- `configure_experiment_runtime`: cấu hình giới hạn thread và seed, sau đó trả về seed cùng các giá trị thu được từ `collect_runtime_metadata`.
- `run_validate_training_data`: kiểm tra file `data_contract`, lấy report sau khi kiểm tra, đưa thông tin vào artifact và ghi file trên máy.
- `load_snapshot_context`: kiểm tra file experiment, cấu hình thread và seed, sau đó trả về `ModelConfig`, `ExperimentConfig`, `DatasetManifest` và các thông tin như features, target của các split.
- `run_snapshot_training_dataset`:
  - Đọc cấu hình của file experiment.
  - Thiết lập các thông số toàn cục.
  - Khởi tạo ClickHouse client.
  - Tải các file config và `data_contract` trên máy lên S3.
  - Trả về dictionary chứa các thông tin cấu hình của manifest.
- `run_train`: sử dụng `load_snapshot_context`, bắt đầu huấn luyện và trả về kết quả như mã hash của file model.
- `run_evaluate`: sử dụng `load_snapshot_context`, bắt đầu đánh giá, trả về kết quả đánh giá và lưu file trên máy.
- `run_split_diagnostics`: sử dụng `load_snapshot_context`, kiểm định lại các split, ghi kết quả ra file và trả về đường dẫn của file đó.

## 2. Nội dung rút ra

### Protocol và các kiểu dữ liệu trong `typing`

- `Protocol` được dùng để mô tả một lớp có các hàm giống lớp gốc mà không yêu cầu lớp đó phải kế thừa trực tiếp từ lớp gốc.
- `Sequence` đại diện cho một danh sách có thứ tự. Khác với `list`, `Sequence` cho phép truyền cả tuple và list.
- `Mapping` đại diện cho kiểu key-value và cho phép truyền vào bất kỳ kiểu dữ liệu nào có cấu trúc key-value.

### Validator trong Pydantic

- Khi sử dụng `field_validator`, cần đi kèm `classmethod` để tránh mypy báo lỗi.
- `model_validator` được dùng để kiểm tra nhiều field cùng nhau.
- Dùng `model_validator` ở chế độ `after` khi cần kiểm tra các trường dữ liệu sau khi chúng đã đi qua `field_validator`.
- Dùng `model_validator` ở chế độ `before` khi cần ép kiểu dữ liệu trước khi đưa dữ liệu vào class.

### Vai trò của data manifest

File manifest giống như giấy khai sinh của đúng một lần chạy, chứa định danh, nguồn gốc code thông qua `git_sha`, vị trí dữ liệu và các thống kê dữ liệu.

Một data manifest chuẩn cần có bốn nhóm thông tin:

| Nhóm | Nội dung |
| --- | --- |
| Metadata | ID, version, storage path, created time |
| Lineage | Git SHA, config hash, SQL hash, DBT hash |
| Integrity | File SHA-256, row/data fingerprint |
| Profile | Schema, feature list, splits, stats và drift |

### Cách dự án bảo đảm data lineage

Một model bất kỳ có thể được truy vết lại thông qua:

- Code: `git_sha`.
- Config: `training_config_sha256`.
- Transform: `dbt_manifest_sha256`.
- Logic lấy dữ liệu: `population_query_sha256`.
- Chất lượng dữ liệu: `contract_artifact_sha256`.
