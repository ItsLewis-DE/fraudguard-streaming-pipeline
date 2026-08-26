# Phase 5 — Xây dựng notebook so sánh bốn model candidate

Tài liệu này hướng dẫn tạo notebook:

```text
notebooks/model_experiments.ipynb
```

Notebook không huấn luyện lại model. Nó đọc các artifact đã được Phase 4 tạo ra,
kiểm tra tính nhất quán, trực quan hóa validation result và đề xuất candidate để
chuyển sang Phase 6. Bốn file JSON là nguồn chính cho bảng metric và các biểu đồ
metric tổng hợp.

## 1. Phạm vi và giả định

Tài liệu giả định Phase 1–4 đã hoàn thành và mỗi candidate có đủ ba artifact:

```text
airflow_ml_artifacts/model_experiments/<RUN_ID>/
├── candidates/
│   ├── A/
│   │   ├── experiment/dataset_manifest.json
│   │   ├── experiment/data.parquet
│   │   └── model/
│   │       ├── validation_metrics.json
│   │       └── model_bundle.joblib
│   ├── B/...
│   ├── C/...
│   └── D/...
└── comparison/
```

Candidate matrix:

| ID | Model | Feature set |
| --- | --- | --- |
| A | Logistic Regression | Baseline |
| B | XGBoost | Baseline |
| C | Logistic Regression | Balance |
| D | XGBoost | Balance |

Notebook chỉ sử dụng validation split. Không đọc hoặc đánh giá test prediction
trong Phase 5.

> **Phân biệt quan trọng:** bốn file `validation_metrics.json` đủ để tạo bảng và
> biểu đồ scalar metric như PR-AUC, precision, recall, alert rate và training
> time. Một Precision–Recall curve đầy đủ cần toàn bộ `y_true` và probability ở
> nhiều threshold; feature importance và coefficient cũng không nằm trong bốn
> JSON. Vì vậy notebook chỉ load thêm snapshot và model bundle cho ba phần này.
> Notebook vẫn không fit hay điều chỉnh model.

## 2. Output cần tạo

Sau khi notebook chạy hết, thư mục sau phải tồn tại:

```text
reports/model_experiments/<RUN_ID>/
├── model_comparison.csv
├── model_selection.json
├── validation_metric_overview.png
├── validation_threshold_metrics.png
├── validation_pr_curve.png
├── feature_importance.png
├── logistic_coefficients.png
└── training_seconds.png
```

Đặt output dưới `<RUN_ID>` giúp một lần chạy notebook không ghi đè báo cáo của
experiment khác.

## 3. Chuẩn bị môi trường

Chạy từ repository root:

```bash
uv sync --dev
uv run python -m ipykernel install --user \
  --name fraudguard \
  --display-name "Python (FraudGuard)"
```

Mở `notebooks/model_experiments.ipynb` và chọn kernel `Python (FraudGuard)`.
Nếu dùng VS Code, có thể tạo notebook trống rồi thêm các cell bên dưới theo đúng
thứ tự.

## 4. Cấu trúc notebook

Notebook nên có các phần sau:

1. Mục tiêu và giới hạn.
2. Khai báo run và candidate registry.
3. Load bốn JSON validation metrics.
4. Kiểm tra invariant và manifest.
5. Hiển thị thống kê train/validation/test.
6. Tạo bảng validation comparison.
7. Trực quan hóa scalar metrics.
8. Tái tạo validation PR curve từ artifact đã fit.
9. Hiển thị XGBoost feature importance.
10. Hiển thị Logistic Regression coefficient.
11. Áp dụng selection rule và ghi kết luận.
12. Kiểm tra output.

## 5. Code chi tiết từng notebook cell

### Cell 1 — Markdown: tiêu đề, mục tiêu và giới hạn

Tạo một Markdown cell:

```markdown
# FraudGuard — Validation Model Experiment

## Mục tiêu

So sánh công bằng bốn candidate Logistic Regression/XGBoost trên hai feature
set bằng cùng population, temporal split, threshold policy và random seed.

## Quy tắc

- Chỉ sử dụng validation để so sánh và chọn candidate.
- Không dùng test để chỉnh model, feature hoặc threshold.
- Precision tối thiểu là 10%.
- Ưu tiên recall, sau đó PR-AUC, sau đó alert rate.
- Model phức tạp hơn chỉ được chọn khi có cải thiện đủ rõ.

## Giới hạn

Dữ liệu hiện tại nhỏ và có rất ít fraud case. Kết quả chứng minh quy trình
experiment; không phải bằng chứng về hiệu năng production.
```

### Cell 2 — Import và cấu hình hiển thị

```python
from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from IPython.display import Markdown, display
from sklearn.metrics import average_precision_score, precision_recall_curve

from fraudguard_ml.dataset_loader import load_dataset_splits
from fraudguard_ml.dataset_manifest import load_manifest
from fraudguard_ml.experiment_config import ExperimentConfig

pd.set_option("display.max_columns", 50)
pd.set_option("display.float_format", lambda value: f"{value:,.4f}")

sns.set_theme(style="whitegrid", context="notebook")
plt.rcParams.update(
    {
        "figure.figsize": (10, 6),
        "figure.dpi": 120,
        "axes.titleweight": "bold",
        "axes.labelsize": 11,
    }
)

CANDIDATE_COLORS = {
    "A": "#4C78A8",
    "B": "#F58518",
    "C": "#54A24B",
    "D": "#E45756",
}
```

### Cell 3 — Tìm repository root

Cell này cho phép notebook chạy khi working directory là repository root hoặc
thư mục `notebooks/`.

