"""Inert copy/pin controls; no runtime execution or network operations."""

import copy
import importlib.util
import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


s = load("supplement_test", ROOT / "scripts/supplement_linux_preview_inputs.py")
f = load("supplement_material_fixture", ROOT / "scripts/tests/test_standalone_package_materials.py")
LINUX = pytest.mark.skipif(sys.platform != "linux", reason="Actual Linux filesystem copying/modes")


def record(path="licenses/tools/notice.txt", roles=None):
    return dict(
        path=path,
        mode=420,
        size=4,
        sha256=s.A.digest(b"data"),
        roles=roles or ["notice", "provenance"],
    )


def test_manifest_positive():
    assert s.parse_additions(dict(schema_version=1, files=[record()]))[0]["size"] == 4


@pytest.mark.parametrize(
    "change",
    [
        "schema",
        "unknown",
        "empty",
        "count",
        "role",
        "duplicate_role",
        "mode",
        "hash",
        "size",
        "budget",
        "absolute",
        "traversal",
        "collision",
        "case",
        "parent",
        "prefix",
        "executable",
    ],
)
def test_manifest_negatives(change):
    row = record()
    value = dict(schema_version=1, files=[row])
    if change == "schema":
        value["schema_version"] = True
    elif change == "unknown":
        value["approval"] = True
    elif change == "empty":
        value["files"] = []
    elif change == "count":
        value["files"] = [row] * 65
    elif change == "role":
        row["roles"] = ["approval"]
    elif change == "duplicate_role":
        row["roles"] = ["notice"] * 2
    elif change == "mode":
        row["mode"] = 493
    elif change == "hash":
        row["sha256"] = "x" * 64
    elif change == "size":
        row["size"] = True
    elif change == "budget":
        row["size"] = s.MAX_BYTES + 1
    elif change == "absolute":
        row["path"] = "/licenses/tools/a"
    elif change == "traversal":
        row["path"] = "licenses/../a"
    elif change == "collision":
        value["files"].append(copy.deepcopy(row))
    elif change == "case":
        value["files"].append(dict(row, path="licenses/tools/NOTICE.txt"))
    elif change == "parent":
        value["files"].append(dict(row, path=row["path"] + "/child.txt"))
    elif change == "prefix":
        row["roles"] = ["source"]
    elif change == "executable":
        row["path"] = "licenses/tools/x.exe"
    with pytest.raises((ValueError, OSError)):
        s.parse_additions(value)


@pytest.fixture
def base(tmp_path, monkeypatch):
    if sys.platform != "linux":
        pytest.skip("Linux preparation fixture")
    raw = f.inputs.__wrapped__(tmp_path / "fixture")
    root = tmp_path / "base"
    root.mkdir()
    shutil.copytree(raw["source_root"], root / "source")
    shutil.copytree(raw["runtime_root"], root / "inputs/runtime")
    shutil.copytree(raw["materials_root"], root / "inputs/materials")
    for row in raw["runtime_files"]:
        (root / "inputs/runtime" / row["path"]).chmod(row["mode"])
    value = json.loads(raw["materials_map"])
    for i in range(40):
        item = copy.deepcopy(value["components"][0])
        item["id"] = "extra" + str(i)
        issue = "issue" + str(i)
        item["unresolved_issue_ids"] = [issue]
        value["components"].append(item)
        value["runtime_bindings"][0]["component_ids"].append(item["id"])
        value["unresolved_issues"].append(
            dict(id=issue, role="other_unresolved", description="Inert issue")
        )
    meta = root / "inputs/metadata"
    meta.mkdir()
    for name, data in (
        ("runtime-lock.json", raw["runtime_lock"]),
        (
            "runtime-inventory.json",
            s.A.canonical(sorted(raw["runtime_files"], key=lambda r: r["path"])),
        ),
        (
            "materials-inventory.json",
            s.A.canonical(sorted(raw["materials_files"], key=lambda r: r["path"])),
        ),
        ("materials-map.json", s.A.canonical(value)),
    ):
        (meta / name).write_bytes(data)
    receipt = dict(value, status=s.STATUS, materials_map_sha256=s.A.digest(s.A.canonical(value)))
    (root / "preparation-receipt.json").write_bytes(s.A.canonical(receipt))
    additions = tmp_path / "additions"
    (additions / "licenses/tools").mkdir(parents=True)
    (additions / "licenses/tools/notice.txt").write_bytes(b"data")
    manifest = tmp_path / "additions.json"
    manifest.write_bytes(s.A.canonical(dict(schema_version=1, files=[record()])))
    # Private-module facade only; actual accounting and copy operations retained.
    monkeypatch.setattr(
        s.P,
        "shutil",
        SimpleNamespace(
            copyfileobj=shutil.copyfileobj,
            disk_usage=lambda path: SimpleNamespace(free=20 * 1024**3),
        ),
    )
    return SimpleNamespace(
        base=root,
        base_receipt_sha256=s.A.digest(s.A.canonical(receipt)),
        base_map_sha256=receipt["materials_map_sha256"],
        additions_root=additions,
        additions_manifest=manifest,
        additions_sha256=s.A.digest(manifest.read_bytes()),
        output=tmp_path / "output",
    )


