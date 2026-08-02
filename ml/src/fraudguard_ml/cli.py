from __future__ import annotations

import argparse
import json
from collections.abc import Sequence  # Giống với list nhưng read-only
from dataclasses import asdict
from pathlib import Path

from clickhouse_connect.driver.exceptions import ClickHouseError
from pydantic import ValidationError

from fraudguard_ml.clickhouse import (
    ClickHouseSettings,
    create_clickhouse_client,
)
from fraudguard_ml.config import SmokeConfig, load_yaml_config
from fraudguard_ml.reproducibility import configure_thread_limits, seed_everything
from fraudguard_ml.runtime import collect_runtime_metadata
from fraudguard_ml.training_data_contract import (
    DataContractError,
    TrainingDataContractConfig,
    validate_training_data_contract,
)


def build_parser() -> argparse.ArgumentParser:
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
    return parser


def run_validate_training_data(config_path: Path) -> int:
    config = load_yaml_config(config_path, TrainingDataContractConfig)
    client = create_clickhouse_client(ClickHouseSettings.from_env())
    try:
        report = validate_training_data_contract(client, config)
    finally:
        client.close()
    print(json.dumps(asdict(report), indent=2, sort_keys=True))
    return 0


def run_smoke(config_path: Path, json_output: bool) -> int:
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


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "smoke":
            exit_code = run_smoke(args.config, args.json_output)
        elif args.command == "validate-training-data":
            exit_code = run_validate_training_data(args.config)
        else:
            parser.error(f"Unknown command: {args.command}")
    except (OSError, ValueError, ValidationError) as exc:
        parser.exit(2, f"configuration error: {exc}\n")
    except DataContractError as exc:
        parser.exit(2, f"contract error: {exc}\n")
    except ClickHouseError:
        parser.exit(2, "ClickHouse validation request failed\n")
    raise SystemExit(exit_code)  # Để báo cho hệ điều hành chương trình có lỗi hay k