```python
def find_repository_root(start: Path) -> Path:
    """Find the nearest parent containing pyproject.toml and the ML package."""

    for candidate in (start, *start.parents):
        if (
            (candidate / "pyproject.toml").is_file()
            and (candidate / "ml" / "src" / "fraudguard_ml").is_dir()
        ):
            return candidate
    raise FileNotFoundError(
        "Cannot find repository root. Start Jupyter inside ML_Fraud_Banking."
    )


REPOSITORY_ROOT = find_repository_root(Path.cwd().resolve())
REPOSITORY_ROOT
```

### Cell 4 — Khóa `RUN_ID` và khai báo candidate registry

Không tự động lấy “latest run” trong báo cáo cuối. Một báo cáo có thể tái lập
phải ghi rõ run nào đang được phân tích. Có thể truyền `RUN_ID` qua environment,
hoặc sửa giá trị mặc định trong cell.

```python
RUN_ID = os.getenv("FRAUDGUARD_EXPERIMENT_RUN_ID", "20260825T082223Z")

RUN_ROOT = (
    REPOSITORY_ROOT
    / "airflow_ml_artifacts"
    / "model_experiments"
    / RUN_ID
)
REPORT_ROOT = (
    REPOSITORY_ROOT
    / "reports"
    / "model_experiments"
    / RUN_ID
)
REPORT_ROOT.mkdir(parents=True, exist_ok=True)

CANDIDATES: dict[str, dict[str, str]] = {
    "A": {
        "model": "logistic_regression",
        "model_label": "Logistic Regression",
        "feature_set": "baseline",
        "label": "A · Logistic · Baseline",
    },
    "B": {
        "model": "xgboost",
        "model_label": "XGBoost",
        "feature_set": "baseline",
        "label": "B · XGBoost · Baseline",
    },
    "C": {
        "model": "logistic_regression",
        "model_label": "Logistic Regression",
        "feature_set": "balance",
        "label": "C · Logistic · Balance",
    },
    "D": {
        "model": "xgboost",
        "model_label": "XGBoost",
        "feature_set": "balance",
        "label": "D · XGBoost · Balance",
    },
}

assert RUN_ROOT.is_dir(), f"Run directory does not exist: {RUN_ROOT}"
print(f"Analyzing RUN_ID={RUN_ID}")
print(f"Artifacts: {RUN_ROOT}")
print(f"Reports:   {REPORT_ROOT}")
```

Nếu phân tích run khác:

```bash
FRAUDGUARD_EXPERIMENT_RUN_ID=<RUN_ID> uv run jupyter notebook
```

### Cell 5 — Khai báo đường dẫn và fail-fast nếu thiếu artifact

```python
def candidate_paths(candidate_id: str) -> dict[str, Path]:
    candidate_root = RUN_ROOT / "candidates" / candidate_id
    return {
        "metrics": candidate_root / "model" / "validation_metrics.json",
        "manifest": candidate_root / "experiment" / "dataset_manifest.json",
        "snapshot": candidate_root / "experiment" / "data.parquet",
        "bundle": candidate_root / "model" / "model_bundle.joblib",
    }


ARTIFACT_PATHS = {
    candidate_id: candidate_paths(candidate_id)
    for candidate_id in CANDIDATES
}

missing_artifacts = [
    path
    for paths in ARTIFACT_PATHS.values()
    for path in paths.values()
    if not path.is_file()
]
if missing_artifacts:
    formatted = "\n".join(f"- {path}" for path in missing_artifacts)
    raise FileNotFoundError(f"Required Phase-4 artifacts are missing:\n{formatted}")

pd.DataFrame(
    [
        {
            "candidate_id": candidate_id,
            **{name: str(path.relative_to(REPOSITORY_ROOT)) for name, path in paths.items()},
        }
        for candidate_id, paths in ARTIFACT_PATHS.items()
    ]
)
```

### Cell 6 — Load đúng bốn file JSON metrics

Đây là cell chính theo yêu cầu: mỗi model cung cấp một
`validation_metrics.json`; notebook không hard-code metric result.

```python
def load_json_object(path: Path) -> dict[str, Any]:
    """Load a JSON object and fail with a path-specific error."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise TypeError(f"JSON root must be an object: {path}")
    return payload


raw_metrics: dict[str, dict[str, Any]] = {
    candidate_id: load_json_object(paths["metrics"])
    for candidate_id, paths in ARTIFACT_PATHS.items()
}

assert set(raw_metrics) == {"A", "B", "C", "D"}
print("Loaded 4/4 validation_metrics.json files")
```

### Cell 7 — Chuẩn hóa JSON thành một DataFrame

