# Đánh giá FraudGuard so với RecSys-MLops và đề xuất cải tiến

## 1. Mục đích và phạm vi

Tài liệu này đối chiếu dự án FraudGuard hiện tại với repository tham khảo
[RecSys-MLops](https://github.com/itsmekhoathekid/RecSys-MLops), tập trung vào
những cách làm tốt có thể áp dụng hợp lý thay vì sao chép toàn bộ kiến trúc.

Phạm vi đánh giá:

- Phần Data giữ nguyên các thành phần chính của FraudGuard: Kafka, Schema
  Registry, Spark, MinIO, Airflow, ClickHouse và dbt.
- Phần Data chỉ đề xuất hoàn thiện governance, ownership, data contract, data
  quality, lineage, bảo mật, retention và khả năng audit.
- Phần ML được phép bổ sung công nghệ nếu giải quyết được một khoảng trống thật
  sự của FraudGuard.
- Notebook, training pipeline, model registry, API serving, monitoring, CI/CD và
  kiểm thử được đánh giá riêng theo mức độ phù hợp với bài toán fraud detection.

Snapshot được dùng khi đánh giá:

- FraudGuard: working tree hiện tại, commit gần nhất `410dac5` ngày 2026-08-03.
  Working tree đang có thay đổi chưa commit, vì vậy đánh giá phản ánh cả trạng
  thái đang phát triển chứ không chỉ commit cuối.
- RecSys-MLops: commit
  [`e99df9d14ed8da75285990eee17028dc3b06ccc1`](https://github.com/itsmekhoathekid/RecSys-MLops/tree/e99df9d14ed8da75285990eee17028dc3b06ccc1)
  ngày 2026-08-04.

Hai dự án khác domain. RecSys tối ưu việc xếp hạng nhiều sản phẩm cho một người
dùng; FraudGuard dự đoán rủi ro của một giao dịch hiếm và có chi phí sai lệch
rất bất đối xứng. Vì vậy, kiến trúc vận hành có thể học hỏi, nhưng feature,
model, metric và cách rollout không thể bê nguyên từ RecSys.

## 2. Kết luận điều hành

FraudGuard đã có một data foundation tốt hơn mức thường thấy ở một dự án ML cá
nhân: ingestion theo event, Avro schema, quarantine, quality manifest, canonical
record, xử lý replay/conflict, tách transaction khỏi final label, dbt mart cho
training, temporal split, training-data contract, reproducibility metadata và
unit test. Điểm mạnh này nên được giữ nguyên.

Khoảng trống chính là FraudGuard mới hoàn thành phần chuẩn bị dữ liệu cho ML,
nhưng chưa hoàn thành vòng đời ML:

1. Chưa có quyết định rõ hệ thống dự đoán trước khi giao dịch được ghi sổ hay
   phát hiện sau khi ghi sổ. Đây là quyết định quan trọng nhất vì nó xác định
   feature nào hợp lệ và API phải đáp ứng latency nào.
2. Có cấu hình `fraudguard_logistic_baseline` và challenger nhưng chưa có code
   train/evaluate model thực tế.
3. Chưa có bộ metric phù hợp với fraud, threshold policy, calibration, error
   analysis và model acceptance gate.
4. Chưa có experiment tracking, model registry, model package và quy tắc
   promotion/rollback.
5. Chưa có scoring API hoặc asynchronous scoring consumer.
6. Chưa có monitoring cho prediction, drift, delayed label, model performance
   và operational latency.
7. Chưa có CI ở cấp repository và chưa có test cho feature/model/API.
8. Notebook hiện mới bao phủ EDA/audit, chưa bao phủ experiment, threshold và
   error analysis.

Khuyến nghị tổng quát:

- Làm một ML vertical slice nhỏ nhưng hoàn chỉnh trước: data contract → train →
  evaluate → package → register → score → monitor.
- Dùng Airflow hiện có để orchestration training ở giai đoạn đầu. Không cần
  Kubeflow hoặc Ray ngay.
- Bổ sung scikit-learn và MLflow trước; FastAPI chỉ trở thành ưu tiên cao nếu
  mục tiêu là synchronous/near-real-time fraud scoring.
- Không thêm Feast, Redis, Triton, KServe hoặc Kubernetes chỉ để giống repo mẫu.
  Chỉ thêm khi có yêu cầu online feature freshness, throughput, autoscaling hoặc
  nhiều model đủ lớn để biện minh chi phí vận hành.

## 3. Bảng đối chiếu nhanh

| Năng lực | FraudGuard hiện tại | RecSys-MLops | Đánh giá khoảng trống |
| --- | --- | --- | --- |
| Event ingestion | Kafka → Spark → MinIO | PostgreSQL/CDC/Kafka → Spark/Flink/lakehouse | FraudGuard đã đủ tốt cho phạm vi hiện tại |
| Schema contract | Avro + Schema Registry | Contract, catalog và validation nhiều lớp | FraudGuard mạnh ở schema kỹ thuật, còn thiếu governance policy |
| Data quality | Quarantine, manifest, dbt tests, eligibility/exclusion | Runtime validation, assertion publication và dashboard | Nên bổ sung SLO, owner, cảnh báo và lịch sử quality |
| Data lineage | Kafka/MinIO/ClickHouse metadata + dbt graph | Runtime OpenLineage + DataHub | Giữ stack; hoàn thiện lineage bằng dbt/Airflow metadata trước |
| Training dataset | Có mart và strict contract | Có point-in-time feature retrieval và dataset lineage | FraudGuard mạnh ở contract, thiếu versioned training snapshot |
| EDA/notebook | Một notebook EDA/audit | Ba notebook `.ipynb` và helper scripts | Nên thêm notebook modeling và error analysis, không cần nhiều notebook rời rạc |
| Training code | Chưa có estimator/training loop | Có model, dataset, trainer, CLI và distributed training | Khoảng trống ưu tiên cao nhất sau leakage contract |
| Evaluation | Chưa có model metrics/gates | Có offline metrics và promotion gate | Cần metric riêng cho fraud, không dùng ranking metrics của RecSys |
| Experiment tracking | Chưa có | MLflow | Nên thêm sớm |
| Model registry | Chưa có | MLflow + registry metadata | Nên thêm sau khi có training pipeline chạy được |
| Serving | Chưa có | FastAPI + Feast + Triton | FastAPI phù hợp; Feast/Triton chưa cần ở giai đoạn đầu |
| Model monitoring | Chưa có | Metrics, logs, traces, drift và retraining trigger | Nên bắt đầu bằng ClickHouse + Airflow, mở rộng sau |
| CI/CD | Chưa thấy workflow CI | Jenkins với test, build, deploy, shadow/A-B/rollback | Cần CI tối thiểu; rollout nâng cao để giai đoạn sau |
| Test strategy | ML contract tests + dbt tests | Unit, contract, integration, E2E, load, property/mutation | Cần mở rộng theo feature/model/API |
| Documentation | Chưa có root README; tài liệu còn phân tán | README, architecture, design và operations rất chi tiết | Nên bổ sung tài liệu kiến trúc và runbook sớm |

## 4. Những điểm tốt của FraudGuard cần giữ lại

### 4.1 Tách transaction và label

FraudGuard dùng hai schema/event stream riêng cho transaction và final label:

- [`fraud_transaction.avsc`](schemas/fraud_transaction.avsc)
- [`fraud_transaction_label.avsc`](schemas/fraud_transaction_label.avsc)

Đây là thiết kế đúng cho fraud detection vì label thường đến chậm hơn sự kiện
giao dịch. Việc tách label giúp mô phỏng đúng delayed feedback, tránh vô tình đưa
`isFraud` hoặc `isFlaggedFraud` vào request inference và hỗ trợ backfill label.

### 4.2 Landing có quarantine và quality evidence

Spark landing kiểm tra event time, ingestion time, step và label domain; record
không hợp lệ được đưa vào quarantine, đồng thời ghi quality manifest. Đây là nền
tảng tốt cho audit và data-quality SLO:

- [`event_kafka_minio.py`](spark/jobs/event_kafka_minio.py)
- [`labels_kafka_minio.py`](spark/jobs/labels_kafka_minio.py)
- [`kafka_minio_landing.py`](spark/jobs/kafka_minio_landing.py)

### 4.3 Canonicalization và replay handling rõ ràng

Các dbt model giữ metadata Kafka/MinIO/ClickHouse, xếp hạng physical records,
phát hiện duplicate và payload conflict trước khi chọn canonical transaction.
Điều này rất phù hợp với hệ thống event-driven, nơi replay là hành vi bình
thường chứ không nhất thiết là lỗi.

### 4.4 Training eligibility có lý do loại trừ

[`ml_training_candidates.sql`](dbt/models/marts/ml/ml_training_candidates.sql)
không chỉ lọc dữ liệu mà gán một `training_exclusion_reason` xác định cho mỗi
candidate. Cách làm này tốt hơn một `WHERE` âm thầm loại bản ghi vì có thể
reconcile và audit vì sao training population thay đổi.

### 4.5 Training-data contract chặt chẽ

[`training_data_contract.yml`](configs/training_data_contract.yml) và
[`training_data_contract.py`](ml/src/fraudguard_ml/training_data_contract.py)
kiểm tra schema chính xác, primary key, source, target domain, lineage và các
feature bị cấm. Đây là một ưu điểm lớn, đặc biệt khi model chưa được viết: data
boundary đã có tính kỷ luật từ trước.

### 4.6 Temporal split và reproducibility đã được nghĩ tới

Hai cấu hình baseline/challenger đều khai báo temporal split, random seed và
feature allowlist. Package cũng đã có runtime metadata, seeding, atomic artifact
writer và unit test. Những phần này nên trở thành nền móng của training pipeline,
không nên viết lại trong notebook.

## 5. Những điểm tốt của RecSys-MLops nên học hỏi

### 5.1 Chia repository theo deployable capability

Repo mẫu chia `apps/data-platform`, `apps/analytics`, `apps/ml-system` và
`apps/api-serving`, bên cạnh `infra`, `ops`, `tests` và `docs`. Cấu trúc này làm
rõ code nào thuộc training, serving, data processing hay operations. Xem
[cấu trúc repository trong README](https://github.com/itsmekhoathekid/RecSys-MLops/blob/e99df9d14ed8da75285990eee17028dc3b06ccc1/README.md).

FraudGuard chưa cần tái cấu trúc lớn ngay, nhưng nên tạo boundary rõ giữa:

- reusable ML package;
- notebook exploration;
- training orchestration;
- scoring service;
- monitoring jobs;
- model artifacts.

### 5.2 Notebook liên kết với production code

Notebook `ml.ipynb` của repo mẫu gọi lại dataset/trainer từ `apps/ml-system`
thay vì tạo một implementation hoàn toàn riêng. Đây là nguyên tắc đáng học:
notebook dùng để trình bày, khám phá và phân tích; business logic cần test được
nằm trong Python package.

Repo mẫu cũng cho thấy số lượng notebook không tự động đồng nghĩa với chất
lượng: `notebook.ipynb` chỉ đọc dữ liệu và gọi `head/info`, trong khi
`explore.ipynb` chứa prototype dài. Vì vậy FraudGuard không nên tạo nhiều
notebook chỉ để tăng số lượng hoặc copy code giữa các notebook.

### 5.3 Training là một application có CLI và artifact contract

Repo mẫu có model, dataset, trainer, training entry point, config, checkpoint,
metric output, dataset lineage và MLflow logging. Xem
[`train.py`](https://github.com/itsmekhoathekid/RecSys-MLops/blob/e99df9d14ed8da75285990eee17028dc3b06ccc1/apps/ml-system/src/training/train.py).

Điểm đáng học không phải mô hình BST, mà là contract của một training run:

- nhận config và dataset version rõ ràng;
- xuất metrics có cấu trúc;
- xuất immutable model artifact;
- ghi code/data/config lineage;
- có candidate version;
- chỉ promote khi vượt acceptance gate.

### 5.4 API có production contract tối thiểu

Hai FastAPI service của repo mẫu có Pydantic request/response, lifecycle,
`/healthz`, `/ready`, `/version`, `/metrics`, timeout, dependency injection và
test bằng fake client/ranker. Xem
[`inference API`](https://github.com/itsmekhoathekid/RecSys-MLops/blob/e99df9d14ed8da75285990eee17028dc3b06ccc1/apps/api-serving/inference-api/src/recsys_inference_api/app.py)
và
[`serving contracts`](https://github.com/itsmekhoathekid/RecSys-MLops/blob/e99df9d14ed8da75285990eee17028dc3b06ccc1/apps/api-serving/shared/src/recsys_serving_common/contracts.py).

FraudGuard có thể học trực tiếp các nguyên tắc này mà chưa cần dùng Triton,
KServe hoặc feature store.

### 5.5 Experiment tracking, registry và promotion là một flow thống nhất

Repo mẫu nối training metrics, artifact URI, MLflow run, model version và
promotion. Kubeflow pipeline còn có các stage prepare, train/tune, evaluate và
promote. Xem
[`bst_training_pipeline.py`](https://github.com/itsmekhoathekid/RecSys-MLops/blob/e99df9d14ed8da75285990eee17028dc3b06ccc1/apps/ml-system/src/kubeflow/pipelines/bst_training_pipeline.py).

FraudGuard nên học stage boundary và gate, nhưng triển khai bằng Python CLI +
Airflow trước để tận dụng stack sẵn có.

### 5.6 Test pyramid và operational verification

Repo mẫu có unit, contract, integration, E2E và load tests; API, model promotion,
repository layout và deployment policies đều có test. Đây là ưu điểm lớn hơn
bản thân số lượng công nghệ. Tham khảo
[`tests`](https://github.com/itsmekhoathekid/RecSys-MLops/tree/e99df9d14ed8da75285990eee17028dc3b06ccc1/tests).

### 5.7 Governance và observability được coi là sản phẩm

Repo mẫu mô tả owner/contract/validation/lineage, ghi assertion và runtime
lineage; serving ghi metrics, structured log và trace. Tham khảo
[`data_governance.md`](https://github.com/itsmekhoathekid/RecSys-MLops/blob/e99df9d14ed8da75285990eee17028dc3b06ccc1/docs/submission/rubic-%28mini-coursework%29/data_governance.md)
và
[`observability.py`](https://github.com/itsmekhoathekid/RecSys-MLops/blob/e99df9d14ed8da75285990eee17028dc3b06ccc1/apps/api-serving/shared/src/recsys_serving_common/observability.py).

## 6. Những phần không nên sao chép nguyên trạng

### 6.1 Không nên đưa toàn bộ platform vào local FraudGuard

RecSys-MLops dùng Kubernetes, Helm, Terraform, Jenkins, Kubeflow, Ray, Feast,
Redis, MLflow, Triton, KServe, KEDA, Istio, Vault, Prometheus, Grafana, Loki và
Tempo. Đây là một platform có chi phí vận hành lớn. Đưa tất cả vào FraudGuard
trước khi có một model chạy end-to-end sẽ làm chậm tiến độ và che lấp rủi ro ML
cốt lõi như leakage, calibration và threshold.

### 6.2 Feature store chưa phải khoảng trống cấp bách

FraudGuard hiện có tập feature nhỏ và training source tập trung trong
ClickHouse/dbt. Feast chỉ đáng thêm khi:

- có feature aggregate theo tài khoản cần dùng giống nhau ở training và online;
- freshness ở mức giây/phút là bắt buộc;
- xuất hiện training-serving skew;
- nhiều model/service cùng tái sử dụng feature;
- cần point-in-time join phức tạp.

Trước thời điểm đó, một feature builder dùng chung và strict request schema sẽ
đơn giản hơn nhiều.

### 6.3 Triton/KServe chưa phù hợp với model baseline

Logistic regression hoặc gradient-boosted trees có thể phục vụ tốt bằng một
FastAPI process tải immutable model bundle. Triton/KServe chỉ hợp lý khi model
lớn, có GPU, multi-model serving, batching hoặc throughput cao đến mức một
Python service không đáp ứng SLA.

### 6.4 Ray/Kubeflow chưa có lợi ích tương xứng

Dataset PaySim khoảng vài triệu dòng và model tabular có thể train trên một máy.
Airflow đã tồn tại và đủ để orchestrate validate → train → evaluate → register.
Ray/Kubeflow chỉ nên xem xét khi thời gian search/train vượt giới hạn một node,
có nhiều team hoặc cần isolation/scheduling trên cluster.

### 6.5 Metric RecSys không áp dụng cho fraud

NDCG, HitRate và MRR phù hợp xếp hạng recommendation. FraudGuard cần PR-AUC,
recall/precision theo threshold, recall tại false-positive-rate cố định,
calibration, expected loss/cost và latency. Không nên sao chép acceptance gate
của repo mẫu mà không đổi metric và denominator.

## 7. Đề xuất cải thiện Data Governance, giữ nguyên tech stack

### 7.1 Xác định ownership và data product contract

Tạo tài liệu `docs/data-governance.md` mô tả cho từng dataset chính:

- business owner và technical owner;
- purpose và consumers;
- grain, business key và event-time semantics;
- freshness SLO;
- quality SLO;
- retention;
- mức độ nhạy cảm;
- quy trình xử lý contract change;
- runbook khi quality gate thất bại.

Có thể dùng dbt descriptions/docs làm catalog kỹ thuật. Chưa cần DataHub.

### 7.2 Phân loại dữ liệu và bảo vệ account identifier

`nameOrig` và `nameDest` là synthetic identifiers trong PaySim nhưng tương ứng
với account/customer identifiers trong dữ liệu ngân hàng thật. Cần định nghĩa
ngay từ bây giờ:

- classification: public/internal/confidential/restricted;
- không log raw identifier trong API hoặc monitoring;
- pseudonymization/tokenization trước ML nếu chuyển sang dữ liệu thật;
- quyền đọc raw và quyền đọc training mart tách biệt;
- dữ liệu xuất từ notebook không được chứa identifier;
- retention và xóa dữ liệu theo chính sách.

Các identifier đang bị loại khỏi feature allowlist là đúng, nhưng governance
cần bao phủ cả storage, logs, artifacts và notebook outputs.

### 7.3 Quản lý schema evolution

Avro/Schema Registry đã có. Cần bổ sung policy:

- version owner và compatibility rule;
- trường nào được thêm có default, trường nào là breaking change;
- CI kiểm tra schema compatibility trước merge;
- mapping version Avro → ClickHouse raw → dbt mart;
- backfill/migration plan;
- thời gian hỗ trợ producer schema cũ.

### 7.4 Biến data quality thành SLO có lịch sử

Quality manifest hiện tại là nền tốt. Nên định nghĩa ít nhất:

| SLO | Ví dụ cách đo bằng stack hiện tại |
| --- | --- |
| Freshness | `max(event_time)` và batch commit time trong ClickHouse |
| Completeness | transaction count, label coverage, null rate |
| Uniqueness | canonical key count so với physical count |
| Validity | quarantine rate, invalid amount/balance rate |
| Consistency | quality manifest reconcile với rows loaded |
| Label maturity | tỷ lệ transaction có final label theo age bucket |
| Replay/conflict | duplicate và payload-conflict rate |

Ghi kết quả theo từng batch/day vào ClickHouse, dùng Airflow để chạy check và
alert khi vượt threshold. Như vậy vẫn giữ nguyên tech stack.

### 7.5 Định nghĩa label lifecycle

Fraud label thường có trạng thái thay đổi: unknown → suspected → confirmed →
reversed. PaySim chỉ có final binary label, nhưng kiến trúc nên chuẩn bị:

- `label_status`, `label_source`, `label_event_time`, `label_version`;
- thời gian chờ label được coi là mature;
- cách xử lý label correction;
- snapshot label cutoff cho mỗi training run;
- performance monitoring chỉ dùng cohort đã mature.

Nếu không có label cutoff, model run sau có thể dùng label mà model run trước
chưa thể biết, khiến so sánh experiment không công bằng.

### 7.6 Version hóa training dataset

Artifact hiện có hash source/config nhưng cần manifest cho dữ liệu training:

- relation/model version hoặc dbt manifest hash;
- min/max `event_time`;
- label cutoff;
- row count và fraud count;
- partition list hoặc batch IDs;
- feature schema hash;
- query/model SHA;
- exclusion summary;
- data-quality status.

Không cần thay ClickHouse hoặc MinIO. Có thể ghi JSON manifest cùng model
artifact trong MinIO.

### 7.7 Lineage khả dụng mà không cần DataHub

Trong giai đoạn hiện tại:

- phát hành `dbt docs` để xem source → staging → core → ML mart;
- khai báo dbt exposure cho training job và scoring/monitoring consumers;
- lưu Airflow run ID, dbt invocation ID, dataset manifest và model run ID;
- đưa các ID này vào model metadata;
- giữ Kafka topic/partition/offset và MinIO object lineage như hiện tại.

Khi số pipeline/team lớn và việc tìm lineage trong nhiều hệ thống trở nên khó,
lúc đó mới đánh giá DataHub/OpenLineage.

### 7.8 Retention, replay và disaster recovery

Cần viết rõ:

- retention của raw, quarantine, quality manifest, ClickHouse marts, training
  snapshots và model artifacts;
- checkpoint mất thì replay từ đâu;
- replay có idempotent không;
- cách rebuild canonical tables;
- backup/restore cho ClickHouse metadata và MinIO artifacts;
- RPO/RTO kỳ vọng cho local demo và môi trường triển khai thật.

## 8. Đánh giá và đề xuất cho notebook

### 8.1 FraudGuard có cần nhiều notebook như repo mẫu không?

Có thể thêm notebook, nhưng không nên lấy số lượng làm mục tiêu. Một notebook
tốt phải trả lời một câu hỏi rõ ràng và gọi reusable code từ package.

Notebook hiện tại [`EDA_and_Audit.ipynb`](notebooks/EDA_and_Audit.ipynb) phù
hợp cho data audit và EDA. Nên hoàn thiện notebook này với các phân tích đã xác
định: type mix, log-amount distribution, non-positive amount, balance zero rate,
fraud rate/amount share theo type, amount bucket và step.

### 8.2 Bộ notebook đề xuất

1. `01_eda_and_data_audit.ipynb`
   - giữ vai trò của notebook hiện tại;
   - đọc dữ liệu theo chunk hoặc query aggregate từ ClickHouse;
   - kiểm tra imbalance, data quality, label coverage và leakage candidates;
   - không train model chính thức.

2. `02_baseline_experiment.ipynb`
   - gọi code từ `fraudguard_ml.training`;
   - so sánh dummy baseline, logistic regression và tree baseline;
   - dùng temporal train/validation/test;
   - báo PR-AUC, ROC-AUC, precision, recall, F-beta và confusion matrix;
   - không tự tạo một training implementation riêng trong notebook.

3. `03_threshold_calibration_error_analysis.ipynb`
   - precision-recall curve và threshold theo cost;
   - calibration curve/Brier score;
   - false positive/false negative theo type, amount bucket và step;
   - stability theo time window;
   - SHAP hoặc feature importance khi model phù hợp;
   - đề xuất operating threshold và các nhóm cần rule/manual review.

4. `04_monitoring_backtest.ipynb` chỉ thêm ở giai đoạn sau
   - mô phỏng delayed labels;
   - population/feature/prediction drift;
   - performance theo mature label window;
   - champion/challenger comparison.

### 8.3 Quy tắc notebook

- Notebook không chứa password, endpoint nội bộ hoặc raw account IDs.
- Không commit output quá lớn hoặc data extract.
- Mọi transform/model/metric dùng trong production phải ở Python package và có
  test.
- Notebook ghi rõ dataset version, code SHA, config, random seed và thời điểm
  chạy.
- Dùng tên notebook có mục tiêu rõ; tránh tên chung như `notebook.ipynb`.
- CI có thể chạy smoke execution trên sample nhỏ hoặc kiểm tra notebook syntax.

## 9. Đánh giá và đề xuất cho ML

### 9.1 Việc cần làm trước khi chọn model

Phải chốt `prediction_point`:

| Lựa chọn | Ý nghĩa | Feature hợp lệ |
| --- | --- | --- |
| Pre-authorization | Score trước khi cho phép giao dịch | Chỉ dữ liệu có trước ledger update; không dùng after-balance/delta phát sinh sau xử lý |
| Post-ledger monitoring | Phát hiện sau khi giao dịch đã ghi sổ | Có thể dùng after-balance nếu hệ thống thật cung cấp tại thời điểm score |

Config hiện ghi `post_ledger_update`, trong khi tên FraudGuard có thể khiến
người đọc kỳ vọng chặn giao dịch real time. Hai mục tiêu này cần được phân biệt
trong README và API contract.

Các cột `origin_balance_after`, `destination_balance_after`, delta và residual
đã được đánh dấu chờ leakage audit trong dbt docs. Đây phải là một release gate,
không chỉ là ghi chú.

### 9.2 Baseline phù hợp

Thứ tự đề xuất:

1. `DummyClassifier` để có lower bound.
2. Logistic regression với preprocessing pipeline và class weighting để có
   baseline giải thích được.
3. Gradient-boosted trees, ưu tiên `HistGradientBoostingClassifier` hoặc
   LightGBM/XGBoost sau khi baseline ổn định.
4. Neural network chỉ khi dữ liệu/feature sequence chứng minh lợi ích.

PaySim là dữ liệu tabular và synthetic; deep learning không mặc nhiên tốt hơn
tree model. Model đơn giản giúp phát hiện leakage và pipeline bug dễ hơn.

### 9.3 Metric và acceptance gate

Không dùng accuracy làm metric chính. Mỗi run nên có:

- PR-AUC: quan trọng vì fraud rất hiếm;
- ROC-AUC: metric phụ, không đủ để chọn model;
- precision, recall, F1/F2 tại operating threshold;
- recall tại false-positive-rate hoặc review-capacity cố định;
- false positives trên 1.000/10.000 giao dịch;
- confusion matrix theo type, amount bucket và time window;
- Brier score/calibration curve;
- expected fraud amount captured;
- expected cost hoặc net value theo ma trận chi phí;
- inference latency và artifact size.

Promotion gate nên so candidate với champion trên cùng temporal test window và
dataset version. Ví dụ gate ban đầu:

- không giảm recall tại review capacity mục tiêu;
- precision không thấp hơn mức tối thiểu;
- calibration không xấu đi đáng kể;
- không có segment quan trọng bị suy giảm vượt tolerance;
- inference p95 dưới SLA;
- data contract và leakage tests đều pass.

Threshold là một artifact/versioned policy riêng, không nên hard-code tùy ý vào
API.

### 9.4 Experiment tracking và registry

MLflow phù hợp với FraudGuard vì:

- có thể dùng MinIO hiện tại làm artifact store;
- log params, metrics, plots, data manifest và model bundle;
- quản lý candidate/champion alias;
- giúp Airflow training DAG truyền run/model version cho downstream tasks.

Nên dùng một PostgreSQL database/schema riêng cho MLflow metadata thay vì dùng
chung bảng nghiệp vụ của Airflow. Nếu chưa muốn chạy server, bắt đầu bằng local
MLflow file store để hoàn thiện contract, sau đó chuyển sang PostgreSQL + MinIO.

### 9.5 Model bundle cần chứa gì?

Một immutable bundle nên chứa:

- preprocessing pipeline;
- estimator;
- ordered feature schema và dtype;
- model version;
- training dataset manifest;
- metrics và threshold policy;
- label/positive-class semantics;
- code/config hashes;
- library versions;
- created-at timestamp;
- optional explainer metadata.

API chỉ tải bundle đã pass validation; không tự fit encoder hoặc tự suy ra thứ
tự feature khi startup.

### 9.6 Training orchestration

Nên thêm một Airflow DAG dùng các task rõ ràng:

```text
dbt training mart ready
  -> validate training-data contract
  -> snapshot/version dataset manifest
  -> train baseline/challenger
  -> offline evaluation
  -> acceptance gate
  -> register candidate
  -> manual approval hoặc controlled promotion
```

Giai đoạn đầu không nên tự động retrain chỉ vì drift. Drift là tín hiệu điều
tra; retraining cần data-quality pass, mature labels và evaluation gate.

### 9.7 ML tech stack đề xuất

| Công nghệ | Khi nào thêm | Khuyến nghị |
| --- | --- | --- |
| scikit-learn | Ngay | Cần cho preprocessing, baseline, metrics và serialization pipeline |
| MLflow | Sau khi training CLI chạy | Nên thêm để tracking/registry/artifacts |
| joblib | Cùng model bundle | Phù hợp model sklearn; vẫn cần kiểm soát version và trusted artifact |
| LightGBM hoặc XGBoost | Sau baseline | Thêm một trong hai nếu cải thiện metric/cost rõ ràng |
| imbalanced-learn | Khi cần resampling | Optional; ưu tiên class weight và threshold trước |
| SHAP | Khi dùng tree model và cần explainability | Nên thêm ở error analysis, không nhất thiết chạy trên mọi request |
| Optuna | Khi manual search trở thành bottleneck | Optional, trước Ray Tune |
| FastAPI + Uvicorn | Khi cần synchronous score | Phù hợp và nhẹ |
| prometheus-client | Khi có service chạy lâu dài | Phù hợp cho latency/error/prediction metrics |
| Evidently | Khi monitoring thủ công khó duy trì | Optional; không bắt buộc để có drift monitoring |
| Feast/Redis | Khi có online aggregate features dùng chung | Chưa thêm ngay |
| ONNX Runtime | Khi cần portable/nhanh hơn | Chỉ thêm sau parity và benchmark |
| Triton/KServe | Khi throughput/GPU/multi-model cần | Chưa phù hợp hiện tại |
| Ray/Kubeflow | Khi training/search cần cluster | Chưa phù hợp hiện tại |

## 10. API và real-time scoring có phù hợp không?

### 10.1 Kết luận

Có, nếu mục tiêu của FraudGuard là ra quyết định trên từng giao dịch với latency
thấp hoặc cung cấp risk score cho một hệ thống khác. Nếu dự án chỉ nhằm batch
analytics/offline detection, API không bắt buộc và batch scoring qua Airflow +
ClickHouse sẽ đơn giản hơn.

Pipeline hiện tại Kafka → Spark → MinIO → Airflow → ClickHouse phù hợp ingestion
và training/audit, nhưng không phải đường inference latency thấp vì có microbatch
và lịch Airflow. Không nên đặt API phía sau đường này rồi gọi đó là real-time.

### 10.2 Kiến trúc tối thiểu đề xuất

```text
Synchronous path
Client -> FastAPI scoring service -> feature/preprocessing bundle -> model -> decision

Asynchronous path
Kafka fraud.transaction -> scoring consumer -> prediction topic/table

Feedback path
fraud.transaction.label -> join by event_id -> mature performance monitoring
```

FastAPI và Kafka consumer phải dùng cùng model bundle, feature schema và
threshold policy để tránh hai implementation khác nhau.

### 10.3 API contract đề xuất

Endpoint chính:

- `POST /v1/score`
- `GET /healthz`: process còn sống;
- `GET /readyz`: model đã load và dependencies sẵn sàng;
- `GET /version`: service/model/schema/threshold version;
- `GET /metrics`: chỉ khi có metrics collector.

Response nên có:

```json
{
  "event_id": "...",
  "risk_score": 0.973,
  "decision": "review",
  "threshold": 0.91,
  "model_version": "fraudguard-v1",
  "feature_schema_version": "v1",
  "reason_codes": ["HIGH_AMOUNT", "BALANCE_PATTERN"]
}
```

`reason_codes` phải được thiết kế cẩn thận: có thể là stable policy reasons hoặc
explanation được chuẩn hóa; không trả raw SHAP vector như một public contract.

### 10.4 Yêu cầu an toàn cho API

- Không nhận `is_fraud` hoặc `is_flagged_fraud` trong scoring payload.
- Request chỉ chứa feature khả dụng tại prediction point.
- Validate range, enum, currency/unit và schema version bằng Pydantic.
- Dùng `event_id` cho idempotency và tracing, nhưng không log account ID thô.
- Model load một lần khi startup; startup thất bại thì readiness fail.
- Timeout, request-size limit và bounded concurrency.
- Structured logs có model version, decision và latency nhưng không có dữ liệu
  nhạy cảm.
- Có contract tests và serialization parity tests.
- Tách risk score khỏi business action: model đưa score, policy quyết định
  allow/review/block.

### 10.5 Khi nào cần online feature store?

Nếu API chỉ dùng `type`, `amount` và balance có trong request, chưa cần feature
store. Khi thêm các feature như số giao dịch/tổng amount/số destination khác
nhau trong 5 phút, 1 giờ hoặc 24 giờ theo account, cần một stateful feature path.
Khi đó có thể:

1. Bắt đầu bằng Spark/Kafka tạo aggregate và lưu vào một online store nhỏ.
2. Chỉ đánh giá Feast khi cần point-in-time consistency và tái sử dụng nhiều
   feature views.

Không nên để API query ClickHouse bằng nhiều aggregate nặng trên mỗi request.

## 11. Monitoring và feedback loop

### 11.1 Data monitoring

- ingestion lag;
- batch success/failure;
- quarantine rate;
- schema version mix;
- duplicate/conflict rate;
- label coverage và label delay;
- training eligibility/exclusion rate.

### 11.2 Model/service monitoring không cần label ngay

- request rate, error rate, timeout;
- p50/p95/p99 latency;
- model load/version;
- score distribution;
- decision distribution;
- feature missing/zero/out-of-range rates;
- population drift theo type/amount/balance;
- unseen category/schema mismatch.

### 11.3 Performance monitoring sau khi label mature

- PR-AUC/precision/recall theo cohort time;
- false positive và false negative theo type/amount bucket;
- fraud amount captured;
- calibration;
- threshold stability;
- champion/challenger deltas;
- performance theo label age để tránh đánh giá trên label chưa mature.

Giai đoạn đầu có thể lưu prediction events và monitoring aggregates trong
ClickHouse, dùng Airflow để join final labels và chạy báo cáo định kỳ. Cách này
giữ nguyên Data stack. Prometheus/Grafana chỉ cần thêm khi API production cần
operational alerts thời gian thực.

## 12. Kiểm thử và CI cần bổ sung

### 12.1 CI tối thiểu

Repository hiện chưa có GitHub Actions/Jenkins workflow. Một CI ban đầu nên
chạy:

1. Ruff format/lint.
2. Mypy.
3. Pytest unit tests và coverage.
4. dbt parse/compile và schema tests không cần warehouse nếu khả thi.
5. Avro schema validation/compatibility check.
6. Docker Compose config validation.
7. Notebook syntax hoặc smoke execution trên sample nhỏ.
8. Dependency/security scan ở mức phù hợp.

Không cần deployment CI/CD phức tạp trước khi có model artifact và API image.

### 12.2 Test cho feature và training

- temporal split không overlap;
- feature allowlist không chứa target/ID/future fields;
- preprocessing train/serve parity;
- deterministic run với seed;
- class/positive-label semantics;
- metric correctness và edge case không có positive;
- threshold gate;
- model bundle load/save parity;
- dataset version manifest;
- row/exclusion reconciliation.

### 12.3 Test cho API

- request equivalence partitions và boundary values;
- invalid enum/range/schema version;
- missing model/readiness;
- deterministic output cho fixed bundle;
- idempotent `event_id` handling;
- timeout/dependency failure;
- no sensitive field in logs;
- latency/load smoke test;
- API response contract tương thích ngược.

### 12.4 Integration/E2E

Một E2E nhỏ nên chứng minh:

```text
sample transaction
  -> ingest/feature contract
  -> score với pinned model
  -> prediction event được lưu
  -> final label đến
  -> monitoring join đúng event_id
  -> performance metric cập nhật đúng
```

## 13. Cấu trúc thư mục ML đề xuất

Đề xuất này mở rộng cấu trúc hiện tại, không yêu cầu tái cấu trúc Data stack:

```text
ml/
├── src/fraudguard_ml/
│   ├── data/                 # dataset loading, manifest, temporal split
│   ├── features/             # reusable preprocessing/feature contract
│   ├── models/               # baseline/challenger builders
│   ├── training/             # train orchestration and CLI implementation
│   ├── evaluation/           # metrics, calibration, threshold, reports
│   ├── registry/             # MLflow adapter and promotion rules
│   ├── serving/              # model bundle loading and score service logic
│   └── monitoring/           # prediction/label joins and drift metrics
├── tests/
└── Dockerfile               # chỉ khi có training/API runtime riêng

services/
└── scoring_api/              # FastAPI routes/settings/lifecycle

notebooks/
├── 01_eda_and_data_audit.ipynb
├── 02_baseline_experiment.ipynb
└── 03_threshold_calibration_error_analysis.ipynb

airflow/dags/
├── fraudguard_train_model.py
└── fraudguard_monitor_model.py
```

Không bắt buộc tạo toàn bộ thư mục cùng lúc. Chỉ tạo khi có implementation và
test tương ứng.

## 14. Roadmap ưu tiên

### P0 — Chốt ML contract và có baseline chạy được

1. Viết root `README.md` với mục tiêu hệ thống và sơ đồ hiện tại.
2. Chốt pre-authorization hay post-ledger detection.
3. Hoàn thành leakage audit và feature allowlist.
4. Tạo reusable temporal split/data loader.
5. Implement Dummy + LogisticRegression baseline bằng scikit-learn.
6. Implement metric suite, threshold analysis và model bundle.
7. Hoàn thiện EDA notebook; thêm baseline và error-analysis notebooks mỏng.
8. Thêm unit tests và CI tối thiểu.

Điều kiện hoàn thành P0: từ một training relation/version xác định có thể chạy
một command để tạo reproducible model bundle, metrics report và threshold
policy; test set chỉ được dùng một lần để báo cáo cuối.

### P1 — Tracking, registry và orchestration

1. Thêm MLflow tracking.
2. Ghi training dataset manifest vào mỗi run.
3. Thêm Airflow training DAG.
4. Thêm candidate/champion convention và manual promotion gate.
5. Thêm model comparison report và rollback metadata.

Điều kiện hoàn thành P1: truy ngược được một model version đến code, config,
dataset partitions, label cutoff, metrics và threshold.

### P2A — Nếu mục tiêu là batch fraud detection

1. Viết batch scoring job.
2. Ghi score/model version/threshold vào ClickHouse.
3. Airflow join score với delayed labels.
4. Theo dõi data/model performance theo thời gian.

API có thể hoãn ở nhánh này.

### P2B — Nếu mục tiêu là synchronous hoặc near-real-time scoring

1. Viết FastAPI scoring service tối thiểu.
2. Container hóa service và thêm health/readiness/version/metrics.
3. Viết Kafka asynchronous scoring consumer dùng cùng model bundle.
4. Xác định latency SLA và load test.
5. Thêm shadow mode: candidate nhận cùng input nhưng không ảnh hưởng decision.
6. Lưu prediction event để join delayed labels.

### P3 — Chỉ mở rộng khi có bằng chứng về nhu cầu

- Optuna cho hyperparameter search.
- LightGBM/XGBoost challenger.
- Prometheus/Grafana cho production service alerts.
- Online aggregate feature store.
- Automated champion/challenger promotion có approval.
- Kubernetes/KServe/Triton khi benchmark cho thấy cần.
- Ray/Kubeflow khi một node/Airflow không còn đáp ứng training scale.

## 15. Danh sách “nên thêm / chưa nên thêm”

### Nên thêm sớm

- Prediction-point decision và leakage gate.
- Root README, architecture diagram và runbook.
- Reusable training/evaluation code.
- scikit-learn baseline.
- Fraud-specific metrics, calibration và threshold policy.
- Dataset/model manifest.
- MLflow.
- CI tối thiểu.
- Hai notebook: baseline experiment và threshold/error analysis.
- Data ownership, classification, quality SLO và label lifecycle docs.

### Nên thêm khi bước vào serving

- FastAPI/Uvicorn.
- Model bundle loader.
- Health/readiness/version/metrics endpoints.
- Structured logging và request tracing bằng `event_id`.
- Prediction event storage và delayed-label join.
- Load/contract/E2E tests.
- Shadow evaluation trước promotion.

### Chưa nên thêm

- Kubeflow.
- Ray distributed training.
- Feast/Redis chỉ để “có feature store”.
- Triton/KServe.
- Kubernetes/Helm/Terraform nếu mục tiêu vẫn là local platform.
- Service mesh và progressive A/B phức tạp.
- Deep learning trước khi tabular baselines và leakage audit hoàn chỉnh.

## 16. Definition of Done cho một FraudGuard ML vertical slice

Một phiên bản đầu tiên có thể coi là hoàn chỉnh khi đáp ứng tất cả điều kiện:

- Dataset có schema contract, version manifest, label cutoff và quality pass.
- Feature allowlist phù hợp prediction point và có leakage test.
- Temporal split không overlap và được lưu trong metadata.
- Training chạy bằng CLI/config, không phụ thuộc notebook state.
- Có dummy và model baseline.
- Metrics phản ánh class imbalance và business cost.
- Threshold được version hóa.
- Model bundle load lại cho prediction giống kết quả trước khi serialize.
- Mỗi model truy ngược được code/config/data/metrics.
- Có candidate/champion rule và rollback artifact.
- Batch job hoặc API trả model version trong mọi prediction.
- Prediction được join với mature labels để monitor.
- CI kiểm tra lint, type, unit, contract và serialization parity.
- Không có target, future feature hoặc account identifier bị log/đưa vào model
  ngoài contract.

## 17. Thứ tự đầu tư khuyến nghị cuối cùng

Ưu tiên cao nhất của FraudGuard không phải API hay Kubernetes mà là làm rõ thời
điểm dự đoán và hoàn thành một baseline có đánh giá đúng. Sau đó nên thêm MLflow
và Airflow training DAG để tạo vòng đời model có thể truy vết. FastAPI rất phù
hợp nếu dự án muốn real-time scoring, nhưng chỉ nên được triển khai sau khi model
bundle, threshold policy và train/serve feature parity đã ổn định.

Những ưu điểm lớn nhất cần học từ RecSys-MLops là: boundary rõ, artifact và
version rõ, API contract rõ, monitoring/test là một phần của sản phẩm, và model
promotion có gate. Những công nghệ hạ tầng nặng chỉ là một cách triển khai các
nguyên tắc đó, không phải điều kiện để FraudGuard trở thành một dự án MLOps tốt.
