# Temporal EDA — các cell để chèn vào `EDA.ipynb`

Mục tiêu của phần này là tách rõ ba đại lượng:

- `fraud_count`: số giao dịch gian lận;
- `row_count` / volume: tổng số giao dịch;
- `fraud_per_10k`: fraud rate đã chuẩn hoá theo volume.

`step` của PaySim là **simulation hour**. Vì vậy phân tích dưới đây chỉ mô tả nhịp trong dữ liệu mô phỏng, không chứng minh hành vi ngày/đêm của người dùng hoặc kẻ gian trong ngân hàng thật.

> Lưu ý: một giá trị gần 340 ở bảng `hour_of_day_summary` nghĩa là tổng số fraud của cùng một giờ trong ngày qua nhiều ngày mô phỏng. Nó không có nghĩa là một simulation step có 340 fraud. Cột `avg_fraud_per_step` mới là số fraud trung bình của một simulation hour.

## 1. Bổ sung tổng hợp chính xác theo từng `step`

Phần này phải được thêm vào cell scan dữ liệu lớn (cell hiện tạo `step_day_parts`). Nhờ đó toàn bộ temporal EDA dùng **toàn bộ 6,362,620 dòng**, không dùng `natural_sample`.

### 1a. Thêm trước vòng lặp `for chunk_number, chunk in enumerate(...)`

Đặt ngay dưới dòng hiện có:

```python
step_day_parts: list[pd.DataFrame] = []
```

Code cần thêm:

```python
step_parts: list[pd.DataFrame] = []
```

### 1b. Thêm trong vòng lặp, ngay sau block `step_day_parts.append(...)`

`chunk["_fraud_amount"]` đã được tạo trước vị trí này, nên block dưới đây dùng được trực tiếp.

```python
step_parts.append(
    chunk.groupby("step", dropna=False).agg(
        row_count=("isFraud", "size"),
        fraud_count=("isFraud", "sum"),
        flagged_fraud_count=("isFlaggedFraud", "sum"),
        amount_sum=("amount", "sum"),
        fraud_amount_sum=("_fraud_amount", "sum"),
    )
)
```

### 1c. Thêm sau khi tạo `step_summary`

Đặt sau block kết thúc bằng:

```python
display(step_summary)
```

```python
hourly_summary = (
    combine_group_summaries(step_parts, "step")
    .reset_index()
    .sort_values("step")
    .reset_index(drop=True)
)

hourly_summary["fraud_rate"] = (
    hourly_summary["fraud_count"] / hourly_summary["row_count"]
)
hourly_summary["fraud_per_10k"] = hourly_summary["fraud_rate"] * 10_000
hourly_summary["step_day"] = (
    (hourly_summary["step"] - 1) // STEP_BUCKET_WIDTH + 1
).astype("int16")
hourly_summary["hour_of_day"] = (
    (hourly_summary["step"] - 1) % STEP_BUCKET_WIDTH
).astype("int8")
hourly_summary["period"] = np.where(
    hourly_summary["hour_of_day"].between(6, 21),
    "Ban ngày",
    "Ban đêm",
)

# Ngày 31 chỉ có 23 simulation hours và toàn bộ là fraud.
# Giữ lại để nhìn thấy artifact, nhưng loại khỏi phép so sánh day/night chính.
last_step_day = hourly_summary["step_day"].max()
hourly_summary["is_partial_day"] = hourly_summary["step_day"].eq(last_step_day)

assert hourly_summary["row_count"].sum() == total_rows
assert hourly_summary["fraud_count"].sum() == full_fraud_count

display(hourly_summary.head())
```

Đồng thời thêm hai dòng này vào khu vực export CSV ở cuối cell scan:

```python
hourly_summary.to_csv(REPORT_DIR / "hourly_summary.csv", index=False)
```

## 2. Bảng kiểm tra trước khi vẽ

Chèn cell mới sau phần data-quality hoặc ngay trước phần visualisation.

```python
hourly_summary[
    ["row_count", "fraud_count", "fraud_per_10k"]
].describe(percentiles=[0.05, 0.50, 0.95]).T
```

Mục tiêu của bảng này là kiểm tra xem fraud count và volume có biến thiên độc lập hay không. Không viết kết luận “fraud tăng” chỉ từ fraud rate.

## 3. Diễn biến theo từng simulation step

Chèn cell mới. Ba panel dùng cùng trục X, nhưng tách ba thang đo khác nhau để không dùng dual axis.