```python
def require_finite_number(
    payload: dict[str, Any],
    key: str,
    *,
    candidate_id: str,
) -> float:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"Candidate {candidate_id}: {key!r} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"Candidate {candidate_id}: {key!r} must be finite")
    return number


def metrics_row(
    candidate_id: str,
    metrics: dict[str, Any],
) -> dict[str, Any]:
    expected = CANDIDATES[candidate_id]
    metadata = metrics.get("model_metadata")
    if not isinstance(metadata, dict):
        raise TypeError(f"Candidate {candidate_id}: model_metadata must be an object")

    model_kind = metadata.get("model_kind")
    if model_kind != expected["model"]:
        raise ValueError(
            f"Candidate {candidate_id}: expected {expected['model']!r}, "
            f"got {model_kind!r}"
        )

    threshold_selection = metrics.get("threshold_selection")
    if not isinstance(threshold_selection, dict):
        raise TypeError(
            f"Candidate {candidate_id}: threshold_selection must be an object"
        )

    return {
        "candidate_id": candidate_id,
        "candidate_label": expected["label"],
        "model": expected["model"],
        "model_label": expected["model_label"],
        "feature_set": expected["feature_set"],
        "population_fingerprint": metrics.get("population_fingerprint"),
        "train_rows": int(
            require_finite_number(metrics, "train_rows", candidate_id=candidate_id)
        ),
        "train_fraud": int(
            require_finite_number(metrics, "train_fraud", candidate_id=candidate_id)
        ),
        "best_iteration": metadata.get("best_iteration"),
        "scale_pos_weight": metadata.get("scale_pos_weight"),
        "threshold": require_finite_number(
            metrics, "threshold", candidate_id=candidate_id
        ),
        "threshold_strategy": threshold_selection.get("strategy_result"),
        "validation_pr_auc": require_finite_number(
            metrics, "pr_auc", candidate_id=candidate_id
        ),
        "validation_roc_auc": require_finite_number(
            metrics, "roc_auc", candidate_id=candidate_id
        ),
        "validation_precision": require_finite_number(
            metrics, "precision", candidate_id=candidate_id
        ),
        "validation_recall": require_finite_number(
            metrics, "recall", candidate_id=candidate_id
        ),
        "validation_f1": require_finite_number(
            metrics, "f1", candidate_id=candidate_id
        ),
        "validation_alert_rate": require_finite_number(
            metrics, "alert_rate", candidate_id=candidate_id
        ),
        "training_seconds": require_finite_number(
            metrics, "training_seconds", candidate_id=candidate_id
        ),
    }


comparison = pd.DataFrame(
    [metrics_row(candidate_id, raw_metrics[candidate_id]) for candidate_id in CANDIDATES]
).sort_values("candidate_id", ignore_index=True)

comparison
```

### Cell 8 — Kiểm tra invariant trước khi xem biểu đồ

Không nên vẽ một bảng so sánh nếu các candidate không cùng population hoặc dùng
artifact sai model.

```python
PROBABILITY_METRICS = [
    "threshold",
    "validation_pr_auc",
    "validation_roc_auc",
    "validation_precision",
    "validation_recall",
    "validation_f1",
    "validation_alert_rate",
]

assert comparison["candidate_id"].tolist() == ["A", "B", "C", "D"]
assert comparison["population_fingerprint"].nunique() == 1, (
    "Candidates do not share one population fingerprint"
)
assert comparison["train_rows"].nunique() == 1, "Train row counts differ"
assert comparison["train_fraud"].nunique() == 1, "Train fraud counts differ"
assert (comparison["training_seconds"] >= 0).all()
assert comparison[PROBABILITY_METRICS].apply(
    lambda series: series.between(0.0, 1.0).all()
).all()
assert set(comparison["threshold_strategy"]) <= {
    "max_recall_at_min_precision",
    "fallback_max_f1",
}

for candidate_id in ("A", "C"):
    row = comparison.set_index("candidate_id").loc[candidate_id]
    assert pd.isna(row["best_iteration"])
    assert pd.isna(row["scale_pos_weight"])

for candidate_id in ("B", "D"):
    row = comparison.set_index("candidate_id").loc[candidate_id]
    assert pd.notna(row["best_iteration"])
    assert pd.notna(row["scale_pos_weight"])

print("Metric invariants passed")
print("Population:", comparison["population_fingerprint"].iloc[0])
```

### Cell 9 — Load và đối chiếu bốn manifest

Metric JSON xác nhận population fingerprint nhưng không chứa split boundary và
split statistics. Manifest được load để chứng minh temporal comparison là công
bằng.

```python
manifests = {
    candidate_id: load_manifest(paths["manifest"])
    for candidate_id, paths in ARTIFACT_PATHS.items()
}

manifest_invariants = pd.DataFrame(
    [
        {
            "candidate_id": candidate_id,
            "run_id": manifest.run_id,
            "experiment_name": manifest.experiment_name,
            "population_fingerprint": manifest.population_fingerprint,
            "train_end": manifest.split.train_end,
            "validation_end": manifest.split.validation_end,
            "test_end": manifest.split.test_end,
            "row_count": manifest.row_count,
            "fraud_count": manifest.fraud_count,
        }
        for candidate_id, manifest in manifests.items()
    ]
)

assert manifest_invariants["run_id"].nunique() == 1
assert manifest_invariants["run_id"].iloc[0] == RUN_ID
assert manifest_invariants["population_fingerprint"].nunique() == 1
assert manifest_invariants["train_end"].nunique() == 1
assert manifest_invariants["validation_end"].nunique() == 1
assert manifest_invariants["test_end"].nunique() == 1
assert manifest_invariants["row_count"].nunique() == 1
assert manifest_invariants["fraud_count"].nunique() == 1

manifest_invariants
```

### Cell 10 — Hiển thị row count, fraud count và fraud rate theo split

Các candidate có cùng population và split, vì vậy có thể lấy manifest A làm bản
đại diện cho thống kê dữ liệu.

```python
reference_manifest = manifests["A"]

split_summary = pd.DataFrame(
    [
        {
            "split": split_name,
            "row_count": statistics.row_count,
            "fraud_count": statistics.fraud_count,
            "fraud_rate": statistics.fraud_rate,
            "min_event_time": pd.to_datetime(statistics.min_event_time, utc=True),
            "max_event_time": pd.to_datetime(statistics.max_event_time, utc=True),
        }
        for split_name, statistics in (
            ("train", reference_manifest.split_statistics.train),
            ("validation", reference_manifest.split_statistics.validation),
            ("test", reference_manifest.split_statistics.test),
        )
    ]
)

display(
    split_summary.style.format(
        {
            "row_count": "{:,}",
            "fraud_count": "{:,}",
            "fraud_rate": "{:.3%}",
        }
    )
)
```

