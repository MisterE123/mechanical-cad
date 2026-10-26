"""Tiny inert build fixtures; these never install or execute a runtime."""

import ast
import hashlib
import importlib
import importlib.util
import io
import json
import os
import stat
import subprocess
import sys
import tomllib
import types
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "standalone_builder_tests", ROOT / "scripts/package_standalone_extension.py"
)
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def record(name, data, mode=0o644):
    return {"path": name, "sha256": digest(data), "size": len(data), "mode": mode}


def stage(root, files):
    records = []
    for name, data in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        records.append(record(name, data, 0o755 if name.startswith("python/") else 0o644))
    return records


@pytest.fixture
def inputs(tmp_path):
    source = tmp_path / "source with space é"
    runtime = tmp_path / "inert runtime"
    source_files = stage(
        source,
        {
            "pyproject.toml": b'[project]\nversion = "0.7.0"\n',
            "LICENSE": b"Synthetic project license\n",
            "THIRD_PARTY_NOTICES.md": b"Synthetic test notices only\n",
            builder.ADDON_PREFIX + "__init__.py": b"# inert UI fixture\n",
            builder.ADDON_PREFIX + "assets/icon.svg": b"<svg/>\n",
            builder.CORE_PREFIX + "__init__.py": b'__version__ = "0.7.0"\n',
            builder.CORE_PREFIX + "sidecar.py": b"# inert exact sidecar bytes\n",
            "docs/readme.md": b"Audited source, absent from extension\n",
            builder.BOOTSTRAP_SOURCE_PATH: (ROOT / builder.BOOTSTRAP_SOURCE_PATH).read_bytes(),
        },
    )
    runtime_files = stage(
        runtime,
        {
            "python/bin/python3.12": b"INERT INTERPRETER FIXTURE, DO NOT RUN\n",
            "packages/OCP/__init__.py": b"# inert package fixture\n",
            "licenses/test.txt": b"Synthetic test license\n",
        },
    )
    return {
        "source_root": source,
        "source_commit": "6" * 40,
        "source_files": source_files,
        "runtime_root": runtime,
        "runtime_files": runtime_files,
        "runtime_lock": b'{"status":"TEST_FIXTURE_ONLY"}\n',
        "platform": "linux-x64",
        "python_path": "python/bin/python3.12",
        "destination": tmp_path / "contract-one.zip",
    }


def test_private_staging_never_calls_publication_and_keeps_exact_bootstrap(
    inputs, tmp_path, monkeypatch
):
    def forbidden(*args):
        pytest.fail("private staging attempted publication")

    monkeypatch.setattr(builder.os, "link", forbidden)
    args = dict(inputs)
    args.pop("destination")
    receipt = builder.stage_contract_extension(**args, work_root=tmp_path)
    archive = Path(receipt["archive_path"])
    assert not receipt["published"] and receipt["destination"] is None
    assert receipt["bytes"] == archive.stat().st_size
    assert receipt["sha256"] == digest(archive.read_bytes())
    assert not inputs["destination"].exists()
    with zipfile.ZipFile(archive) as outer:
        payload = next(name for name in outer.namelist() if name.endswith("/payload.zip"))
        with zipfile.ZipFile(io.BytesIO(outer.read(payload))) as inner:
            assert inner.read("bootstrap.py") == (ROOT / builder.BOOTSTRAP_SOURCE_PATH).read_bytes()


def test_exact_deterministic_root_manifest_and_isolated_payload(inputs, tmp_path):
    first = builder.build_contract_extension(**inputs)
    second = builder.build_contract_extension(**(inputs | {"destination": tmp_path / "two.zip"}))
    assert first["sha256"] == second["sha256"]
    assert first["status"] == builder.STATUS
    assert first["bytes"] == inputs["destination"].stat().st_size
    with zipfile.ZipFile(inputs["destination"]) as archive:
        names = archive.namelist()
        assert names == sorted(names)
        assert "__init__.py" in names
        assert "blender_manifest.toml" in names
        assert not any(
            name.startswith(("mechanical_cad_blender/", "src/", "packages/")) for name in names
        )
        manifest = tomllib.loads(archive.read("blender_manifest.toml").decode())
        assert manifest["schema_version"] == "1.0.0"
        assert manifest["platforms"] == ["linux-x64"]
        assert manifest["version"] == "0.7.0"
        assert manifest["blender_version_min"] == "5.2.2"
        assert manifest["blender_version_max"] == "5.2.3"
        assert set(manifest["permissions"]) == {"files", "clipboard"}
        assert "wheels" not in manifest and "network" not in manifest["permissions"]
        assert json.loads(archive.read("BUILD_CONTRACT.json"))["status"] == builder.STATUS
        release = builder.CONTRACTS.parse_release_manifest(
            archive.read("release_identity.json"),
            expected_platform="linux-x64",
            limits=builder.CONTRACTS.BundleLimits(),
        )
        bundle = builder.CONTRACTS.parse_bundle_manifest(
            archive.read(release.manifest_path),
            release,
            limits=builder.CONTRACTS.BundleLimits(),
        )
        payload = archive.read(release.payload_path)
        assert digest(payload) == release.payload_sha256
        assert len(payload) == release.payload_size
        assert archive.getinfo(release.payload_path).compress_type == zipfile.ZIP_STORED
        for info in archive.infolist():
            assert info.date_time == (1980, 1, 1, 0, 0, 0)
            assert stat.S_IFMT(info.external_attr >> 16) == stat.S_IFREG
            assert stat.S_IMODE(info.external_attr >> 16) == 0o644
    with zipfile.ZipFile(io.BytesIO(payload)) as inner:
        assert set(inner.namelist()) == {entry.path for entry in bundle.files}
        for item in bundle.files:
            assert digest(inner.read(item.path)) == item.sha256
            assert len(inner.read(item.path)) == item.size
            assert stat.S_IMODE(inner.getinfo(item.path).external_attr >> 16) == item.mode
        assert (
            inner.read(builder.CORE_PREFIX + "sidecar.py")
            == (inputs["source_root"] / (builder.CORE_PREFIX + "sidecar.py")).read_bytes()
        )
        assert not any(name.startswith("blender_addon/") for name in inner.namelist())


