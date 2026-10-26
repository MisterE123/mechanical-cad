"""Materialize exact historical guard inputs, never current runtime qualification.

Only inert, hash-pinned functional source and test fixtures are copied. Current
production modules and the live boundary tests continue using the real checkout.
"""

import hashlib
import json
import tempfile
from pathlib import Path, PurePosixPath

REPOSITORY = Path(__file__).resolve().parents[2]
FIXTURE = REPOSITORY / "tests/fixtures/historical_runtime_db8cac4"
SOURCE_COMMIT = "db8cac466c8b7dad3a17d2107b66128180be395e"
MANIFEST_SHA256 = "fc9a6516fc3e5ad6a358c0c037f8740fa8d9685ba1efc17487897a87f5a2a301"
_SNAPSHOT = None


def _safe_path(value):
    assert isinstance(value, str) and value
    path = PurePosixPath(value)
    assert not path.is_absolute() and path.as_posix() == value
    assert not set(path.parts) & {".", ".."}
    assert "\\" not in value and ":" not in value
    return path


def verified_files(*, fixture=FIXTURE, repository=REPOSITORY):
    """Verify the complete sealed membership and all bytes before materialization."""
    raw = (fixture / "manifest.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == MANIFEST_SHA256
    manifest = json.loads(raw)
    assert set(manifest) == {"schema", "source_commit", "files"}
    assert manifest["schema"] == "historical-runtime-source-v1"
    assert manifest["source_commit"] == SOURCE_COMMIT
    assert type(manifest["files"]) is list and len(manifest["files"]) == 408
    answer, expected_objects = {}, set()
    for row in manifest["files"]:
        kind = "object" if "object" in row else "repository_fixture"
        assert set(row) == {"path", "bytes", "sha256", kind}
        name = _safe_path(row["path"]).as_posix()
        assert name not in answer
        assert type(row["bytes"]) is int and row["bytes"] > 0
        assert isinstance(row["sha256"], str) and len(row["sha256"]) == 64
        if kind == "object":
            assert row[kind] == row["sha256"] + ".txt"
            expected_objects.add(row[kind])
            path = fixture / "objects" / row[kind]
        else:
            relative = _safe_path(row[kind]).as_posix()
            assert relative.startswith("tests/fixtures/") or relative == (
                "docs/architecture/arc_profile_service/BASELINE.json"
            )
            path = repository / relative
        assert not path.is_symlink() and path.is_file()
        content = path.read_bytes()
        assert len(content) == row["bytes"]
        assert hashlib.sha256(content).hexdigest() == row["sha256"]
        answer[name] = content
    assert {path.name for path in (fixture / "objects").iterdir()} == expected_objects
    return answer


def historical_runtime_root():
    """One disposable source snapshot used only by historical inverse helpers."""
    global _SNAPSHOT
    if _SNAPSHOT is None:
        files = verified_files()
        temporary = tempfile.TemporaryDirectory(prefix="mcad-historical-source-")
        root = Path(temporary.name)
        try:
            for name, content in files.items():
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
        except BaseException:
            temporary.cleanup()
            raise
        _SNAPSHOT = temporary
    return Path(_SNAPSHOT.name)
