# Feature ownership và workflow từ EDA đến model

## 1. Mục tiêu của tài liệu

Tài liệu này đặt ra một nguyên tắc kiến trúc cho FraudGuard:

> Mỗi feature nghiệp vụ chỉ được định nghĩa và tính toán tại một nơi. Trong dự
> án này, nơi đó là dbt.

Notebook có thể khám phá dữ liệu và đề xuất feature, nhưng không được trở thành
implementation thứ hai của feature dùng để train hoặc inference. Sau khi một
feature được chấp nhận, notebook, pipeline training và các bước đánh giá đều
phải đọc cùng feature đó từ mart do dbt tạo ra.

Mục tiêu của nguyên tắc này là ngăn **training-serving skew** và **feature
drift** âm thầm: model được train bằng một công thức pandas nhưng production
inference lại nhận một công thức SQL hơi khác.

Tài liệu này quy định trách nhiệm của dbt, notebook, experiment config và package
`fraudguard_ml`; đồng thời mô tả quy trình đưa một feature mới từ ý tưởng EDA
đến model bundle có thể audit.

## 2. Quyết định kiến trúc

### 2.1. dbt là feature factory duy nhất

dbt chịu trách nhiệm:

- xác định grain của training relation;
- join và chuẩn hóa nguồn dữ liệu cần thiết;
- tính các feature nghiệp vụ theo một công thức duy nhất;
- bảo đảm feature có semantics rõ ràng tại prediction point;
- kiểm tra null, domain, tính hợp lệ và các invariant quan trọng;
- cung cấp mart mà cả notebook và training pipeline cùng tiêu thụ.

Trong phạm vi hiện tại, training relation là
`fraudguard_ml.ml_training_transactions`, được cấu hình tại:

- `configs/training_baseline.yml`;
- `configs/training_challenger_balance.yml`.

Việc một cột tồn tại trong mart **không đồng nghĩa** cột đó đã được duyệt làm
feature. Mart có thể chứa ID, cột thời gian, target và cột phục vụ audit. Quyền
được đưa cột vào estimator được quyết định bởi `dataset.feature_columns` trong
experiment config.

### 2.2. Notebook là nơi khám phá, không phải feature factory

Notebook được dùng để:

- xem phân phối và chất lượng dữ liệu;
- tìm pattern và đặt giả thuyết;
- đề xuất feature mới;
- trực quan hóa feature đã được dbt materialize;
- chạy thử pipeline dùng chung từ package `fraudguard_ml`;
- so sánh kết quả giữa các experiment config.

Notebook không được dùng để:

- giữ công thức pandas chính thức của feature;
- tự tạo tập feature khác với mart rồi dùng tập đó để train model cuối;
- tự viết một pipeline sklearn thứ hai;
- fit imputer hoặc scaler trên toàn bộ dataset;
- chọn threshold bằng test split;
- tự ý chọn thêm cột ngoài `feature_columns`.

Một phép tính tạm thời trong EDA vẫn được phép khi mục đích là kiểm tra một giả
thuyết. Kết quả đó chỉ là **prototype**, chưa phải feature chính thức và không
được dùng để tạo model artifact. Nếu giả thuyết đáng theo đuổi, công thức phải
được chuyển sang dbt, được test, rồi notebook đọc lại feature đã materialize từ
mart.

### 2.3. Experiment config là feature allowlist

`dataset.feature_columns` là danh sách có thứ tự các input mà experiment được
phép đưa vào preprocessing và estimator. Vì vậy:

- thêm hoặc bỏ feature phải là một thay đổi config có chủ đích;
- thứ tự feature phải được bảo toàn;
- notebook và CLI không được tự động dùng mọi cột số có trong DataFrame;
- ID, target và các cột bị cấm không được xuất hiện trong estimator input.

Baseline hiện tại khóa bốn feature:

```yaml
feature_columns:
  - transaction_type
  - amount
  - origin_balance_before
  - destination_balance_before
```

