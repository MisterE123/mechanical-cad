"""Sealed service history and independently reviewed current runtime boundaries.

Historical byte preservation never qualifies current code. Current paths, imports,
legacy sketch-output extension and UI registration have separate positive and
negative controls. See fixtures/result_v3/CURRENT_BOUNDARY_REVIEW.md.
"""

from __future__ import annotations

import ast
import hashlib
import json
import shutil
import tempfile
from functools import lru_cache
from pathlib import Path

import pytest
from historical_runtime_source import historical_runtime_root
from test_arc_profile_native_end_cap import (
    ASSEMBLY_STEP_ADDED,
    AUTHORING_REVISION_FIXTURE,
    AUTHORING_REVISION_SHA256,
    GATE_C_OWNER_SOURCE_ADDED,
    GATE_C_OWNER_SOURCE_ORIGINALS,
    VISUAL_JOINT_ADDED,
    authoring_revision_originals,
    gate_c_owner_source_originals,
    geometry_revision_originals,
    standalone_live_originals,
    standalone_revision_added,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/fixtures/result_v3/protected_30383a1.json"
FIXTURE_SHA256 = "6049e08dad6a797294a9738fb81c143359d07c2a0c33db0608429dca29548b28"
DISPATCH_FIXTURE = ROOT / "tests/fixtures/result_v3/dispatch_extension_30383a1.json"
DISPATCH_SHA256 = "4eed9a50153d2c4b3d0ea8fda5e48cd378e050287ca374241b56ee0481b497c8"
AUTHORING_RUNTIME_NEW = frozenset(
    {
        "blender_addon/mechanical_cad_blender/operation_contracts.py",
        "blender_addon/mechanical_cad_blender/general_arc_authoring_store.py",
    }
)
GEOMETRY_RUNTIME_NEW = frozenset(
    {
        "src/mechanical_cad/geometry_policy_v3.py",
        "src/mechanical_cad/geometry_protocol_v3.py",
        "blender_addon/mechanical_cad_blender/geometry_result_v3.py",
    }
)

STANDALONE_RUNTIME_NEW = frozenset(
    "blender_addon/mechanical_cad_blender/" + name + ".py"
    for name in (
        "backend_platform",
        "windows_process",
        "windows_runtime",
        "windows_cache",
        "runtime_bundle_manifest",
        "runtime_bundle_materialize",
        "runtime_bundle_pin",
        "runtime_bundle_prepare",
        "runtime_bundle_launch",
    )
)
# Exact reviewed Gate-B/C dependency edges. Historical source still reconstructs
# byte-for-byte below; no broad importer or new-runtime wildcard is introduced.
AUTHORING_IMPORTERS = {
    "assembly_display": {"operation_contracts"},
    "assembly_operator_helpers": {"operation_contracts"},
    "assembly_operators": {"operation_contracts"},
    "assembly_state": {"operation_contracts"},
    "assembly_validation_model": {"result_v3"},
    "constraint_diagnostics": {"operation_contracts"},
    "constraint_selection": {"sketch_contracts_v3"},
    "display": {"operation_contracts", "sketch_contracts_v3"},
    "document_state": {"operation_contracts"},
    "draft_dispatch": {"general_arc_authoring_store"},
    "general_session": {"operation_contracts"},
    "general_sketch_commands": {"operation_contracts"},
    "general_sketch_draft": {"operation_contracts"},
    "general_sketch_overlay": {"arc_geometry"},
    "general_view_geometry": {"arc_geometry", "operation_contracts", "sketch_contracts_v3"},
    "guarded_evidence": {"operation_contracts"},
    "guarded_operations": {"operation_contracts"},
    "operators": {"operation_contracts"},
    "part_snapshot_bridge": {"part_contracts_v3"},
    "sketch_annotation_store": {"sketch_contracts_v3"},
    "sketch_display": {"sketch_contracts_v3"},
    "sketch_pending": {"operation_contracts"},
    "viewport_sketch": {"operation_contracts"},
}
DISPATCH_PATHS = frozenset(
    "src/mechanical_cad/" + name + ".py" for name in ("engine", "sidecar", "backend_contract")
)
ALLOWED_NEW = frozenset(
    {
        "src/mechanical_cad/profile_adapter_v3.py",
        "src/mechanical_cad/result_policy_v3.py",
        "src/mechanical_cad/sketch_service_v3.py",
        "src/mechanical_cad/sketch_protocol_v3.py",
        "blender_addon/mechanical_cad_blender/arc_geometry.py",
        "blender_addon/mechanical_cad_blender/arc_profile_primitives.py",
        "blender_addon/mechanical_cad_blender/arc_profile_intervals.py",
        "blender_addon/mechanical_cad_blender/arc_profile_sector_source.py",
        "blender_addon/mechanical_cad_blender/arc_profile_sector_policy.py",
        "blender_addon/mechanical_cad_blender/part_contracts_v3.py",
        "blender_addon/mechanical_cad_blender/sketch_contracts_v3.py",
        "blender_addon/mechanical_cad_blender/sector_topology_v3.py",
        "blender_addon/mechanical_cad_blender/result_v3.py",
        "blender_addon/mechanical_cad_blender/service_v3.py",
    }
)


CURRENT_POLICY = ROOT / "tests/fixtures/result_v3/current_boundary_policy.json"
CURRENT_POLICY_SHA256 = "8789f50d60f4a181859a7f05065d4a2117e1eee569fb97106fbd60feb2823516"
_RESULT_HISTORY = None


def _current_policy():
    raw = CURRENT_POLICY.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == CURRENT_POLICY_SHA256
    value = json.loads(raw)
    assert value["schema"] == 1
    assert value["reviewed_source"] == "a15bdbf107116b8ebd6f5f2a547144b6eef3a225"
    assert len(value["path_origins"]) == 249
    assert len(value["authoring_importers"]) == 40
    assert len(value["general_classes"]) == 13
    return value


def result_history_root():
    """Complete old baseline assets without copying any mutable current code."""
    global _RESULT_HISTORY
    if _RESULT_HISTORY is None:
        temporary = tempfile.TemporaryDirectory(prefix="mcad-result-history-")
        root = Path(temporary.name)
        try:
            shutil.copytree(historical_runtime_root(), root, dirs_exist_ok=True)
            copied = 0
            for relative, expected in _baseline()["files"].items():
                if (root / relative).exists():
                    continue
                # The 527 referenced assets are unchanged original-baseline data.
                # Never use this fallback for executable current Python source.
                assert not relative.endswith(".py")
                raw = (ROOT / relative).read_bytes()
                assert len(raw) == expected["bytes"]
                assert hashlib.sha256(raw).hexdigest() == expected["sha256"]
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(raw)
                copied += 1
            assert copied == 527
        except BaseException:
            temporary.cleanup()
            raise
        _RESULT_HISTORY = temporary
    return Path(_RESULT_HISTORY.name)


def _runtime_paths(root):
    return {
        path.relative_to(root).as_posix()
        for prefix in ("src", "blender_addon")
        for path in (root / prefix).rglob("*")
        if path.is_file()
        and not (path.suffix == ".pyc" and path.parent.name == "__pycache__")
    }


def _assert_current_paths(root):
    expected = set(_baseline()["files"]) | set(_current_policy()["path_origins"])
    assert _runtime_paths(root) == expected


def _current_addon_sources(root):
    return {
        path.stem: path.read_bytes()
        for path in (root / "blender_addon/mechanical_cad_blender").glob("*.py")
    }


@lru_cache(maxsize=1024)
def _import_evidence(raw):
    """Cache immutable AST facts by exact bytes; every mutation gets a new key."""
    tree = ast.parse(raw)
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    references, loaders = set(), []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            references.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            references.update([node.module or "", *(alias.name for alias in node.names)])
            assert not (node.module == "importlib" and any(
                alias.name == "import_module" for alias in node.names
            ))
        assert not (isinstance(node, ast.Name) and node.id == "__import__")
        if isinstance(node, ast.Attribute) and node.attr == "import_module":
            parent = parents[node]
            assert isinstance(parent, ast.Call) and parent.func is node
            scope = parent
            while scope in parents and not isinstance(scope, ast.FunctionDef):
                scope = parents[scope]
            assert isinstance(scope, ast.FunctionDef)
            loaders.append((scope.name, ast.unparse(parent)))
    return tuple(sorted(references)), tuple(loaders)


def _assert_current_imports(sources):
    names = {
        Path(path).stem for path in ALLOWED_NEW | AUTHORING_RUNTIME_NEW
        if path.startswith("blender_addon/")
    }
    observed, loaders = {}, []
    for module, raw in sources.items():
        references, dynamic = _import_evidence(raw)
        imports = {name for name in names if any(name in ref.split(".") for ref in references)}
        for scope, call in dynamic:
            assert module == "registration" and scope == "_start_bundle_setup"
            assert call == "importlib.import_module(__package__ + '.standalone_launch_constants')"
            loaders.append(module)
        if imports:
            observed[module] = sorted(imports)
    assert loaders == ["registration"]
    assert observed == _current_policy()["authoring_importers"]


def _assert_current_registry(raw):
    tree = ast.parse(raw)
    values = [node.value for node in tree.body if isinstance(node, ast.Assign)
              and any(isinstance(target, ast.Name) and target.id == "CLASSES"
                      for target in node.targets)]
    assert len(values) == 1 and isinstance(values[0], ast.Tuple)
    assert all(isinstance(node, ast.Name) for node in values[0].elts)
    names = [node.id for node in values[0].elts]
    assert names == _current_policy()["general_classes"]
    assert len(names) == len(set(names))
    defined = {node.name for node in tree.body if isinstance(node, ast.ClassDef)}
    assert set(names) <= defined


def _assert_current_sketch_output(raw):
    """Only the 36daecd ProfileRegions extension may change the old function."""
    tree = ast.parse(raw)
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef)
             and node.name == "_sketch_output"]
    assert len(nodes) == 1 and not nodes[0].decorator_list
    node = nodes[0]
    span = b"".join(raw.splitlines(keepends=True)[node.lineno - 1:node.end_lineno])
    expanded_import = b"""        from .profile_region import (
            CircleProfile,
            OpenChainProfile,
            ProfileRegions,
            classify_profile,
        )"""
    expanded_branch = b"""        if isinstance(region, ProfileRegions):
            shape = kernel.region_profile(
                region.regions,
                origin=report.sketch.plane.origin,
                quaternion=report.sketch.plane.quaternion,
            )
            return SketchOutput(
                report.sketch, AvailableProfile(shape, "regions", region.boundary_ids)
            )
"""
    assert span.count(expanded_import) == span.count(expanded_branch) == 1
    restored = span.replace(expanded_import, b"        from .profile_region import CircleProfile, OpenChainProfile, classify_profile")
    restored = restored.replace(expanded_branch, b"")
    expected = _baseline()["preserved_function_spans"]["src/mechanical_cad/engine.py:_sketch_output"]
    assert len(restored) == expected["bytes"]
    assert hashlib.sha256(restored).hexdigest() == expected["sha256"]


