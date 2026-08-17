# Hoàn thiện FraudGuard ML CLI

Tài liệu này mô tả các thay đổi còn thiếu để CLI chạy được toàn bộ workflow:

```text
validate-training-data
        |
        v
snapshot-training-dataset
        |
        v
diagnose-training-splits
        |
        v
train
        |
        v
evaluate
```

## Phạm vi theo yêu cầu hiện tại

Hai kiểm tra sau **không được thêm vào implementation**:

- Không thêm hoặc gọi `assert_diagnostic_invariants()`. Command diagnostics chỉ tạo
  báo cáo để người dùng đọc, không dùng báo cáo đó làm quality gate.
- Không thêm `verify_split_statistics()` và không kiểm tra row count, fraud count,
  duplicate key hoặc key overlap giữa các split trong `load_dataset_splits()`.

Việc không có hai nhóm kiểm tra này là chủ ý của dự án, không phải phần còn thiếu.

## 1. Những lỗi cần sửa

### 1.1. Parser có command nhưng `main()` chưa dispatch

`build_parser()` đã khai báo `snapshot-training-dataset`,
`diagnose-training-splits`, `train` và `evaluate`, nhưng `main()` mới chạy được
`smoke` và `validate-training-data`.

### 1.2. `run_validate_training_data()` đang được gọi thiếu tham số

Hàm hiện nhận `repository_root`, nhưng `main()` chỉ truyền `config` và `output`.
Lỗi này tạo `TypeError` trước khi quá trình validation bắt đầu.

### 1.3. Các hàm CLI đang dùng tên chưa import

Các tên như `ExperimentConfig`, `load_manifest`, `create_s3_client`,
`train_and_select_threshold` và `evaluate_test_split` chưa được import. Nên dùng
lazy import cho các thư viện ML nặng để cấu hình thread được áp dụng trước khi
NumPy, SciPy hoặc scikit-learn được import.

### 1.4. Thiếu dbt manifest provenance

`DatasetManifest` bắt buộc trường `dbt_manifest_sha256`. Vì vậy cả validation và
snapshot phải nhận `--dbt-manifest`, hash file này và ghi hash vào artifact tương
ứng. Không nên xóa trường này khỏi `DatasetManifest`, vì nó chứng minh snapshot
được tạo từ đúng lần build dbt nào.

### 1.5. Thiếu mapping lỗi domain sang exit code

Các lỗi `ManifestError`, `SnapshotError`, `TrainingError` và `GpuRequiredError`
cần được đổi thành thông báo CLI ngắn gọn với exit code `2`, thay vì in traceback.

### 1.6. Thiếu dependency trực tiếp và test CLI

Package đang import boto3, joblib, NumPy, PyArrow, scikit-learn và SciPy nhưng
chưa khai báo trực tiếp các package này trong `pyproject.toml`.

## 2. Sửa `artifacts.py`

Thêm `dbt_manifest_path` vào `build_artifact()` và ghi SHA-256 của dbt manifest.
Phần còn lại của file giữ nguyên.

```python
def build_artifact(
    *,
    report: Mapping[str, Any],
    repository_root: Path,
    contract_path: Path,
    lock_path: Path,
    dbt_manifest_path: Path,
    relevant_paths: Sequence[Path],
) -> dict[str, Any]:
    """Combine a successful validation report with content and Git provenance."""

    git = collect_git_provenance(repository_root, relevant_paths)
    return {
        "artifact_schema_version": 1,
        "status": "validated",
        "validation": dict(report),
        "provenance": {
            **git,
            "sha256": {
                "contract": sha256_file(contract_path),
                "lockfile": sha256_file(lock_path),
                "dbt_manifest": sha256_file(dbt_manifest_path),
            },
            "dbt_selection": "+tag:training",
        },
    }
```

Ý nghĩa các hash:

- `contract`: data contract đã dùng để validation.
- `lockfile`: phiên bản dependency của code chạy validation.
- `dbt_manifest`: graph/model metadata chính xác của lần dbt build.

## 3. Sửa `dataset_snapshot.py`

