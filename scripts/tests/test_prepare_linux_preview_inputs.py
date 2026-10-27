"""Synthetic, inert Linux refresh controls. No runtime or source material is executed."""
from __future__ import annotations

import importlib.util
import io
import json
import shutil
import stat
import struct
import subprocess
import sys
import zipfile
from contextlib import nullcontext
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


p = load("linux_refresh_tests", ROOT / "scripts/prepare_linux_preview_inputs.py")
f = load("linux_refresh_material_fixtures", ROOT / "scripts/tests/test_standalone_package_materials.py")
LINUX_ONLY = pytest.mark.skipif(sys.platform != "linux", reason="Real POSIX filesystem modes")


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], stderr=subprocess.PIPE).decode().strip()


def commit(repo):
    git(repo, "add", ".")
    git(repo, "-c", "user.name=Fixture", "-c", "user.email=test@example.invalid", "commit", "-m", "fixture")
    return git(repo, "rev-parse", "HEAD")


def zip_bytes(entries):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        for name, data, mode in entries:
            info = zipfile.ZipInfo(name)
            # ZipInfo normalizes os.sep on Windows. Adversarial fixtures must
            # preserve the actual supplied spelling in both ZIP headers.
            info.filename = name
            info.orig_filename = name
            info.create_system = 3
            info.external_attr = mode << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
    return out.getvalue()


def record(name, data, mode=0o644):
    return {"path": name, "size": len(data), "sha256": p.A.digest(data), "mode": mode}


@pytest.fixture
def disk_capacity(tmp_path, monkeypatch):
    """Observe synthetic capacity only in this preparer's tiny fixture tree.

    Keep production reserve/allocation checks and real file operations intact.
    Rebinding the private imported module's shutil name does NOT monkeypatch
    shared stdlib functions or affect other validators, pytest or subprocesses.
    This is not the actual disk observation used for real-seed preparation.
    """
    real_disk_usage = shutil.disk_usage
    capacity = SimpleNamespace(free=p.RESERVE + 1024**3, available=None, observations=[])

    def observe(path):
        path = Path(path)
        assert path == tmp_path or tmp_path in path.parents
        free = capacity.free if capacity.available is None else capacity.available(path)
        capacity.observations.append((path, free))
        return SimpleNamespace(free=free)

    monkeypatch.setattr(p, "shutil", SimpleNamespace(
        disk_usage=observe, copyfileobj=shutil.copyfileobj))
    assert shutil.disk_usage is real_disk_usage
    assert p.shutil is not shutil
    assert p.RESERVE == 5 * 1024**3
    yield capacity
    assert shutil.disk_usage is real_disk_usage