`configs/training_challenger_balance.yml` mở rộng allowlist bằng after-balance,
delta và residual. Đây là một experiment challenger riêng; sự tồn tại của
config này chưa chứng minh các feature mở rộng đã qua leakage audit hoặc mart
hiện đã build thành công.

### 2.4. `fraudguard_ml` sở hữu training semantics

Package `ml/src/fraudguard_ml` chịu trách nhiệm cho các hành vi không thuộc
feature engineering nghiệp vụ, gồm:

- đọc config và validate feature allowlist;
- tạo snapshot và manifest tái lập được;
- load đúng cột, đúng thứ tự và đúng temporal split;
- fit preprocessing trên train split;
- train estimator;
- chọn threshold trên validation split;
- evaluate một lần trên test split đã được giữ riêng;
- ghi model bundle và metrics theo cách immutable.

Imputation, scaling và one-hot encoding là **model preprocessing**, không phải
công thức feature nghiệp vụ. Chúng nên nằm trong sklearn pipeline để trạng thái
đã fit đi cùng model bundle. Notebook chỉ gọi lại implementation dùng chung,
không sao chép logic này vào cell riêng.

Thiết kế Phase 4 cho `training.py`, `evaluation.py`, threshold selection và
immutable bundle đã được mô tả trong
`docs/mart_to_training/04_TRAIN_AND_EVALUATE.md`. Cho tới khi implementation đó
tồn tại và được kiểm thử, notebook không nên tuyên bố đã chạy production-like
training flow.

## 3. Luồng làm việc chuẩn

### Vòng 1 — EDA đề xuất feature

1. Notebook đọc dữ liệu nguồn hoặc mart phù hợp để khám phá.
2. Người phân tích xác định giả thuyết nghiệp vụ, ví dụ một chênh lệch số dư có
   thể giúp phân biệt giao dịch gian lận.
3. Có thể tính thử feature bằng pandas để đánh giá nhanh phân phối, missingness,
   outlier và khả năng phân biệt nhãn.
4. Ghi rõ phép tính chỉ là prototype EDA và không dùng nó để tạo artifact.
5. Trước khi chấp nhận feature, xác định:
   - dữ liệu đầu vào có sẵn tại prediction point hay không;
   - công thức có dùng thông tin tương lai hoặc target hay không;
   - null, số âm, zero balance và edge case được hiểu như thế nào;
   - feature có thể được tái tạo ổn định bằng dbt hay không.

**Đầu ra của vòng 1:** một đề xuất feature và bằng chứng EDA, chưa phải feature
training chính thức.

### Vòng 2 — Implement một lần trong dbt

1. Viết công thức feature trong model dbt ở đúng grain.
2. Đặt tên và kiểu dữ liệu rõ ràng; thống nhất quy ước dấu và cách xử lý null.
3. Thêm mô tả schema và test tương xứng với semantics của feature.
4. Build/test model dbt và kiểm tra row count, uniqueness cùng eligibility
   partition không bị thay đổi ngoài ý muốn.
5. Đọc mart đã materialize từ ClickHouse vào notebook.
6. Lặp lại EDA và thử nghiệm trên chính cột do dbt tạo ra; không dùng lại cột
   pandas prototype.

**Đầu ra của vòng 2:** một feature có implementation duy nhất trong dbt, có
lineage và có thể được mọi consumer đọc giống nhau.

### Vòng 3 — Khóa experiment và tạo artifact

1. Thêm feature đã duyệt vào `dataset.feature_columns` của một config
   challenger; không âm thầm sửa baseline.
2. Tạo snapshot/manifest từ đúng relation và đúng feature list.
3. Loader xác minh relation, feature order, target, split boundaries và label
   policy giữa manifest với config.
4. `train_and_select_threshold` fit preprocessing/model trên train và chọn
   threshold trên validation.
