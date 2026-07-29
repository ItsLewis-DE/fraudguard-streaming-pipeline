from __future__ import annotations

import argparse
import json
from collections.abc import Sequence  # Giống với list nhưng read-only
from pathlib import Path

from pydantic import ValidationError

from fraudguard_ml.config import SmokeConfig, load_yaml_config
from fraudguard_ml.reproducibility import configure_thread_limits, seed_everything
from fraudguard_ml.runtime import collect_runtime_metadata


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
    return parser


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
        else:
            parser.error(f"Unknown command: {args.command}")
    except (OSError, ValueError, ValidationError) as exc:
        parser.exit(2, f"configuration error: {exc}\n")

    raise SystemExit(exit_code)  # Để báo cho hệ điều hành chương trình có lỗi hay k
