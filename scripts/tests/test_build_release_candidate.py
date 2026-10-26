"""Offline adapter tests. Synthetic runtime bytes are NEVER executed."""
import copy
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_REPO = Path(os.environ.get("MCAD_BUILDER_FIXTURE_REPO", ROOT))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


adapter = load("candidate_adapter_tests", ROOT / "scripts/build_release_candidate.py")
fixtures = load("candidate_materials_fixtures",
                FIXTURE_REPO / "scripts/tests/test_standalone_package_materials.py")


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], stderr=subprocess.PIPE).decode().strip()


@pytest.fixture
def prepared(tmp_path):
    original = fixtures.inputs.__wrapped__(tmp_path)
    repo = original["source_root"]
    version = fixtures.PROJECT_VERSION
    (repo / "src/mechanical_cad/__init__.py").write_text(f'__version__ = "{version}"\n')
    for name in ("scripts/package_standalone_extension.py", "scripts/package_standalone_materials.py",
                 "blender_addon/mechanical_cad_blender/runtime_bundle_manifest.py"):
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((FIXTURE_REPO / name).read_bytes())
    git(repo, "init", "-b", "main")
    git(repo, "add", ".")
    git(repo, "-c", "user.name=Fixture", "-c", "user.email=test@example.invalid", "commit", "-m", "fixture")
    commit = git(repo, "rev-parse", "HEAD")
    git(repo, "tag", "v" + version)
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    original["runtime_root"].rename(inputs / "runtime")
    original["materials_root"].rename(inputs / "materials")
    metadata = inputs / "metadata"
    metadata.mkdir()
    exported = tmp_path / "source-export"
    exported.mkdir()
    source_files = adapter.export_source(repo, commit, exported)
    original.update(source_commit=commit, source_files=source_files)
    fixtures.pins(original)
    for name, value in (("runtime-inventory.json", adapter.canonical(original["runtime_files"])),
                        ("materials-inventory.json", adapter.canonical(original["materials_files"])),
                        ("runtime-lock.json", original["runtime_lock"]),
                        ("materials-map.json", original["materials_map"])):
        (metadata / name).write_bytes(value)
    args = SimpleNamespace(source_repo=repo, source_commit=commit, tag="v" + version,
        main_ref="refs/heads/main", inputs_root=inputs, platform="linux-x64",
        output=tmp_path / "candidate.zip", receipt=tmp_path / "candidate.json",
        runtime_lock_sha256=adapter.digest(original["runtime_lock"]),
        materials_map_sha256=adapter.digest(original["materials_map"]))
    return args


def test_real_offline_build_preserves_status_and_immutable_source(prepared):
    # Deliberately dirty working files are not exported as release source.
    (prepared.source_repo / "src/mechanical_cad/__init__.py").write_text("raise AssertionError('dirty')")
    result = adapter.build(prepared)
    assert result["status"] == adapter.STATUS
    assert result["qualification"] == "NOT_RUN"
    assert result["source_commit"] == prepared.source_commit
    assert result["sha256"] == adapter.digest(prepared.output.read_bytes())
    assert json.loads(prepared.receipt.read_text()) == result
    assert result["unresolved_material_issue_ids"] == ["rebuild", "rights"]
    assert not (prepared.output.parent / "EXECUTED").exists()
    assert str(prepared.output.parent) not in prepared.receipt.read_text()


@pytest.mark.parametrize("change", ["bad_sha", "bad_tag", "leading_zero", "not_main", "wrong_platform",
    "lock_hash", "map_hash", "extra_metadata", "duplicate_metadata", "runtime_mutation",
    "runtime_extra", "material_mutation", "output_exists", "receipt_exists", "stale_map"])
def test_refuses_invalid_inputs_without_candidate(prepared, change):
    args = copy.copy(prepared)
    metadata = args.inputs_root / "metadata"
    if change == "bad_sha":
        args.source_commit = "deadbeef"
    elif change == "bad_tag":
        args.tag = "v9.9.9"
    elif change == "leading_zero":
        args.tag = "v01.29.0"
    elif change == "not_main":
        args.main_ref = "refs/heads/other"
    elif change == "wrong_platform":
        args.platform = "windows-x64"
    elif change == "lock_hash":
        args.runtime_lock_sha256 = "0" * 64
    elif change == "map_hash":
        args.materials_map_sha256 = "0" * 64
    elif change == "extra_metadata":
        (metadata / "extra.json").write_text("{}")
    elif change == "duplicate_metadata":
        (metadata / "runtime-lock.json").write_text('{"a":1,"a":2}')
    elif change == "runtime_mutation":
        (args.inputs_root / "runtime/python/bin/python3.12").write_text("changed")
    elif change == "runtime_extra":
        (args.inputs_root / "runtime/extra").write_text("extra")
    elif change == "material_mutation":
        (args.inputs_root / "materials/licenses/NOTICE.txt").write_text("changed")
    elif change == "output_exists":
        args.output.write_bytes(b"existing")
    elif change == "receipt_exists":
        args.receipt.write_text("existing")
    elif change == "stale_map":
        path = metadata / "materials-map.json"
        value = json.loads(path.read_bytes())
        value["source_commit"] = "0" * 40
        path.write_bytes(adapter.canonical(value))
        args.materials_map_sha256 = adapter.digest(path.read_bytes())
    with pytest.raises((ValueError, subprocess.CalledProcessError)):
        adapter.build(args)
    assert not args.output.exists() or args.output.read_bytes() == b"existing"