### Cell 11 — Xác nhận temporal ordering

```python
train = split_summary.set_index("split").loc["train"]
validation = split_summary.set_index("split").loc["validation"]
test = split_summary.set_index("split").loc["test"]

assert train["max_event_time"] < validation["min_event_time"]
assert validation["max_event_time"] < test["min_event_time"]

temporal_check = pd.DataFrame(
    [
        {
            "check": "train before validation",
            "left_max": train["max_event_time"],
            "right_min": validation["min_event_time"],
            "passed": True,
        },
        {
            "check": "validation before test",
            "left_max": validation["max_event_time"],
            "right_min": test["min_event_time"],
            "passed": True,
        },
    ]
)
temporal_check
```

### Cell 12 — Bảng validation metrics dành cho người đọc

```python
DISPLAY_COLUMNS = [
    "candidate_id",
    "model_label",
    "feature_set",
    "validation_pr_auc",
    "validation_roc_auc",
    "validation_precision",
    "validation_recall",
    "validation_f1",
    "validation_alert_rate",
    "threshold",
    "best_iteration",
    "training_seconds",
]

display(
    comparison[DISPLAY_COLUMNS].style.format(
        {
            "validation_pr_auc": "{:.4f}",
            "validation_roc_auc": "{:.4f}",
            "validation_precision": "{:.2%}",
            "validation_recall": "{:.2%}",
            "validation_f1": "{:.4f}",
            "validation_alert_rate": "{:.2%}",
            "threshold": "{:.6f}",
            "training_seconds": "{:.4f}",
        }
    ).background_gradient(
        subset=["validation_pr_auc", "validation_recall"],
        cmap="YlGn",
    )
)

comparison.to_csv(REPORT_ROOT / "model_comparison.csv", index=False)
```

### Cell 13 — Trực quan PR-AUC, ROC-AUC và F1 từ bốn JSON

```python
metric_overview = comparison.melt(
    id_vars=["candidate_id", "candidate_label"],
    value_vars=[
        "validation_pr_auc",
        "validation_roc_auc",
        "validation_f1",
    ],
    var_name="metric",
    value_name="value",
)

metric_labels = {
    "validation_pr_auc": "PR-AUC",
    "validation_roc_auc": "ROC-AUC",
    "validation_f1": "F1",
}
metric_overview["metric"] = metric_overview["metric"].map(metric_labels)

fig, ax = plt.subplots(figsize=(11, 6))
sns.barplot(
    data=metric_overview,
    x="candidate_id",
    y="value",
    hue="metric",
    ax=ax,
)
ax.set(
    title="Validation ranking metrics by candidate",
    xlabel="Candidate",
    ylabel="Metric value",
    ylim=(0.0, 1.05),
)
ax.legend(title="Metric", loc="lower right")
ax.bar_label(ax.containers[0], fmt="%.3f", padding=2, fontsize=8)
ax.bar_label(ax.containers[1], fmt="%.3f", padding=2, fontsize=8)
ax.bar_label(ax.containers[2], fmt="%.3f", padding=2, fontsize=8)
fig.tight_layout()
fig.savefig(REPORT_ROOT / "validation_metric_overview.png", bbox_inches="tight")
plt.show()
```

PR-AUC là metric ranking chính cho fraud imbalance. ROC-AUC vẫn được báo cáo,
nhưng không nên dùng nó một mình để chọn model.

### Cell 14 — Precision, recall và alert rate tại threshold đã chọn

```python
threshold_metrics = comparison.melt(
    id_vars=["candidate_id", "candidate_label"],
    value_vars=[
        "validation_precision",
        "validation_recall",
        "validation_alert_rate",
    ],
    var_name="metric",
    value_name="value",
)

threshold_metric_labels = {
    "validation_precision": "Precision",
    "validation_recall": "Recall",
    "validation_alert_rate": "Alert rate",
}
threshold_metrics["metric"] = threshold_metrics["metric"].map(
    threshold_metric_labels
)

fig, ax = plt.subplots(figsize=(11, 6))
sns.barplot(
    data=threshold_metrics,
    x="candidate_id",
    y="value",
    hue="metric",
    ax=ax,
)
ax.axhline(
    0.10,
    color="black",
    linestyle="--",
    linewidth=1.2,
    label="Minimum precision = 10%",
)
ax.set(
    title="Validation operating point at each selected threshold",
    xlabel="Candidate",
    ylabel="Rate",
    ylim=(0.0, 1.05),
)
ax.yaxis.set_major_formatter(lambda value, _: f"{value:.0%}")
ax.legend(title="Metric / constraint", loc="upper center")
fig.tight_layout()
fig.savefig(REPORT_ROOT / "validation_threshold_metrics.png", bbox_inches="tight")
plt.show()
```

Đọc biểu đồ theo ba câu hỏi:

1. Candidate có đạt precision tối thiểu 10% không?
2. Trong nhóm đạt constraint, candidate nào bắt được nhiều fraud nhất?
3. Với recall tương đương, candidate nào tạo ít alert hơn?

### Cell 15 — Load model bundle và tái tạo validation probabilities

Cell này không train lại. Nó load model đã fit và chạy inference trên validation
split để lấy đủ probability cho PR curve.

