# Kiến thức scikit-learn cần nắm để làm dự án Machine Learning

> Tài liệu thực hành dành cho người đã biết Python cơ bản và muốn xây dựng một dự án Machine Learning có quy trình đúng, kết quả đáng tin cậy và có thể triển khai.
>
> Tên thư viện đúng là **scikit-learn**, package import là **`sklearn`**. Nội dung được đối chiếu với tài liệu ổn định **scikit-learn 1.9.0** ngày 15/08/2026.

## Mục lục

1. [Scikit-learn dùng để làm gì?](#1-scikit-learn-dùng-để-làm-gì)
2. [Kiến thức nền cần có](#2-kiến-thức-nền-cần-có)
3. [Tư duy API thống nhất](#3-tư-duy-api-thống-nhất)
4. [Quy trình chuẩn của một dự án](#4-quy-trình-chuẩn-của-một-dự-án)
5. [Chia dữ liệu đúng cách](#5-chia-dữ-liệu-đúng-cách)
6. [Tiền xử lý dữ liệu](#6-tiền-xử-lý-dữ-liệu)
7. [Pipeline và ColumnTransformer](#7-pipeline-và-columntransformer)
8. [Các nhóm mô hình nên biết](#8-các-nhóm-mô-hình-nên-biết)
9. [Đánh giá mô hình](#9-đánh-giá-mô-hình)
10. [Cross-validation](#10-cross-validation)
11. [Tối ưu siêu tham số](#11-tối-ưu-siêu-tham-số)
12. [Mất cân bằng lớp và ngưỡng dự đoán](#12-mất-cân-bằng-lớp-và-ngưỡng-dự-đoán)
13. [Giải thích và kiểm tra mô hình](#13-giải-thích-và-kiểm-tra-mô-hình)
14. [Lưu và triển khai mô hình](#14-lưu-và-triển-khai-mô-hình)
15. [Mẫu dự án classification hoàn chỉnh](#15-mẫu-dự-án-classification-hoàn-chỉnh)
16. [Các lỗi thường gặp](#16-các-lỗi-thường-gặp)
17. [Cấu trúc thư mục đề xuất](#17-cấu-trúc-thư-mục-đề-xuất)
18. [Checklist trước khi bàn giao](#18-checklist-trước-khi-bàn-giao)
19. [Lộ trình học](#19-lộ-trình-học)
20. [Bài thực hành đầu tiên với dữ liệu FraudGuard](#20-bài-thực-hành-đầu-tiên-với-dữ-liệu-fraudguard)
21. [Hiểu Logistic Regression thay vì chỉ gọi API](#21-hiểu-logistic-regression-thay-vì-chỉ-gọi-api)
22. [Đọc Phase 4 của dự án bằng tư duy ML](#22-đọc-phase-4-của-dự-án-bằng-tư-duy-ml)
23. [Cách debug scikit-learn cho người mới](#23-cách-debug-scikit-learn-cho-người-mới)
24. [Tài liệu chính thức](#24-tài-liệu-chính-thức)

---

## 1. Scikit-learn dùng để làm gì?

Scikit-learn là thư viện Machine Learning tổng quát cho dữ liệu dạng bảng. Thư viện cung cấp:

- Học có giám sát: classification và regression.
- Học không giám sát: clustering, giảm chiều, phát hiện bất thường.
- Tiền xử lý dữ liệu và tạo đặc trưng.
- Chia dữ liệu, cross-validation và tối ưu siêu tham số.
- Metric đánh giá.
- Pipeline để đóng gói toàn bộ quy trình.
- Công cụ kiểm tra và giải thích mô hình.

Scikit-learn đặc biệt phù hợp với:

- Dự đoán khách hàng rời bỏ.
- Chấm điểm tín dụng/rủi ro.
- Phát hiện gian lận.
- Dự báo giá hoặc nhu cầu từ dữ liệu dạng bảng.
- Phân loại văn bản bằng TF-IDF.
- Phân khúc khách hàng.
- Xây dựng baseline trước khi dùng mô hình phức tạp hơn.

Scikit-learn **không phải lựa chọn chính** cho deep learning quy mô lớn, xử lý ảnh/video thô hoặc huấn luyện mô hình ngôn ngữ lớn.

---

## 2. Kiến thức nền cần có

### Python

Cần dùng được:

- Biến, hàm, vòng lặp, list/dict.
- Import module.
- Xử lý ngoại lệ cơ bản.
- Môi trường ảo và cài package.
- Đọc thông báo lỗi.

### NumPy và pandas

Cần hiểu:

- `ndarray`, `Series`, `DataFrame`.
- Hàng là quan sát, cột là đặc trưng.
- Kiểu dữ liệu số, chuỗi, category, datetime.
- Lọc dữ liệu, xử lý giá trị thiếu, `groupby`, `merge`.
- Shape của dữ liệu.

Quy ước quan trọng:

```text
X.shape = (n_samples, n_features)
y.shape = (n_samples,)
```

### Kiến thức Machine Learning

Cần phân biệt:

- Feature (`X`) và target (`y`).
- Classification, regression và clustering.
- Train, validation và test.
- Overfitting và underfitting.
- Parameter và hyperparameter.
- Metric kỹ thuật và mục tiêu kinh doanh.

---

## 3. Tư duy API thống nhất

Hầu hết đối tượng trong scikit-learn dùng chung một giao diện.

### Estimator

```python
model.fit(X_train, y_train)
y_pred = model.predict(X_test)
```

Một số classifier còn có:

```python
y_score = model.decision_function(X_test)
y_proba = model.predict_proba(X_test)[:, 1]
```

### Transformer

```python
transformer.fit(X_train)
X_train_new = transformer.transform(X_train)
X_test_new = transformer.transform(X_test)
```

Viết gọn trên tập train:

```python
X_train_new = transformer.fit_transform(X_train)
```

Không được gọi `fit_transform(X_test)`, vì transformer sẽ học thông tin từ tập test.

### Quy ước tên thuộc tính

- Tham số truyền vào constructor: `model.get_params()`.
- Thuộc tính học được sau `fit` thường có dấu gạch dưới ở cuối: `classes_`, `coef_`, `feature_names_in_`.
- Thay tham số: `model.set_params(max_depth=5)`.

### Clone thay vì tái sử dụng mô hình đã fit

```python
from sklearn.base import clone

new_model = clone(model)
```

`clone` giữ cấu hình nhưng không giữ trạng thái đã học.

---

## 4. Quy trình chuẩn của một dự án

```text
Bài toán kinh doanh
        ↓
Định nghĩa target, đơn vị quan sát và thời điểm dự đoán
        ↓
Thu thập + kiểm tra chất lượng dữ liệu
        ↓
Tách test độc lập
        ↓
EDA chỉ trên dữ liệu train
        ↓
Baseline đơn giản
        ↓
Pipeline tiền xử lý + mô hình
        ↓
Cross-validation + chọn metric
        ↓
Tuning trên tập train
        ↓
Đánh giá một lần trên test
        ↓
Phân tích lỗi, độ ổn định, rủi ro và công bằng
        ↓
Lưu toàn bộ pipeline + triển khai + giám sát
```

Trước khi code, cần trả lời:

1. Một hàng dữ liệu đại diện cho gì?
2. Target là gì và được quan sát ở thời điểm nào?
3. Khi dự đoán thực tế, những feature nào thật sự có sẵn?
4. Sai false positive và false negative gây thiệt hại thế nào?
5. Dữ liệu test có đại diện cho tương lai không?
6. Metric nào phản ánh đúng mục tiêu kinh doanh?

---

## 5. Chia dữ liệu đúng cách

### Dữ liệu độc lập, phân bố tương đối ổn định

```python
from sklearn.model_selection import train_test_split

X_train, X_test, y_train, y_test = train_test_split(
    X,
    y,
    test_size=0.2,
    random_state=42,
    stratify=y,  # nên dùng cho classification
)
```

### Dữ liệu theo thời gian

Không shuffle tương lai vào quá khứ.

```python
from sklearn.model_selection import TimeSeriesSplit

cv = TimeSeriesSplit(n_splits=5)
```

Tập test cuối nên là giai đoạn mới nhất.

### Nhiều hàng thuộc cùng một đối tượng

Ví dụ một khách hàng có nhiều giao dịch hoặc một bệnh nhân có nhiều lần khám. Không để cùng một đối tượng xuất hiện ở cả train và validation/test.

```python
from sklearn.model_selection import GroupKFold, GroupShuffleSplit

cv = GroupKFold(n_splits=5)
```

### Chọn splitter

| Dữ liệu | Cách chia thường dùng |
|---|---|
| Classification thông thường | `StratifiedKFold` |
| Regression thông thường | `KFold` |
| Theo thời gian | `TimeSeriesSplit` |
| Có nhóm/đối tượng lặp lại | `GroupKFold` |
| Vừa cần giữ tỷ lệ lớp vừa có nhóm | `StratifiedGroupKFold` |

Tập test phải được “niêm phong”: không dùng để chọn feature, chọn model, tuning hay đặt threshold.

---

## 6. Tiền xử lý dữ liệu

### Giá trị thiếu

```python
from sklearn.impute import SimpleImputer

num_imputer = SimpleImputer(strategy="median")
cat_imputer = SimpleImputer(strategy="most_frequent")
```

Các lựa chọn:

- Số: `mean`, `median`, `constant`.
- Phân loại: `most_frequent`, `constant`.
- Nâng cao: `KNNImputer`, `IterativeImputer`.

Giá trị thiếu đôi khi mang thông tin. Có thể thêm cờ:

```python
SimpleImputer(strategy="median", add_indicator=True)
```

### Chuẩn hóa dữ liệu số

```python
from sklearn.preprocessing import StandardScaler, MinMaxScaler, RobustScaler
```

- `StandardScaler`: lựa chọn mặc định cho linear model, SVM, KNN, PCA.
- `MinMaxScaler`: đưa dữ liệu về một khoảng, nhạy với outlier.
- `RobustScaler`: bền hơn khi có outlier.
- Tree-based model thường không cần scaling.

### Mã hóa biến phân loại

```python
from sklearn.preprocessing import OneHotEncoder

encoder = OneHotEncoder(
    handle_unknown="ignore",
    min_frequency=5,
)
```

`handle_unknown="ignore"` giúp pipeline không lỗi khi production gặp category chưa thấy lúc train.

Không dùng `LabelEncoder` cho các cột đầu vào `X`; công cụ này chủ yếu dành cho target `y`. Nếu category có thứ tự thực, dùng `OrdinalEncoder` với thứ tự được định nghĩa rõ.

### Feature ngày giờ

Không nên đưa datetime thô trực tiếp vào đa số mô hình. Có thể tạo:

- Năm, tháng, ngày trong tuần.
- Giờ.
- Ngày lễ/cuối tuần.
- Thời gian kể từ một mốc.
- Đặc trưng chu kỳ bằng `sin`/`cos` nếu phù hợp.

Mọi feature phải sử dụng thông tin có sẵn tại **thời điểm dự đoán**.

### Dữ liệu văn bản

Baseline hiệu quả:

```python
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline

text_model = make_pipeline(
    TfidfVectorizer(ngram_range=(1, 2), min_df=3),
    LogisticRegression(max_iter=1000),
)
```

### Feature selection và giảm chiều

Các công cụ thường gặp:

- `SelectKBest`, `SelectPercentile`.
- `RFE`, `RFECV`.
- `SelectFromModel`.
- `PCA`, `TruncatedSVD`.

Feature selection/PCA phải nằm trong pipeline để mỗi fold chỉ học từ phần train.

---

## 7. Pipeline và ColumnTransformer

Đây là phần quan trọng nhất khi làm dự án.

### Vì sao cần Pipeline?

- Chống data leakage.
- Áp dụng đúng cùng một tiền xử lý khi train và predict.
- Cho phép cross-validation/tuning toàn bộ quy trình.
- Lưu và triển khai một object duy nhất.
- Giảm code thủ công và lỗi lệch feature.

### Tiền xử lý dữ liệu hỗn hợp

```python
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

numeric_features = ["age", "income", "tenure_months"]
categorical_features = ["city", "plan"]

numeric_pipeline = Pipeline(
    steps=[
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
    ]
)

categorical_pipeline = Pipeline(
    steps=[
        ("imputer", SimpleImputer(strategy="most_frequent")),
        (
            "onehot",
            OneHotEncoder(
                handle_unknown="ignore",
                min_frequency=5,
            ),
        ),
    ]
)

preprocessor = ColumnTransformer(
    transformers=[
        ("num", numeric_pipeline, numeric_features),
        ("cat", categorical_pipeline, categorical_features),
    ],
    remainder="drop",
)
```

### Ghép với mô hình

```python
from sklearn.linear_model import LogisticRegression

pipeline = Pipeline(
    steps=[
        ("preprocess", preprocessor),
        (
            "model",
            LogisticRegression(
                max_iter=1000,
                class_weight="balanced",
            ),
        ),
    ]
)

pipeline.fit(X_train, y_train)
y_proba = pipeline.predict_proba(X_test)[:, 1]
```

### Truy cập thành phần

```python
pipeline.named_steps["model"]
pipeline.named_steps["preprocess"]
pipeline.get_params().keys()
```

Tên tham số bên trong pipeline có dạng:

```text
<tên_bước>__<tên_tham_số>
```

Ví dụ:

```python
pipeline.set_params(model__C=0.1)
```

---

## 8. Các nhóm mô hình nên biết

### Classification

| Mô hình | Khi nên thử | Lưu ý |
|---|---|---|
| `DummyClassifier` | Baseline bắt buộc | Không phải mô hình cuối |
| `LogisticRegression` | Baseline mạnh, dễ giải thích | Cần scaling; quan hệ gần tuyến tính |
| `DecisionTreeClassifier` | Quy tắc dễ hình dung | Rất dễ overfit |
| `RandomForestClassifier` | Baseline phi tuyến tốt | Lớn, có thể chậm |
| `HistGradientBoostingClassifier` | Dữ liệu bảng, quan hệ phi tuyến | Cần tuning vừa phải |
| `SVC` | Dataset nhỏ/vừa, biên phân lớp phức tạp | Chậm khi dữ liệu lớn; cần scaling |
| `KNeighborsClassifier` | Dataset nhỏ, cấu trúc cục bộ | Nhạy scaling và số chiều |
| `NaiveBayes` | Văn bản/sparse data | Giả định độc lập đơn giản |

### Regression

| Mô hình | Khi nên thử | Lưu ý |
|---|---|---|
| `DummyRegressor` | Baseline bắt buộc | Dự đoán trung bình/median |
| `LinearRegression` | Quan hệ gần tuyến tính | Nhạy đa cộng tuyến/outlier |
| `Ridge`, `Lasso`, `ElasticNet` | Linear model có regularization | Cần scaling |
| `RandomForestRegressor` | Phi tuyến, ít tiền xử lý | Có thể lớn/chậm |
| `HistGradientBoostingRegressor` | Dữ liệu bảng | Mạnh với phi tuyến |
| `SVR` | Dataset nhỏ/vừa | Cần scaling; tuning quan trọng |

### Unsupervised learning

- `KMeans`: cần chọn số cụm, nhạy scaling và outlier.
- `DBSCAN`: phát hiện cụm hình dạng bất kỳ và noise; nhạy `eps`.
- `AgglomerativeClustering`: clustering phân cấp.
- `PCA`: giảm chiều tuyến tính.
- `IsolationForest`: phát hiện bất thường.

Clustering không có “đáp án đúng” chỉ từ một metric. Cần kết hợp:

- Silhouette score hoặc metric nội tại.
- Độ ổn định của cụm.
- Khả năng diễn giải.
- Tính hữu ích trong nghiệp vụ.

### Chiến lược thực tế

1. Luôn có `Dummy*` baseline.
2. Thử một linear model.
3. Thử một tree ensemble.
4. Chỉ tăng độ phức tạp khi validation cho thấy lợi ích ổn định.

---

## 9. Đánh giá mô hình

### Classification

Từ confusion matrix:

| | Dự đoán âm | Dự đoán dương |
|---|---:|---:|
| Thực tế âm | TN | FP |
| Thực tế dương | FN | TP |

Các metric:

```text
Precision = TP / (TP + FP)
Recall    = TP / (TP + FN)
F1        = 2 × Precision × Recall / (Precision + Recall)
```

- **Accuracy**: chỉ phù hợp khi các lớp tương đối cân bằng và chi phí lỗi gần nhau.
- **Precision**: quan trọng khi false positive tốn kém.
- **Recall**: quan trọng khi bỏ sót positive tốn kém.
- **F1**: cân bằng precision và recall.
- **ROC AUC**: đánh giá khả năng xếp hạng trên nhiều threshold.
- **Average Precision (AP)**: tóm tắt đường precision-recall và thường hữu ích
  hơn ROC AUC khi positive hiếm. AP không hoàn toàn giống diện tích PR tính
  bằng quy tắc hình thang, vì cách nội suy khác nhau.
- **Log loss**: đánh giá chất lượng xác suất và phạt dự đoán tự tin nhưng sai.
- **Balanced accuracy**: hữu ích khi lệch lớp.

Ví dụ:

```python
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    roc_auc_score,
    average_precision_score,
)

print(classification_report(y_test, y_pred))
print(confusion_matrix(y_test, y_pred))
print("ROC AUC:", roc_auc_score(y_test, y_proba))
print("Average precision:", average_precision_score(y_test, y_proba))
```

### Regression

- **MAE**: dễ diễn giải, ít nhạy outlier hơn MSE.
- **MSE/RMSE**: phạt lỗi lớn mạnh hơn.
- **R²**: tỷ lệ phương sai được giải thích; có thể âm trên dữ liệu test.
- **MAPE**: không phù hợp khi giá trị thật bằng hoặc gần 0.

```python
from sklearn.metrics import (
    mean_absolute_error,
    root_mean_squared_error,
    r2_score,
)

print("MAE:", mean_absolute_error(y_test, y_pred))
print("RMSE:", root_mean_squared_error(y_test, y_pred))
print("R²:", r2_score(y_test, y_pred))
```

### Metric âm trong API `scoring`

Scikit-learn quy ước scorer càng lớn càng tốt. Vì vậy loss có thể có tên như:

```python
scoring="neg_mean_absolute_error"
```

Muốn MAE thật:

```python
mae = -scores["test_score"].mean()
```

### Baseline

```python
from sklearn.dummy import DummyClassifier, DummyRegressor

DummyClassifier(strategy="prior")
DummyRegressor(strategy="mean")
```

Mô hình chỉ có giá trị khi vượt baseline theo metric phù hợp và mức cải thiện đủ ý nghĩa với nghiệp vụ.

---

## 10. Cross-validation

Cross-validation giúp ước lượng độ ổn định của mô hình tốt hơn một lần chia train/validation.

```python
from sklearn.model_selection import StratifiedKFold, cross_validate

cv = StratifiedKFold(
    n_splits=5,
    shuffle=True,
    random_state=42,
)

scores = cross_validate(
    pipeline,
    X_train,
    y_train,
    cv=cv,
    scoring={
        "roc_auc": "roc_auc",
        "average_precision": "average_precision",
        "f1": "f1",
    },
    return_train_score=True,
    n_jobs=-1,
)
```

Cần báo cáo:

- Trung bình qua các fold.
- Độ lệch chuẩn.
- Chênh lệch train và validation.
- Thời gian fit nếu có yêu cầu vận hành.

Ví dụ:

```python
import numpy as np

for metric in ["roc_auc", "average_precision", "f1"]:
    values = scores[f"test_{metric}"]
    print(f"{metric}: {np.mean(values):.3f} ± {np.std(values):.3f}")
```

Nếu train score cao hơn validation score nhiều, mô hình có dấu hiệu overfit.

---

## 11. Tối ưu siêu tham số

### RandomizedSearchCV

Thường nên thử trước `GridSearchCV` vì tiết kiệm tài nguyên hơn.

```python
from scipy.stats import loguniform
from sklearn.model_selection import RandomizedSearchCV

param_distributions = {
    "model__C": loguniform(1e-3, 1e2),
    "model__class_weight": [None, "balanced"],
}

search = RandomizedSearchCV(
    estimator=pipeline,
    param_distributions=param_distributions,
    n_iter=30,
    scoring="average_precision",
    cv=cv,
    n_jobs=-1,
    random_state=42,
    refit=True,
    return_train_score=True,
)

search.fit(X_train, y_train)

best_pipeline = search.best_estimator_
print(search.best_params_)
print(search.best_score_)
```

### Nguyên tắc tuning

- Tune cả pipeline, không chỉ model.
- Chọn không gian tìm kiếm có lý do.
- Không tune trên test.
- Không mặc định rằng nhiều tổ hợp hơn luôn tốt hơn.
- So sánh lợi ích với chi phí train/inference.
- Với nhiều lần thử và dataset nhỏ, cân nhắc nested cross-validation để có ước lượng ít thiên lệch hơn.

### Overfitting vào validation

Nếu thử quá nhiều ý tưởng trên cùng validation set, nhóm phát triển sẽ dần “học thuộc” validation. Cách giảm:

- Giữ test độc lập đến cuối.
- Ghi lại thí nghiệm.
- Hạn chế quyết định thủ công dựa trên test.
- Dùng CV phù hợp.

---

## 12. Mất cân bằng lớp và ngưỡng dự đoán

Với positive hiếm:

- Không chỉ nhìn accuracy.
- Ưu tiên precision, recall, F1, average precision.
- Dùng stratified split.
- Thử `class_weight="balanced"` nếu estimator hỗ trợ.
- Resampling phải thực hiện chỉ trên tập train của mỗi fold.
- Chọn threshold dựa trên chi phí kinh doanh.

### Chọn threshold

Mặc định classifier thường dùng 0.5, nhưng 0.5 không nhất thiết tối ưu.

```python
import numpy as np
from sklearn.metrics import precision_recall_curve

precision, recall, thresholds = precision_recall_curve(
    y_validation,
    validation_proba,
)

f1 = 2 * precision[:-1] * recall[:-1] / (
    precision[:-1] + recall[:-1] + 1e-12
)
best_threshold = thresholds[np.argmax(f1)]
```

Threshold phải chọn trên validation hoặc bằng phương pháp cross-validation, không chọn trên test.

### Calibration

Nếu xác suất được dùng để ra quyết định hoặc ước tính rủi ro:

- Kiểm tra calibration curve.
- Xem Brier score/log loss.
- Cân nhắc `CalibratedClassifierCV`.

Xác suất 0.8 nên có ý nghĩa gần với “khoảng 80% trường hợp tương tự là positive”.

---

## 13. Giải thích và kiểm tra mô hình

### Hệ số mô hình tuyến tính

- `coef_` thể hiện hướng và độ lớn tác động trong không gian feature sau tiền xử lý.
- Cần cẩn thận khi feature khác thang đo hoặc tương quan mạnh.
- Hệ số không tự động chứng minh quan hệ nhân quả.

### Permutation importance

```python
from sklearn.inspection import permutation_importance

result = permutation_importance(
    best_pipeline,
    X_test,
    y_test,
    scoring="average_precision",
    n_repeats=20,
    random_state=42,
    n_jobs=-1,
)
```

Permutation importance đo mức metric giảm khi đảo ngẫu nhiên một feature. Nên tính trên dữ liệu hold-out. Feature tương quan mạnh có thể làm importance của từng feature bị đánh giá thấp.

### Partial Dependence và ICE

Dùng để xem dự đoán thay đổi thế nào theo một hoặc hai feature. Không diễn giải như quan hệ nhân quả; kết quả có thể sai lệch khi feature phụ thuộc mạnh vào nhau.

### Error analysis

Không dừng ở một con số tổng:

- Kiểm tra các mẫu dự đoán sai tự tin nhất.
- So sánh metric theo phân khúc: khu vực, nhóm tuổi, loại sản phẩm, thời gian.
- Kiểm tra missingness và category mới.
- Kiểm tra dữ liệu trùng lặp.
- Kiểm tra drift giữa train và production.
- Kiểm tra độ công bằng nếu mô hình ảnh hưởng đến con người.

---

## 14. Lưu và triển khai mô hình

Nên lưu **toàn bộ pipeline**, không chỉ estimator cuối.

```python
import joblib

joblib.dump(best_pipeline, "model_pipeline.joblib")
loaded_pipeline = joblib.load("model_pipeline.joblib")
predictions = loaded_pipeline.predict(new_data)
```

### Cảnh báo bảo mật

Chỉ load file `pickle`/`joblib` từ nguồn tin cậy. File độc hại có thể thực thi mã khi được load.

### Tái lập môi trường

Cần lưu:

- Phiên bản Python.
- Phiên bản `scikit-learn`, `numpy`, `scipy`, `pandas`, `joblib`.
- Code tạo feature.
- Danh sách và schema feature.
- Thời điểm và phiên bản dữ liệu train.
- Metric, threshold và bộ test.
- Seed ngẫu nhiên.
- Commit hoặc phiên bản source code.

Không nên kỳ vọng model artifact luôn tương thích giữa các phiên bản scikit-learn khác nhau. Môi trường serving nên tái tạo môi trường training.

### Contract đầu vào

Trước khi `predict`, cần kiểm tra:

- Đủ cột bắt buộc.
- Đúng kiểu dữ liệu.
- Đơn vị đo đúng.
- Range hợp lệ.
- Quy tắc xử lý missing.
- Không có feature “tương lai”.

### Giám sát production

Theo dõi:

- Data/schema drift.
- Phân bố feature và prediction.
- Tỷ lệ category chưa gặp.
- Missing rate.
- Latency và lỗi hệ thống.
- Metric thực khi label đến muộn.
- Calibration và threshold.

---

## 15. Mẫu dự án classification hoàn chỉnh

```python
import json
import joblib
import numpy as np

from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    classification_report,
    confusion_matrix,
    roc_auc_score,
)
from sklearn.model_selection import (
    RandomizedSearchCV,
    StratifiedKFold,
    cross_validate,
    train_test_split,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


RANDOM_STATE = 42
TARGET = "churn"

# df là DataFrame đã được kiểm tra schema và chất lượng.
X = df.drop(columns=[TARGET])
y = df[TARGET]

# 1. Giữ test độc lập.
X_train, X_test, y_train, y_test = train_test_split(
    X,
    y,
    test_size=0.2,
    stratify=y,
    random_state=RANDOM_STATE,
)

# 2. Khai báo cột rõ ràng.
numeric_features = ["age", "income", "tenure_months"]
categorical_features = ["city", "plan"]

# 3. Tiền xử lý.
numeric_pipeline = Pipeline(
    steps=[
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
    ]
)

categorical_pipeline = Pipeline(
    steps=[
        ("imputer", SimpleImputer(strategy="most_frequent")),
        (
            "onehot",
            OneHotEncoder(
                handle_unknown="ignore",
                min_frequency=5,
            ),
        ),
    ]
)

preprocessor = ColumnTransformer(
    transformers=[
        ("num", numeric_pipeline, numeric_features),
        ("cat", categorical_pipeline, categorical_features),
    ]
)

# 4. Baseline.
baseline = Pipeline(
    steps=[
        ("preprocess", preprocessor),
        ("model", DummyClassifier(strategy="prior")),
    ]
)

# 5. Mô hình ứng viên.
pipeline = Pipeline(
    steps=[
        ("preprocess", preprocessor),
        (
            "model",
            LogisticRegression(
                max_iter=2000,
                random_state=RANDOM_STATE,
            ),
        ),
    ]
)

# 6. Cross-validation.
cv = StratifiedKFold(
    n_splits=5,
    shuffle=True,
    random_state=RANDOM_STATE,
)

scoring = {
    "roc_auc": "roc_auc",
    "average_precision": "average_precision",
    "f1": "f1",
}

for name, estimator in {
    "baseline": baseline,
    "logistic_regression": pipeline,
}.items():
    cv_scores = cross_validate(
        estimator,
        X_train,
        y_train,
        cv=cv,
        scoring=scoring,
        n_jobs=-1,
    )
    summary = {
        metric: {
            "mean": float(np.mean(cv_scores[f"test_{metric}"])),
            "std": float(np.std(cv_scores[f"test_{metric}"])),
        }
        for metric in scoring
    }
    print(name, json.dumps(summary, indent=2))

# 7. Tuning chỉ trên train.
param_distributions = {
    "model__C": np.logspace(-3, 2, 30),
    "model__class_weight": [None, "balanced"],
}

search = RandomizedSearchCV(
    estimator=pipeline,
    param_distributions=param_distributions,
    n_iter=20,
    scoring="average_precision",
    cv=cv,
    refit=True,
    n_jobs=-1,
    random_state=RANDOM_STATE,
)
search.fit(X_train, y_train)

best_pipeline = search.best_estimator_

# 8. Đánh giá một lần trên test.
y_pred = best_pipeline.predict(X_test)
y_proba = best_pipeline.predict_proba(X_test)[:, 1]

print("Best params:", search.best_params_)
print("Test ROC AUC:", roc_auc_score(y_test, y_proba))
print("Test AP:", average_precision_score(y_test, y_proba))
print("Confusion matrix:\n", confusion_matrix(y_test, y_pred))
print(classification_report(y_test, y_pred))

# 9. Lưu toàn bộ pipeline.
joblib.dump(best_pipeline, "churn_pipeline.joblib")
```

Trong dự án thật, threshold nên được chọn từ validation/out-of-fold prediction trước khi đánh giá test.

---

## 16. Các lỗi thường gặp

### 1. Tiền xử lý trước khi chia dữ liệu

Sai:

```python
X_scaled = scaler.fit_transform(X)
X_train, X_test = train_test_split(X_scaled)
```

Đúng: chia trước hoặc đặt scaler trong pipeline.

### 2. `fit` trên test

Không dùng:

```python
scaler.fit_transform(X_test)
```

Chỉ dùng:

```python
scaler.transform(X_test)
```

### 3. Chọn model bằng điểm test

Test không phải validation. Nếu đã dùng test để chọn model, test đó không còn là đánh giá độc lập.

### 4. Dùng accuracy khi lệch lớp

Nếu 99% là lớp 0, mô hình luôn dự đoán 0 đạt accuracy 99% nhưng không phát hiện positive nào.

### 5. Shuffle dữ liệu thời gian

Điều này cho mô hình “nhìn thấy tương lai”.

### 6. Cùng khách hàng ở train và test

Mô hình có thể học đặc điểm nhận dạng thay vì quy luật tổng quát.

### 7. Quên `handle_unknown`

One-hot encoder có thể lỗi khi gặp category mới ở production.

### 8. Không dùng baseline

Không biết mô hình phức tạp có thật sự tốt hơn quy tắc đơn giản hay không.

### 9. Nhầm `predict` với `predict_proba`

- `predict`: nhãn sau threshold.
- `predict_proba`: xác suất ước lượng.
- ROC AUC/PR AUC thường dùng score hoặc probability, không dùng nhãn cứng.

### 10. Tuning quá nhiều trên dataset nhỏ

Kết quả CV tốt nhất có thể chỉ là may mắn.

### 11. Lưu riêng model

Production có thể thiếu imputer, scaler, encoder hoặc sai thứ tự feature.

### 12. Coi feature importance là quan hệ nhân quả

Importance chỉ mô tả cách mô hình dự đoán trong dữ liệu quan sát được.

### 13. Không cố định randomness khi cần tái lập

Đặt `random_state` cho splitter và estimator ngẫu nhiên. Trong báo cáo cuối, vẫn cần đánh giá độ ổn định qua nhiều fold/seed khi rủi ro cao.

---

## 17. Cấu trúc thư mục đề xuất

```text
ml-project/
├── README.md
├── pyproject.toml
├── data/
│   ├── raw/
│   ├── interim/
│   └── processed/
├── notebooks/
│   ├── 01_eda.ipynb
│   └── 02_experiments.ipynb
├── src/
│   ├── data.py
│   ├── features.py
│   ├── train.py
│   ├── evaluate.py
│   └── predict.py
├── tests/
│   ├── test_data.py
│   ├── test_features.py
│   └── test_predict.py
├── models/
├── reports/
└── configs/
```

Notebook dùng để khám phá; logic cần tái sử dụng nên chuyển vào `src/` và có test.

---

## 18. Checklist trước khi bàn giao

### Bài toán và dữ liệu

- [ ] Định nghĩa rõ đơn vị quan sát, target và thời điểm dự đoán.
- [ ] Chỉ dùng feature có sẵn tại thời điểm dự đoán.
- [ ] Kiểm tra duplicate, missing, outlier, kiểu dữ liệu và label.
- [ ] Chia dữ liệu phù hợp với thời gian/nhóm.
- [ ] Test được giữ độc lập.

### Huấn luyện

- [ ] Có `DummyClassifier` hoặc `DummyRegressor`.
- [ ] Tiền xử lý nằm trong pipeline.
- [ ] CV phù hợp với cấu trúc dữ liệu.
- [ ] Metric khớp với chi phí kinh doanh.
- [ ] Báo cáo trung bình và độ lệch chuẩn qua fold.
- [ ] Tuning không sử dụng test.
- [ ] Kiểm tra overfitting.

### Đánh giá

- [ ] Có confusion matrix hoặc residual analysis.
- [ ] Có metric theo phân khúc quan trọng.
- [ ] Kiểm tra các lỗi nghiêm trọng.
- [ ] Threshold được chọn trên validation, không phải test.
- [ ] Nếu dùng probability, đã kiểm tra calibration.
- [ ] Có giới hạn, giả định và rủi ro được ghi lại.

### Triển khai

- [ ] Lưu toàn bộ pipeline.
- [ ] Lưu phiên bản môi trường.
- [ ] Có kiểm tra schema đầu vào.
- [ ] Có test cho prediction trên dữ liệu mẫu.
- [ ] Có kế hoạch theo dõi drift, latency và metric thực.
- [ ] Chỉ load model artifact từ nguồn tin cậy.

---

## 19. Lộ trình học

### Mức 1 — Đủ làm baseline

1. `train_test_split`.
2. `fit`, `predict`, `predict_proba`.
3. `DummyClassifier`/`DummyRegressor`.
4. Metric classification/regression.
5. `StandardScaler`, `OneHotEncoder`, `SimpleImputer`.

### Mức 2 — Đủ làm dự án đúng quy trình

1. `Pipeline`.
2. `ColumnTransformer`.
3. Cross-validation.
4. Split theo stratified/group/time.
5. `RandomizedSearchCV`.
6. Chống data leakage.
7. Error analysis.

### Mức 3 — Đủ đưa vào production

1. Calibration và threshold.
2. Feature importance/PDP/ICE.
3. Model persistence và dependency pinning.
4. Schema validation.
5. Unit/integration test.
6. Data drift, concept drift và monitoring.
7. Reproducibility và experiment tracking.

### Thứ tự dự án luyện tập

1. Iris classification: học API.
2. Titanic/churn: dữ liệu số + category + missing.
3. House price regression: metric và residual.
4. Text classification: TF-IDF + linear model.
5. Customer segmentation: preprocessing + clustering.
6. Dự án có thời gian: time-aware validation.

---

## 20. Bài thực hành đầu tiên với dữ liệu FraudGuard

Phần này cố ý dùng dữ liệu rất nhỏ để có thể nhìn thấy từng bước. Các metric
thu được **không có giá trị kết luận** vì dữ liệu là giả lập và quá ít dòng.
Mục tiêu là hiểu object nào học cái gì, dữ liệu đi qua pipeline ra sao và vì
sao test phải được giữ kín.

### 20.1. Kiểm tra môi trường

Tên package khi cài là `scikit-learn`, nhưng tên dùng khi import là `sklearn`:

```bash
python3 -c "import sklearn; print(sklearn.__version__)"
```

Nếu gặp `ModuleNotFoundError`, môi trường hiện tại chưa có scikit-learn. Hãy
cài dependency bằng công cụ quản lý môi trường mà repository đang sử dụng,
không cài bừa vào Python hệ thống. Việc cài package là thay đổi môi trường,
khác với câu lệnh `import` chỉ dùng package đã có.

### 20.2. Tạo một dataset nhỏ

Trong FraudGuard:

- Một hàng là một giao dịch.
- `X` chứa thông tin dùng để dự đoán.
- `y` là nhãn `is_fraud`: `1` nghĩa là fraud, `0` nghĩa là bình thường.
- `event_time` dùng để chia theo thời gian, không đưa vào estimator baseline.

```python
import pandas as pd

df = pd.DataFrame(
    {
        "event_time": pd.date_range(
            "2026-01-01", periods=15, freq="h", tz="UTC"
        ),
        "transaction_type": [
            "PAYMENT", "TRANSFER", "CASH_OUT", "PAYMENT", "TRANSFER",
            "CASH_OUT", "PAYMENT", "TRANSFER", "CASH_OUT", "PAYMENT",
            "TRANSFER", "CASH_OUT", "PAYMENT", "TRANSFER", "CASH_OUT",
        ],
        "amount": [
            20, 9000, 300, 45, 15000, 500, 70, 12000, 250,
            35, 18000, 450, 55, 22000, 600,
        ],
        "origin_balance_before": [
            500, 10000, 900, 800, 16000, 1200, 950, 13000, 700,
            600, 19000, 1000, 750, 23000, 1300,
        ],
        "destination_balance_before": [
            100, 200, 400, 120, 0, 500, 180, 100, 600,
            200, 0, 700, 250, 0, 800,
        ],
        "is_fraud": [0, 0, 0, 0, 1, 0, 0, 1, 0, 0, 1, 0, 0, 1, 0],
    }
)

FEATURES = [
    "transaction_type",
    "amount",
    "origin_balance_before",
    "destination_balance_before",
]
TARGET = "is_fraud"

X = df.loc[:, FEATURES]
y = df[TARGET]

print(X.shape)       # (15, 4): 15 giao dịch, 4 feature
print(y.shape)       # (15,): một nhãn cho mỗi giao dịch
print(y.value_counts())
```

Không dùng `df.drop(columns=[TARGET])` một cách máy móc trong dự án thật, vì
cách đó có thể vô tình đưa ID, thời gian hoặc cột audit vào model. Danh sách
cho phép như `FEATURES` an toàn và dễ audit hơn.

### 20.3. Chia train, validation và test theo thời gian

Ví dụ đã được sắp tăng dần theo `event_time`:

```python
train = df.iloc[:9]
validation = df.iloc[9:12]
test = df.iloc[12:]

X_train = train.loc[:, FEATURES]
y_train = train[TARGET]
X_validation = validation.loc[:, FEATURES]
y_validation = validation[TARGET]
X_test = test.loc[:, FEATURES]
y_test = test[TARGET]

assert train["event_time"].max() < validation["event_time"].min()
assert validation["event_time"].max() < test["event_time"].min()
```

Vai trò của ba phần khác nhau:

| Split | Được dùng để làm gì? | Không được dùng để làm gì? |
|---|---|---|
| Train | Học imputer, scaler, category và hệ số model | Báo cáo chất lượng cuối |
| Validation | Chọn model, hyperparameter và threshold | Fit lại preprocessing |
| Test | Đánh giá đúng một lần sau khi quyết định đã khóa | Chọn threshold/model |

Trong repository, `DatasetSplits` và `read_one_split` thực hiện cùng ý tưởng
này trên snapshot Parquet bằng các mốc thời gian từ config.

### 20.4. Tạo và fit toàn bộ pipeline

```python
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

categorical_features = ["transaction_type"]
numeric_features = [
    "amount",
    "origin_balance_before",
    "destination_balance_before",
]

categorical_pipeline = Pipeline(
    steps=[
        ("imputer", SimpleImputer(strategy="most_frequent")),
        ("one_hot", OneHotEncoder(handle_unknown="ignore")),
    ]
)

numeric_pipeline = Pipeline(
    steps=[
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
    ]
)

preprocessing = ColumnTransformer(
    transformers=[
        ("categorical", categorical_pipeline, categorical_features),
        ("numeric", numeric_pipeline, numeric_features),
    ]
)

pipeline = Pipeline(
    steps=[
        ("preprocessing", preprocessing),
        (
            "estimator",
            LogisticRegression(
                class_weight="balanced",
                max_iter=500,
                random_state=42,
            ),
        ),
    ]
)

pipeline.fit(X_train, y_train)
```

Khi gọi dòng cuối, thứ tự thực tế là:

```text
X_train
  → categorical: học mode và danh sách category → one-hot
  → numeric: học median, mean và standard deviation → scale
  → ghép các cột đã biến đổi
  → LogisticRegression học các hệ số
```

Validation/test chỉ đi qua `transform`; chúng không làm thay đổi median, mean,
category hay hệ số đã học.

Có thể quan sát pipeline sau khi fit:

```python
feature_names = (
    pipeline.named_steps["preprocessing"].get_feature_names_out()
)
coefficients = pipeline.named_steps["estimator"].coef_[0]

coefficient_table = pd.DataFrame(
    {"feature": feature_names, "coefficient": coefficients}
).sort_values("coefficient", ascending=False)

print(coefficient_table)
```

Tên sau biến đổi có thể giống
`categorical__transaction_type_TRANSFER`. Một cột category ban đầu có thể trở
thành nhiều cột one-hot, nên số feature sau preprocessing thường khác 4.

### 20.5. Score, probability và prediction khác nhau thế nào?

```python
validation_probability = pipeline.predict_proba(X_validation)[:, 1]
validation_prediction_at_05 = pipeline.predict(X_validation)

print(validation_probability)
print(validation_prediction_at_05)
```

Với binary classifier, `predict_proba` trả ma trận `(n_samples, 2)`:

- Cột `0`: xác suất ước lượng cho lớp `0`.
- Cột `1`: xác suất ước lượng cho lớp `1` (fraud).
- `[:, 1]`: lấy probability fraud của tất cả các hàng.

`predict` chuyển score thành nhãn bằng quy tắc mặc định của estimator. Trong
FraudGuard, không dựa vào mặc định đó; dự án khóa một threshold được chọn trên
validation:

```python
import numpy as np
from sklearn.metrics import precision_recall_curve

precision, recall, thresholds = precision_recall_curve(
    y_validation,
    validation_probability,
)

# precision và recall dài hơn thresholds một phần tử. Phần tử cuối không có
# threshold tương ứng, vì vậy phải dùng precision[:-1] và recall[:-1].
candidate_indices = np.flatnonzero(precision[:-1] >= 0.50)

if len(candidate_indices) > 0:
    best_index = candidate_indices[
        np.argmax(recall[:-1][candidate_indices])
    ]
else:
    denominator = precision[:-1] + recall[:-1]
    f1 = np.divide(
        2 * precision[:-1] * recall[:-1],
        denominator,
        out=np.zeros_like(denominator),
        where=denominator > 0,
    )
    best_index = int(np.argmax(f1))

threshold = float(thresholds[best_index])
print("Locked threshold:", threshold)
```

`0.50` ở đây chỉ để minh họa. Config hiện tại của dự án dùng
`min_precision: 0.10`; ý nghĩa nghiệp vụ của mức này phải được giải thích trong
báo cáo, không nên coi nó là hằng số đúng cho mọi hệ thống fraud.

### 20.6. Đánh giá test sau khi đã khóa threshold

```python
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    precision_score,
    recall_score,
    roc_auc_score,
)

test_probability = pipeline.predict_proba(X_test)[:, 1]
test_prediction = (test_probability >= threshold).astype("uint8")

print("Confusion matrix:\n", confusion_matrix(y_test, test_prediction))
print("Precision:", precision_score(y_test, test_prediction, zero_division=0))
print("Recall:", recall_score(y_test, test_prediction, zero_division=0))
print("Average precision:", average_precision_score(y_test, test_probability))
print("ROC AUC:", roc_auc_score(y_test, test_probability))
```

Hai nhóm metric trả lời hai câu hỏi khác nhau:

- Average Precision và ROC AUC dùng probability, đo khả năng **xếp hạng** qua
  nhiều threshold.
- Precision, recall và confusion matrix dùng nhãn sau threshold, đo **quyết
  định vận hành** tại threshold đã khóa.

Với tập nhỏ, metric có thể nhảy mạnh chỉ vì một giao dịch đổi kết quả. Trên dữ
liệu thật cần báo cả số đếm `TP/FP/FN/TN`, tỷ lệ fraud và kích thước mỗi split.

---

## 21. Hiểu Logistic Regression thay vì chỉ gọi API

Tên có chữ “Regression”, nhưng `LogisticRegression` là mô hình
**classification**. Với mỗi giao dịch, mô hình tính một điểm tuyến tính:

```text
z = b + w₁x₁ + w₂x₂ + ... + wₙxₙ
```

Sau đó hàm sigmoid đổi điểm đó thành số trong khoảng 0 đến 1:

```text
p(fraud | x) = 1 / (1 + exp(-z))
```

- `wᵢ > 0`: khi feature tăng, log-odds fraud có xu hướng tăng, nếu các feature
  khác được giữ nguyên.
- `wᵢ < 0`: log-odds fraud có xu hướng giảm.
- `|wᵢ|` lớn không tự động có nghĩa feature quan trọng hơn nếu các feature chưa
  cùng thang đo hoặc tương quan mạnh.
- Đây là quan hệ dự đoán, không phải bằng chứng nhân quả.

### 21.1. Vì sao cần StandardScaler?

`amount` có thể hàng chục nghìn, còn cột cờ chỉ là 0/1. Scaling đưa các feature
số về thang đo gần nhau:

```text
x_scaled = (x - mean_train) / std_train
```

`mean_train` và `std_train` chỉ được học trên train. Scaling giúp quá trình tối
ưu Logistic Regression ổn định hơn và khiến regularization đối xử hợp lý hơn
với các feature khác đơn vị.

### 21.2. Regularization và tham số `C`

Regularization phạt hệ số quá lớn để giảm overfitting. Trong scikit-learn,
`C` là **nghịch đảo** của độ mạnh regularization:

| Giá trị `C` | Regularization | Hệ quả thường thấy |
|---:|---|---|
| Nhỏ, ví dụ `0.01` | Mạnh | Hệ số co nhỏ, model đơn giản hơn, có thể underfit |
| Lớn, ví dụ `100` | Yếu | Model bám train hơn, có thể overfit |

Do đó `regularization_c: 1.0` trong config là hyperparameter, không phải hệ số
đã học. Muốn thay nó phải đánh giá trên validation/CV, không nhìn test.

### 21.3. `class_weight="balanced"` làm gì?

Khi fraud hiếm, lỗi trên một mẫu fraud được gán trọng số lớn hơn lỗi trên một
mẫu bình thường. Scikit-learn tính trọng số lớp gần theo công thức:

```text
n_samples / (n_classes × số mẫu của lớp)
```

Điều này thay đổi hàm loss lúc **train**; nó không:

- Tạo thêm giao dịch fraud.
- Đảm bảo xác suất đã được calibration tốt.
- Đảm bảo precision hoặc recall đạt mục tiêu.
- Thay thế việc chọn threshold.

Vì vậy quy trình hợp lý là: dùng class weight nếu validation chứng minh có lợi,
sau đó vẫn chọn threshold và đánh giá calibration riêng.

### 21.4. Ranking, calibration và decision

Ba khả năng này liên quan nhưng không giống nhau:

| Khả năng | Câu hỏi | Metric/công cụ ví dụ |
|---|---|---|
| Ranking | Fraud có thường được xếp trên non-fraud? | AP/PR AUC, ROC AUC |
| Calibration | Score 0.8 có gần 80% fraud không? | Brier score, calibration curve |
| Decision | Với nguồn lực hiện có, cảnh báo dòng nào? | Precision, recall, alert rate, chi phí |

Một model có ranking tốt vẫn có thể có probability chưa calibration. Một model
có probability tốt vẫn cần threshold phù hợp với năng lực xử lý alert.

---

## 22. Đọc Phase 4 của dự án bằng tư duy ML

Tài liệu `docs/mart_to_training/04_TRAIN_AND_EVALUATE.md` mô tả một thiết kế dự
kiến cho Phase 4. Khi đọc, nên nối mỗi đoạn code với invariant ML mà nó bảo vệ:

| Thành phần | Ý nghĩa ML/kỹ thuật |
|---|---|
| `feature_groups` | Chọn đúng phép biến đổi cho category và numeric |
| `normalize_feature_types` | Ép schema trước inference, tránh train/serve skew |
| `ColumnTransformer` | Mỗi nhóm cột đi qua đúng preprocessing |
| `Pipeline` | Preprocessing và estimator được fit/lưu như một đơn vị |
| `train_and_select_threshold` | Fit trên train, chọn threshold trên validation |
| `binary_metrics` | Báo cả ranking, quyết định và số lỗi |
| `model_bundle.joblib` | Gói pipeline, threshold, config và lineage |
| `evaluate_test_split` | Chỉ evaluate test với bundle đã khóa |
| Manifest SHA/fingerprint | Ngăn model bị đánh giá trên nhầm snapshot/population |

### 22.1. Chính sách feature của baseline

Baseline hiện dùng:

```text
transaction_type
amount
origin_balance_before
destination_balance_before
```

`is_fraud` là target nên tuyệt đối không nằm trong `X`. `event_time`/`step` có
vai trò chia và audit; nếu đưa chúng vào model, model có thể học vị trí thời
gian của dữ liệu thay vì quy luật fraud tổng quát. ID như `event_id` hoặc
`source` cũng không nên tự động trở thành feature.

Challenger có after-balance/delta/residual chỉ hợp lệ ở prediction point
`post_ledger_update`. Nếu muốn chặn giao dịch **trước** khi ghi sổ, các feature
chỉ xuất hiện sau ghi sổ là temporal leakage dù chúng làm metric đẹp hơn.

### 22.2. Vì sao `OneHotEncoder(handle_unknown="ignore")` quan trọng?

Giả sử train chỉ thấy `PAYMENT`, `TRANSFER`, nhưng production nhận `DEBIT`:

```python
unseen = pd.DataFrame(
    {
        "transaction_type": ["DEBIT"],
        "amount": [100.0],
        "origin_balance_before": [900.0],
        "destination_balance_before": [200.0],
    }
)

# Không lỗi; category chưa biết được mã hóa thành các số 0 ở block one-hot.
probability = pipeline.predict_proba(unseen)[:, 1]
```

Không crash không có nghĩa dự đoán chắc chắn tốt. Tỷ lệ category lạ cần được
monitor vì tăng mạnh có thể báo hiệu data drift hoặc schema upstream thay đổi.

### 22.3. Đọc confusion matrix theo nghiệp vụ fraud

Với `confusion_matrix(..., labels=[0, 1])`, thứ tự là:

```text
[[TN, FP],
 [FN, TP]]
```

- `FP`: giao dịch hợp lệ bị cảnh báo; làm tăng tải điều tra và gây phiền khách.
- `FN`: fraud bị bỏ lọt; gây tổn thất trực tiếp hoặc rủi ro tuân thủ.
- Precision cao: trong các alert, tỷ lệ fraud cao.
- Recall cao: trong toàn bộ fraud, bắt được nhiều.
- `alert_rate = (TP + FP) / N`: khối lượng alert đội vận hành phải xử lý.
- `fraud_capture_rate = TP / (TP + FN)`: chính là recall với lớp fraud.

Ví dụ quy đổi metric thành năng lực vận hành:

```python
def operational_summary(
    *,
    total_transactions: int,
    alert_rate: float,
    precision: float,
    review_capacity: int,
) -> dict[str, float | int | bool]:
    expected_alerts = round(total_transactions * alert_rate)
    expected_true_fraud_alerts = round(expected_alerts * precision)
    return {
        "expected_alerts": expected_alerts,
        "expected_true_fraud_alerts": expected_true_fraud_alerts,
        "within_review_capacity": expected_alerts <= review_capacity,
    }
```

Metric kỹ thuật chỉ hữu ích khi đặt cạnh volume, capacity và chi phí lỗi.

### 22.4. Vì sao không chọn lại threshold trên test?

Nếu thử nhiều threshold trên test rồi giữ threshold đẹp nhất, ta đã dùng nhãn
test để ra quyết định. Kết quả test sau đó lạc quan và không còn đại diện cho dữ
liệu chưa thấy. Invariant đúng của dự án là:

```text
train.fit → validation.select_threshold → lock bundle → test.evaluate once
```

Khi không có threshold nào đạt `min_precision`, fallback max-F1 phải được ghi
rõ. Nếu không ghi `strategy_result`, người đọc có thể hiểu nhầm rằng constraint
precision đã được đáp ứng.

### 22.5. Baseline ngẫu nhiên của Average Precision

Với ranking ngẫu nhiên, Average Precision thường ở quanh tỷ lệ positive. Nếu
fraud rate là `0.1%`, AP `1%` cao gấp khoảng 10 lần baseline ngẫu nhiên, dù con
số tuyệt đối trông nhỏ. Luôn báo fraud prevalence bên cạnh AP:

```python
fraud_prevalence = float(y_test.mean())
average_precision = average_precision_score(y_test, test_probability)

print("Fraud prevalence:", fraud_prevalence)
print("Average precision:", average_precision)
print("Lift over random:", average_precision / fraud_prevalence)
```

Không dùng phép chia trên nếu test không có fraud; đó cũng là dấu hiệu split
không đủ dữ liệu để đánh giá metric này.

---

## 23. Cách debug scikit-learn cho người mới

Khi có lỗi, đừng thay tham số ngẫu nhiên. Kiểm tra theo thứ tự: shape → tên cột
→ dtype → missing/infinity → phân bố target → trạng thái fit.

### 23.1. Bộ kiểm tra đầu vào tối thiểu

```python
import numpy as np
from sklearn.utils.multiclass import type_of_target

print("X shape:", X_train.shape)
print("y shape:", y_train.shape)
print("Target type:", type_of_target(y_train))
print("Target counts:\n", y_train.value_counts(dropna=False))
print("Dtypes:\n", X_train.dtypes)
print("Missing:\n", X_train.isna().sum())

assert X_train.shape[0] == y_train.shape[0]
assert X_train.columns.tolist() == FEATURES
assert set(y_train.unique()).issubset({0, 1})

numeric = X_train.select_dtypes(include="number")
assert np.isfinite(numeric.to_numpy()).all()
```

`SimpleImputer` xử lý `NaN`, nhưng không nên mặc định coi `inf`/`-inf` là
missing. Hãy tìm nguyên nhân tạo infinity, thường là phép chia cho 0.

### 23.2. Các lỗi/cảnh báo thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra/sửa |
|---|---|---|
| `Found input variables with inconsistent numbers of samples` | `X` và `y` lệch hàng/index | In shape và tạo chúng từ cùng frame/split |
| `could not convert string to float` | Chuỗi đi thẳng vào estimator | Đưa category qua `OneHotEncoder` |
| `Input X contains NaN` | Estimator nhận missing chưa impute | Đặt `SimpleImputer` trong pipeline |
| `NotFittedError` | Gọi predict/transform trước fit | Fit pipeline đúng một lần trên train |
| `unknown categories` | Encoder gặp category mới | Dùng `handle_unknown="ignore"` và monitor drift |
| `ConvergenceWarning` | Tối ưu chưa hội tụ | Scale, kiểm tra dữ liệu, tăng `max_iter`; không chỉ tắt warning |
| Số feature không khớp | Sai/thiếu/thừa/thứ tự cột | Truyền DataFrame theo feature contract |
| Điểm CV rất cao bất thường | Leakage, duplicate, group/time split sai | Audit feature và splitter trước khi tin metric |

Không nên dùng `warnings.filterwarnings("ignore")` để che
`ConvergenceWarning`. Warning là triệu chứng; cần kiểm tra scaling, dữ liệu,
solver và `max_iter`.

### 23.3. Kiểm tra pipeline đã học gì

```python
from sklearn.utils.validation import check_is_fitted

check_is_fitted(pipeline)

print(pipeline.named_steps.keys())
print(pipeline.named_steps["estimator"].classes_)
print(
    pipeline.named_steps["preprocessing"]
    .named_transformers_["categorical"]
    .named_steps["one_hot"]
    .categories_
)
```

Quy ước dấu `_` cuối tên như `classes_`, `categories_`, `coef_` cho biết đây là
trạng thái được tạo ra sau `fit`.

### 23.4. Test nhỏ để bắt lỗi leakage và category mới

```python
def test_pipeline_handles_unseen_category(pipeline, X_train, y_train):
    fitted = pipeline.fit(X_train, y_train)
    example = X_train.iloc[[0]].copy()
    example.loc[:, "transaction_type"] = "UNSEEN_TYPE"

    probability = fitted.predict_proba(example)[:, 1]

    assert probability.shape == (1,)
    assert 0.0 <= probability[0] <= 1.0


def test_target_is_not_a_feature(X_train):
    forbidden = {"is_fraud", "event_time", "step", "event_id", "source"}
    assert forbidden.isdisjoint(X_train.columns)
```

Test này không chứng minh model tốt, nhưng bảo vệ hai contract quan trọng:
inference không crash vì category mới và feature đầu vào không chứa cột cấm.

### 23.5. Bài tập nên tự làm

1. Chạy ví dụ ở mục 20 và in `feature_names`, `coef_`, `intercept_`.
2. Đổi một category trong validation thành `DEBIT`; giải thích vector one-hot.
3. So sánh probability và prediction tại threshold `0.2`, `0.5`, `0.8`.
4. Viết bảng `threshold`, `precision`, `recall`, `alert_rate` cho nhiều threshold.
5. Bỏ `StandardScaler`, so sánh số vòng lặp `n_iter_` và metric; không kết luận
   từ dataset 15 dòng.
6. So sánh `class_weight=None` và `"balanced"` trên validation.
7. Cố tình đưa `is_fraud` vào feature để thấy metric bất thường, rồi giải thích
   tại sao đó là target leakage.
8. Viết test bảo đảm mọi thời điểm train nhỏ hơn mọi thời điểm validation và
   mọi thời điểm validation nhỏ hơn mọi thời điểm test.

Khi làm bài tập, ghi lại giả thuyết trước khi chạy và giải thích sau khi chạy.
Thói quen này quan trọng hơn việc thử thật nhiều estimator.

---

## 24. Tài liệu chính thức

- [Getting Started](https://scikit-learn.org/stable/getting_started.html)
- [User Guide](https://scikit-learn.org/stable/user_guide.html)
- [Model selection and evaluation](https://scikit-learn.org/stable/model_selection.html)
- [Common pitfalls and recommended practices](https://scikit-learn.org/stable/common_pitfalls.html)
- [Choosing the right estimator](https://scikit-learn.org/stable/machine_learning_map.html)
- [API reference](https://scikit-learn.org/stable/api/index.html)
- [Model persistence](https://scikit-learn.org/stable/model_persistence.html)
- [Inspection](https://scikit-learn.org/stable/inspection.html)

---

## Tóm tắt 10 điều phải nhớ

1. Chia test trước khi tiền xử lý.
2. Không bao giờ `fit` trên test.
3. Dùng `Pipeline` và `ColumnTransformer`.
4. Chọn splitter theo cấu trúc dữ liệu.
5. Luôn so sánh với baseline.
6. Chọn metric theo bài toán, không mặc định dùng accuracy.
7. Tuning chỉ trên train bằng cross-validation.
8. Chọn threshold trên validation, không phải test.
9. Lưu toàn bộ pipeline và phiên bản môi trường.
10. Đánh giá lỗi, độ ổn định và rủi ro—không chỉ nhìn một con số.
