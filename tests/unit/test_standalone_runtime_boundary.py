"""Current live-launch/import boundaries and exact historical inverse mutations.

Only inverse inputs use the pinned historical source snapshot. ROOT, ADDON and
all live boundary checks/mutations still target the current checkout.
"""

import ast
import hashlib
import json
import sys
from pathlib import Path

import pytest
from historical_runtime_source import historical_runtime_root

ROOT = Path(__file__).resolve().parents[2]
ADDON = ROOT / "blender_addon/mechanical_cad_blender"
EXPECTED_LIVE_GUARD_SOURCE_SHA256 = (
    "398fda102da7ebddf29213ae824dd72a4011882e6c23a27d8fa33955bc80e075"
)
LEAVES = {
    "backend_platform",
    "windows_process",
    "windows_runtime",
    "windows_cache",
    "runtime_bundle_manifest",
    "runtime_bundle_materialize",
    "runtime_bundle_pin",
    "runtime_bundle_prepare",
    "runtime_bundle_launch",
}
# Exact import statements, including imported symbols, aliases and multiplicity.
# No core, native adapter, publisher or validator is an admitted importer.
IMPORT_EDGES = {
    "backend_platform.py": (
        "from .runtime_bundle_manifest import BundleDescriptor",
        "from .runtime_bundle_manifest import BundleDescriptor",
    ),
    "backend_runtime.py": (
        "from .runtime_bundle_launch import LAUNCH_CONSTANT_FIELDS, capture_bundled_policy",
        "from .runtime_bundle_manifest import BundleLimits",
        "from .runtime_bundle_prepare import BundlePreparationJob",
    ),
    "backend_selection.py": (
        "from .runtime_bundle_launch import BundledLaunchPolicy, _windows_path",
    ),
    "registration.py": ("from .runtime_bundle_launch import LAUNCH_CONSTANT_FIELDS",),
    "runtime_bundle_launch.py": (
        "from .windows_cache import WindowsCacheLocation",
        "from . import runtime_bundle_materialize as materialize",
        "from . import runtime_bundle_pin as pins",
        "from .runtime_bundle_manifest import "
        "BundleDescriptor, BundleError, BundleLimits, parse_release_manifest, validate_path",
    ),
    "runtime_bundle_materialize.py": (
        "from .windows_cache import WindowsCacheCancelled, WindowsCacheOwner",
        "from .runtime_bundle_manifest import "
        "BundleDescriptor, BundleError, parse_bundle_manifest, parse_release_manifest",
    ),
    "runtime_bundle_prepare.py": (
        "from .windows_cache import "
        "WindowsCacheCancelled, WindowsCacheLocation, WindowsCacheOwner, _windows_path",
        "from .runtime_bundle_manifest import "
        "PLATFORMS, BundleDescriptor, BundleLimits, parse_release_manifest",
        "from .runtime_bundle_materialize import BundleCancelled, materialize_bundle",
        "from .runtime_bundle_pin import "
        "MAX_TIMEOUT_SECONDS, BundlePinCancelled, BundlePinError, BundlePinTimeout, "
        "acquire_bundle_pin",
    ),
    "sidecar_job.py": (
        "from .windows_runtime import WindowsOperationOwner",
        "from .runtime_bundle_launch import BundleCleanupUncertain, BundledOperationOwner",
    ),
    "windows_cache.py": (
        "from .runtime_bundle_manifest import "
        "BundleError, BundleFile, BundleLimits, BundleManifest, ReleaseManifest, "
        "bundle_identity, validate_path",
    ),
    "windows_runtime.py": (
        "from .windows_cache import WindowsCacheOwner",
        "from . import runtime_bundle_materialize as materialize",
        "from . import runtime_bundle_pin as pins",
        "from .backend_platform import LaunchObservation, LaunchSpec, ProcessError",
        "from .runtime_bundle_launch import "
        "MAX_RELEASE_BYTES, BundleCleanupUncertain, BundledLaunchPolicy, _windows_path",
        "from .runtime_bundle_manifest import "
        "BundleDescriptor, BundleLimits, parse_bundle_manifest, parse_release_manifest",
        "from .windows_process import Win32API, WindowsOwnedProcess",
    ),
    "windows_process.py": (
        "from .backend_platform import MAX_STDERR_BYTES, MAX_STDOUT_BYTES, LaunchObservation, "
        "LaunchSpec, LaunchValidation, ProcessError, RuntimePin",
    ),
}


def guard_namespace():
    path = ROOT / "tests/unit/test_arc_profile_native_end_cap.py"
    names = {
        "VISUAL_JOINT_FIXTURE",
        "VISUAL_JOINT_SHA256",
        "VISUAL_JOINT_ADDED",
        "VISUAL_JOINT_ORIGINALS",
        "_visual_joint_revision",
        "_visual_joint_bytes",
        "visual_joint_originals",
        "RELEASE_071_FIXTURE",
        "RELEASE_071_SHA256",
        "RELEASE_071_ORIGINALS",
        "_release_071_bytes",
        "ASSEMBLY_STEP_FIXTURE",
        "ASSEMBLY_STEP_SHA256",
        "ASSEMBLY_STEP_ADDED",
        "ASSEMBLY_STEP_ORIGINALS",
        "_assembly_step_revision",
        "_assembly_step_bytes",
        "assembly_step_originals",
        "RELEASE_070_FIXTURE",
        "RELEASE_070_SHA256",
        "RELEASE_070_ORIGINALS",
        "_release_070_bytes",
        "ASSEMBLY_SOURCE_FIXTURE",
        "ASSEMBLY_SOURCE_SHA256",
        "ASSEMBLY_SOURCE_ADDED",
        "ASSEMBLY_SOURCE_ORIGINALS",
        "ASSEMBLY_HARNESS_FIXTURE",
        "ASSEMBLY_HARNESS_SHA256",
        "ASSEMBLY_HARNESS_ORIGINALS",
        "assembly_source_originals",
        "assembly_harness_originals",
        "GATE_C_OWNER_SOURCE_FIXTURE",
        "GATE_C_OWNER_SOURCE_SHA256",
        "GATE_C_OWNER_SOURCE_ADDED",
        "GATE_C_OWNER_SOURCE_ORIGINALS",
        "GATE_C_OWNER_HARNESS_FIXTURE",
        "GATE_C_OWNER_HARNESS_SHA256",
        "GATE_C_OWNER_HARNESS_ORIGINALS",
        "gate_c_owner_source_originals",
        "gate_c_owner_harness_originals",
        "INVENTORY_GUARD_HARNESS_FIXTURE",
        "INVENTORY_GUARD_HARNESS_SHA256",
        "INVENTORY_GUARD_HARNESS_ORIGINALS",
        "inventory_guard_harness_originals",
        "REDUNDANT_SOLVE_SOURCE_FIXTURE",
        "REDUNDANT_SOLVE_SOURCE_SHA256",
        "REDUNDANT_SOLVE_SOURCE_ORIGINALS",
        "REDUNDANT_SOLVE_HARNESS_FIXTURE",
        "REDUNDANT_SOLVE_HARNESS_SHA256",
        "REDUNDANT_SOLVE_HARNESS_ORIGINALS",
        "redundant_solve_source_originals",
        "redundant_solve_harness_originals",
        "INTEGRATION_SOURCE_FIXTURE",
        "INTEGRATION_SOURCE_SHA256",
        "INTEGRATION_HARNESS_FIXTURE",
        "STANDALONE_INTEGRATION_HARNESS_SHA256",
        "GEOMETRY_REVISION_FIXTURE",
        "GEOMETRY_REVISION_SHA256",
        "INTEGRATION_SOURCE_ADDED",
        "INTEGRATION_SOURCE_ORIGINALS",
        "INTEGRATION_HARNESS_ORIGINALS",
        "_integration_restore_entry",
        "standalone_integration_source_originals",
        "standalone_integration_harness_originals",
        "_geometry_recovered_harness_bytes",
        "geometry_revision_originals",
        "WINDOWS_RUNTIME_CACHE_REVISION_FIXTURE",
        "WINDOWS_RUNTIME_CACHE_REVISION_SHA256",
        "WINDOWS_RUNTIME_CACHE_REVISION_CHANGED",
        "WINDOWS_RUNTIME_CACHE_REVISION_ADDED",
        "WINDOWS_RUNTIME_CACHE_REVISION_ORIGINALS",
        "WINDOWS_RUNTIME_CACHE_HARNESS_FIXTURE",
        "WINDOWS_RUNTIME_CACHE_HARNESS_SHA256",
        "WINDOWS_RUNTIME_CACHE_HARNESS_ORIGINALS",
        "windows_runtime_cache_originals",
        "windows_runtime_cache_harness_originals",
        "WINDOWS_CACHE_REVISION_FIXTURE",
        "WINDOWS_CACHE_REVISION_SHA256",
        "WINDOWS_CACHE_REVISION_CHANGED",
        "WINDOWS_CACHE_REVISION_ADDED",
        "WINDOWS_CACHE_REVISION_ORIGINALS",
        "WINDOWS_CACHE_HARNESS_FIXTURE",
        "WINDOWS_CACHE_HARNESS_SHA256",
        "WINDOWS_CACHE_HARNESS_ORIGINALS",
        "windows_cache_originals",
        "windows_cache_harness_originals",
        "WINDOWS_TRANSPORT_REVISION_FIXTURE",
        "WINDOWS_TRANSPORT_REVISION_SHA256",
        "WINDOWS_TRANSPORT_REVISION_CHANGED",
        "WINDOWS_TRANSPORT_REVISION_ADDED",
        "WINDOWS_TRANSPORT_HARNESS_FIXTURE",
        "WINDOWS_TRANSPORT_HARNESS_SHA256",
        "WINDOWS_TRANSPORT_HARNESS_ORIGINALS",
        "windows_transport_originals",
        "windows_transport_harness_originals",
        "STANDALONE_HARNESS_FIXTURE",
        "STANDALONE_HARNESS_SHA256",
        "STANDALONE_HARNESS_ORIGINALS",
        "standalone_harness_originals",
        "AUTHORING_REVISION_FIXTURE",
        "AUTHORING_REVISION_SHA256",
        "authoring_revision_originals",
        "SERVICE_REVISION_FIXTURE",
        "SERVICE_REVISION_SHA256",
        "service_revision_originals",
        "STANDALONE_REVISION_FIXTURE",
        "STANDALONE_REVISION_SHA256",
        "standalone_revision_added",
        "STANDALONE_LIVE_FIXTURE",
        "STANDALONE_LIVE_SHA256",
        "STANDALONE_LIVE_CHANGED",
        "STANDALONE_LIVE_ADDED",
        "standalone_live_originals",
        "protected_python_digest",
        "SNAPSHOT3_PYTHON_PROTECTED",
        "copy_python_guard_tree",
    }
    nodes = []
    for node in ast.parse(path.read_bytes()).body:
        if isinstance(node, ast.FunctionDef) and node.name in names:
            nodes.append(node)
        elif isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and target.id in names:
                nodes.append(node)
    namespace = {"hashlib": hashlib, "json": json, "ROOT": historical_runtime_root()}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)
    assert names <= set(namespace)
    return namespace


def assert_guard_source_bytes(raw, fixture_sha256):
    seal = ('STANDALONE_LIVE_SHA256 = "' + fixture_sha256 + '"').encode()
    assert raw.count(seal) == 1
    normalized = raw.replace(seal, ('STANDALONE_LIVE_SHA256 = "' + "0" * 64 + '"').encode())
    assert hashlib.sha256(normalized).hexdigest() == EXPECTED_LIVE_GUARD_SOURCE_SHA256


def historical_guard_input(namespace):
    """Exact historical data for the seven guard-byte cases, never current-code approval.

    The fixture is inert text from the original reviewed ancestor. Its identity
    must match the existing trusted original hash before the unchanged normalized
    guard seal or any intentional mutation is tested. No Git is needed at runtime.
    """
    fixture = ROOT / "tests/fixtures/standalone/historical_guard_1c8f030.py.txt"
    provenance = json.loads(fixture.with_suffix(".provenance.json").read_bytes())
    path = "tests/unit/test_arc_profile_native_end_cap.py"
    expected = namespace["STANDALONE_HARNESS_ORIGINALS"][path]
    assert provenance["source_commit"] == "1c8f03026c814cd69bfb25c35449810b5b858fb2"
    assert provenance["source_path"] == path
    assert (provenance["bytes"], provenance["sha256"]) == expected
    raw = fixture.read_bytes()
    assert (len(raw), hashlib.sha256(raw).hexdigest()) == expected
    return raw


def test_guard_module_remains_exact_except_the_fixture_hash_slot():
    namespace = guard_namespace()
    raw = historical_guard_input(namespace)
    assert_guard_source_bytes(raw, namespace["STANDALONE_LIVE_SHA256"])


@pytest.mark.parametrize(
    "before, after",
    [
        (
            b"def standalone_live_originals(root):",
            b"def standalone_live_originals(root): # changed",
        ),
        (
            b"def authoring_revision_originals(root):",
            b"def authoring_revision_originals(root): # changed",
        ),
        (
            b"def service_revision_originals(root):",
            b"def service_revision_originals(root): # changed",
        ),
        (
            b"def standalone_revision_added(root):",
            b"def standalone_revision_added(root): # changed",
        ),
        (b"def protected_python_digest(root):", b"def protected_python_digest(root): # changed"),
        (
            b"class NoNativeImports(importlib.abc.MetaPathFinder):",
            b"class NoNativeImports(importlib.abc.MetaPathFinder): # changed",
        ),
    ],
)
def test_guard_source_mutations_have_no_historical_exemption(before, after):
    namespace = guard_namespace()
    raw = historical_guard_input(namespace)
    # Establish the valid baseline first; setup failure is not mutation rejection.
    assert_guard_source_bytes(raw, namespace["STANDALONE_LIVE_SHA256"])
    assert raw.count(before) == 1
    with pytest.raises(AssertionError):
        assert_guard_source_bytes(raw.replace(before, after), namespace["STANDALONE_LIVE_SHA256"])


def test_harness_inverse_restores_exact_parent_test_bytes_and_original_guard_seal():
    namespace = guard_namespace()
    restored = namespace["standalone_harness_originals"](historical_runtime_root())
    assert set(restored) == set(namespace["STANDALONE_HARNESS_ORIGINALS"])
    assert len(restored) == 6
    for path, raw in restored.items():
        assert path.startswith("tests/unit/")
        assert (len(raw), hashlib.sha256(raw).hexdigest()) == (
            namespace["STANDALONE_HARNESS_ORIGINALS"][path]
        )
    assert_guard_source_bytes(
        restored["tests/unit/test_arc_profile_native_end_cap.py"],
        namespace["STANDALONE_LIVE_SHA256"],
    )