@LINUX
def test_copy_preserves_bindings_and_is_reproducible(base):
    result = s.supplement(base)
    old = json.loads((base.base / "inputs/metadata/materials-map.json").read_bytes())
    new = json.loads((base.output / "inputs/metadata/materials-map.json").read_bytes())
    assert s.P.preserved_identity(old) == s.P.preserved_identity(new)
    assert result["status"] == s.STATUS and result["release_admission"] == "NOT_ESTABLISHED"
    for tree in ("source", "inputs/runtime"):
        assert s.inventory(base.base / tree) == s.inventory(base.output / tree)
    for path in base.output.rglob("*"):
        if path.is_file():
            assert path.stat().st_nlink == 1
    assert (base.output / "inputs/materials" / result["implementation_source_path"]).is_file()
    old_output = base.output
    base.output = old_output.with_name("second")
    assert s.supplement(base) == result
    base.output = old_output
    with pytest.raises(ValueError, match="Fresh output"):
        s.supplement(base)


@LINUX
@pytest.mark.parametrize(
    "change",
    [
        "receipt",
        "map",
        "source",
        "runtime",
        "material",
        "extra_metadata",
        "extra_addition",
        "missing_addition",
        "addition_hash",
        "output",
        "low_space",
        "issue_count",
    ],
)
def test_preflight_refusals(base, monkeypatch, change):
    if change == "receipt":
        base.base_receipt_sha256 = "0" * 64
    elif change == "map":
        base.base_map_sha256 = "0" * 64
    elif change in {"source", "runtime", "material"}:
        folder = {"source": "source", "runtime": "inputs/runtime", "material": "inputs/materials"}[
            change
        ]
        next(p for p in (base.base / folder).rglob("*") if p.is_file()).write_bytes(b"changed")
    elif change == "extra_metadata":
        (base.base / "inputs/metadata/extra.json").write_text("{}")
    elif change == "extra_addition":
        (base.additions_root / "extra.txt").write_text("extra")
    elif change == "missing_addition":
        (base.additions_root / record()["path"]).unlink()
    elif change == "addition_hash":
        (base.additions_root / record()["path"]).write_bytes(b"fake")
    elif change == "output":
        base.output.mkdir()
    elif change == "low_space":
        monkeypatch.setattr(
            s.P, "shutil", SimpleNamespace(disk_usage=lambda p: SimpleNamespace(free=s.P.RESERVE))
        )
    elif change == "issue_count":
        path = base.base / "inputs/metadata/materials-map.json"
        value = json.loads(path.read_bytes())
        value["unresolved_issues"].pop()
        path.write_bytes(s.A.canonical(value))
        base.base_map_sha256 = s.A.digest(path.read_bytes())
        receipt_path = base.base / "preparation-receipt.json"
        receipt = json.loads(receipt_path.read_bytes())
        receipt["materials_map_sha256"] = base.base_map_sha256
        receipt_path.write_bytes(s.A.canonical(receipt))
        base.base_receipt_sha256 = s.A.digest(receipt_path.read_bytes())
    with pytest.raises((ValueError, OSError)):
        s.supplement(base)
    assert not base.output.exists() or list(base.output.iterdir()) == []


