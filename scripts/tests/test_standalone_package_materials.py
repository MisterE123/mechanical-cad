"""Independent synthetic build-tool controls. No CAD/runtime/source material is run."""

import ast
import builtins
import copy
import hashlib
import importlib
import importlib.util
import io
import json
import os
import socket
import stat
import struct
import subprocess
import sys
import tomllib
import types
import zipfile
from contextlib import contextmanager
from dataclasses import asdict, fields, replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PROJECT_VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
SPEC = importlib.util.spec_from_file_location(
    "materials_wrapper_tests", ROOT / "scripts/package_standalone_materials.py"
)
w = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = w
SPEC.loader.exec_module(w)
b = w.BUILDER
LIMITS = w.MaterialsLimits(chunk_bytes=17, reserve_free_bytes=0)
PINNED = {
    "scripts/package_standalone_extension.py": "1fd634b545480816a277b0707f27488e3253b8aae1a47090fe99c806b1d92750",
    "scripts/standalone_child_bootstrap.py": "df85aeb34905ca1e18f34610ecbf74b8c00fa26738f520e65f9bc278b058188c",
    "blender_addon/mechanical_cad_blender/runtime_bundle_manifest.py": "8e6f66dbc12ef135795b247dcf244805f188cf0a91ac30ab5b4ccf8435a0f246",
}
HISTORICAL = ROOT / "tests/fixtures/standalone/materials_07f2550"
PLATFORM_CHANGES_SHA256 = "4d666e6cd43252454b0161922e0ad5b2e5020f3563aa63945069c0681103900a"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def reviewed_materials_sources(manifest_bytes=None, originals=None):
    """Restore reviewed source bytes as data, never import historical builders."""
    if manifest_bytes is None:
        manifest_bytes = (HISTORICAL / "reviewed_platform_changes.json").read_bytes()
    assert digest(manifest_bytes) == PLATFORM_CHANGES_SHA256
    manifest = json.loads(manifest_bytes)
    assert manifest["schema_version"] == 1
    expected_paths = set(PINNED) - {"blender_addon/mechanical_cad_blender/runtime_bundle_manifest.py"}
    assert set(manifest["files"]) == expected_paths
    result = {}
    for path, record in manifest["files"].items():
        original = (
            (HISTORICAL / record["original_file"]).read_bytes()
            if originals is None else originals[path]
        )
        assert digest(original) == PINNED[path]
        source = original.decode("utf-8")
        for change in record["changes"]:
            assert set(change) == {"before", "after"}
            assert change["before"] and source.count(change["before"]) == 1
            source = source.replace(change["before"], change["after"], 1)
        result[path] = source.encode("utf-8")
    return result


def assert_reviewed_materials_source(path, data):
    if path == "scripts/standalone_child_bootstrap.py":
        current = f'package.__version__ != "{PROJECT_VERSION}"'.encode()
        assert data.count(current) == 1
        data = data.replace(current, b'package.__version__ != "0.6.0"')
    reviewed = reviewed_materials_sources()
    if path in reviewed:
        assert data == reviewed[path]
    else:
        assert digest(data) == PINNED[path]


def record(path, data, mode=0o644):
    return {"path": path, "size": len(data), "sha256": digest(data), "mode": mode}


def stage(root, entries):
    result = []
    for name, data in entries.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        result.append(record(name, data, 0o755 if name == "python/bin/python3.12" else 0o644))
    return result


def inventory_hash(records):
    return digest(b._json(sorted(records, key=lambda item: item["path"])))


def map_value(inputs):
    return json.loads(inputs["materials_map"])


def pins(inputs, value=None):
    value = map_value(inputs) if value is None else value
    value.update(
        source_commit=inputs["source_commit"],
        platform=inputs["platform"],
        runtime_lock_sha256=digest(inputs["runtime_lock"]),
        source_inventory_sha256=inventory_hash(inputs["source_files"]),
        runtime_inventory_sha256=inventory_hash(inputs["runtime_files"]),
        materials_inventory_sha256=inventory_hash(inputs["materials_files"]),
    )
    inputs["materials_map"] = b._json(value)
    return value


