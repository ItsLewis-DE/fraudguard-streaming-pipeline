# Phân phối đơn biến và tương quan của các feature số dư

Các cell dưới đây được chèn **sau cell zero-rate heatmap** trong `EDA.ipynb`.
Chúng tái sử dụng các biến đã có trong notebook: `eda_plot_sample`,
`diagnostic_sample`, `VALUE_COLUMNS`, các màu `BLUE`/`ORANGE`/`INK` và
`REPORT_DIR`.

`eda_plot_sample` gồm toàn bộ fraud và non-fraud từ `natural_sample`, đồng thời
đã loại `step_day == 31`; dùng nó cho đồ thị phân phối để tránh hàng dữ liệu
không đầy đủ. `diagnostic_sample` được oversample fraud và stratify non-fraud
theo `(type, step_day)`; chỉ dùng nó để nhìn cấu trúc giữa các feature, **không
dùng tỷ lệ fraud hoặc hệ số với target trong mẫu này làm ước lượng cho toàn bộ
dân số**.

Các residual được định nghĩa đúng như mart
`ml_training_candidates` hiện tại:

- `origin_amount_residual = abs((oldbalanceOrg - newbalanceOrig) - amount)`;
- `destination_amount_residual = abs((newbalanceDest - oldbalanceDest) - amount)`.

Vì thế `origin_amount_residual` của `CASH_IN` không phải một residual kế toán
theo chiều tiền vào; không diễn giải giá trị lớn của nó là lỗi dữ liệu nếu chưa
có quy ước residual riêng cho `CASH_IN`.

## 1. Chuẩn bị dữ liệu cho phần balance EDA

```python
# Chạy sau cell tạo eda_plot_sample và zero-rate heatmap.
# Không sửa eda_plot_sample tại chỗ để các cell trước vẫn reproducible.

BALANCE_COLUMNS = [
    "oldbalanceOrg",
    "newbalanceOrig",
    "oldbalanceDest",
    "newbalanceDest",
]

BALANCE_FEATURE_COLUMNS = [
    "amount",
    *BALANCE_COLUMNS,
    "origin_amount_residual",
    "destination_amount_residual",
]

FRAUD_LABEL_ORDER = ["Không gian lận", "Gian lận"]
LABEL_PALETTE = {
    "Không gian lận": BLUE,
    "Gian lận": ORANGE,
}

balance_plot_sample = eda_plot_sample.loc[
    :,
    ["step", "type", "isFraud", "fraud_label", "amount", *BALANCE_COLUMNS],
].copy()

# Công thức khớp với dbt/models/marts/ml/ml_training_candidates.sql.
balance_plot_sample["origin_amount_residual"] = np.abs(
    (balance_plot_sample["oldbalanceOrg"] - balance_plot_sample["newbalanceOrig"])
    - balance_plot_sample["amount"]
)
balance_plot_sample["destination_amount_residual"] = np.abs(
    (balance_plot_sample["newbalanceDest"] - balance_plot_sample["oldbalanceDest"])
    - balance_plot_sample["amount"]
)

# Mẫu chẩn đoán giữ toàn bộ fraud và oversample non-fraud theo (type, step_day).
# Loại ngày 31 để nhất quán với các đồ thị EDA hiện tại.
balance_diagnostic_sample = diagnostic_sample.loc[
    diagnostic_sample["step_day"].ne(31),
    ["step", "type", "isFraud", "amount", *BALANCE_COLUMNS],
].copy()
balance_diagnostic_sample["origin_amount_residual"] = np.abs(
    (
        balance_diagnostic_sample["oldbalanceOrg"]
        - balance_diagnostic_sample["newbalanceOrig"]
    )
    - balance_diagnostic_sample["amount"]
)
balance_diagnostic_sample["destination_amount_residual"] = np.abs(
    (
        balance_diagnostic_sample["newbalanceDest"]
        - balance_diagnostic_sample["oldbalanceDest"]
    )
    - balance_diagnostic_sample["amount"]
)

assert balance_plot_sample[BALANCE_FEATURE_COLUMNS].ge(0).all().all()
assert balance_diagnostic_sample[BALANCE_FEATURE_COLUMNS].ge(0).all().all()

display(
    balance_plot_sample.groupby("fraud_label", observed=True)
    .size()
    .reindex(FRAUD_LABEL_ORDER)
    .rename("row_count")
    .to_frame()
)
```

## 2. Zero mass và ECDF log1p của số dư

Cell này vừa định lượng mass tại 0, vừa vẽ ECDF của `log1p(balance)`. Giá trị
0 được giữ lại (vẫn là 0 sau `log1p`), nên không bị che khuất bởi đuôi phải.

