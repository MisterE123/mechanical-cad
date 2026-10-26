"""Pinned historical data never replaces current-source runtime admission."""

import json
import shutil
from pathlib import Path

import historical_runtime_source as historical
import pytest


def test_historical_snapshot_retains_original_protected_digest():
    from test_arc_profile_native_end_cap import SNAPSHOT3_PYTHON_PROTECTED, protected_python_digest

    root = historical.historical_runtime_root()
    assert root != historical.REPOSITORY
    assert protected_python_digest(root) == SNAPSHOT3_PYTHON_PROTECTED
    assert len(historical.verified_files()) == 408


@pytest.mark.parametrize("mutation", ("manifest", "member", "missing", "corrupt", "unexpected"))
def test_historical_snapshot_rejects_tampering_before_use(tmp_path, mutation):
    fixture = tmp_path / "fixture"
    shutil.copytree(historical.FIXTURE, fixture)
    manifest = fixture / "manifest.json"
    if mutation == "manifest":
        manifest.write_bytes(manifest.read_bytes() + b"\n")
    elif mutation == "member":
        data = json.loads(manifest.read_bytes())
        data["files"].append(data["files"][0])
        manifest.write_text(json.dumps(data))
    elif mutation == "unexpected":
        (fixture / "objects" / "unexpected.txt").write_text("not in sealed membership")
    else:
        path = next((fixture / "objects").iterdir())
        if mutation == "missing":
            path.unlink()
        else:
            raw = path.read_bytes()
            path.write_bytes(bytes([raw[0] ^ 1]) + raw[1:])
    with pytest.raises((AssertionError, FileNotFoundError)):
        historical.verified_files(fixture=fixture)


def test_reused_repository_fixture_is_still_hash_checked(tmp_path):
    files = json.loads((historical.FIXTURE / "manifest.json").read_bytes())["files"]
    for row in files:
        if "repository_fixture" not in row:
            continue
        path = tmp_path / row["repository_fixture"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((historical.REPOSITORY / row["repository_fixture"]).read_bytes())
    first = next(row for row in files if "repository_fixture" in row)
    path = tmp_path / first["repository_fixture"]
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(AssertionError):
        historical.verified_files(repository=tmp_path)


def test_live_boundary_and_addon_inputs_remain_current_source(monkeypatch):
    import test_standalone_runtime_boundary as boundary

    current = Path(__file__).resolve().parents[2]
    assert boundary.ROOT == current
    assert boundary.ADDON == current / "blender_addon/mechanical_cad_blender"
    assert boundary.guard_namespace()["ROOT"] == historical.historical_runtime_root()
    calls = []
    monkeypatch.setattr(boundary, "assert_import_boundary", lambda root: calls.append(root))
    # Exercise the real live-boundary test, not merely a helper with a supplied root.
    boundary.test_only_exact_named_runtime_edges_import_new_leaves_and_no_dynamic_bootstrap()
    assert calls == [current]


def test_live_mutation_fixture_copies_current_addon_not_historical_snapshot(tmp_path, monkeypatch):
    import test_standalone_runtime_boundary as boundary

    name = "runtime_bundle_launch.py"
    before, after = b"MAX_RELEASE_BYTES = 16 * 1024", b"MAX_RELEASE_BYTES = 32 * 1024"
    current = (boundary.ADDON / name).read_bytes()
    assert current.count(before) == 1
    calls = []

    def reject(root):
        copied = root / "blender_addon/mechanical_cad_blender" / name
        calls.append(copied.read_bytes())
        raise AssertionError("controlled live mutation rejection")

    monkeypatch.setattr(boundary, "assert_windows_runtime_cache_finite_symbols", reject)
    boundary.test_windows_runtime_cache_nonfinite_symbol_and_import_mutations_reject(
        tmp_path, name, before, after
    )
    assert calls == [current.replace(before, after)]