@pytest.fixture
def inputs(tmp_path):
    source, runtime, materials = (tmp_path / name for name in ("source é", "runtime", "materials"))
    source_files = stage(
        source,
        {
            "pyproject.toml": f'[project]\nversion = "{PROJECT_VERSION}"\n'.encode(),
            "LICENSE": b"Synthetic project license.\n",
            "THIRD_PARTY_NOTICES.md": b"Synthetic test notices only.\n",
            b.ADDON_PREFIX + "__init__.py": b"# inert add-on\n",
            b.ADDON_PREFIX + "assets/icon.svg": b"<svg/>\n",
            b.CORE_PREFIX + "__init__.py": b"# inert core\n",
            b.CORE_PREFIX + "sidecar.py": b"# never execute fixture\n",
            b.BOOTSTRAP_SOURCE_PATH: (ROOT / b.BOOTSTRAP_SOURCE_PATH).read_bytes(),
        },
    )
    runtime_files = stage(
        runtime,
        {
            "python/bin/python3.12": b"INERT INTERPRETER; NEVER RUN\n",
            "packages/OCP/inert.so": b"INERT NATIVE LIBRARY; NEVER LOAD\n",
        },
    )
    nested = io.BytesIO()
    with zipfile.ZipFile(nested, "w") as archive:
        archive.writestr("recipe.py", f"open({str(tmp_path / 'EXECUTED')!r}, 'w').write('bad')")
        archive.writestr("hooks/__init__.py", "raise AssertionError('SOURCE MATERIAL EXECUTED')")
    materials_files = stage(
        materials,
        {
            "sources/dependency.zip": nested.getvalue(),
            "sources/shared.tar.gz": b"OPAQUE SHARED SOURCE ARCHIVE\0\xff",
            "sources/project.tar.xz": b"OPAQUE PROJECT SOURCE ARCHIVE\n",
            "licenses/NOTICE.txt": b"Exact caller notice bytes\r\n\xff\x00",
            "licenses/UPSTREAM.txt": b"Exact upstream alternative text; no selection.\n",
            "licenses/provenance.json": b'{"declared_only":true}\n',
        },
    )
    value = {
        "schema_version": 1,
        "coverage_scope": w.COVERAGE,
        "components": [
            {
                "id": "runtime",
                "kind": "external_runtime",
                "name": "Inert runtime",
                "declared_identity": "Declared synthetic input",
                "source_paths": ["sources/dependency.zip", "sources/shared.tar.gz"],
                "notice_paths": ["licenses/NOTICE.txt", "licenses/UPSTREAM.txt"],
                "provenance_paths": ["licenses/provenance.json"],
                "unresolved_issue_ids": ["rebuild", "rights"],
            },
            {
                "id": "headers",
                "kind": "external_runtime",
                "name": "Shared static headers",
                "declared_identity": "Declared embedded contribution",
                "source_paths": ["sources/shared.tar.gz"],
                "notice_paths": ["licenses/NOTICE.txt"],
                "provenance_paths": [],
                "unresolved_issue_ids": ["rights"],
            },
            {
                "id": "project",
                "kind": "project_package",
                "name": "Project source declaration",
                "declared_identity": "Synthetic application/backend/bootstrap/build source declaration",
                "source_paths": ["sources/project.tar.xz"],
                "notice_paths": ["licenses/NOTICE.txt"],
                "provenance_paths": [],
                "unresolved_issue_ids": [],
            },
        ],
        "runtime_bindings": [
            {"path": item["path"], "component_ids": ["runtime", "headers"]}
            for item in runtime_files
        ],
        "unresolved_issues": [
            {
                "id": "rebuild",
                "role": "other_unresolved",
                "description": "Recipient rebuild not established.",
            },
            {
                "id": "rights",
                "role": "other_unresolved",
                "description": "Redistribution permission not established.",
            },
        ],
    }
    result = {
        "source_root": source,
        "source_commit": "6" * 40,
        "source_files": source_files,
        "runtime_root": runtime,
        "runtime_files": runtime_files,
        "runtime_lock": b'{"status":"SYNTHETIC_ONLY"}\n',
        "platform": "linux-x64",
        "python_path": "python/bin/python3.12",
        "destination": tmp_path / "extended.zip",
        "materials_root": materials,
        "materials_files": materials_files,
        "limits": LIMITS,
    }
    pins(result, value)
    return result


def parse(inputs, value=None, **overrides):
    arguments = {
        "source_commit": inputs["source_commit"],
        "platform": inputs["platform"],
        "runtime_lock": inputs["runtime_lock"],
        "limits": inputs["limits"],
    }
    for name in ("source", "runtime", "materials"):
        arguments[name] = w.C.validate_file_inventory(inputs[name + "_files"], limits=LIMITS)
    return w._parse_map(
        inputs["materials_map"] if value is None else b._json(value), **(arguments | overrides)
    )


def build(inputs, **overrides):
    return w.build_materials_extension(**(inputs | overrides))


