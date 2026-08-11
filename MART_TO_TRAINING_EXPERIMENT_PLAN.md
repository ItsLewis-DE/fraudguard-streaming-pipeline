# Kế hoạch đưa ML mart vào training experiment

Code triển khai theo từng phase được mô tả tại [`docs/mart_to_training/README.md`](docs/mart_to_training/README.md).

## 1. Quyết định đã chốt

Tài liệu này chỉ áp dụng cho FraudGuard và PaySim CSV tĩnh hiện tại.

| Quyết định | Cách áp dụng |
| --- | --- |
| Prediction point | `post_ledger_update`: training sau khi giao dịch chốt sổ. Cần audit feature balance sau giao dịch/residual theo đúng prediction point này. |
| Dataset nguồn | `fraudguard_ml.ml_training_transactions`; chỉ một row cho mỗi `(source, event_id)` đủ điều kiện training. |
| Label | `is_fraud` là final static label của PaySim. Không dùng `label_cutoff_utc`; manifest ghi `label_policy: static_final_labels`. |
| Refresh mart | dbt refresh mart mỗi 5 phút để cập nhật data layer. Đây không phải training window và không bắt buộc retrain mỗi 5 phút. |
| Training input | Trainer không đọc live ClickHouse mart; mỗi experiment đọc Parquet snapshot immutable trong MinIO. |
| Split | Temporal trên `event_time`: train, validation, test theo boundaries trong YAML. |
| Training schedule | Manual hoặc weekly/monthly sau khi dữ liệu sẵn sàng; độc lập với lịch refresh dbt. |

## 2. Những phần đã có trong dự án

- Kafka/Spark/MinIO landing, quarantine và quality manifest theo batch.
- ClickHouse canonical/core tables và dbt ML mart.
- `ml_training_candidates` có `is_training_eligible` và `training_exclusion_reason` rõ ràng.
- `ml_training_transactions` là offline training relation; dbt materialize nó là `table`.
- DAG `fraudguard_dbt_build` chạy mỗi 5 phút.
- `training_data_contract.yml` và validator kiểm schema, key, lineage, target domain, residual formula và cột cấm.
- Baseline/challenger YAML có relation, feature allowlist và temporal boundaries.
- `write_json_atomic`, `sha256_file` đã có trong `ml/src/fraudguard_ml/artifacts.py`.

Chưa có snapshot dataset, manifest theo experiment, training/evaluation CLI, Airflow training DAG, MLflow và model registry.

## 3. Nguyên tắc dữ liệu

Mart 5 phút là relation live, không là dataset training immutable. Ingestion, backfill hoặc dbt logic có thể làm nó đổi. Vì vậy trainer không được tự query mart nhiều lần khi train/evaluate.

```text
CSV PaySim -> ingestion -> ClickHouse -> dbt mart refresh 5 phút
                                     -> validate contract
                                     -> Parquet snapshot theo experiment
                                     -> dataset manifest
                                     -> train/validation/test từ snapshot
                                     -> model + evaluation artifact
```

Population là toàn bộ transaction eligible trong mart tại thời điểm snapshot với predicate:

```sql
event_time <= test_end
```

Không phải chỉ dữ liệu đến trong 5 phút mới nhất.

## 4. Temporal split contract

| Split | Predicate |
| --- | --- |
| Train | `event_time <= train_end` |
| Validation | `event_time > train_end AND event_time <= validation_end` |
| Test | `event_time > validation_end AND event_time <= test_end` |

Validator phải fail nếu `train_end < validation_end < test_end` không đúng, split rỗng, split không có fraud positive case (trừ smoke test), hoặc `(source, event_id)` overlap giữa split. Feature list luôn lấy từ YAML allowlist, không tự lấy toàn bộ column của mart.

## 5. Dataset manifest

Manifest là JSON immutable cho một experiment/run. Nó bắt buộc dù CSV tĩnh vì CSV ingest, dbt definition và eligibility logic vẫn có thể đổi. Không có trường label cutoff.