```python
partial_steps = hourly_summary.loc[
    hourly_summary["is_partial_day"],
    "step",
]
partial_start = partial_steps.min() - 0.5
partial_end = partial_steps.max() + 0.5

fig, axes = plt.subplots(
    nrows=3,
    ncols=1,
    figsize=(16, 12),
    sharex=True,
    constrained_layout=True,
)

axes[0].plot(
    hourly_summary["step"],
    hourly_summary["fraud_count"],
    color=ORANGE,
    linewidth=1.4,
)
axes[0].set_title("Fraud count theo simulation step")
axes[0].set_ylabel("Số fraud")

axes[1].plot(
    hourly_summary["step"],
    hourly_summary["row_count"],
    color=BLUE,
    linewidth=1.4,
)
axes[1].set_title("Volume giao dịch theo simulation step")
axes[1].set_ylabel("Số giao dịch")
axes[1].set_yscale("log")

axes[2].plot(
    hourly_summary["step"],
    hourly_summary["fraud_per_10k"],
    color=INK,
    linewidth=1.4,
)
axes[2].set_title("Fraud rate theo simulation step")
axes[2].set_xlabel("Simulation step (mỗi step = 1 giờ mô phỏng)")
axes[2].set_ylabel("Fraud / 10.000 giao dịch")

for ax in axes:
    ax.axvspan(
        partial_start,
        partial_end,
        color=LIGHT_ORANGE,
        alpha=0.25,
        label="Ngày 31 không đầy đủ",
    )
    ax.grid(axis="x", alpha=0.35)
    ax.legend(loc="upper left")

sns.despine()
plt.show()
```

Panel volume dùng thang log vì số giao dịch chênh lệch rất lớn; tiêu đề và trục Y đã nêu rõ điều này. Không dùng scale log cho fraud count hoặc fraud rate.

## 4. Tổng hợp theo giờ trong ngày

Chèn cell mới. Phần này trả lời câu hỏi “các giờ trong ngày mô phỏng có khác nhau không?”. Ngày 31 được loại khỏi bảng này vì không đủ 24 giờ.

```python
complete_hourly_summary = hourly_summary.loc[
    ~hourly_summary["is_partial_day"]
].copy()

hour_of_day_summary = (
    complete_hourly_summary
    .groupby("hour_of_day", as_index=False)
    .agg(
        observed_step_count=("step", "size"),
        transaction_count=("row_count", "sum"),
        fraud_count=("fraud_count", "sum"),
    )
)
hour_of_day_summary["fraud_rate"] = (
    hour_of_day_summary["fraud_count"]
    / hour_of_day_summary["transaction_count"]
)
hour_of_day_summary["fraud_per_10k"] = (
    hour_of_day_summary["fraud_rate"] * 10_000
)
hour_of_day_summary["avg_fraud_per_step"] = (
    hour_of_day_summary["fraud_count"]
    / hour_of_day_summary["observed_step_count"]
)
hour_of_day_summary["period"] = np.where(
    hour_of_day_summary["hour_of_day"].between(6, 21),
    "Ban ngày",
    "Ban đêm",
)

display(hour_of_day_summary)
```

```python
fig, axes = plt.subplots(
    nrows=3,
    ncols=1,
    figsize=(15, 12),
    sharex=True,
    constrained_layout=True,
)

axes[0].plot(
    hour_of_day_summary["hour_of_day"],
    hour_of_day_summary["avg_fraud_per_step"],
    marker="o",
    color=ORANGE,
)
axes[0].set_title("Fraud trung bình trên mỗi simulation step theo giờ trong ngày")
axes[0].set_ylabel("Fraud trung bình / step")

axes[1].plot(
    hour_of_day_summary["hour_of_day"],
    hour_of_day_summary["transaction_count"],
    marker="o",
    color=BLUE,
)
axes[1].set_title("Tổng volume theo giờ trong ngày qua các ngày hoàn chỉnh")
axes[1].set_ylabel("Tổng số giao dịch")
axes[1].set_yscale("log")

axes[2].plot(
    hour_of_day_summary["hour_of_day"],
    hour_of_day_summary["fraud_per_10k"],
    marker="o",
    color=INK,
)
axes[2].set_title("Fraud rate theo giờ trong ngày")
axes[2].set_xlabel("Giờ trong ngày mô phỏng")
axes[2].set_ylabel("Fraud / 10.000 giao dịch")

for ax in axes:
    ax.axvspan(5.5, 21.5, color=LIGHT_BLUE, alpha=0.25, label="Ban ngày (06:00–21:59)")
    ax.set_xticks(range(24))
    ax.grid(axis="x", alpha=0.35)
    ax.legend(loc="upper left")

sns.despine()
plt.show()
```

## 5. Heatmap day × hour

Chèn cell mới. Ba heatmap phải được đọc cùng nhau: fraud count, volume và fraud rate. Ô xám ở cuối ngày 31 là giờ không có trong dữ liệu, không phải zero.