@pytest.mark.parametrize("path", sorted(guard_namespace()["STANDALONE_HARNESS_ORIGINALS"]))
def test_each_repaired_test_path_rejects_unreviewed_current_bytes(tmp_path, path):
    namespace = guard_namespace()
    namespace["copy_python_guard_tree"](tmp_path)
    target = tmp_path / path
    target.write_bytes(target.read_bytes() + b"\n# unreviewed test mutation\n")
    with pytest.raises(AssertionError):
        namespace["standalone_harness_originals"](tmp_path)


@pytest.mark.parametrize("mutation", ["fixture", "slot", "helper", "coordinated"])
def test_harness_pair_tampering_cannot_replace_trusted_validator(tmp_path, mutation):
    # The namespace always comes from the trusted source, never the copied tree.
    namespace = guard_namespace()
    namespace["copy_python_guard_tree"](tmp_path)
    fixture = tmp_path / namespace["STANDALONE_HARNESS_FIXTURE"]
    guard = tmp_path / "tests/unit/test_arc_profile_native_end_cap.py"
    if mutation in {"fixture", "coordinated"}:
        fixture.write_bytes(fixture.read_bytes() + b"\n")
    if mutation in {"slot", "coordinated"}:
        new_digest = hashlib.sha256(fixture.read_bytes()).hexdigest()
        if mutation == "slot":
            new_digest = "f" * 64
        old_slot = (
            'STANDALONE_HARNESS_SHA256 = "' + namespace["STANDALONE_HARNESS_SHA256"] + '"'
        ).encode()
        new_slot = ('STANDALONE_HARNESS_SHA256 = "' + new_digest + '"').encode()
        raw = guard.read_bytes()
        assert raw.count(old_slot) == 1
        guard.write_bytes(raw.replace(old_slot, new_slot))
    if mutation == "helper":
        raw = guard.read_bytes()
        before = b"def standalone_harness_originals(root):"
        assert raw.count(before) == 1
        guard.write_bytes(raw.replace(before, before + b" # unreviewed"))
    with pytest.raises(AssertionError):
        namespace["standalone_harness_originals"](tmp_path)


def repin_harness_fixture_for_inner_control(namespace, root, revision):
    """Explicitly bypass the outer digest/slot only to test inner assertions."""
    # Deliberately bypass only the newer outer seal in these legacy inner controls.
    # Its own independent pair/slot controls below still exercise that seal.
    transport_harness = namespace["windows_transport_harness_originals"](root)
    raw = (json.dumps(revision, sort_keys=True, indent=2) + "\n").encode()
    (root / namespace["STANDALONE_HARNESS_FIXTURE"]).write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    guard = root / "tests/unit/test_arc_profile_native_end_cap.py"
    old_slot = (
        'STANDALONE_HARNESS_SHA256 = "' + namespace["STANDALONE_HARNESS_SHA256"] + '"'
    ).encode()
    new_slot = ('STANDALONE_HARNESS_SHA256 = "' + digest + '"').encode()
    data = guard.read_bytes()
    assert data.count(old_slot) == 1
    guard.write_bytes(data.replace(old_slot, new_slot))
    namespace["STANDALONE_HARNESS_SHA256"] = digest

    path = "tests/unit/test_arc_profile_native_end_cap.py"
    historical = transport_harness[path]
    assert historical.count(old_slot) == 1
    transport_harness[path] = historical.replace(old_slot, new_slot)
    namespace["windows_transport_harness_originals"] = lambda _root: transport_harness


@pytest.mark.parametrize(
    "mutation",
    [
        "schema",
        "base",
        "extra_key",
        "missing_path",
        "extra_path",
        "production_path",
        "original_hash",
        "reviewed_hash",
        "original_length",
        "reviewed_length",
        "entry_key",
        "hunk_key",
        "empty_hunks",
        "start_negative",
        "start_bool",
        "end_bool",
        "end_before_start",
        "end_overflow",
        "replacement",
        "original",
        "duplicate_hunk",
        "reversed_hunks",
        "forged_original",
    ],
)
def test_harness_inverse_rejects_invalid_hunks_metadata_and_non_test_paths(tmp_path, mutation):
    namespace = guard_namespace()
    namespace["copy_python_guard_tree"](tmp_path)
    revision = json.loads((tmp_path / namespace["STANDALONE_HARNESS_FIXTURE"]).read_bytes())
    name = "tests/unit/test_arc_profile_incidence.py"
    entry = revision["changed"][name]
    hunk = entry["hunks"][0]
    if mutation == "schema":
        revision["schema"] = "other"
    elif mutation == "base":
        revision["base_commit"] = "0" * 40
    elif mutation == "extra_key":
        revision["allow_other_paths"] = True
    elif mutation == "missing_path":
        revision["changed"].pop(name)
    elif mutation == "extra_path":
        revision["changed"]["tests/unit/test_unreviewed.py"] = dict(entry)
    elif mutation == "production_path":
        revision["changed"]["src/mechanical_cad/kernel_ocp.py"] = revision["changed"].pop(name)
    elif mutation in {"original_hash", "reviewed_hash"}:
        entry[mutation.replace("_hash", "_sha256")] = "0" * 64
    elif mutation in {"original_length", "reviewed_length"}:
        entry[mutation.replace("_length", "_bytes")] = True
    elif mutation == "entry_key":
        entry["exempt"] = True
    elif mutation == "hunk_key":
        hunk["skip_validation"] = True
    elif mutation == "empty_hunks":
        entry["hunks"] = []
    elif mutation == "start_negative":
        hunk["new_start"] = -1
    elif mutation == "start_bool":
        hunk["new_start"] = False
    elif mutation == "end_bool":
        hunk["new_end"] = True
    elif mutation == "end_before_start":
        hunk["new_end"] = hunk["new_start"] - 1
    elif mutation == "end_overflow":
        hunk["new_end"] = entry["reviewed_bytes"] + 1
    elif mutation == "replacement":
        hunk["replacement"] += "# altered reviewed bytes\n"
    elif mutation == "original":
        hunk["original"] += "# altered before bytes\n"
    elif mutation == "duplicate_hunk":
        entry["hunks"].insert(1, dict(hunk))
    elif mutation == "reversed_hunks":
        assert len(entry["hunks"]) > 1
        entry["hunks"].reverse()
    else:
        assert mutation == "forged_original"
        restored = namespace["standalone_harness_originals"](tmp_path)[name] + b"\n# forged\n"
        current = (tmp_path / name).read_bytes()
        entry["original_bytes"] = len(restored)
        entry["original_sha256"] = hashlib.sha256(restored).hexdigest()
        entry["hunks"] = [
            {
                "new_start": 0,
                "new_end": len(current),
                "original": restored.decode(),
                "replacement": current.decode(),
            }
        ]
    repin_harness_fixture_for_inner_control(namespace, tmp_path, revision)
    with pytest.raises(AssertionError):
        namespace["standalone_harness_originals"](tmp_path)


def test_historical_core_addon_bytes_and_current_linux_manual_selection_guard():
    namespace = guard_namespace()
    added, restored = namespace["standalone_live_originals"](historical_runtime_root())
    assert added == (
        namespace["STANDALONE_LIVE_ADDED"]
        | namespace["WINDOWS_TRANSPORT_REVISION_ADDED"]
        | namespace["WINDOWS_CACHE_REVISION_ADDED"]
        | namespace["WINDOWS_RUNTIME_CACHE_REVISION_ADDED"]
    )
    assert set(restored) == (
        namespace["STANDALONE_LIVE_CHANGED"]
        | namespace["WINDOWS_TRANSPORT_REVISION_CHANGED"]
        | namespace["WINDOWS_CACHE_REVISION_CHANGED"]
        | namespace["WINDOWS_RUNTIME_CACHE_REVISION_CHANGED"]
    )
    namespace["standalone_revision_added"](historical_runtime_root())
    revision = json.loads((ROOT / namespace["STANDALONE_REVISION_FIXTURE"]).read_bytes())
    baseline = revision["baseline_runtime"]
    assert len(baseline) == 129
    assert "src/mechanical_cad/kernel_ocp.py" in baseline
    assert "blender_addon/mechanical_cad_blender/backend_selection.py" in baseline
    assert "blender_addon/mechanical_cad_blender/guarded_evidence.py" in baseline
    _, transport_originals = namespace["windows_transport_originals"](historical_runtime_root())
    _, integration_originals = namespace["standalone_integration_source_originals"](historical_runtime_root())
    _, gate_c_originals = namespace["gate_c_owner_source_originals"](historical_runtime_root())
    _, assembly_originals = namespace["assembly_source_originals"](historical_runtime_root())
    integration_originals = (
        assembly_originals
        | gate_c_originals
        | integration_originals
        | namespace["redundant_solve_source_originals"](historical_runtime_root())
    )
    for path, expected in baseline.items():
        data = restored.get(
            path, integration_originals.get(path, namespace["_release_070_bytes"](historical_runtime_root(), path))
        )
        assert hashlib.sha256(data).hexdigest() == expected, path
        if path not in namespace["STANDALONE_LIVE_CHANGED"]:
            # Every old core/add-on hash remains exact after the separately
            # sealed finite geometry inverse; untouched bytes are still read live.
            assert (
                hashlib.sha256(
                    transport_originals.get(
                        path,
                        integration_originals.get(
                            path, namespace["_release_070_bytes"](historical_runtime_root(), path)
                        ),
                    )
                ).hexdigest()
                == expected
            ), path
    assert not any(path.startswith("src/") for path in restored)
    assert 'if sys.platform != "linux":' in (ADDON / "backend_selection.py").read_text()
    assert namespace["protected_python_digest"](historical_runtime_root()) == namespace["SNAPSHOT3_PYTHON_PROTECTED"]
    assert namespace["SNAPSHOT3_PYTHON_PROTECTED"] == (
        259,
        "f1c9a006975a48a8ef3fb051709eb4ac75a0dadc207090c27783902034e939b7",
    )


