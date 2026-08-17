"""Build trustworthy, reproducible metadata artifacts for ML pipeline runs.

Flow:
    1. Hash every input that materially affects the run.
    2. Verify that the relevant Git paths are committed and unchanged.
    3. Wrap validation results with provenance and a stable schema version.
    4. Persist JSON atomically, or immutably when overwriting is forbidden.

The functions in this module deliberately fail closed: incomplete provenance or
an interrupted write must never look like a valid artifact.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


class ArtifactError(RuntimeError):
    """Raised when an artifact cannot be proven reproducible or written safely."""


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of a file without loading it fully into memory."""

    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)  # Nạp chunnk vào digest để nó băm
    except OSError as exc:
        raise ArtifactError(f"cannot hash required file: {path}") from exc
    return digest.hexdigest()  # Chốt lại và trả về một chuỗi kí tự


def git_output(root: Path, arguments: Sequence[str]) -> str:
    """Run a read-only Git command and return its trimmed standard output."""

    try:
        completed = subprocess.run(
            ["git", *arguments],
            cwd=root,
            check=True,  # Dừng khi lỗi
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ArtifactError("cannot inspect Git provenance") from exc
    return completed.stdout.strip()


def collect_git_provenance(
    repository_root: Path, relative_paths: Sequence[Path]
) -> dict[str, Any]:
    """Capture the commit SHA after proving that relevant paths are clean.

    A dirty source or configuration path makes the run ambiguous, so this
    function raises :class:`ArtifactError` instead of recording weak provenance.
    """

    str_paths = [str(path.relative_to(repository_root)) for path in relative_paths]
    status = git_output(
        repository_root, arguments=["status", "--porcelain", "--", *str_paths]
    )
    if status:
        raise ArtifactError("relevant source/config paths must be committed and clean")
    return {
        "git_sha": git_output(repository_root, ["rev-parse", "HEAD"]),
        "relevant_paths_clean": True,
        "relevant_paths": sorted(str_paths),
    }


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


def write_json_atomic(destination: Path, payload: Mapping[str, Any]) -> None:
    """Write complete JSON via a temporary file and an atomic replacement.

    ``fsync`` ensures bytes reach the filesystem before ``os.replace`` exposes
    the new file, preventing readers from observing a partially written artifact.
    """

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=destination.parent,
            prefix=f".{destination.name}",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary_path = Path(stream.name)
            json.dump(payload, stream, indent=2, sort_keys=True, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, destination)
        temporary_path = None
    except OSError as exc:
        raise ArtifactError(f"cannot atomically write artifact: {destination}") from exc
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def write_json_immutable(destination: Path, payload: Mapping[str, Any]) -> None:
    """Write JSON once, rejecting any attempt to overwrite an existing artifact."""

    if destination.exists():
        raise ArtifactError(f"refusing to overwrite immutable artifact: {destination}")
    write_json_atomic(destination, payload)


def canonical_json_sha256(payload: Mapping[str, Any]) -> str:
    """Hash a mapping using deterministic JSON ordering and separators."""

    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