@pytest.fixture
def prepared(tmp_path, monkeypatch, disk_capacity):
    if sys.platform != "linux":
        pytest.skip("Linux-only preparation fixture; portable parser tests remain active")
    original = f.inputs.__wrapped__(tmp_path)
    repo = original["source_root"]
    (repo / "src/mechanical_cad/__init__.py").write_text(f'__version__ = "{f.PROJECT_VERSION}"\n')
    git(repo, "init", "-b", "main")
    git(repo, "remote", "add", "origin", p.PUBLIC_URL)
    ancestor = commit(repo)
    (repo / "old-marker.txt").write_bytes(b"seed source marker")
    old = commit(repo)
    (repo / "new.txt").write_bytes(b"new exact public-fixture source\n")
    new = commit(repo)
    git(repo, "update-ref", "refs/remotes/origin/main", new)
    value = json.loads(original["materials_map"])
    project = next(c for c in value["components"] if c["kind"] == "project_package")
    project["source_paths"] = ["sources/project/old.zip", "sources/preparation/candidate-input-preparation.zip"]
    material_bytes = {r["path"]: (original["materials_root"] / r["path"]).read_bytes()
                      for r in original["materials_files"] if r["path"] != "sources/project.tar.xz"}
    material_bytes["sources/project/old.zip"] = b"INERT OLD SOURCE\n"
    preparation = b"INERT SAME-SOURCE RECONSTRUCTOR; NEVER EXECUTE\n"
    material_bytes["sources/preparation/candidate-input-preparation.zip"] = preparation
    materials = sorted([record(n, b) for n, b in material_bytes.items()], key=lambda r: r["path"])
    runtime = sorted(original["runtime_files"], key=lambda r: r["path"])
    runtime_hash = p.A.digest(p.A.canonical(runtime))
    lock = original["runtime_lock"]
    value.update(source_commit=old, runtime_lock_sha256=p.A.digest(lock),
                 runtime_inventory_sha256=runtime_hash,
                 materials_inventory_sha256=p.A.digest(p.A.canonical(materials)))
    packaged = {"materials_map": value, "materials_inventory": materials,
                "materials_map_sha256": p.A.digest(p.A.canonical(value)),
                "materials_inventory_sha256": value["materials_inventory_sha256"],
                "runtime_lock_sha256": p.A.digest(lock), "runtime_inventory_sha256": runtime_hash,
                "source_commit": old, "platform": "linux-x64", "bundle_id": "a" * 64}
    payload_entries = [(r["path"], (original["runtime_root"] / r["path"]).read_bytes(),
                        stat.S_IFREG | r["mode"]) for r in runtime]
    payload_entries.append(("src/mechanical_cad/poison.py", b"raise AssertionError('never run')", stat.S_IFREG | 0o644))
    manifest = {"platform": "linux-x64", "bundle_id": packaged["bundle_id"],
                "files": sorted([record(n, b, stat.S_IMODE(m)) for n, b, m in payload_entries], key=lambda r: r["path"])}
    prefix = "_backend/" + packaged["bundle_id"] + "/"
    members = {**material_bytes, "runtime-lock.json": lock,
               "PACKAGED_MATERIALS.json": p.A.canonical(packaged),
               prefix + "bundle-manifest.json": p.A.canonical(manifest),
               prefix + "payload.zip": zip_bytes(payload_entries)}
    seed = tmp_path / "seed.zip"
    seed.write_bytes(zip_bytes([(n, b, stat.S_IFREG | 0o644) for n, b in members.items()]))
    acquisition = p.A.canonical({"platform": "linux-x64", "inventory_sha256": runtime_hash,
                                "files": [{"destination": r["path"], **{k: v for k, v in r.items() if k != "path"}}
                                          for r in runtime]})
    pin = {"size": seed.stat().st_size, "sha256": p.A.digest(seed.read_bytes()), "source_commit": old,
           "packaged": p.A.digest(members["PACKAGED_MATERIALS.json"]), "runtime_lock": p.A.digest(lock),
           "runtime_inventory": runtime_hash, "acquisition": p.A.digest(acquisition),
           "preparation_source": p.A.digest(preparation), "runtime_count": len(runtime),
           "component_count": 2, "issue_count": 2}
    monkeypatch.setattr(p, "PIN", pin)
    actual_read = p.A.read_metadata
    monkeypatch.setattr(p.A, "read_metadata", lambda path: acquisition if Path(path) ==
                        ROOT / "release_inputs/linux-x64/acquisition-lock.json" else actual_read(path))
    return SimpleNamespace(seed=seed, source_repo=repo, source_commit=new, version=f.PROJECT_VERSION,
                           output=tmp_path / "refreshed", original=packaged, ancestor=ancestor, runtime=runtime,
                           material_bytes=material_bytes, seed_bytes=seed.read_bytes())


