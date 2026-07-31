# FraudGuard — ML-first Implementation Roadmap

> Phiên bản 2.0 — cập nhật ngày 24/07/2026
> Phạm vi: chỉ mô tả công việc tiếp theo của dự án, không lặp lại lịch sử triển
> khai.
> Mục tiêu: học Machine Learning một cách có hệ thống, đặc biệt là feature
> engineering và hyperparameter tuning, đồng thời giữ tiêu chuẩn của một dự án
> Data/ML Engineering chuyên nghiệp chạy hoàn toàn local và miễn phí.

## 1. Định hướng đã chốt

### 1.1 Hồ sơ dự án

FraudGuard được phát triển như một hệ thống ưu tiên điều tra gian lận theo batch,
không phải hệ thống tự động chặn giao dịch real-time.

Đầu ra chính của hệ thống là:

```text
transaction
  → point-in-time features
  → calibrated fraud risk score
  → alert policy theo capacity
  → business-safe reason codes
  → case investigation
  → local LLM case summary
  → delayed analyst/label feedback
  → model monitoring
```

Trọng tâm thực thi:

- khoảng 65% cho feature engineering, training, evaluation, tuning và
  explainability;
- khoảng 25% cho data quality, reproducibility, orchestration và model
  lifecycle;
- khoảng 10% cho Streamlit và local LLM copilot.

Định hướng nghề nghiệp của portfolio là cân bằng nhưng hơi nghiêng về Data
Engineering. Vì vậy mọi thí nghiệm ML phải truy được về dữ liệu, feature,
config, code và model artifact; không chấp nhận notebook-only project.

### 1.2 Ràng buộc

- Chạy local trên 16 CPU, khoảng 8 GB RAM và NVIDIA RTX 3050 4 GB.
- Không dùng dịch vụ cloud hoặc API trả phí.
- Dataset PaySim có khoảng 6,36 triệu dòng; không giả định toàn bộ DataFrame luôn
  nằm vừa trong RAM cùng lúc.
- Docker services chạy trong WSL/Docker Desktop; training ưu tiên chạy từ host
  bằng `uv` để dễ kiểm soát CPU/GPU.
- Batch inference là bắt buộc. Online feature store, low-latency API và
  Kubernetes không thuộc active roadmap.
- Deep learning và LLM là bắt buộc để học và demo, nhưng không được ưu ái khi
  chọn champion. Model tốt nhất phải thắng bằng evidence.

### 1.3 Prediction semantics

- Grain: một `event_id` tương ứng một giao dịch.
- Prediction time: sau khi transaction event đã được ghi nhận, trước khi analyst
  bắt đầu điều tra.
- Business action: xếp hạng và ưu tiên case, không tự động từ chối giao dịch.
- Target chính: `is_fraud`.
- `is_flagged_fraud` chỉ dùng để phân tích rule hiện có; không được dùng làm
  feature.
- Label chỉ hợp lệ tại một cutoff nếu `observed_at <= cutoff`.
- Model tạo score; policy độc lập chuyển score thành alert.

## 2. Tech stack cho giai đoạn tiếp theo

### 2.1 Stack được chọn

| Nhu cầu | Công nghệ | Vai trò |
|---|---|---|
| Dependency/runtime | Python 3.12, `uv` | Môi trường tái lập |
| SQL feature layer | ClickHouse, dbt-clickhouse | Point-in-time features và data tests |
| Dataset I/O | Parquet, PyArrow, Polars Lazy API | Snapshot và xử lý tiết kiệm RAM |
| Data contracts | Pandera, Pydantic | Feature schema, config và output validation |
| ML nền tảng | NumPy, scikit-learn | Pipeline, baseline, metrics, calibration |
| Tree challengers | HistGradientBoosting, XGBoost, LightGBM, CatBoost | Benchmark nhiều model family |
| Deep learning | PyTorch | Tabular MLP challenger |
| Imbalance experiments | class/sample weights; `imbalanced-learn` chỉ cho lab | Học imbalance có kiểm soát |
| Tuning | Optuna | Search space, pruning, resumable studies |
| Tracking/registry | MLflow, PostgreSQL, MinIO | Run, artifact, dataset và model version |
| Explainability | SHAP | Global/local attribution và reason codes |
| Local LLM | Ollama + một small instruct model quantized | Fraud Case Copilot miễn phí |
| ML application | Streamlit, Plotly | Model comparison và case investigation |
| Tests | pytest, dbt tests | Unit, contract, temporal và integration tests |
| Code quality | Ruff, mypy, pre-commit | Lint, format và static checks |
| CI | GitHub Actions | Fast checks không cần full local stack |

### 2.2 Quy tắc sử dụng stack

- Polars dùng `scan_parquet`/lazy execution cho snapshot; chỉ chuyển dữ liệu cần
  thiết sang NumPy/pandas tại boundary của thư viện ML.
- scikit-learn cung cấp preprocessing/evaluation contract chung. Wrapper của
  XGBoost, LightGBM và CatBoost phải trả cùng prediction schema.
- Không tuning tất cả model bằng search space lớn. Benchmark hẹp trước, sau đó
  chỉ tune tối đa hai model tree tốt nhất và một PyTorch challenger.
- MLflow phải được dùng từ baseline đầu tiên, không thêm vào sau khi thí nghiệm
  đã kết thúc.