```python
zero_mass_by_label = (
    balance_plot_sample.groupby("fraud_label", observed=True)[BALANCE_COLUMNS]
    .agg(lambda series: series.eq(0).mean() * 100)
    .reindex(FRAUD_LABEL_ORDER)
    .T
)
zero_mass_by_label.index.name = "feature"
zero_mass_by_label.columns.name = "fraud_label"

display(zero_mass_by_label.style.format("{:.2f}%"))

balance_long = balance_plot_sample.melt(
    id_vars=["fraud_label"],
    value_vars=BALANCE_COLUMNS,
    var_name="feature",
    value_name="balance",
)
balance_long["log1p_balance"] = np.log1p(balance_long["balance"])

fig, axes = plt.subplots(
    nrows=2,
    ncols=2,
    figsize=(16, 10),
    sharey=True,
    constrained_layout=True,
)

for feature, ax in zip(BALANCE_COLUMNS, axes.flat, strict=True):
    feature_data = balance_long.loc[balance_long["feature"].eq(feature)]
    sns.ecdfplot(
        data=feature_data,
        x="log1p_balance",
        hue="fraud_label",
        hue_order=FRAUD_LABEL_ORDER,
        palette=LABEL_PALETTE,
        ax=ax,
    )
    ax.set_title(f"ECDF log1p({feature}) theo nhãn")
    ax.set_xlabel(f"log1p({feature})")
    ax.set_ylabel("Tỷ lệ tích luỹ")
    ax.grid(alpha=0.30)

sns.despine()
plt.show()
```

## 3. Histogram log của phần số dư dương

ECDF phía trên trả lời đầy đủ cả zero mass lẫn đuôi phải. Histogram này chỉ
nhìn phần `balance > 0`, để thấy hình dạng của các giá trị khác 0 thay vì để
mass tại 0 chi phối toàn bộ biểu đồ. Vì mỗi nhãn được chuẩn hoá độc lập,
histogram là so sánh *hình dạng*, không phải so sánh số giao dịch tuyệt đối.

```python
positive_balance_long = balance_long.loc[
    balance_long["balance"].gt(0)
].copy()

fig, axes = plt.subplots(
    nrows=2,
    ncols=2,
    figsize=(16, 10),
    constrained_layout=True,
)

for feature, ax in zip(BALANCE_COLUMNS, axes.flat, strict=True):
    feature_data = positive_balance_long.loc[
        positive_balance_long["feature"].eq(feature)
    ]
    sns.histplot(
        data=feature_data,
        x="log1p_balance",
        hue="fraud_label",
        hue_order=FRAUD_LABEL_ORDER,
        palette=LABEL_PALETTE,
        stat="density",
        common_norm=False,
        bins=60,
        element="step",
        fill=False,
        ax=ax,
    )
    ax.set_title(f"Phần {feature} > 0 theo nhãn")
    ax.set_xlabel(f"log1p({feature})")
    ax.set_ylabel("Mật độ trong từng nhãn")
    ax.grid(alpha=0.30)

sns.despine()
plt.show()
```

## 4. Ma trận tương quan Pearson giữa feature số

Với biến liên tục, ma trận Pearson trên `balance_diagnostic_sample` thuận tiện
để nhận ra các cặp gần trùng lặp như `oldbalanceOrg` và `newbalanceOrig`.
Đây không phải lý do tự động xoá feature cho tree model; nó là cảnh báo đa cộng
tuyến cho mô hình tuyến tính và gợi ý dùng delta/residual thay cho hai mức số
dư gần đồng nhất. Không đưa `isFraud` vào heatmap này để tách phần mô tả feature
với phần liên hệ target ở cell kế tiếp.

```python
correlation_feature_columns = [
    "step",
    "amount",
    *BALANCE_COLUMNS,
    "origin_amount_residual",
    "destination_amount_residual",
]

feature_correlation = balance_diagnostic_sample[
    correlation_feature_columns
].corr(method="pearson")

display(feature_correlation.round(4))

upper_triangle_mask = np.triu(
    np.ones(feature_correlation.shape, dtype=bool),
    k=1,
)

fig, ax = plt.subplots(figsize=(11, 9))
sns.heatmap(
    feature_correlation,
    mask=upper_triangle_mask,
    cmap="vlag",
    center=0,
    vmin=-1,
    vmax=1,
    annot=True,
    fmt=".2f",
    square=True,
    linewidths=0.5,
    linecolor="white",
    cbar_kws={"label": "Tương quan Pearson"},
    ax=ax,
)
ax.set_title("Tương quan feature số — diagnostic sample (oversampled)", pad=16)
ax.tick_params(axis="x", rotation=35)
ax.tick_params(axis="y", rotation=0)
plt.show()

feature_correlation.to_csv(REPORT_DIR / "balance_feature_correlation_diagnostic.csv")
```

## 5. Point-biserial correlation với target

Với target nhị phân `isFraud`, Pearson correlation giữa feature số và target
0/1 chính là point-biserial correlation. Dấu âm của residual cho biết residual
nhỏ hơn có liên hệ với fraud nhiều hơn; nó không có nghĩa residual âm vì các
residual ở đây đều là trị tuyệt đối.