def test_refresh_preserves_exact_history_and_cannot_create_approval(prepared, disk_capacity):
    # Neither the source working copy nor opaque seed source is executed/exported.
    (prepared.source_repo / "new.txt").write_bytes(b"dirty working file")
    result = p.prepare(prepared)
    assert result["status"] == p.STATUS
    assert result["review"] == "NOT_PERFORMED_NO_TRUSTED_REVIEW_LEDGER"
    assert result["native_qualification"] == "NOT_RUN"
    assert result["release_admission"] == "NOT_ESTABLISHED"
    assert not any("review_sha" in k or "disposition" in k for k in result)
    assert (prepared.output / "source/new.txt").read_bytes() == b"new exact public-fixture source\n"
    inputs = prepared.output / "inputs"
    updated = json.loads((inputs / "metadata/materials-map.json").read_bytes())
    old = prepared.original["materials_map"]
    assert updated["unresolved_issues"] == old["unresolved_issues"]
    assert updated["runtime_bindings"] == old["runtime_bindings"]
    assert [c for c in updated["components"] if c["kind"] != "project_package"] == [
        c for c in old["components"] if c["kind"] != "project_package"]
    assert p.preserved_identity(updated) == p.preserved_identity(old)
    assert p.A.digest((inputs / "metadata/runtime-lock.json").read_bytes()) == p.PIN["runtime_lock"]
    assert p.A.digest((inputs / "metadata/runtime-inventory.json").read_bytes()) == p.PIN["runtime_inventory"]
    for row in prepared.runtime:
        assert p.file_record(inputs / "runtime" / row["path"], row["path"]) == row
    for name, data in prepared.material_bytes.items():
        if name.startswith("sources/project/"):
            assert not (inputs / "materials" / name).exists()
        else:
            assert (inputs / "materials" / name).read_bytes() == data
    assert len(list((inputs / "metadata").iterdir())) == 4
    assert prepared.seed.read_bytes() == prepared.seed_bytes
    assert not (prepared.output.parent / "EXECUTED").exists()
    assert not (inputs / "runtime/src").exists()
    assert result["implementation_is_separate_from_target_source"] is True
    assert result["public_source_verification"] == "CALLER_VERIFICATION_REQUIRED_NOT_ESTABLISHED_BY_THIS_TOOL"
    source_zip = inputs / "materials/sources/project" / f"mechanical-cad-{prepared.source_commit}.zip"
    with zipfile.ZipFile(source_zip) as archive:
        assert "scripts/prepare_linux_preview_inputs.py" not in archive.namelist()
    with zipfile.ZipFile(inputs / "materials" / result["implementation_source_path"]) as archive:
        assert set(archive.namelist()) == set(p.IMPLEMENTATION_FILES)
        assert archive.read("scripts/prepare_linux_preview_inputs.py") == (ROOT / "scripts/prepare_linux_preview_inputs.py").read_bytes()
    assert json.loads((prepared.output / "preparation-receipt.json").read_bytes()) == result
    # The complete positive path still consults capacity initially and before
    # bounded source/material/runtime/receipt allocations; reserve is not stubbed.
    observed = [path for path, _ in disk_capacity.observations]
    assert len(observed) > 20
    assert observed[0] == prepared.output.parent
    for directory in (prepared.output, inputs / "runtime", inputs / "metadata"):
        assert directory in observed


@pytest.mark.parametrize("change", ["seed_size", "seed_digest", "source", "same_source", "version",
                                   "output_exists", "origin", "pin", "symlink", "older_source"])
def test_refusal_before_output(prepared, monkeypatch, change):
    if change == "seed_size":
        prepared.seed.write_bytes(prepared.seed_bytes + b"x")
    elif change == "seed_digest":
        prepared.seed.write_bytes(b"x" + prepared.seed_bytes[1:])
    elif change == "source":
        prepared.source_commit = "f" * 40
    elif change == "same_source":
        prepared.source_commit = p.PIN["source_commit"]
    elif change == "older_source":
        prepared.source_commit = prepared.ancestor
    elif change == "version":
        prepared.version = "99.0.0"
    elif change == "output_exists":
        prepared.output.mkdir()
        (prepared.output / "keep").write_bytes(b"untouched")
    elif change == "origin":
        git(prepared.source_repo, "remote", "set-url", "origin", "https://example.invalid/repo")
    elif change == "pin":
        monkeypatch.setitem(p.PIN, "acquisition", "0" * 64)
    elif change == "symlink":
        link = prepared.seed.with_name("linked.zip")
        link.symlink_to(prepared.seed)
        prepared.seed = link
    with pytest.raises((ValueError, subprocess.CalledProcessError)):
        p.prepare(prepared)
    assert not prepared.output.exists() or (prepared.output / "keep").read_bytes() == b"untouched"


@pytest.mark.parametrize("headroom", [-1, 32 * 1024**2], ids=["below_floor", "unfunded_allocation"])
def test_preparation_capacity_refusal_precedes_output(prepared, disk_capacity, headroom):
    # Even being above the floor cannot fund the initial remaining-allocation
    # budget: fixed metadata overhead alone is 32 MiB, before source/runtime.
    disk_capacity.free = p.RESERVE + headroom
    with pytest.raises(p.RefreshError, match="5 GiB free-disk reserve required"):
        p.prepare(prepared)
    assert disk_capacity.observations == [(prepared.output.parent, disk_capacity.free)]
    assert not prepared.output.exists()
    assert prepared.seed.read_bytes() == prepared.seed_bytes


@LINUX_ONLY
def test_reserve_includes_rounded_remaining_allocation(tmp_path, disk_capacity):
    needed = 4097
    allocation = p.allocation_bytes(tmp_path, needed)
    assert allocation >= needed
    disk_capacity.free = p.RESERVE + allocation
    p.reserve_space(tmp_path, needed)  # Exact sufficient boundary is accepted.
    disk_capacity.free -= 1
    with pytest.raises(p.RefreshError, match="5 GiB free-disk reserve required"):
        p.reserve_space(tmp_path, needed)
    assert len(disk_capacity.observations) == 2
    assert list(tmp_path.iterdir()) == []