- PyTorch dùng mini-batch, early stopping và automatic mixed precision khi CUDA
  ổn định. Không đưa toàn bộ dataset lên VRAM.
- Ollama chỉ sinh bản tóm tắt từ evidence đã được truy xuất. LLM không tạo fraud
  score, không sửa model decision và không truy cập raw account identifier.
- Streamlit là giao diện duy nhất trong active roadmap. Superset được hoãn; chỉ
  xem xét lại khi monitoring marts đã ổn định và cần BI chuyên dụng.

### 2.3 Công nghệ cố ý chưa dùng

- Không dùng Feast: feature definitions và offline batch features chưa cần
  online store.
- Không dùng Spark MLlib: mục tiêu là học Python ML ecosystem và model vừa với
  single-machine sau khi materialize features.
- Không dùng distributed training, Ray, Dask hoặc Kubernetes.
- Không dùng LangChain/LlamaIndex: copilot chưa cần agent framework.
- Không dùng vector database/RAG: hiện chưa có document corpus cần semantic
  retrieval.
- Không fine-tune LLM: 4 GB VRAM không phù hợp và không tạo đủ giá trị cho bài
  toán này.
- Không dùng GNN trên full transaction graph trong phiên bản này. Point-in-time
  graph features phải được chứng minh trước.

## 3. Nguyên tắc học và triển khai

Mỗi milestone phải trả lời đủ bốn câu hỏi:

1. Kiến thức nào cần hiểu trước khi code?
2. Artifact nào sẽ được tạo?
3. Làm sao chứng minh artifact đúng?
4. Kết quả học được ghi lại ở đâu?

Notebook được phép dùng cho EDA và learning experiments. Logic dùng để train,
evaluate, tune, explain hoặc score phải nằm trong importable package và có test.

Ba cấp dữ liệu được dùng xuyên suốt:

| Cấp | Mục đích | Được dùng để kết luận model? |
|---|---|---|
| Smoke | Chạy nhanh contract/test, fixed hash sample nhỏ | Không |
| Benchmark | So sánh model/feature nhanh, validation giữ prevalence tự nhiên | Chỉ để shortlist |
| Final | Full immutable snapshot | Có |

Mọi báo cáo phải phân biệt:

- kết quả trên smoke/benchmark/final;
- observation, inference và recommendation;
- performance model và performance decision policy;
- metric trên label đã mature và label chưa mature.

## 4. Cấu trúc repository mục tiêu

```text
ML_Fraud_Banking/
├── AGENTS.md
├── ROADMAP.md
├── pyproject.toml
├── uv.lock
├── configs/
│   ├── data/
│   │   ├── smoke.yaml
│   │   ├── benchmark.yaml
│   │   └── final.yaml
│   ├── models/
│   │   ├── logistic.yaml
│   │   ├── hist_gradient_boosting.yaml
│   │   ├── xgboost.yaml
│   │   ├── lightgbm.yaml
│   │   ├── catboost.yaml
│   │   └── pytorch_mlp.yaml
│   ├── tuning/
│   ├── policy/
│   └── llm/
├── dbt/
│   ├── models/
│   │   ├── staging/
│   │   ├── intermediate/
│   │   ├── features/
│   │   ├── marts/
│   │   └── monitoring/
│   └── tests/
├── ml/
│   ├── src/fraudguard_ml/
│   │   ├── cli.py
│   │   ├── config.py
│   │   ├── contracts.py
│   │   ├── dataset.py
│   │   ├── leakage.py
│   │   ├── split.py
│   │   ├── preprocessing.py
│   │   ├── metrics.py
│   │   ├── models/
│   │   ├── training/
│   │   ├── tuning/
│   │   ├── calibration.py
│   │   ├── policy.py
│   │   ├── explain.py
│   │   ├── registry.py
│   │   ├── scoring.py
│   │   ├── monitoring.py
│   │   └── copilot.py
│   └── tests/
│       ├── unit/
│       ├── contract/
│       ├── temporal/
│       └── integration/
├── notebooks/
│   ├── 01_data_understanding.ipynb
│   ├── 02_leakage_audit.ipynb
│   ├── 03_feature_experiments.ipynb
│   ├── 04_model_error_analysis.ipynb
│   └── 05_deep_learning.ipynb
├── reports/
│   ├── eda/
│   ├── experiments/
│   ├── model_cards/
│   └── llm_evals/
├── streamlit_app/
│   ├── app.py
│   ├── pages/
│   └── components/
└── scripts/
    ├── build_training_snapshot.py
    ├── train.py
    ├── tune.py
    ├── evaluate.py
    ├── promote.py
    ├── score.py
    └── monitor.py
```

Không commit snapshot, model binary, MLflow data, Optuna database, notebook
output lớn hoặc Ollama model weights.

## 5. Roadmap thực thi

Các milestone sau có dependency tuần tự. Không chuyển milestone chỉ vì code đã
chạy; phải đạt exit criteria.

### M0 — Khôi phục development gate và tạo ML package

Hướng dẫn code và checklist chi tiết: [`M0.md`](M0.md).

#### Mục tiêu học

- Hiểu dependency groups, `src` layout, configuration validation và test
  pyramid.
- Phân biệt service runtime với training runtime.

#### Triển khai

1. Khôi phục Docker Desktop WSL integration và xác nhận
   `docker compose config --quiet` chạy được.
2. Tạo dependency groups trong `pyproject.toml`: `data`, `ml`, `deep-learning`,
   `app`, `dev`.