Khôi phục tham số `dbt_manifest_path` và truyền hash vào `DatasetManifest`.

```python
def create_snapshot_and_manifest(
    *,
    client: Any,
    s3_client: BaseClient,
    config: ExperimentConfig,
    config_path: Path,
    contract_artifact_path: Path,
    dbt_manifest_path: Path,
    repository_root: Path,
    run_id: str,
    output_dir: Path,
    now_utc: datetime | None = None,
) -> DatasetManifest:
    validate_contract_artifact(contract_artifact_path, config.dataset.relation)
    output_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = output_dir / "data.parquet"
    manifest_path = output_dir / "dataset_manifest.json"

    total, split, population_fingerprint, query_hash = stream_snapshot(
        client,
        config,
        parquet_path,
    )

    snapshot_uri = join_s3_uri(
        config.snapshot.storage_uri,
        config.experiment_name,
        run_id,
        "data.parquet",
    )
    snapshot_sha256 = upload_file_immutable(
        s3_client,
        parquet_path,
        snapshot_uri,
    )

    manifest = DatasetManifest(
        manifest_schema_version=1,
        experiment_name=config.experiment_name,
        run_id=run_id,
        created_at_utc=(now_utc or datetime.now(UTC)).astimezone(UTC).isoformat(),
        source_relation=config.dataset.relation,
        snapshot_uri=snapshot_uri,
        snapshot_format="parquet",
        snapshot_sha256=snapshot_sha256,
        data_fingerprint=f"sha256:{snapshot_sha256}",
        snapshot_size_bytes=parquet_path.stat().st_size,
        label_policy=config.snapshot.label_policy,
        row_count=total.row_count,
        fraud_count=total.fraud_count,
        fraud_rate=total.fraud_rate,
        min_event_time=total.min_event_time or "",
        max_event_time=total.max_event_time or "",
        split=SplitBoundaries(
            strategy="temporal",
            train_end=config.split.train_end,
            validation_end=config.split.validation_end,
            test_end=config.split.test_end,
        ),
        feature_list=config.dataset.feature_columns,
        target_column=config.dataset.target_column,
        dbt_manifest_sha256=sha256_file(dbt_manifest_path),
        training_config_sha256=sha256_file(config_path),
        population_query_sha256=query_hash,
        population_fingerprint=population_fingerprint,
        fingerprint_algorithm=config.snapshot.fingerprint_algorithm,
        quality_status="passed",
        contract_artifact_sha256=sha256_file(contract_artifact_path),
        git_sha=git_output(repository_root, ["rev-parse", "HEAD"]),
        split_statistics=split,
    )

    write_json_immutable(manifest_path, manifest.model_dump(mode="json"))

    manifest_uri = join_s3_uri(
        config.snapshot.storage_uri,
        config.experiment_name,
        run_id,
        "dataset_manifest.json",
    )
    upload_file_immutable(s3_client, manifest_path, manifest_uri)

    contract_uri = join_s3_uri(
        config.snapshot.storage_uri,
        config.experiment_name,
        run_id,
        "training_data_contract.json",
    )
    upload_file_immutable(s3_client, contract_artifact_path, contract_uri)
    return manifest
```

Điểm quan trọng là file dbt manifest chỉ được hash; nó không cần được load toàn bộ
vào RAM và không cần được upload cùng snapshot ở phase này.

## 4. Thay nội dung `cli.py`

Implementation dưới đây có các đặc điểm:

- Dispatch đủ sáu command.
- Truyền đúng toàn bộ argument.
- Giữ thông báo lỗi ngắn gọn và không in credential.
- Đóng ClickHouse và S3 client bằng `finally`.
- Áp dụng seed/thread/runtime config trước khi lazy-import module ML nặng.
- Diagnostics chỉ ghi report; không có quality gate.
- Loader giữ nguyên hành vi hiện tại; không kiểm tra thống kê/key giữa các split.