@LINUX_ONLY
def test_write_rejects_unfunded_allocation_before_open(tmp_path, disk_capacity):
    data = b"tiny fixture"
    disk_capacity.free = p.RESERVE + p.allocation_bytes(tmp_path, len(data) + 4096) - 1
    with pytest.raises(p.RefreshError, match="5 GiB free-disk reserve required"):
        p.write_new(tmp_path / "must-not-exist", data)
    assert disk_capacity.observations == [(tmp_path, disk_capacity.free)]
    assert list(tmp_path.iterdir()) == []


def test_no_clobber_after_success(prepared):
    p.prepare(prepared)
    before = (prepared.output / "preparation-receipt.json").read_bytes()
    with pytest.raises(p.RefreshError, match="Fresh output"):
        p.prepare(prepared)
    assert (prepared.output / "preparation-receipt.json").read_bytes() == before


def test_core_version_divergence_is_not_a_completed_preparation(prepared):
    (prepared.source_repo / "src/mechanical_cad/__init__.py").write_text('__version__ = "0.0.0"\n')
    prepared.source_commit = commit(prepared.source_repo)
    git(prepared.source_repo, "update-ref", "refs/remotes/origin/main", prepared.source_commit)
    with pytest.raises(ValueError, match="versions must agree"):
        p.prepare(prepared)
    assert not (prepared.output / "preparation-receipt.json").exists()
    assert json.loads((prepared.output / "PREPARATION_FAILED.json").read_bytes())["status"] == "PREPARATION_FAILED_NOT_READY"


@pytest.mark.parametrize("change", ["content", "mode"])
@LINUX_ONLY
def test_source_export_zip_rejects_divergence(tmp_path, change):
    source = tmp_path / "source"
    source.mkdir()
    path = source / "file"
    path.write_bytes(b"original")
    path.chmod(0o644)
    rows = [record("file", b"original")]
    if change == "content":
        path.write_bytes(b"modified")
    else:
        path.chmod(0o755)
    with pytest.raises(ValueError):
        p.export_zip(tmp_path / "source.zip", source, rows)
    assert not (tmp_path / "source.zip").exists()


@pytest.mark.parametrize("name", ["../escape", "/absolute", "a\\b", "a//b", "a/./b", "C:file",
                                  "a/CON.txt", "a/NUL", "a/com¹", "a/trailing.", "a/trailing ",
                                  "a/\x01control", "a/.git/config", "a/e\u0301", "a/CONIN$"])
def test_rejects_unsafe_zip_names(name):
    data = zip_bytes([(name, b"x", stat.S_IFREG | 0o644)])
    flags, = struct.unpack_from("<H", data, 6)
    encoded = name.encode("utf-8" if flags & 0x800 else "cp437")
    local_length, = struct.unpack_from("<H", data, 26)
    central = data.index(b"PK\x01\x02")
    central_length, = struct.unpack_from("<H", data, central + 28)
    assert local_length == central_length == len(encoded)
    assert data[30:30 + local_length] == encoded
    assert data[central + 46:central + 46 + central_length] == encoded
    with pytest.raises(ValueError), p.checked_archive(io.BytesIO(data)):
        pass


@pytest.mark.parametrize("names", [["same", "same"], ["A", "a"], ["A/one", "a/two"], ["a", "a/child"]])
def test_rejects_duplicate_alias_and_file_directory_collisions(names):
    with pytest.warns(UserWarning) if names[0] == names[1] else nullcontext():
        data = zip_bytes([(n, b"x", stat.S_IFREG | 0o644) for n in names])
    with pytest.raises(ValueError), p.checked_archive(io.BytesIO(data)):
        pass


@pytest.mark.parametrize("mode", [stat.S_IFLNK | 0o777, stat.S_IFDIR | 0o755, stat.S_IFIFO | 0o644,
                                  stat.S_IFREG | 0o4755, 0o644])
def test_rejects_nonregular_special_and_untyped_modes(mode):
    with pytest.raises(ValueError), p.checked_archive(io.BytesIO(zip_bytes([("file", b"x", mode)]))):
        pass


@pytest.mark.parametrize("change", ["prefix", "suffix", "truncated", "local_name", "local_mode",
                                   "compressed_bound", "expanded_bound", "count_bound", "member_bound"])
