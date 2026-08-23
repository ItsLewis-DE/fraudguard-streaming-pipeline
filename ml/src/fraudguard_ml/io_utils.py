"""Atomic I/O and deterministic JSON hashing utilities."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from fraudguard_ml.artifacts import ArtifactError


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