```python
"""Command-line entry points for the FraudGuard ML workflow."""

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
    """Define all public CLI commands and their typed arguments."""

    parser = argparse.ArgumentParser(prog="fraudguard")
    subparsers = parser.add_subparsers(dest="command", required=True)

    smoke = subparsers.add_parser(
        "smoke",
        help="Validate package, config, seed and local runtime.",
    )
    smoke.add_argument("--config", type=Path, required=True)
    smoke.add_argument("--json", action="store_true", dest="json_output")

    validate = subparsers.add_parser(
        "validate-training-data",
        help="Validate the ClickHouse training relation and save provenance.",
    )
    validate.add_argument("--config", type=Path, required=True)
    validate.add_argument("--dbt-manifest", type=Path, required=True)
    validate.add_argument("--repository-root", type=Path, default=Path.cwd())
    validate.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/ml/training_data_contract.json"),
    )

    snapshot = subparsers.add_parser(
        "snapshot-training-dataset",
        help="Create and publish an immutable training snapshot.",
    )
    snapshot.add_argument("--config", type=Path, required=True)
    snapshot.add_argument("--contract-artifact", type=Path, required=True)
    snapshot.add_argument("--dbt-manifest", type=Path, required=True)
    snapshot.add_argument("--repository-root", type=Path, default=Path.cwd())
    snapshot.add_argument("--run-id", required=True)
    snapshot.add_argument("--output", type=Path, required=True)

    diagnostics = subparsers.add_parser(
        "diagnose-training-splits",
        help="Write descriptive split and drift diagnostics.",
    )
    diagnostics.add_argument("--config", type=Path, required=True)
    diagnostics.add_argument("--dataset-manifest", type=Path, required=True)
    diagnostics.add_argument("--cache-dir", type=Path, required=True)
    diagnostics.add_argument("--output", type=Path, required=True)

    train = subparsers.add_parser(
        "train",
        help="Train the configured model and select its threshold.",
    )
    train.add_argument("--config", type=Path, required=True)
    train.add_argument("--dataset-manifest", type=Path, required=True)
    train.add_argument("--cache-dir", type=Path, required=True)
    train.add_argument("--output", type=Path, required=True)

    evaluate = subparsers.add_parser(
        "evaluate",
        help="Evaluate a trained model bundle on the test split.",
    )
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


def run_smoke(config_path: Path, json_output: bool) -> int:
    """Check configuration, deterministic seeding and compute resources."""

    config = load_yaml_config(config_path, SmokeConfig)
    configure_thread_limits(config.runtime.max_cpu_threads)
    seed_status = seed_everything(config.runtime.random_seed)
    runtime = collect_runtime_metadata(config.runtime)
    result = {
        "status": "ok",
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


def run_validate_training_data(
    config_path: Path,
    dbt_manifest_path: Path,
    repository_root: Path,
    output_path: Path,
) -> int:
    """Validate training data and persist an immutable contract artifact."""

    repository_root = repository_root.resolve()
    config_path = config_path.resolve()
    dbt_manifest_path = dbt_manifest_path.resolve()
    config = load_yaml_config(config_path, TrainingDataContractConfig)
    client = create_clickhouse_client(ClickHouseSettings.from_env())
    try:
        report = validate_training_data_contract(client, config)
    finally:
        client.close()

    artifact = build_artifact(
        report=asdict(report),
        repository_root=repository_root,
        contract_path=config_path,
        lock_path=repository_root / "uv.lock",
        dbt_manifest_path=dbt_manifest_path,
        relevant_paths=[
            repository_root / "ml" / "src",
            config_path,
        ],
    )
    write_json_immutable(output_path, artifact)
    print(output_path)
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
```

### Vì sao dùng `Any` trong `load_snapshot_context()`?

`DatasetManifest` và `DatasetSplits` nằm trong các module được lazy-import. Dùng
`Any` ở đây tránh import NumPy/Pandas/PyArrow trước khi cấu hình thread. Nếu muốn
type checking chặt hơn, dùng `TYPE_CHECKING`:

```python
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fraudguard_ml.dataset_loader import DatasetSplits
    from fraudguard_ml.dataset_manifest import DatasetManifest


def load_snapshot_context(
    config_path: Path,
    manifest_path: Path,
    cache_dir: Path,
) -> tuple[ExperimentConfig, DatasetManifest, DatasetSplits]:
    ...
```

Do file đã có `from __future__ import annotations`, cách dùng `TYPE_CHECKING` là
lựa chọn nên áp dụng khi chạy mypy strict.

## 5. Giữ nguyên `dataset_loader.py`

Theo phạm vi đã thống nhất, `load_dataset_splits()` chỉ cần:

1. Đối chiếu cấu hình cơ bản bằng `verify_manifest_config()`.
2. Tạo ba temporal filter.
3. Đọc và trả về `DatasetSplits`.

Không thêm bất kỳ lời gọi nào tới `verify_split_statistics()`:

```python
def load_dataset_splits(
    *,
    snapshot_path: Path,
    manifest: DatasetManifest,
    config: ExperimentConfig,
) -> DatasetSplits:
    verify_manifest_config(manifest, config)
    train_end = parse_utc(manifest.split.train_end)
    validation_end = parse_utc(manifest.split.validation_end)
    test_end = parse_utc(manifest.split.test_end)

    train = read_one_split(
        snapshot_path=snapshot_path,
        config=config,
        filters=[("event_time", "<=", train_end)],
    )
    validation = read_one_split(
        snapshot_path=snapshot_path,
        config=config,
        filters=[
            ("event_time", ">", train_end),
            ("event_time", "<=", validation_end),
        ],
    )
    test = read_one_split(
        snapshot_path=snapshot_path,
        config=config,
        filters=[
            ("event_time", ">", validation_end),
            ("event_time", "<=", test_end),
        ],
    )
    return DatasetSplits(train=train, validation=validation, test=test)
```

Lưu ý: `read_one_split()` hiện vẫn từ chối split rỗng. Đây là điều kiện kỹ thuật
để code phía sau có thể train/evaluate, không phải bước đối chiếu thống kê giữa
các split.

## 6. Giữ diagnostics ở chế độ báo cáo

Không thêm `assert_diagnostic_invariants()` vào `split_diagnostics.py`. Hàm cuối
file tiếp tục chỉ ghi JSON immutable:

```python
def write_diagnostics(path: Path, report: dict[str, Any]) -> None:
    write_json_immutable(path, report)
```

Và trong CLI chỉ có:

```python
report = build_split_diagnostics(
    splits,
    numeric_columns=tuple(numeric),
    categorical_columns=tuple(categorical),
)
write_diagnostics(args.output, report)
```

Như vậy PSI, KS, missing rate và fraud rate là thông tin quan sát, không tự động
làm command thất bại.

## 7. Bổ sung dependency trong `pyproject.toml`

Đổi danh sách `[project].dependencies` thành:

```toml
dependencies = [
    "boto3>=1.40,<2",
    "clickhouse-connect>=1.5.0",
    "confluent-kafka[avro]>=2.15.0",
    "joblib>=1.5,<2",
    "numpy>=2.3,<3",
    "pandas>=3.0.5,<4",
    "psutil>=7,<8",
    "pyarrow>=21,<22",
    "pydantic>=2.12,<3",
    "pyyaml>=6,<7",
    "scikit-learn>=1.7,<2",
    "scipy>=1.16,<2",
    "seaborn>=0.13.2,<1",
]
```

Sau khi sửa, cập nhật lockfile:

```bash
uv lock
uv sync --dev
```

Không nên dựa vào dependency bắc cầu. Ví dụ NumPy có thể đang được cài vì Pandas
hoặc Seaborn, nhưng code dự án import trực tiếp NumPy nên phải khai báo trực tiếp.

## 8. Test CLI cần bổ sung

Tạo `ml/tests/test_cli.py`.

