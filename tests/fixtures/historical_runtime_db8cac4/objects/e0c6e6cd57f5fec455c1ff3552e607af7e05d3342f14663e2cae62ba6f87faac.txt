"""Synthetic strict bundle metadata; no Blender/native runtime or downloads."""

import hashlib
import importlib
import json
import sys
import types
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "mcad_runtime_bundle_tests"
package = sys.modules.setdefault(PACKAGE, types.ModuleType(PACKAGE))
package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
m = importlib.import_module(PACKAGE + ".runtime_bundle_manifest")
LIMITS = m.BundleLimits()


def encode(value):
    return json.dumps(value, ensure_ascii=True, separators=(",", ":")).encode()


def documents(platform="linux-x64"):
    bundle_id = m.bundle_identity("a" * 40, "b" * 64, platform)
    python_path = "python/python.exe" if platform == "windows-x64" else "python/bin/python3.12"
    files = [
        {"path": path, "size": 1, "sha256": hashlib.sha256(b"x").hexdigest(), "mode": mode}
        for path, mode in (
            (python_path, 0o755),
            ("bootstrap.py", 0o644),
            ("src/mechanical_cad/__init__.py", 0o644),
        )
    ]
    payload = {
        "schema_version": 1,
        "bundle_id": bundle_id,
        "platform": platform,
        "python_path": python_path,
        "bootstrap_path": "bootstrap.py",
        "files": files,
    }
    release = {
        "schema_version": 1,
        "bundle_id": bundle_id,
        "source_commit": "a" * 40,
        "runtime_lock_sha256": "b" * 64,
        "platform": platform,
        "manifest_path": f"_backend/{bundle_id}/bundle-manifest.json",
        "manifest_sha256": hashlib.sha256(encode(payload)).hexdigest(),
        "payload_path": f"_backend/{bundle_id}/payload.zip",
        "payload_sha256": "c" * 64,
        "payload_size": 100,
    }
    return release, payload


def parse(release, payload, limits=LIMITS):
    data = encode(payload)
    release = dict(release, manifest_sha256=hashlib.sha256(data).hexdigest())
    parsed = m.parse_release_manifest(
        encode(release), expected_platform=release["platform"], limits=limits
    )
    return m.parse_bundle_manifest(data, parsed, limits=limits)


@pytest.mark.parametrize("platform", ["linux-x64", "windows-x64"])
def test_detached_frozen_data_with_platform_identity(platform):
    release, payload = documents(platform)
    result = parse(release, payload)
    payload["files"].clear()
    assert len(result.files) == 3
    assert result.platform == platform
    with pytest.raises(FrozenInstanceError):
        result.platform = "anything"
    assert m.bundle_identity("a" * 40, "b" * 64, platform) == result.bundle_id
    assert m.bundle_identity("c" * 40, "b" * 64, platform) != result.bundle_id


@pytest.mark.parametrize(
    "path",
    [
        "/absolute",
        "../outside",
        "a/../b",
        "a//b",
        "a/./b",
        "a/",
        "C:/evil",
        "C:evil",
        "a\\b",
        "file:stream",
        "NUL",
        "con.txt",
        "x/LPT1.dat",
        "COM¹",
        "aux",
        "a.",
        "a ",
        "a/PRN/x",
        "a\x00b",
        "a\nb",
        "a?b",
        "e\u0301",
        "\ud800",
        ".bundle-ready.json",
    ],
)
def test_unsafe_and_noncanonical_paths_fail(path):
    release, payload = documents()
    payload["files"].append(dict(payload["files"][0], path=path))
    with pytest.raises(m.BundleError):
        parse(release, payload)


@pytest.mark.parametrize(
    "paths", [("a", "a"), ("A", "a"), ("A/x", "a/y"), ("a", "a/x"), ("a/x", "a"), ("é/x", "É/y")]
)
def test_collisions_include_implicit_parent_directories(paths):
    release, payload = documents()
    payload["files"].extend(dict(payload["files"][0], path=p) for p in paths)
    with pytest.raises(m.BundleError, match="collision|conflict"):
        parse(release, payload)


def test_unicode_spaces_and_native_resource_neighbors_are_preserved():
    release, payload = documents()
    paths = [
        "packages/OCP.libs/libcodec.so",
        "packages/OCP/data/name é.bin",
        "packages/OCP-8.0.dist-info/METADATA",
        "python/Lib/中文 data.txt",
    ]
    payload["files"].extend(dict(payload["files"][1], path=p) for p in paths)
    assert [f.path for f in parse(release, payload).files][-4:] == paths


@pytest.mark.parametrize(
    "change",
    [
        {"schema_version": True},
        {"schema_version": 2},
        {"unknown": 1},
        {"source_commit": "a" * 39},
        {"payload_size": True},
        {"payload_size": -1},
        {"payload_sha256": "A" * 64},
        {"manifest_path": "elsewhere.json"},
        {"bundle_id": "f" * 64},
        {"platform": "win32"},
    ],
)
def test_release_exact_fields_types_and_identity(change):
    release, _ = documents()
    release.update(change)
    with pytest.raises(m.BundleError):
        m.parse_release_manifest(encode(release), expected_platform="linux-x64", limits=LIMITS)


@pytest.mark.parametrize(
    "field,value",
    [
        ("size", True),
        ("size", -1),
        ("size", 1.0),
        ("mode", True),
        ("mode", 0o777),
        ("mode", 0o4755),
        ("sha256", "bad"),
    ],
)
def test_file_inventory_strict_types(field, value):
    release, payload = documents()
    payload["files"][0][field] = value
    with pytest.raises(m.BundleError):
        parse(release, payload)