5. `evaluate_test_split` dùng bundle đã khóa để đánh giá test riêng.
6. Bundle ghi lại feature list, prediction point, config, threshold và liên kết
   tới dataset manifest để lần chạy có thể audit.

**Đầu ra của vòng 3:** model bundle bất biến gắn với một config và một dataset
manifest cụ thể.

Luồng đầy đủ có thể tóm tắt như sau:

```text
EDA prototype
    |
    v
Đề xuất + leakage audit
    |
    v
dbt implement/test feature một lần
    |
    v
ClickHouse ML mart
    |                         
    +--> notebook khám phá lại
    |
    +--> snapshot + manifest
              |
              v
        config feature allowlist
              |
              v
       train -> validation threshold
              |
              v
       locked bundle -> test evaluation
```

## 4. Chống leakage

### 4.1. Khóa prediction point trước khi đánh giá feature

Experiment hiện khai báo:

```yaml
prediction_point: post_ledger_update
```

Mọi feature phải được diễn giải theo prediction point này. Cần trả lời bằng
lineage thực tế rằng tại thời điểm chấm điểm, hệ thống đã biết những trường nào.
Tên cột như `*_after` không tự động chứng minh leakage, nhưng cũng không tự động
chứng minh an toàn. Quyết định phải dựa trên thời điểm dữ liệu phát sinh và thời
điểm model ra quyết định.

Nếu sau này use case chuyển sang chặn giao dịch **trước** ledger update, các
after-balance feature có khả năng không còn hợp lệ. Khi đó prediction point,
contract, feature allowlist và model phải được đánh giá lại cùng nhau; không
được tái sử dụng bundle cũ mà không audit.

### 4.2. Feature theo thời gian chỉ dùng quá khứ hợp lệ

Đối với rolling/window/aggregate feature:

- partition theo đúng entity nghiệp vụ;
- order theo `event_time` và có tie-breaker xác định khi cần;
- window phải loại trừ event hiện tại nếu thông tin của event đó chưa có tại
  prediction point;
- không aggregate trên toàn bộ dataset trước khi temporal split;
- không dùng dữ liệu validation/test để tạo statistics cho hàng train;
- quy định rõ hành vi với late event và nhiều event cùng timestamp.

dbt là nơi định nghĩa SQL của window feature, nhưng việc dùng dbt không tự động
loại bỏ temporal leakage. SQL vẫn phải được review theo event-time semantics.

### 4.3. Preprocessing chỉ fit trên train

Các phép biến đổi có trạng thái học từ dữ liệu phải tuân theo:

| Thành phần | Fit/chọn bằng | Chỉ transform/evaluate trên |
|---|---|---|
| Imputer | Train | Validation, test, inference |
| Scaler | Train | Validation, test, inference |
| One-hot vocabulary | Train | Validation, test, inference |
| Model parameters | Train | Validation, test |
| Decision threshold | Validation predictions | Test, inference |
| Final metrics | Locked bundle | Test |

Nếu median, mean, category vocabulary hoặc threshold được tính trên toàn bộ
DataFrame trước khi chia tập thì kết quả evaluation đã bị leakage, dù bản thân
feature SQL không dùng thông tin tương lai.

### 4.4. Test split không dùng để phát triển

Không dùng test để:

- chọn feature;
- chọn hyperparameter;
- chọn threshold;
- quyết định giữa nhiều lần chỉnh sửa sau khi đã xem test metrics.

Baseline và challenger phải được quyết định bằng train/validation theo tiêu chí
định trước. Test chỉ dùng cho final evaluation của bundle đã khóa. Nếu liên tục
điều chỉnh sau khi xem test, test đã trở thành validation và cần một holdout mới.

## 5. Baseline và balance challenger

### 5.1. Vai trò của hai config

`configs/training_baseline.yml` là đường chuẩn nhỏ, dễ giải thích. Nó giúp kiểm
tra pipeline end-to-end trước khi mở rộng feature set.