def files(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_determinism_exact_bytes_shared_components_and_base_identity(inputs, tmp_path):
    before = {key: files(inputs[key]) for key in ("source_root", "runtime_root", "materials_root")}
    first = build(inputs)
    equivalent = copy.deepcopy(inputs)
    value = map_value(equivalent)
    for name in ("components", "runtime_bindings", "unresolved_issues"):
        value[name].reverse()
    for component in value["components"]:
        for key in ("source_paths", "notice_paths", "provenance_paths", "unresolved_issue_ids"):
            component[key].reverse()
    for binding in value["runtime_bindings"]:
        binding["component_ids"].reverse()
    for key in ("source_files", "runtime_files", "materials_files"):
        equivalent[key].reverse()
    equivalent["materials_map"] = b._json(value)
    second = build(equivalent, destination=tmp_path / "equivalent.zip")
    assert first["sha256"] == second["sha256"] == digest(inputs["destination"].read_bytes())
    assert first["bytes"] == inputs["destination"].stat().st_size
    assert first["status"] == w.STATUS and first["published"] is True
    assert first["sha256"] != first["base_zip_sha256"]
    with zipfile.ZipFile(Path(first["work_directory"]) / "base.zip") as base:
        with zipfile.ZipFile(inputs["destination"]) as final:
            assert final.namelist()[: len(base.namelist())] == base.namelist()
            for info in base.infolist():
                assert base.read(info) == final.read(info.filename)
                assert w._zip_metadata(info) == w._zip_metadata(final.getinfo(info.filename))
            assert len(final.namelist()) == len(set(final.namelist())) == first["outer_files"]
            assert sum(name.endswith("/payload.zip") for name in final.namelist()) == 1
            assert "blender_manifest.toml" in final.namelist()
            for item in inputs["materials_files"]:
                assert final.read(item["path"]) == before["materials_root"][item["path"]]
            for info in final.infolist():
                assert info.date_time == (1980, 1, 1, 0, 0, 0)
                assert info.external_attr == (stat.S_IFREG | 0o644) << 16
            document = json.loads(final.read("PACKAGED_MATERIALS.json"))
            assert document["base_zip_sha256"] == first["base_zip_sha256"]
            assert document["materials_map_sha256"] == digest(b._json(document["materials_map"]))
            assert document["materials_inventory"] == sorted(
                inputs["materials_files"], key=lambda i: i["path"]
            )
            assert (
                document["materials_map"]["unresolved_issues"] == parse(inputs)["unresolved_issues"]
            )
            assert "sha256" not in document and "destination" not in document
            assert not {"approved", "release_ready", "license_cleared"} & document.keys()
    for key, snapshot in before.items():
        assert files(inputs[key]) == snapshot
    assert not (tmp_path / "EXECUTED").exists()
    work = Path(first["work_directory"])
    assert json.loads((work / "MATERIALS_RECEIPT.before.json").read_bytes())["published"] is False
    assert json.loads((work / "MATERIALS_RECEIPT.json").read_bytes())["published"] is True


def test_material_change_does_not_change_any_base_member_or_live_identity(inputs, tmp_path):
    first = build(inputs)
    path = "licenses/NOTICE.txt"
    data = b"Different exact caller material bytes.\n"
    (inputs["materials_root"] / path).write_bytes(data)
    inputs["materials_files"] = [
        record(path, data) if i["path"] == path else i for i in inputs["materials_files"]
    ]
    pins(inputs)
    second = build(inputs, destination=tmp_path / "changed.zip")
    assert first["sha256"] != second["sha256"]
    assert first["base_zip_sha256"] == second["base_zip_sha256"]
    assert first["bundle_id"] == second["bundle_id"]
    with (
        zipfile.ZipFile(inputs["destination"]) as one,
        zipfile.ZipFile(tmp_path / "changed.zip") as two,
    ):
        release = json.loads(one.read("release_identity.json"))
        for name in (
            "release_identity.json",
            "BUILD_CONTRACT.json",
            b.GENERATED_LAUNCH_MODULE,
            release["payload_path"],
            release["manifest_path"],
            "runtime-lock.json",
        ):
            assert one.read(name) == two.read(name)
        manifest = json.loads(one.read(release["manifest_path"]))
        assert not any(i["path"].startswith(("sources/", "licenses/")) for i in manifest["files"])
        with zipfile.ZipFile(io.BytesIO(one.read(release["payload_path"]))) as payload:
            assert not any(n.startswith(("sources/", "licenses/")) for n in payload.namelist())


@pytest.mark.parametrize(
    "raw",
    [
        b'{"schema_version":1,"schema_version":1}',
        b"{}",
        b"[]",
        b"null",
        b"false",
        b"NaN",
        b"{",
        b"\xff",
        b'{"bad":Infinity}',
        b"[" * 9 + b"]" * 9,
    ],
)
def test_strict_json_rejected_before_builder(inputs, raw, monkeypatch):
    monkeypatch.setattr(b, "build_contract_extension", lambda **kw: pytest.fail("builder called"))
    with pytest.raises(w.C.BundleError):
        build(inputs, materials_map=raw)
    assert not inputs["destination"].exists()


def set_field(value, path, replacement):
    parts = path.split(".")
    for part in parts[:-1]:
        value = value[int(part)] if type(value) is list else value[part]
    value[int(parts[-1]) if type(value) is list else parts[-1]] = replacement


@pytest.mark.parametrize(
    "path,replacement",
    [
        ("schema_version", True),
        ("schema_version", 2),
        ("schema_version", 1.0),
        ("source_commit", "F" * 40),
        ("source_commit", "7" * 40),
        ("platform", "windows-x64"),
        ("coverage_scope", "complete-dependency-discovery"),
        ("runtime_lock_sha256", "x" * 64),
        ("runtime_lock_sha256", "0" * 64),
        ("source_inventory_sha256", "0" * 64),
        ("runtime_inventory_sha256", "0" * 64),
        ("materials_inventory_sha256", "0" * 64),
        ("components", []),
        ("components", {}),
        ("components.0.id", "bad id"),
        ("components.0.id", "é"),
        ("components.0.id", "i" * 129),
        ("components.0.kind", "legal_approval"),
        ("components.0.name", ""),
        ("components.0.name", True),
        ("components.0.name", "control\ntext"),
        ("components.0.name", "\ud800"),
        ("components.0.name", "é" * 513),
        ("components.0.declared_identity", "x" * 1025),
        ("components.0.source_paths", ["sources/absent.zip"]),
        ("components.0.source_paths", ["sources/dependency.zip", "sources/dependency.zip"]),
        ("components.0.source_paths", ["licenses/NOTICE.txt"]),
        ("components.0.notice_paths", ["sources/dependency.zip"]),
        ("components.0.provenance_paths", ["../licenses/NOTICE.txt"]),
        ("components.0.unresolved_issue_ids", ["unknown"]),
        ("components.0.unresolved_issue_ids", ["rights", "rights"]),
        ("runtime_bindings.0.path", "missing/runtime"),
        ("runtime_bindings.0.component_ids", []),
        ("runtime_bindings.0.component_ids", ["runtime", "runtime"]),
        ("runtime_bindings.0.component_ids", ["project"]),
        ("runtime_bindings.0.component_ids", ["unknown"]),
        ("unresolved_issues.0.id", "bad\0id"),
        ("unresolved_issues.0.role", "untyped"),
        ("unresolved_issues.0.role", []),
        ("unresolved_issues.0.description", "x" * 4097),
    ],
)
def test_closed_map_fields_and_relations(inputs, path, replacement):
    value = map_value(inputs)
    set_field(value, path, replacement)
    with pytest.raises(w.C.BundleError):
        parse(inputs, value)


@pytest.mark.parametrize(
    "object_path", ["", "components.0", "runtime_bindings.0", "unresolved_issues.0"]
)
@pytest.mark.parametrize("operation", ["unknown", "missing"])
def test_exact_object_fields(inputs, object_path, operation):
    value = map_value(inputs)
    target = value
    for part in filter(None, object_path.split(".")):
        target = target[int(part)] if type(target) is list else target[part]
    if operation == "unknown":
        target["approved"] = True
    else:
        del target[next(iter(target))]
    with pytest.raises(w.C.BundleError):
        parse(inputs, value)


@pytest.mark.parametrize(
    "case",
    [
        "duplicate_component",
        "duplicate_binding",
        "uncovered_runtime",
        "unused_component",
        "unused_material",
        "unused_issue",
        "duplicate_issue",
        "no_project",
        "two_projects",
    ],
)
def test_complete_declared_coverage_required(inputs, case):
    value = map_value(inputs)
    if case == "duplicate_component":
        value["components"].append(copy.deepcopy(value["components"][0]))
    elif case == "duplicate_binding":
        value["runtime_bindings"].append(copy.deepcopy(value["runtime_bindings"][0]))
    elif case == "uncovered_runtime":
        value["runtime_bindings"].pop()
    elif case == "unused_component":
        for binding in value["runtime_bindings"]:
            binding["component_ids"].remove("headers")
    elif case == "unused_material":
        value["components"][0]["provenance_paths"] = []
    elif case == "unused_issue":
        value["components"][0]["unresolved_issue_ids"].remove("rebuild")
    elif case == "duplicate_issue":
        value["unresolved_issues"].append(copy.deepcopy(value["unresolved_issues"][0]))
    elif case == "no_project":
        value["components"].pop()
    elif case == "two_projects":
        value["components"].append(value["components"][-1] | {"id": "second-project"})
    with pytest.raises(w.C.BundleError):
        parse(inputs, value)


def test_missing_source_and_notice_need_separate_typed_roles(inputs):
    value = map_value(inputs)
    component = value["components"][1]
    component["source_paths"], component["notice_paths"] = [], []
    with pytest.raises(w.BuildError, match="typed unresolved"):
        parse(inputs, value)
    for role in ("missing_source_material", "missing_notice_material"):
        value["unresolved_issues"].append(
            {"id": role, "role": role, "description": "Not supplied."}
        )
        component["unresolved_issue_ids"].append(role)
        if role == "missing_source_material":
            with pytest.raises(w.BuildError, match="typed unresolved"):
                parse(inputs, value)
    inputs["materials_map"] = b._json(value)
    build(inputs)
    with zipfile.ZipFile(inputs["destination"]) as archive:
        record_value = json.loads(archive.read("PACKAGED_MATERIALS.json"))
        assert len(record_value["materials_map"]["unresolved_issues"]) == 4
        assert b"missing_source_material" in archive.read("MATERIALS.md")
        assert b"missing_notice_material" in archive.read("MATERIALS.md")


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_components", 2),
        ("max_issues", 1),
        ("max_runtime_bindings", 1),
        ("max_references", 1),
        ("max_id_bytes", 3),
        ("max_text_bytes", 5),
        ("max_issue_text_bytes", 5),
        ("max_json_bytes", 10),
        ("max_json_depth", 3),
    ],
)
def test_reduced_trusted_map_limits(inputs, field, value):
    with pytest.raises(w.C.BundleError):
        parse(inputs, limits=replace(LIMITS, **{field: value}))