def _baseline():
    raw = FIXTURE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == FIXTURE_SHA256
    value = json.loads(raw)
    assert value["commit"] == "30383a1bbaeae02b447bab2c37290d5f3927df8c"
    assert value["file_count"] == len(value["files"]) == 640
    assert sum(name.startswith("src/") for name in value["files"]) == 35
    assert sum(name.startswith("blender_addon/") for name in value["files"]) == 605
    return value


def _assert_preserved(root, files, *, originals=None):
    originals = {} if originals is None else originals
    for relative, expected in files.items():
        raw = originals.get(relative, (root / relative).read_bytes())
        assert len(raw) == expected["bytes"], relative
        assert hashlib.sha256(raw).hexdigest() == expected["sha256"], relative


def _dispatch_entries():
    raw = DISPATCH_FIXTURE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == DISPATCH_SHA256
    value = json.loads(raw)
    assert value["base_commit"] == _baseline()["commit"]
    assert set(value["files"]) == DISPATCH_PATHS
    return value["files"]


def _restore_dispatch_original(raw, entry):
    """Only the complete reviewed byte delta may replace a protected module."""
    assert len(raw) == entry["reviewed_bytes"]
    assert hashlib.sha256(raw).hexdigest() == entry["reviewed_sha256"]
    previous = 0
    for hunk in entry["hunks"]:
        start, end = hunk["new_start"], hunk["new_end"]
        assert type(start) is type(end) is int
        assert previous <= start <= end <= len(raw)
        assert raw[start:end] == hunk["replacement"].encode("utf-8")
        previous = end
    restored = raw
    for hunk in reversed(entry["hunks"]):
        restored = (
            restored[: hunk["new_start"]]
            + hunk["original"].encode("utf-8")
            + restored[hunk["new_end"] :]
        )
    assert len(restored) == entry["original_bytes"]
    assert hashlib.sha256(restored).hexdigest() == entry["original_sha256"]
    return restored


