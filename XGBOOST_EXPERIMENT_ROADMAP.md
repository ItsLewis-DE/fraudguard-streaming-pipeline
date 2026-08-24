# Roadmap thêm XGBoost và Model Experiment cho FraudGuard

## 1. Mục tiêu

Mở rộng dự án từ một Logistic Regression baseline thành một quy trình có thể:

- huấn luyện Logistic Regression và XGBoost trên cùng dữ liệu;
- so sánh model và feature set một cách công bằng;
- chọn model tốt hơn bằng metric phù hợp bài toán fraud;
- trình bày kết quả rõ ràng trong notebook và README;
- chứng minh với nhà tuyển dụng rằng dự án có tư duy về data pipeline, model
  validation, reproducibility và tránh data leakage.

Đây là dự án portfolio, không phải production system. Mục tiêu là code rõ ràng,
pipeline chạy được và quyết định model có căn cứ; không cần xây thêm hệ sinh thái
MLOps phức tạp.

## 2. Phạm vi

### Cần làm

- Giữ Logistic Regression làm baseline.
- Thêm XGBoost làm challenger.
- Dùng chung immutable snapshot và temporal split.
- So sánh hai model trên hai feature set.
- Chọn threshold trên validation.
- Chỉ dùng test set sau khi đã chọn candidate tốt nhất.
- Tạo notebook trình bày experiment và kết luận.
- Cập nhật README bằng bảng kết quả cuối cùng.

### Không cần làm cho phiên bản portfolio

- MLflow hoặc một model registry riêng.
- Optuna/Ray Tune hoặc distributed hyperparameter tuning.
- Kubernetes, model serving API hoặc real-time inference.
- Drift monitoring production.
- Feature store.
- CI/CD và automated deployment phức tạp.
- Grid search hàng trăm cấu hình.

## 3. Trạng thái baseline hiện tại

Các số liệu này là mốc tham chiếu để so sánh, không phải kết quả production:

| Hạng mục | Giá trị hiện tại |
| --- | ---: |
| Snapshot | 6.534 dòng, 54 fraud |
| Train | 3.723 dòng, 24 fraud |
| Validation | 1.117 dòng, 14 fraud |
| Test | 1.694 dòng, 16 fraud |
| Test ROC-AUC | 0,9158 |
| Test PR-AUC | 0,1437 |
| Test precision | 8,29% |
| Test recall | 93,75% |
| Test alert rate | 10,68% |

> Dữ liệu hiện tại rất nhỏ. XGBoost có thể overfit và metric có độ biến động lớn.
> Experiment này chủ yếu chứng minh quy trình so sánh và lựa chọn model. Nếu có
> thời gian, load thêm dữ liệu trước khi công bố kết luận cuối cùng.

## 4. Nguyên tắc experiment

Mọi candidate phải đáp ứng các điều kiện sau:

- cùng `population_fingerprint`;
- cùng temporal split boundaries;
- cùng label policy;
- cùng target và cùng prediction point;
- không fit preprocessing trên validation hoặc test;
- không dùng test để chỉnh hyperparameter;
- threshold chỉ được chọn trên validation;
- random seed được cố định;
- model artifact ghi lại model kind và resolved hyperparameters.

Nếu XGBoost không cải thiện rõ ràng, giữ Logistic Regression vẫn là một kết luận
hợp lệ. Portfolio tốt cần thể hiện quyết định dựa trên bằng chứng, không nhất thiết
phải chọn model phức tạp hơn.

## 5. Phase 1 — Chuẩn bị XGBoost

Hướng dẫn triển khai đầy đủ, gồm code, lệnh kiểm tra và Definition of Done:
[`PHASE_1_XGBOOST_SETUP.md`](PHASE_1_XGBOOST_SETUP.md).

### Công việc