```python
def load_validation_artifacts(
    candidate_id: str,
) -> tuple[dict[str, Any], Any, np.ndarray]:
    paths = ARTIFACT_PATHS[candidate_id]
    bundle = joblib.load(paths["bundle"])
    if not isinstance(bundle, dict):
        raise TypeError(f"Candidate {candidate_id}: model bundle must be a dict")

    config = ExperimentConfig.model_validate(bundle["config"])
    manifest = manifests[candidate_id]
    splits = load_dataset_splits(
        snapshot_path=paths["snapshot"],
        manifest=manifest,
        config=config,
    )

    model = bundle["model"]
    probability = np.asarray(
        model.predict_proba(splits.validation.features)[:, 1],
        dtype=np.float64,
    )
    target = splits.validation.target.to_numpy(dtype=np.uint8)

    if probability.shape != target.shape:
        raise ValueError(f"Candidate {candidate_id}: prediction shape mismatch")
    if not np.isfinite(probability).all():
        raise ValueError(f"Candidate {candidate_id}: non-finite probabilities")
    if ((probability < 0.0) | (probability > 1.0)).any():
        raise ValueError(f"Candidate {candidate_id}: probabilities outside [0, 1]")

    expected_pr_auc = float(raw_metrics[candidate_id]["pr_auc"])
    observed_pr_auc = float(average_precision_score(target, probability))
    if not math.isclose(observed_pr_auc, expected_pr_auc, abs_tol=1e-12):
        raise ValueError(
            f"Candidate {candidate_id}: reproduced PR-AUC {observed_pr_auc} "
            f"does not match JSON {expected_pr_auc}"
        )

    return bundle, splits.validation, probability


loaded_validation = {
    candidate_id: load_validation_artifacts(candidate_id)
    for candidate_id in CANDIDATES
}

print("Reproduced validation probabilities and PR-AUC for 4/4 candidates")
```

### Cell 16 — Precision–Recall curve trên validation

```python
fig, ax = plt.subplots(figsize=(10, 7))

validation_prevalence: float | None = None
for candidate_id, (_, validation_split, probability) in loaded_validation.items():
    target = validation_split.target.to_numpy(dtype=np.uint8)
    precision, recall, _ = precision_recall_curve(target, probability)
    prevalence = float(target.mean())

    if validation_prevalence is None:
        validation_prevalence = prevalence
    elif not math.isclose(validation_prevalence, prevalence, abs_tol=1e-15):
        raise ValueError("Validation prevalence differs across candidates")

    pr_auc = float(raw_metrics[candidate_id]["pr_auc"])
    ax.step(
        recall,
        precision,
        where="post",
        color=CANDIDATE_COLORS[candidate_id],
        linewidth=2,
        label=f"{CANDIDATES[candidate_id]['label']} · AP={pr_auc:.3f}",
    )

    ax.scatter(
        raw_metrics[candidate_id]["recall"],
        raw_metrics[candidate_id]["precision"],
        color=CANDIDATE_COLORS[candidate_id],
        edgecolor="black",
        s=55,
        zorder=3,
    )

assert validation_prevalence is not None
ax.axhline(
    validation_prevalence,
    color="gray",
    linestyle=":",
    linewidth=1.5,
    label=f"Validation prevalence={validation_prevalence:.3%}",
)
ax.set(
    title="Validation Precision–Recall curves",
    xlabel="Recall",
    ylabel="Precision",
    xlim=(0.0, 1.01),
    ylim=(0.0, 1.01),
)
ax.legend(loc="upper right", fontsize=8)
fig.tight_layout()
fig.savefig(REPORT_ROOT / "validation_pr_curve.png", bbox_inches="tight")
plt.show()
```

Mỗi chấm tròn là operating point tại threshold đã được Phase 4 chọn. Đường cong
không được tạo từ test data.

### Cell 17 — XGBoost feature importance

`feature_importances_` của XGBoost phụ thuộc vào cách estimator định nghĩa
importance. Đây là tín hiệu mô tả model, không phải causal effect. Không kết luận
rằng feature “gây ra fraud”.

```python
def clean_transformed_feature_name(name: str) -> str:
    """Remove ColumnTransformer prefixes while preserving category names."""

    return name.split("__", maxsplit=1)[-1]


def xgboost_importance(candidate_id: str) -> pd.DataFrame:
    bundle, _, _ = loaded_validation[candidate_id]
    fitted_model = bundle["model"]
    feature_names = fitted_model.preprocessor.get_feature_names_out()
    importance = np.asarray(
        fitted_model.estimator.feature_importances_,
        dtype=np.float64,
    )
    if len(feature_names) != len(importance):
        raise ValueError(f"Candidate {candidate_id}: importance shape mismatch")

    return pd.DataFrame(
        {
            "candidate_id": candidate_id,
            "feature": [
                clean_transformed_feature_name(name) for name in feature_names
            ],
            "importance": importance,
        }
    ).sort_values("importance", ascending=False, ignore_index=True)


xgboost_importances = pd.concat(
    [xgboost_importance("B"), xgboost_importance("D")],
    ignore_index=True,
)

fig, axes = plt.subplots(1, 2, figsize=(15, 7))
for ax, candidate_id in zip(axes, ("B", "D"), strict=True):
    plot_data = (
        xgboost_importances.query("candidate_id == @candidate_id")
        .nlargest(12, "importance")
        .sort_values("importance")
    )
    sns.barplot(
        data=plot_data,
        x="importance",
        y="feature",
        color=CANDIDATE_COLORS[candidate_id],
        ax=ax,
    )
    ax.set(
        title=f"{CANDIDATES[candidate_id]['label']} — top feature importance",
        xlabel="XGBoost feature importance",
        ylabel="Transformed feature",
    )

fig.suptitle("XGBoost feature importance on fitted Phase-4 artifacts", y=1.02)
fig.tight_layout()
fig.savefig(REPORT_ROOT / "feature_importance.png", bbox_inches="tight")
plt.show()
```