def test_rejects_malformed_or_unbounded_zip(monkeypatch, change):
    data = zip_bytes([("file", b"bytes", stat.S_IFREG | 0o644)])
    if change == "prefix":
        data = b"x" + data
    elif change == "suffix":
        data += b"x"
    elif change == "truncated":
        data = data[:-1]
    elif change == "local_name":
        data = data[:30] + b"fIle" + data[34:]
    elif change == "local_mode":
        data = data[:8] + b"\x00\x00" + data[10:]
    else:
        monkeypatch.setattr(p, {"compressed_bound": "MAX_ZIP", "expanded_bound": "MAX_EXPANDED",
                              "count_bound": "MAX_ENTRIES", "member_bound": "MAX_MEMBER"}[change], 0 if change == "count_bound" else 1)
    with pytest.raises(ValueError), p.checked_archive(io.BytesIO(data)):
        pass


def test_member_hash_mode_and_size_are_checked():
    data = zip_bytes([("file", b"bytes", stat.S_IFREG | 0o644)])
    with p.checked_archive(io.BytesIO(data)) as (archive, infos):
        for change in ({"sha256": "0" * 64}, {"size": 6}, {"mode": 0o755}):
            with pytest.raises(ValueError):
                p.copy_member(archive, infos["file"], record("file", b"bytes") | change)


def test_cannot_pass_review_or_override_seed_pins_through_cli():
    with pytest.raises(SystemExit):
        p.parser().parse_args(["--seed", "seed.zip", "--source-repo", "repo",
                               "--source-commit", "a" * 40, "--version", "1.30.0",
                               "--output", "new", "--seed-sha256", "0" * 64,
                               "--review", "fabricated.json"])


def test_git_environment_strips_ambient_overrides(monkeypatch):
    monkeypatch.setenv("GIT_DIR", "/fake/repository")
    monkeypatch.setenv("GIT_INDEX_FILE", "/fake/index")
    monkeypatch.setenv("GIT_CONFIG_COUNT", "99")
    env = p.git_environment()
    assert "GIT_DIR" not in env and "GIT_INDEX_FILE" not in env and "GIT_CONFIG_COUNT" not in env
    assert env["GIT_NO_LAZY_FETCH"] == "1" and env["GIT_NO_REPLACE_OBJECTS"] == "1"



@pytest.mark.parametrize("change", ["extra", "comment", "encrypted", "descriptor", "unknown_method", "count"])
def test_rejects_unsupported_zip_metadata(change):
    data = zip_bytes([("file", b"bytes", stat.S_IFREG | 0o644)])
    if change in {"extra", "comment"}:
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            info = zipfile.ZipInfo("file")
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            if change == "extra":
                info.extra = b"\xfe\xca\x00\x00"
            else:
                info.comment = b"unsupported"
            archive.writestr(info, b"bytes")
        data = stream.getvalue()
    else:
        changed = bytearray(data)
        cd = data.index(b"PK\x01\x02")
        if change == "count":
            struct.pack_into("<HH", changed, len(data) - 14, 2, 2)
        elif change == "unknown_method":
            struct.pack_into("<H", changed, 8, 99)
            struct.pack_into("<H", changed, cd + 10, 99)
        else:
            flags = 1 if change == "encrypted" else 8
            struct.pack_into("<H", changed, 6, flags)
            struct.pack_into("<H", changed, cd + 8, flags)
        data = bytes(changed)
    with pytest.raises(ValueError), p.checked_archive(io.BytesIO(data)):
        pass


def test_export_preserves_git_executable_mode_not_dirty_working_mode(prepared):
    path = prepared.source_repo / "new.txt"
    path.chmod(0o755)
    prepared.source_commit = commit(prepared.source_repo)
    git(prepared.source_repo, "update-ref", "refs/remotes/origin/main", prepared.source_commit)
    path.chmod(0o644)
    p.prepare(prepared)
    assert stat.S_IMODE((prepared.output / "source/new.txt").stat().st_mode) == 0o755


@LINUX_ONLY
def test_implementation_commit_requires_exact_modes(tmp_path, monkeypatch, disk_capacity):
    repository = tmp_path / "implementation"
    repository.mkdir()
    for name in p.IMPLEMENTATION_FILES:
        target = repository / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
        target.chmod(0o644)
    git(repository, "init", "-b", "main")
    expected_commit = commit(repository)
    monkeypatch.setattr(p, "ROOT", repository)
    first = tmp_path / "first"
    first.mkdir()
    assert p.implementation_snapshot(first)[3] == expected_commit
    (repository / p.IMPLEMENTATION_FILES[0]).chmod(0o755)
    second = tmp_path / "second"
    second.mkdir()
    assert p.implementation_snapshot(second)[3] is None