def _reviewed_history(root):
    """Keep standalone restoration distinct from the historical arc revision."""
    live_added, live_originals = standalone_live_originals(root)
    isolated_added = standalone_revision_added(root)
    standalone_runtime = frozenset(
        name for name in live_added | isolated_added if name.startswith(("src/", "blender_addon/"))
    )
    assert standalone_runtime == STANDALONE_RUNTIME_NEW
    geometry_added, geometry_originals = geometry_revision_originals(root)
    assert {
        name for name in geometry_added if name.startswith(("src/", "blender_addon/"))
    } == GEOMETRY_RUNTIME_NEW
    added, originals = authoring_revision_originals(root)
    live_originals = geometry_originals | live_originals
    raw = (root / AUTHORING_REVISION_FIXTURE).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == AUTHORING_REVISION_SHA256
    arc_changed = frozenset(json.loads(raw)["changed"])
    return added - live_added - geometry_added, originals, live_originals, arc_changed


def _assert_new_paths(
    root,
    original,
    *,
    standalone_new=frozenset(),
    geometry_new=frozenset(),
    assembly_step_new=frozenset(),
    visual_joint_new=frozenset(),
):
    observed = set()
    for prefix in ("src", "blender_addon"):
        for path in (root / prefix).rglob("*"):
            if not path.is_file():
                continue
            # Isolated Python test children can generate bytecode. These are
            # separately bounded/preserved by the qualification controller and
            # are never added to the source/package manifest.
            if path.suffix == ".pyc" and path.parent.name == "__pycache__":
                continue
            observed.add(path.relative_to(root).as_posix())
    assert standalone_new in (frozenset(), STANDALONE_RUNTIME_NEW)
    assert standalone_new <= observed, "missing sealed standalone runtime path"
    assert geometry_new in (frozenset(), GEOMETRY_RUNTIME_NEW)
    assert geometry_new <= observed, "missing sealed geometry runtime path"
    expected_export = frozenset(
        name for name in ASSEMBLY_STEP_ADDED if name.startswith(("src/", "blender_addon/"))
    )
    assert assembly_step_new in (frozenset(), expected_export)
    assert assembly_step_new <= observed, "missing sealed Assembly export runtime path"
    expected_visual = frozenset(
        name for name in VISUAL_JOINT_ADDED if name.startswith(("src/", "blender_addon/"))
    )
    assert expected_visual == {
        "blender_addon/mechanical_cad_blender/assembly_joint_draft.py",
        "blender_addon/mechanical_cad_blender/assembly_joint_overlay.py",
        "blender_addon/mechanical_cad_blender/assembly_joint_viewport.py",
    }
    assert visual_joint_new in (frozenset(), expected_visual)
    assert visual_joint_new <= observed, "missing sealed visual Assembly joint runtime path"
    historical_observed = (
        observed - standalone_new - geometry_new - assembly_step_new - visual_joint_new
    )
    assert historical_observed - set(original) <= ALLOWED_NEW | AUTHORING_RUNTIME_NEW, sorted(
        historical_observed - set(original)
    )