```python
from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from fraudguard_ml import cli


def test_parser_accepts_validate_arguments(tmp_path: Path) -> None:
    args = cli.build_parser().parse_args(
        [
            "validate-training-data",
            "--config",
            str(tmp_path / "contract.yml"),
            "--dbt-manifest",
            str(tmp_path / "manifest.json"),
            "--repository-root",
            str(tmp_path),
            "--output",
            str(tmp_path / "contract.json"),
        ]
    )

    assert args.command == "validate-training-data"
    assert args.dbt_manifest == tmp_path / "manifest.json"
    assert args.repository_root == tmp_path


def test_parser_accepts_snapshot_arguments(tmp_path: Path) -> None:
    args = cli.build_parser().parse_args(
        [
            "snapshot-training-dataset",
            "--config",
            str(tmp_path / "training.yml"),
            "--contract-artifact",
            str(tmp_path / "contract.json"),
            "--dbt-manifest",
            str(tmp_path / "manifest.json"),
            "--run-id",
            "20260817T120000",
            "--output",
            str(tmp_path / "experiment"),
        ]
    )

    assert args.command == "snapshot-training-dataset"
    assert args.run_id == "20260817T120000"
    assert args.dbt_manifest == tmp_path / "manifest.json"


@pytest.mark.parametrize(
    ("command", "runner_name"),
    [
        ("snapshot-training-dataset", "run_snapshot_training_dataset"),
        ("diagnose-training-splits", "run_split_diagnostics"),
        ("train", "run_train"),
        ("evaluate", "run_evaluate"),
    ],
)
def test_dispatch_routes_ml_commands(
    monkeypatch: pytest.MonkeyPatch,
    command: str,
    runner_name: str,
) -> None:
    called: list[argparse.Namespace] = []

    def fake_runner(args: argparse.Namespace) -> int:
        called.append(args)
        return 0

    monkeypatch.setattr(cli, runner_name, fake_runner)
    args = argparse.Namespace(command=command)

    assert cli.dispatch(args) == 0
    assert called == [args]


def test_dispatch_passes_all_validate_arguments(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    received: list[tuple[Path, Path, Path, Path]] = []

    def fake_validate(
        config: Path,
        dbt_manifest: Path,
        repository_root: Path,
        output: Path,
    ) -> int:
        received.append((config, dbt_manifest, repository_root, output))
        return 0

    monkeypatch.setattr(cli, "run_validate_training_data", fake_validate)
    args = argparse.Namespace(
        command="validate-training-data",
        config=tmp_path / "contract.yml",
        dbt_manifest=tmp_path / "manifest.json",
        repository_root=tmp_path,
        output=tmp_path / "contract.json",
    )

    assert cli.dispatch(args) == 0
    assert received == [
        (
            tmp_path / "contract.yml",
            tmp_path / "manifest.json",
            tmp_path,
            tmp_path / "contract.json",
        )
    ]


def test_main_maps_safe_domain_error_to_exit_two(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail(_: argparse.Namespace) -> int:
        raise cli.MLCommandError("training", "cannot select threshold")

    monkeypatch.setattr(cli, "dispatch", fail)

    with pytest.raises(SystemExit) as exc_info:
        cli.main(["smoke", "--config", "unused.yml"])

    assert exc_info.value.code == 2
    assert "training error: cannot select threshold" in capsys.readouterr().err
```

### Test provenance cho `build_artifact()`

Bổ sung một test vào `ml/tests/test_artifacts.py` để chắc chắn dbt manifest được
hash và ghi đúng:

```python
from fraudguard_ml.artifacts import build_artifact, sha256_file


def test_build_artifact_records_dbt_manifest_hash(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    contract = tmp_path / "contract.yml"
    lockfile = tmp_path / "uv.lock"
    dbt_manifest = tmp_path / "manifest.json"
    source = tmp_path / "ml" / "src"
    source.mkdir(parents=True)
    contract.write_text("schema_version: 1\n", encoding="utf-8")
    lockfile.write_text("version = 1\n", encoding="utf-8")
    dbt_manifest.write_text('{"metadata": {}}\n', encoding="utf-8")

    monkeypatch.setattr(
        "fraudguard_ml.artifacts.collect_git_provenance",
        lambda repository_root, relative_paths: {
            "git_sha": "a" * 40,
            "relevant_paths_clean": True,
            "relevant_paths": ["ml/src"],
        },
    )

    artifact = build_artifact(
        report={"relation": "fraudguard_ml.ml_training_transactions"},
        repository_root=tmp_path,
        contract_path=contract,
        lock_path=lockfile,
        dbt_manifest_path=dbt_manifest,
        relevant_paths=[source],
    )

    assert artifact["provenance"]["sha256"]["dbt_manifest"] == sha256_file(
        dbt_manifest
    )
```