def test_original_standalone_fixture_and_all_fourteen_before_files_stay_exact():
    namespace = guard_namespace()
    raw = (ROOT / namespace["STANDALONE_REVISION_FIXTURE"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == (
        "0e6152a913e23079c770f23bbe6daf111d28f82981496e1c85af19ae1bc5c6c9"
    )
    _added, restored = namespace["standalone_live_originals"](historical_runtime_root())
    old = json.loads(raw)["added"]
    assert len(old) == 14
    for path, expected in old.items():
        data = restored.get(path, namespace["_release_070_bytes"](historical_runtime_root(), path))
        assert len(data) == expected["bytes"], path
        assert hashlib.sha256(data).hexdigest() == expected["sha256"], path


def assert_import_boundary(root):
    forbidden = LEAVES | {"standalone_child_bootstrap"}
    found = {}
    for directory in (root / "src", root / "blender_addon"):
        for path in directory.rglob("*.py"):
            tree = ast.parse(path.read_bytes())
            field_literals = []
            if path.relative_to(root).as_posix() == (
                "blender_addon/mechanical_cad_blender/runtime_bundle_launch.py"
            ):
                policies = [
                    node
                    for node in tree.body
                    if isinstance(node, ast.ClassDef) and node.name == "BundledLaunchPolicy"
                ]
                assert len(policies) == 1
                methods = [
                    node
                    for node in policies[0].body
                    if isinstance(node, ast.FunctionDef) and node.name == "__post_init__"
                ]
                assert len(methods) == 1
                captures = []
                pending = list(methods[0].body)
                while pending:
                    candidate = pending.pop()
                    if isinstance(
                        candidate, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
                    ):
                        continue
                    if (
                        isinstance(candidate, ast.Expr)
                        and isinstance(candidate.value, ast.Call)
                        and ast.unparse(candidate.value)
                        == "object.__setattr__(self, 'windows_cache', location)"
                    ):
                        captures.append(candidate.value)
                    pending.extend(ast.iter_child_nodes(candidate))
                assert len(captures) == 1
                field_literals = [captures[0].args[1]]
            for node in ast.walk(tree):
                if node in field_literals:
                    continue
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    names = [alias.name for alias in node.names]
                    if isinstance(node, ast.ImportFrom):
                        names.append(node.module or "")
                    if any(forbidden.intersection(name.split(".")) for name in names):
                        relative = path.relative_to(root).as_posix()
                        found.setdefault(relative, []).append(ast.unparse(node))
                elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                    assert not any(name in node.value for name in forbidden - {"windows_cache"}), (
                        path
                    )
                    assert "windows_cache" not in node.value.split("."), path
    expected = {
        "blender_addon/mechanical_cad_blender/" + name: sorted(edges)
        for name, edges in IMPORT_EDGES.items()
    }
    assert {path: sorted(edges) for path, edges in found.items()} == expected


def test_only_exact_named_runtime_edges_import_new_leaves_and_no_dynamic_bootstrap():
    # No leaf-module exemption: internal imports are pinned as narrowly as live callers.
    assert_import_boundary(ROOT)


@pytest.mark.parametrize(
    "path, statement",
    [
        ("src/mechanical_cad/kernel_ocp.py", "from x import runtime_bundle_launch"),
        ("src/mechanical_cad/kernel_ocp.py", "import windows_runtime"),
        (
            "blender_addon/mechanical_cad_blender/part_publication.py",
            "from .windows_runtime import WindowsOperationOwner",
        ),
        (
            "blender_addon/mechanical_cad_blender/sidecar_job.py",
            "from .windows_runtime import WindowsOperationOwner as hidden",
        ),
        (
            "blender_addon/mechanical_cad_blender/sidecar_job.py",
            "from .windows_runtime import WindowsOperationOwner",
        ),
        (
            "blender_addon/mechanical_cad_blender/windows_runtime.py",
            "from . import runtime_bundle_prepare",
        ),
        (
            "blender_addon/mechanical_cad_blender/backend_runtime.py",
            "importlib.import_module('windows_runtime')",
        ),
        ("src/mechanical_cad/sidecar.py", "import runtime_bundle_prepare"),
        (
            "blender_addon/mechanical_cad_blender/part_publication.py",
            "from .runtime_bundle_launch import BundledOperationOwner",
        ),
        (
            "blender_addon/mechanical_cad_blender/guarded_evidence.py",
            "from . import runtime_bundle_materialize",
        ),
        (
            "blender_addon/mechanical_cad_blender/backend_runtime.py",
            "from .runtime_bundle_launch import BundledOperationOwner",
        ),
        (
            "blender_addon/mechanical_cad_blender/runtime_bundle_launch.py",
            "import standalone_child_bootstrap",
        ),
        (
            "blender_addon/mechanical_cad_blender/runtime_bundle_prepare.py",
            "__import__('standalone_child_bootstrap')",
        ),
        (
            "blender_addon/mechanical_cad_blender/backend_selection.py",
            "importlib.import_module('runtime_bundle_pin')",
        ),
        ("src/mechanical_cad/model.py", "module_name = 'pkg.runtime_bundle_manifest'"),
        (
            "blender_addon/mechanical_cad_blender/backend_runtime.py",
            "from .runtime_bundle_prepare import BundlePreparationJob",
        ),
    ],
)
def test_new_importers_symbols_duplicates_and_dynamic_names_reject(tmp_path, path, statement):
    namespace = guard_namespace()
    namespace["copy_python_guard_tree"](tmp_path)
    target = tmp_path / path
    target.write_bytes(target.read_bytes() + b"\n" + statement.encode() + b"\n")
    with pytest.raises(AssertionError):
        assert_import_boundary(tmp_path)
    with pytest.raises(AssertionError):
        namespace["protected_python_digest"](tmp_path)


@pytest.mark.parametrize(
    "path",
    [
        "blender_addon/mechanical_cad_blender/backend_platform.py",
        "blender_addon/mechanical_cad_blender/windows_process.py",
        "blender_addon/mechanical_cad_blender/runtime_bundle_manifest.py",
        "blender_addon/mechanical_cad_blender/runtime_bundle_materialize.py",
        "blender_addon/mechanical_cad_blender/runtime_bundle_pin.py",
        "scripts/package_standalone_extension.py",
        "scripts/standalone_child_bootstrap.py",
        "tests/unit/test_runtime_bundle_manifest.py",
        "tests/unit/test_runtime_bundle_materialize.py",
        "tests/unit/test_runtime_bundle_pin.py",
        "tests/unit/test_standalone_child_bootstrap.py",
        "tests/unit/test_windows_process.py",
        "tests/unit/test_standalone_extension_builder.py",
        "tests/unit/test_standalone_runtime_boundary.py",
    ],
)
def test_every_new_file_is_exactly_pinned_and_mutations_reject(tmp_path, path):
    namespace = guard_namespace()
    namespace["copy_python_guard_tree"](tmp_path)
    target = tmp_path / path
    target.write_bytes(target.read_bytes() + b"\n# unreviewed mutation\n")
    with pytest.raises(AssertionError):
        namespace["protected_python_digest"](tmp_path)


@pytest.mark.parametrize(
    "path",
    sorted(
        guard_namespace()["STANDALONE_LIVE_CHANGED"] | guard_namespace()["STANDALONE_LIVE_ADDED"]
    ),
)
def test_every_live_changed_or_added_path_is_exactly_pinned(tmp_path, path):
    namespace = guard_namespace()
    namespace["copy_python_guard_tree"](tmp_path)
    target = tmp_path / path
    target.write_bytes(target.read_bytes() + b"\n# unreviewed live mutation\n")
    with pytest.raises(AssertionError):
        namespace["protected_python_digest"](tmp_path)


def test_new_fixture_tampering_rejects_and_unlisted_python_changes_old_digest(tmp_path):
    namespace = guard_namespace()
    namespace["copy_python_guard_tree"](tmp_path)
    new = tmp_path / "blender_addon/mechanical_cad_blender/unreviewed_runtime.py"
    new.write_bytes(b"# unauthorized additional runtime leaf\n")
    assert namespace["protected_python_digest"](tmp_path) != namespace["SNAPSHOT3_PYTHON_PROTECTED"]
    fixture = tmp_path / namespace["STANDALONE_REVISION_FIXTURE"]
    fixture.write_bytes(fixture.read_bytes() + b"\n")
    with pytest.raises(AssertionError):
        namespace["protected_python_digest"](tmp_path)


def test_live_fixture_bytes_are_pinned_before_loading_any_delta(tmp_path):
    namespace = guard_namespace()
    namespace["copy_python_guard_tree"](tmp_path)
    fixture = tmp_path / namespace["STANDALONE_LIVE_FIXTURE"]
    fixture.write_bytes(fixture.read_bytes() + b"\n")
    with pytest.raises(AssertionError):
        namespace["protected_python_digest"](tmp_path)


@pytest.mark.parametrize(
    "path",
    [
        "src/mechanical_cad/unreviewed_live.py",
        "blender_addon/mechanical_cad_blender/unreviewed_live.py",
        "tests/unit/test_unreviewed_live.py",
    ],
)
def test_unlisted_live_python_paths_remain_in_historical_digest(tmp_path, path):
    namespace = guard_namespace()
    namespace["copy_python_guard_tree"](tmp_path)
    (tmp_path / path).write_bytes(b"pass\n")
    assert namespace["protected_python_digest"](tmp_path) != namespace["SNAPSHOT3_PYTHON_PROTECTED"]


def repin_test_fixture(namespace, root, revision):
    """Bypass only the outer seal in a test to exercise inner semantic assertions."""
    raw = (json.dumps(revision, sort_keys=True, indent=2) + "\n").encode()
    (root / namespace["STANDALONE_LIVE_FIXTURE"]).write_bytes(raw)
    namespace["STANDALONE_LIVE_SHA256"] = hashlib.sha256(raw).hexdigest()


@pytest.mark.parametrize(
    "mutation",
    [
        "schema",
        "base",
        "extra_key",
        "missing_added",
        "missing_changed",
        "added_path",
        "changed_path",
        "core_path",
        "original_hash",
        "reviewed_hash",
        "original_length",
        "reviewed_length",
        "entry_key",
        "hunk_key",
        "empty_hunks",
        "start_negative",
        "start_bool",
        "end_before_start",
        "end_overflow",
        "replacement",
        "original",
        "duplicate_hunk",
        "reversed_hunks",
    ],
)
def test_live_inverse_rejects_invalid_hunks_metadata_and_nonfinite_paths(tmp_path, mutation):
    namespace = guard_namespace()
    namespace["copy_python_guard_tree"](tmp_path)
    revision = json.loads((tmp_path / namespace["STANDALONE_LIVE_FIXTURE"]).read_bytes())
    name = "blender_addon/mechanical_cad_blender/backend_runtime.py"
    entry = revision["changed"][name]
    hunk = entry["hunks"][0]
    if mutation == "schema":
        revision["schema"] = "other"
    elif mutation == "base":
        revision["base_commit"] = "0" * 40
    elif mutation == "extra_key":
        revision["allow_other_paths"] = True
    elif mutation == "missing_added":
        revision["added"].pop(next(iter(revision["added"])))
    elif mutation == "missing_changed":
        revision["changed"].pop(name)
    elif mutation == "added_path":
        revision["added"]["../unreviewed.py"] = revision["added"].pop(next(iter(revision["added"])))
    elif mutation == "changed_path":
        revision["changed"]["blender_addon/../unreviewed.py"] = revision["changed"].pop(name)
    elif mutation == "core_path":
        revision["changed"]["src/mechanical_cad/kernel_ocp.py"] = revision["changed"].pop(name)
    elif mutation in {"original_hash", "reviewed_hash"}:
        entry[mutation.replace("_hash", "_sha256")] = "0" * 64
    elif mutation in {"original_length", "reviewed_length"}:
        entry[mutation.replace("_length", "_bytes")] = True
    elif mutation == "entry_key":
        entry["exempt"] = True
    elif mutation == "hunk_key":
        hunk["skip_validation"] = True
    elif mutation == "empty_hunks":
        entry["hunks"] = []
    elif mutation == "start_negative":
        hunk["new_start"] = -1
    elif mutation == "start_bool":
        hunk["new_start"] = False
    elif mutation == "end_before_start":
        hunk["new_end"] = hunk["new_start"] - 1
    elif mutation == "end_overflow":
        hunk["new_end"] = entry["reviewed_bytes"] + 1
    elif mutation == "replacement":
        hunk["replacement"] += "# altered reviewed bytes\n"
    elif mutation == "original":
        hunk["original"] += "# altered before bytes\n"
    elif mutation == "duplicate_hunk":
        entry["hunks"].insert(1, dict(hunk))
    else:
        assert mutation == "reversed_hunks" and len(entry["hunks"]) > 1
        entry["hunks"].reverse()
    repin_test_fixture(namespace, tmp_path, revision)
    with pytest.raises(AssertionError):
        namespace["protected_python_digest"](tmp_path)


@pytest.mark.parametrize(
    "name",
    [
        "blender_addon/mechanical_cad_blender/backend_runtime.py",
        "scripts/package_standalone_extension.py",
        "tests/unit/test_standalone_extension_builder.py",
        "tests/unit/test_standalone_runtime_boundary.py",
    ],
)
def test_forged_before_hash_cannot_replace_baseline_or_older_added_bytes(tmp_path, name):
    namespace = guard_namespace()
    namespace["copy_python_guard_tree"](tmp_path)
    _added, original = namespace["standalone_live_originals"](tmp_path)
    revision = json.loads((tmp_path / namespace["STANDALONE_LIVE_FIXTURE"]).read_bytes())
    entry = revision["changed"][name]
    # Even internally self-consistent forged originals must reach the unchanged
    # historical baseline/standalone checks instead of becoming exempt paths.
    before = original[name] + b"\n# forged baseline\n"
    reviewed = (tmp_path / name).read_bytes()
    entry["original_bytes"] = len(before)
    entry["original_sha256"] = hashlib.sha256(before).hexdigest()
    entry["hunks"] = [
        {
            "new_start": 0,
            "new_end": len(reviewed),
            "original": before.decode(),
            "replacement": reviewed.decode(),
        }
    ]
    repin_test_fixture(namespace, tmp_path, revision)
    with pytest.raises(AssertionError):
        namespace["protected_python_digest"](tmp_path)


def test_windows_inverse_restores_exact_reviewed_parent_before_older_guards():
    namespace = guard_namespace()
    harness = namespace["windows_transport_harness_originals"](historical_runtime_root())
    assert set(harness) == set(namespace["WINDOWS_TRANSPORT_HARNESS_ORIGINALS"])
    assert len(harness) == 5
    for path, data in harness.items():
        assert (len(data), hashlib.sha256(data).hexdigest()) == (
            namespace["WINDOWS_TRANSPORT_HARNESS_ORIGINALS"][path]
        )
    added, restored = namespace["windows_transport_originals"](historical_runtime_root())
    assert added == namespace["WINDOWS_TRANSPORT_REVISION_ADDED"]
    assert set(restored) == namespace["WINDOWS_TRANSPORT_REVISION_CHANGED"]
    assert len(added) == 4 and len(restored) == 8
    assert not any(path.startswith("src/") for path in added | restored.keys())
    old = namespace["standalone_harness_originals"](historical_runtime_root())
    assert_guard_source_bytes(
        old["tests/unit/test_arc_profile_native_end_cap.py"], namespace["STANDALONE_LIVE_SHA256"]
    )
    assert namespace["protected_python_digest"](historical_runtime_root()) == namespace["SNAPSHOT3_PYTHON_PROTECTED"]


@pytest.mark.parametrize(
    "path",
    sorted(
        guard_namespace()["WINDOWS_TRANSPORT_REVISION_CHANGED"]
        | guard_namespace()["WINDOWS_TRANSPORT_REVISION_ADDED"]
        | guard_namespace()["WINDOWS_TRANSPORT_HARNESS_ORIGINALS"].keys()
    ),
)
def test_every_windows_transport_and_harness_path_rejects_extra_bytes(tmp_path, path):
    namespace = guard_namespace()
    namespace["copy_python_guard_tree"](tmp_path)
    target = tmp_path / path
    target.write_bytes(target.read_bytes() + b"\n# unreviewed Windows transport mutation\n")
    with pytest.raises(AssertionError):
        namespace["protected_python_digest"](tmp_path)


@pytest.mark.parametrize(
    "key", ["WINDOWS_TRANSPORT_REVISION_FIXTURE", "WINDOWS_TRANSPORT_HARNESS_FIXTURE"]
)
def test_windows_fixture_digests_are_checked_before_loading(tmp_path, key):
    namespace = guard_namespace()
    namespace["copy_python_guard_tree"](tmp_path)
    target = tmp_path / namespace[key]
    target.write_bytes(target.read_bytes() + b"\n")
    with pytest.raises(AssertionError):
        namespace["protected_python_digest"](tmp_path)


@pytest.mark.parametrize("mutation", ["fixture", "slot", "helper", "coordinated"])
def test_windows_harness_pair_tampering_cannot_replace_trusted_validator(tmp_path, mutation):
    # The namespace always comes from the trusted source, never the copied tree.
    namespace = guard_namespace()
    namespace["copy_python_guard_tree"](tmp_path)
    fixture = tmp_path / namespace["WINDOWS_TRANSPORT_HARNESS_FIXTURE"]
    guard = tmp_path / "tests/unit/test_arc_profile_native_end_cap.py"
    if mutation in {"fixture", "coordinated"}:
        fixture.write_bytes(fixture.read_bytes() + b"\n")
    if mutation in {"slot", "coordinated"}:
        new_digest = hashlib.sha256(fixture.read_bytes()).hexdigest()
        if mutation == "slot":
            new_digest = "f" * 64
        old_slot = (
            'WINDOWS_TRANSPORT_HARNESS_SHA256 = (\n    "'
            + namespace["WINDOWS_TRANSPORT_HARNESS_SHA256"]
            + '"\n)'
        ).encode()
        new_slot = ('WINDOWS_TRANSPORT_HARNESS_SHA256 = (\n    "' + new_digest + '"\n)').encode()
        raw = guard.read_bytes()
        assert raw.count(old_slot) == 1
        guard.write_bytes(raw.replace(old_slot, new_slot))
    if mutation == "helper":
        raw = guard.read_bytes()
        before = b"def windows_transport_harness_originals(root):"
        assert raw.count(before) == 1
        guard.write_bytes(raw.replace(before, before + b" # unreviewed"))
    with pytest.raises(AssertionError):
        namespace["windows_transport_harness_originals"](tmp_path)


def repin_windows_harness_fixture_for_inner_control(namespace, root, revision):
    """Explicitly bypass the outer digest/slot only to test inner assertions."""
    cache_harness = namespace["windows_cache_harness_originals"](root)
    raw = (json.dumps(revision, sort_keys=True, indent=2) + "\n").encode()
    (root / namespace["WINDOWS_TRANSPORT_HARNESS_FIXTURE"]).write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    guard = root / "tests/unit/test_arc_profile_native_end_cap.py"
    old_slot = (
        'WINDOWS_TRANSPORT_HARNESS_SHA256 = (\n    "'
        + namespace["WINDOWS_TRANSPORT_HARNESS_SHA256"]
        + '"\n)'
    ).encode()
    new_slot = ('WINDOWS_TRANSPORT_HARNESS_SHA256 = (\n    "' + digest + '"\n)').encode()
    data = guard.read_bytes()
    assert data.count(old_slot) == 1
    guard.write_bytes(data.replace(old_slot, new_slot))
    namespace["WINDOWS_TRANSPORT_HARNESS_SHA256"] = digest

    path = "tests/unit/test_arc_profile_native_end_cap.py"
    historical = cache_harness[path]
    assert historical.count(old_slot) == 1
    cache_harness[path] = historical.replace(old_slot, new_slot)
    namespace["windows_cache_harness_originals"] = lambda _root: cache_harness


@pytest.mark.parametrize(
    "mutation",
    [
        "schema",
        "base",
        "extra_key",
        "missing_path",
        "extra_path",
        "production_path",
        "original_hash",
        "reviewed_hash",
        "original_length",
        "reviewed_length",
        "entry_key",
        "hunk_key",
        "empty_hunks",
        "start_negative",
        "start_bool",
        "end_bool",
        "end_before_start",
        "end_overflow",
        "replacement",
        "original",
        "duplicate_hunk",
        "reversed_hunks",
        "forged_original",
    ],
)
def test_windows_harness_inverse_rejects_invalid_hunks_metadata_and_non_test_paths(
    tmp_path, mutation
):
    namespace = guard_namespace()
    namespace["copy_python_guard_tree"](tmp_path)
    revision = json.loads((tmp_path / namespace["WINDOWS_TRANSPORT_HARNESS_FIXTURE"]).read_bytes())
    name = "tests/unit/test_arc_profile_incidence.py"
    entry = revision["changed"][name]
    hunk = entry["hunks"][0]
    if mutation == "schema":
        revision["schema"] = "other"
    elif mutation == "base":
        revision["base_commit"] = "0" * 40
    elif mutation == "extra_key":
        revision["allow_other_paths"] = True
    elif mutation == "missing_path":
        revision["changed"].pop(name)
    elif mutation == "extra_path":
        revision["changed"]["tests/unit/test_unreviewed.py"] = dict(entry)
    elif mutation == "production_path":
        revision["changed"]["src/mechanical_cad/kernel_ocp.py"] = revision["changed"].pop(name)
    elif mutation in {"original_hash", "reviewed_hash"}:
        entry[mutation.replace("_hash", "_sha256")] = "0" * 64
    elif mutation in {"original_length", "reviewed_length"}:
        entry[mutation.replace("_length", "_bytes")] = True
    elif mutation == "entry_key":
        entry["exempt"] = True
    elif mutation == "hunk_key":
        hunk["skip_validation"] = True
    elif mutation == "empty_hunks":
        entry["hunks"] = []
    elif mutation == "start_negative":
        hunk["new_start"] = -1
    elif mutation == "start_bool":
        hunk["new_start"] = False
    elif mutation == "end_bool":
        hunk["new_end"] = True
    elif mutation == "end_before_start":
        hunk["new_end"] = hunk["new_start"] - 1
    elif mutation == "end_overflow":
        hunk["new_end"] = entry["reviewed_bytes"] + 1
    elif mutation == "replacement":
        hunk["replacement"] += "# altered reviewed bytes\n"
    elif mutation == "original":
        hunk["original"] += "# altered before bytes\n"
    elif mutation == "duplicate_hunk":
        entry["hunks"].insert(1, dict(hunk))
    elif mutation == "reversed_hunks":
        assert len(entry["hunks"]) > 1
        entry["hunks"].reverse()
    else:
        assert mutation == "forged_original"
        restored = (
            namespace["windows_transport_harness_originals"](tmp_path)[name] + b"\n# forged\n"
        )
        current = (tmp_path / name).read_bytes()
        entry["original_bytes"] = len(restored)
        entry["original_sha256"] = hashlib.sha256(restored).hexdigest()
        entry["hunks"] = [
            {
                "new_start": 0,
                "new_end": len(current),
                "original": restored.decode(),
                "replacement": current.decode(),
            }
        ]
    repin_windows_harness_fixture_for_inner_control(namespace, tmp_path, revision)
    with pytest.raises(AssertionError):
        namespace["windows_transport_harness_originals"](tmp_path)


def repin_windows_revision_fixture(namespace, root, revision):
    """Bypass only the outer seal in a test to exercise inner semantic assertions."""
    raw = (json.dumps(revision, sort_keys=True, indent=2) + "\n").encode()
    (root / namespace["WINDOWS_TRANSPORT_REVISION_FIXTURE"]).write_bytes(raw)
    namespace["WINDOWS_TRANSPORT_REVISION_SHA256"] = hashlib.sha256(raw).hexdigest()


@pytest.mark.parametrize(
    "mutation",
    [
        "schema",
        "base",
        "extra_key",
        "missing_added",
        "missing_changed",
        "added_path",
        "changed_path",
        "core_path",
        "original_hash",
        "reviewed_hash",
        "original_length",
        "reviewed_length",
        "entry_key",
        "hunk_key",
        "empty_hunks",
        "start_negative",
        "start_bool",
        "end_before_start",
        "end_overflow",
        "replacement",
        "original",
        "duplicate_hunk",
        "reversed_hunks",
    ],
)
def test_windows_inverse_rejects_invalid_hunks_metadata_and_nonfinite_paths(tmp_path, mutation):
    namespace = guard_namespace()
    namespace["copy_python_guard_tree"](tmp_path)
    revision = json.loads((tmp_path / namespace["WINDOWS_TRANSPORT_REVISION_FIXTURE"]).read_bytes())
    name = "blender_addon/mechanical_cad_blender/backend_selection.py"
    entry = revision["changed"][name]
    hunk = entry["hunks"][0]
    if mutation == "schema":
        revision["schema"] = "other"
    elif mutation == "base":
        revision["base_commit"] = "0" * 40
    elif mutation == "extra_key":
        revision["allow_other_paths"] = True
    elif mutation == "missing_added":
        revision["added"].pop(next(iter(revision["added"])))
    elif mutation == "missing_changed":
        revision["changed"].pop(name)
    elif mutation == "added_path":
        revision["added"]["../unreviewed.py"] = revision["added"].pop(next(iter(revision["added"])))
    elif mutation == "changed_path":
        revision["changed"]["blender_addon/../unreviewed.py"] = revision["changed"].pop(name)
    elif mutation == "core_path":
        revision["changed"]["src/mechanical_cad/kernel_ocp.py"] = revision["changed"].pop(name)
    elif mutation in {"original_hash", "reviewed_hash"}:
        entry[mutation.replace("_hash", "_sha256")] = "0" * 64
    elif mutation in {"original_length", "reviewed_length"}:
        entry[mutation.replace("_length", "_bytes")] = True
    elif mutation == "entry_key":
        entry["exempt"] = True
    elif mutation == "hunk_key":
        hunk["skip_validation"] = True
    elif mutation == "empty_hunks":
        entry["hunks"] = []
    elif mutation == "start_negative":
        hunk["new_start"] = -1
    elif mutation == "start_bool":
        hunk["new_start"] = False
    elif mutation == "end_before_start":
        hunk["new_end"] = hunk["new_start"] - 1
    elif mutation == "end_overflow":
        hunk["new_end"] = entry["reviewed_bytes"] + 1
    elif mutation == "replacement":
        hunk["replacement"] += "# altered reviewed bytes\n"
    elif mutation == "original":
        hunk["original"] += "# altered before bytes\n"
    elif mutation == "duplicate_hunk":
        entry["hunks"].insert(1, dict(hunk))
    else:
        assert mutation == "reversed_hunks" and len(entry["hunks"]) > 1
        entry["hunks"].reverse()
    repin_windows_revision_fixture(namespace, tmp_path, revision)
    with pytest.raises(AssertionError):
        namespace["protected_python_digest"](tmp_path)


@pytest.mark.parametrize("path", sorted(guard_namespace()["WINDOWS_TRANSPORT_REVISION_CHANGED"]))
def test_forged_windows_before_bytes_must_reach_unchanged_historical_guards(tmp_path, path):
    namespace = guard_namespace()
    namespace["copy_python_guard_tree"](tmp_path)
    _, original = namespace["windows_transport_originals"](tmp_path)
    revision = json.loads((tmp_path / namespace["WINDOWS_TRANSPORT_REVISION_FIXTURE"]).read_bytes())
    entry = revision["changed"][path]
    before = original[path] + b"\n# forged Windows before bytes\n"
    reviewed = (tmp_path / path).read_bytes()
    entry["original_bytes"] = len(before)
    entry["original_sha256"] = hashlib.sha256(before).hexdigest()
    entry["hunks"] = [
        {
            "new_start": 0,
            "new_end": len(reviewed),
            "original": before.decode(),
            "replacement": reviewed.decode(),
        }
    ]
    repin_windows_revision_fixture(namespace, tmp_path, revision)
    with pytest.raises(AssertionError):
        namespace["protected_python_digest"](tmp_path)


def assert_windows_qualification_constructor_is_dormant(root):
    name = "_capture_windows_bundled_transport"
    definitions = []
    for prefix in ("src", "blender_addon"):
        for path in (root / prefix).rglob("*.py"):
            tree = ast.parse(path.read_bytes())
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
                    definitions.append(path.relative_to(root).as_posix())
                    parents = [
                        parent
                        for parent in ast.walk(tree)
                        if isinstance(parent, ast.ClassDef) and node in parent.body
                    ]
                    assert len(parents) == 1 and parents[0].name == "BackendSelection"
                    assert [ast.unparse(value) for value in node.decorator_list] == ["classmethod"]
                if isinstance(node, ast.Name):
                    assert node.id != name, path
                elif isinstance(node, ast.Attribute):
                    assert node.attr != name, path
                elif isinstance(node, ast.alias):
                    assert name not in node.name and name not in (node.asname or ""), path
                elif isinstance(node, ast.Constant) and type(node.value) is str:
                    assert name not in node.value, path
    assert definitions == ["blender_addon/mechanical_cad_blender/backend_selection.py"]


def test_windows_qualification_constructor_has_no_production_callers_aliases_or_dynamic_names():
    assert_windows_qualification_constructor_is_dormant(ROOT)


@pytest.mark.parametrize(
    "statement",
    [
        "BackendSelection._capture_windows_bundled_transport(policy)",
        "alias = BackendSelection._capture_windows_bundled_transport",
        "_capture_windows_bundled_transport(policy)",
        "getattr(BackendSelection, '_capture_windows_bundled_transport')(policy)",
        "from .backend_selection import _capture_windows_bundled_transport as hidden",
        "def _capture_windows_bundled_transport(): pass",
    ],
)
def test_windows_qualification_constructor_new_caller_or_alias_rejects(tmp_path, statement):
    namespace = guard_namespace()
    namespace["copy_python_guard_tree"](tmp_path)
    target = tmp_path / "blender_addon/mechanical_cad_blender/backend_runtime.py"
    target.write_bytes(target.read_bytes() + b"\n" + statement.encode() + b"\n")
    with pytest.raises(AssertionError):
        assert_windows_qualification_constructor_is_dormant(tmp_path)
    with pytest.raises(AssertionError):
        namespace["protected_python_digest"](tmp_path)


WINDOWS_CALL_EDGES = {
    "WindowsOperationOwner": [("sidecar_job.py", "SidecarJob._exchange_windows")],
    "WindowsOwnedProcess": [("windows_runtime.py", "WindowsOperationOwner._acquire")],
    "WindowsRuntimeAPI": [("windows_runtime.py", "WindowsOperationOwner._acquire")],
    "WindowsRuntimeValidation": [("windows_runtime.py", "WindowsOperationOwner._acquire")],
    "_TrackedProcessAPI": [("windows_runtime.py", "WindowsOperationOwner._acquire")],
    "_verify_cached_tree": [("windows_runtime.py", "WindowsOperationOwner._acquire")],
    "_read_launch_inputs": [("windows_runtime.py", "WindowsOperationOwner._acquire")],
}


def assert_windows_transport_call_edges(root):
    found = {name: [] for name in WINDOWS_CALL_EDGES}
    for prefix in ("src", "blender_addon"):
        for path in (root / prefix).rglob("*.py"):
            tree = ast.parse(path.read_bytes())
            parents = {
                child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)
            }
            for node in ast.walk(tree):
                if isinstance(node, ast.Name) and node.id in found:
                    parent = parents[node]
                    assert isinstance(parent, ast.Call) and parent.func is node, path
                    owners = []
                    while parent in parents:
                        parent = parents[parent]
                        if isinstance(
                            parent, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
                        ):
                            owners.append(parent.name)
                    assert path.parent == root / "blender_addon/mechanical_cad_blender", path
                    found[node.id].append((path.name, ".".join(reversed(owners))))
                elif isinstance(node, ast.Attribute):
                    assert node.attr not in found, path
                elif isinstance(node, ast.Constant) and type(node.value) is str:
                    assert not any(name in node.value for name in found), path
    assert found == WINDOWS_CALL_EDGES


def test_windows_transport_owner_and_input_seams_have_exact_callers():
    assert_windows_transport_call_edges(ROOT)


@pytest.mark.parametrize(
    "statement",
    [
        "WindowsOperationOwner(policy, payload)",
        "alias = WindowsOperationOwner",
        "runtime.WindowsOperationOwner(policy, payload)",
        "getattr(runtime, 'WindowsOperationOwner')(policy, payload)",
        "WindowsOwnedProcess(spec, pin, validation)",
        "_verify_cached_tree(policy, pin, cancelled)",
        "_read_launch_inputs(policy)",
    ],
)
def test_windows_transport_extra_callers_aliases_and_dynamic_names_reject(tmp_path, statement):
    namespace = guard_namespace()
    namespace["copy_python_guard_tree"](tmp_path)
    target = tmp_path / "blender_addon/mechanical_cad_blender/backend_runtime.py"
    target.write_bytes(target.read_bytes() + b"\n" + statement.encode() + b"\n")
    with pytest.raises(AssertionError):
        assert_windows_transport_call_edges(tmp_path)
    with pytest.raises(AssertionError):
        namespace["protected_python_digest"](tmp_path)


@pytest.mark.parametrize(
    "constant",
    [
        "WINDOWS_TRANSPORT_REVISION_SHA256",
        "STANDALONE_HARNESS_SHA256",
        "STANDALONE_LIVE_SHA256",
    ],
)
def test_windows_harness_normalizes_no_other_digest_slot(tmp_path, constant):
    namespace = guard_namespace()
    namespace["copy_python_guard_tree"](tmp_path)
    guard = tmp_path / "tests/unit/test_arc_profile_native_end_cap.py"
    raw = guard.read_bytes()
    digest = namespace[constant].encode("ascii")
    assert raw.count(digest) == 1
    guard.write_bytes(raw.replace(digest, b"f" * 64))
    with pytest.raises(AssertionError):
        namespace["windows_transport_harness_originals"](tmp_path)


def test_windows_cache_inverse_restores_exact_reviewed_parent_before_older_guards():
    namespace = guard_namespace()
    harness = namespace["windows_cache_harness_originals"](historical_runtime_root())
    assert set(harness) == set(namespace["WINDOWS_CACHE_HARNESS_ORIGINALS"])
    assert len(harness) == 5
    for path, data in harness.items():
        assert (len(data), hashlib.sha256(data).hexdigest()) == (
            namespace["WINDOWS_CACHE_HARNESS_ORIGINALS"][path]
        )
    added, restored = namespace["windows_cache_originals"](historical_runtime_root())
    assert added == namespace["WINDOWS_CACHE_REVISION_ADDED"]
    assert set(restored) == namespace["WINDOWS_CACHE_REVISION_CHANGED"]
    assert len(added) == 3 and len(restored) == 7
    assert not any(path.startswith("src/") for path in added | restored.keys())
    old = namespace["standalone_harness_originals"](historical_runtime_root())
    assert_guard_source_bytes(
        old["tests/unit/test_arc_profile_native_end_cap.py"], namespace["STANDALONE_LIVE_SHA256"]
    )
    assert namespace["protected_python_digest"](historical_runtime_root()) == namespace["SNAPSHOT3_PYTHON_PROTECTED"]


@pytest.mark.parametrize(
    "path",
    sorted(
        guard_namespace()["WINDOWS_CACHE_REVISION_CHANGED"]
        | guard_namespace()["WINDOWS_CACHE_REVISION_ADDED"]
        | guard_namespace()["WINDOWS_CACHE_HARNESS_ORIGINALS"].keys()
    ),
)
def test_every_windows_cache_and_harness_path_rejects_extra_bytes(tmp_path, path):
    namespace = guard_namespace()
    namespace["copy_python_guard_tree"](tmp_path)
    target = tmp_path / path
    target.write_bytes(target.read_bytes() + b"\n# unreviewed Windows cache mutation\n")
    with pytest.raises(AssertionError):
        namespace["protected_python_digest"](tmp_path)


@pytest.mark.parametrize("key", ["WINDOWS_CACHE_REVISION_FIXTURE", "WINDOWS_CACHE_HARNESS_FIXTURE"])
def test_windows_cache_fixture_digests_are_checked_before_loading(tmp_path, key):
    namespace = guard_namespace()
    namespace["copy_python_guard_tree"](tmp_path)
    target = tmp_path / namespace[key]
    target.write_bytes(target.read_bytes() + b"\n")
    with pytest.raises(AssertionError):
        namespace["protected_python_digest"](tmp_path)


@pytest.mark.parametrize("mutation", ["fixture", "slot", "helper", "coordinated"])
def test_windows_cache_harness_pair_tampering_cannot_replace_trusted_validator(tmp_path, mutation):
    # The namespace always comes from the trusted source, never the copied tree.
    namespace = guard_namespace()
    namespace["copy_python_guard_tree"](tmp_path)
    fixture = tmp_path / namespace["WINDOWS_CACHE_HARNESS_FIXTURE"]
    guard = tmp_path / "tests/unit/test_arc_profile_native_end_cap.py"
    if mutation in {"fixture", "coordinated"}:
        fixture.write_bytes(fixture.read_bytes() + b"\n")
    if mutation in {"slot", "coordinated"}:
        new_digest = hashlib.sha256(fixture.read_bytes()).hexdigest()
        if mutation == "slot":
            new_digest = "f" * 64
        old_slot = (
            'WINDOWS_CACHE_HARNESS_SHA256 = "' + namespace["WINDOWS_CACHE_HARNESS_SHA256"] + '"'
        ).encode()
        new_slot = ('WINDOWS_CACHE_HARNESS_SHA256 = "' + new_digest + '"').encode()
        raw = guard.read_bytes()
        assert raw.count(old_slot) == 1
        guard.write_bytes(raw.replace(old_slot, new_slot))
    if mutation == "helper":
        raw = guard.read_bytes()
        before = b"def windows_cache_harness_originals(root):"
        assert raw.count(before) == 1
        guard.write_bytes(raw.replace(before, before + b" # unreviewed"))
    with pytest.raises(AssertionError):
        namespace["windows_cache_harness_originals"](tmp_path)


def repin_windows_cache_harness_fixture_for_inner_control(namespace, root, revision):
    """Explicitly bypass the outer digest/slot only to test inner assertions."""
    integration_harness = namespace["standalone_integration_harness_originals"](root)
    runtime_harness = namespace["windows_runtime_cache_harness_originals"](root)
    raw = (json.dumps(revision, sort_keys=True, indent=2) + "\n").encode()
    (root / namespace["WINDOWS_CACHE_HARNESS_FIXTURE"]).write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    guard = root / "tests/unit/test_arc_profile_native_end_cap.py"
    old_slot = (
        'WINDOWS_CACHE_HARNESS_SHA256 = "' + namespace["WINDOWS_CACHE_HARNESS_SHA256"] + '"'
    ).encode()
    new_slot = ('WINDOWS_CACHE_HARNESS_SHA256 = "' + digest + '"').encode()
    data = guard.read_bytes()
    assert data.count(old_slot) == 1
    guard.write_bytes(data.replace(old_slot, new_slot))
    namespace["WINDOWS_CACHE_HARNESS_SHA256"] = digest

    path = "tests/unit/test_arc_profile_native_end_cap.py"
    historical = runtime_harness[path]
    assert historical.count(old_slot) == 1
    runtime_harness[path] = historical.replace(old_slot, new_slot)
    namespace["windows_runtime_cache_harness_originals"] = lambda _root: runtime_harness
    historical = integration_harness[path]
    assert historical.count(old_slot) == 1
    integration_harness[path] = historical.replace(old_slot, new_slot)
    namespace["standalone_integration_harness_originals"] = lambda _root: integration_harness


@pytest.mark.parametrize(
    "mutation",
    [
        "schema",
        "base",
        "extra_key",
        "missing_path",
        "extra_path",
        "production_path",
        "original_hash",
        "reviewed_hash",
        "original_length",
        "reviewed_length",
        "entry_key",
        "hunk_key",
        "empty_hunks",
        "start_negative",
        "start_bool",
        "end_bool",
        "end_before_start",
        "end_overflow",
        "replacement",
        "original",
        "duplicate_hunk",
        "reversed_hunks",
        "forged_original",
    ],
)
def test_windows_cache_harness_inverse_rejects_invalid_hunks_metadata_and_non_test_paths(
    tmp_path, mutation
):
    namespace = guard_namespace()
    namespace["copy_python_guard_tree"](tmp_path)
    revision = json.loads((tmp_path / namespace["WINDOWS_CACHE_HARNESS_FIXTURE"]).read_bytes())
    name = "tests/unit/test_arc_profile_incidence.py"
    entry = revision["changed"][name]
    hunk = entry["hunks"][0]
    if mutation == "schema":
        revision["schema"] = "other"
    elif mutation == "base":
        revision["base_commit"] = "0" * 40
    elif mutation == "extra_key":
        revision["allow_other_paths"] = True
    elif mutation == "missing_path":
        revision["changed"].pop(name)
    elif mutation == "extra_path":
        revision["changed"]["tests/unit/test_unreviewed.py"] = dict(entry)
    elif mutation == "production_path":
        revision["changed"]["src/mechanical_cad/kernel_ocp.py"] = revision["changed"].pop(name)
    elif mutation in {"original_hash", "reviewed_hash"}:
        entry[mutation.replace("_hash", "_sha256")] = "0" * 64
    elif mutation in {"original_length", "reviewed_length"}:
        entry[mutation.replace("_length", "_bytes")] = True
    elif mutation == "entry_key":
        entry["exempt"] = True
    elif mutation == "hunk_key":
        hunk["skip_validation"] = True
    elif mutation == "empty_hunks":
        entry["hunks"] = []
    elif mutation == "start_negative":
        hunk["new_start"] = -1
    elif mutation == "start_bool":
        hunk["new_start"] = False
    elif mutation == "end_bool":
        hunk["new_end"] = True
    elif mutation == "end_before_start":
        hunk["new_end"] = hunk["new_start"] - 1
    elif mutation == "end_overflow":
        hunk["new_end"] = entry["reviewed_bytes"] + 1
    elif mutation == "replacement":
        hunk["replacement"] += "# altered reviewed bytes\n"
    elif mutation == "original":
        hunk["original"] += "# altered before bytes\n"
    elif mutation == "duplicate_hunk":
        entry["hunks"].insert(1, dict(hunk))
    elif mutation == "reversed_hunks":
        assert len(entry["hunks"]) > 1
        entry["hunks"].reverse()
    else:
        assert mutation == "forged_original"
        restored = namespace["windows_cache_harness_originals"](tmp_path)[name] + b"\n# forged\n"
        current = (tmp_path / name).read_bytes()
        entry["original_bytes"] = len(restored)
        entry["original_sha256"] = hashlib.sha256(restored).hexdigest()
        entry["hunks"] = [
            {
                "new_start": 0,
                "new_end": len(current),
                "original": restored.decode(),
                "replacement": current.decode(),
            }
        ]
    repin_windows_cache_harness_fixture_for_inner_control(namespace, tmp_path, revision)
    with pytest.raises(AssertionError):
        namespace["windows_cache_harness_originals"](tmp_path)


def repin_windows_cache_revision_fixture(namespace, root, revision):
    """Bypass only the outer seal in a test to exercise inner semantic assertions."""
    raw = (json.dumps(revision, sort_keys=True, indent=2) + "\n").encode()
    (root / namespace["WINDOWS_CACHE_REVISION_FIXTURE"]).write_bytes(raw)
    namespace["WINDOWS_CACHE_REVISION_SHA256"] = hashlib.sha256(raw).hexdigest()


@pytest.mark.parametrize(
    "mutation",
    [
        "schema",
        "base",
        "extra_key",
        "missing_added",
        "missing_changed",
        "added_path",
        "changed_path",
        "core_path",
        "original_hash",
        "reviewed_hash",
        "original_length",
        "reviewed_length",
        "entry_key",
        "hunk_key",
        "empty_hunks",
        "start_negative",
        "start_bool",
        "end_before_start",
        "end_overflow",
        "replacement",
        "original",
        "duplicate_hunk",
        "reversed_hunks",
    ],
)
def test_windows_cache_inverse_rejects_invalid_hunks_metadata_and_nonfinite_paths(
    tmp_path, mutation
):
    namespace = guard_namespace()
    namespace["copy_python_guard_tree"](tmp_path)
    revision = json.loads((tmp_path / namespace["WINDOWS_CACHE_REVISION_FIXTURE"]).read_bytes())
    name = "blender_addon/mechanical_cad_blender/runtime_bundle_prepare.py"
    entry = revision["changed"][name]
    hunk = entry["hunks"][0]
    if mutation == "schema":
        revision["schema"] = "other"
    elif mutation == "base":
        revision["base_commit"] = "0" * 40
    elif mutation == "extra_key":
        revision["allow_other_paths"] = True
    elif mutation == "missing_added":
        revision["added"].pop(next(iter(revision["added"])))
    elif mutation == "missing_changed":
        revision["changed"].pop(name)
    elif mutation == "added_path":
        revision["added"]["../unreviewed.py"] = revision["added"].pop(next(iter(revision["added"])))
    elif mutation == "changed_path":
        revision["changed"]["blender_addon/../unreviewed.py"] = revision["changed"].pop(name)
    elif mutation == "core_path":
        revision["changed"]["src/mechanical_cad/kernel_ocp.py"] = revision["changed"].pop(name)
    elif mutation in {"original_hash", "reviewed_hash"}:
        entry[mutation.replace("_hash", "_sha256")] = "0" * 64
    elif mutation in {"original_length", "reviewed_length"}:
        entry[mutation.replace("_length", "_bytes")] = True
    elif mutation == "entry_key":
        entry["exempt"] = True
    elif mutation == "hunk_key":
        hunk["skip_validation"] = True
    elif mutation == "empty_hunks":
        entry["hunks"] = []
    elif mutation == "start_negative":
        hunk["new_start"] = -1
    elif mutation == "start_bool":
        hunk["new_start"] = False
    elif mutation == "end_before_start":
        hunk["new_end"] = hunk["new_start"] - 1
    elif mutation == "end_overflow":
        hunk["new_end"] = entry["reviewed_bytes"] + 1
    elif mutation == "replacement":
        hunk["replacement"] += "# altered reviewed bytes\n"
    elif mutation == "original":
        hunk["original"] += "# altered before bytes\n"
    elif mutation == "duplicate_hunk":
        entry["hunks"].insert(1, dict(hunk))
    else:
        assert mutation == "reversed_hunks" and len(entry["hunks"]) > 1
        entry["hunks"].reverse()
    repin_windows_cache_revision_fixture(namespace, tmp_path, revision)
    with pytest.raises(AssertionError):
        namespace["protected_python_digest"](tmp_path)


@pytest.mark.parametrize("path", sorted(guard_namespace()["WINDOWS_CACHE_REVISION_CHANGED"]))
def test_forged_windows_cache_before_bytes_cannot_replace_transport_predecessor(tmp_path, path):
    namespace = guard_namespace()
    namespace["copy_python_guard_tree"](tmp_path)
    _, original = namespace["windows_cache_originals"](tmp_path)
    revision = json.loads((tmp_path / namespace["WINDOWS_CACHE_REVISION_FIXTURE"]).read_bytes())
    entry = revision["changed"][path]
    before = original[path] + b"\n# forged Windows before bytes\n"
    reviewed = (tmp_path / path).read_bytes()
    entry["original_bytes"] = len(before)
    entry["original_sha256"] = hashlib.sha256(before).hexdigest()
    entry["hunks"] = [
        {
            "new_start": 0,
            "new_end": len(reviewed),
            "original": before.decode(),
            "replacement": reviewed.decode(),
        }
    ]
    repin_windows_cache_revision_fixture(namespace, tmp_path, revision)
    with pytest.raises(AssertionError):
        namespace["protected_python_digest"](tmp_path)


@pytest.mark.parametrize(
    "constant",
    [
        "WINDOWS_CACHE_REVISION_SHA256",
        "WINDOWS_TRANSPORT_REVISION_SHA256",
        "WINDOWS_TRANSPORT_HARNESS_SHA256",
        "STANDALONE_HARNESS_SHA256",
        "STANDALONE_LIVE_SHA256",
    ],
)
def test_windows_cache_harness_normalizes_no_other_digest_slot(tmp_path, constant):
    namespace = guard_namespace()
    namespace["copy_python_guard_tree"](tmp_path)
    guard = tmp_path / "tests/unit/test_arc_profile_native_end_cap.py"
    raw = guard.read_bytes()
    digest = namespace[constant].encode("ascii")
    assert raw.count(digest) == 1
    guard.write_bytes(raw.replace(digest, b"f" * 64))
    with pytest.raises(AssertionError):
        namespace["windows_cache_harness_originals"](tmp_path)


def assert_windows_cache_dependency_leaf(root):
    path = root / "blender_addon/mechanical_cad_blender/windows_cache.py"
    consumers = {
        "runtime_bundle_launch",
        "runtime_bundle_materialize",
        "runtime_bundle_prepare",
        "windows_runtime",
        "backend_runtime",
        "registration",
    }
    for node in ast.walk(ast.parse(path.read_bytes())):
        if isinstance(node, ast.Import):
            assert all(alias.name.split(".")[0] in sys.stdlib_module_names for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                assert node.level == 1 and node.module == "runtime_bundle_manifest"
            else:
                assert (node.module or "").split(".")[0] in sys.stdlib_module_names
        elif isinstance(node, ast.Call):
            assert not (
                isinstance(node.func, ast.Name)
                and node.func.id == "__import__"
                or isinstance(node.func, ast.Attribute)
                and node.func.attr == "import_module"
            )
        elif isinstance(node, ast.Constant) and type(node.value) is str:
            assert not consumers.intersection(node.value.split("."))


def test_windows_cache_has_only_standard_library_and_exact_lower_manifest_edges():
    assert_windows_cache_dependency_leaf(ROOT)
    assert_import_boundary(ROOT)


@pytest.mark.parametrize(
    "statement",
    [
        "from .runtime_bundle_launch import _windows_path",
        "def delayed():\n    from .runtime_bundle_prepare import BundlePreparationJob",
        "from . import registration",
        "from .windows_runtime import WindowsOperationOwner",
        "from .backend_runtime import begin_bundled_setup",
        "import OCP",
        "__import__('runtime_bundle_materialize')",
        "importlib.import_module('mechanical_cad_blender.runtime_bundle_launch')",
    ],
)
def test_windows_cache_consumer_edges_are_rejected_even_when_deferred(tmp_path, statement):
    namespace = guard_namespace()
    namespace["copy_python_guard_tree"](tmp_path)
    target = tmp_path / "blender_addon/mechanical_cad_blender/windows_cache.py"
    target.write_bytes(target.read_bytes() + b"\n" + statement.encode() + b"\n")
    with pytest.raises(AssertionError):
        assert_windows_cache_dependency_leaf(tmp_path)
    with pytest.raises(AssertionError):
        namespace["protected_python_digest"](tmp_path)


@pytest.mark.parametrize(
    "path, statement",
    [
        ("backend_runtime.py", "from .windows_cache import WindowsCacheOwner"),
        ("registration.py", "from .windows_cache import query_windows_cache_location"),
        ("runtime_bundle_launch.py", "from .windows_cache import WindowsCacheLocation"),
        ("windows_runtime.py", "from .windows_cache import WindowsCacheOwner"),
        ("runtime_bundle_prepare.py", "from .windows_cache import WindowsCacheOwner as callback"),
        ("runtime_bundle_materialize.py", "from .windows_cache import WindowsCacheOwner"),
        ("backend_selection.py", "__import__('mechanical_cad_blender.windows_cache')"),
    ],
)
def test_windows_cache_extra_importers_symbols_aliases_and_duplicates_reject(
    tmp_path, path, statement
):
    namespace = guard_namespace()
    namespace["copy_python_guard_tree"](tmp_path)
    target = tmp_path / "blender_addon/mechanical_cad_blender" / path
    target.write_bytes(target.read_bytes() + b"\n" + statement.encode() + b"\n")
    with pytest.raises(AssertionError):
        assert_import_boundary(tmp_path)


def assert_windows_cache_qualification_is_dormant(root):
    name = "for_windows_qualification"
    definitions = []
    for prefix in ("src", "blender_addon"):
        for path in (root / prefix).rglob("*.py"):
            tree = ast.parse(path.read_bytes())
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
                    definitions.append(path.relative_to(root).as_posix())
                    parents = [
                        parent
                        for parent in ast.walk(tree)
                        if isinstance(parent, ast.ClassDef) and node in parent.body
                    ]
                    assert len(parents) == 1 and parents[0].name == "BundlePreparationJob"
                    assert [ast.unparse(value) for value in node.decorator_list] == ["classmethod"]
                if isinstance(node, ast.Name):
                    assert node.id != name, path
                elif isinstance(node, ast.Attribute):
                    assert node.attr != name, path
                elif isinstance(node, ast.alias):
                    assert name not in node.name and name not in (node.asname or ""), path
                elif isinstance(node, ast.Constant) and type(node.value) is str:
                    assert name not in node.value, path
    assert definitions == ["blender_addon/mechanical_cad_blender/runtime_bundle_prepare.py"]


def test_windows_cache_qualification_has_no_production_caller_alias_or_dynamic_name():
    assert_windows_cache_qualification_is_dormant(ROOT)


@pytest.mark.parametrize(
    "statement",
    [
        "BundlePreparationJob.for_windows_qualification(package, location, release)",
        "alias = BundlePreparationJob.for_windows_qualification",
        "for_windows_qualification(package, location, release)",
        "getattr(BundlePreparationJob, 'for_windows_qualification')()",
        "from .runtime_bundle_prepare import for_windows_qualification as hidden",
        "def for_windows_qualification(): pass",
    ],
)
def test_windows_cache_qualification_extra_callers_and_aliases_reject(tmp_path, statement):
    namespace = guard_namespace()
    namespace["copy_python_guard_tree"](tmp_path)
    target = tmp_path / "blender_addon/mechanical_cad_blender/backend_runtime.py"
    target.write_bytes(target.read_bytes() + b"\n" + statement.encode() + b"\n")
    with pytest.raises(AssertionError):
        assert_windows_cache_qualification_is_dormant(tmp_path)


def assert_windows_cache_materializer_scope(root):
    # Read the trusted source's inverse, never validator code from a mutation tree.
    namespace = guard_namespace()
    _, originals = namespace["windows_cache_originals"](historical_runtime_root())
    relative = "blender_addon/mechanical_cad_blender/runtime_bundle_materialize.py"
    original = originals[relative]
    current = (root / relative).read_bytes()
    edge = b"from .windows_cache import WindowsCacheCancelled, WindowsCacheOwner\n"
    assert current.count(edge) == 1
    current = current.replace(edge, b"", 1)
    allowed = {"_documents", "_inventory", "verify_cached_bundle", "materialize_bundle"}

    def protected(data):
        lines = data.splitlines(keepends=True)
        nodes = [
            node
            for node in ast.parse(data).body
            if isinstance(node, ast.FunctionDef) and node.name in allowed
        ]
        assert {node.name for node in nodes} == allowed and len(nodes) == 4
        for node in reversed(nodes):
            lines[node.lineno - 1 : node.end_lineno] = [node.name.encode() + b"\n"]
        return b"".join(lines)

    assert protected(current) == protected(original)


def assert_windows_cache_concrete_inventory(root):
    relative = "blender_addon/mechanical_cad_blender/runtime_bundle_materialize.py"
    raw = (root / relative).read_bytes()
    tree = ast.parse(raw)
    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    for name in ("_documents", "_inventory", "verify_cached_bundle", "materialize_bundle"):
        assert any(
            isinstance(node, ast.Compare)
            and ast.unparse(node) == "type(windows_storage) is not WindowsCacheOwner"
            for node in ast.walk(functions[name])
        ), name
    inventory = functions["_inventory"]
    literal = b"if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:"
    assert raw.count(literal) == 1
    expected = ast.parse(
        "if windows_storage is None:\n"
        "    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:\n"
        "        raise BundleError('Runtime inventory requires independent regular files.')\n"
        "else:\n"
        "    if not stat.S_ISREG(info.st_mode):\n"
        "        raise BundleError('Runtime inventory requires independent regular files.')\n"
        "    windows_storage.check_private_entry(parent / entry.name, directory=False)\n"
    ).body[0]
    branches = [
        node
        for node in ast.walk(inventory)
        if isinstance(node, ast.If) and ast.unparse(node.test) == "windows_storage is None"
    ]
    assert len(branches) == 1 and ast.dump(branches[0]) == ast.dump(expected)
    containers = [
        node
        for node in ast.walk(inventory)
        if type(getattr(node, "body", None)) is list and branches[0] in node.body
    ]
    assert len(containers) == 1
    body = containers[0].body
    markers = [
        node
        for node in body
        if isinstance(node, ast.If) and ast.unparse(node.test) == "relative == _READY and ready"
    ]
    assert len(markers) == 1 and body.index(branches[0]) < body.index(markers[0])
    materialize = functions["materialize_bundle"]
    diagnostics = [
        node
        for node in ast.walk(materialize)
        if isinstance(node, ast.If)
        and ast.unparse(node.test) == "type(windows_storage) is WindowsCacheOwner"
    ]
    assert len(diagnostics) == 2
    for branch in diagnostics:
        assert len(branch.body) == 1 and isinstance(branch.body[0], ast.Assign)
        assert ast.unparse(branch.body[0].value) == "windows_storage.owned_stage_path"
        assert ast.unparse(branch.orelse[0].value) == (
            "str(stage) if stage is not None and stage.exists() else None"
        )


def test_windows_cache_materializer_changes_only_four_functions_and_exact_import():
    assert_windows_cache_materializer_scope(ROOT)
    assert_windows_cache_concrete_inventory(ROOT)


@pytest.mark.parametrize(
    "before, after",
    [
        (
            b"type(windows_storage) is not WindowsCacheOwner",
            b"not isinstance(windows_storage, WindowsCacheOwner)",
        ),
        (
            b"if windows_storage is None:\n                    if not stat.S_ISREG",
            b"if False:\n                    if not stat.S_ISREG",
        ),
        (b"or info.st_nlink != 1:", b"or info.st_nlink > 1:"),
        (b"windows_storage.check_private_entry(parent / entry.name, directory=False)", b"None"),
        (
            b"retained = windows_storage.owned_stage_path",
            b"retained = str(stage) if stage.exists() else None",
        ),
    ],
)
def test_windows_cache_subclasses_callbacks_link_waivers_and_diagnostic_io_reject(
    tmp_path, before, after
):
    namespace = guard_namespace()
    namespace["copy_python_guard_tree"](tmp_path)
    target = tmp_path / "blender_addon/mechanical_cad_blender/runtime_bundle_materialize.py"
    raw = target.read_bytes()
    assert before in raw
    target.write_bytes(raw.replace(before, after))
    with pytest.raises(AssertionError):
        assert_windows_cache_concrete_inventory(tmp_path)


@pytest.mark.parametrize(
    "before, after",
    [
        (
            b"def _descriptor(root, release, manifest):",
            b"def _descriptor(root, release, manifest): # changed",
        ),
        (b'_READY = ".bundle-ready.json"', b'_READY = ".other-ready.json"'),
        (b"import hashlib", b"import hashlib\nimport platform"),
    ],
)
def test_windows_cache_fifth_function_constant_and_import_changes_reject(tmp_path, before, after):
    namespace = guard_namespace()
    namespace["copy_python_guard_tree"](tmp_path)
    target = tmp_path / "blender_addon/mechanical_cad_blender/runtime_bundle_materialize.py"
    raw = target.read_bytes()
    assert raw.count(before) == 1
    target.write_bytes(raw.replace(before, after))
    with pytest.raises(AssertionError):
        assert_windows_cache_materializer_scope(tmp_path)


def assert_windows_cache_query_is_dormant(root):
    name = "query_windows_cache_location"
    definitions = []
    for prefix in ("src", "blender_addon"):
        for path in (root / prefix).rglob("*.py"):
            tree = ast.parse(path.read_bytes())
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
                    definitions.append(path.relative_to(root).as_posix())
                    assert node in tree.body and not node.decorator_list
                if isinstance(node, ast.Name):
                    assert node.id != name, path
                elif isinstance(node, ast.Attribute):
                    assert node.attr != name, path
                elif isinstance(node, ast.alias):
                    assert name not in node.name and name not in (node.asname or ""), path
                elif isinstance(node, ast.Constant) and type(node.value) is str:
                    assert name not in node.value, path
    assert definitions == ["blender_addon/mechanical_cad_blender/windows_cache.py"]


def test_windows_cache_known_folder_query_has_no_production_caller_alias_or_dynamic_name():
    assert_windows_cache_query_is_dormant(ROOT)


@pytest.mark.parametrize(
    "statement",
    [
        "query_windows_cache_location()",
        "alias = windows_cache.query_windows_cache_location",
        "getattr(windows_cache, 'query_windows_cache_location')()",
        "from .windows_cache import query_windows_cache_location as hidden",
        "def query_windows_cache_location(): pass",
    ],
)
def test_windows_cache_known_folder_query_extra_callers_and_aliases_reject(tmp_path, statement):
    namespace = guard_namespace()
    namespace["copy_python_guard_tree"](tmp_path)
    target = tmp_path / "blender_addon/mechanical_cad_blender/registration.py"
    target.write_bytes(target.read_bytes() + b"\n" + statement.encode() + b"\n")
    with pytest.raises(AssertionError):
        assert_windows_cache_query_is_dormant(tmp_path)


def test_windows_runtime_cache_inverse_restores_exact_reviewed_parent_before_older_guards():
    namespace = guard_namespace()
    harness = namespace["windows_runtime_cache_harness_originals"](historical_runtime_root())
    assert set(harness) == set(namespace["WINDOWS_RUNTIME_CACHE_HARNESS_ORIGINALS"])
    assert len(harness) == 4
    for path, data in harness.items():
        assert (len(data), hashlib.sha256(data).hexdigest()) == (
            namespace["WINDOWS_RUNTIME_CACHE_HARNESS_ORIGINALS"][path]
        )
    added, restored = namespace["windows_runtime_cache_originals"](historical_runtime_root())
    assert added == namespace["WINDOWS_RUNTIME_CACHE_REVISION_ADDED"]
    assert set(restored) == namespace["WINDOWS_RUNTIME_CACHE_REVISION_CHANGED"]
    assert len(added) == 1 and len(restored) == 8
    assert not any(path.startswith("src/") for path in added | restored.keys())
    old = namespace["standalone_harness_originals"](historical_runtime_root())
    assert_guard_source_bytes(
        old["tests/unit/test_arc_profile_native_end_cap.py"], namespace["STANDALONE_LIVE_SHA256"]
    )
    assert namespace["protected_python_digest"](historical_runtime_root()) == namespace["SNAPSHOT3_PYTHON_PROTECTED"]


@pytest.mark.parametrize(
    "path",
    sorted(
        guard_namespace()["WINDOWS_RUNTIME_CACHE_REVISION_CHANGED"]
        | guard_namespace()["WINDOWS_RUNTIME_CACHE_REVISION_ADDED"]
        | guard_namespace()["WINDOWS_RUNTIME_CACHE_HARNESS_ORIGINALS"].keys()
    ),
)
def test_every_windows_runtime_cache_and_harness_path_rejects_extra_bytes(tmp_path, path):
    namespace = guard_namespace()
    namespace["copy_python_guard_tree"](tmp_path)
    target = tmp_path / path
    target.write_bytes(target.read_bytes() + b"\n# unreviewed Windows runtime-cache mutation\n")
    with pytest.raises(AssertionError):
        namespace["protected_python_digest"](tmp_path)


@pytest.mark.parametrize(
    "key", ["WINDOWS_RUNTIME_CACHE_REVISION_FIXTURE", "WINDOWS_RUNTIME_CACHE_HARNESS_FIXTURE"]
)
def test_windows_runtime_cache_fixture_digests_are_checked_before_loading(tmp_path, key):
    namespace = guard_namespace()
    namespace["copy_python_guard_tree"](tmp_path)
    target = tmp_path / namespace[key]
    target.write_bytes(target.read_bytes() + b"\n")
    with pytest.raises(AssertionError):
        namespace["protected_python_digest"](tmp_path)


@pytest.mark.parametrize("mutation", ["fixture", "slot", "helper", "coordinated"])
def test_windows_runtime_cache_harness_pair_tampering_cannot_replace_trusted_validator(
    tmp_path, mutation
):
    # The namespace always comes from the trusted source, never the copied tree.
    namespace = guard_namespace()
    namespace["copy_python_guard_tree"](tmp_path)
    fixture = tmp_path / namespace["WINDOWS_RUNTIME_CACHE_HARNESS_FIXTURE"]
    guard = tmp_path / "tests/unit/test_arc_profile_native_end_cap.py"
    if mutation in {"fixture", "coordinated"}:
        fixture.write_bytes(fixture.read_bytes() + b"\n")
    if mutation in {"slot", "coordinated"}:
        new_digest = hashlib.sha256(fixture.read_bytes()).hexdigest()
        if mutation == "slot":
            new_digest = "f" * 64
        old_slot = (
            'WINDOWS_RUNTIME_CACHE_HARNESS_SHA256 = (\n    "'
            + namespace["WINDOWS_RUNTIME_CACHE_HARNESS_SHA256"]
            + '"\n)'
        ).encode()
        new_slot = (
            'WINDOWS_RUNTIME_CACHE_HARNESS_SHA256 = (\n    "' + new_digest + '"\n)'
        ).encode()
        raw = guard.read_bytes()
        assert raw.count(old_slot) == 1
        guard.write_bytes(raw.replace(old_slot, new_slot))
    if mutation == "helper":
        raw = guard.read_bytes()
        before = b"def windows_runtime_cache_harness_originals(root):"
        assert raw.count(before) == 1
        guard.write_bytes(raw.replace(before, before + b" # unreviewed"))
    with pytest.raises(AssertionError):
        namespace["windows_runtime_cache_harness_originals"](tmp_path)


def repin_windows_runtime_cache_harness_fixture_for_inner_control(namespace, root, revision):
    """Explicitly bypass the outer digest/slot only to test inner assertions."""
    integration_harness = namespace["standalone_integration_harness_originals"](root)
    raw = (json.dumps(revision, sort_keys=True, indent=2) + "\n").encode()
    (root / namespace["WINDOWS_RUNTIME_CACHE_HARNESS_FIXTURE"]).write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    guard = root / "tests/unit/test_arc_profile_native_end_cap.py"
    old_slot = (
        'WINDOWS_RUNTIME_CACHE_HARNESS_SHA256 = (\n    "'
        + namespace["WINDOWS_RUNTIME_CACHE_HARNESS_SHA256"]
        + '"\n)'
    ).encode()
    new_slot = ('WINDOWS_RUNTIME_CACHE_HARNESS_SHA256 = (\n    "' + digest + '"\n)').encode()
    data = guard.read_bytes()
    assert data.count(old_slot) == 1
    guard.write_bytes(data.replace(old_slot, new_slot))
    namespace["WINDOWS_RUNTIME_CACHE_HARNESS_SHA256"] = digest

    path = "tests/unit/test_arc_profile_native_end_cap.py"
    historical = integration_harness[path]
    assert historical.count(old_slot) == 1
    integration_harness[path] = historical.replace(old_slot, new_slot)
    namespace["standalone_integration_harness_originals"] = lambda _root: integration_harness


@pytest.mark.parametrize(
    "mutation",
    [
        "schema",
        "base",
        "extra_key",
        "missing_path",
        "extra_path",
        "production_path",
        "original_hash",
        "reviewed_hash",
        "original_length",
        "reviewed_length",
        "entry_key",
        "hunk_key",
        "empty_hunks",
        "start_negative",
        "start_bool",
        "end_bool",
        "end_before_start",
        "end_overflow",
        "replacement",
        "original",
        "duplicate_hunk",
        "reversed_hunks",
        "forged_original",
    ],
)
def test_windows_runtime_cache_harness_inverse_rejects_invalid_hunks_metadata_and_non_test_paths(
    tmp_path, mutation
):
    namespace = guard_namespace()
    namespace["copy_python_guard_tree"](tmp_path)
    revision = json.loads(
        (tmp_path / namespace["WINDOWS_RUNTIME_CACHE_HARNESS_FIXTURE"]).read_bytes()
    )
    name = "tests/unit/test_arc_profile_incidence.py"
    entry = revision["changed"][name]
    hunk = entry["hunks"][0]
    if mutation == "schema":
        revision["schema"] = "other"
    elif mutation == "base":
        revision["base_commit"] = "0" * 40
    elif mutation == "extra_key":
        revision["allow_other_paths"] = True
    elif mutation == "missing_path":
        revision["changed"].pop(name)
    elif mutation == "extra_path":
        revision["changed"]["tests/unit/test_unreviewed.py"] = dict(entry)
    elif mutation == "production_path":
        revision["changed"]["src/mechanical_cad/kernel_ocp.py"] = revision["changed"].pop(name)
    elif mutation in {"original_hash", "reviewed_hash"}:
        entry[mutation.replace("_hash", "_sha256")] = "0" * 64
    elif mutation in {"original_length", "reviewed_length"}:
        entry[mutation.replace("_length", "_bytes")] = True
    elif mutation == "entry_key":
        entry["exempt"] = True
    elif mutation == "hunk_key":
        hunk["skip_validation"] = True
    elif mutation == "empty_hunks":
        entry["hunks"] = []
    elif mutation == "start_negative":
        hunk["new_start"] = -1
    elif mutation == "start_bool":
        hunk["new_start"] = False
    elif mutation == "end_bool":
        hunk["new_end"] = True
    elif mutation == "end_before_start":
        hunk["new_end"] = hunk["new_start"] - 1
    elif mutation == "end_overflow":
        hunk["new_end"] = entry["reviewed_bytes"] + 1
    elif mutation == "replacement":
        hunk["replacement"] += "# altered reviewed bytes\n"
    elif mutation == "original":
        hunk["original"] += "# altered before bytes\n"
    elif mutation == "duplicate_hunk":
        entry["hunks"].insert(1, dict(hunk))
    elif mutation == "reversed_hunks":
        assert len(entry["hunks"]) > 1
        entry["hunks"].reverse()
    else:
        assert mutation == "forged_original"
        restored = (
            namespace["windows_runtime_cache_harness_originals"](tmp_path)[name] + b"\n# forged\n"
        )
        current = (tmp_path / name).read_bytes()
        entry["original_bytes"] = len(restored)
        entry["original_sha256"] = hashlib.sha256(restored).hexdigest()
        entry["hunks"] = [
            {
                "new_start": 0,
                "new_end": len(current),
                "original": restored.decode(),
                "replacement": current.decode(),
            }
        ]
    repin_windows_runtime_cache_harness_fixture_for_inner_control(namespace, tmp_path, revision)
    with pytest.raises(AssertionError):
        namespace["windows_runtime_cache_harness_originals"](tmp_path)


def repin_windows_runtime_cache_revision_fixture(namespace, root, revision):
    """Bypass only the outer seal in a test to exercise inner semantic assertions."""
    raw = (json.dumps(revision, sort_keys=True, indent=2) + "\n").encode()
    (root / namespace["WINDOWS_RUNTIME_CACHE_REVISION_FIXTURE"]).write_bytes(raw)
    namespace["WINDOWS_RUNTIME_CACHE_REVISION_SHA256"] = hashlib.sha256(raw).hexdigest()


@pytest.mark.parametrize(
    "mutation",
    [
        "schema",
        "base",
        "extra_key",
        "missing_added",
        "missing_changed",
        "added_path",
        "changed_path",
        "core_path",
        "original_hash",
        "reviewed_hash",
        "original_length",
        "reviewed_length",
        "entry_key",
        "hunk_key",
        "empty_hunks",
        "start_negative",
        "start_bool",
        "end_before_start",
        "end_overflow",
        "replacement",
        "original",
        "duplicate_hunk",
        "reversed_hunks",
    ],
)
def test_windows_runtime_cache_inverse_rejects_invalid_hunks_metadata_and_nonfinite_paths(
    tmp_path, mutation
):
    namespace = guard_namespace()
    namespace["copy_python_guard_tree"](tmp_path)
    revision = json.loads(
        (tmp_path / namespace["WINDOWS_RUNTIME_CACHE_REVISION_FIXTURE"]).read_bytes()
    )
    name = "blender_addon/mechanical_cad_blender/runtime_bundle_launch.py"
    entry = revision["changed"][name]
    hunk = entry["hunks"][0]
    if mutation == "schema":
        revision["schema"] = "other"
    elif mutation == "base":
        revision["base_commit"] = "0" * 40
    elif mutation == "extra_key":
        revision["allow_other_paths"] = True
    elif mutation == "missing_added":
        revision["added"].pop(next(iter(revision["added"])))
    elif mutation == "missing_changed":
        revision["changed"].pop(name)
    elif mutation == "added_path":
        revision["added"]["../unreviewed.py"] = revision["added"].pop(next(iter(revision["added"])))
    elif mutation == "changed_path":
        revision["changed"]["blender_addon/../unreviewed.py"] = revision["changed"].pop(name)
    elif mutation == "core_path":
        revision["changed"]["src/mechanical_cad/kernel_ocp.py"] = revision["changed"].pop(name)
    elif mutation in {"original_hash", "reviewed_hash"}:
        entry[mutation.replace("_hash", "_sha256")] = "0" * 64
    elif mutation in {"original_length", "reviewed_length"}:
        entry[mutation.replace("_length", "_bytes")] = True
    elif mutation == "entry_key":
        entry["exempt"] = True
    elif mutation == "hunk_key":
        hunk["skip_validation"] = True
    elif mutation == "empty_hunks":
        entry["hunks"] = []
    elif mutation == "start_negative":
        hunk["new_start"] = -1
    elif mutation == "start_bool":
        hunk["new_start"] = False
    elif mutation == "end_before_start":
        hunk["new_end"] = hunk["new_start"] - 1
    elif mutation == "end_overflow":
        hunk["new_end"] = entry["reviewed_bytes"] + 1
    elif mutation == "replacement":
        hunk["replacement"] += "# altered reviewed bytes\n"
    elif mutation == "original":
        hunk["original"] += "# altered before bytes\n"
    elif mutation == "duplicate_hunk":
        entry["hunks"].insert(1, dict(hunk))
    else:
        assert mutation == "reversed_hunks" and len(entry["hunks"]) > 1
        entry["hunks"].reverse()
    repin_windows_runtime_cache_revision_fixture(namespace, tmp_path, revision)
    with pytest.raises(AssertionError):
        namespace["protected_python_digest"](tmp_path)


@pytest.mark.parametrize(
    "path", sorted(guard_namespace()["WINDOWS_RUNTIME_CACHE_REVISION_CHANGED"])
)
def test_forged_windows_runtime_cache_before_bytes_cannot_replace_cache_predecessor(tmp_path, path):
    namespace = guard_namespace()
    namespace["copy_python_guard_tree"](tmp_path)
    _, original = namespace["windows_runtime_cache_originals"](tmp_path)
    revision = json.loads(
        (tmp_path / namespace["WINDOWS_RUNTIME_CACHE_REVISION_FIXTURE"]).read_bytes()
    )
    entry = revision["changed"][path]
    before = original[path] + b"\n# forged Windows before bytes\n"
    reviewed = (tmp_path / path).read_bytes()
    entry["original_bytes"] = len(before)
    entry["original_sha256"] = hashlib.sha256(before).hexdigest()
    entry["hunks"] = [
        {
            "new_start": 0,
            "new_end": len(reviewed),
            "original": before.decode(),
            "replacement": reviewed.decode(),
        }
    ]
    repin_windows_runtime_cache_revision_fixture(namespace, tmp_path, revision)
    with pytest.raises(AssertionError):
        namespace["protected_python_digest"](tmp_path)


@pytest.mark.parametrize(
    "constant",
    [
        "WINDOWS_RUNTIME_CACHE_REVISION_SHA256",
        "WINDOWS_CACHE_REVISION_SHA256",
        "WINDOWS_CACHE_HARNESS_SHA256",
        "WINDOWS_TRANSPORT_REVISION_SHA256",
        "WINDOWS_TRANSPORT_HARNESS_SHA256",
        "STANDALONE_HARNESS_SHA256",
        "STANDALONE_LIVE_SHA256",
    ],
)
def test_windows_runtime_cache_harness_normalizes_no_other_digest_slot(tmp_path, constant):
    namespace = guard_namespace()
    namespace["copy_python_guard_tree"](tmp_path)
    guard = tmp_path / "tests/unit/test_arc_profile_native_end_cap.py"
    raw = guard.read_bytes()
    digest = namespace[constant].encode("ascii")
    assert raw.count(digest) == 1
    guard.write_bytes(raw.replace(digest, b"f" * 64))
    with pytest.raises(AssertionError):
        namespace["windows_runtime_cache_harness_originals"](tmp_path)


def assert_windows_runtime_cache_finite_symbols(root):
    """Only the reviewed methods, exact imports and one policy field may change."""
    namespace = guard_namespace()
    _, originals = namespace["windows_runtime_cache_originals"](historical_runtime_root())
    allowed = {
        "backend_selection.py": {"BackendSelection._capture_windows_bundled_transport"},
        "runtime_bundle_launch.py": {
            "BundledLaunchPolicy.__post_init__",
            "capture_bundled_policy",
        },
        "windows_cache.py": {"WindowsCacheOwner.close", "WindowsCacheOwner._finish"},
        "windows_runtime.py": {
            "_verify_cached_tree",
            "WindowsRuntimeAPI.open_anchor",
            "WindowsRuntimeAPI.stream_handle",
            "WindowsRuntimeAPI.stream_info",
            "_TrackedProcessAPI.initialize_file",
            "WindowsRuntimeValidation.__init__",
            "WindowsRuntimeValidation.acquire",
            "WindowsRuntimeValidation._recheck",
            "WindowsRuntimeValidation.before_write",
            "WindowsRuntimeValidation.before_create",
            "WindowsRuntimeValidation.close",
            "WindowsRuntimeValidation._assert_cache_binding",
            "WindowsOperationOwner.__init__",
            "WindowsOperationOwner._acquire",
            "WindowsOperationOwner.cleanup",
            "WindowsOperationOwner.checkpoint",
        },
    }
    imports = {
        "backend_selection.py": ("from dataclasses import dataclass, field, replace",),
        "runtime_bundle_launch.py": (
            "from dataclasses import asdict, dataclass, field, replace",
            "from .windows_cache import WindowsCacheLocation",
        ),
        "windows_runtime.py": (
            "from dataclasses import dataclass, replace",
            "from .windows_cache import WindowsCacheOwner",
        ),
        "windows_cache.py": (),
    }
    added = {
        "WindowsRuntimeAPI.stream_handle",
        "WindowsRuntimeValidation.before_write",
        "WindowsRuntimeValidation._assert_cache_binding",
    }

    def protected(data, filename, *, current):
        lines = data.splitlines(keepends=True)
        found = set()
        found_imports = []
        found_fields = []

        def members(nodes, parent=""):
            result = []
            for node in nodes:
                name = getattr(node, "name", "")
                name = f"{parent}.{name}" if parent else name
                if (
                    isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and name in allowed[filename]
                ):
                    assert isinstance(node, ast.FunctionDef) and name not in found
                    found.add(name)
                    continue
                if isinstance(node, ast.ClassDef):
                    header = ast.ClassDef(
                        name=node.name,
                        bases=node.bases,
                        keywords=node.keywords,
                        body=[],
                        decorator_list=node.decorator_list,
                    )
                    result.append((ast.dump(header), members(node.body, node.name)))
                    continue
                if current and isinstance(node, ast.ImportFrom) and not parent:
                    statement = ast.unparse(node)
                    if statement in imports[filename]:
                        found_imports.append(statement)
                        if node.module == "dataclasses":
                            aliases = [alias for alias in node.names if alias.name != "replace"]
                            result.append(
                                ast.dump(
                                    ast.ImportFrom(module="dataclasses", names=aliases, level=0)
                                )
                            )
                        continue
                if isinstance(node, ast.ImportFrom) and node.module == "dataclasses" and not parent:
                    result.append(ast.dump(node))
                    continue
                if (
                    current
                    and filename == "runtime_bundle_launch.py"
                    and parent == "BundledLaunchPolicy"
                    and isinstance(node, ast.AnnAssign)
                    and isinstance(node.target, ast.Name)
                    and node.target.id == "windows_cache"
                ):
                    found_fields.append(ast.unparse(node))
                    continue
                start = min(
                    [node.lineno] + [item.lineno for item in getattr(node, "decorator_list", [])]
                )
                result.append(b"".join(lines[start - 1 : node.end_lineno]))
            return result

        result = members(ast.parse(data).body)
        expected = allowed[filename] if current else allowed[filename] - added
        assert found == expected, (filename, found, expected)
        if current:
            assert sorted(found_imports) == sorted(imports[filename]), filename
            assert found_fields == (
                ["windows_cache: WindowsCacheLocation | None = field(default=None, repr=False)"]
                if filename == "runtime_bundle_launch.py"
                else []
            ), filename
        return result

    for filename in allowed:
        relative = "blender_addon/mechanical_cad_blender/" + filename
        assert protected((root / relative).read_bytes(), filename, current=True) == protected(
            originals[relative], filename, current=False
        ), relative

    relative = "blender_addon/mechanical_cad_blender/windows_runtime.py"
    original, current = originals[relative], (root / relative).read_bytes()

    def method(data, owner, name):
        tree = ast.parse(data)
        cls = next(
            node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == owner
        )
        matches = [
            node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == name
        ]
        assert len(matches) == 1
        node = matches[0]
        return b"".join(data.splitlines(keepends=True)[node.lineno - 1 : node.end_lineno])

    old = method(original, "WindowsOperationOwner", "checkpoint")
    expected = []
    for line in old.splitlines(keepends=True):
        if line.lstrip() in {
            b'raise ProcessError("cancelled")\n',
            b'raise ProcessError("timeout")\n',
        }:
            value = b"cancelled" if b"cancelled" in line else b"timeout"
            indent = line[: len(line) - len(line.lstrip())]
            expected.append(indent + b'self.failure_code = "' + value + b'"\n')
        expected.append(line)
    assert method(current, "WindowsOperationOwner", "checkpoint") == b"".join(expected)
    old = method(original, "_TrackedProcessAPI", "initialize_file")
    needle = b"        return super().initialize_file(file, data)\n"
    assert old.count(needle) == 1
    assert method(current, "_TrackedProcessAPI", "initialize_file") == old.replace(
        needle, b"        self._validation.before_write(file)\n" + needle
    )
    old = method(original, "WindowsRuntimeAPI", "open_anchor")
    needle = b"0x80 if directory else 0x80000000"
    assert old.count(needle) == 1
    assert method(current, "WindowsRuntimeAPI", "open_anchor") == old.replace(
        needle, b"0x00020080 if directory else 0x80000000"
    )


def test_windows_runtime_cache_changes_only_exact_approved_symbols_and_imports():
    assert_windows_runtime_cache_finite_symbols(ROOT)
    assert_import_boundary(ROOT)
    assert_windows_cache_dependency_leaf(ROOT)
    assert_windows_cache_query_is_dormant(ROOT)
    assert_windows_cache_qualification_is_dormant(ROOT)
    assert_windows_qualification_constructor_is_dormant(ROOT)


@pytest.mark.parametrize(
    "filename, before, after",
    [
        ("windows_cache.py", b"_MAX_ACES = 16", b"_MAX_ACES = 17"),
        ("windows_cache.py", b"import threading", b"import threading\nimport os"),
        (
            "windows_cache.py",
            b"    def acquire_existing(self, *, cancelled=lambda: False):",
            b"    def acquire_existing(self, *, cancelled=lambda: False): # altered",
        ),
        ("windows_runtime.py", b"CLEANUP_SECONDS = 5.0", b"CLEANUP_SECONDS = 6.0"),
        (
            "windows_runtime.py",
            b'            self.failure_code = "cancelled"\n            raise ProcessError("cancelled")',
            b'            self.failure_code = "timeout"\n            raise ProcessError("cancelled")',
        ),
        (
            "windows_runtime.py",
            b"        self._validation.before_write(file)\n",
            b"        self._validation.before_write(file)\n        file.flush()\n",
        ),
        (
            "windows_runtime.py",
            b"            0x00020080 if directory else 0x80000000,\n",
            b"            0x00020080 if directory else 0x80000000 | 2,\n",
        ),
        (
            "runtime_bundle_launch.py",
            b"MAX_RELEASE_BYTES = 16 * 1024",
            b"MAX_RELEASE_BYTES = 32 * 1024",
        ),
        (
            "backend_selection.py",
            b"def _path(value: str, label: str) -> str:",
            b"def _path(value: str, label: str) -> str: # altered",
        ),
    ],
)
def test_windows_runtime_cache_nonfinite_symbol_and_import_mutations_reject(
    tmp_path, filename, before, after
):
    for source in ADDON.glob("*.py"):
        target = tmp_path / "blender_addon/mechanical_cad_blender" / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    target = tmp_path / "blender_addon/mechanical_cad_blender" / filename
    raw = target.read_bytes()
    assert raw.count(before) == 1
    target.write_bytes(raw.replace(before, after))
    with pytest.raises(AssertionError):
        assert_windows_runtime_cache_finite_symbols(tmp_path)


@pytest.mark.parametrize(
    "filename", ["registration.py", "backend_runtime.py", "backend_selection.py"]
)
@pytest.mark.parametrize(
    "statement",
    [
        "from .windows_runtime import WindowsOperationOwner",
        "from .windows_process import WindowsOwnedProcess",
        "alias = BackendSelection._capture_windows_bundled_transport",
        "getattr(BackendSelection, '_capture_windows_bundled_transport')(policy)",
        "BundlePreparationJob.for_windows_qualification(package, location, release)",
        "query_windows_cache_location()",
    ],
)
def test_windows_runtime_cache_public_process_and_recipe_reachability_mutations_reject(
    tmp_path, filename, statement
):
    for source in ADDON.glob("*.py"):
        target = tmp_path / "blender_addon/mechanical_cad_blender" / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    target = tmp_path / "blender_addon/mechanical_cad_blender" / filename
    target.write_text(target.read_text() + "\n" + statement + "\n")
    with pytest.raises(AssertionError):
        assert_import_boundary(tmp_path)
        assert_windows_cache_query_is_dormant(tmp_path)
        assert_windows_cache_qualification_is_dormant(tmp_path)
        assert_windows_qualification_constructor_is_dormant(tmp_path)


@pytest.mark.parametrize("mutation", ["fixture", "slot", "helper", "coordinated"])
def test_windows_runtime_cache_source_pair_tampering_cannot_replace_trusted_validator(
    tmp_path, mutation
):
    namespace = guard_namespace()
    namespace["copy_python_guard_tree"](tmp_path)
    fixture = tmp_path / namespace["WINDOWS_RUNTIME_CACHE_REVISION_FIXTURE"]
    guard = tmp_path / "tests/unit/test_arc_profile_native_end_cap.py"
    if mutation in {"fixture", "coordinated"}:
        fixture.write_bytes(fixture.read_bytes() + b"\n")
    if mutation in {"slot", "coordinated"}:
        digest = (
            hashlib.sha256(fixture.read_bytes()).hexdigest()
            if mutation == "coordinated"
            else "f" * 64
        )
        old = namespace["WINDOWS_RUNTIME_CACHE_REVISION_SHA256"].encode()
        raw = guard.read_bytes()
        assert raw.count(old) == 1
        guard.write_bytes(raw.replace(old, digest.encode()))
    if mutation == "helper":
        raw = guard.read_bytes()
        before = b"def windows_runtime_cache_originals(root):"
        assert raw.count(before) == 1
        guard.write_bytes(raw.replace(before, before + b" # unreviewed"))
    with pytest.raises(AssertionError):
        namespace["protected_python_digest"](tmp_path)


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate",
        "missing",
        "wrong_object",
        "wrong_method",
        "nested_scope",
        "setter_alias",
        "wrong_callee",
        "wrong_value",
        "wrong_context",
        "dynamic_import",
        "alias",
        "wrong_module",
    ],
)
def test_windows_runtime_cache_exact_field_literal_does_not_exempt_dynamic_module_names(
    tmp_path, mutation
):
    for source in ADDON.glob("*.py"):
        target = tmp_path / "blender_addon/mechanical_cad_blender" / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    target = tmp_path / "blender_addon/mechanical_cad_blender/runtime_bundle_launch.py"
    raw = target.read_bytes()
    statement = b'            object.__setattr__(self, "windows_cache", location)\n'
    assert raw.count(statement) == 1
    if mutation == "duplicate":
        raw = raw.replace(statement, statement + statement)
    elif mutation == "missing":
        raw = raw.replace(statement, b"            pass\n")
    elif mutation == "wrong_object":
        raw = raw.replace(statement, statement.replace(b"(self,", b"(other,"))
    elif mutation == "wrong_method":
        start = raw.index(b"    def __post_init__(self):", raw.index(b"class BundledLaunchPolicy:"))
        raw = raw[:start] + raw[start:].replace(
            b"def __post_init__(self):", b"def other_method(self):", 1
        )
    elif mutation == "nested_scope":
        raw = raw.replace(statement, b"            def nested():\n    " + statement)
    elif mutation == "setter_alias":
        raw = raw.replace(
            statement,
            b"            setter = object.__setattr__\n"
            + statement.replace(b"object.__setattr__", b"setter"),
        )
    elif mutation == "wrong_callee":
        raw = raw.replace(statement, statement.replace(b"object.__setattr__", b"setattr"))
    elif mutation == "wrong_value":
        raw = raw.replace(statement, statement.replace(b", location)", b", self.windows_cache)"))
    elif mutation == "wrong_context":
        raw = raw.replace(statement, b"            pass\n") + b"\n" + statement.lstrip()
    elif mutation == "dynamic_import":
        raw += b"\n__import__('windows_cache')\n"
    elif mutation == "alias":
        raw += b"\nmodule_name = 'windows_cache'\n"
    else:
        assert mutation == "wrong_module"
        other = tmp_path / "blender_addon/mechanical_cad_blender/backend_selection.py"
        other.write_bytes(other.read_bytes() + b"\n" + statement.lstrip())
    target.write_bytes(raw)
    with pytest.raises(AssertionError):
        assert_import_boundary(tmp_path)