def test_build_does_not_mutate_inputs_or_require_git(inputs, monkeypatch):
    before = {
        str(root): {
            p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()
        }
        for root in (inputs["source_root"], inputs["runtime_root"])
    }
    monkeypatch.setenv("PATH", "")
    builder.build_contract_extension(**inputs)
    for root, inventory in before.items():
        assert {
            p.relative_to(root).as_posix(): p.read_bytes()
            for p in Path(root).rglob("*")
            if p.is_file()
        } == inventory


@pytest.mark.parametrize(
    "which,path",
    [
        ("source", builder.ADDON_PREFIX + "__init__.py"),
        ("source", builder.CORE_PREFIX + "sidecar.py"),
        ("source", "docs/readme.md"),
        ("runtime", "python/bin/python3.12"),
        ("source", builder.BOOTSTRAP_SOURCE_PATH),
    ],
)
def test_mutated_input_fails_without_final_archive(inputs, which, path):
    (inputs[which + "_root"] / path).write_bytes(b"substituted")
    with pytest.raises(builder.BuildError, match="bytes differ|grew"):
        builder.build_contract_extension(**inputs)
    assert not inputs["destination"].exists()


@pytest.mark.parametrize(
    "which,path",
    [
        ("source", builder.ADDON_PREFIX + "unlisted.py"),
        ("source", builder.CORE_PREFIX + "unlisted.py"),
        ("runtime", "unexpected.dll"),
    ],
)
def test_extra_packaged_input_fails(inputs, which, path):
    (inputs[which + "_root"] / path).write_bytes(b"unlisted")
    with pytest.raises(builder.BuildError, match="inventory"):
        builder.build_contract_extension(**inputs)
    assert not inputs["destination"].exists()


@pytest.mark.parametrize(
    "which,path",
    [
        ("source", builder.ADDON_PREFIX + "__init__.py"),
        ("source", builder.BOOTSTRAP_SOURCE_PATH),
    ],
)
def test_symlink_input_fails(inputs, tmp_path, which, path):
    item = inputs[which + "_root"] / path
    target = tmp_path / "same-bytes"
    target.write_bytes(item.read_bytes())
    item.unlink()
    item.symlink_to(target)
    with pytest.raises(builder.BuildError, match="Symlink"):
        builder.build_contract_extension(**inputs)
    assert not inputs["destination"].exists()


def test_core_shadowing_runtime_rejected(inputs):
    path = builder.CORE_PREFIX + "__init__.py"
    inputs["runtime_files"] += stage(inputs["runtime_root"], {path: b"evil core"})
    with pytest.raises(builder.BuildError, match="shadow canonical"):
        builder.build_contract_extension(**inputs)


@pytest.mark.parametrize("path", ["../escape", "C:evil", "CON", "packages/../evil", "e\u0301"])
def test_nonportable_inventory_rejected(inputs, path):
    inputs["runtime_files"].append(record(path, b"x"))
    with pytest.raises(builder.CONTRACTS.BundleError):
        builder.build_contract_extension(**inputs)
    assert not inputs["destination"].exists()


def test_case_collision_is_not_silently_folded(inputs):
    inputs["runtime_files"] += stage(inputs["runtime_root"], {"Bootstrap.py": b"other"})
    with pytest.raises(builder.CONTRACTS.BundleError, match="collision"):
        builder.build_contract_extension(**inputs)


