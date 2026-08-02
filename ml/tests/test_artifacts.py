from __future__ import annotations

import json
from pathlib import Path

import pytest

from fraudguard_ml.artifacts import ArtifactError, write_json_atomic


def test_atomic_writer_replaces_complete_json(tmp_path: Path) -> None:
    output = tmp_path / "contract.json"
    output.write_text('{"old": true}\n', encoding="utf-8")

    write_json_atomic(output, {"status": "validated"})

    assert json.loads(output.read_text(encoding="utf-8")) == {"status": "validated"}
    assert list(tmp_path.glob(".*.tmp")) == []


def test_atomic_writer_keeps_no_temporary_file_on_failure(
    monkeypatch: pytest.MonkeyPatch,  # Dùng để đánh tráo rồi sau đó tráo trở lại
    tmp_path: Path,
) -> None:
    output = tmp_path / "contract.json"

    def fail_replace(source: str | Path, destination: str | Path) -> None:
        raise OSError("simulated")

    monkeypatch.setattr("fraudguard_ml.artifacts.os.replace", fail_replace)

    with pytest.raises(ArtifactError, match="atomically"):
        write_json_atomic(output, {"status": "validated"})

    assert not output.exists()
    assert list(tmp_path.glob(".*.tmp")) == []