3. Tạo `ml/src/fraudguard_ml` và CLI entry point.
4. Tạo Pydantic config models; YAML không được đọc thành dictionary không kiểm
   soát.
5. Thêm Ruff, mypy, pytest và pre-commit.
6. Tạo smoke command không cần services để kiểm tra import/config.
7. Ghi lại CPU count, RAM limit, GPU availability và random seed trong mỗi
   training run.

#### Tests

- Package import được trong clean `uv sync`.
- Config thiếu field bắt buộc phải fail với message rõ ràng.
- Seed được truyền tới NumPy, scikit-learn, Optuna và PyTorch.
- `ruff check`, `mypy` cho core package và unit tests pass.

#### Exit criteria

```text
uv sync --all-groups
uv run pytest ml/tests/unit
uv run ruff check .
uv run python -m fraudguard_ml.cli --help
docker compose config --quiet
```

### M1 — dbt canonical layer và data quality gate

#### Mục tiêu học

- Grain, cardinality, deduplication semantics và delayed-label joins.
- Vì sao ML không được train trực tiếp từ raw ingestion tables.

#### Triển khai

1. Tạo staging models chuẩn hóa tên/type nhưng không thêm business logic.
2. Tạo canonical transaction model có đúng một row cho mỗi `event_id`.
3. Tạo canonical label model chọn label version hợp lệ mới nhất tại mỗi cutoff.
4. Tạo reconciliation model so sánh source rows, canonical rows, duplicate và
   quarantine counts.
5. Document grain, owner, freshness và contract cho từng model.
6. Tạo data-quality summary làm đầu vào cho snapshot builder.

#### Tests bắt buộc

- `event_id` unique và not null ở canonical transaction.
- `is_fraud` chỉ nhận 0/1.
- `observed_at >= event_time`.
- Không orphan label sau maturity window đã định nghĩa.
- Amount/balance range hợp lệ hoặc được gắn data-quality flag.
- Join transaction-label không làm tăng transaction grain.
- Future label không xuất hiện tại cutoff quá khứ.

#### Exit criteria

- `dbt build` pass trên fixture và dữ liệu local.
- Có báo cáo row-count/duplicate/null/label coverage theo event date.
- Snapshot builder từ chối chạy nếu critical dbt test fail.

### M2 — EDA, problem framing và leakage audit

#### Mục tiêu học

- Imbalanced classification khác balanced classification như thế nào.
- Temporal drift, selection bias, target leakage và proxy leakage.
- Vì sao EDA phải dẫn đến feature hypothesis, không chỉ tạo biểu đồ.

#### Triển khai

1. Profile fraud prevalence theo thời gian, transaction type và amount band.
2. Phân tích label delay và xác định maturity window.
3. Phân tích balance inconsistencies của PaySim.
4. Kiểm tra account recurrence, new-account rate và counterparty concentration.
5. Xác định temporal split boundaries không cắt duplicate/correction.
6. Tạo feature allowlist, denylist và review checklist.
7. Viết problem statement cuối:
   - prediction time;
   - target;
   - alert capacity;
   - cost của false positive/false negative;
   - giới hạn dữ liệu synthetic.
8. Ghi feature hypotheses trước khi nhìn test metric.

#### Leakage denylist tối thiểu

- `is_fraud`, `is_flagged_fraud` và mọi biến dẫn xuất từ chúng.
- `observed_at`, label version hoặc investigation outcome tại inference.
- Future transaction/future aggregate.
- Raw account ID dùng như categorical shortcut.
- Dataset row order nếu nó vô tình mã hóa target.
- Feature được tính bằng toàn bộ dataset trước khi split.

#### Deliverables

- `notebooks/01_data_understanding.ipynb`.
- `notebooks/02_leakage_audit.ipynb`.
- `reports/eda/eda_report.md`.
- `configs/data/split_v1.yaml`.
- `configs/data/feature_allowlist_v1.yaml`.

#### Exit criteria

- Mọi feature V1 có availability time và business rationale.
- Split được chốt trước model comparison.
- Test window chưa được dùng để chọn feature/model.

### M3 — Point-in-time feature engineering V1

#### Mục tiêu học

- Window features, entity history, availability time và cold-start handling.
- Feature definition khác feature value như thế nào.
- Cách chứng minh một aggregate point-in-time correct.

#### Feature groups

| Nhóm | Feature ví dụ |
|---|---|
| Transaction | `log_amount`, transaction type, hour/day, amount bucket |
| Balance | origin/destination balance ratios, delta, zero-balance flags |
| Origin velocity | count/sum/mean/max trong 1h, 6h, 24h |
| Destination velocity | inbound count/sum/unique origins trong 1h, 6h, 24h |
| Counterparty | first-seen flag, prior pair count, prior pair amount |
| Novelty | amount z-score/robust deviation so với lịch sử entity |
| Behavioral | time since prior transaction, burstiness, cash-out sequence |
| Data quality | missing/inconsistent balance indicators |

#### Quy tắc

- Window phải kết thúc trước event hiện tại; tie-break bằng event sequence hoặc
  event ID ổn định.
- Không dùng raw account ID làm model input.
- Null không tự động fill 0 nếu 0 có business meaning.
- Feature có logic/window/unit/null policy thay đổi phải tạo version mới.
- Feature SQL phải giữ grain một row mỗi `event_id`.

#### Triển khai