@LINUX
@pytest.mark.parametrize("change", ["exhaustion", "source_race", "metadata_race", "manifest_race"])
def test_failure_never_emits_completion_or_masks_cause(base, monkeypatch, change):
    original = s.copy_records
    calls = 0

    def copy_then_change(src, destination, records):
        nonlocal calls
        original(src, destination, records)
        calls += 1
        if calls == 1:
            if change == "exhaustion":
                monkeypatch.setattr(
                    s.P,
                    "shutil",
                    SimpleNamespace(
                        copyfileobj=shutil.copyfileobj,
                        disk_usage=lambda path: SimpleNamespace(free=s.P.RESERVE - 1),
                    ),
                )
            elif change == "source_race":
                (src / records[0]["path"]).write_bytes(b"changed after copy")
            elif change == "metadata_race":
                (base.base / "inputs/metadata/materials-map.json").write_bytes(b"{}")
            else:
                base.additions_manifest.write_bytes(b"{}")

    monkeypatch.setattr(s, "copy_records", copy_then_change)
    with pytest.raises(ValueError):
        s.supplement(base)
    assert base.output.is_dir()
    assert not (base.output / "preparation-receipt.json").exists()
    assert any((base.output / "source").rglob("*"))  # No destructive cleanup.


@LINUX
def test_output_inside_base_refused(base):
    base.output = base.base / "nested"
    with pytest.raises(ValueError, match="separate"):
        s.supplement(base)
    assert not base.output.exists()


@LINUX
def test_addition_cannot_replace_existing_material(base):
    value = dict(schema_version=1, files=[record("licenses/NOTICE.txt")])
    old = base.additions_root / record()["path"]
    new = base.additions_root / "licenses/NOTICE.txt"
    old.rename(new)
    base.additions_manifest.write_bytes(s.A.canonical(value))
    base.additions_sha256 = s.A.digest(base.additions_manifest.read_bytes())
    with pytest.raises(ValueError, match="Duplicate"):
        s.supplement(base)
    assert not base.output.exists()


@LINUX
@pytest.mark.parametrize(
    "change",
    ["retained_material", "addition", "runtime_inventory", "materials_inventory", "runtime_lock"],
)
def test_post_copy_corruption_cannot_rebaseline(base, monkeypatch, change):
    original = s.P.export_zip

    def corrupt_after_copy(*args):
        result = original(*args)
        if change in {"retained_material", "addition"}:
            name = "licenses/NOTICE.txt" if change == "retained_material" else record()["path"]
            (base.output / "inputs/materials" / name).write_bytes(b"corrupted")
        else:
            name = {
                "runtime_inventory": "runtime-inventory.json",
                "materials_inventory": "materials-inventory.json",
                "runtime_lock": "runtime-lock.json",
            }[change]
            (base.base / "inputs/metadata" / name).write_bytes(b"{}")
        return result

    monkeypatch.setattr(s.P, "export_zip", corrupt_after_copy)
    with pytest.raises(ValueError):
        s.supplement(base)
    assert not (base.output / "preparation-receipt.json").exists()


@LINUX
@pytest.mark.parametrize("tree", ["inputs/runtime", "inputs/materials", "source"])
def test_disk_modes_are_not_reinterpreted(base, tree):
    file = next(p for p in (base.base / tree).rglob("*") if p.is_file())
    file.chmod(0o600)
    with pytest.raises(ValueError):
        s.supplement(base)
    assert not base.output.exists()


def test_aggregate_addition_boundary():
    rows = [
        dict(record("licenses/tools/one.txt"), size=s.MAX_BYTES // 2),
        dict(record("licenses/tools/two.txt"), size=s.MAX_BYTES // 2),
    ]
    assert len(s.parse_additions(dict(schema_version=1, files=rows))) == 2
    rows[1]["size"] += 1
    with pytest.raises(ValueError, match="Addition byte bound"):
        s.parse_additions(dict(schema_version=1, files=rows))


@LINUX
def test_helper_snapshot_imports_without_git_or_original_checkout(base):
    import subprocess
    import zipfile

    result = s.supplement(base)
    target = base.output.parent / "standalone-helper"
    with zipfile.ZipFile(
        base.output / "inputs/materials" / result["implementation_source_path"]
    ) as archive:
        assert set(archive.namelist()) == set(s.IMPLEMENTATION_FILES)
        for name in archive.namelist():
            path = target / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(archive.read(name))
    assert not (target / ".git").exists()
    run = subprocess.run(
        [
            sys.executable,
            "-I",
            str(target / "scripts/supplement_linux_preview_inputs.py"),
            "--help",
        ],
        cwd=target,
        capture_output=True,
        timeout=30,
    )
    assert run.returncode == 0, run.stderr
    assert b"--base-receipt-sha256" in run.stdout


@pytest.mark.skipif(sys.platform == "linux", reason="Actual unsupported-host admission")
def test_nonlinux_rejects_before_inputs():
    with pytest.raises(ValueError, match="Linux preparation host"):
        s.supplement(SimpleNamespace())