def test_generated_outer_name_cannot_be_shadowed(inputs):
    inputs["source_files"] += stage(
        inputs["source_root"],
        {
            builder.ADDON_PREFIX + "blender_manifest.toml": b"foreign manifest",
        },
    )
    with pytest.raises(builder.CONTRACTS.BundleError, match="Duplicate"):
        builder.build_contract_extension(**inputs)
    assert not inputs["destination"].exists()


def test_destination_preserved_and_output_inside_inputs_rejected(inputs):
    inputs["destination"].write_bytes(b"existing")
    with pytest.raises(builder.BuildError, match="already exists"):
        builder.build_contract_extension(**inputs)
    assert inputs["destination"].read_bytes() == b"existing"
    inputs["destination"] = inputs["source_root"] / "bad.zip"
    with pytest.raises(builder.BuildError, match="outside"):
        builder.build_contract_extension(**inputs)


def test_atomic_publish_failure_keeps_diagnostic_work_and_no_final(inputs, monkeypatch):
    def failed_link(*args):
        raise OSError("test injected publication failure")

    monkeypatch.setattr(os, "link", failed_link)
    with pytest.raises(OSError, match="injected"):
        builder.build_contract_extension(**inputs)
    assert not inputs["destination"].exists()
    work = list(inputs["destination"].parent.glob("standalone-contract-*"))
    assert len(work) == 1 and (work[0] / "extension.zip").is_file()
    assert json.loads((work[0] / "BUILD_RECEIPT.json").read_bytes())["published"] is False


@pytest.mark.parametrize("phase", ["private_stage_complete", "before_publication"])
def test_pre_publication_receipt_failure_never_publishes(inputs, monkeypatch, phase):
    original = Path.write_bytes

    def fail_receipt(path, data):
        if path.name == "BUILD_RECEIPT.json" and json.loads(data)["receipt_phase"] == phase:
            raise OSError("injected pre-publication receipt failure")
        return original(path, data)

    monkeypatch.setattr(Path, "write_bytes", fail_receipt)
    monkeypatch.setattr(os, "link", lambda *args: pytest.fail("published without receipt"))
    with pytest.raises(OSError, match="injected pre-publication receipt failure"):
        builder.build_contract_extension(**inputs)
    assert not inputs["destination"].exists()
    work = list(inputs["destination"].parent.glob("standalone-contract-*"))
    assert len(work) == 1 and (work[0] / "extension.zip").is_file()