1. Tạo intermediate models cho entity histories.
2. Tạo feature models theo từng group thay vì một SQL khổng lồ.
3. Tạo feature registry YAML gồm:
   - name/type;
   - entity;
   - description;
   - lookback window;
   - availability;
   - null policy;
   - owner;
   - source model;
   - feature version.
4. Tạo final `features_transaction_v1`.
5. Tạo smoke fixtures có event tương lai để test invariance.

#### Tests bắt buộc

- Thêm transaction tương lai không thay đổi feature quá khứ.
- Row count và event IDs bằng canonical transaction spine.
- Feature types khớp registry.
- Không xuất hiện denylisted column.
- First-event/cold-start behavior đúng.
- Window boundary và same-timestamp tie-break deterministic.

#### Exit criteria

- Point-in-time tests pass.
- Có profile null/range/distribution cho mọi feature.
- Feature query chạy được trên full local dataset trong resource budget.

### M4 — Immutable training snapshots

#### Mục tiêu học

- Dataset versioning, reproducibility và label maturity.
- Tại sao training không đọc mutable feature view trực tiếp.

#### Triển khai

1. Tạo training spine bằng feature version, label policy và cutoff cụ thể.
2. Materialize Parquet partitioned theo split/time.
3. Tạo ba configs: smoke, benchmark và final.
4. Tạo manifest chứa:
   - dataset/version;
   - creation time;
   - source model và dbt manifest hash;
   - Git SHA;
   - feature/split/label-policy versions;
   - cutoff/maturity window;
   - row/positive counts theo split;
   - schema;
   - object paths, sizes và SHA-256.
5. Builder phải atomic: chỉ publish manifest sau khi mọi part và validation
   hoàn thành.
6. Dùng Polars lazy scan để đọc selected columns; không load toàn snapshot khi
   chỉ cần một split.

#### Sampling contract

- Smoke sample dùng stable hash của `event_id`, chỉ để chạy code/test.
- Benchmark có thể giảm training negatives nhưng validation giữ prevalence tự
  nhiên.
- Final dùng full data.
- Nếu training prevalence bị thay đổi, sample weights và original prevalence
  phải được ghi lại; calibration luôn dùng natural-prevalence data.

#### Exit criteria

- Build lại cùng input tạo cùng logical dataset hash.
- Corrupt/missing Parquet part làm validation fail.
- Không event nào xuất hiện ở nhiều split.
- Training command chỉ nhận dataset version, không nhận mutable SQL query.

### M5 — MLflow foundation và experiment contract

#### Mục tiêu học

- Run, experiment, artifact, registered model và alias khác nhau thế nào.
- Model reproducibility cần nhiều hơn một file model.

#### Triển khai

1. Thêm một PostgreSQL metadata service dành cho MLflow/Optuna, tách database và
   user theo least privilege.
2. Thêm MLflow server; metadata ở PostgreSQL, artifacts ở MinIO.
3. Tạo helper logging dùng chung cho mọi model family.
4. Log bắt buộc:
   - Git SHA và dirty-worktree flag;
   - environment/lock hash;
   - dataset manifest/hash;
   - feature/split/label-policy versions;
   - config đầy đủ;
   - seed và resource limits;
   - metrics theo split/segment;
   - fit/predict duration và memory;
   - model signature, input example và artifact.
5. Tạo prediction reload-parity test.

#### Exit criteria

- Restart MLflow không mất metadata/artifacts.
- Một run có thể tải lại exact model và tái tạo prediction trong tolerance.
- Run thiếu required metadata không đủ điều kiện register.

### M6 — Baseline models và evaluation framework

#### Mục tiêu học

- Baseline, preprocessing pipeline, class imbalance và metric selection.
- Ranking quality khác probability quality và decision quality.

#### Model ladder

1. `DummyClassifier(strategy="prior")`.
2. Business rule baseline.
3. Logistic Regression có regularization và class weights.
4. `HistGradientBoostingClassifier`.

#### Evaluation contract

| Mục đích | Metrics |
|---|---|
| Ranking | AUPRC/Average Precision; ROC-AUC chỉ là phụ |
| Alert operations | Precision@k, Recall@k, fraud amount recall@k |
| Capacity | alerts/hour, false positives/day |
| Classification | confusion matrix, F2, MCC tại policy đã chọn |
| Probability | Brier score, log loss, calibration bins |
| Robustness | metric theo time/type/amount/activity segment |
| Runtime | fit time, score throughput, peak memory |

#### Triển khai

1. Tạo model interface chung: `fit`, `predict_score`, `save`, `load`.
2. Fit preprocessing chỉ trên train.
3. Tạo walk-forward validation folds từ config đã khóa.
4. Tạo bootstrap confidence interval theo time block, không bootstrap row độc
   lập nếu phá temporal dependence.
5. Log PR curve, score distribution, error slices và resource metrics.
6. Viết model card cho Logistic Regression baseline.

#### Exit criteria

- Baseline chạy được end-to-end từ immutable snapshot tới MLflow.
- Metrics có unit tests với hand-calculated fixture.
- Test split vẫn khóa.
- Logistic model coefficients được map về business feature names.

### M7 — Multi-library tree benchmark

#### Mục tiêu học

- Bagging/boosting, leaf-wise/level-wise growth, categorical handling và early
  stopping.
- So sánh model công bằng trên cùng data/split/metric/resource budget.

#### Models

- HistGradientBoosting.
- XGBoost.
- LightGBM.
- CatBoost.