### Cell 18 — Logistic Regression coefficient magnitude

Numeric features của Logistic Regression đã được standardize, nên độ lớn
coefficient có thể so sánh trong cùng model dễ hơn. One-hot category vẫn cần được
đọc theo category reference và các feature tương quan có thể làm coefficient
không ổn định.

```python
def logistic_coefficients(candidate_id: str) -> pd.DataFrame:
    bundle, _, _ = loaded_validation[candidate_id]
    fitted_model = bundle["model"]
    feature_names = fitted_model.preprocessor.get_feature_names_out()
    coefficient = np.asarray(fitted_model.estimator.coef_[0], dtype=np.float64)
    if len(feature_names) != len(coefficient):
        raise ValueError(f"Candidate {candidate_id}: coefficient shape mismatch")

    return pd.DataFrame(
        {
            "candidate_id": candidate_id,
            "feature": [
                clean_transformed_feature_name(name) for name in feature_names
            ],
            "coefficient": coefficient,
            "absolute_coefficient": np.abs(coefficient),
        }
    ).sort_values("absolute_coefficient", ascending=False, ignore_index=True)


logistic_coefficients_frame = pd.concat(
    [logistic_coefficients("A"), logistic_coefficients("C")],
    ignore_index=True,
)

fig, axes = plt.subplots(1, 2, figsize=(15, 7))
for ax, candidate_id in zip(axes, ("A", "C"), strict=True):
    plot_data = (
        logistic_coefficients_frame.query("candidate_id == @candidate_id")
        .nlargest(12, "absolute_coefficient")
        .sort_values("coefficient")
    )
    colors = ["#D62728" if value < 0 else "#2CA02C" for value in plot_data["coefficient"]]
    ax.barh(plot_data["feature"], plot_data["coefficient"], color=colors)
    ax.axvline(0.0, color="black", linewidth=1)
    ax.set(
        title=f"{CANDIDATES[candidate_id]['label']} — top coefficients",
        xlabel="Standardized logistic coefficient",
        ylabel="Transformed feature",
    )

fig.suptitle("Logistic Regression coefficient magnitude", y=1.02)
fig.tight_layout()
fig.savefig(REPORT_ROOT / "logistic_coefficients.png", bbox_inches="tight")
plt.show()
```

Màu xanh biểu thị coefficient dương và màu đỏ biểu thị coefficient âm. Đây là
association trong model, không phải quan hệ nhân quả.

### Cell 19 — So sánh thời gian train

```python
fig, ax = plt.subplots(figsize=(9, 5))
training_plot = comparison.sort_values("training_seconds", ascending=False)

sns.barplot(
    data=training_plot,
    x="candidate_id",
    y="training_seconds",
    hue="candidate_id",
    palette=CANDIDATE_COLORS,
    legend=False,
    ax=ax,
)
for container in ax.containers:
    ax.bar_label(container, fmt="%.4f s", padding=3)

ax.set(
    title="Model fit duration by candidate",
    xlabel="Candidate",
    ylabel="Training seconds",
)
fig.tight_layout()
fig.savefig(REPORT_ROOT / "training_seconds.png", bbox_inches="tight")
plt.show()
```

Chỉ diễn giải training time như số đo tham khảo. Với thời gian dưới một giây,
OS scheduling và warm-up có thể chi phối chênh lệch nhỏ. Không tuyên bố model A
nhanh hơn model C một cách tổng quát chỉ từ một lần đo.

### Cell 20 — Áp dụng selection rule

Các tolerance phải được khóa trước khi xem test:

- precision tối thiểu: `0.10`;
- recall được xem là gần bằng nhau nếu chênh không quá `0.001` absolute;
- PR-AUC được xem là gần bằng nhau nếu chênh không quá `0.01` absolute;
- nếu XGBoost và Logistic gần bằng nhau theo các tolerance trên, ưu tiên Logistic
  vì đơn giản hơn.