Do fraud bị oversample có chủ đích, hệ số dưới đây chỉ dùng để xếp hạng tín hiệu
trong sample chẩn đoán. Không báo p-value: mẫu không phải random population
sample và kích thước lớn khiến p-value gần như luôn nhỏ dù effect size nhỏ.

```python
def point_biserial_with_target(
    frame: pd.DataFrame,
    feature_columns: list[str],
    target_column: str = "isFraud",
) -> pd.DataFrame:
    rows: list[dict[str, float | str]] = []

    for feature in feature_columns:
        valid = frame[[feature, target_column]].dropna()
        feature_values = valid[feature].to_numpy(dtype="float64")
        target_values = valid[target_column].to_numpy(dtype="float64")

        correlation = np.nan
        if np.std(feature_values) > 0 and np.std(target_values) > 0:
            correlation = float(np.corrcoef(feature_values, target_values)[0, 1])

        rows.append(
            {
                "feature": feature,
                "point_biserial_r": correlation,
                "abs_r": abs(correlation) if pd.notna(correlation) else np.nan,
                "n": len(valid),
            }
        )

    return (
        pd.DataFrame(rows)
        .sort_values("abs_r", ascending=False)
        .drop(columns="abs_r")
        .reset_index(drop=True)
    )

target_correlation_columns = [
    "step",
    "amount",
    *BALANCE_COLUMNS,
    "origin_amount_residual",
    "destination_amount_residual",
]

target_point_biserial = point_biserial_with_target(
    balance_diagnostic_sample,
    target_correlation_columns,
)
display(target_point_biserial.style.format({"point_biserial_r": "{:.4f}"}))

target_point_biserial.to_csv(
    REPORT_DIR / "numeric_target_point_biserial_diagnostic.csv",
    index=False,
)
```

## 6. Chi-square và Cramér's V cho `type × isFraud`

Không thêm SciPy vào environment hiện tại: cell tự tính chi-square statistic và
Cramér's V từ bảng chéo. Với bảng 5 × 2, Cramér's V nằm trong [0, 1] và thích
hợp hơn p-value để mô tả cường độ liên hệ. Các tổ hợp có expected count bằng 0
được loại khỏi phép chia phòng thủ, dù dữ liệu hiện tại không kỳ vọng trường hợp
đó.

```python
def chi_square_and_cramers_v(
    contingency: pd.DataFrame,
) -> tuple[float, float, int, int]:
    observed = contingency.to_numpy(dtype="float64")
    n = observed.sum()

    if n == 0 or observed.shape[0] < 2 or observed.shape[1] < 2:
        return np.nan, np.nan, 0, 0

    expected = np.outer(observed.sum(axis=1), observed.sum(axis=0)) / n
    valid_expected = expected > 0
    chi_square = float(
        np.sum(((observed - expected) ** 2)[valid_expected] / expected[valid_expected])
    )
    degrees_of_freedom = (observed.shape[0] - 1) * (observed.shape[1] - 1)
    min_dimension = min(observed.shape[0] - 1, observed.shape[1] - 1)
    cramers_v = float(np.sqrt(chi_square / (n * min_dimension)))

    return chi_square, cramers_v, int(n), int(degrees_of_freedom)

type_target_contingency = pd.crosstab(
    balance_diagnostic_sample["type"],
    balance_diagnostic_sample["isFraud"],
).reindex(index=sorted(VALID_TYPES), columns=[0, 1], fill_value=0)
type_target_contingency.columns = ["Không gian lận", "Gian lận"]
type_target_contingency.index.name = "type"

chi_square, cramers_v, n, dof = chi_square_and_cramers_v(type_target_contingency)

display(type_target_contingency)
display(
    pd.DataFrame(
        {
            "metric": ["chi_square", "degrees_of_freedom", "n", "cramers_v"],
            "value": [chi_square, dof, n, cramers_v],
            "scope": ["diagnostic_sample, step_day != 31"] * 4,
        }
    )
)

type_target_contingency.to_csv(
    REPORT_DIR / "type_target_contingency_diagnostic.csv"
)
```

## Cách ghi kết luận sau khi chạy

- Nêu zero mass trước, sau đó mới so sánh phần dương của các balance; tránh nói
  “phân phối giống nhau” chỉ vì histogram bị một cột 0 che phủ.
- Nếu `oldbalanceOrg ↔ newbalanceOrig` gần 1, ghi đó là đa cộng tuyến của mức
  số dư. Với logistic regression, thử giữ một mức hoặc thay bằng delta/residual;
  với tree model, dùng ablation trên temporal validation để quyết định.
- Nêu rõ point-biserial và Cramér's V là **diagnostic associations trong mẫu
  oversampled**. Chúng không chứng minh causal effect, cũng không là lý do đủ để
  đưa feature vào production.
- Nếu residual có association mạnh, đối chiếu với temporal split và model card:
  đó có thể là shortcut do PaySim mô phỏng số dư nhất quán hơn ở fraud, không
  đồng nghĩa nó sẽ tồn tại trong ledger của ngân hàng thực.