### Test snapshot manifest có dbt hash

Trong test của `dataset_snapshot.py`, mock phần stream/upload rồi kiểm tra:

```python
assert manifest.dbt_manifest_sha256 == sha256_file(dbt_manifest_path)
```

Test này quan trọng vì nếu quên truyền field, Pydantic sẽ từ chối toàn bộ manifest.

## 9. Command mẫu sau khi sửa

### Validation

```bash
uv run python -m fraudguard_ml validate-training-data \
  --config configs/training_data_contract.yml \
  --dbt-manifest dbt/target/manifest.json \
  --repository-root . \
  --output artifacts/ml/training_data_contract.json
```

### Snapshot

```bash
uv run python -m fraudguard_ml snapshot-training-dataset \
  --config configs/training_baseline.yml \
  --contract-artifact artifacts/ml/training_data_contract.json \
  --dbt-manifest dbt/target/manifest.json \
  --repository-root . \
  --run-id 20260817T120000 \
  --output artifacts/ml/experiment
```

### Diagnostics không có quality gate

```bash
uv run python -m fraudguard_ml diagnose-training-splits \
  --config configs/training_baseline.yml \
  --dataset-manifest artifacts/ml/experiment/dataset_manifest.json \
  --cache-dir artifacts/ml/cache \
  --output artifacts/ml/experiment/split_diagnostics.json
```

### Training

```bash
uv run python -m fraudguard_ml train \
  --config configs/training_baseline.yml \
  --dataset-manifest artifacts/ml/experiment/dataset_manifest.json \
  --cache-dir artifacts/ml/cache \
  --output artifacts/ml/experiment/model
```

### Evaluation

```bash
uv run python -m fraudguard_ml evaluate \
  --config configs/training_baseline.yml \
  --dataset-manifest artifacts/ml/experiment/dataset_manifest.json \
  --cache-dir artifacts/ml/cache \
  --model artifacts/ml/experiment/model/model_bundle.joblib \
  --output artifacts/ml/experiment/evaluation.json
```

## 10. Checklist triển khai

Thứ tự sửa nên là:

1. Khôi phục `dbt_manifest_path` trong `artifacts.py`.
2. Khôi phục `dbt_manifest_path` và `dbt_manifest_sha256` trong
   `dataset_snapshot.py`.
3. Thay `cli.py` bằng implementation đầy đủ ở trên.
4. Thêm dependency trực tiếp và cập nhật `uv.lock`.
5. Thêm test parser, dispatch, error mapping và provenance.
6. Chạy formatter, linter, type checker và test.

```bash
uv run ruff format ml/src/fraudguard_ml ml/tests
uv run ruff check ml/src/fraudguard_ml ml/tests
uv run mypy
uv run pytest
```

Acceptance criteria:

- `fraudguard --help` hiển thị đủ sáu command.
- Mỗi command được dispatch tới đúng runner.
- Validation và snapshot đều bắt buộc `--dbt-manifest`.
- Contract artifact và dataset manifest chứa cùng dbt manifest SHA-256.
- Snapshot manifest khởi tạo thành công, không thiếu field Pydantic.
- ClickHouse và S3 client luôn được đóng kể cả khi command lỗi.
- Lỗi dự kiến trả exit code `2` và không in credential.
- Diagnostics luôn ghi report nếu việc tính report thành công, không áp dụng quality
  gate.
- Loader không thực hiện kiểm tra thống kê, duplicate hoặc overlap giữa các split.
- Ruff, mypy và pytest đều pass.