@pytest.mark.parametrize("field", [item.name for item in fields(w.MaterialsLimits)])
def test_limits_cannot_be_enlarged(field):
    defaults = w.MaterialsLimits()
    with pytest.raises(w.C.BundleError):
        replace(defaults, **{field: getattr(defaults, field) + 1})


def test_limit_and_required_argument_types(inputs):
    for key in ("materials_root", "materials_files", "materials_map"):
        missing = dict(inputs)
        del missing[key]
        with pytest.raises(TypeError):
            w.build_materials_extension(**missing)
    with pytest.raises(TypeError):
        build(inputs, base_zip=inputs["destination"])
    for limits in ({}, b.CONTRACTS.BundleLimits(), True):
        with pytest.raises(w.BuildError, match="MaterialsLimits"):
            build(inputs, limits=limits)
    with pytest.raises(w.BuildError, match="immutable"):
        build(inputs, runtime_lock=bytearray(inputs["runtime_lock"]))


@pytest.mark.parametrize(
    "path",
    [
        "sources/recipe.py",
        "sources/native.so",
        "sources/plain.txt",
        "Sources/archive.zip",
        "licenses/hook.py",
        "licenses/hook.pyc",
        "licenses/hook.pyo",
        "licenses/site.pth",
        "licenses/native.so",
        "licenses/native.so.1",
        "licenses/NATIVE.PYD",
        "licenses/native.dll",
        "licenses/native.exe",
        "licenses/native.dylib",
        "licenses/script.cmd",
        "licenses/module.py/data.txt",
        "../sources/x.zip",
        "/sources/x.zip",
        "C:/sources/x.zip",
        "sources\\x.zip",
        "sources/CON.zip",
        "sources/e\u0301.zip",
        "sources/x.zip.",
        "PACKAGED_MATERIALS.json",
        "MATERIALS.md/x.txt",
    ],
)
def test_inert_portable_material_placement(path):
    with pytest.raises(w.C.BundleError):
        w._material_inventory([record(path, b"opaque")], LIMITS)


@pytest.mark.parametrize("suffix", w.SOURCE_SUFFIXES)
def test_all_sealed_opaque_source_suffixes(suffix):
    assert w._material_inventory([record("sources/exact" + suffix, b"opaque")], LIMITS)


@pytest.mark.parametrize(
    "extra",
    [
        record("licenses/NOTICE.txt", b"x"),
        record("licenses/notice.txt", b"x"),
        record("licenses/NOTICE.txt/child.txt", b"x"),
        record("licenses", b"x"),
        record("licenses/NOTICE.txt", b"x", 0o755),
    ],
)
def test_material_inventory_duplicate_case_prefix_and_mode(extra):
    with pytest.raises(w.C.BundleError):
        w._material_inventory([record("licenses/NOTICE.txt", b"x"), extra], LIMITS)