`configs/training_challenger_balance.yml` mô tả thử nghiệm có thêm:

- `origin_balance_after`;
- `destination_balance_after`;
- `origin_balance_delta`;
- `destination_balance_delta`;
- `origin_amount_residual`;
- `destination_amount_residual`.

Nên giữ hai config độc lập để thay đổi feature là explicit và có thể so sánh,
thay vì dùng một notebook cell chọn cột theo điều kiện.

### 5.2. Khoảng trống hiện tại trong dbt

Tại thời điểm viết tài liệu:

- `dbt/models/marts/ml/ml_training_transactions.sql` đang select bốn cột
  `origin_balance_delta`, `destination_balance_delta`,
  `origin_amount_residual` và `destination_amount_residual` từ
  `ml_training_candidates`;
- `dbt/models/marts/ml/ml_training_candidates.sql` chưa tạo hoặc select bốn cột
  đó;
- `configs/training_data_contract.yml` và config challenger đã kỳ vọng các cột
  này;
- mô tả trong `dbt/models/marts/ml/_ml.yml` vẫn xem after-balance, delta và
  residual là các ứng viên chờ leakage audit M2.

Do đó, challenger chưa nên được coi là sẵn sàng chỉ vì config đã tồn tại. Cần
hoàn thành cùng lúc công thức dbt, schema documentation, tests, contract
validation và leakage audit.

### 5.3. Công thức phải có semantics được chốt

Trước khi implement, mỗi delta/residual cần được định nghĩa bằng lời và bằng
phương trình. Ví dụ, hai công thức sau mang ý nghĩa và dấu khác nhau:

```text
origin_balance_before - origin_balance_after
origin_balance_after - origin_balance_before
```

Tương tự, residual có thể có dấu hoặc trị tuyệt đối. Notebook EDA hiện có phép
tính thử không phải là contract mặc định cho dbt. Cần chọn một semantics, mô tả
edge case và test chính semantics đó; không suy ra công thức chỉ từ tên cột.

Một feature balance tối thiểu cần trả lời:

- Dấu dương và dấu âm có nghĩa gì?
- Có dùng `abs()` hay giữ dấu?
- Null được giữ nguyên hay thay bằng giá trị nào?
- Zero balance là dữ liệu hợp lệ, missing sentinel hay đặc tính của PaySim?
- Decimal precision/scale có đủ không?
- Công thức có khác theo `transaction_type` không?
- Cả before và after balance có thực sự sẵn có tại prediction point không?

## 6. Quy trình đưa một challenger feature vào hệ thống

### Bước A — Viết feature proposal

Ghi ngắn gọn:

- tên feature;
- giả thuyết fraud mà feature đại diện;
- input columns;
- công thức prototype;
- prediction-time availability;
- null/edge-case policy;
- rủi ro leakage;
- bằng chứng EDA ban đầu.

### Bước B — Chốt contract trước khi train

Chốt:

- tên cột và kiểu ClickHouse;
- grain và entity key;
- công thức chính xác;
- time/window semantics nếu có;
- description trong dbt schema;
- test cases có input và expected output cụ thể.

### Bước C — Implement và validate dbt

Feature được tạo trong model dbt phù hợp và truyền tới training mart. Validation
tối thiểu gồm:

- dbt build/test thành công;
- không làm đổi grain hoặc tạo duplicate key;
- row count/eligible population được reconcile;
- null rate và domain hợp lý;
- một số fixture hoặc truy vấn kiểm tra xác nhận đúng công thức;
- contract thấy đúng tên và ClickHouse type.

### Bước D — Notebook đọc lại mart

Notebook bỏ cột prototype khỏi đường train thử và đọc cột dbt từ ClickHouse.
EDA lại:

- phân phối theo split và label;
- missing/zero/outlier rate;
- drift train–validation và train–test;
- tương quan hoặc tính dư thừa với feature hiện có;
- pattern đáng ngờ có thể phản ánh artefact của PaySim.