- [ ] Thêm dependency `xgboost>=3,<4` vào `pyproject.toml`.
- [ ] Thêm cùng dependency vào `docker/airflow/requirements.txt`.
- [ ] Chạy `uv lock` hoặc để `uv add` cập nhật `uv.lock`.
- [ ] Rebuild Airflow image và kiểm tra import XGBoost trong container.
- [ ] Xác nhận XGBoost chạy CPU với `tree_method="hist"`.

### Lệnh dự kiến

```bash
uv add 'xgboost>=3,<4'

docker compose build airflow-init
docker compose up -d --force-recreate airflow-init
docker compose up -d --force-recreate \
  airflow-apiserver airflow-scheduler airflow-dag-processor airflow-triggerer

docker compose exec airflow-scheduler python -c \
  "import xgboost; print(xgboost.__version__)"
```

### Hoàn thành khi

- `uv run python -c "import xgboost"` chạy thành công;
- Airflow scheduler import được XGBoost;
- version XGBoost được khóa trong `uv.lock`.

## 6. Phase 2 — Mở rộng model configuration

Hướng dẫn triển khai đầy đủ, gồm code, test matrix và Definition of Done:
[`PHASE_2_MODEL_CONFIGURATION.md`](PHASE_2_MODEL_CONFIGURATION.md).

### Công việc

- [ ] Tách config hiện tại thành `LogisticRegressionConfig`.
- [ ] Tạo `XGBoostConfig`.
- [ ] Dùng discriminated union với field `kind`.
- [ ] Validate các giới hạn cơ bản của hyperparameter.
- [ ] Không cho config Logistic chứa field XGBoost và ngược lại.
- [ ] Thêm config `configs/training_xgboost_baseline.yml`.
- [ ] Thêm config `configs/training_xgboost_balance.yml`.
- [ ] Đồng bộ split 2h/4h/6h cho tất cả config demo.

### XGBoost config khởi đầu

```yaml
model:
  kind: xgboost
  objective: binary:logistic
  eval_metric: aucpr
  tree_method: hist
  n_estimators: 1000
  learning_rate: 0.05
  max_depth: 4
  min_child_weight: 10
  subsample: 0.8
  colsample_bytree: 0.8
  reg_alpha: 0.0
  reg_lambda: 1.0
  early_stopping_rounds: 50
  imbalance_strategy: train_ratio
```

### Files dự kiến

```text
ml/src/fraudguard_ml/experiment_config.py
ml/tests/test_config.py
configs/training_xgboost_baseline.yml
configs/training_xgboost_balance.yml
```

### Hoàn thành khi

- cả Logistic và XGBoost YAML load thành công;
- config sai model-specific field bị reject;
- test config mới chạy pass.

## 7. Phase 3 — Tạo model interface chung

### Mục tiêu thiết kế

`training.py` không cần biết chi tiết Logistic hay XGBoost. Tạo module mới:

```text
ml/src/fraudguard_ml/modeling.py
```

Interface đề xuất:

```python
fit_probability_model(
    config,
    train,
    validation,
) -> FittedProbabilityModel
```

Model trả về phải hỗ trợ:

```python
model.predict_proba(features)
```

### Công việc

- [ ] Tạo `FittedProbabilityModel` giữ preprocessor và estimator.
- [ ] Tạo Logistic Regression adapter.
- [ ] Tạo XGBoost adapter.
- [ ] Dùng one-hot encoding cho `transaction_type` ở cả hai model.
- [ ] Scale numeric features cho Logistic Regression.
- [ ] Không scale numeric features cho XGBoost.
- [ ] Fit preprocessor chỉ trên train.
- [ ] Transform validation bằng preprocessor đã fit.
- [ ] Truyền validation vào XGBoost `eval_set` để early stopping.
- [ ] Tính `scale_pos_weight = negative_train / positive_train` chỉ từ train.
- [ ] Ghi `scale_pos_weight` và `best_iteration` vào model metadata.
- [ ] Giữ threshold selection và `binary_metrics` dùng chung.

### Files dự kiến