def test_historical_preexisting_bytes_remain_exact_except_reviewed_dispatch():
    root = result_history_root()
    original = _baseline()["files"]
    protected = {name: entry for name, entry in original.items() if name not in DISPATCH_PATHS}
    assert len(protected) == 637
    added, originals, _, _ = _reviewed_history(root)
    assert {name for name in added if name.startswith("blender_addon/")} == AUTHORING_RUNTIME_NEW
    _assert_preserved(root, protected, originals=originals)
    for relative, entry in _dispatch_entries().items():
        assert entry["original_sha256"] == original[relative]["sha256"]
        assert entry["original_bytes"] == original[relative]["bytes"]
        _restore_dispatch_original(originals.get(relative, (root / relative).read_bytes()), entry)


@pytest.mark.parametrize("relative", sorted(DISPATCH_PATHS))
def test_unreviewed_byte_change_cannot_hide_in_dispatch_extension(relative):
    root = result_history_root()
    entry = _dispatch_entries()[relative]
    _, originals = geometry_revision_originals(root)
    raw = originals.get(relative, (root / relative).read_bytes())
    _restore_dispatch_original(raw, entry)
    for changed in (raw + b"\n# unreviewed mutation\n", raw.replace(b"3", b"4", 1)):
        assert changed != raw
        with pytest.raises(AssertionError):
            _restore_dispatch_original(changed, entry)