### Bước E — Tạo experiment challenger

Thêm feature vào config challenger theo thứ tự rõ ràng. Snapshot và manifest mới
phải ghi đúng feature list. Không sửa snapshot cũ hoặc model bundle cũ tại chỗ.

### Bước F — So sánh công bằng

Baseline và challenger cần dùng cùng:

- eligible population;
- temporal boundaries;
- label policy;
- random seed và model family, trừ khi experiment chủ đích thay đổi chúng;
- evaluation policy và minimum precision constraint.

Manifest SHA có thể khác khi snapshot chứa feature list khác, nhưng population
fingerprint, số hàng/số fraud, split boundaries và label policy phải reconcile.
Nếu các đại lượng đó khác, chưa thể quy metric change hoàn toàn cho feature mới.

### Bước G — Quyết định promote hoặc reject

Không promote chỉ vì ROC-AUC tăng nhẹ. Với fraud detection cần xem tối thiểu:

- PR-AUC;
- precision và recall tại threshold policy đã chọn;
- confusion matrix;
- alert rate và fraud capture rate;
- độ ổn định giữa các temporal split;
- leakage risk, inference availability và chi phí vận hành.

Nếu feature bị reject, vẫn nên ghi lại lý do để tránh lặp lại cùng một thí
nghiệm mà không có thông tin mới.

## 7. Contract và lineage giữa các lớp

| Lớp | Nguồn chân lý | Invariant chính |
|---|---|---|
| Công thức feature | dbt SQL | Một công thức tại đúng grain/prediction point |
| Schema và semantics | dbt YAML + training data contract | Tên, type, role và mô tả nhất quán |
| Feature dùng cho experiment | `dataset.feature_columns` | Allowlist có thứ tự, không chứa cột cấm |
| Dataset cụ thể | Snapshot + dataset manifest | Immutable, có hash, population và split metadata |
| Preprocessing/model | `fraudguard_ml` training pipeline | Fit train-only và serialize cùng model |
| Threshold | Validation selection | Không chọn bằng test |
| Inference contract | Model bundle | Feature list/order, prediction point và threshold đã khóa |
| Khám phá | Notebook | Consumer của mart; prototype không phải production contract |

Một model run chỉ đáng tin khi lineage nối được xuyên suốt:

```text
dbt commit/model
  -> ClickHouse relation
  -> snapshot hash + manifest
  -> experiment config + ordered feature list
  -> fitted pipeline + selected threshold
  -> immutable model bundle
  -> final test metrics
```

## 8. Anti-pattern và failure mode

### Cùng một feature ở pandas và SQL

Hai bản có thể lệch do dấu, rounding, timezone, window boundary, null semantics
hoặc kiểu dữ liệu. Model vẫn chạy nhưng nhận giá trị khác lúc inference. Đây là
failure mode nguy hiểm vì thường không tạo exception.

### Tự động lấy toàn bộ cột số

Các lệnh kiểu `select_dtypes()` hoặc “mọi cột trừ target” có thể đưa ID, time,
audit field hoặc cột mới chưa review vào model. Luôn select đúng ordered
`feature_columns`.

### Impute trước khi split

Median/mean từ validation hoặc test chảy vào train làm metrics lạc quan. Đặt
imputer/scaler trong pipeline và chỉ gọi `fit` trên train.

### Aggregate không có event-time boundary

Feature như tổng tiền theo tài khoản có thể vô tình dùng giao dịch tương lai.
Mọi window feature cần point-in-time semantics và test bằng ví dụ nhỏ có timeline.

### Thay baseline tại chỗ

Sửa feature list của baseline khiến kết quả cũ và mới khó đối chiếu. Giữ baseline
ổn định; dùng config challenger có tên experiment riêng.

### Cho rằng cột tồn tại nghĩa là cột an toàn

Schema presence chỉ chứng minh khả năng truy cập. Feature vẫn cần prediction-time
availability, leakage audit và operational feasibility.