@pytest.mark.parametrize(
    "name",
    [
        "sources/owned.zip",
        "Sources/owned.zip",
        "licenses/owned.txt",
        "PACKAGED_MATERIALS.json",
        "materials.md/child.txt",
    ],
)
def test_addon_cannot_claim_reserved_namespaces(inputs, name):
    inputs["source_files"] += stage(inputs["source_root"], {b.ADDON_PREFIX + name: b"collision"})
    pins(inputs)
    with pytest.raises(w.BuildError, match="reserved"):
        build(inputs)
    assert not inputs["destination"].exists()


@pytest.mark.parametrize(
    "change", ["missing", "extra", "short", "grown", "same_size_hash", "symlink", "fifo"]
)
def test_material_tree_mutations_rejected(inputs, tmp_path, change):
    path = inputs["materials_root"] / "licenses/NOTICE.txt"
    if change == "missing":
        path.unlink()
    elif change == "extra":
        (path.parent / "extra.txt").write_bytes(b"unlisted")
    elif change == "short":
        path.write_bytes(b"x")
    elif change == "grown":
        path.write_bytes(path.read_bytes() + b"x")
    elif change == "same_size_hash":
        path.write_bytes(b"x" * path.stat().st_size)
    elif change == "symlink":
        target = tmp_path / "linked.txt"
        target.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(target)
    else:
        path.unlink()
        os.mkfifo(path)
    with pytest.raises((w.C.BundleError, OSError)):
        build(inputs)
    assert not inputs["destination"].exists()


def test_reparse_material_root_rejected(inputs, monkeypatch):
    original = Path.lstat
    target = inputs["materials_root"]

    def lstat(path, *args, **kwargs):
        result = original(path, *args, **kwargs)
        if path == target:
            return types.SimpleNamespace(st_mode=result.st_mode, st_file_attributes=0x400)
        return result

    monkeypatch.setattr(Path, "lstat", lstat)
    with pytest.raises(w.BuildError, match="reparse"):
        build(inputs)


def test_regular_to_fifo_swap_before_open_is_rejected_without_blocking(inputs, monkeypatch):
    original = b.os.open
    target = inputs["materials_root"] / "licenses/NOTICE.txt"

    def swap(path, flags, *args, **kwargs):
        if Path(path) == target:
            target.unlink()
            os.mkfifo(target)
        return original(path, flags, *args, **kwargs)

    monkeypatch.setattr(b.os, "open", swap)
    with pytest.raises(w.BuildError, match="regular"):
        build(inputs)


@pytest.mark.parametrize("change", ["material", "extra", "source", "runtime"])
def test_mutation_after_internal_builder_fails(inputs, monkeypatch, change):
    original = b.build_contract_extension

    def changed(**kwargs):
        result = original(**kwargs)
        if change == "extra":
            (inputs["materials_root"] / "licenses/new.txt").write_bytes(b"x")
        else:
            root_key, relative = {
                "material": ("materials_root", "licenses/NOTICE.txt"),
                "source": ("source_root", b.ADDON_PREFIX + "__init__.py"),
                "runtime": ("runtime_root", "python/bin/python3.12"),
            }[change]
            (inputs[root_key] / relative).write_bytes(b"mutated")
        return result

    monkeypatch.setattr(b, "build_contract_extension", changed)
    with pytest.raises(w.C.BundleError):
        build(inputs)
    assert not inputs["destination"].exists()


def test_material_stream_mutation_is_checked_at_copy(inputs, monkeypatch):
    original = b._copy_checked
    changed = False

    def copy_checked(stream, target, item, limits):
        nonlocal changed
        if target is not None and item.path == "licenses/NOTICE.txt" and not changed:
            changed = True
            (inputs["materials_root"] / item.path).write_bytes(b"substitute at stream time")
        return original(stream, target, item, limits)

    monkeypatch.setattr(b, "_copy_checked", copy_checked)
    with pytest.raises(w.BuildError, match="bytes differ|grew"):
        build(inputs)
    assert changed and not inputs["destination"].exists()


@pytest.mark.parametrize("field", ["bytes", "sha256", "published", "bundle_id"])
def test_internal_base_receipt_mismatch(inputs, monkeypatch, field):
    original = b.build_contract_extension

    def corrupt(**kwargs):
        receipt = original(**kwargs)
        receipt[field] = {
            "bytes": True,
            "sha256": "0" * 64,
            "published": False,
            "bundle_id": "0" * 64,
        }[field]
        return receipt

    monkeypatch.setattr(b, "build_contract_extension", corrupt)
    with pytest.raises(w.BuildError, match="receipt"):
        build(inputs)
    assert not inputs["destination"].exists()


@pytest.mark.parametrize("change", ["extra", "collision", "mode", "truncate", "base_bytes"])
def test_internal_base_mutation_rejected(inputs, monkeypatch, change):
    original = b.build_contract_extension

    def corrupt(**kwargs):
        receipt = original(**kwargs)
        path = kwargs["destination"]
        if change in {"extra", "collision"}:
            with zipfile.ZipFile(path, "a") as archive:
                name = "unexpected.txt" if change == "extra" else "sources/rogue.zip"
                archive.writestr(b._zip_info(name, 0o644), b"bad")
        elif change == "mode":
            data = path.read_bytes()
            with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(path, "w") as target:
                for info in source.infolist():
                    if info.filename == "__init__.py":
                        info.external_attr = (stat.S_IFREG | 0o755) << 16
                    target.writestr(info, source.read(info.filename))
        elif change == "truncate":
            path.write_bytes(path.read_bytes()[:-1])
        else:
            path.write_bytes(b"corrupted base")
            return receipt
        receipt["sha256"], receipt["bytes"] = digest(path.read_bytes()), path.stat().st_size
        return receipt

    monkeypatch.setattr(b, "build_contract_extension", corrupt)
    with pytest.raises((w.C.BundleError, zipfile.BadZipFile)):
        build(inputs)
    assert not inputs["destination"].exists()


