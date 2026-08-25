from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
import pandas as pd
from numpy.typing import NDArray
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from xgboost import XGBClassifier

from fraudguard_ml.dataset_loader import FrameSplit
from fraudguard_ml.experiment_config import (
    ExperimentConfig,
    LogisticRegressionConfig,
    XGBoostConfig,
)

type ModelKind = Literal["logistic_regression", "xgboost"]
type ProbabilityEstimator = LogisticRegression | XGBClassifier


class ModelingError(RuntimeError):
    """A probability model cannot be fit or used safely."""


@dataclass(frozen=True)
class ModelMetadata:
    """Resolved model and preprocessing facts persisted with the artifact."""

    model_kind: ModelKind
    resolved_hyperparameters: dict[str, Any]
    numeric_scaling: Literal["standard", "none"]
    scale_pos_weight: float | None
    best_iteration: int | None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable copy of the metadata."""

        return {
            "model_kind": self.model_kind,
            "resolved_hyperparameters": dict(self.resolved_hyperparameters),
            "numeric_scaling": self.numeric_scaling,
            "scale_pos_weight": self.scale_pos_weight,
            "best_iteration": self.best_iteration,
        }


def _normalize_feature_types(
    frame: pd.DataFrame,
    *,
    feature_columns: tuple[str, ...],
    categorical_columns: tuple[str, ...],
    numeric_columns: tuple[str, ...],
) -> pd.DataFrame:
    missing = [column for column in feature_columns if column not in frame.columns]
    if missing:
        raise ModelingError(f"missing required feature columns: {missing}")
    normalized = frame.loc[:, list(feature_columns)].copy()
    for column in categorical_columns:
        normalized[column] = normalized[column].astype("string")
    for column in numeric_columns:
        try:
            normalized[column] = pd.to_numeric(
                normalized[column],
                errors="raise",
            ).astype("float64")
        except (TypeError, ValueError) as exc:
            raise ModelingError(
                f"feature column {column!r} cannot be converted to float64"
            ) from exc
    return normalized


def _feature_groups(
    config: ExperimentConfig,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    categorical = tuple(
        column
        for column in config.dataset.feature_columns
        if column == "transaction_type"
    )
    numeric = tuple(
        column for column in config.dataset.feature_columns if column not in categorical
    )
    return categorical, numeric


@dataclass(frozen=True)
class FittedProbabilityModel:
    """A fitted preprocessor and estimator exposed through one interface."""

    feature_columns: tuple[str, ...]
    categorical_columns: tuple[str, ...]
    numeric_columns: tuple[str, ...]
    preprocessor: ColumnTransformer
    estimator: ProbabilityEstimator
    metadata: ModelMetadata

    def predict_proba(
        self,
        features: pd.DataFrame,
    ) -> NDArray[np.float64]:
        """Transform features and return validated two-class probabilities."""

        normalized = _normalize_feature_types(
            features,
            feature_columns=self.feature_columns,
            categorical_columns=self.categorical_columns,
            numeric_columns=self.numeric_columns,
        )
        matrix = self.preprocessor.transform(normalized)
        probability = np.asarray(
            self.estimator.predict_proba(matrix),
            dtype=np.float64,
        )
        expected_shape = (len(normalized), 2)
        if probability.shape != expected_shape:
            raise ModelingError(
                "predict_proba returned shape "
                f"{probability.shape}, expected {expected_shape}"
            )
        if not np.isfinite(probability).all():
            raise ModelingError("predict_proba returned non-finite values")
        if ((probability < 0.0) | (probability > 1.0)).any():
            raise ModelingError("predict_proba returned values outside [0, 1]")
        return probability


def _build_preprocessor(
    *,
    categorical_columns: tuple[str, ...],
    numeric_columns: tuple[str, ...],
    scale_numeric: bool,
) -> ColumnTransformer:
    transformers: list[tuple[str, Pipeline, list[str]]] = []
    if categorical_columns:
        categorical_pipeline = Pipeline(
            steps=[
                ("imputer", SimpleImputer(strategy="most_frequent")),
                (
                    "one_hot",
                    OneHotEncoder(handle_unknown="ignore", sparse_output=True),
                ),
            ]
        )
        transformers.append(
            ("categorical", categorical_pipeline, list(categorical_columns))
        )
    if numeric_columns:
        numeric_steps: list[tuple[str, Any]] = [
            ("imputer", SimpleImputer(strategy="median"))
        ]
        if scale_numeric:
            numeric_steps.append(("scaler", StandardScaler()))
        numeric_pipeline = Pipeline(steps=numeric_steps)
        transformers.append(("numeric", numeric_pipeline, list(numeric_columns)))
    if not transformers:
        raise ModelingError("at least one feature column is required")
    return ColumnTransformer(
        transformers=transformers,
        remainder="drop",
        verbose_feature_names_out=True,
    )


def _validate_binary_target(target: pd.Series, *, split_name: str) -> None:
    if target.isna().any():
        raise ModelingError(f"{split_name} target contains null values")
    values = {int(value) for value in pd.unique(target)}
    if values != {0, 1}:
        raise ModelingError(
            f"{split_name} target must contain both binary classes, got {values}"
        )


def _calculate_scale_pos_weight(target: pd.Series) -> float:
    positive_count = int((target == 1).sum())
    negative_count = int((target == 0).sum())
    if positive_count == 0 or negative_count == 0:
        raise ModelingError(
            "train target must contain positives and negatives for class weighting"
        )
    return float(negative_count / positive_count)


def _fit_logistic_regression(
    *,
    config: ExperimentConfig,
    model_config: LogisticRegressionConfig,
    train: FrameSplit,
) -> FittedProbabilityModel:
    categorical, numeric = _feature_groups(config)
    preprocessor = _build_preprocessor(
        categorical_columns=categorical,
        numeric_columns=numeric,
        scale_numeric=True,
    )
    train_features = _normalize_feature_types(
        train.features,
        feature_columns=config.dataset.feature_columns,
        categorical_columns=categorical,
        numeric_columns=numeric,
    )
    train_matrix = preprocessor.fit_transform(train_features)
    estimator = LogisticRegression(
        C=model_config.regularization_c,
        class_weight=model_config.class_weight,
        max_iter=model_config.max_iter,
        random_state=config.runtime.random_seed,
        solver="lbfgs",
    )
    estimator.fit(train_matrix, train.target)
    metadata = ModelMetadata(
        model_kind="logistic_regression",
        resolved_hyperparameters={
            **model_config.model_dump(mode="json"),
            "random_state": config.runtime.random_seed,
            "solver": "lbfgs",
        },
        numeric_scaling="standard",
        scale_pos_weight=None,
        best_iteration=None,
    )
    return FittedProbabilityModel(
        feature_columns=config.dataset.feature_columns,
        categorical_columns=categorical,
        numeric_columns=numeric,
        preprocessor=preprocessor,
        estimator=estimator,
        metadata=metadata,
    )


def _fit_xgboost(
    *,
    config: ExperimentConfig,
    model_config: XGBoostConfig,
    train: FrameSplit,
    validation: FrameSplit,
) -> FittedProbabilityModel:
    categorical, numeric = _feature_groups(config)
    preprocessor = _build_preprocessor(
        categorical_columns=categorical,
        numeric_columns=numeric,
        scale_numeric=False,
    )
    train_features = _normalize_feature_types(
        train.features,
        feature_columns=config.dataset.feature_columns,
        categorical_columns=categorical,
        numeric_columns=numeric,
    )
    validation_features = _normalize_feature_types(
        validation.features,
        feature_columns=config.dataset.feature_columns,
        categorical_columns=categorical,
        numeric_columns=numeric,
    )
    train_matrix = preprocessor.fit_transform(train_features)
    validation_matrix = preprocessor.transform(validation_features)
    scale_pos_weight = (
        _calculate_scale_pos_weight(train.target)
        if model_config.imbalance_strategy == "train_ratio"
        else 1.0
    )
    estimator = XGBClassifier(
        objective=model_config.objective,
        eval_metric=model_config.eval_metric,
        tree_method=model_config.tree_method,
        n_estimators=model_config.n_estimators,
        learning_rate=model_config.learning_rate,
        max_depth=model_config.max_depth,
        min_child_weight=model_config.min_child_weight,
        subsample=model_config.subsample,
        colsample_bytree=model_config.colsample_bytree,
        reg_alpha=model_config.reg_alpha,
        reg_lambda=model_config.reg_lambda,
        early_stopping_rounds=model_config.early_stopping_rounds,
        scale_pos_weight=scale_pos_weight,
        random_state=config.runtime.random_seed,
        n_jobs=config.runtime.max_cpu_threads,
        verbosity=0,
    )
    estimator.fit(
        train_matrix,
        train.target,
        eval_set=[(validation_matrix, validation.target)],
        verbose=False,
    )
    best_iteration = int(estimator.best_iteration)
    metadata = ModelMetadata(
        model_kind="xgboost",
        resolved_hyperparameters={
            **model_config.model_dump(mode="json"),
            "scale_pos_weight": scale_pos_weight,
            "random_state": config.runtime.random_seed,
            "n_jobs": config.runtime.max_cpu_threads,
        },
        numeric_scaling="none",
        scale_pos_weight=scale_pos_weight,
        best_iteration=best_iteration,
    )
    return FittedProbabilityModel(
        feature_columns=config.dataset.feature_columns,
        categorical_columns=categorical,
        numeric_columns=numeric,
        preprocessor=preprocessor,
        estimator=estimator,
        metadata=metadata,
    )


def fit_probability_model(
    config: ExperimentConfig,
    train: FrameSplit,
    validation: FrameSplit,
) -> FittedProbabilityModel:
    """Fit the configured model without leaking validation into preprocessing."""

    _validate_binary_target(train.target, split_name="train")
    _validate_binary_target(validation.target, split_name="validation")
    model_config = config.model
    if isinstance(model_config, LogisticRegressionConfig):
        return _fit_logistic_regression(
            config=config,
            model_config=model_config,
            train=train,
        )
    if isinstance(model_config, XGBoostConfig):
        return _fit_xgboost(
            config=config,
            model_config=model_config,
            train=train,
            validation=validation,
        )
    raise ModelingError(f"unsupported model config: {type(model_config).__name__}")