def test_insufficient_space_does_not_create_failure_marker_or_mask_error(prepared, disk_capacity):
    disk_capacity.available = lambda path: (
        p.RESERVE - 1 if prepared.output.exists() else p.RESERVE + 1024**3)
    with pytest.raises(p.RefreshError, match="5 GiB"):
        p.prepare(prepared)
    assert disk_capacity.observations[0][1] > p.RESERVE
    assert all(free < p.RESERVE for _, free in disk_capacity.observations[1:])
    assert len(disk_capacity.observations) >= 3  # Admission, directory, diagnostic.
    assert list(prepared.output.iterdir()) == []  # No unsafe write after exhaustion.
    assert not (prepared.output / "preparation-receipt.json").exists()
    assert not (prepared.output / "PREPARATION_FAILED.json").exists()


def test_failure_marker_cannot_mask_original_error_at_reserve_boundary(prepared, monkeypatch,
                                                                     disk_capacity):
    failed = False

    def broken_export(*args):
        nonlocal failed
        failed = True
        raise p.RefreshError("original export failure")

    monkeypatch.setattr(p.A, "export_source", broken_export)
    disk_capacity.available = lambda path: p.RESERVE + (4096 if failed else 1024**3)
    with pytest.raises(p.RefreshError, match="original export failure"):
        p.prepare(prepared)
    assert not (prepared.output / "PREPARATION_FAILED.json").exists()


def test_current_recipient_notice_explicitly_supersedes_seed_locators(prepared):
    result = p.prepare(prepared)
    materials = prepared.output / "inputs/materials"
    notice = (materials / result["current_recipient_notice"]).read_text()
    for name in ("licenses/DISTRIBUTION_NOTICE.md", "licenses/INTEGRATED_MATERIALS.md",
                 "licenses/preparation/REPRODUCE_INPUTS.md",
                 "licenses/provenance/project-source-freeze.json"):
        assert name in notice
    assert prepared.source_commit in notice and p.PIN["source_commit"] in notice
    assert f"sources/project/mechanical-cad-{prepared.source_commit}.zip" in notice
    assert result["implementation_source_path"] in notice
    assert "NOT these refreshed inputs" in notice
    assert "reconstruction need NOT require the predecessor" in notice
    assert "ACTUAL_VERIFIED_NEW_PACKAGED_MATERIALS_SHA256" in notice
    assert "No issue has been automatically resolved" in notice
    assert "docs/RUNTIME_ACQUISITION.md" in notice
    assert "release_inputs/linux-x64/acquisition-lock.json" in notice
    assert "Review the retained helper before execution" in notice
    assert "Cross-filesystem or link denial fails without a copy fallback" in notice
    assert "not a hardlink mode in this preparer" in notice
    value = json.loads((prepared.output / "inputs/metadata/materials-map.json").read_bytes())
    project = next(c for c in value["components"] if c["kind"] == "project_package")
    assert result["current_recipient_notice"] in project["notice_paths"]
    assert result["current_recipient_notice"] in project["provenance_paths"]


def test_preparer_source_is_self_contained_without_git_history(prepared, monkeypatch):
    result = p.prepare(prepared)
    root = prepared.output / "preparer-source"
    checked = subprocess.run([sys.executable, "-B", str(root / "scripts/prepare_linux_preview_inputs.py"),
                              "--help"], check=True, capture_output=True, text=True)
    assert "--source-commit" in checked.stdout
    monkeypatch.setattr(p, "ROOT", root)
    destination = prepared.output.parent / "nongit-reconstruction"
    destination.mkdir()
    _, _, identity, commit = p.implementation_snapshot(destination)
    assert identity == result["implementation_source_inventory_sha256"]
    assert commit is None


@pytest.mark.skipif(sys.platform == "linux", reason="Requires a real non-Linux host, never spoofed")
def test_non_linux_refuses_before_git_or_filesystem_side_effects(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Git must not run on an unsupported host")

    monkeypatch.setattr(p.subprocess, "run", forbidden)
    args = SimpleNamespace(source_repo=tmp_path / "absent-repo", seed=tmp_path / "absent-seed",
                           output=tmp_path / "output", source_commit="a" * 40, version="1.30.0")
    with pytest.raises(p.RefreshError, match="Linux builder host required"):
        p.prepare(args)
    assert list(tmp_path.iterdir()) == []