```json
{
  "manifest_schema_version": 1,
  "experiment_name": "fraudguard_logistic_baseline",
  "run_id": "manual-2026-02-01T100000Z",
  "created_at_utc": "2026-02-01T10:00:04Z",
  "source_relation": "fraudguard_ml.ml_training_transactions",
  "snapshot_uri": "s3://fraudguard/training-snapshots/fraudguard_logistic_baseline/manual-2026-02-01T100000Z/data.parquet",
  "snapshot_format": "parquet",
  "label_policy": "static_final_labels",
  "row_count": 5230000,
  "fraud_count": 6354,
  "fraud_rate": 0.00121491,
  "min_event_time": "2026-01-01T00:00:00Z",
  "max_event_time": "2026-01-31T23:00:00Z",
  "split": {"strategy": "temporal", "train_end": "2026-01-21T20:00:00Z", "validation_end": "2026-01-26T20:00:00Z", "test_end": "2026-01-31T23:00:00Z"},
  "feature_list": ["transaction_type", "amount", "origin_balance_before", "destination_balance_before"],
  "target_column": "is_fraud",
  "dbt_manifest_sha256": "<sha256>",
  "training_config_sha256": "<sha256>",
  "population_query_sha256": "<sha256>",
  "fingerprint_algorithm": "clickhouse_group_bit_xor_v1",
  "data_fingerprint": "<hex>",
  "quality_status": "passed",
  "split_statistics": {"train": {"row_count": 0, "fraud_count": 0, "fraud_rate": 0.0}, "validation": {"row_count": 0, "fraud_count": 0, "fraud_rate": 0.0}, "test": {"row_count": 0, "fraud_count": 0, "fraud_rate": 0.0}}
}
```

Các số là minh họa. Manifest lưu row/fraud count, rate, min/max time, boundaries, ordered feature list, dbt manifest hash, config/query hash và fingerprint. Không lưu raw row hoặc PII. `data_fingerprint` là aggregate order-independent trên key, event time, target và feature values; nó luôn đi kèm count/time/hash, không đứng một mình.

## 6. Snapshot Parquet trong MinIO

Tạo `ml/src/fraudguard_ml/dataset_snapshot.py`:

1. Parse `ExperimentConfig` strict/immutable từ baseline/challenger YAML.
2. Kiểm tra artifact `validate-training-data` đã pass trong cùng run.
3. Đọc live relation một lần với `event_time <= test_end`.
4. Tính population/split statistics, query hash và fingerprint.
5. Export toàn bộ population sang Parquet.
6. Ghi manifest local bằng `write_json_atomic`.
7. Upload Parquet, manifest và contract artifact lên MinIO; kiểm tra object tồn tại trước success.

Path không được overwrite:

```text
s3://fraudguard/training-snapshots/<experiment_name>/<run_id>/data.parquet
s3://fraudguard/training-snapshots/<experiment_name>/<run_id>/dataset_manifest.json
s3://fraudguard/training-snapshots/<experiment_name>/<run_id>/training_data_contract.json
artifacts/ml/<experiment_name>/<run_id>/
```

Nếu retry cùng `run_id`, object hash phải trùng để reuse; khác hash phải fail. Dataset lớn có thể là folder Parquet partition theo `event_date`, nhưng path folder vẫn immutable và manifest ghi `parquet_dataset`.

## 7. Config và module mới

Thêm block sau vào hai experiment config, thay vì label cutoff:

```yaml
snapshot:
  storage_uri: s3://fraudguard/training-snapshots
  format: parquet
  fingerprint_algorithm: clickhouse_group_bit_xor_v1
  label_policy: static_final_labels
```

| Module | Trách nhiệm |
| --- | --- |
| `training_data_contract.py` | Validate live mart trước snapshot. |
| `dataset_snapshot.py` | Snapshot, manifest và split statistics; không train model. |
| `dataset_loader.py` | Đọc Parquet snapshot, kiểm manifest, tạo split. |
| `training.py` | Fit preprocessing trên train và fit estimator. |
| `evaluation.py` | Evaluate final test; không chỉnh model theo test. |
| `artifacts.py` | Reuse atomic writer/hash helper. |
| `cli.py` | Expose command local/Airflow. |

## 8. CLI flow