```python
MIN_PRECISION = 0.10
RECALL_TOLERANCE = 0.001
PR_AUC_TOLERANCE = 0.01


def select_validation_candidate(frame: pd.DataFrame) -> tuple[pd.Series, list[str]]:
    reasons: list[str] = []

    eligible = frame.loc[
        frame["validation_precision"] >= MIN_PRECISION
    ].copy()
    if eligible.empty:
        raise RuntimeError("No candidate satisfies minimum validation precision")
    reasons.append(
        f"{len(eligible)}/4 candidates satisfy precision >= {MIN_PRECISION:.0%}."
    )

    best_recall = float(eligible["validation_recall"].max())
    recall_pool = eligible.loc[
        eligible["validation_recall"] >= best_recall - RECALL_TOLERANCE
    ].copy()
    reasons.append(
        "Kept candidates within "
        f"{RECALL_TOLERANCE:.3f} of best recall ({best_recall:.4f})."
    )

    best_pr_auc = float(recall_pool["validation_pr_auc"].max())
    pr_auc_pool = recall_pool.loc[
        recall_pool["validation_pr_auc"] >= best_pr_auc - PR_AUC_TOLERANCE
    ].copy()
    reasons.append(
        "Kept candidates within "
        f"{PR_AUC_TOLERANCE:.3f} of best PR-AUC ({best_pr_auc:.4f})."
    )

    ranked = pr_auc_pool.sort_values(
        [
            "validation_alert_rate",
            "training_seconds",
            "candidate_id",
        ],
        ascending=[True, True, True],
    )
    winner = ranked.iloc[0]

    logistic_alternative = pr_auc_pool.loc[
        pr_auc_pool["model"] == "logistic_regression"
    ].sort_values(
        ["validation_alert_rate", "training_seconds", "candidate_id"]
    )
    if winner["model"] == "xgboost" and not logistic_alternative.empty:
        winner = logistic_alternative.iloc[0]
        reasons.append(
            "XGBoost and Logistic remained inside the declared PR-AUC tolerance; "
            "selected Logistic Regression as the simpler model."
        )
    else:
        reasons.append(
            "Selected the lowest alert rate after recall and PR-AUC filtering."
        )

    return winner, reasons


winner, selection_reasons = select_validation_candidate(comparison)

display(
    comparison.sort_values(
        [
            "validation_precision",
            "validation_recall",
            "validation_pr_auc",
            "validation_alert_rate",
        ],
        ascending=[False, False, False, True],
    )[DISPLAY_COLUMNS]
)

print("Selected candidate:", winner["candidate_id"])
for reason in selection_reasons:
    print("-", reason)
```

Lưu ý: đoạn code trên không tối ưu một weighted score tùy ý. Nó áp dụng rule
theo thứ tự để quyết định dễ giải thích và audit.

### Cell 21 — Tạo `model_selection.json`

File này chỉ ghi quyết định dựa trên validation. `test_accessed` phải là `false`.
Phase 6 sẽ dùng candidate và threshold đã khóa để đánh giá test đúng một lần.

```python
def json_safe(value: Any) -> Any:
    if value is None or value is pd.NA:
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if np.isnan(value) else float(value)
    if isinstance(value, float) and np.isnan(value):
        return None
    return value


winner_id = str(winner["candidate_id"])
winner_manifest = manifests[winner_id]
winner_metrics = raw_metrics[winner_id]

selection_payload = {
    "selection_schema_version": 1,
    "run_id": RUN_ID,
    "selected_candidate_id": winner_id,
    "selected_model": winner["model"],
    "selected_feature_set": winner["feature_set"],
    "population_fingerprint": winner_manifest.population_fingerprint,
    "selected_threshold": float(winner["threshold"]),
    "validation_metrics": {
        "pr_auc": float(winner["validation_pr_auc"]),
        "roc_auc": float(winner["validation_roc_auc"]),
        "precision": float(winner["validation_precision"]),
        "recall": float(winner["validation_recall"]),
        "f1": float(winner["validation_f1"]),
        "alert_rate": float(winner["validation_alert_rate"]),
    },
    "model_metadata": {
        key: json_safe(value)
        for key, value in winner_metrics["model_metadata"].items()
    },
    "selection_policy": {
        "minimum_precision": MIN_PRECISION,
        "recall_tolerance": RECALL_TOLERANCE,
        "pr_auc_tolerance": PR_AUC_TOLERANCE,
        "tie_breaker": "lower_alert_rate_then_simpler_model",
    },
    "reasons": selection_reasons,
    "test_accessed": False,
    "limitations": [
        "Small demo dataset with few fraud cases.",
        "Validation was reused for XGBoost early stopping and candidate selection.",
        "Results must not be described as production performance.",
    ],
}

selection_path = REPORT_ROOT / "model_selection.json"
selection_path.write_text(
    json.dumps(selection_payload, indent=2, ensure_ascii=False) + "\n",
    encoding="utf-8",
)

display(Markdown(f"## Selected candidate: **{winner_id}**"))
display(Markdown(f"- Model: `{winner['model']}`"))
display(Markdown(f"- Feature set: `{winner['feature_set']}`"))
display(Markdown(f"- Validation PR-AUC: `{winner['validation_pr_auc']:.4f}`"))
display(Markdown(f"- Validation precision: `{winner['validation_precision']:.2%}`"))
display(Markdown(f"- Validation recall: `{winner['validation_recall']:.2%}`"))
display(Markdown(f"- Validation alert rate: `{winner['validation_alert_rate']:.2%}`"))
display(Markdown("**Test has not been accessed in this notebook.**"))
```

### Cell 22 — Cảnh báo giới hạn dữ liệu tự động

```python
total_fraud = int(reference_manifest.fraud_count)
validation_fraud = int(reference_manifest.split_statistics.validation.fraud_count)

display(
    Markdown(
        f"""
## Data limitation

- Total rows: **{reference_manifest.row_count:,}**
- Total fraud cases: **{total_fraud:,}**
- Validation fraud cases: **{validation_fraud:,}**

Validation chỉ có {validation_fraud} fraud case. Một case dự đoán đúng hoặc sai
có thể làm recall thay đổi khoảng **{1 / validation_fraud:.2%}**. Vì vậy không
nên diễn giải chênh lệch nhỏ là bằng chứng model ổn định hơn trong production.
"""
    )
)
```

### Cell 23 — Kiểm tra output cuối notebook