def test_base_mutation_during_copy_and_after_append_rejected(inputs, monkeypatch):
    original = w._append

    def append(path, entries, limits):
        original(path, entries, limits)
        (path.parent / "base.zip").write_bytes(b"changed retained base")

    monkeypatch.setattr(w, "_append", append)
    with pytest.raises(w.BuildError, match="bytes differ"):
        build(inputs)
    assert not inputs["destination"].exists()


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_files", 13),
        ("max_total_bytes", 10),
        ("max_zip_metadata_bytes", 1000),
        ("max_outer_zip_bytes", 1000),
        ("max_file_bytes", 10),
    ],
)
def test_aggregate_and_stream_limits_fail_without_publication(inputs, field, value):
    with pytest.raises(w.C.BundleError):
        build(inputs, limits=replace(LIMITS, **{field: value}))
    assert not inputs["destination"].exists()


def test_outer_compressed_cap_is_independent_of_payload_cap(inputs, tmp_path):
    first = build(inputs)
    assert first["base_zip_bytes"] < first["bytes"]
    limited = replace(LIMITS, max_outer_zip_bytes=first["base_zip_bytes"] + 20)
    target = tmp_path / "limited.zip"
    with pytest.raises(w.BuildError, match="compressed"):
        build(inputs, destination=target, limits=limited)
    assert not target.exists()


def test_aggregate_expanded_limit_counts_base_materials_and_documents(inputs, tmp_path):
    data = bytes(range(256)) * 200
    inputs["materials_files"] += stage(inputs["materials_root"], {"sources/large.tar": data})
    value = map_value(inputs)
    value["components"][0]["source_paths"].append("sources/large.tar")
    pins(inputs, value)
    first = build(inputs)
    separate_maximum = max(
        sum(item["size"] for item in inputs[name + "_files"])
        for name in ("source", "runtime", "materials")
    )
    assert separate_maximum + 1 < first["outer_expanded_bytes"]
    limited = replace(LIMITS, max_total_bytes=separate_maximum + 1)
    with pytest.raises(w.C.BundleError, match="expanded"):
        build(inputs, destination=tmp_path / "aggregate.zip", limits=limited)
    assert not (tmp_path / "aggregate.zip").exists()


def test_aggregate_metadata_limit_counts_new_entries(inputs, tmp_path):
    first = build(inputs)
    with zipfile.ZipFile(Path(first["work_directory"]) / "base.zip") as archive:
        base_metadata = sum(46 + len(info.filename.encode()) for info in archive.infolist())
    with pytest.raises(w.BuildError, match="Aggregate outer ZIP metadata"):
        build(
            inputs,
            destination=tmp_path / "metadata.zip",
            limits=replace(LIMITS, max_zip_metadata_bytes=base_metadata + 1),
        )


@pytest.mark.parametrize("path", ["sources/payload.zip", "sources/pkg/payload.zip"])
def test_valid_source_archive_named_payload_zip_is_preserved(inputs, path):
    data = b"OPAQUE SOURCE MATERIAL, NOT THE BACKEND PAYLOAD"
    inputs["materials_files"] += stage(inputs["materials_root"], {path: data})
    value = map_value(inputs)
    value["components"][0]["source_paths"].append(path)
    pins(inputs, value)
    build(inputs)
    with zipfile.ZipFile(inputs["destination"]) as archive:
        assert archive.read(path) == data
        assert archive.getinfo(path).compress_type == zipfile.ZIP_STORED


def test_material_mutation_after_append_is_rejected(inputs, monkeypatch):
    original = w._append

    def append(path, entries, limits):
        original(path, entries, limits)
        (inputs["materials_root"] / "licenses/NOTICE.txt").write_bytes(b"changed after copy")

    monkeypatch.setattr(w, "_append", append)
    with pytest.raises(w.BuildError, match="bytes differ|grew"):
        build(inputs)
    assert not inputs["destination"].exists()


def test_base_mutation_at_checked_copy_is_rejected(inputs, monkeypatch):
    original = b._copy_checked
    changed = False

    def copying(stream, target, item, limits):
        nonlocal changed
        if item.path == "base.zip" and target is not None:
            changed = True
            (Path(target.name).parent / "base.zip").write_bytes(b"mutated base at copy")
        return original(stream, target, item, limits)

    monkeypatch.setattr(b, "_copy_checked", copying)
    with pytest.raises(w.BuildError, match="bytes differ"):
        build(inputs)
    assert changed and not inputs["destination"].exists()


def test_inherited_source_member_mismatch_rejected_even_with_matching_base_receipt(
    inputs, monkeypatch
):
    original = b.build_contract_extension

    def changed(**kwargs):
        result = original(**kwargs)
        path = kwargs["destination"]
        with (
            zipfile.ZipFile(io.BytesIO(path.read_bytes())) as source,
            zipfile.ZipFile(path, "w") as target,
        ):
            for info in source.infolist():
                data = source.read(info.filename)
                if info.filename == "__init__.py":
                    data = b"substituted source member"
                target.writestr(info, data)
        result["bytes"], result["sha256"] = path.stat().st_size, digest(path.read_bytes())
        return result

    monkeypatch.setattr(b, "build_contract_extension", changed)
    with pytest.raises(w.BuildError, match="inventoried source"):
        build(inputs)
    assert not inputs["destination"].exists()


def test_caller_mutable_inventories_are_detached_before_builder(inputs, monkeypatch):
    original = b.build_contract_extension

    def mutate_caller(**kwargs):
        inputs["source_files"][0]["sha256"] = "0" * 64
        inputs["runtime_files"].clear()
        inputs["materials_files"].clear()
        return original(**kwargs)

    monkeypatch.setattr(b, "build_contract_extension", mutate_caller)
    result = build(inputs)
    assert result["published"] is True and result["material_files"] == 6