def test_new_runtime_paths_are_exactly_scoped():
    _assert_current_paths(ROOT)


@pytest.mark.parametrize("mutation", ["missing", "extra", "wrong_directory", "partial_set"])
def test_standalone_paths_cannot_expand_or_shrink_historical_boundary(tmp_path, mutation):
    for relative in STANDALONE_RUNTIME_NEW:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"# path-only control; source hashes are checked separately\n")
    _assert_new_paths(tmp_path, {}, standalone_new=STANDALONE_RUNTIME_NEW)
    relative = sorted(STANDALONE_RUNTIME_NEW)[0]
    if mutation == "missing":
        (tmp_path / relative).unlink()
    elif mutation == "extra":
        (tmp_path / "blender_addon/mechanical_cad_blender/unreviewed.py").write_bytes(b"pass\n")
    elif mutation == "wrong_directory":
        target = tmp_path / "blender_addon/impostor" / Path(relative).name
        target.parent.mkdir(parents=True)
        (tmp_path / relative).rename(target)
    else:
        with pytest.raises(AssertionError):
            _assert_new_paths(tmp_path, {}, standalone_new=STANDALONE_RUNTIME_NEW - {relative})
        return
    with pytest.raises(AssertionError):
        _assert_new_paths(tmp_path, {}, standalone_new=STANDALONE_RUNTIME_NEW)


def test_historical_sketch_output_complete_function_bytes_remain_exact():
    root = result_history_root()
    baseline = _baseline()
    for key, expected in baseline["preserved_function_spans"].items():
        relative, name = key.split(":")
        raw = (root / relative).read_bytes()
        tree = ast.parse(raw)
        matches = [
            node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name
        ]
        assert len(matches) == 1
        node = matches[0]
        assert not node.decorator_list
        span = b"".join(raw.splitlines(keepends=True)[node.lineno - 1 : node.end_lineno])
        assert len(span) == expected["bytes"]
        assert hashlib.sha256(span).hexdigest() == expected["sha256"]


def test_historical_importer_boundary_and_exact_gate_b_c_edges():
    root = result_history_root()
    new_names = {
        Path(name).stem
        for name in ALLOWED_NEW | AUTHORING_RUNTIME_NEW
        if name.startswith("blender_addon/")
    }
    _, originals, live_originals, _ = _reviewed_history(root)
    original = _baseline()["files"]
    observed = {}
    for relative in original:
        if not relative.startswith("blender_addon/") or not relative.endswith(".py"):
            continue
        raw = (root / relative).read_bytes()
        # Preserve the complete historical no-import assertion on exact restored
        # source; current additions are separately finite and source-hash bound.
        tree = ast.parse(originals.get(relative, raw))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                imports = [node.module or "", *(alias.name for alias in node.names)]
            else:
                continue
            assert not any(
                name in imported.split(".") for name in new_names for imported in imports
            )
        current_imports = set()
        for node in ast.walk(ast.parse(live_originals.get(relative, raw))):
            if isinstance(node, ast.Import):
                imports = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                imports = [node.module or "", *(alias.name for alias in node.names)]
            else:
                continue
            current_imports.update(
                name for name in new_names if any(name in item.split(".") for item in imports)
            )
        if current_imports:
            observed[Path(relative).stem] = current_imports
    assert observed == AUTHORING_IMPORTERS