```python
EXPECTED_OUTPUTS = [
    REPORT_ROOT / "model_comparison.csv",
    REPORT_ROOT / "model_selection.json",
    REPORT_ROOT / "validation_metric_overview.png",
    REPORT_ROOT / "validation_threshold_metrics.png",
    REPORT_ROOT / "validation_pr_curve.png",
    REPORT_ROOT / "feature_importance.png",
    REPORT_ROOT / "logistic_coefficients.png",
    REPORT_ROOT / "training_seconds.png",
]

output_check = pd.DataFrame(
    [
        {
            "artifact": path.name,
            "exists": path.is_file(),
            "size_bytes": path.stat().st_size if path.is_file() else 0,
        }
        for path in EXPECTED_OUTPUTS
    ]
)

assert output_check["exists"].all(), "One or more notebook outputs are missing"
assert (output_check["size_bytes"] > 0).all(), "One or more outputs are empty"
output_check
```

### Cell 24 — Markdown: kết luận cuối notebook

Sau khi chạy và đọc các con số, viết một Markdown cell bằng cấu trúc sau. Không
hard-code kết luận trước khi notebook chạy.

```markdown
## Kết luận

Candidate được chọn bằng validation rule là **<ID> — <model>/<feature set>**.

Lý do:

1. Candidate đạt precision constraint tối thiểu 10%.
2. Candidate có validation recall <giá trị>.
3. Trong nhóm recall gần bằng nhau, candidate có PR-AUC <giá trị>.
4. Alert rate tại threshold đã khóa là <giá trị>.
5. Mức cải thiện so với Logistic baseline là <mô tả có số liệu>.

Quyết định hiện tại chỉ khóa candidate, hyperparameters và validation threshold.
Test set chưa được dùng. Phase 6 sẽ đánh giá candidate được khóa đúng một lần
trên test và sẽ không quay lại tune model dựa trên test result.

Dữ liệu demo có ít fraud case, vì vậy kết luận chỉ chứng minh quy trình model
selection có kiểm soát leakage và có thể tái lập; không đại diện cho hiệu năng
production.
```

## 6. Chạy notebook từ đầu đến cuối

Trong giao diện notebook, chọn **Restart Kernel and Run All**. Nếu muốn kiểm tra
bằng command line sau khi đã lưu notebook:

```bash
uv run jupyter nbconvert \
  --to notebook \
  --execute notebooks/model_experiments.ipynb \
  --output model_experiments.executed.ipynb \
  --ExecutePreprocessor.timeout=600
```

File executed mặc định được ghi trong `notebooks/`. Có thể mở nó để xác nhận mọi
cell đã chạy và output được render.

## 7. Cách diễn giải kết quả hiện có

Với run `20260825T082223Z`, bốn JSON hiện tại cho thấy:

| Candidate | PR-AUC | Precision | Recall | Alert rate | Train time |
| --- | ---: | ---: | ---: | ---: | ---: |
| A | 0.5661 | 10.00% | 92.86% | 11.64% | 0.1243 s |
| B | 0.7560 | 10.00% | 100.00% | 12.53% | 0.2190 s |
| C | 0.8484 | 10.00% | 100.00% | 12.53% | 0.1464 s |
| D | 0.9556 | 10.14% | 100.00% | 12.35% | 0.1886 s |

Theo rule đã khai báo, candidate D là đề xuất hợp lý để chuyển sang Phase 6:

- đạt precision tối thiểu;
- recall bằng 100%;
- PR-AUC cao nhất trong nhóm recall 100%;
- alert rate thấp hơn B và C;
- PR-AUC cao hơn candidate C khoảng `0.1072` absolute, lớn hơn tolerance `0.01`,
  nên complexity fallback không đổi winner về Logistic Regression.

Đây vẫn chỉ là validation decision. Không được ghi “D là model cuối cùng tốt
nhất” cho đến khi Phase 6 khóa D và đánh giá test đúng một lần.

## 8. Những điều không nên làm trong notebook

- Không gọi `fit`, `train_and_select_threshold` hoặc thay hyperparameter.
- Không chạy grid search hay cross-validation trong Phase 5 này.
- Không xem test metrics trước khi ghi `model_selection.json`.
- Không thay threshold sau khi thấy test result.
- Không chỉ vẽ ROC-AUC rồi bỏ qua PR-AUC và alert rate.
- Không suy ra PR curve từ một điểm precision/recall trong JSON.
- Không gọi feature importance là bằng chứng nhân quả.
- Không so sánh training time rất nhỏ như benchmark tổng quát.
- Không tự động chọn run mới nhất cho báo cáo cần tái lập.

## 9. Definition of Done

Phase 5 hoàn thành khi:

- [ ] Notebook load đúng bốn `validation_metrics.json`.
- [ ] Candidate A/B/C/D khớp model kind và feature set dự kiến.
- [ ] Bốn candidate có cùng population fingerprint, run ID và temporal boundary.
- [ ] Split summary hiển thị row count, fraud count và fraud rate.
- [ ] Temporal ordering được assert bằng code.
- [ ] Bảng comparison được ghi thành `model_comparison.csv`.
- [ ] Có biểu đồ PR-AUC/ROC-AUC/F1 từ bốn JSON.
- [ ] Có biểu đồ precision/recall/alert rate tại selected threshold.
- [ ] PR curve được tái tạo từ validation probability, không dùng test.
- [ ] Có XGBoost feature importance và Logistic coefficient plot.
- [ ] Có training duration plot.
- [ ] Selection rule được khai báo trước test và chạy bằng code.
- [ ] `model_selection.json` chứa `test_accessed: false`.
- [ ] Notebook có cảnh báo dữ liệu nhỏ và không nói quá hiệu năng.
- [ ] `Restart Kernel and Run All` chạy thành công.

Sau Definition of Done này, Phase 6 chỉ được load winner đã khóa, dùng đúng
threshold đã khóa và evaluate test một lần.
