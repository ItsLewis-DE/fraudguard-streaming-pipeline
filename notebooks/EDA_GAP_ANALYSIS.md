# Đánh giá EDA hiện tại và các điểm cần bổ sung

## 1. Điểm mạnh của EDA hiện tại (giữ nguyên)

- Pipeline xử lý chunked (250k dòng) đúng cho file 6.3M dòng, có `sha256` + `git_commit` cho reproducibility.
- Data quality đầy đủ: null / empty / zero / negative / min-max trên toàn bộ dân số, có assertion schema.
- Phương pháp lấy mẫu chuẩn: reservoir sampling (mẫu tự nhiên) + stratified sampling theo `(type, step_day)` (mẫu chẩn đoán), kèm kiểm tra đại diện (representativeness gaps đều < 0.13 pp).
- Đã phát hiện đúng các vấn đề cốt lõi: nhãn lệch nặng (0.13%), fraud chỉ ở `CASH_OUT`/`TRANSFER`, zero-rate theo type × nhãn, hiệu ứng biên ngày 31.

## 2. Những phần còn thiếu — xếp theo ưu tiên

> Các con số dưới đây đã được kiểm chứng trực tiếp trên `data/data.csv` hiện tại (6,362,620 dòng). Nên đưa vào EDA dưới dạng biểu đồ + bảng để tài liệu hoá.

### P0 — Bắt buộc bổ sung

#### 2.1. Phân rã thời gian: fraud *count* vs fraud *rate* vs volume giao dịch

**Hiện trạng:** EDA chỉ vẽ fraud rate theo `step_day` và chỉ bàn về "spike" của ngày 31. Chưa tách được hiệu ứng **volume** khỏi hiệu ứng **fraud rate**.

**Phát hiện quan trọng nhất của bộ dữ liệu (chưa được nêu):**

- Số giao dịch fraud ≈ **đồng đều theo thời gian** (~250–300 giao dịch/ngày, ~270/25-step; tương quan fraud-count ↔ volume chỉ 0.13).
- Ngược lại, **volume hợp lệ sụp đổ theo thời gian**: ngày 1–2 ~500k giao dịch/ngày → ngày 3 chỉ 1,070 → ngày 6–17 ~400k → ngày 18–31 chỉ ~10k–60k → ngày 31 chỉ 272.
- Vì vậy **mọi "spike" fraud rate (ngày 3–5, 18–19, 31; giờ 2–5 AM)** đều là artifact của volume giảm, không phải fraud tăng. Ngày 31 không phải "fraud đột biến" mà là "volume hợp lệ biến mất, fraud tiếp tục đúng nhịp cũ".
- Giờ 2–5 AM: fraud rate ~1,600–2,230/10k vs ~6/10k ban ngày, nhưng số fraud mỗi giờ là đồng đều (~340/giờ) — nguyên nhân là volume hợp lệ ban đêm chỉ ~1k–3k giao dịch/giờ so với ~640k lúc 17–18h.

**Cách làm:** vẽ 3 biểu đồ cạnh nhau: (a) fraud count/ngày, (b) volume/ngày, (c) fraud rate/ngày — trên cùng trục thời gian, đánh dấu các cửa sổ 3–5, 18–19, 31. Lặp lại theo giờ trong ngày. Kết luận phải nêu rõ: *fraud là quá trình rate-constant, phần lớn biến thiên của fraud rate quan sát được là do volume hợp lệ giảm*.

#### 2.2. Cảnh báo distribution shift với temporal split (config hiện tại)

**Hiện trạng:** EDA chưa đối chiếu với split trong `configs/training_baseline.yaml` / `training_challenger_balance.yaml` (train ≤ step 500, val ≤ 620, test ≤ 743).

**Phát hiện đã kiểm chứng:**

| Split | Số dòng | Số fraud | Fraud rate/10k |
|---|---|---|---|
| train (step ≤ 500) | 6,061,807 | 5,561 | **9.2** |
| val (501–620) | 209,984 | 1,286 | **61.2** |
| test (621–743) | 90,829 | 1,366 | **150.4** |

Fraud rate val gấp 6.7× train, test gấp 16.4× train — **test set rơi vào vùng out-of-distribution và cực nhỏ (90k dòng)**. Hệ quả:

- Metric trên val/test sẽ dao động rất mạnh theo threshold; cần báo cáo metric theo từng ngày/window và kèm CI (bootstrap), không chỉ 1 con số tổng.
- Khuyến nghị kiểm tra thêm: giữ split temporal nhưng đánh giá riêng trên "ngày lành" (6–17) so với "ngày suy thoái volume" (18–31).

#### 2.3. Audit nhất quán số dư (balance-consistency) — feature leakage