#### Benchmark protocol

1. Dùng cùng feature set V1 và benchmark snapshot.
2. Dùng fixed seed và giới hạn tối đa 8 CPU threads/model.
3. Chọn reasonable defaults và một search rất nhỏ; chưa chạy full tuning.
4. Early stopping chỉ nhìn validation fold.
5. Log:
   - mean/fold AUPRC;
   - recall và precision tại alert budget;
   - calibration trước calibration step;
   - train/inference time;
   - peak RAM;
   - serialized size;
   - segment regressions.
6. Shortlist tối đa hai tree libraries để tuning sâu.

#### Exit criteria

- Có model comparison report giải thích trade-off, không chỉ bảng metric.
- Chênh lệch metric có confidence interval hoặc stability evidence.
- Shortlist được chọn bằng tiêu chí đã định trước.

### M8 — Feature selection, ablation và graph features V2

#### Mục tiêu học

- Feature importance không đồng nghĩa causal importance.
- Ablation study, redundancy, stability và feature cost.
- Graph concepts áp dụng được mà chưa cần GNN.

#### Triển khai

1. Ablate từng feature group V1.
2. Đo permutation importance và SHAP stability giữa temporal folds.
3. Nhóm correlated/redundant features; ưu tiên feature dễ giải thích và ổn định.
4. Không dùng recursive feature elimination trên full dataset nếu chi phí quá
   lớn.
5. Tạo point-in-time graph features:
   - prior in/out degree;
   - unique counterparties;
   - fan-in/fan-out;
   - shared-destination count;
   - rapid fund-flow chain indicators;
   - counterparty concentration;
   - rolling net-flow ratio.
6. Tạo feature version V2 và chạy V1-vs-V2 comparison.

#### Exit criteria

- Mỗi feature group có measured lift/cost/stability.
- Graph feature không dùng future edge.
- Feature set cuối được khóa trước full tuning.

### M9 — Hyperparameter tuning với Optuna

#### Mục tiêu học

- Search space design, sampling, pruning, overfitting vào validation và compute
  budgeting.
- Vì sao nhiều trials không tự động tạo model tốt hơn.

#### Tuning strategy

1. Tune hai tree models đã shortlist.
2. Objective chính: mean walk-forward AUPRC.
3. Log secondary constraints:
   - minimum recall@budget;
   - no severe segment regression;
   - maximum fit time/RAM.
4. Dùng seeded TPE.
5. Dùng library-compatible pruning/early stopping.
6. Mỗi trial là nested MLflow run.
7. Study lưu PostgreSQL và resume được.
8. Chạy tuần tự; không parallel nhiều model trên máy 8 GB RAM.

#### Compute budgets

| Cấp | Trial budget | Mục đích |
|---|---:|---|
| Smoke | 3–5/model | Test objective/search space |
| Benchmark | 15–25/model | Thu hẹp search |
| Final | tối đa 40–60/model | Tuning có kiểm soát |

Không dùng test metric trong objective. Không giữ mọi model artifact của trial
thua nếu gây đầy MinIO; giữ params/metrics và top-N artifacts.

#### Deliverables

- Search-space YAML cho từng model.
- Optimization history.
- Hyperparameter importance.
- Parallel-coordinate plot.
- Trial failure/OOM report.
- Best-config files không phụ thuộc trực tiếp vào Optuna database.

#### Exit criteria

- Study resume được sau interruption.
- Best trial được retrain từ config độc lập và cho metric parity.
- Tuning report chỉ ra tham số nào có tác động và dấu hiệu overfitting.

### M10 — Calibration và alert decision policy

#### Mục tiêu học

- Discrimination khác calibration.
- Threshold, top-k và analyst capacity là business policy, không phải model
  hyperparameter.

#### Triển khai

1. Dành calibration window riêng sau training window.
2. So sánh uncalibrated, sigmoid/Platt và isotonic.
3. Không fit calibrator trên prediction in-sample.
4. Đánh giá reliability diagram, Brier/log loss và stability theo time.
5. Tạo policy versions:
   - fixed threshold;
   - top-k mỗi hour;
   - hybrid minimum score + capacity cap.
6. Báo cáo sensitivity ở nhiều capacity levels.
7. Chốt deterministic tie-break.

#### Exit criteria

- Model artifact và policy artifact có version riêng.
- Calibration cải thiện reliability mà không làm ranking contract sai.
- Policy được chọn trên validation/calibration, không trên test.

### M11 — Deep-learning challenger bằng PyTorch

#### Mục tiêu học

- Dataset/DataLoader, mini-batch optimization, regularization, embeddings,
  weighted loss, focal loss, early stopping và GPU memory.
- Hiểu vì sao deep learning có thể không thắng gradient boosting trên tabular
  data.

#### Model V1

- MLP cho numeric features.
- Embedding chỉ cho low-cardinality fields như transaction type/time bucket.
- Không embedding raw account IDs.
- Batch normalization hoặc layer normalization được coi là experiment.
- Weighted BCE là loss chính; focal loss là controlled comparison.

#### Triển khai

1. Tạo dataset reader từ Parquet theo batch.
2. Fit numeric preprocessing chỉ trên train.
3. Tạo training loop có:
   - fixed seeds;
   - early stopping;
   - gradient clipping;
   - checkpoint best validation state;
   - AMP nếu CUDA pass numerical parity;
   - CPU fallback.