def test_deterministic_receipt_and_archive(prepared):
    first = adapter.build(prepared)
    args = copy.copy(prepared)
    directory = prepared.output.parent / "second"
    directory.mkdir()
    args.output, args.receipt = directory / prepared.output.name, directory / prepared.receipt.name
    second = adapter.build(args)
    assert first == second
    assert prepared.output.read_bytes() == args.output.read_bytes()


def test_tag_must_belong_to_main(prepared):
    git(prepared.source_repo, "checkout", "--orphan", "unrelated")
    git(prepared.source_repo, "-c", "user.name=Fixture", "-c", "user.email=test@example.invalid",
        "commit", "-m", "unrelated")
    git(prepared.source_repo, "branch", "-f", "main", "HEAD")
    with pytest.raises(subprocess.CalledProcessError):
        adapter.build(prepared)
    assert not prepared.output.exists()


def test_symlink_input_refused(prepared):
    link = prepared.inputs_root.parent / "linked-inputs"
    link.symlink_to(prepared.inputs_root, target_is_directory=True)
    prepared.inputs_root = link
    with pytest.raises(adapter.CandidateError, match="Symlink"):
        adapter.build(prepared)
    assert not prepared.output.exists()


def test_denied_publication_not_retried(prepared, monkeypatch):
    calls = []
    def deny(*args, **kwargs):
        calls.append(args)
        raise PermissionError("synthetic denied publication")
    monkeypatch.setattr(os, "link", deny)
    with pytest.raises(PermissionError):
        adapter.build(prepared)
    assert len(calls) == 1
    assert not prepared.output.exists()
    assert json.loads(prepared.receipt.read_text())["status"] == "BUILD_UNCONFIRMED"
    with pytest.raises(adapter.CandidateError, match="already exists"):
        adapter.build(prepared)
    assert len(calls) == 1


def test_real_cli(prepared):
    command = [sys.executable, str(ROOT / "scripts/build_release_candidate.py")]
    for name, value in vars(prepared).items():
        command.extend(["--" + name.replace("_", "-"), str(value)])
    completed = subprocess.run(command, capture_output=True, text=True, check=True, timeout=120)
    assert json.loads(completed.stdout)["qualification"] == "NOT_RUN"
    assert completed.stderr == ""


def test_windows_contract_only_candidate(prepared):
    # Offline format/profile exercise, explicitly NOT native Windows qualification.
    metadata = prepared.inputs_root / "metadata"
    path = metadata / "runtime-inventory.json"
    records = json.loads(path.read_text())
    interpreter = prepared.inputs_root / "runtime/python/bin/python3.12"
    interpreter.rename(interpreter.parent.parent / "python.exe")
    interpreter.parent.rmdir()
    for record in records:
        if record["path"] == "python/bin/python3.12":
            record["path"] = "python/python.exe"
    path.write_bytes(adapter.canonical(records))
    value = json.loads((metadata / "materials-map.json").read_text())
    value["platform"] = "windows-x64"
    value["runtime_inventory_sha256"] = fixtures.inventory_hash(records)
    for binding in value["runtime_bindings"]:
        if binding["path"] == "python/bin/python3.12":
            binding["path"] = "python/python.exe"
    (metadata / "materials-map.json").write_bytes(adapter.canonical(value))
    prepared.materials_map_sha256 = adapter.digest(adapter.canonical(value))
    prepared.platform = "windows-x64"
    result = adapter.build(prepared)
    assert result["platform"] == "windows-x64"
    assert result["status"] == adapter.STATUS
    assert result["qualification"] == "NOT_RUN"


def test_export_ignores_attributes_and_dirty_worktree(prepared, tmp_path):
    repo = prepared.source_repo
    (repo / ".gitattributes").write_text("LICENSE export-ignore\nsrc/** export-subst\n")
    git(repo, "add", ".gitattributes")
    git(repo, "-c", "user.name=Fixture", "-c", "user.email=test@example.invalid", "commit", "-m", "attributes")
    sha = git(repo, "rev-parse", "HEAD")
    (repo / "LICENSE").write_text("not committed")
    destination = tmp_path / "attributes-export"
    destination.mkdir()
    inventory = adapter.export_source(repo, sha, destination)
    assert (destination / "LICENSE").read_bytes() != b"not committed"
    assert any(item["path"] == "LICENSE" for item in inventory)


def test_source_version_mismatch(prepared):
    with pytest.raises(adapter.CandidateError, match="versions"):
        adapter.version_check(prepared.source_repo, "9.9.9")