```bash
# dbt build và contract trước.
cd dbt && dbt build --select +tag:training

fraudguard validate-training-data \
  --config configs/training_data_contract.yml \
  --output artifacts/ml/<run_id>/training_data_contract.json

fraudguard snapshot-training-dataset \
  --config configs/training_baseline.yaml \
  --contract-artifact artifacts/ml/<run_id>/training_data_contract.json \
  --dbt-manifest dbt/target/manifest.json \
  --run-id <run_id> \
  --output artifacts/ml/fraudguard_logistic_baseline/<run_id>

fraudguard train \
  --config configs/training_baseline.yaml \
  --dataset-manifest artifacts/ml/fraudguard_logistic_baseline/<run_id>/dataset_manifest.json \
  --output artifacts/ml/fraudguard_logistic_baseline/<run_id>/model

fraudguard evaluate \
  --model artifacts/ml/fraudguard_logistic_baseline/<run_id>/model \
  --dataset-manifest artifacts/ml/fraudguard_logistic_baseline/<run_id>/dataset_manifest.json \
  --output artifacts/ml/fraudguard_logistic_baseline/<run_id>/evaluation.json
```

Sau snapshot, `train` và `evaluate` chỉ được nhận manifest/snapshot URI; không nhận live ClickHouse relation.

## 9. Quy tắc train/evaluate

1. Loader kiểm hash/statistics của snapshot với manifest trước split.
2. `OneHotEncoder`, scaler, imputer chỉ `fit` trên train.
3. Validation chọn hyperparameter/model/threshold policy.
4. Test chỉ chạy sau khi config chốt; không dùng test để chỉnh feature/threshold.
5. Bundle chứa estimator, preprocessing, ordered feature list, config hash, metrics, threshold policy, manifest URI/SHA.
6. Báo PR-AUC, ROC-AUC, recall/precision tại threshold, fraud capture rate và confusion matrix. Không dùng accuracy làm metric acceptance chính vì fraud hiếm.

Hai experiment cùng feature contract chỉ so sánh trực tiếp khi có cùng manifest SHA. Nếu feature set khác, manifest SHA có thể khác; khi đó phải có cùng `population_fingerprint`, temporal boundaries, row/fraud counts và label policy. Tốt nhất tạo một canonical snapshot chứa union feature columns rồi để mỗi experiment chọn subset từ cùng snapshot.

## 10. EDA/split diagnostics

Report từ snapshot (không từ live mart) phải gồm row/fraud count/rate và min/max time từng split; key overlap; missing rate; numeric p05/p50/p95/mean/std; tỷ lệ `transaction_type`; PSI/KS train-to-validation/test. EDA/correlation dùng để chọn feature chỉ được chạy trên train. Test khác train vì dữ liệu tương lai là bình thường; cần điều tra khi fraud rate 0, category biến mất, missingness tăng, key overlap hoặc boundary sai.

## 11. Airflow

Giữ `fraudguard_dbt_build` chạy 5 phút để data freshness. Tạo training DAG manual hoặc weekly/monthly, không trigger theo mọi dbt run:

```text
dbt mart ready -> validate contract -> snapshot dataset -> split diagnostics
               -> train baseline/challenger -> evaluate -> publish artifacts
```

Task snapshot nhận `run_id` và dbt manifest của đúng build. XCom truyền manifest URI/SHA. Sau snapshot không task nào query live mart. dbt có refresh trong lúc training cũng không ảnh hưởng vì trainer đọc Parquet snapshot.

## 12. Tests và lộ trình P0

Tests: config/boundary/feature invalid; split no-overlap; query parameterized; empty/invalid population; fingerprint/hash change; atomic no-overwrite; loader detects mismatched snapshot; ClickHouse-to-MinIO snapshot-to-train integration; dbt refresh sau snapshot không đổi run output.

1. Thêm `ExperimentConfig` + `snapshot` block YAML.
2. Sửa artifact dbt-manifest path về `dbt/target/manifest.json`.
3. Viết `dataset_snapshot.py`, manifest và tests.
4. Thêm MinIO storage adapter/Parquet export.
5. Viết loader + diagnostics.
6. Viết sklearn baseline training/evaluation CLI + bundle.
7. Thêm Airflow training DAG.
8. Khi baseline ổn định, thêm MLflow để log metrics/model/manifest.

P0 hoàn thành khi một manifest cụ thể tái lập được cùng population, split và feature order dù mart vẫn refresh 5 phút/lần.