4. Log epoch metrics/checkpoints vào MLflow.
5. Dùng Optuna budget nhỏ cho hidden dimensions, dropout, learning rate,
   weight decay và batch size.
6. So sánh với tree champion trên cùng final candidate features.

#### Resource guards

- Bắt đầu batch size nhỏ; tự động giảm batch nếu CUDA OOM một lần.
- Không chạy nhiều DL trials song song.
- DataLoader không spawn quá nhiều workers trên WSL.
- Ghi peak VRAM/RAM và training time.

#### Exit criteria

- Checkpoint reload cho prediction parity.
- CPU và GPU prediction nằm trong numerical tolerance.
- Báo cáo giải thích model thắng/thua ở metric, stability và cost.
- Deep model không được chọn chỉ vì phức tạp hơn.

### M12 — Anomaly detection và final model selection

#### Mục tiêu học

- Supervised fraud detection khác unsupervised anomaly detection.
- Anomaly không đồng nghĩa fraud.
- Champion selection cần nhiều quality gates.

#### Triển khai

1. Fit Isolation Forest trên feature subset phù hợp.
2. Đánh giá anomaly score như tín hiệu riêng.
3. Thử hai phương án có kiểm soát:
   - hiển thị anomaly score cho analyst;
   - dùng anomaly score làm feature của supervised model, chỉ khi point-in-time
     và train-only fit được đảm bảo.
4. Không blend score thủ công nếu chưa có validation evidence.
5. Khóa model family, feature version, calibration và policy.
6. Mở test đúng một lần cho final comparison.

#### Promotion gates

```text
data_quality_passed
AND snapshot_integrity_passed
AND point_in_time_tests_passed
AND leakage_audit_passed
AND validation_auprc_beats_baseline
AND recall_at_budget_meets_floor
AND calibration_within_tolerance
AND no_severe_segment_regression
AND serialization_parity_passed
AND resource_budget_passed
AND human_approval
```

#### Exit criteria

- Có final evaluation report và model card.
- Test result không được dùng để quay lại tune cùng test set.
- Champion được chọn bằng evidence; có thể là Logistic Regression, tree hoặc
  PyTorch.

### M13 — Explainability, registry và batch scoring

#### Mục tiêu học

- Global importance, local attribution, reason code và causal explanation khác
  nhau.
- Registry alias, immutable model version và rollback.

#### Triển khai

1. Dùng SHAP phù hợp với champion model; background sample có fixed seed.
2. Kiểm tra output space và SHAP additivity.
3. Tạo global artifacts theo fold/segment.
4. Chuyển top local attributions thành versioned business reason codes.
5. Không lưu raw account ID trong explanation artifact.
6. Register exact evaluated artifact vào MLflow.
7. Dùng aliases `candidate`, `challenger`, `champion`.
8. Batch scorer:
   - resolve alias thành exact version trước run;
   - validate input signature/feature version;
   - đọc bounded batches;
   - ghi score, decision, reason codes và lineage;
   - idempotent theo event/model/feature/policy version;
   - fail closed nếu artifact không tải được.

#### Score contract

```text
event_id
prediction_score
calibrated_probability
risk_band
alert_decision
anomaly_score
top_reason_codes
model_name
model_version
feature_version
calibration_version
policy_version
dataset_version
scorer_git_sha
scored_at
```

#### Exit criteria

- Một score trace được về input event, feature, snapshot, code và exact model.
- Rerun cùng version không tạo duplicate.
- Rollback chỉ chuyển alias; không xóa prediction history.

### M14 — Local LLM Fraud Case Copilot và Streamlit

#### Mục tiêu học

- Grounded generation, structured output, hallucination evaluation và
  human-in-the-loop.
- Phân biệt model prediction với natural-language explanation.

#### LLM architecture

```text
Streamlit case request
  → deterministic ClickHouse case query
  → redact/hash identifiers
  → structured evidence package
  → Ollama local instruct model
  → Pydantic JSON validation
  → evidence/citation checks
  → rendered case summary
```

Không cần RAG/vector database. Context được lấy bằng deterministic queries từ
transaction, historical aggregates, graph signals, model score và reason codes.

#### Local model selection

1. Chọn 2–3 small instruct models quantized có thể chạy trong giới hạn máy.
2. Benchmark tại thời điểm triển khai thay vì hard-code model name lâu dài.
3. Đo:
   - schema-valid rate;
   - evidence coverage;
   - unsupported-claim rate;
   - latency;
   - RAM/VRAM.
4. Chọn model nhỏ nhất đạt quality gate.
5. Temperature mặc định 0 và structured JSON schema.

#### Output schema

```text
case_summary
risk_factors[]
supporting_evidence[]
related_activity[]
suggested_investigation_steps[]
uncertainty_and_limitations[]
source_event_ids[]
prompt_version
local_model_name
```

LLM không được:

- thay đổi `prediction_score` hoặc `alert_decision`;
- tuyên bố fraud đã được xác nhận nếu label chưa mature;
- thêm số liệu không có trong evidence package;
- hiển thị raw account identifier;
- tự động thực hiện hành động bên ngoài hệ thống.

#### LLM evaluation

Tạo ít nhất 50 cases gồm:

- true positive/false positive/false negative/true negative;
- score cao nhưng anomaly thấp và ngược lại;
- cold-start;
- missing/inconsistent balance;
- graph pattern;
- insufficient evidence;
- Ollama timeout hoặc malformed output.