```python
from matplotlib.colors import LogNorm

heatmap_days = pd.Index(
    range(1, int(hourly_summary["step_day"].max()) + 1),
    name="step_day",
)
heatmap_hours = pd.Index(range(24), name="hour_of_day")

def make_temporal_matrix(value_column: str) -> pd.DataFrame:
    return (
        hourly_summary
        .pivot(
            index="step_day",
            columns="hour_of_day",
            values=value_column,
        )
        .reindex(index=heatmap_days, columns=heatmap_hours)
    )

fraud_count_matrix = make_temporal_matrix("fraud_count")
volume_matrix = make_temporal_matrix("row_count")
fraud_rate_matrix = make_temporal_matrix("fraud_per_10k")

fig, axes = plt.subplots(
    nrows=1,
    ncols=3,
    figsize=(24, 10),
    constrained_layout=True,
)

for ax in axes:
    ax.set_facecolor("#ECEFF1")

sns.heatmap(
    fraud_count_matrix,
    cmap=sns.light_palette(ORANGE, as_cmap=True),
    linewidths=0.15,
    linecolor="white",
    cbar_kws={"label": "Số fraud"},
    ax=axes[0],
)
axes[0].set_title("Fraud count: day × hour")

sns.heatmap(
    volume_matrix,sswwww
    cmap=sns.light_palette(BLUE, as_cmap=True),
    norm=LogNorm(
        vmin=volume_matrix.stack().min(),
        vmax=volume_matrix.stack().max(),
    ),
    linewidths=0.15,
    linecolor="white",
    cbar_kws={"label": "Số giao dịch (thang log)"},
    ax=axes[1],
)
axes[1].set_title("Volume: day × hour")

sns.heatmap(
    fraud_rate_matrix,
    cmap=sns.light_palette(INK, as_cmap=True),
    vmin=0,
    vmax=fraud_rate_matrix.stack().max(),
    linewidths=0.15,
    linecolor="white",
    cbar_kws={"label": "Fraud / 10.000 giao dịch"},
    ax=axes[2],
)
axes[2].set_title("Fraud rate: day × hour")

for ax in axes:
    ax.set_xlabel("Giờ trong ngày mô phỏng")
    ax.set_ylabel("Simulation day")
    ax.tick_params(axis="x", rotation=0)

plt.show()
```

Không kết luận một ô fraud rate đậm màu là “fraud tăng” trước khi đối chiếu đúng ô đó ở hai heatmap còn lại.

## 6. So sánh ban ngày và ban đêm

Chèn cell mới. Đây là bảng aggregate; không suy diễn hành vi ngoài dữ liệu PaySim.

```python
day_night_summary = (
    complete_hourly_summary
    .groupby("period", as_index=False)
    .agg(
        transaction_count=("row_count", "sum"),
        fraud_count=("fraud_count", "sum"),
    )
    .assign(
        fraud_rate=lambda frame: (
            frame["fraud_count"] / frame["transaction_count"]
        ),
        fraud_per_10k=lambda frame: frame["fraud_rate"] * 10_000,
    )
)

day_night_summary["period"] = pd.Categorical(
    day_night_summary["period"],
    categories=["Ban ngày", "Ban đêm"],
    ordered=True,
)
day_night_summary = day_night_summary.sort_values("period")

display(day_night_summary)
day_night_summary.to_csv(REPORT_DIR / "day_night_summary.csv", index=False)
```

```python
metrics_to_plot = [
    ("transaction_count", "Tổng volume", "Số giao dịch"),
    ("fraud_count", "Tổng fraud count", "Số fraud"),
    ("fraud_per_10k", "Fraud rate", "Fraud / 10.000 giao dịch"),
]
period_colors = {
    "Ban ngày": BLUE,
    "Ban đêm": ORANGE,
}

fig, axes = plt.subplots(
    nrows=1,
    ncols=3,
    figsize=(18, 5),
    constrained_layout=True,
)

for ax, (metric, title, ylabel) in zip(axes, metrics_to_plot, strict=True):
    bars = ax.bar(
        day_night_summary["period"].astype(str),
        day_night_summary[metric],
        color=[period_colors[period] for period in day_night_summary["period"]],
        edgecolor=INK,
        linewidth=0.7,
    )
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.bar_label(bars, fmt="%.1f", padding=3)
    ax.grid(axis="x", visible=False)

axes[0].yaxis.set_major_formatter(
    plt.FuncFormatter(lambda value, _: f"{value:,.0f}")
)
axes[1].yaxis.set_major_formatter(
    plt.FuncFormatter(lambda value, _: f"{value:,.0f}")
)

sns.despine()
plt.show()
```

## 7. Cách viết kết luận sau khi có output

Chỉ dùng các câu thuộc một trong hai dạng sau:

```text
Fraud count theo simulation step [ổn định/dao động] trong khi volume [ổn định/dao động].
Do đó, các spike fraud rate ở [window] chủ yếu đi cùng [volume giảm / fraud count tăng / cả hai].
```

```text
Trong dữ liệu PaySim, giờ mô phỏng [X] có fraud rate cao hơn,
nhưng kết luận này cần được đọc cùng volume và fraud count; đây không phải bằng chứng về hành vi ngày/đêm của người thật.
```

Không viết “kẻ gian không nghỉ ngơi” hoặc “fraud luôn cố định theo giờ” nếu chưa kiểm tra các bảng và biểu đồ trên.