def test_post_publication_receipt_failure_returns_explicit_committed_artifact(inputs, monkeypatch):
    original = Path.write_bytes

    def fail_post_publication_receipt(path, data):
        if (
            path.name == "BUILD_RECEIPT.json"
            and json.loads(data)["receipt_phase"] == "after_publication"
        ):
            assert inputs["destination"].is_file()
            raise OSError("injected post-publication receipt failure")
        return original(path, data)

    monkeypatch.setattr(Path, "write_bytes", fail_post_publication_receipt)
    receipt = builder.build_contract_extension(**inputs)
    assert receipt["published"] is True
    assert receipt["receipt_write_error"] == "OSError"
    assert receipt["receipt_phase"] == "after_publication_receipt_write_failed"
    assert digest(inputs["destination"].read_bytes()) == receipt["sha256"]
    saved = json.loads((Path(receipt["work_directory"]) / "BUILD_RECEIPT.json").read_bytes())
    assert saved["receipt_phase"] == "before_publication"


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX nonblocking FIFO control")
def test_nonregular_input_rejected_before_os_open(tmp_path, monkeypatch):
    path = tmp_path / "inert.fifo"
    os.mkfifo(path)
    monkeypatch.setattr(os, "open", lambda *a, **kw: pytest.fail("opened nonregular input"))
    with pytest.raises(builder.BuildError, match="regular"):
        with builder._open(path):
            pytest.fail("Nonregular input was admitted.")


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX regular-to-FIFO race control")
def test_regular_to_fifo_race_is_nonblocking_and_rejected(tmp_path, monkeypatch):
    path = tmp_path / "was-regular"
    path.write_bytes(b"old")
    original = os.open

    def replaced_before_open(target, flags, *args, **kwargs):
        path.unlink()
        os.mkfifo(path)
        assert flags & os.O_NONBLOCK
        return original(target, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", replaced_before_open)
    with pytest.raises(builder.BuildError, match="regular"):
        with builder._open(path):
            pytest.fail("Nonregular input was admitted.")


@pytest.mark.parametrize("path", ["_backend/foreign.bin", "_BACKEND/foreign.bin", "_backend"])
def test_addon_cannot_populate_generated_backend_namespace(inputs, path):
    inputs["source_files"] += stage(inputs["source_root"], {builder.ADDON_PREFIX + path: b"x"})
    with pytest.raises(builder.BuildError, match="generated backend namespace"):
        builder.build_contract_extension(**inputs)
    assert not inputs["destination"].exists()


def test_runtime_mutation_after_inventory_still_rejected_during_stream_copy(inputs, monkeypatch):
    original = builder._write_archive

    def change_then_copy(path, entries, limits):
        (inputs["runtime_root"] / inputs["python_path"]).write_bytes(b"mutated after inventory")
        return original(path, entries, limits)

    monkeypatch.setattr(builder, "_write_archive", change_then_copy)
    with pytest.raises(builder.BuildError, match="grew|bytes differ"):
        builder.build_contract_extension(**inputs)
    assert not inputs["destination"].exists()


def _materializer_exercise(inputs, tmp_path):
    result = builder.build_contract_extension(**inputs)
    package = tmp_path / "known synthetic package"
    package.mkdir()
    with zipfile.ZipFile(inputs["destination"]) as archive:
        # Only the just-built, independently enumerated synthetic test archive.
        for item in archive.infolist():
            path = package / item.filename
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(archive.read(item))
    name = "mcad_builder_materializer_tests"
    module = types.ModuleType(name)
    module.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
    sys.modules[name] = module
    materializer = importlib.import_module(name + ".runtime_bundle_materialize")

    class FakePin:
        bundle_id = result["bundle_id"]
        mode = "exclusive"

        def assert_held(self):
            pass  # Synthetic contract only, not OS lock qualification.

    cache = tmp_path / "cache"
    cache.mkdir()
    descriptor = materializer.materialize_bundle(
        package,
        cache,
        (package / "release_identity.json").read_bytes(),
        expected_platform="linux-x64",
        limits=builder.CONTRACTS.BundleLimits(),
        pin=FakePin(),
    )
    assert Path(descriptor.python_path).read_bytes().startswith(b"INERT INTERPRETER")
    assert (Path(descriptor.root) / "src/mechanical_cad/sidecar.py").read_bytes() == (
        inputs["source_root"] / "src/mechanical_cad/sidecar.py"
    ).read_bytes()
    assert not {"bpy", "OCP", "slvs"}.intersection(sys.modules)


def _run_isolated_materializer(inputs, tmp_path, forbidden=""):
    """Run the complete inert exercise without ambient pytest/native imports."""
    encoded = dict(inputs)
    for key in ("source_root", "runtime_root", "destination"):
        encoded[key] = str(encoded[key])
    encoded["runtime_lock"] = encoded["runtime_lock"].hex()
    program = r"""
import ast
import importlib.abc
import importlib.util
import json
import sys
import types
import zipfile
from pathlib import Path

ROOT = Path(sys.argv[1])
tmp_path = Path(sys.argv[2])
inputs = json.loads(sys.argv[3])
for key in ("source_root", "runtime_root", "destination"):
    inputs[key] = Path(inputs[key])
inputs["runtime_lock"] = bytes.fromhex(inputs["runtime_lock"])
forbidden = sys.argv[4]
roots = {"OCP", "OCC", "cadquery", "slvs", "bpy"}
assert not roots.intersection(sys.modules)
assert "mechanical_cad.kernel_ocp" not in sys.modules
attempts = []

class DenyNative(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in roots or fullname == "mechanical_cad.kernel_ocp":
            attempts.append(fullname)
            raise AssertionError("ISOLATED_NATIVE_IMPORT_BLOCKED:" + fullname)
        return None

blocker = DenyNative()
sys.meta_path.insert(0, blocker)
if forbidden:
    assert forbidden in roots | {"mechanical_cad.kernel_ocp"}
    if forbidden == "mechanical_cad.kernel_ocp":
        parent = types.ModuleType("mechanical_cad")
        parent.__path__ = []
        sys.modules["mechanical_cad"] = parent
    importlib.import_module(forbidden)
    raise AssertionError("native import blocker failed")

spec = importlib.util.spec_from_file_location(
    "isolated_standalone_builder", ROOT / "scripts/package_standalone_extension.py"
)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
# Extract only the inert exercise body. Never import this pytest module, its
# fixtures, production model, site-packages or any replacement validator.
path = ROOT / "tests/unit/test_standalone_extension_builder.py"
matches = [
    node for node in ast.parse(path.read_bytes()).body
    if isinstance(node, ast.FunctionDef) and node.name == "_materializer_exercise"
]
assert len(matches) == 1 and not matches[0].decorator_list
exec(compile(ast.Module(body=matches, type_ignores=[]), str(path), "exec"), globals())
_materializer_exercise(inputs, tmp_path)
assert sys.meta_path[0] is blocker
assert not attempts
assert not roots.intersection(sys.modules)
assert "mechanical_cad.kernel_ocp" not in sys.modules
print("ISOLATED_INERT_BUILD_MATERIALIZE_OK")
"""
    return subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            "-B",
            "-c",
            program,
            str(ROOT),
            str(tmp_path),
            json.dumps(encoded),
            forbidden,
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def test_generated_payload_is_admitted_by_actual_materializer_with_fake_pin(inputs, tmp_path):
    result = _run_isolated_materializer(inputs, tmp_path)
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert result.stdout == "ISOLATED_INERT_BUILD_MATERIALIZE_OK\n"
    assert result.stderr == ""


@pytest.mark.parametrize(
    "forbidden", ["OCP", "OCC", "cadquery", "slvs", "bpy", "mechanical_cad.kernel_ocp"]
)
def test_isolated_materializer_rejects_every_forbidden_import(inputs, tmp_path, forbidden):
    result = _run_isolated_materializer(inputs, tmp_path, forbidden)
    assert result.returncode != 0
    assert result.stdout == ""
    assert "AssertionError: ISOLATED_NATIVE_IMPORT_BLOCKED:" + forbidden in result.stderr


def test_isolated_materializer_ignores_parent_collection_imports(inputs, tmp_path, monkeypatch):
    poisoned = {name: types.ModuleType(name) for name in ("bpy", "OCP", "slvs")}
    for name, module in poisoned.items():
        monkeypatch.setitem(sys.modules, name, module)
    result = _run_isolated_materializer(inputs, tmp_path)
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert result.stdout == "ISOLATED_INERT_BUILD_MATERIALIZE_OK\n"
    assert result.stderr == ""
    assert all(sys.modules[name] is module for name, module in poisoned.items())


def test_resource_caps_apply_before_final_publish(inputs):
    limits = replace(builder.CONTRACTS.BundleLimits(), max_files=3)
    with pytest.raises(builder.CONTRACTS.BundleError, match="count"):
        builder.build_contract_extension(**inputs, limits=limits)
    assert not inputs["destination"].exists()


@pytest.mark.parametrize(
    "key,value",
    [
        ("source_commit", "not-a-commit"),
        ("platform", "windows-arm64"),
        ("runtime_lock", b""),
        ("runtime_lock", {"mutable": True}),
        ("python_path", "python/absent"),
    ],
)
def test_invalid_identity_or_entrypoint_rejected(inputs, key, value):
    inputs[key] = value
    with pytest.raises((builder.BuildError, builder.CONTRACTS.BundleError)):
        builder.build_contract_extension(**inputs)
    assert not inputs["destination"].exists()


def test_windows_uses_direct_interpreter_not_linux_or_path_fallback(inputs):
    inputs["platform"] = "windows-x64"
    with pytest.raises(builder.CONTRACTS.BundleError, match="direct bundled"):
        builder.build_contract_extension(**inputs)
    old = inputs["runtime_root"] / inputs["python_path"]
    data = old.read_bytes()
    old.unlink()
    inputs["runtime_files"] = [
        i for i in inputs["runtime_files"] if i["path"] != inputs["python_path"]
    ]
    inputs["runtime_files"] += stage(inputs["runtime_root"], {"python/python.exe": data})
    inputs["python_path"] = "python/python.exe"
    result = builder.build_contract_extension(**inputs)
    assert result["platform"] == "windows-x64"
    assert result["status"] == builder.STATUS  # synthetic success does not qualify Windows
    with zipfile.ZipFile(inputs["destination"]) as archive:
        constants = literal_launch_constants(archive)
        assert constants["PLATFORM"] == "windows-x64"
        assert constants["PYTHON_PATH"] == "python/python.exe"
        assert constants["PYTHON_VERSION"] == (3, 12, 10, "final", 0)
        assert constants["PYTHON_BITS"] == 64


@pytest.mark.parametrize("failure", ["fstat", "fdopen", "body", "wrapper_close", "none"])
def test_input_stream_keeps_raw_owner_until_one_close(tmp_path, monkeypatch, failure):
    path = tmp_path / "owned-input"
    path.write_bytes(b"known input")
    original_open, original_close = os.open, os.close
    original_fdopen, original_fstat = os.fdopen, os.fstat
    opened, closed, streams = [], [], []

    def tracked_open(*args, **kwargs):
        fd = original_open(*args, **kwargs)
        opened.append(fd)
        return fd

    def checked_fstat(fd):
        if failure == "fstat" and fd in opened:
            raise OSError("injected fstat failure")
        return original_fstat(fd)

    def checked_fdopen(fd, *args, **kwargs):
        assert kwargs.get("closefd") is False
        # Match CPython's partial-construction cleanup: closing a wrapper
        # with closefd=False must not consume its caller-owned raw descriptor.
        stream = original_fdopen(fd, *args, **kwargs)
        streams.append(stream)
        if failure == "fdopen":
            stream.close()
            assert original_fstat(fd)
            raise OSError("injected fdopen failure")
        if failure == "wrapper_close":

            class Wrapper:
                def read(self):
                    return stream.read()

                def close(self):
                    stream.close()
                    assert original_fstat(fd)
                    raise OSError("injected wrapper close failure")

            return Wrapper()
        return stream

    def tracked_close(fd):
        closed.append(fd)
        return original_close(fd)

    monkeypatch.setattr(os, "open", tracked_open)
    monkeypatch.setattr(os, "close", tracked_close)
    monkeypatch.setattr(os, "fstat", checked_fstat)
    monkeypatch.setattr(os, "fdopen", checked_fdopen)

    def exercise():
        with builder._open(path) as stream:
            assert stream.read() == b"known input"
            if failure == "body":
                raise OSError("injected body failure")

    if failure == "none":
        exercise()
    else:
        with pytest.raises(OSError, match="injected"):
            exercise()
    assert len(opened) == 1 and closed == opened
    assert all(stream.closed for stream in streams)
    with pytest.raises(OSError):
        original_fstat(opened[0])


def test_uncertain_input_close_never_retries_reused_descriptor(tmp_path, monkeypatch):
    path = tmp_path / "owned-input"
    path.write_bytes(b"known input")
    replacement = tmp_path / "unrelated-input"
    replacement.write_bytes(b"unrelated")
    original_close, original_open = os.close, os.open
    closed, reused = [], []

    def close_and_reuse(fd):
        closed.append(fd)
        original_close(fd)
        other = original_open(replacement, os.O_RDONLY)
        reused.append(other)
        assert other == fd
        raise OSError("uncertain raw close")

    monkeypatch.setattr(os, "close", close_and_reuse)
    try:
        with pytest.raises(OSError, match="uncertain raw close"):
            with builder._open(path) as stream:
                assert stream.read() == b"known input"
        assert len(closed) == 1 and closed == reused
        assert os.read(reused[0], 20) == b"unrelated"
    finally:
        for fd in reused:
            original_close(fd)


def literal_launch_constants(archive):
    """Inspect generated Blender bytes without importing or executing the loader."""
    tree = ast.parse(archive.read(builder.GENERATED_LAUNCH_MODULE))
    result = {}
    for node in tree.body:
        assert type(node) is ast.Assign
        assert len(node.targets) == 1 and type(node.targets[0]) is ast.Name
        name = node.targets[0].id
        assert name.isupper() and name not in result
        result[name] = ast.literal_eval(node.value)
    return result


def test_trusted_child_and_literal_launch_identity_are_bound_without_circular_hash(inputs):
    result = builder.build_contract_extension(**inputs)
    trusted = (ROOT / builder.BOOTSTRAP_SOURCE_PATH).read_bytes()
    with zipfile.ZipFile(inputs["destination"]) as archive:
        values = literal_launch_constants(archive)
        release_data = archive.read("release_identity.json")
        release = json.loads(release_data)
        manifest_data = archive.read(release["manifest_path"])
        manifest = json.loads(manifest_data)
        payload_data = archive.read(release["payload_path"])
        record_data = json.loads(archive.read("BUILD_CONTRACT.json"))
        assert values == {
            "SCHEMA_VERSION": 1,
            "BUILD_STATUS": builder.STATUS,
            "SOURCE_COMMIT": inputs["source_commit"],
            "RUNTIME_LOCK_SHA256": digest(inputs["runtime_lock"]),
            "BUNDLE_ID": release["bundle_id"],
            "PLATFORM": "linux-x64",
            "PYTHON_IMPLEMENTATION": "cpython",
            "PYTHON_VERSION": (3, 12, 15, "final", 0),
            "PYTHON_CACHE_TAG": "cpython-312",
            "PYTHON_BITS": 64,
            "PYTHON_PATH": "python/bin/python3.12",
            "PYTHON_FLAGS": ("-I", "-S", "-B", "-X", "utf8", "-c"),
            "BOOTSTRAP_PATH": "bootstrap.py",
            "BOOTSTRAP_SHA256": digest(trusted),
            "RELEASE_IDENTITY_PATH": "release_identity.json",
            "RELEASE_IDENTITY_BYTES": release_data,
            "RELEASE_IDENTITY_SHA256": digest(release_data),
            "BUNDLE_MANIFEST_SHA256": digest(manifest_data),
            "PAYLOAD_SHA256": digest(payload_data),
            "ENTRY_LOADER": builder._entry_loader(trusted),
        }
        loader = values["ENTRY_LOADER"]
        assert len(loader.encode("ascii")) <= 4096
        assert values["BOOTSTRAP_SHA256"] in loader
        assert inputs["source_commit"] not in loader
        assert record_data["bootstrap_source_path"] == builder.BOOTSTRAP_SOURCE_PATH
        assert record_data["bootstrap_sha256"] == digest(trusted)
        assert record_data["release_identity_sha256"] == digest(release_data)
        assert record_data["generated_launch_sha256"] == digest(
            archive.read(builder.GENERATED_LAUNCH_MODULE)
        )
        assert not any("standalone_child_bootstrap" in name for name in archive.namelist())
        assert result["sha256"] not in release_data.decode()
        assert result["sha256"] not in archive.read(builder.GENERATED_LAUNCH_MODULE).decode()
    with zipfile.ZipFile(io.BytesIO(payload_data)) as payload:
        assert payload.read("bootstrap.py") == trusted
        assert "release_identity.json" not in payload.namelist()
        assert builder.GENERATED_LAUNCH_MODULE not in payload.namelist()
        assert next(item for item in manifest["files"] if item["path"] == "bootstrap.py") == (
            record("bootstrap.py", trusted)
        )
    assert "entry_loader" not in release and "entry_loader" not in manifest


@pytest.mark.parametrize("replacement", [None, "scripts/other_bootstrap.py"])
def test_exact_bootstrap_source_path_is_required(inputs, replacement):
    inputs["source_files"] = [
        item for item in inputs["source_files"] if item["path"] != builder.BOOTSTRAP_SOURCE_PATH
    ]
    if replacement is not None:
        inputs["source_files"] += stage(
            inputs["source_root"],
            {replacement: (ROOT / builder.BOOTSTRAP_SOURCE_PATH).read_bytes()},
        )
    with pytest.raises(builder.BuildError, match="lacks required"):
        builder.build_contract_extension(**inputs)
    assert not inputs["destination"].exists()


def test_self_consistent_foreign_child_source_is_rejected_before_execution(inputs, tmp_path):
    marker = tmp_path / "foreign-code-executed"
    foreign = f"from pathlib import Path\nPath({str(marker)!r}).touch()\n".encode()
    (inputs["source_root"] / builder.BOOTSTRAP_SOURCE_PATH).write_bytes(foreign)
    inputs["source_files"] = [
        record(item["path"], foreign) if item["path"] == builder.BOOTSTRAP_SOURCE_PATH else item
        for item in inputs["source_files"]
    ]
    with pytest.raises(builder.BuildError, match="bytes differ"):
        builder.build_contract_extension(**inputs)
    assert not marker.exists() and not inputs["destination"].exists()


@pytest.mark.parametrize("size", [0, 65537])
def test_bootstrap_fixed_size_bound_precedes_factory_execution(inputs, monkeypatch, size):
    data = b"#" * size
    (inputs["source_root"] / builder.BOOTSTRAP_SOURCE_PATH).write_bytes(data)
    inputs["source_files"] = [
        record(item["path"], data) if item["path"] == builder.BOOTSTRAP_SOURCE_PATH else item
        for item in inputs["source_files"]
    ]
    monkeypatch.setattr(builder, "_entry_loader", lambda *a: pytest.fail("factory ran"))
    with pytest.raises(builder.BuildError, match="fixed byte limit"):
        builder.build_contract_extension(**inputs)
    assert not inputs["destination"].exists()


@pytest.mark.parametrize(
    "path",
    [
        "standalone_launch_constants.py",
        "STANDALONE_LAUNCH_CONSTANTS.PY",
        "standalone_launch_constants/__init__.py",
        "standalone_launch_constants.py/data",
        "standalone_launch_constants.pyc",
        "standalone_launch_constants.cpython-312-x86_64-linux-gnu.so",
        "__pycache__/standalone_launch_constants.cpython-312.pyc",
        "__PYCACHE__/STANDALONE_LAUNCH_CONSTANTS.cpython-312.pyc",
    ],
)
def test_source_cannot_shadow_generated_launch_module_or_bytecode(inputs, path):
    inputs["source_files"] += stage(inputs["source_root"], {builder.ADDON_PREFIX + path: b"x"})
    with pytest.raises(builder.BuildError, match="generated launch namespace"):
        builder.build_contract_extension(**inputs)
    assert not inputs["destination"].exists()


@pytest.mark.parametrize("path", ["bootstrap.py", "Bootstrap.PY", "bootstrap.py/foreign.py"])
def test_runtime_cannot_supply_generated_child_bootstrap(inputs, path):
    inputs["runtime_files"] += stage(inputs["runtime_root"], {path: b"# foreign bootstrap\n"})
    with pytest.raises(builder.BuildError, match="bootstrap.py namespace collision"):
        builder.build_contract_extension(**inputs)
    assert not inputs["destination"].exists()


@pytest.mark.parametrize("loader", [None, b"loader", "", "\0", "é", "#" * 4097])
def test_child_factory_must_return_bounded_ascii_launch_text(inputs, monkeypatch, loader):
    def fake_factory(_code, namespace):
        namespace["entry_loader"] = lambda _digest: loader

    monkeypatch.setattr(builder, "exec", fake_factory, raising=False)
    with pytest.raises(builder.BuildError, match="fixed launch contract"):
        builder.build_contract_extension(**inputs)
    assert not inputs["destination"].exists()


def test_factory_failure_is_explicit_and_does_not_publish(inputs, monkeypatch):
    def failed_factory(*args):
        raise RuntimeError("synthetic build factory failure")

    monkeypatch.setattr(builder, "exec", failed_factory, raising=False)
    with pytest.raises(builder.BuildError, match="launch factory failed"):
        builder.build_contract_extension(**inputs)
    assert not inputs["destination"].exists()


def test_child_factory_accepts_exact_loader_byte_bound(monkeypatch):
    def fake_factory(_code, namespace):
        namespace["entry_loader"] = lambda _digest: "#" * 4096

    monkeypatch.setattr(builder, "exec", fake_factory, raising=False)
    assert builder._entry_loader(b"# synthetic factory contract only") == "#" * 4096


def test_metadata_cannot_supply_loader_text(inputs, tmp_path):
    marker = tmp_path / "descriptor-code-executed"
    evil = f"from pathlib import Path; Path({str(marker)!r}).touch()"
    inputs["runtime_lock"] = json.dumps({"entry_loader": evil, "bootstrap": evil}).encode()
    builder.build_contract_extension(**inputs)
    with zipfile.ZipFile(inputs["destination"]) as archive:
        values = literal_launch_constants(archive)
        assert evil not in values["ENTRY_LOADER"]
        assert values["ENTRY_LOADER"] == builder._entry_loader(
            (ROOT / builder.BOOTSTRAP_SOURCE_PATH).read_bytes()
        )
    assert not marker.exists()


def test_linux_rejects_inventoried_alternative_interpreter_location(inputs):
    inputs["runtime_files"] += stage(
        inputs["runtime_root"], {"python/bin/python": b"INERT ALTERNATIVE, DO NOT RUN"}
    )
    inputs["python_path"] = "python/bin/python"
    with pytest.raises(builder.BuildError, match=r"direct bundled CPython 3\.12 interpreter"):
        builder.build_contract_extension(**inputs)
    assert not inputs["destination"].exists()


def test_reordered_exact_inventories_produce_identical_archive(inputs, tmp_path):
    first = builder.build_contract_extension(**inputs)
    second = builder.build_contract_extension(
        **(
            inputs
            | {
                "destination": tmp_path / "reordered.zip",
                "source_files": list(reversed(inputs["source_files"])),
                "runtime_files": list(reversed(inputs["runtime_files"])),
            }
        )
    )
    assert first["sha256"] == second["sha256"]


def test_changed_source_release_identity_changes_constants_without_changing_child(inputs, tmp_path):
    builder.build_contract_extension(**inputs)
    second = tmp_path / "different-source-identity.zip"
    builder.build_contract_extension(
        **(
            inputs
            | {
                "destination": second,
                "source_commit": "7" * 40,
            }
        )
    )
    with zipfile.ZipFile(inputs["destination"]) as one, zipfile.ZipFile(second) as two:
        first, next_values = literal_launch_constants(one), literal_launch_constants(two)
        assert first["BOOTSTRAP_SHA256"] == next_values["BOOTSTRAP_SHA256"]
        assert first["ENTRY_LOADER"] == next_values["ENTRY_LOADER"]
        assert first["BUNDLE_ID"] != next_values["BUNDLE_ID"]
        assert first["RELEASE_IDENTITY_SHA256"] != next_values["RELEASE_IDENTITY_SHA256"]
        assert first["BUNDLE_MANIFEST_SHA256"] != next_values["BUNDLE_MANIFEST_SHA256"]
        assert first["PAYLOAD_SHA256"] == next_values["PAYLOAD_SHA256"]


def test_candidate_version_is_consistent_across_core_addon_and_launch_gates():
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    assert len(version.split(".")) == 3 and all(part.isdigit() for part in version.split("."))
    core = ast.parse((ROOT / "src/mechanical_cad/__init__.py").read_text())
    assert (
        next(
            ast.literal_eval(node.value)
            for node in core.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "__version__"
                for target in node.targets
            )
        )
        == version
    )
    addon = ast.parse((ROOT / "blender_addon/mechanical_cad_blender/__init__.py").read_text())
    assert next(
        ast.literal_eval(node.value)["version"]
        for node in addon.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "bl_info" for target in node.targets)
    ) == tuple(int(component) for component in version.split("."))
    verifier = ast.parse((ROOT / "scripts/verify_sidecar_install.py").read_text())
    assert (
        next(
            ast.literal_eval(node.value)
            for node in verifier.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "EXPECTED_VERSION"
                for target in node.targets
            )
        )
        == version
    )
    bootstrap = ast.parse((ROOT / "scripts/standalone_child_bootstrap.py").read_text())
    gates = [
        node
        for node in ast.walk(bootstrap)
        if isinstance(node, ast.Compare)
        and isinstance(node.left, ast.Attribute)
        and node.left.attr == "__version__"
    ]
    assert len(gates) == 1 and len(gates[0].ops) == 1
    assert isinstance(gates[0].ops[0], ast.NotEq)
    assert ast.literal_eval(gates[0].comparators[0]) == version