Mỗi case kiểm tra schema, evidence citation, factual consistency, uncertainty và
forbidden claims. LLM eval report được version hóa theo prompt/model.

#### Streamlit pages

1. **Portfolio Overview** — architecture, dataset limits và demo flow.
2. **Model Lab** — run comparison, PR/calibration/segment plots.
3. **Alert Queue** — filter/rank theo score, amount, type và reason.
4. **Case Investigation** — history, graph signals, SHAP reasons và copilot.
5. **Monitoring** — data/model/policy health.

#### Exit criteria

- App vẫn hiển thị deterministic evidence khi Ollama unavailable.
- Copilot output luôn qua Pydantic validation.
- Unsupported-claim rate đạt threshold đã định trước.
- Người dùng nhìn rõ đâu là model evidence và đâu là LLM-generated text.

### M15 — Monitoring, feedback loop và end-to-end demo

#### Mục tiêu học

- Data drift, concept drift, delayed performance và retraining trigger.
- Monitoring có hành động khác dashboard trang trí.

#### Triển khai

1. Data monitoring:
   - freshness;
   - schema/null/range;
   - duplicate/reconciliation;
   - feature distribution.
2. Model monitoring:
   - score distribution;
   - alert volume;
   - calibration;
   - mature-cohort AUPRC/precision/recall@budget;
   - segment regressions.
3. System monitoring:
   - scoring throughput/failure;
   - MLflow/MinIO availability;
   - Ollama latency/schema failures.
4. Feedback contract:
   - analyst outcome;
   - observed time;
   - label source/version;
   - correction history.
5. Drift chỉ mở investigation/retraining recommendation; không auto-retrain,
   auto-promote hoặc auto-rollback.
6. Tạo reproducible end-to-end demo script.

#### Exit criteria

- Demo trace được một transaction từ canonical data tới score, reasons, copilot
  summary và delayed evaluation.
- Monitoring metric có definition, window, threshold, owner và response action.
- Restart services không làm mất MLflow/Optuna metadata hoặc artifacts.
- README đủ để một người khác chạy smoke demo từ clean checkout.

## 6. Tuning curriculum chi tiết

Vì tuning là trọng tâm học tập, mỗi model phải đi qua các bước sau:

1. Hiểu hyperparameter bằng một-variable-at-a-time experiment nhỏ.
2. Xác định search space từ learning curve và model behavior, không copy space
   từ Internet.
3. Chạy random/TPE smoke study để bắt lỗi.
4. Vẽ optimization history và parameter importance.
5. Kiểm tra trial failures, OOM và overfitting.
6. Thu hẹp search space có lý do.
7. Retrain best config ngoài Optuna objective.
8. So sánh best-tuned với strong default; tuning phải chứng minh lift.
9. Đánh giá stability qua temporal folds.
10. Ghi bài học vào experiment report.

Search-space anti-patterns:

- range quá rộng không có log scale;
- tune parameter không ảnh hưởng model;
- thay feature/split giữa trials;
- dùng test metric làm objective;
- chọn trial bằng một metric rồi bỏ qua constraints;
- parallelism làm thiếu RAM và khiến comparison không công bằng;
- coi Optuna `best_trial` là production model.

## 7. Feature-engineering curriculum chi tiết

Mỗi feature proposal phải có:

```text
name
business hypothesis
entity/grain
source columns
availability time
lookback window
SQL definition
null/cold-start policy
expected direction
leakage risk
compute cost
validation test
version
```

Quy trình feature experiment:

1. Viết hypothesis trước.
2. Implement point-in-time SQL.
3. Chạy contract/temporal tests.
4. Profile distribution và nulls.
5. Benchmark incremental lift trên validation.
6. Kiểm tra stability theo time/segment.
7. Ablate để xác nhận đóng góp.
8. Giữ, sửa hoặc loại bỏ bằng evidence.

Không dùng feature importance duy nhất để quyết định feature. Phải kết hợp
business validity, point-in-time correctness, stability, compute cost và model
lift.

## 8. Test strategy

### Unit tests

- Config/schema parsing.
- Temporal split.
- Metric và alert-budget calculations.
- Calibration wrapper.
- Model save/load.
- Reason-code mapping.
- LLM output validation.

### Data/contract tests

- dbt uniqueness/not-null/relationships.
- Feature registry khớp physical schema.
- Snapshot manifest/hash.
- Model input signature.
- Score schema.

### Temporal/leakage tests

- Future event invariance.
- Future label isolation.
- Preprocessing train-only fit.
- Duplicate không qua nhiều split.
- Same-timestamp deterministic ordering.

### ML validation tests

- Model tốt hơn dummy bằng minimum margin.
- Prediction finite và nằm trong range.
- Metric reproducible trong tolerance.
- Serialization parity.
- No severe segment regression.

### Integration tests

- Snapshot → train → MLflow.
- Registry → score → ClickHouse.
- Score/reasons → Streamlit.
- Evidence → Ollama → validated JSON.

### CI policy

GitHub Actions chỉ chạy smoke data và small model fixtures. Full ClickHouse,
full training, GPU, Ollama và end-to-end tests chạy local theo documented
commands; không giả vờ CI free runner đại diện cho full environment.

## 9. Resource và cost controls