def test_historical_ui_freeze_and_exact_gate_c_entry_points():
    root = result_history_root()
    _, restored, live_originals, arc_changed = _reviewed_history(root)
    originals = {name: restored[name] for name in arc_changed}
    # Qualified Gate B a05fc17 kept these five UI modules byte-identical to the
    # historical baseline. Preserve that complete assertion on exact restored
    # bytes, then bound Gate C's live entry points independently below.
    modules = (
        "general_viewport",
        "general_sketch_overlay",
        "workspace_ui",
        "panels",
        "sketch_overlay",
    )
    baseline = _baseline()["files"]
    for module in modules:
        relative = f"blender_addon/mechanical_cad_blender/{module}.py"
        _assert_preserved(root, {relative: baseline[relative]}, originals=restored)
    # Rectangle drawing and the sole lifecycle registry acquire no new arc path.
    for module in ("sketch_overlay", "registration"):
        relative = f"blender_addon/mechanical_cad_blender/{module}.py"
        assert relative not in originals
        _assert_preserved(root, {relative: baseline[relative]}, originals=live_originals)
    tree = ast.parse(
        (root / "blender_addon/mechanical_cad_blender/general_viewport.py").read_bytes()
    )
    registries = [
        node.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "CLASSES" for target in node.targets)
    ]
    assert len(registries) == 1 and isinstance(registries[0], ast.Tuple)
    assert [node.id for node in registries[0].elts] == [
        "MCAD_OT_general_sketch",
        "MCAD_OT_edit_general_sketch",
        "MCAD_OT_general_tool",
        "MCAD_OT_enable_arc_editing",
        "MCAD_OT_use_existing_point",
        "MCAD_OT_reverse_arc_sweep",
    ]


@pytest.mark.parametrize(
    "relative",
    (
        "src/mechanical_cad/engine.py",
        "src/mechanical_cad/sketch_solver.py",
        "src/mechanical_cad/arc_profile_native_plan.py",
        "src/mechanical_cad/kernel_ocp.py",
        "blender_addon/mechanical_cad_blender/guarded_evidence.py",
        "blender_addon/mechanical_cad_blender/document_state.py",
    ),
)
def test_unrelated_or_protected_byte_mutation_cannot_hide_in_new_leaf_extension(tmp_path, relative):
    root = result_history_root()
    expected = _baseline()["files"][relative]
    _, originals, _, _ = _reviewed_history(root)
    raw = originals.get(relative, (root / relative).read_bytes())
    if relative in DISPATCH_PATHS:
        raw = _restore_dispatch_original(raw, _dispatch_entries()[relative])
    path = tmp_path / relative
    path.parent.mkdir(parents=True)
    path.write_bytes(raw)
    _assert_preserved(tmp_path, {relative: expected})  # clean positive first
    path.write_bytes(raw + b"\n# unreviewed mutation\n")
    with pytest.raises(AssertionError):
        _assert_preserved(tmp_path, {relative: expected})


@pytest.mark.parametrize(
    "relative",
    (
        "src/impostor/profile_adapter_v3.py",
        "blender_addon/impostor/result_v3.py",
        "blender_addon/mechanical_cad_blender/hidden_v3.py",
        "blender_addon/mechanical_cad_blender/foreign_payload.bin",
    ),
)
def test_basename_or_non_source_payload_cannot_expand_runtime_allowlist(tmp_path, relative):
    path = tmp_path / relative
    path.parent.mkdir(parents=True)
    path.write_bytes(b"unreviewed")
    with pytest.raises(AssertionError):
        _assert_new_paths(tmp_path, {})


@pytest.mark.parametrize("mutation", ["missing", "extra", "wrong_directory", "partial_set"])
def test_geometry_paths_cannot_expand_or_shrink_historical_boundary(tmp_path, mutation):
    for relative in GEOMETRY_RUNTIME_NEW:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"# path-only control; source hashes are separately sealed\n")
    _assert_new_paths(tmp_path, {}, geometry_new=GEOMETRY_RUNTIME_NEW)
    relative = sorted(GEOMETRY_RUNTIME_NEW)[0]
    if mutation == "missing":
        (tmp_path / relative).unlink()
    elif mutation == "extra":
        (tmp_path / "src/mechanical_cad/unreviewed.py").write_bytes(b"pass\n")
    elif mutation == "wrong_directory":
        target = tmp_path / "blender_addon/impostor" / Path(relative).name
        target.parent.mkdir(parents=True)
        (tmp_path / relative).rename(target)
    else:
        with pytest.raises(AssertionError):
            _assert_new_paths(tmp_path, {}, geometry_new=GEOMETRY_RUNTIME_NEW - {relative})
        return
    with pytest.raises(AssertionError):
        _assert_new_paths(tmp_path, {}, geometry_new=GEOMETRY_RUNTIME_NEW)