### Đánh giá lặp lại trên test

Sau nhiều lần xem rồi chỉnh theo test, test metrics không còn là ước lượng độc
lập. Dùng validation để phát triển và khóa bundle trước test.

## 9. Definition of Ready cho một feature

Một feature chỉ sẵn sàng để thêm vào challenger config khi tất cả điều kiện sau
được đáp ứng:

- [ ] Có giả thuyết nghiệp vụ và tên rõ nghĩa.
- [ ] Prediction point và input availability đã được xác nhận.
- [ ] Không dùng target, tương lai hoặc statistics từ validation/test.
- [ ] Công thức, dấu, null và edge-case semantics đã được chốt.
- [ ] Feature được implement một lần trong dbt.
- [ ] dbt schema description và tests đã được thêm.
- [ ] Training data contract khớp tên và kiểu dữ liệu.
- [ ] Mart build thành công mà không đổi grain ngoài ý muốn.
- [ ] Notebook đọc cột từ mart thay vì tự tính lại cho đường training.
- [ ] EDA theo temporal split không phát hiện artefact/leakage chưa giải thích.
- [ ] Feature được thêm explicit vào một challenger `feature_columns`.
- [ ] Snapshot/manifest ghi đúng ordered feature list.

## 10. Definition of Done cho một experiment feature

Experiment chỉ hoàn thành khi:

- [ ] Baseline và challenger dùng population, boundaries và label policy có thể
      reconcile.
- [ ] Preprocessing và estimator chỉ fit trên train.
- [ ] Threshold chỉ được chọn trên validation.
- [ ] Test chỉ được evaluate bằng bundle đã khóa.
- [ ] Bundle chứa đúng ordered feature list, prediction point và threshold.
- [ ] Metrics phù hợp với bài toán mất cân bằng, không chỉ có accuracy/ROC-AUC.
- [ ] Kết luận nêu cả lợi ích, rủi ro leakage và chi phí inference.
- [ ] Artifact và manifest là immutable, có hash để audit.
- [ ] Không còn implementation pandas song song của feature chính thức.

## 11. Cell nguyên tắc đề xuất cho notebook

Khi tạo notebook thử nghiệm mới, đặt một Markdown cell gần đầu notebook:

```markdown
## Feature ownership rule

Notebook này chỉ khám phá và đề xuất feature. Mọi feature dùng để tạo model
artifact phải được implement một lần trong dbt và được đọc từ ClickHouse ML
mart. Danh sách input chính thức lấy từ `dataset.feature_columns`; preprocessing,
training, threshold selection và evaluation phải gọi lại package
`fraudguard_ml`, không được định nghĩa thành pipeline thứ hai trong notebook.
```

Cell này là lời nhắc cho người làm thí nghiệm, không thay thế contract, dbt tests
hay validation trong code.

## 12. Thứ tự triển khai khuyến nghị cho FraudGuard

1. **Làm ngay:** chốt semantics và leakage audit của nhóm balance
   delta/residual tại `post_ledger_update`.
2. **Làm ngay:** bổ sung implementation dbt cùng schema tests để
   `ml_training_candidates` thực sự cung cấp các cột mà
   `ml_training_transactions` đang tham chiếu.
3. **Làm ngay:** build/test dbt và validate training data contract trước khi chạy
   challenger.
4. **Sau đó:** để notebook đọc mart và đánh giá lại các feature đã materialize.
5. **Sau đó:** hoàn thành Phase 4, rồi để notebook gọi
   `train_and_select_threshold` và `evaluate_test_split` từ package dùng chung.
6. **Cuối cùng:** chạy baseline/challenger bằng config riêng, khóa bundle và so
   sánh trên cùng evaluation protocol.

Trật tự này giữ notebook hữu ích cho việc học và khám phá, đồng thời tránh biến
notebook thành nguồn chân lý thứ hai mà production pipeline không thể tái tạo.
