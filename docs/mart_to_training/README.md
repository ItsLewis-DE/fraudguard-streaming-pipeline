# Hướng dẫn triển khai mart → training experiment

Đây là bộ tài liệu code theo phase cho [kế hoạch tổng thể](../../MART_TO_TRAINING_EXPERIMENT_PLAN.md). Code được thiết kế cho cấu trúc hiện tại của FraudGuard: Python 3.12, ClickHouse, dbt, MinIO, Airflow, Pydantic v2 và PaySim CSV tĩnh.

## Các quyết định không thay đổi

- Prediction point là `post_ledger_update`.
- `is_fraud` là final static label; không có `label_cutoff_utc`.
- dbt mart vẫn refresh mỗi 5 phút, nhưng training không đọc mart live.
- Một query ClickHouse duy nhất tạo Parquet snapshot run-scoped.
- Statistics và hash được tính trên chính snapshot đã ghi.
- Train/validation/test được tái tạo từ snapshot theo temporal boundaries.
- Test chỉ được evaluate sau khi model và threshold đã chốt bằng train/validation.

## Thứ tự triển khai

| Phase | Tài liệu | Output chính |
| --- | --- | --- |
| 1 | [Config và contract](01_CONFIG_AND_CONTRACTS.md) | Dependency, YAML schema, `ExperimentConfig`, manifest models |
| 2 | [Snapshot và MinIO](02_SNAPSHOT_AND_MANIFEST.md) | `object_storage.py`, `dataset_snapshot.py`, immutable Parquet + manifest |
| 3 | [Loader và diagnostics](03_LOADER_AND_DIAGNOSTICS.md) | Verify snapshot, temporal split, EDA/drift report |
| 4 | [Train và evaluate](04_TRAIN_AND_EVALUATE.md) | sklearn pipeline, threshold selection, model bundle, final evaluation |
| 5 | [CLI, Airflow và tests](05_CLI_AIRFLOW_AND_TESTS.md) | Commands, training DAG, Docker/MinIO wiring, test suite |

Không triển khai phase sau trước khi acceptance checks của phase trước pass.

## Cấu trúc đích

```text
ml/src/fraudguard_ml/
├── artifacts.py                    # đã có; bổ sung immutable helper
├── clickhouse.py                   # đã có
├── cli.py                          # mở rộng ở phase 5
├── experiment_config.py            # phase 1
├── dataset_manifest.py             # phase 1
├── object_storage.py               # phase 2
├── dataset_snapshot.py             # phase 2
├── dataset_loader.py               # phase 3
├── split_diagnostics.py            # phase 3
├── training.py                     # phase 4
└── evaluation.py                   # phase 4

ml/tests/
├── test_experiment_config.py
├── test_dataset_snapshot.py
├── test_dataset_loader.py
├── test_split_diagnostics.py
├── test_training.py
└── test_evaluation.py

airflow/dags/
└── fraudguard_training.py           # phase 5
```

## Hai loại fingerprint

Không dùng một hash cho hai mục đích khác nhau:

- `population_fingerprint`: XOR của `cityHash64(source, event_id, event_time, is_fraud)`. Nó độc lập với feature list và dùng để xác nhận hai experiment có cùng row/label population.
- `data_fingerprint`: SHA-256 của file Parquet. Nó xác định toàn bộ artifact, gồm feature columns và encoding.

Baseline và challenger có thể dùng feature list khác nhau nên manifest SHA/data fingerprint có thể khác. Chúng vẫn so sánh công bằng nếu population fingerprint, temporal boundaries, row/fraud counts và label policy giống nhau. Nếu cần bảo đảm tuyệt đối cùng file snapshot cho feature experiments, tạo một canonical snapshot chứa union feature columns rồi để mỗi config chọn subset khi load.

## Definition of done toàn pipeline

```text
dbt build +tag:training
  -> data contract pass
  -> immutable Parquet snapshot + manifest
  -> manifest verification
  -> temporal split diagnostics pass
  -> train và threshold selection trên train/validation
  -> final test evaluation
  -> model bundle trỏ ngược tới manifest URI/SHA
```

Một run chỉ thành công khi từ `evaluation.json` có thể truy ngược tới model bundle, config hash, manifest, Parquet snapshot, dbt manifest hash và source relation.