@pytest.mark.parametrize("layer", ["runtime_cache", "cache", "transport", "standalone"])
def test_old_harness_inner_controls_reach_positive_equivalent_repin(tmp_path, layer):
    """A changed outer digest must still reach a valid historical inner inverse."""
    namespace = guard_namespace()
    namespace["copy_python_guard_tree"](tmp_path)
    if layer == "runtime_cache":
        prefix = "WINDOWS_RUNTIME_CACHE"
        function = namespace["windows_runtime_cache_harness_originals"]
        current = namespace["standalone_integration_harness_originals"](tmp_path)
        repin = repin_windows_runtime_cache_harness_fixture_for_inner_control
    elif layer == "cache":
        prefix = "WINDOWS_CACHE"
        function = namespace["windows_cache_harness_originals"]
        current = namespace["standalone_integration_harness_originals"](tmp_path) | namespace[
            "windows_runtime_cache_harness_originals"
        ](tmp_path)
        repin = repin_windows_cache_harness_fixture_for_inner_control
    elif layer == "transport":
        prefix = "WINDOWS_TRANSPORT"
        function = namespace["windows_transport_harness_originals"]
        current = namespace["windows_cache_harness_originals"](tmp_path)
        repin = repin_windows_harness_fixture_for_inner_control
    else:
        prefix = "STANDALONE"
        function = namespace["standalone_harness_originals"]
        current = namespace["windows_transport_harness_originals"](tmp_path)
        repin = repin_harness_fixture_for_inner_control
    expected = function(tmp_path)
    fixture = tmp_path / namespace[prefix + "_HARNESS_FIXTURE"]
    original_raw = fixture.read_bytes()
    revision = json.loads(original_raw)
    name = "tests/unit/test_arc_profile_incidence.py"
    revision["changed"][name]["hunks"] = [
        {
            "new_start": 0,
            "new_end": len(current[name]),
            "original": expected[name].decode(),
            "replacement": current[name].decode(),
        }
    ]
    repin(namespace, tmp_path, revision)
    assert fixture.read_bytes() != original_raw
    assert function(tmp_path) == expected
