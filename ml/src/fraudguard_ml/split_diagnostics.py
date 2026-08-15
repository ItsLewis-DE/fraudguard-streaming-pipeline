from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import ks_2samp # được dùng để kiểm tra phân phối của
#2 feature có giống nhau k

from fraudguard_ml.artifacts import write_json_immutable
from fraudguard_ml.dataset_loader import DatasetSplits, FrameSplit

EPSILON = 1e-6

def basic_split_summary(split: FrameSplit) -> dict[str, Any]:
    row_count = len(split.target)
    fraud_count = int(split.target.sum())
    return {
        "row_count": row_count,
        "fraud_count": fraud_count,
        "fraud_rate": fraud_count / row_count if row_count else 0.0,
        "min_event_time": split.event_time.min().isoformat(),
        "max_event_time": split.event_time.max().isoformat(),
        "missing_rate": {
            column: float(value)
            for column, value in split.features.isna().mean().items()
        },
    }

def numeric_summary(series: pd.Series) -> dict[str, float | None]:
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().sum() == 0:
        return {name: None for name in ("mean", "std", "p05", "p50", "p95")}
    return {
        "mean": float(numeric.mean()),
        "std": float(numeric.std()),
        "p05": float(numeric.quantile(0.05)),
        "p50": float(numeric.quantile(0.50)),
        "p95": float(numeric.quantile(0.95)),
    }

def categorical_distribution(series: pd.Series) -> dict[str, float]:
    normalized = series.fillna("<MISSING>").astype(str).value_counts(normalize=True)
    return {str(key): float(value) for key, value in normalized.items()}

def population_stability_index(
    reference: pd.Series,
    comparison: pd.Series,
    bins: int = 10,
) -> float | None:
    ref = pd.to_numeric(reference, errors="coerce").dropna().to_numpy()
    cmp = pd.to_numeric(comparison, errors="coerce").dropna().to_numpy()
    if len(ref) == 0 or len(cmp) == 0:
        return None
    edges = np.unique(np.quantile(ref, np.linspace(0.0, 1.0, bins + 1)))
    if len(edges) < 3:
        return 0.0
    edges[0], edges[-1] = -np.inf, np.inf
    ref_counts, _ = np.histogram(ref, bins=edges)
    cmp_counts, _ = np.histogram(cmp, bins=edges)
    ref_rate = np.maximum(ref_counts / ref_counts.sum(), EPSILON)
    cmp_rate = np.maximum(cmp_counts / cmp_counts.sum(), EPSILON)
    return float(np.sum((cmp_rate - ref_rate) * np.log(cmp_rate / ref_rate)))

def numeric_drift(
    reference: pd.Series, comparison: pd.Series
) -> dict[str, float | None]:
    ref = pd.to_numeric(reference, errors="coerce").dropna()
    cmp = pd.to_numeric(comparison, errors="coerce").dropna()
    if ref.empty or cmp.empty:
        return {"psi": None, "ks_statistic": None, "ks_pvalue": None}
    ks = ks_2samp(ref, cmp)
    return {
        "psi": population_stability_index(ref, cmp),
        "ks_statistic": float(ks.statistic),
        "ks_pvalue": float(ks.pvalue),
    }

def build_split_diagnostics(
    splits: DatasetSplits,
    *,
    numeric_columns: tuple[str, ...],
    categorical_columns: tuple[str, ...],
) -> dict[str, Any]:
    split_map: Mapping[str, FrameSplit] = {
        "train": splits.train,
        "validation": splits.validation,
        "test": splits.test,
    }
    report: dict[str, Any] = {
        "splits": {
            name: basic_split_summary(value) for name, value in split_map.items()
        },
        "numeric": {},
        "categorical": {},
    }
    for column in numeric_columns:
        report["numeric"][column] = {
            "summary": {
                name: numeric_summary(value.features[column])
                for name, value in split_map.items()
            },
            "drift_from_train": {
                "validation": numeric_drift(
                    splits.train.features[column],
                    splits.validation.features[column],
                ),
                "test": numeric_drift(
                    splits.train.features[column],
                    splits.test.features[column],
                ),
            },
        }
    for column in categorical_columns:
        report["categorical"][column] = {
            name: categorical_distribution(value.features[column])
            for name, value in split_map.items()
        }
    return report

def write_diagnostics(path: Path, report: dict[str, Any]) -> None:
    write_json_immutable(path, report)
    