- Model training threads mặc định tối đa 8 để giữ máy responsive.
- Optuna trials chạy tuần tự.
- Chỉ giữ top-N large trial artifacts.
- Snapshot và MLflow artifacts có retention policy.
- Smoke tests không khởi động toàn bộ stack nếu không cần.
- PyTorch bắt đầu bằng small batch và có CPU fallback.
- Ollama chỉ load một model tại một thời điểm.
- Tách service profiles để không chạy Airflow, MLflow, Streamlit và Ollama cùng
  lúc khi milestone không cần.
- Ghi wall time, CPU/RAM/GPU peak cho benchmark quan trọng.

## 10. Command contract mục tiêu

Tên command có thể được triển khai dần nhưng semantics phải ổn định:

```bash
# Data quality và features
./scripts/dbt.sh build
uv run python scripts/build_training_snapshot.py --config configs/data/smoke.yaml

# Baseline và benchmark
uv run python scripts/train.py \
  --model configs/models/logistic.yaml \
  --data configs/data/benchmark.yaml

uv run python scripts/evaluate.py --run-id <run_id>

# Tuning
uv run python scripts/tune.py \
  --model lightgbm \
  --config configs/tuning/lightgbm.yaml

# Deep learning
uv run python scripts/train.py \
  --model configs/models/pytorch_mlp.yaml \
  --data configs/data/benchmark.yaml

# Promotion và scoring
uv run python scripts/promote.py --run-id <run_id> --alias candidate
uv run python scripts/score.py --model-alias champion

# Monitoring và application
uv run python scripts/monitor.py --model-alias champion
uv run streamlit run streamlit_app/app.py

# Quality
uv run pytest
uv run ruff check .
uv run mypy ml/src
```

## 11. Definition of Done cho toàn dự án

### Data và features

- Canonical grain và delayed-label semantics được test.
- Feature set point-in-time correct và versioned.
- Immutable snapshot có manifest/hash và build reproducible.

### ML

- Có dummy, rule, linear, nhiều tree libraries, deep learning và anomaly
  experiments.
- Model comparison dùng temporal folds và cùng resource/evaluation contract.
- Tuning có resumable study, pruning, report và retrain parity.
- Test chỉ được mở sau khi model/feature/policy khóa.
- Champion có calibration, policy, model card và segment analysis.

### MLOps

- Mọi run trace được về dataset/feature/split/code/config.
- Registry load/reload/rollback pass.
- Scoring idempotent và có full lineage.
- Monitoring dùng mature-label cohorts.

### LLM và application

- Ollama chạy local, không cần paid API.
- Copilot grounded trên deterministic evidence và structured output.
- LLM eval suite kiểm tra factuality/unsupported claims.
- Streamlit có model lab, alert queue, case investigation và monitoring.

### Engineering

- Unit/contract/temporal/integration tests phù hợp đều pass.
- Secret, dataset, model binary và generated artifacts không nằm trong Git.
- Clean-checkout smoke guide hoạt động.
- Tài liệu nói rõ PaySim là synthetic và không chứng minh production banking
  performance.

## 12. Những điều không được dùng làm bằng chứng thành công

- Accuracy cao trên imbalanced dataset.
- ROC-AUC cao nhưng precision/recall@budget thấp.
- Random split đẹp hơn temporal split.
- Tuning trên test set.
- Một SHAP plot không có stability/leakage review.
- Deep model phức tạp nhưng không thắng strong tree baseline.
- LLM summary nghe thuyết phục nhưng không cite evidence.
- Dashboard đẹp nhưng model/data lineage không truy được.
- Claim “production-ready banking fraud” dựa trên PaySim synthetic.

## 13. Tài liệu chính thức nên dùng khi triển khai

- scikit-learn model selection và metrics:
  <https://scikit-learn.org/stable/model_selection.html>
- scikit-learn probability calibration:
  <https://scikit-learn.org/stable/modules/calibration.html>
- XGBoost Python/scikit-learn interface:
  <https://xgboost.readthedocs.io/en/stable/python/>
- LightGBM Python API:
  <https://lightgbm.readthedocs.io/en/stable/Python-API.html>
- CatBoost documentation:
  <https://catboost.ai/docs/>
- PyTorch documentation:
  <https://docs.pytorch.org/docs/stable/>
- Optuna:
  <https://optuna.readthedocs.io/en/stable/>
- MLflow traditional ML:
  <https://mlflow.org/docs/latest/ml/traditional-ml/>
- SHAP:
  <https://shap.readthedocs.io/en/latest/>
- Polars Lazy API:
  <https://docs.pola.rs/user-guide/lazy/>
- Ollama structured outputs:
  <https://docs.ollama.com/capabilities/structured-outputs>
- Streamlit:
  <https://docs.streamlit.io/>
- dbt data tests:
  <https://docs.getdbt.com/docs/build/data-tests>

## 14. Việc bắt đầu ngay

Chỉ bắt đầu M0. Không cài toàn bộ ML stack và dựng mọi service trong một lần.

Thứ tự phiên làm việc tiếp theo:

1. Khôi phục Docker integration trong WSL.
2. Chốt dependency groups và scaffold `fraudguard_ml`.
3. Thêm config/test/quality foundation.
4. Chạy development gate.
5. Chuyển sang M1 và hoàn thiện canonical dbt models.

Khi M1 chưa pass, chưa train model “thử cho biết”. Một model học từ grain sai,
duplicate hoặc future label chỉ tạo ra metric đẹp nhưng không tạo ra kiến thức
ML đáng tin cậy.
