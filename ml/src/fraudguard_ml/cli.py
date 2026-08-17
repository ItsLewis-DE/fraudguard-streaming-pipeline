"""Command-line entry points for validating the FraudGuard ML environment.

Flow:
    * ``smoke`` loads strict runtime configuration, applies reproducibility
      settings, inspects available hardware, and prints a readiness report.
    * ``validate-training-data`` loads the data contract, queries ClickHouse,
      builds a provenance-rich artifact, and writes it atomically.
    * ``main`` translates expected domain/configuration failures into concise,
      credential-safe CLI errors and non-zero exit codes.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

from clickhouse_connect.driver.exceptions import ClickHouseError
from pydantic import ValidationError

from fraudguard_ml.artifacts import (
    ArtifactError,
    build_artifact,
    write_json_immutable,
)
from fraudguard_ml.clickhouse import ClickHouseSettings, create_clickhouse_client
from fraudguard_ml.config import SmokeConfig, load_yaml_config
from fraudguard_ml.experiment_config import ExperimentConfig
from fraudguard_ml.reproducibility import configure_thread_limits, seed_everything
from fraudguard_ml.runtime import GpuRequiredError, collect_runtime_metadata
from fraudguard_ml.training_data_contract import (
    DataContractError,
    TrainingDataContractConfig,
    validate_training_data_contract,
)

class MLCommandError(RuntimeError):
    """A safe domain error that can be printed without exposing credentials."""

    def __init__(self, category: str, message: str) -> None:
        super().__init__(message)
        self.category = category

        
def build_parser() -> argparse.ArgumentParser:
    """Define the public CLI commands and their typed arguments."""

    parser = argparse.ArgumentParser(prog="fraudguard")
    subparsers = parser.add_subparsers(dest="command", required=True)

    smoke = subparsers.add_parser(
        "smoke",
        help="Validate package, config, seed and local runtime.",
    )
    smoke.add_argument(
        "--config",
        type=Path,
        required=True,
    )
    smoke.add_argument(
        "--json",
        action="store_true",  # Gán giá trị cho nó là True
        dest="json_output",
    )
    validate = subparsers.add_parser("validate-training-data")
    validate.add_argument("--config", type=Path, required=True)
    validate.add_argument("--dbt-manifest", type=Path, required=True)
    validate.add_argument("--repository-root", type=Path, default=Path.cwd())
    validate.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/ml/training_data_contract.json"),
    )

    snapshot = subparsers.add_parser("snapshot-training-dataset")
    snapshot.add_argument("--config", type=Path, required=True)
    snapshot.add_argument("--contract-artifact", type=Path, required=True)
    snapshot.add_argument("--repository-root", type=Path, default=Path.cwd())
    snapshot.add_argument("--dbt-manifest", type=Path, required=True)
    snapshot.add_argument("--run-id", required=True)
    snapshot.add_argument("--output", type=Path, required=True)

    diagnostics = subparsers.add_parser("diagnose-training-splits")
    diagnostics.add_argument("--config", type=Path, required=True)
    diagnostics.add_argument("--dataset-manifest", type=Path, required=True)
    diagnostics.add_argument("--cache-dir", type=Path, required=True)
    diagnostics.add_argument("--output", type=Path, required=True)

    train = subparsers.add_parser("train")
    train.add_argument("--config", type=Path, required=True)
    train.add_argument("--dataset-manifest", type=Path, required=True)
    train.add_argument("--cache-dir", type=Path, required=True)
    train.add_argument("--output", type=Path, required=True)

    evaluate = subparsers.add_parser("evaluate")
    evaluate.add_argument("--config", type=Path, required=True)
    evaluate.add_argument("--dataset-manifest", type=Path, required=True)
    evaluate.add_argument("--cache-dir", type=Path, required=True)
    evaluate.add_argument("--model", type=Path, required=True)
    evaluate.add_argument("--output", type=Path, required=True)
    return parser

def configure_experiment_runtime(config: ExperimentConfig) -> dict[str, Any]:
    """Apply reproducibility settings and validate runtime requirements."""

    configure_thread_limits(config.runtime.max_cpu_threads)
    seed_status = seed_everything(config.runtime.random_seed)
    runtime = collect_runtime_metadata(config.runtime)
    return {
        "seed_status": seed_status,
        "runtime": runtime.model_dump(mode="json"),
    }

def run_validate_training_data(config_path: Path,
    output_path: Path,
    repository_root: Path) -> int:
    """Validate ClickHouse training data and persist its contract artifact.

    The database client is always closed. The returned report is wrapped by
    :func:`build_artifact`, which adds ``status``, hashes, and Git provenance.
    """

    config = load_yaml_config(config_path, TrainingDataContractConfig)
    client = create_clickhouse_client(ClickHouseSettings.from_env())
    try:
        report = validate_training_data_contract(client, config)
    finally:
        client.close()

    report_dict = asdict(report)
    artifact = build_artifact(
        report=report_dict,
        repository_root=repository_root,
        contract_path=config_path,
        lock_path=repository_root / "uv.lock",
        relevant_paths=[repository_root / "ml" / "src"],
    )

    write_json_immutable(output_path, artifact)
    print(f"\nReport successfully saved to: {output_path}")
    return 0


def run_smoke(config_path: Path, json_output: bool) -> int:
    """Check configuration, deterministic seeding, and local compute resources."""

    config = load_yaml_config(config_path, SmokeConfig)
    configure_thread_limits(config.runtime.max_cpu_threads)
    seed_status = seed_everything(config.runtime.random_seed)
    runtime = collect_runtime_metadata(config.runtime)

    result = {
        "status": "ok bro",
        "config": config.model_dump(mode="json"),
        "seed_status": seed_status,
        "runtime": runtime.model_dump(mode="json"),
    }
    if json_output:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(
            "FraudGuard smoke check passed: "
            f"cpus={runtime.cpu_available_count}, "
            f"gpu={runtime.gpu_available}, "
            f"seed={runtime.random_seed}"
        )
    return 0

def load_snapshot_context(
    config_path: Path,
    manifest_path: Path,
    cache_dir: Path,
) -> tuple[ExperimentConfig, Any, Any]:
    """Load config, download the trusted snapshot and derive temporal splits."""

    config = load_yaml_config(config_path, ExperimentConfig)
    configure_experiment_runtime(config)

    # Lazy imports keep NumPy/PyArrow loading after runtime configuration.
    from fraudguard_ml.dataset_loader import (
        load_dataset_splits,
        materialize_snapshot,
    )
    from fraudguard_ml.dataset_manifest import ManifestError, load_manifest
    from fraudguard_ml.object_storage import (
        ObjectStorageSettings,
        create_s3_client,
    )

    try:
        manifest = load_manifest(manifest_path)
        s3_client = create_s3_client(ObjectStorageSettings.from_env())
        try:
            snapshot_path = materialize_snapshot(
                s3_client=s3_client,
                manifest=manifest,
                cache_dir=cache_dir,
            )
        finally:
            s3_client.close()

        splits = load_dataset_splits(
            snapshot_path=snapshot_path,
            manifest=manifest,
            config=config,
        )
    except ManifestError as exc:
        raise MLCommandError("manifest", str(exc)) from exc

    return config, manifest, splits

def run_snapshot_training_dataset(args: argparse.Namespace) -> int:
    """Create a snapshot and its manifest, then publish them to object storage."""

    config = load_yaml_config(args.config, ExperimentConfig)
    configure_experiment_runtime(config)

    from fraudguard_ml.dataset_snapshot import (
        SnapshotError,
        create_snapshot_and_manifest,
    )
    from fraudguard_ml.object_storage import (
        ObjectStorageSettings,
        create_s3_client,
    )

    clickhouse = create_clickhouse_client(ClickHouseSettings.from_env())
    try:
        s3_client = create_s3_client(ObjectStorageSettings.from_env())
        try:
            try:
                manifest = create_snapshot_and_manifest(
                    client=clickhouse,
                    s3_client=s3_client,
                    config=config,
                    config_path=args.config.resolve(),
                    contract_artifact_path=args.contract_artifact.resolve(),
                    dbt_manifest_path=args.dbt_manifest.resolve(),
                    repository_root=args.repository_root.resolve(),
                    run_id=args.run_id,
                    output_dir=args.output,
                )
            except SnapshotError as exc:
                raise MLCommandError("snapshot", str(exc)) from exc
        finally:
            s3_client.close()
    finally:
        clickhouse.close()

    print(json.dumps(manifest.model_dump(mode="json"), sort_keys=True))
    return 0

def run_train(args: argparse.Namespace) -> int:
    """Train a model and persist its immutable model bundle and metrics."""

    config, manifest, splits = load_snapshot_context(
        args.config,
        args.dataset_manifest,
        args.cache_dir,
    )

    from fraudguard_ml.training import TrainingError, train_and_select_threshold

    try:
        result = train_and_select_threshold(
            splits=splits,
            config=config,
            manifest=manifest,
            manifest_path=args.dataset_manifest,
            output_dir=args.output,
        )
    except TrainingError as exc:
        raise MLCommandError("training", str(exc)) from exc

    print(json.dumps(result, sort_keys=True))
    return 0

def run_evaluate(args: argparse.Namespace) -> int:
    """Evaluate the frozen model and threshold against the test split."""

    config, manifest, splits = load_snapshot_context(
        args.config,
        args.dataset_manifest,
        args.cache_dir,
    )

    from fraudguard_ml.dataset_manifest import ManifestError
    from fraudguard_ml.evaluation import evaluate_test_split

    try:
        result = evaluate_test_split(
            test=splits.test,
            config=config,
            manifest=manifest,
            manifest_path=args.dataset_manifest,
            model_path=args.model,
            output_path=args.output,
        )
    except ManifestError as exc:
        raise MLCommandError("manifest", str(exc)) from exc

    print(json.dumps(result, sort_keys=True))
    return 0


def run_split_diagnostics(args: argparse.Namespace) -> int:
    """Write diagnostics without turning diagnostic values into a quality gate."""

    config, _, splits = load_snapshot_context(
        args.config,
        args.dataset_manifest,
        args.cache_dir,
    )

    from fraudguard_ml.split_diagnostics import (
        build_split_diagnostics,
        write_diagnostics,
    )
    from fraudguard_ml.training import feature_groups

    categorical, numeric = feature_groups(config)
    report = build_split_diagnostics(
        splits,
        numeric_columns=tuple(numeric),
        categorical_columns=tuple(categorical),
    )
    write_diagnostics(args.output, report)
    print(args.output)
    return 0

def dispatch(args: argparse.Namespace) -> int:
    """Dispatch one already-parsed command."""

    if args.command == "smoke":
        return run_smoke(args.config, args.json_output)
    if args.command == "validate-training-data":
        return run_validate_training_data(
            args.config,
            args.dbt_manifest,
            args.repository_root,
            args.output,
        )
    if args.command == "snapshot-training-dataset":
        return run_snapshot_training_dataset(args)
    if args.command == "diagnose-training-splits":
        return run_split_diagnostics(args)
    if args.command == "train":
        return run_train(args)
    if args.command == "evaluate":
        return run_evaluate(args)
    raise ValueError(f"unsupported command: {args.command}")

def main(argv: Sequence[str] | None = None) -> None:
    """Parse, dispatch and map expected failures to stable exit code 2."""

    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        exit_code = dispatch(args)
    except MLCommandError as exc:
        parser.exit(2, f"{exc.category} error: {exc}\n")
    except (OSError, ValueError, ValidationError, GpuRequiredError) as exc:
        parser.exit(2, f"configuration error: {exc}\n")
    except ArtifactError as exc:
        parser.exit(2, f"artifact error: {exc}\n")
    except DataContractError as exc:
        parser.exit(2, f"contract error: {exc}\n")
    except ClickHouseError:
        parser.exit(2, "ClickHouse request failed\n")
    raise SystemExit(exit_code)