@pytest.mark.parametrize(
    "field,value",
    [
        ("count", 65535),
        ("count", 50001),
        ("metadata", 16 * 1024 * 1024 + 1),
        ("offset", 0xFFFFFFFF),
        ("comment", 1),
        ("disk", 1),
    ],
)
def test_directory_bounds_precede_zipfile_allocation(field, value):
    values = {"count": 1, "metadata": 0, "offset": 4, "comment": 0, "disk": 0}
    values[field] = value
    data = b"PK\x03\x04" + struct.pack(
        "<4s4H2LH",
        b"PK\x05\x06",
        values["disk"],
        0,
        values["count"],
        values["count"],
        values["metadata"],
        values["offset"],
        values["comment"],
    )
    with pytest.raises(w.BuildError):
        w._zip_directory(io.BytesIO(data), len(data), LIMITS)


@pytest.mark.parametrize("root", ["source_root", "runtime_root", "materials_root"])
def test_output_inside_any_input_rejected(inputs, root):
    with pytest.raises(w.BuildError, match="outside"):
        build(inputs, destination=inputs[root] / "output.zip")


@pytest.mark.parametrize("kind", ["file", "symlink"])
def test_existing_destination_preserved(inputs, tmp_path, kind):
    original = b"existing archive"
    if kind == "file":
        inputs["destination"].write_bytes(original)
    else:
        target = tmp_path / "other.zip"
        target.write_bytes(original)
        inputs["destination"].symlink_to(target)
    with pytest.raises(w.BuildError, match="already exists"):
        build(inputs)
    assert inputs["destination"].read_bytes() == original


@pytest.mark.parametrize(
    "failure", ["race", "link", "append", "receipt_before", "hash", "tamper_before_link"]
)
def test_publication_failures_leave_no_replaced_destination(inputs, monkeypatch, failure):
    original_link, original_receipt = os.link, w._write_receipt
    links = []

    def link(source, target, *args, **kwargs):
        if Path(target) == inputs["destination"]:
            links.append(target)
            if failure == "race":
                Path(target).write_bytes(b"race winner")
            elif failure == "link":
                raise OSError("unsupported hard links")
        return original_link(source, target, *args, **kwargs)

    def receipt(path, value):
        if failure == "receipt_before":
            raise OSError("prepublication storage failed")
        original_receipt(path, value)
        if failure == "tamper_before_link":
            (path.parent / "materials-extension.zip").write_bytes(b"changed final")

    monkeypatch.setattr(os, "link", link)
    monkeypatch.setattr(w, "_write_receipt", receipt)
    if failure == "append":
        monkeypatch.setattr(
            w, "_append", lambda *args: (_ for _ in ()).throw(OSError("append failed"))
        )
    if failure == "hash":
        original_hash = w._file_item

        def hash_file(path, *args):
            if path.name == "materials-extension.zip":
                raise OSError("hash read failed")
            return original_hash(path, *args)

        monkeypatch.setattr(w, "_file_item", hash_file)
    with pytest.raises((w.C.BundleError, OSError)):
        build(inputs)
    if failure == "race":
        assert inputs["destination"].read_bytes() == b"race winner"
    else:
        assert not inputs["destination"].exists()
    assert len(links) <= 1


def test_post_link_receipt_failure_is_honest_committed_success(inputs, monkeypatch):
    original, original_link = w._write_receipt, os.link
    final_links = []

    def receipt(path, value):
        if value["published"]:
            raise OSError("diagnostic storage unavailable")
        original(path, value)

    def link(source, target):
        if target == inputs["destination"]:
            final_links.append(target)
        original_link(source, target)

    monkeypatch.setattr(w, "_write_receipt", receipt)
    monkeypatch.setattr(os, "link", link)
    result = build(inputs)
    assert result["published"] is True
    assert result["receipt_phase"] == "after_publication_receipt_write_failed"
    assert result["receipt_write_error"] == "OSError"
    assert digest(inputs["destination"].read_bytes()) == result["sha256"]
    assert len(final_links) == 1
    work = Path(result["work_directory"])
    assert json.loads((work / "MATERIALS_RECEIPT.before.json").read_bytes())["published"] is False


def test_human_index_identifies_exact_packaged_source_and_notice_bytes(inputs):
    build(inputs)
    with zipfile.ZipFile(inputs["destination"]) as archive:
        index = archive.read("MATERIALS.md").decode()
        for item in inputs["materials_files"]:
            assert item["path"].startswith(("sources/", "licenses/"))
            assert archive.read(item["path"]) == (inputs["materials_root"] / item["path"]).read_bytes()
            # The index quotes punctuation for inert Markdown display.
            display_path = item["path"].replace(".", r"\.")
            assert f'{display_path}: {item["size"]} bytes; SHA-256 {item["sha256"]}' in index
        assert "redistribution rights, rebuild success or native/release approval" in index


def test_human_index_escapes_caller_markup_and_preserves_json_text(inputs):
    value = map_value(inputs)
    hostile = '<img src="https://invalid.example/x"> [link](https://invalid.example) ![remote](url)'
    value["components"][0]["name"] = hostile
    value["unresolved_issues"][0]["description"] = hostile
    inputs["materials_map"] = b._json(value)
    build(inputs)
    with zipfile.ZipFile(inputs["destination"]) as archive:
        index = archive.read("MATERIALS.md").decode()
        assert "<img" not in index and "![remote]" not in index and "[link](" not in index
        document = json.loads(archive.read("PACKAGED_MATERIALS.json"))
        component = next(c for c in document["materials_map"]["components"] if c["id"] == "runtime")
        assert component["name"] == hostile