```text
ml/src/fraudguard_ml/modeling.py
ml/src/fraudguard_ml/training.py
ml/src/fraudguard_ml/evaluation.py
ml/tests/test_modeling.py
ml/tests/test_training.py
```

### Hoàn thành khi

- cùng một training command chạy được với cả hai `model.kind`;
- cả hai model trả probability trong `[0, 1]`;
- evaluation không cần chứa nhánh logic riêng cho từng model;
- model bundle vẫn kiểm tra manifest, feature order và fingerprint.

## 8. Phase 4 — Chạy experiment 2 × 2

Chạy bốn candidate:

| ID | Model | Feature set |
| --- | --- | --- |
| A | Logistic Regression | Baseline 4 features |
| B | XGBoost | Baseline 4 features |
| C | Logistic Regression | Balance challenger features |
| D | XGBoost | Balance challenger features |

### Công việc

- [ ] Dùng cùng population và temporal boundaries.
- [ ] Chạy từng candidate với seed 42.
- [ ] Không chạy grid search trên snapshot nhỏ hiện tại.
- [ ] Lưu validation metrics cho cả bốn candidate.
- [ ] Ghi training duration.
- [ ] Kiểm tra XGBoost `best_iteration`.
- [ ] Xác nhận population fingerprint trước khi ghép kết quả.

### Metric cần thu thập

```text
model
feature_set
population_fingerprint
train_rows
train_fraud
best_iteration
scale_pos_weight
threshold
validation_pr_auc
validation_roc_auc
validation_precision
validation_recall
validation_f1
validation_alert_rate
training_seconds
```

### Hoàn thành khi

- có một bảng validation gồm đủ bốn candidate;
- không candidate nào đã nhìn vào test trong quá trình so sánh;
- có thể giải thích vì sao một candidate tốt hoặc không tốt.

## 9. Phase 5 — Notebook model experiment

Tạo notebook:

```text
notebooks/model_experiments.ipynb
```

Notebook chỉ orchestration và visualization; không copy lại implementation của
`training.py` hoặc `modeling.py`.

### Nội dung notebook

- [ ] Mục tiêu và giới hạn của experiment.
- [ ] Load immutable snapshot và dataset manifest.
- [ ] Hiển thị số dòng, fraud count và fraud rate theo split.
- [ ] Xác nhận temporal ordering và population fingerprint.
- [ ] Chạy hoặc load kết quả bốn candidate.
- [ ] Bảng validation metrics.
- [ ] Precision–Recall curve trên validation.
- [ ] Biểu đồ precision, recall và alert rate tại threshold đã chọn.
- [ ] Feature importance của XGBoost.
- [ ] Coefficient magnitude của Logistic Regression.
- [ ] So sánh thời gian train.
- [ ] Kết luận chọn candidate nào và lý do.
- [ ] Cảnh báo dữ liệu hiện tại chưa được load đầy đủ.

### Outputs

```text
reports/model_experiments/model_comparison.csv
reports/model_experiments/model_selection.json
reports/model_experiments/validation_pr_curve.png
reports/model_experiments/feature_importance.png
```

### Hoàn thành khi

- notebook chạy từ đầu đến cuối;
- mọi biểu đồ có title, axis và chú thích rõ ràng;
- kết luận phù hợp với con số, không nói quá khả năng của model.

## 10. Phase 6 — Chọn winner và đánh giá test

### Quy tắc chọn winner

Áp dụng theo thứ tự:

1. `validation_precision >= 10%`;
2. chọn candidate có validation recall cao nhất;
3. nếu recall gần bằng nhau, chọn PR-AUC cao hơn;
4. nếu vẫn gần bằng nhau, chọn alert rate thấp hơn;
5. nếu XGBoost không cải thiện rõ ràng, giữ Logistic Regression.

### Công việc