def test_gate_c_owner_before_view_adds_no_runtime_or_historical_importer_exemption():
    root = result_history_root()
    added, originals = gate_c_owner_source_originals(root)
    assert added == GATE_C_OWNER_SOURCE_ADDED
    assert len(added) == 3 and all(name.startswith("tests/") for name in added)
    assert not added & originals.keys()
    assert set(originals) == set(GATE_C_OWNER_SOURCE_ORIGINALS)
    assert {name for name in originals if name.startswith(("src/", "blender_addon/"))} == {
        "src/mechanical_cad/actions.py",
        "src/mechanical_cad/geometry_protocol_v3.py",
        "src/mechanical_cad/backend_contract.py",
        "blender_addon/mechanical_cad_blender/operation_contracts.py",
        "blender_addon/mechanical_cad_blender/geometry_operations.py",
        "blender_addon/mechanical_cad_blender/workspace_ui.py",
        "blender_addon/mechanical_cad_blender/help_topics.py",
    }
    test_historical_importer_boundary_and_exact_gate_b_c_edges()
    test_new_runtime_paths_are_exactly_scoped()


@pytest.mark.parametrize("mutation", ["missing", "extra", "wrong_directory", "partial_set"])
def test_visual_joint_paths_cannot_expand_or_shrink_historical_boundary(tmp_path, mutation):
    added = frozenset(name for name in VISUAL_JOINT_ADDED if name.startswith("blender_addon/"))
    for relative in added:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"# path-only control; the outer inverse separately checks hashes\n")
    _assert_new_paths(tmp_path, {}, visual_joint_new=added)
    relative = sorted(added)[0]
    if mutation == "missing":
        (tmp_path / relative).unlink()
    elif mutation == "extra":
        (tmp_path / "blender_addon/mechanical_cad_blender/unreviewed.py").write_bytes(b"pass\n")
    elif mutation == "wrong_directory":
        target = tmp_path / "blender_addon/impostor" / Path(relative).name
        target.parent.mkdir(parents=True)
        (tmp_path / relative).rename(target)
    else:
        with pytest.raises(AssertionError):
            _assert_new_paths(tmp_path, {}, visual_joint_new=added - {relative})
        return
    with pytest.raises(AssertionError):
        _assert_new_paths(tmp_path, {}, visual_joint_new=added)


def test_current_importers_and_ui_registry_use_live_source():
    _assert_current_imports(_current_addon_sources(ROOT))
    _assert_current_registry((ROOT / "blender_addon/mechanical_cad_blender/general_viewport.py").read_bytes())
    assert ROOT != result_history_root()


def test_current_legacy_sketch_output_has_only_reviewed_regions_extension():
    _assert_current_sketch_output((ROOT / "src/mechanical_cad/engine.py").read_bytes())


@pytest.mark.parametrize("mutation", ["missing", "extra", "impostor", "binary_payload"])
def test_current_path_inventory_rejects_unreviewed_changes(tmp_path, mutation):
    expected = set(_baseline()["files"]) | set(_current_policy()["path_origins"])
    for relative in expected:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"")
    _assert_current_paths(tmp_path)
    relative = "blender_addon/mechanical_cad_blender/general_sketch_validation.py"
    if mutation == "missing":
        (tmp_path / relative).unlink()
    elif mutation == "impostor":
        target = tmp_path / "blender_addon/impostor/general_sketch_validation.py"
        target.parent.mkdir(parents=True)
        (tmp_path / relative).rename(target)
    else:
        name = "unreviewed.py" if mutation == "extra" else "foreign_payload.bin"
        (tmp_path / "blender_addon/mechanical_cad_blender" / name).write_bytes(b"unreviewed")
    with pytest.raises(AssertionError):
        _assert_current_paths(tmp_path)