**Hiện trạng:** EDA mới dừng ở zero-rate. Chưa kiểm tra mối quan hệ `amount ↔ oldbalance ↔ newbalance` — **đây là thứ quan trọng nhất cho việc lựa chọn feature** vì `training_challenger_balance.yaml` đang dùng `origin_amount_residual`, `destination_amount_residual`.

**Phát hiện đã kiểm chứng** (residual = `amount − (oldbalanceOrg − newbalanceOrig)`):

| Type | Fraud có residual = 0 | Non-fraud có residual = 0 |
|---|---|---|
| CASH_OUT | **99.4%** | 10.5% |
| TRANSFER | **99.5%** | 3.6% |
| DEBIT | — | 68.9% |
| PAYMENT | — | 44.0% |
| CASH_IN | — | 0.0% |

- Fraud luôn được mô phỏng với phép tính số dư chính xác → residual ≈ 0 gần như là **chữ ký bất biến của fraud**. Đây vừa là feature mạnh nhất (nên giữ và validate `origin_amount_residual`) vừa là rủi ro leakage nếu test set không được sinh độc lập (ở dataset này test vẫn là cùng phân bố nên OK, nhưng phải ghi rõ trong tài liệu model).
- Phía dest: fraud TRANSFER có `oldbalanceDest`/`newbalanceDest` = 0 tới **99.3–99.9%** → **destination balance gần như vô dụng để nhận diện fraud TRANSFER** (trong khi với non-fraud lại được cập nhật đầy đủ, 70% residual=0). Đây là điều cần nêu thay vì chỉ "audit kĩ".
- CASH_IN có residual=0 ở **0%** cả hai phía — balance hai phía đều không nhất quán với amount.

#### 2.4. Chữ ký "rút cạn tài khoản" (balance fully emptied)

**Phát hiện đã kiểm chứng:**

- CASH_OUT fraud: `amount == oldbalanceOrg` ở **99.4%**, `newbalanceOrig == 0` ở **99.98%** — fraudster rút đúng toàn bộ số dư.
- TRANSFER fraud: `amount == oldbalanceOrg` ở **96.2%**, `newbalanceOrig == 0` ở **96.1%**.
- `oldbalanceOrg > 0` ở **99.5%** fraud (khớp nhận xét hiện tại ở cell 29, nhưng nên định lượng).
- Cần vẽ tỷ lệ `amount / oldbalanceOrg` (log) theo type × nhãn — với CASH_OUT đây là feature một chiều gần như tách được 2 lớp.

### P1 — Nên bổ sung

#### 2.5. Phân tích account graph (các kết quả âm tính đáng giá)

**Hiện trạng:** `nameOrig`/`nameDest` chưa được khai thác ngoài việc tính zero-rate.

**Phát hiện đã kiểm chứng (tiết kiệm công sức feature engineering):**

- 8,213 fraud origins — **mỗi account đúng 1 lần fraud** (0 account tái phạm) → các feature velocity theo origin (số giao dịch/account) **vô ích** cho việc phát hiện fraud.
- Fraud recipients nhận tối đa 2 lần fraud (44/8,169 account nhận 2 lần).
- **Không có chuỗi mule**: 0 giao dịch mà recipient của fraud TRANSFER sau đó trở thành origin của fraud CASH_OUT (kể cả trong cửa sổ 6 giờ) → không nên xây chain feature kiểu mule-network.
- Không có self-transfer (`nameOrig == nameDest`), không có dòng duplicate chính xác.
- Toàn bộ fraud đổ về account prefix `C`; `PAYMENT` luôn về prefix `M` — đây là hệ quả của cấu trúc mô phỏng (M = merchant không nhận fraud), không nên dùng prefix làm feature vì nó tương đương với `type`.

#### 2.6. Audit `isFlaggedFraud` — không được dùng làm feature

**Phát hiện đã kiểm chứng:** quy tắc flag = `TRANSFER` & `amount > 200,000`:

- 409,110 TRANSFER có amount > 200k → chỉ **16** được flag (**0.58%**); trong đó có 2,740 là fraud thật → **flag bắt được 16/2,740 = 0.6% fraud đủ điều kiện**.
- `isFlaggedFraud` là hàm tất định của (type, amount) và nằm trong `forbidden_feature_columns` — EDA nên xác nhận điều này (biến đổi 1-1 với `(type=='TRANSFER') & (amount>200k)` trên 16 dòng) để chốt luận điểm "cấm làm feature vì là leakage/tầm thường".

#### 2.7. Phân phối đơn biến và tương quan của các feature số dư

**Hiện trạng:** chỉ có zero-rate heatmap + ECDF của `amount`. Thiếu:

- ECDF/histogram log của `oldbalanceOrg`, `newbalanceOrig`, `oldbalanceDest`, `newbalanceDest` theo nhãn (toàn bộ đều rất lệch, mass lớn tại 0 — xác nhận "0 là giá trị thật" ở cell 15 nhưng chưa cho thấy hình dạng phần > 0).
- Correlation matrix trên mẫu chẩn đoán (oversampled): `oldbalanceOrg ↔ newbalanceOrig = 0.9988` (đa cộng tuyến gần hoàn hảo → khi hồi quy nên chọn 1 trong 2 hoặc dùng delta/residual); `amount ↔ oldbalanceOrg ≈ 0`; `amount ↔ oldbalanceDest = 0.29`.
- Định lượng tương quan với target (point-biserial, mẫu chẩn đoán): `amount 0.37`, `step 0.32`, `residual_abs −0.13` (nhỏ hơn = gần 0 = fraud), `newbalanceOrig −0.11`.
- Nên dùng chi-square/Cramér's V cho `type ↔ isFraud`.

### P2 — Chi tiết, làm nếu còn thời gian

#### 2.8. Các dòng biên (edge cases) và quyết định xử lý

- **16 dòng fraud CASH_OUT có `amount = 0`** (toàn bộ số dư cũng 0; 11/16 có dest balance thay đổi bằng amount=0 → vô nghĩa). Đây là "giao dịch 0 đồng" mô phỏng trục trặc — cần quyết định loại bỏ hay giữ ở bước preprocessing.
- Ngày 31: 272 dòng, 100% fraud, chỉ 23 giờ (step 721–743) — đã nêu nhưng nên chốt hẳn: **loại khỏi train** (test config đang kết thúc 31T23:00 nên test set sẽ chứa cả ngày này — cần quyết định chính thức).

#### 2.9. Overlap phân phối amount giữa fraud và non-fraud (bổ sung cho cell 22–23)

- CASH_OUT: tách tốt (fraud median 435k, p5 16.7k, p95 7.8M vs legit median 147k, p99 573k, max 2.8M) — nhưng **lưu ý fraud CASH_OUT cũng có đuôi nhỏ** (16 dòng = 0, p5 = 16.7k) nên "tiền lớn = fraud" không tuyệt đối.
- TRANSFER: **overlap gần như toàn phần** — fraud median 445.7k vs legit median 486.5k, cả hai đều có p99 = 10M, max legit 92.4M. Kết luận ở cell 23 đúng nhưng nên định lượng: riêng `amount` không phân tách được TRANSFER, cần residual/hour/type.

#### 2.10. Gợi ý section "Kết luận cho modeling" cuối notebook

Tổng hợp 5 điểm hành động từ EDA:

1. **Feature nên dùng:** `origin_amount_residual` (gần quyết định), `amount/oldbalanceOrg` ratio, `hour` (nếu muốn khai thác pattern volume — thận trọng vì chỉ phản ánh volume hợp lệ giảm), residual dest side.
2. **Feature cấm:** `isFlaggedFraud` (leakage tầm thường), prefix account (≡ type), balance features nếu test set sinh độc lập (rủi ro leakage).
3. **Imbalance:** 0.13% → huấn luyện cần class weight/oversampling, đánh giá bằng **PR curve + threshold tuning**, không dùng accuracy.
4. **Temporal split:** tồn tại distribution shift 9 → 61 → 150/10k; báo cáo metric theo window + CI.
5. **Không cần tốn công:** velocity features theo origin, mule-chain features — dữ liệu chứng minh không tồn tại (mục 2.5).

## 3. Bảng tổng hợp ưu tiên

| ID | Nội dung | Ưu tiên | Ảnh hưởng |
|---|---|---|---|
| 2.1 | Phân rã time: count vs rate vs volume | P0 | Hiểu đúng bản chất dữ liệu |
| 2.2 | Distribution shift theo temporal split | P0 | Thiết kế eval, chọn metric |
| 2.3 | Audit balance-consistency / residual | P0 | Chọn feature, chống leakage |
| 2.4 | Chữ ký "rút cạn tài khoản" | P0 | Feature engineering CASH_OUT |
| 2.5 | Account graph (kết quả âm tính) | P1 | Tiết kiệm công FE |
| 2.6 | Audit isFlaggedFraud | P1 | Chốt forbidden feature |
| 2.7 | Univariate + correlation | P1 | Đa cộng tuyến, chọn feature |
| 2.8 | Edge cases (amount=0, ngày 31) | P2 | Quyết định preprocessing |
| 2.9 | Overlap amount TRANSFER | P2 | Củng cố kết luận cell 23 |
| 2.10 | Kết luận cho modeling | P2 | Cầu nối EDA → training |