- [ ] Khóa candidate và hyperparameters đã chọn.
- [ ] Khóa validation threshold.
- [ ] Evaluate winner đúng một lần trên test.
- [ ] Lưu confusion matrix và test metrics.
- [ ] Không quay lại chỉnh model dựa trên test result.
- [ ] Ghi rõ nếu kết quả không đủ tin cậy do số fraud quá ít.

### Hoàn thành khi

- có `model_selection.json` ghi candidate, rule và lý do chọn;
- có test metrics của winner;
- có kết luận trung thực: chọn XGBoost hoặc giữ Logistic Regression.

## 11. Phase 7 — Tích hợp candidate được chọn vào Airflow

Chỉ làm phase này sau khi notebook đã chọn winner.

### Công việc

- [ ] Tạo config chính thức cho selected model.
- [ ] Cho training DAG nhận config path từ Airflow params hoặc environment.
- [ ] Giữ nguyên các bước snapshot, diagnostics, train và evaluate.
- [ ] Đảm bảo artifact lưu `model_kind` và resolved hyperparameters.
- [ ] Chạy DAG end-to-end và chụp ảnh task graph thành công.

### Không cần làm

- Không tạo Airflow DAG cho hàng trăm hyperparameter trials.
- Không biến scheduler local thành experiment platform.
- Không tự động deploy model.

### Hoàn thành khi

- selected model chạy được bằng DAG hiện tại;
- artifact và metrics được tạo đầy đủ;
- Airflow screenshot thể hiện pipeline thành công.

## 12. Phase 8 — Hoàn thiện portfolio

### README

- [ ] Thêm bảng Logistic Regression vs XGBoost.
- [ ] Thêm ảnh Precision–Recall curve.
- [ ] Thêm ảnh feature importance.
- [ ] Giải thích temporal split và tránh leakage.
- [ ] Giải thích lý do chọn hoặc không chọn XGBoost.
- [ ] Nhấn mạnh dữ liệu model mới là subset của PaySim.
- [ ] Không dùng các từ như “production-ready” hoặc “state-of-the-art”.

### Nội dung nên nói khi phỏng vấn

- Vì sao dùng PR-AUC thay vì accuracy.
- Vì sao threshold được chọn trên validation.
- Vì sao test set chỉ được dùng sau khi chọn model.
- Vì sao model phức tạp hơn không mặc định tốt hơn.
- Cách pipeline bảo đảm schema, quarantine, reconciliation và lineage.
- Nếu có thêm thời gian, sẽ load full data và chạy temporal cross-validation.

### Hoàn thành khi

- recruiter có thể hiểu mục tiêu, kiến trúc, experiment và kết luận trong vài phút;
- notebook chạy được;
- code có test ở các seam quan trọng;
- README thể hiện đúng giới hạn của demo.

## 13. Thứ tự commit gợi ý

```text
1. chore: add xgboost dependency
2. feat: add discriminated model configs
3. feat: add shared probability model interface
4. test: cover logistic and xgboost adapters
5. feat: add xgboost experiment configs
6. notebook: compare model and feature candidates
7. docs: report model selection results
8. feat: run selected model from airflow training dag
```

Mỗi commit nên nhỏ, chạy được test liên quan và có mô tả quyết định chính.

## 14. Definition of Done cho phiên bản portfolio

Dự án được xem là hoàn thành khi:

- [ ] Logistic Regression và XGBoost dùng chung training interface.
- [ ] Bốn candidate 2 × 2 đã được so sánh trên cùng dữ liệu.
- [ ] Có notebook trình bày experiment rõ ràng.
- [ ] Có rule chọn winner và test evaluation cuối.
- [ ] Airflow chạy được selected model end-to-end.
- [ ] README có bảng kết quả và hình minh họa.
- [ ] Unit tests quan trọng pass.
- [ ] Không có data leakage rõ ràng.
- [ ] Giới hạn dữ liệu demo được ghi công khai.
- [ ] Không có hạ tầng thừa chỉ để làm dự án trông phức tạp hơn.