def test_no_material_execution_native_imports_network_or_processes(inputs, tmp_path, monkeypatch):
    original_import = builtins.__import__
    denied = {"OCP", "OCC", "cadquery", "slvs", "bpy"}

    def guarded_import(name, *args, **kwargs):
        if name.split(".")[0] in denied or name == "mechanical_cad.kernel_ocp":
            pytest.fail("Forbidden native import: " + name)
        return original_import(name, *args, **kwargs)

    def forbidden(*args, **kwargs):
        pytest.fail("Network, process or material extraction attempted")

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(os, "system", forbidden)
    monkeypatch.setattr(zipfile.ZipFile, "extract", forbidden)
    monkeypatch.setattr(zipfile.ZipFile, "extractall", forbidden)
    monkeypatch.setenv("PATH", "")
    build(inputs)
    assert not (tmp_path / "EXECUTED").exists()


def test_actual_inert_materializer_and_reverification_never_visit_materials(
    inputs, tmp_path, monkeypatch
):
    result = build(inputs)
    package_root, cache_root = tmp_path / "installed", tmp_path / "cache"
    package_root.mkdir()
    cache_root.mkdir()
    # Stage only installed wrapper members; nested source archives remain opaque bytes.
    with zipfile.ZipFile(inputs["destination"]) as archive:
        for info in archive.infolist():
            path = package_root / info.filename
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(archive.read(info))
    package_name = "materials_inert_runtime_tests"
    package = types.ModuleType(package_name)
    package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
    monkeypatch.setitem(sys.modules, package_name, package)
    materialize = importlib.import_module(package_name + ".runtime_bundle_materialize")
    manifest_module = importlib.import_module(package_name + ".runtime_bundle_manifest")
    original_open, visits = materialize._open_regular, []

    @contextmanager
    def observed(path):
        visits.append(Path(path))
        assert not {"sources", "licenses"}.intersection(Path(path).parts)
        with original_open(path) as stream:
            yield stream

    monkeypatch.setattr(materialize, "_open_regular", observed)
    pin = types.SimpleNamespace(
        bundle_id=result["bundle_id"], mode="exclusive", assert_held=lambda: None
    )
    release_data = (package_root / "release_identity.json").read_bytes()
    options = {
        "expected_platform": "linux-x64",
        "limits": manifest_module.BundleLimits(reserve_free_bytes=0),
        "pin": pin,
    }
    descriptor = materialize.materialize_bundle(package_root, cache_root, release_data, **options)
    assert (
        materialize.verify_cached_bundle(package_root, cache_root, release_data, **options)
        == descriptor
    )
    cached = files(Path(descriptor.root))
    assert not any(path.startswith(("sources/", "licenses/")) for path in cached)
    assert not {"PACKAGED_MATERIALS.json", "MATERIALS.md"}.intersection(cached)
    assert visits and not (tmp_path / "EXECUTED").exists()
    bootstrap = (ROOT / "scripts/standalone_child_bootstrap.py").read_text()
    assert (
        'system.path[:] = [layout["stdlib"], layout["native"], layout["src"], layout["packages"]]'
        in bootstrap
    )


def test_original_materials_sources_and_exact_reviewed_platform_deltas():
    for path in PINNED:
        assert_reviewed_materials_source(path, (ROOT / path).read_bytes())


@pytest.mark.parametrize("path", [
    "scripts/package_standalone_extension.py", "scripts/standalone_child_bootstrap.py"
])
def test_historical_materials_source_tampering_is_rejected(path):
    manifest = json.loads((HISTORICAL / "reviewed_platform_changes.json").read_bytes())
    originals = {
        key: (HISTORICAL / value["original_file"]).read_bytes()
        for key, value in manifest["files"].items()
    }
    originals[path] += b"\n# unreviewed historical change\n"
    with pytest.raises(AssertionError):
        reviewed_materials_sources(originals=originals)


def test_reviewed_platform_delta_tampering_is_rejected():
    data = (HISTORICAL / "reviewed_platform_changes.json").read_bytes()
    with pytest.raises(AssertionError):
        reviewed_materials_sources(manifest_bytes=data + b" ")


def test_bootstrap_version_normalization_requires_one_exact_current_literal():
    path = "scripts/standalone_child_bootstrap.py"
    data = (ROOT / path).read_bytes()
    current = f'package.__version__ != "{PROJECT_VERSION}"'.encode()
    assert data.count(current) == 1
    for changed in (data.replace(current, b'package.__version__ != "9.9.9"'), data + current):
        with pytest.raises(AssertionError):
            assert_reviewed_materials_source(path, changed)


@pytest.mark.parametrize("path,before,after", [
    (
        "scripts/package_standalone_extension.py",
        b"    os.link(archive_path, destination)",
        b"    os.replace(archive_path, destination)",
    ),
    (
        "scripts/standalone_child_bootstrap.py",
        b"            _verify_windows_images(layout)",
        b"            pass  # unreviewed origin bypass",
    ),
])
def test_current_platform_safety_mutations_cannot_hide_in_reviewed_deltas(path, before, after):
    current = (ROOT / path).read_bytes()
    assert current.count(before) == 1
    with pytest.raises(AssertionError):
        assert_reviewed_materials_source(path, current.replace(before, after, 1))
    with pytest.raises(AssertionError):
        assert_reviewed_materials_source(path, current + b"\n# unrelated current change\n")


def test_current_absent_runtime_import_edge_and_default_discovery():
    for directory in ("src", "blender_addon"):
        for path in (ROOT / directory).rglob("*.py"):
            tree = ast.parse(path.read_bytes())
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    assert "package_standalone_materials" not in ast.unparse(node)
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert project["tool"]["pytest"]["ini_options"]["testpaths"] == ["tests", "scripts/tests"]
    assert set(asdict(LIMITS)) == {field.name for field in fields(w.MaterialsLimits)}