def test_nonfinite_metadata_rejected():
    with pytest.raises(adapter.CandidateError, match="Nonfinite"):
        adapter.strict_json(b'{"bad":NaN}')


def test_shadow_runtime_rejected(prepared):
    metadata = prepared.inputs_root / "metadata"
    path = prepared.inputs_root / "runtime/bootstrap.py"
    path.write_bytes(b"shadow")
    records = json.loads((metadata / "runtime-inventory.json").read_bytes())
    records.append(fixtures.record("bootstrap.py", b"shadow"))
    (metadata / "runtime-inventory.json").write_bytes(adapter.canonical(records))
    value = json.loads((metadata / "materials-map.json").read_bytes())
    value["runtime_inventory_sha256"] = fixtures.inventory_hash(records)
    value["runtime_bindings"].append({"path": "bootstrap.py", "component_ids": ["runtime"]})
    (metadata / "materials-map.json").write_bytes(adapter.canonical(value))
    prepared.materials_map_sha256 = adapter.digest(adapter.canonical(value))
    with pytest.raises(ValueError, match="collision"):
        adapter.build(prepared)
    assert not prepared.output.exists()


def test_fifo_metadata_refused_without_blocking(tmp_path):
    if not hasattr(os, "mkfifo"):
        pytest.skip("POSIX FIFO fixture only")
    path = tmp_path / "metadata.json"
    os.mkfifo(path)
    with pytest.raises(adapter.CandidateError, match="regular file"):
        adapter.read_metadata(path)


@pytest.mark.parametrize("ref", ["refs/heads/main", "refs/tags/v01.29.0", "refs/tags/v1.29.0-rc.1"])
def test_readiness_ref_refusals(prepared, ref):
    preflight = load("candidate_preflight", ROOT / "scripts/check_release_ref.py")
    git(prepared.source_repo, "update-ref", "refs/remotes/origin/main", prepared.source_commit)
    with pytest.raises(ValueError):
        preflight.check(prepared.source_repo, ref)


def test_readiness_matching_main_tag(prepared):
    preflight = load("candidate_preflight", ROOT / "scripts/check_release_ref.py")
    git(prepared.source_repo, "update-ref", "refs/remotes/origin/main", prepared.source_commit)
    preflight.check(prepared.source_repo, "refs/tags/" + prepared.tag)


def test_git_replace_cannot_change_exported_commit(prepared, tmp_path):
    repo = prepared.source_repo
    original = (repo / "LICENSE").read_bytes()
    (repo / "LICENSE").write_text("replacement tree")
    git(repo, "add", "LICENSE")
    git(repo, "-c", "user.name=Fixture", "-c", "user.email=test@example.invalid", "commit", "-m", "replacement")
    replacement = git(repo, "rev-parse", "HEAD")
    git(repo, "replace", prepared.source_commit, replacement)
    destination = tmp_path / "replace-export"
    destination.mkdir()
    adapter.export_source(repo, prepared.source_commit, destination)
    assert (destination / "LICENSE").read_bytes() == original


@pytest.mark.parametrize("name", ["C:/escape.py", "file:stream", "CON", "dir/NUL.py", "COM1.txt",
    "LPT²", "dir/space ", "dir/dot.", "../escape", "/escape", "dir\\escape", ".GIT/config",
    "bad\x01name", "e\u0301.py"])
def test_unsafe_export_path_rejected_before_any_write(tmp_path, monkeypatch, name):
    listing = b"100644 blob " + b"a" * 40 + b"\t" + name.encode() + b"\0"
    monkeypatch.setattr(subprocess, "check_output", lambda *a, **kw: listing)
    def must_not_start(*args, **kwargs):
        raise AssertionError("cat-file must not start for unsafe path plan")
    monkeypatch.setattr(subprocess, "Popen", must_not_start)
    export = tmp_path / "export"
    export.mkdir()
    with pytest.raises(adapter.CandidateError):
        adapter.export_source(tmp_path, "a" * 40, export)
    assert list(export.iterdir()) == []
    assert list(tmp_path.iterdir()) == [export]


@pytest.mark.parametrize("names", [("file.py", "FILE.py"), ("Dir/a.py", "dir/b.py")])
def test_casefold_collisions_rejected_before_export(tmp_path, monkeypatch, names):
    listing = b"".join(b"100644 blob " + b"a" * 40 + b"\t" + n.encode() + b"\0" for n in names)
    monkeypatch.setattr(subprocess, "check_output", lambda *a, **kw: listing)
    def must_not_start(*args, **kwargs):
        raise AssertionError("cat-file must not start for colliding path plan")
    monkeypatch.setattr(subprocess, "Popen", must_not_start)
    export = tmp_path / "export"
    export.mkdir()
    with pytest.raises(adapter.CandidateError, match="Case-colliding"):
        adapter.export_source(tmp_path, "a" * 40, export)
    assert list(export.iterdir()) == []