@pytest.mark.parametrize(
    "limit",
    [
        {"max_json_bytes": 50},
        {"max_json_depth": 2},
        {"max_files": 2},
        {"max_path_bytes": 90},
        {"max_path_depth": 2},
        {"max_total_bytes": 2},
        {"max_payload_bytes": 99},
    ],
)
def test_trusted_budget_neighbors(limit):
    release, payload = documents()
    with pytest.raises(m.BundleError):
        parse(release, payload, replace(LIMITS, **limit))


def test_file_limit_exact_boundary_and_wrong_platform():
    release, payload = documents()
    assert len(parse(release, payload, replace(LIMITS, max_file_bytes=1)).files) == 3
    payload["files"][0]["size"] = 2
    with pytest.raises(m.BundleError):
        parse(release, payload, replace(LIMITS, max_file_bytes=1))
    with pytest.raises(m.BundleError):
        m.parse_release_manifest(encode(release), expected_platform="windows-x64", limits=LIMITS)


@pytest.mark.parametrize(
    "data",
    [
        b'{"schema_version":1,"schema_version":1}',
        b'{"x":NaN}',
        b'{"x":Infinity}',
        b"\xff",
        b"\xef\xbb\xbf{}",
        b"[" * 30 + b"]" * 30,
        b'{"x":',
        b"{} trailing",
    ],
)
def test_bounded_json_rejects_duplicates_nonfinite_and_malformed(data):
    with pytest.raises(m.BundleError):
        m.parse_release_manifest(data, expected_platform="linux-x64", limits=LIMITS)


def test_wrong_manifest_bytes_and_entrypoints_never_create_descriptor():
    release, payload = documents()
    parsed = m.parse_release_manifest(encode(release), expected_platform="linux-x64", limits=LIMITS)
    with pytest.raises(m.BundleError, match="digest"):
        m.parse_bundle_manifest(encode(payload) + b" ", parsed, limits=LIMITS)
    for field, value in (("python_path", "missing"), ("bootstrap_path", "other.py")):
        with pytest.raises(m.BundleError):
            parse(release, dict(payload, **{field: value}))
    payload["files"].pop()
    with pytest.raises(m.BundleError, match="Missing"):
        parse(release, payload)


def test_limits_are_trusted_integer_configuration():
    for kwargs in ({"max_files": True}, {"chunk_bytes": 0}, {"max_files": 65535}):
        with pytest.raises(m.BundleError):
            m.BundleLimits(**kwargs)


def test_shared_inventory_helper_is_detached_and_checks_bounds_and_prefixes():
    _, payload = documents()
    files = payload["files"]
    parsed = m.validate_file_inventory(
        files, limits=replace(LIMITS, max_files=3, max_total_bytes=3)
    )
    files[0]["size"] = 99
    assert parsed[0].size == 1
    for bad in ([dict(files[1], extra=1)], [dict(files[1], path="a"), dict(files[1], path="a/b")]):
        with pytest.raises(m.BundleError):
            m.validate_file_inventory(bad, limits=LIMITS)


def test_oversized_integer_and_escaped_braces_are_bounded_json():
    with pytest.raises(m.BundleError):
        m.parse_release_manifest(
            b'{"x":' + b"9" * 5000 + b"}", expected_platform="linux-x64", limits=LIMITS
        )
    value = m._json(b'{"text":"[\\"[[[[[[[[[["}', replace(LIMITS, max_json_depth=1))
    assert value["text"].startswith('["')


def test_payload_manifest_exact_field_types_and_bytes_bound():
    release, payload = documents()
    for change in (
        {"schema_version": True},
        {"schema_version": 2},
        {"extra": 1},
        {"files": {}},
        {"files": []},
        {"bundle_id": "0" * 64},
        {"platform": "windows-x64"},
    ):
        with pytest.raises(m.BundleError):
            parse(release, dict(payload, **change))
    parsed = m.parse_release_manifest(encode(release), expected_platform="linux-x64", limits=LIMITS)
    for data in (bytearray(encode(payload)), b" " * 10):
        with pytest.raises(m.BundleError):
            m.parse_bundle_manifest(data, parsed, limits=replace(LIMITS, max_json_bytes=5))


def test_descriptor_rejects_mutable_unbounded_or_nonprimitive_identity_fields():
    value = m.BundleDescriptor(
        "a" * 64,
        "b" * 40,
        "c" * 64,
        "linux-x64",
        "d" * 64,
        "e" * 64,
        "/cache/bundle",
        "/cache/bundle/python/bin/python3.12",
        "/cache/bundle/bootstrap.py",
    )
    for change in (
        {"root": []},
        {"root": "x" * 32768},
        {"root": "\x00"},
        {"root": "\ud800"},
        {"bundle_id": "bad"},
        {"source_commit": "bad"},
        {"platform": "other"},
    ):
        with pytest.raises(m.BundleError):
            replace(value, **change)


@pytest.mark.parametrize(
    "path", [".BUNDLE-READY.JSON", ".bundle-ready.json/child", ".BUNDLE-READY.JSON/child"]
)
def test_ready_marker_root_component_is_reserved_in_every_case_and_kind(path):
    item = {"path": path, "size": 0, "sha256": hashlib.sha256(b"").hexdigest(), "mode": 0o644}
    with pytest.raises(m.BundleError, match="Reserved materialization marker"):
        m.validate_file_inventory([item], limits=LIMITS)
    # A regular resource with that basename below an unrelated directory cannot
    # shadow the root marker and retains the ordinary inventory policy.
    item["path"] = "packages/resource/.bundle-ready.json"
    assert m.validate_file_inventory([item], limits=LIMITS)[0].path == item["path"]