@pytest.mark.parametrize(
    "mutation",
    ["missing", "new_importer", "extra_edge", "alias", "dynamic", "dynamic_alias", "assigned_loader", "builtin", "registration_target", "registration_duplicate"],
)
def test_current_import_boundary_rejects_unreviewed_edges_and_loader_aliases(mutation):
    sources = _current_addon_sources(ROOT)
    _assert_current_imports(sources)
    additions = {
        "new_importer": "from . import operation_contracts",
        "extra_edge": "from . import result_v3",
        "alias": "from . import operation_contracts as hidden",
        "dynamic": "import importlib\nimportlib.import_module('.operation_contracts', __package__)",
        "dynamic_alias": "from importlib import import_module as load\nload('.operation_contracts', __package__)",
        "assigned_loader": "import importlib\nload = importlib.import_module\nload('.operation_contracts', __package__)",
        "builtin": "__import__('mechanical_cad_blender.operation_contracts')",
    }
    if mutation == "missing":
        sources.pop("operators")
    elif mutation in {"registration_target", "registration_duplicate"}:
        raw = sources["registration"]
        target = b'generated = importlib.import_module(__package__ + ".standalone_launch_constants")'
        assert raw.count(target) == 1
        replacement = (
            target.replace(b".standalone_launch_constants", b".operation_contracts")
            if mutation == "registration_target"
            else target + b"\n        " + target
        )
        sources["registration"] = raw.replace(target, replacement)
    else:
        module = "operators" if mutation == "extra_edge" else "rectangle_tool"
        sources[module] += ("\n" + additions[mutation] + "\n").encode()
    with pytest.raises(AssertionError):
        _assert_current_imports(sources)


@pytest.mark.parametrize("mutation", ["missing", "extra", "duplicate", "computed", "undefined"])
def test_current_ui_registry_rejects_unreviewed_registration(mutation):
    raw = (ROOT / "blender_addon/mechanical_cad_blender/general_viewport.py").read_bytes()
    _assert_current_registry(raw)
    tree = ast.parse(raw)
    assignment = next(node for node in tree.body if isinstance(node, ast.Assign)
                      and any(isinstance(t, ast.Name) and t.id == "CLASSES" for t in node.targets))
    if mutation == "missing":
        assignment.value.elts.pop()
    elif mutation in ("extra", "duplicate"):
        name = "UnreviewedOperator" if mutation == "extra" else assignment.value.elts[0].id
        assignment.value.elts.append(ast.Name(id=name, ctx=ast.Load()))
    elif mutation == "undefined":
        name = assignment.value.elts[0].id
        tree.body = [n for n in tree.body if not (isinstance(n, ast.ClassDef) and n.name == name)]
    else:
        assignment.value = ast.Call(func=ast.Name(id="tuple", ctx=ast.Load()), args=[assignment.value], keywords=[])
    with pytest.raises(AssertionError):
        _assert_current_registry(ast.unparse(ast.fix_missing_locations(tree)))


@pytest.mark.parametrize("mutation", ["missing_branch", "wrong_geometry", "wrong_ids", "unrelated", "wrong_import"])
def test_current_sketch_output_rejects_any_unreviewed_delta(mutation):
    raw = (ROOT / "src/mechanical_cad/engine.py").read_bytes()
    _assert_current_sketch_output(raw)
    before, after = {
        "missing_branch": (b"if isinstance(region, ProfileRegions):", b"if False:"),
        "wrong_geometry": (b"shape = kernel.region_profile(", b"shape = kernel.rectangle("),
        "wrong_ids": (b'AvailableProfile(shape, "regions", region.boundary_ids)', b'AvailableProfile(shape, "regions", ())'),
        "unrelated": (b"feature.id}: {report.status.name.lower()}", b"feature.id}: success"),
        "wrong_import": (b"            ProfileRegions,", b"            ProfileRegions as OtherRegions,"),
    }[mutation]
    assert raw.count(before) == 1
    with pytest.raises(AssertionError):
        _assert_current_sketch_output(raw.replace(before, after))


@pytest.mark.parametrize("field", ["path_origins", "authoring_importers", "general_classes", "reviewed_source"])
def test_current_review_policy_cannot_be_silently_recomputed(tmp_path, monkeypatch, field):
    value = _current_policy()
    if field == "reviewed_source":
        value[field] = "0" * 40
    elif field == "general_classes":
        value[field].append("UnreviewedOperator")
    else:
        value[field]["unreviewed"] = "unreviewed"
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(value))
    monkeypatch.setitem(globals(), "CURRENT_POLICY", path)
    with pytest.raises(AssertionError):
        _current_policy()
