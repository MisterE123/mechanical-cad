"""Pure AST/filesystem controls for the reviewed additive native dependency gate.

Neither the historical kernel fixture nor a production/test module is imported.
Extracted guards execute only source parsing, hashing, and filesystem checks.
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pytest
from historical_runtime_source import historical_runtime_root as historical_source_root

ROOT = Path(__file__).resolve().parents[2]
GUARDS = (
    (
        "test_arc_profile_primitives.py",
        "test_original_arc_policy_bytes_unchanged_and_no_runtime_importers",
    ),
    (
        "test_arc_profile_arc_membership.py",
        "test_no_production_consumer_or_duplicate_arithmetic_implementation",
    ),
)
INCIDENCE_GUARD = "test_104_runtime_files_and_primitives_unchanged_with_reviewed_additive_kernel"
FIXTURE = ROOT / "tests/fixtures/arc_sector/kernel_ocp-a05626e.py.txt"
FIXTURE_SHA256 = "bd06d4b5372758bfd02cf89eebcb1a1385e8222fb36aba06b55764fd449bcbfc"
BASELINE = FIXTURE.read_bytes()
BASELINE_TREE = ast.parse(BASELINE)
PRIMITIVE_FIXTURE = ROOT / "tests/fixtures/arc_sector/arc_profile_primitives-a05626e.py.txt"
PRIMITIVE_SHA256 = "ebd60e4dd35c98459dd6d688e81322f88adcb1766c0864e16d10b9defea738bd"
PRIMITIVE_BASELINE = PRIMITIVE_FIXTURE.read_bytes()
DEFINITION_TYPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
TOP_LEVEL = {node.name: node for node in BASELINE_TREE.body if isinstance(node, DEFINITION_TYPES)}
METHODS = {
    node.name: node for node in TOP_LEVEL["OCPKernel"].body if isinstance(node, DEFINITION_TYPES)
}
IMPORTS = [node for node in BASELINE_TREE.body if isinstance(node, (ast.Import, ast.ImportFrom))]
LEAVES = (
    "arc_profile_primitives",
    "arc_profile_incidence",
    "arc_profile_intervals",
    "arc_profile_sector",
    "arc_profile_sector_source",
    "arc_profile_sector_policy",
    "arc_profile_native_plan",
    "arc_profile_native_evidence",
)
REVIEWED_EDGES = {
    "arc_profile_primitives": (),
    "arc_profile_incidence": ("arc_profile_primitives",),
    "arc_profile_intervals": ("arc_profile_primitives",),
    "arc_profile_sector_source": ("arc_profile_primitives",),
    "arc_profile_sector_policy": (
        "arc_profile_primitives",
        "arc_profile_intervals",
        "arc_profile_sector_source",
    ),
    "arc_profile_sector": (
        "arc_profile_primitives",
        "arc_profile_incidence",
        "arc_profile_intervals",
        "arc_profile_sector_source",
        "arc_profile_sector_policy",
    ),
    "arc_profile_native_plan": (
        "arc_profile_primitives",
        "arc_profile_intervals",
        "arc_profile_sector_source",
        "arc_profile_sector_policy",
    ),
    "arc_profile_native_evidence": (
        "arc_profile_native_plan",
        "arc_profile_primitives",
        "arc_profile_intervals",
    ),
    "kernel_ocp": (
        "arc_profile_native_plan",
        "arc_profile_native_evidence",
        "arc_profile_sector",
    ),
}
IMPORT_STYLES = (
    "import mechanical_cad.{leaf}\n",
    "import mechanical_cad.{leaf} as hidden\n",
    "from mechanical_cad import {leaf} as hidden\n",
    "from . import {leaf} as hidden\n",
    "from mechanical_cad.{leaf} import evidence as hidden\n",
    "from .{leaf} import evidence as hidden\n",
    "from mechanical_cad.{leaf} import *\n",
    "from .{leaf} import *\n",
)
DYNAMIC_IMPORT_STYLES = (
    '__import__("mechanical_cad.{leaf}")\n',
    '__import__("mechanical_cad", fromlist=["{leaf}"])\n',
    'from builtins import __import__ as hidden\nhidden("mechanical_cad.{leaf}")\n',
    'import builtins as hidden\nhidden.__import__("mechanical_cad.{leaf}")\n',
    'import importlib\nimportlib.import_module("mechanical_cad.{leaf}")\n',
    'import importlib as hidden\nhidden.import_module(".{leaf}", "mechanical_cad")\n',
    'from importlib import import_module as hidden\nhidden("mechanical_cad.{leaf}")\n',
    'from importlib import import_module\nimport_module(name="mechanical_cad.{leaf}")\n',
)


def _extract_function(filename, name, namespace):
    namespace = {**namespace, "TRUSTED_GUARD_ROOT": ROOT}
    if name == INCIDENCE_GUARD:
        # Extraction validates the caller's explicit target, not the pristine
        # archive (nor the same-named pytest fixture). ROOT remains independently
        # overridable for the current primitive resource check.
        target = namespace.pop("HISTORICAL_TARGET", namespace["ROOT"])
        namespace["historical_runtime_root"] = lambda: target
    tree = ast.parse((ROOT / "tests/unit" / filename).read_bytes())
    node = next(
        item for item in tree.body if isinstance(item, ast.FunctionDef) and item.name == name
    )
    exec(compile(ast.Module(body=[node], type_ignores=[]), filename, "exec"), namespace)
    return namespace[name]


def _run_dependency_guard(root, guard):
    filename, name = guard
    _extract_function(filename, name, {"ROOT": root, "ast": ast, "hashlib": hashlib})()


def _kernel_guard():
    tree = ast.parse((ROOT / "tests/unit/test_arc_profile_incidence.py").read_bytes())
    outer = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == INCIDENCE_GUARD
    )
    helper = next(
        node
        for node in outer.body
        if isinstance(node, ast.FunctionDef) and node.name == "assert_kernel_additive_boundary"
    )
    namespace = {"ast": ast}
    exec(compile(ast.Module(body=[helper], type_ignores=[]), "kernel_boundary", "exec"), namespace)
    return namespace[helper.name]


def _primitive_guard():
    tree = ast.parse((ROOT / "tests/unit/test_arc_profile_incidence.py").read_bytes())
    outer = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == INCIDENCE_GUARD
    )
    helper = next(
        node
        for node in outer.body
        if isinstance(node, ast.FunctionDef) and node.name == "assert_primitive_resource_boundary"
    )
    namespace = {"hashlib": hashlib}
    exec(
        compile(ast.Module(body=[helper], type_ignores=[]), "primitive_boundary", "exec"), namespace
    )
    return namespace[helper.name]


def _authoring_originals(root):
    tree = ast.parse((ROOT / "tests/unit/test_arc_profile_incidence.py").read_bytes())
    outer = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == INCIDENCE_GUARD
    )
    helper = next(
        node
        for node in outer.body
        if isinstance(node, ast.FunctionDef) and node.name == "reviewed_authoring_originals"
    )
    namespace = {"ast": ast, "hashlib": hashlib, "json": json, "TRUSTED_GUARD_ROOT": ROOT}
    exec(
        compile(ast.Module(body=[helper], type_ignores=[]), "authoring_boundary", "exec"), namespace
    )
    return namespace[helper.name](root)


def _with_native_resource_budget(source=PRIMITIVE_BASELINE):
    old_limit = b"MAX_OPERATIONS = 100_000\n"
    new_limits = b"MAX_OPERATIONS = 200_000\nDEFAULT_OPERATIONS = 100_000\n"
    old_signature = (
        b"    def __init__(self, *, max_bits: int = MAX_INTEGER_BITS, "
        b"max_operations: int = MAX_OPERATIONS):\n"
    )
    new_signature = (
        b"    def __init__(\n"
        b"        self, *, max_bits: int = MAX_INTEGER_BITS, "
        b"max_operations: int = DEFAULT_OPERATIONS\n"
        b"    ):\n"
    )
    assert source.count(old_limit) == source.count(old_signature) == 1
    return source.replace(old_limit, new_limits).replace(old_signature, new_signature)


def _replace_span(node, replacement):
    lines = BASELINE.splitlines(keepends=True)
    start = min([node.lineno] + [item.lineno for item in getattr(node, "decorator_list", ())])
    return b"".join(lines[: start - 1]) + replacement + b"".join(lines[node.end_lineno :])


def _span(node):
    lines = BASELINE.splitlines(keepends=True)
    start = min([node.lineno] + [item.lineno for item in getattr(node, "decorator_list", ())])
    return b"".join(lines[start - 1 : node.end_lineno])


def _with_curve_profile(source=BASELINE):
    old = (
        b"        if operation and operation.kind in "
        b'{"rectangle", "circle", "polygon", "circle_profile"}:\n'
    )
    new = (
        b"        if operation and operation.kind in {\n"
        b'            "rectangle",\n'
        b'            "circle",\n'
        b'            "polygon",\n'
        b'            "circle_profile",\n'
        b'            "curve_profile",\n'
        b"        }:\n"
    )
    assert source.count(old) == 1
    return source.replace(old, new)


@pytest.fixture
def guarded_root(tmp_path):
    for relative in (
        "src/mechanical_cad/arc_geometry.py",
        "src/mechanical_cad/arc_profile_primitives.py",
    ):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / relative).read_bytes())
    (tmp_path / "blender_addon").mkdir()
    return tmp_path


def _write_import(root, path, source):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    existing = target.read_text(encoding="utf-8") if target.exists() else ""
    target.write_text(existing + source, encoding="utf-8", newline="\n")


@pytest.mark.parametrize("guard", GUARDS)
def test_real_repository_runs_both_selected_dependency_functions(guard):
    _run_dependency_guard(ROOT, guard)


@pytest.mark.parametrize("guard", GUARDS)
@pytest.mark.parametrize(
    "owner,leaf", [(owner, leaf) for owner, leaves in REVIEWED_EDGES.items() for leaf in leaves]
)
@pytest.mark.parametrize("style", IMPORT_STYLES)
def test_every_exact_reviewed_edge_and_alias_passes(guarded_root, guard, owner, leaf, style):
    _write_import(guarded_root, f"src/mechanical_cad/{owner}.py", style.format(leaf=leaf))
    _run_dependency_guard(guarded_root, guard)


@pytest.mark.parametrize("guard", GUARDS)
@pytest.mark.parametrize(
    "owner,leaf",
    [
        (owner, leaf)
        for owner, allowed in REVIEWED_EDGES.items()
        for leaf in LEAVES
        if leaf not in allowed
    ],
)
@pytest.mark.parametrize("style", IMPORT_STYLES)
def test_unreviewed_reverse_cyclic_and_kernel_bypass_edges_reject(
    guarded_root, guard, owner, leaf, style
):
    _write_import(guarded_root, f"src/mechanical_cad/{owner}.py", style.format(leaf=leaf))
    with pytest.raises(AssertionError):
        _run_dependency_guard(guarded_root, guard)


@pytest.mark.parametrize("guard", GUARDS)
@pytest.mark.parametrize("owner", LEAVES)
@pytest.mark.parametrize("style", IMPORT_STYLES)
def test_no_pure_leaf_can_reverse_import_the_kernel(guarded_root, guard, owner, style):
    _write_import(guarded_root, f"src/mechanical_cad/{owner}.py", style.format(leaf="kernel_ocp"))
    with pytest.raises(AssertionError):
        _run_dependency_guard(guarded_root, guard)


@pytest.mark.parametrize("guard", GUARDS)
@pytest.mark.parametrize("leaf", ("arc_profile_native_plan", "arc_profile_native_evidence"))
@pytest.mark.parametrize("style", IMPORT_STYLES)
@pytest.mark.parametrize(
    "path",
    (
        "src/mechanical_cad/engine.py",
        "src/mechanical_cad/profile_region.py",
        "src/mechanical_cad/sketch_service.py",
        "src/mechanical_cad/sketch_evaluation.py",
        "src/mechanical_cad/sidecar.py",
        "src/mechanical_cad/backend_contract.py",
        "src/impostor/arc_profile_native_plan.py",
        "src/impostor/kernel_ocp.py",
        "src/mechanical_cad/nested/arc_profile_native_plan.py",
        "src/mechanical_cad/arc_profile_native_plan_impostor.py",
        "src/mechanical_cad/arc_profile_native_plan/__init__.py",
        "blender_addon/arc_profile_native_plan.py",
        "blender_addon/mechanical_cad_blender/arc_profile_native_plan.py",
        "blender_addon/mechanical_cad_blender/kernel_ocp.py",
    ),
)
def test_runtime_service_addon_and_impostor_paths_stay_closed(
    guarded_root, guard, leaf, style, path
):
    _write_import(guarded_root, path, style.format(leaf=leaf))
    with pytest.raises(AssertionError):
        _run_dependency_guard(guarded_root, guard)


@pytest.mark.parametrize("guard", GUARDS)
@pytest.mark.parametrize(
    "style",
    (
        "import {leaf} as hidden\n",
        "import impostor.{leaf} as hidden\n",
        "import mechanical_cad.{leaf}.impostor as hidden\n",
        "from impostor.{leaf} import evidence\n",
        "from mechanical_cad.impostor import {leaf}\n",
        "from mechanical_cad.{leaf}.impostor import evidence\n",
        "from ..{leaf} import evidence\n",
        "from .. import {leaf}\n",
        "from .impostor import {leaf}\n",
    ),
)
def test_approved_source_path_cannot_import_an_impostor_target(guarded_root, guard, style):
    _write_import(
        guarded_root,
        "src/mechanical_cad/kernel_ocp.py",
        style.format(leaf="arc_profile_native_plan"),
    )
    with pytest.raises(AssertionError):
        _run_dependency_guard(guarded_root, guard)


@pytest.mark.parametrize("guard", GUARDS)
@pytest.mark.parametrize("leaf", LEAVES)
@pytest.mark.parametrize("style", DYNAMIC_IMPORT_STYLES)
@pytest.mark.parametrize(
    "path",
    (
        "src/mechanical_cad/kernel_ocp.py",
        "src/mechanical_cad/engine.py",
        "blender_addon/mechanical_cad_blender/arc_profile_native_plan.py",
    ),
)
def test_dynamic_import_aliases_cannot_bypass_the_reviewed_static_graph(
    guarded_root, guard, leaf, style, path
):
    _write_import(guarded_root, path, style.format(leaf=leaf))
    with pytest.raises(AssertionError):
        _run_dependency_guard(guarded_root, guard)


@pytest.mark.parametrize("guard", GUARDS)
@pytest.mark.parametrize("style", DYNAMIC_IMPORT_STYLES)
def test_native_plan_cannot_dynamically_reverse_import_the_kernel(guarded_root, guard, style):
    _write_import(
        guarded_root,
        "src/mechanical_cad/arc_profile_native_plan.py",
        style.format(leaf="kernel_ocp"),
    )
    with pytest.raises(AssertionError):
        _run_dependency_guard(guarded_root, guard)


@pytest.mark.parametrize("guard", GUARDS)
@pytest.mark.parametrize("style", ("from mechanical_cad import *\n", "from . import *\n"))
def test_package_wildcard_is_not_an_exact_reviewed_edge(guarded_root, guard, style):
    _write_import(guarded_root, "src/mechanical_cad/kernel_ocp.py", style)
    with pytest.raises(AssertionError):
        _run_dependency_guard(guarded_root, guard)


def test_historical_fixture_is_exact_and_has_explicit_provenance():
    assert hashlib.sha256(BASELINE).hexdigest() == FIXTURE_SHA256
    provenance = json.loads(FIXTURE.with_name("kernel_ocp-a05626e.provenance.json").read_text(encoding="utf-8"))
    assert provenance["baseline_commit"] == "a05626ef841478bbdaabe5ac3c58e7795a6be375"
    assert provenance["source_path"] == "src/mechanical_cad/kernel_ocp.py"
    assert provenance["fixture"] == FIXTURE.name
    assert provenance["source_command"] == (
        "git show a05626ef841478bbdaabe5ac3c58e7795a6be375:src/mechanical_cad/kernel_ocp.py"
    )
    assert provenance["sha256"] == FIXTURE_SHA256
    assert provenance["size_bytes"] == len(BASELINE)


def test_unchanged_kernel_and_exact_topology_addition_pass():
    check = _kernel_guard()
    check(BASELINE, BASELINE)
    check(BASELINE, _with_curve_profile())


def test_additive_imports_helpers_and_methods_pass_without_loading_the_kernel():
    source = (
        _with_curve_profile()
        .replace(b"from OCP.gp import gp_Ax2,", b"from OCP.gp import gp_Ax1, gp_Ax2,")
        .replace(
            b"class KernelError(ValueError):",
            b"from .arc_profile_native_plan import NativePlan\n\n\nclass KernelError(ValueError):",
        )
    )
    source += b"\n    def new_sector_method(self):\n        return None\n"
    source += b"\n\ndef new_sector_helper():\n    return None\n"
    _kernel_guard()(BASELINE, source)


@pytest.mark.parametrize("name", [name for name in TOP_LEVEL if name != "OCPKernel"])
def test_every_old_top_level_helper_or_class_byte_span_is_protected(name):
    node = TOP_LEVEL[name]
    changed = _span(node).replace(b"\n", b" \n", 1)
    with pytest.raises(AssertionError):
        _kernel_guard()(BASELINE, _replace_span(node, changed))


@pytest.mark.parametrize("name", [name for name in METHODS if name != "topology"])
def test_every_old_kernel_method_byte_span_is_protected(name):
    node = METHODS[name]
    changed = _span(node).replace(b"\n", b" \n", 1)
    with pytest.raises(AssertionError):
        _kernel_guard()(BASELINE, _replace_span(node, changed))


@pytest.mark.parametrize(
    "node",
    list(TOP_LEVEL.values()) + list(METHODS.values()),
    ids=list(TOP_LEVEL) + [f"OCPKernel.{name}" for name in METHODS],
)
def test_deleted_or_duplicate_original_definitions_reject(node):
    check = _kernel_guard()
    with pytest.raises(AssertionError):
        check(BASELINE, _replace_span(node, b""))
    with pytest.raises(AssertionError):
        check(BASELINE, _replace_span(node, _span(node) + b"\n" + _span(node)))


@pytest.mark.parametrize("node", IMPORTS, ids=[f"line-{node.lineno}" for node in IMPORTS])
def test_every_original_import_statement_must_be_retained(node):
    with pytest.raises(AssertionError):
        _kernel_guard()(BASELINE, _replace_span(node, b""))


@pytest.mark.parametrize(
    "index,alias_index",
    [
        (index, alias_index)
        for index, node in enumerate(IMPORTS)
        if len(node.names) > 1
        for alias_index in range(len(node.names))
    ],
)
def test_removing_one_name_from_an_original_import_rejects(index, alias_index):
    node = ast.parse(ast.unparse(IMPORTS[index])).body[0]
    del node.names[alias_index]
    replacement = ast.unparse(node).encode() + b"\n"
    with pytest.raises(AssertionError):
        _kernel_guard()(BASELINE, _replace_span(IMPORTS[index], replacement))


@pytest.mark.parametrize(
    "old,new",
    (
        (b"class OCPKernel:", b"class OCPKernel(KernelError):"),
        (b"class OCPKernel:", b"class OCPKernel :"),
        (b"class OCPKernel:\n", b"class OCPKernel:\n\n"),
        (b"class OCPKernel:", b"@dataclass\nclass OCPKernel:"),
        (b"class OCPKernel:", b"class OCPKernel(metaclass=type):"),
        (b"A millimetre-based B-rep kernel", b"A changed B-rep kernel"),
        (
            b"    def __init__(self) -> None:\n        self._operations",
            b"    changed_class_state = True\n\n    def __init__(self) -> None:\n        self._operations",
        ),
        (
            b"    def __init__(self) -> None:\n        self._operations",
            b"    from math import cos\n\n    def __init__(self) -> None:\n        self._operations",
        ),
        (b"Small OCCT adapter.", b"Changed OCCT adapter."),
        (b"import math\n", b"import math as changed\n"),
        (b"import math\n", b"import math\nfrom .arc_profile_native_plan import unsafe as math\n"),
        (b"import math\n", b"import math\nfrom .arc_profile_native_plan import *\n"),
    ),
)
def test_class_metadata_body_module_statements_and_import_binding_changes_reject(old, new):
    assert BASELINE.count(old) == 1
    with pytest.raises(AssertionError):
        _kernel_guard()(BASELINE, BASELINE.replace(old, new))


def test_unchanged_class_docstring_ast_does_not_waive_original_statement_bytes():
    statement = TOP_LEVEL["OCPKernel"].body[0]
    replacement = _span(statement).replace(b'"""', b"'''")
    assert ast.dump(ast.parse(replacement.decode().lstrip())) == ast.dump(
        ast.parse(_span(statement).decode().lstrip())
    )
    with pytest.raises(AssertionError):
        _kernel_guard()(BASELINE, _replace_span(statement, replacement))


@pytest.mark.parametrize(
    "old,new",
    (
        (b"class OCPKernel:\n", b"class OCPKernel:\n    def fresh(self):\n        pass\n"),
        (b'"""Small OCCT adapter.', b'def fresh():\n    pass\n\n"""Small OCCT adapter.'),
    ),
)
def test_additive_definitions_cannot_displace_original_docstrings(old, new):
    assert BASELINE.count(old) == 1
    with pytest.raises(AssertionError):
        _kernel_guard()(BASELINE, BASELINE.replace(old, new))


@pytest.mark.parametrize(
    "suffix",
    (
        b"\nOCPKernel = None\n",
        b"\n_number = None\n",
        b"\ndef math():\n    return None\n",
        b"\ndef fresh():\n    pass\n\ndef fresh():\n    pass\n",
        b"\n    def fresh(self):\n        pass\n\n    def fresh(self):\n        pass\n",
    ),
)
def test_late_overrides_shadowing_and_duplicate_new_definitions_reject(suffix):
    with pytest.raises(AssertionError):
        _kernel_guard()(BASELINE, BASELINE + suffix)


@pytest.mark.parametrize(
    "replacement",
    (
        b'{"rectangle", "circle", "polygon"}',
        b'{"rectangle", "circle", "polygon", "other_profile"}',
        b'{"rectangle", "circle", "polygon", "circle_profile", "other_profile"}',
        b'{"rectangle", "circle", "polygon", "circle_profile", "curve_profile", "curve_profile"}',
        b'{"rectangle", "circle", "polygon", "curve_profile"}',
        b'{"circle", "rectangle", "polygon", "circle_profile", "curve_profile"}',
        b'{"rectangle", "circle", "polygon", "circle_profile", *["curve_profile"]}',
    ),
)
def test_topology_set_changes_other_than_one_exact_added_constant_reject(replacement):
    old = b'{"rectangle", "circle", "polygon", "circle_profile"}'
    with pytest.raises(AssertionError):
        _kernel_guard()(BASELINE, BASELINE.replace(old, replacement))


@pytest.mark.parametrize(
    "old,new",
    (
        (
            b'assign(shape, "profile", "constructed_profile")',
            b'assign(shape, "profile", "changed_profile")',
        ),
        (b"        del kind, params, inputs\n", b"        del kind, params\n"),
        (
            b"        del kind, params, inputs\n",
            b'        unrelated = {"curve_profile"}\n        del kind, params, inputs\n',
        ),
    ),
)
def test_topology_addition_does_not_exempt_any_other_ast_change(old, new):
    source = _with_curve_profile()
    assert source.count(old) == 1
    with pytest.raises(AssertionError):
        _kernel_guard()(BASELINE, source.replace(old, new))


def test_unchanged_topology_ast_does_not_waive_its_original_byte_span():
    node = METHODS["topology"]
    with pytest.raises(AssertionError):
        _kernel_guard()(BASELINE, _replace_span(node, _span(node).replace(b"\n", b" \n", 1)))


@pytest.mark.parametrize(
    "old,new",
    (
        (b"        del kind, params, inputs\n", b"        del kind, params, inputs  \n"),
        (b"        del kind, params, inputs\n", b"        del kind, params, inputs  # changed\n"),
        (b"        del kind, params, inputs\n", b"\n        del kind, params, inputs\n"),
        (
            b"        del kind, params, inputs\n",
            b"        # inserted comment\n        del kind, params, inputs\n",
        ),
        (b'            "curve_profile",\n', b'            "curve_profile",  # unrelated comment\n'),
    ),
)
def test_reviewed_topology_addition_cannot_hide_unrelated_whitespace_or_comments(old, new):
    source = _with_curve_profile()
    assert source.count(old) == 1
    with pytest.raises(AssertionError):
        _kernel_guard()(BASELINE, source.replace(old, new))


def test_original_runtime_hash_guard_runs_without_importing_production_modules():
    _extract_function(
        "test_arc_profile_incidence.py",
        INCIDENCE_GUARD,
        {"ROOT": historical_source_root(), "ast": ast, "hashlib": hashlib, "json": json},
    )()


@pytest.fixture(scope="module")
def historical_runtime_root(tmp_path_factory):
    source = historical_source_root()
    root = tmp_path_factory.mktemp("historical-runtime-guard")
    added, authoring_originals = _authoring_originals(source)
    standalone_fixtures = {
        "tests/fixtures/standalone/python_additions_69d0f81.json": "0e6152a913e23079c770f23bbe6daf111d28f82981496e1c85af19ae1bc5c6c9",
        "tests/fixtures/standalone/python_revision_ab7edce.json": "28a8c806614dbfd7bb7e81c443630f3b05b34fd089c3684b6b4139c840c038ee",
    }
    guard_source = ast.parse((source / "tests/unit/test_arc_profile_native_end_cap.py").read_bytes())
    windows_digests = {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in guard_source.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id
        in {
            "WINDOWS_TRANSPORT_REVISION_SHA256",
            "WINDOWS_TRANSPORT_HARNESS_SHA256",
            "WINDOWS_CACHE_REVISION_SHA256",
            "WINDOWS_CACHE_HARNESS_SHA256",
        }
    }
    assert len(windows_digests) == 4
    runtime_cache_digests = {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in guard_source.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id
        in {"WINDOWS_RUNTIME_CACHE_REVISION_SHA256", "WINDOWS_RUNTIME_CACHE_HARNESS_SHA256"}
    }
    assert len(runtime_cache_digests) == 2
    standalone_fixtures.update(
        {
            "tests/fixtures/standalone/python_windows_transport_revision_2144b11.json": windows_digests[
                "WINDOWS_TRANSPORT_REVISION_SHA256"
            ],
            "tests/fixtures/standalone/test_windows_transport_harness_revision_2144b11.json": windows_digests[
                "WINDOWS_TRANSPORT_HARNESS_SHA256"
            ],
        }
    )
    standalone_fixtures.update(
        {
            "tests/fixtures/standalone/windows_cache_revision_post_transport.json": windows_digests[
                "WINDOWS_CACHE_REVISION_SHA256"
            ],
            "tests/fixtures/standalone/windows_cache_harness_revision_post_transport.json": windows_digests[
                "WINDOWS_CACHE_HARNESS_SHA256"
            ],
        }
    )
    standalone_fixtures.update(
        {
            "tests/fixtures/standalone/windows_runtime_cache_revision_post_cache.json": runtime_cache_digests[
                "WINDOWS_RUNTIME_CACHE_REVISION_SHA256"
            ],
            "tests/fixtures/standalone/windows_runtime_cache_harness_revision_post_cache.json": runtime_cache_digests[
                "WINDOWS_RUNTIME_CACHE_HARNESS_SHA256"
            ],
        }
    )
    support = {"tests/fixtures/standalone/test_harness_revision_1c8f030.json"}
    for relative in (
        "tests/fixtures/visual_assembly_joints/source_edc574e.json",
        "tests/fixtures/release_071/metadata_56a13b3.json",
        "tests/fixtures/assembly_step_export/source_c405435.json",
        "tests/fixtures/release_070/metadata_eb9b51c.json",
        "tests/fixtures/assembly_v3/source_75c3768.json",
        "tests/fixtures/assembly_v3/harness_75c3768.json",
        "tests/fixtures/geometry_v3/gate_c_owner_source_de70a45.json",
        "tests/fixtures/geometry_v3/gate_c_owner_harness_de70a45.json",
        "tests/fixtures/arc_sector/inventory_guard_harness_a88ac4f.json",
        "tests/fixtures/result_v3/redundant_solve_source_cc130e6.json",
        "tests/fixtures/result_v3/redundant_solve_harness_cc130e6.json",
        "tests/fixtures/geometry_v3/python_revision_69d0f81.json",
        "tests/fixtures/geometry_v3/standalone_integration_source.json",
        "tests/fixtures/geometry_v3/standalone_integration_harness.json",
    ):
        support.add(relative)
        fixture = json.loads((source / relative).read_bytes())
        support.update(fixture.get("added", {}))
        support.update(fixture.get("changed", {}))
    for relative, expected in standalone_fixtures.items():
        raw = (source / relative).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == expected
        fixture = json.loads(raw)
        support.add(relative)
        support.update(fixture.get("added", {}))
        support.update(fixture.get("changed", {}))
        support.update(fixture.get("baseline_runtime", {}))
    # Carry the complete reviewed footprint so every clean inverse check runs
    # before any of the original per-file mutations. There is no fixture mode.
    for relative in (
        set(added)
        | set(authoring_originals)
        | support
        | {
            "tests/fixtures/arc_authoring/python_revision_ce5b50b.json",
            "tests/unit/test_arc_profile_native_end_cap.py",
        }
    ):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((source / relative).read_bytes())
    baseline_path = "docs/architecture/arc_profile_service/BASELINE.json"
    manifest_bytes = (source / baseline_path).read_bytes()
    hashes = json.loads(manifest_bytes)["source_sha256"]
    dispatch_path = "tests/fixtures/result_v3/dispatch_extension_30383a1.json"
    dispatch_bytes = (source / dispatch_path).read_bytes()
    assert hashlib.sha256(dispatch_bytes).hexdigest() == (
        "4eed9a50153d2c4b3d0ea8fda5e48cd378e050287ca374241b56ee0481b497c8"
    )
    dispatch = json.loads(dispatch_bytes)["files"]
    assert set(dispatch) == {
        "src/mechanical_cad/engine.py",
        "src/mechanical_cad/sidecar.py",
        "src/mechanical_cad/backend_contract.py",
    }
    for relative, expected in hashes.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        data = (source / relative).read_bytes()
        # This historical inverse checks the pinned-era kernel against its129
        # baseline. Its original additive-span and per-file mutation assertions
        # remain exact; current runtime boundaries are exercised separately.
        original = (
            BASELINE
            if relative == "src/mechanical_cad/kernel_ocp.py"
            else authoring_originals.get(relative, data)
        )
        if relative in dispatch:
            entry = dispatch[relative]
            assert hashlib.sha256(original).hexdigest() == entry["reviewed_sha256"]
            for hunk in reversed(entry["hunks"]):
                start, end = hunk["new_start"], hunk["new_end"]
                assert original[start:end] == hunk["replacement"].encode("utf-8")
                original = original[:start] + hunk["original"].encode("utf-8") + original[end:]
            assert entry["original_sha256"] == expected
        assert hashlib.sha256(original).hexdigest() == expected
        target.write_bytes(data)
    for relative, data in (
        (baseline_path, manifest_bytes),
        (dispatch_path, dispatch_bytes),
        (str(FIXTURE.relative_to(ROOT)), BASELINE),
        (str(PRIMITIVE_FIXTURE.relative_to(ROOT)), PRIMITIVE_BASELINE),
        (
            "src/mechanical_cad/arc_profile_primitives.py",
            (source / "src/mechanical_cad/arc_profile_primitives.py").read_bytes(),
        ),
    ):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    # A mutation rejection is meaningful only if this exact clean fixture is
    # first admitted. Keep all original 104 per-file mutation assertions below.
    _extract_function(
        "test_arc_profile_incidence.py",
        INCIDENCE_GUARD,
        {"ROOT": root, "ast": ast, "hashlib": hashlib, "json": json},
    )()
    return root


@pytest.mark.parametrize(
    "relative",
    [
        path
        for path in json.loads(
            (ROOT / "docs/architecture/arc_profile_service/BASELINE.json").read_bytes()
        )["source_sha256"]
        if path != "src/mechanical_cad/kernel_ocp.py"
    ],
)
def test_each_of_the_104_non_kernel_runtime_byte_hashes_still_rejects_changes(
    historical_runtime_root, relative
):
    target = historical_runtime_root / relative
    original = target.read_bytes()
    try:
        target.write_bytes(original + b"\n# Unreviewed byte mutation.\n")
        with pytest.raises(AssertionError):
            _extract_function(
                "test_arc_profile_incidence.py",
                INCIDENCE_GUARD,
                {"ROOT": historical_runtime_root, "ast": ast, "hashlib": hashlib, "json": json},
            )()
    finally:
        target.write_bytes(original)


@pytest.mark.parametrize(
    "relative",
    (
        "tests/fixtures/arc_authoring/python_revision_ce5b50b.json",
        "tests/fixtures/standalone/python_windows_transport_revision_2144b11.json",
        "tests/fixtures/standalone/test_windows_transport_harness_revision_2144b11.json",
        "tests/fixtures/standalone/windows_cache_revision_post_transport.json",
        "tests/fixtures/standalone/windows_cache_harness_revision_post_transport.json",
        "tests/fixtures/standalone/windows_runtime_cache_revision_post_cache.json",
        "tests/fixtures/standalone/windows_runtime_cache_harness_revision_post_cache.json",
        "blender_addon/mechanical_cad_blender/operation_contracts.py",
        "blender_addon/mechanical_cad_blender/general_arc_authoring_store.py",
    ),
)
def test_authoring_inverse_and_added_footprint_never_bypass_runtime_guard(
    historical_runtime_root, relative
):
    target = historical_runtime_root / relative
    original = target.read_bytes()
    try:
        target.write_bytes(original + b"\n# Unreviewed byte mutation.\n")
        with pytest.raises(AssertionError):
            _extract_function(
                "test_arc_profile_incidence.py",
                INCIDENCE_GUARD,
                {"ROOT": historical_runtime_root, "ast": ast, "hashlib": hashlib, "json": json},
            )()
    finally:
        target.write_bytes(original)


def test_historical_primitive_fixture_is_exact_and_has_explicit_provenance():
    assert hashlib.sha256(PRIMITIVE_BASELINE).hexdigest() == PRIMITIVE_SHA256
    provenance = json.loads(
        PRIMITIVE_FIXTURE.with_name("arc_profile_primitives-a05626e.provenance.json").read_text(encoding="utf-8")
    )
    assert provenance["baseline_commit"] == "a05626ef841478bbdaabe5ac3c58e7795a6be375"
    assert provenance["source_path"] == "src/mechanical_cad/arc_profile_primitives.py"
    assert provenance["fixture"] == PRIMITIVE_FIXTURE.name
    assert provenance["source_command"] == (
        "git show a05626ef841478bbdaabe5ac3c58e7795a6be375:"
        "src/mechanical_cad/arc_profile_primitives.py"
    )
    assert provenance["sha256"] == PRIMITIVE_SHA256
    assert provenance["size_bytes"] == len(PRIMITIVE_BASELINE) == 29558


def test_only_the_complete_exact_primitive_resource_revision_passes():
    expected = _with_native_resource_budget()
    _primitive_guard()(PRIMITIVE_BASELINE, expected)
    assert (ROOT / "src/mechanical_cad/arc_profile_primitives.py").read_bytes() == expected
    with pytest.raises(AssertionError):
        _primitive_guard()(PRIMITIVE_BASELINE, PRIMITIVE_BASELINE)
    for partial in (
        PRIMITIVE_BASELINE.replace(b"MAX_OPERATIONS = 100_000\n", b"MAX_OPERATIONS = 200_000\n"),
        expected.replace(b"DEFAULT_OPERATIONS = 100_000\n", b""),
        expected.replace(
            b"max_operations: int = DEFAULT_OPERATIONS", b"max_operations: int = 100000"
        ),
    ):
        with pytest.raises(AssertionError):
            _primitive_guard()(PRIMITIVE_BASELINE, partial)


@pytest.mark.parametrize(
    "old,new",
    [
        (b"MAX_OPERATIONS = 200_000\n", b"MAX_OPERATIONS = 200_001\n"),
        (b"DEFAULT_OPERATIONS = 100_000\n", b"DEFAULT_OPERATIONS = 200_000\n"),
        (b"MAX_INTEGER_BITS = 65_536\n", b"MAX_INTEGER_BITS = 131_072\n"),
        (b"INTERVAL_PRECISIONS = (64, 128, 256)\n", b"INTERVAL_PRECISIONS = (64, 128, 512)\n"),
        (b"max_operations: int = DEFAULT_OPERATIONS", b"max_operations: int = MAX_OPERATIONS"),
        (b"not 1 <= max_operations <= MAX_OPERATIONS", b"not 1 <= max_operations <= 400_000"),
        (b'if hasattr(self, "_operations"):', b"if False:"),
        (
            b"if self._operations >= self._max_operations:",
            b"if self._operations > self._max_operations:",
        ),
        (b"self._operations + 1)", b"self._operations + 2)"),
        (b"return left + right", b"return left - right"),
        (b"type(value) is not Dyadic", b"not isinstance(value, Dyadic)"),
        (b"Smaller limits are for tests, never larger limits.", b"Larger limits are unrestricted."),
        (b"MAX_OPERATIONS = 200_000\n", b"MAX_OPERATIONS = 200_000  # unrelated comment\n"),
        (b"import math\n", b"import math\n\n"),
        (b"SPDX-License-Identifier: GPL-3.0-or-later", b"SPDX-License-Identifier: GPL-3.0-only"),
    ],
)
def test_approved_budget_diff_cannot_hide_unreviewed_primitive_changes(old, new):
    expected = _with_native_resource_budget()
    assert expected.count(old) == 1
    with pytest.raises(AssertionError):
        _primitive_guard()(PRIMITIVE_BASELINE, expected.replace(old, new))


@pytest.mark.parametrize(
    "line",
    [
        node.lineno
        for node in ast.walk(ast.parse(PRIMITIVE_BASELINE))
        if isinstance(node, DEFINITION_TYPES)
    ],
)
def test_every_original_primitive_definition_still_rejects_unreviewed_bytes(line):
    lines = PRIMITIVE_BASELINE.splitlines(keepends=True)
    lines.insert(line - 1, b"# Unreviewed definition comment.\n")
    changed = _with_native_resource_budget(b"".join(lines))
    with pytest.raises(AssertionError):
        _primitive_guard()(PRIMITIVE_BASELINE, changed)


def test_primitive_provenance_cannot_be_rebased_to_hide_an_arithmetic_mutation():
    original = PRIMITIVE_BASELINE.replace(b"return left + right", b"return left - right")
    assert original != PRIMITIVE_BASELINE
    with pytest.raises(AssertionError, match="changed historical primitive bytes"):
        _primitive_guard()(original, _with_native_resource_budget(original))


@pytest.mark.parametrize(
    "relative",
    ["src/mechanical_cad/arc_profile_primitives.py", str(PRIMITIVE_FIXTURE.relative_to(ROOT))],
)
def test_runtime_guard_rejects_primitive_source_and_historical_fixture_changes(
    historical_runtime_root, relative
):
    target = historical_runtime_root / relative
    original = target.read_bytes()
    try:
        target.write_bytes(original + b"\n# Unreviewed primitive byte mutation.\n")
        with pytest.raises(AssertionError):
            _extract_function(
                "test_arc_profile_incidence.py",
                INCIDENCE_GUARD,
                {"ROOT": historical_runtime_root, "ast": ast, "hashlib": hashlib, "json": json},
            )()
    finally:
        target.write_bytes(original)


@pytest.mark.parametrize("mutation", ["helper", "constant"])
@pytest.mark.parametrize("entry", ["nested_helper", "whole_guard"])
def test_copied_guard_code_and_constants_are_only_hash_checked(
    historical_runtime_root, mutation, entry
):
    root = historical_runtime_root
    path = root / "tests/unit/test_arc_profile_native_end_cap.py"
    original = path.read_bytes()

    def run():
        if entry == "nested_helper":
            return _authoring_originals(root)
        return _extract_function(
            "test_arc_profile_incidence.py",
            INCIDENCE_GUARD,
            {"ROOT": root, "ast": ast, "hashlib": hashlib, "json": json},
        )()

    run()  # The copied data tree is otherwise admissible before poisoning it.
    if mutation == "helper":
        tree = ast.parse(original)
        node = next(
            item
            for item in tree.body
            if isinstance(item, ast.FunctionDef)
            and item.name == "standalone_integration_harness_originals"
        )
        lines = original.splitlines(keepends=True)
        poisoned = (
            b"".join(lines[: node.lineno])
            + b'    raise RuntimeError("copied validator executed")\n'
            + b"".join(lines[node.end_lineno :])
        )
    else:
        before = b'INTEGRATION_HARNESS_FIXTURE = "tests/fixtures/geometry_v3/standalone_integration_harness.json"'
        assert original.count(before) == 1
        poisoned = original.replace(
            before,
            b'INTEGRATION_HARNESS_FIXTURE = "tests/fixtures/geometry_v3/SHOULD_NOT_BE_READ.json"',
        )
    assert poisoned != original
    try:
        path.write_bytes(poisoned)
        # Loading the copied helper would raise RuntimeError; loading its copied
        # path constant would raise FileNotFoundError. Only the trusted validator
        # must run, rejecting these copied bytes against the unchanged outer seal.
        with pytest.raises(AssertionError):
            run()
    finally:
        path.write_bytes(original)


def test_incidence_guard_routes_history_and_live_primitives_independently(
    historical_runtime_root, tmp_path
):
    relative = "src/mechanical_cad/arc_profile_primitives.py"
    live = tmp_path / relative
    live.parent.mkdir(parents=True)
    live.write_bytes((ROOT / relative).read_bytes())
    namespace = {
        "ROOT": tmp_path,
        "HISTORICAL_TARGET": historical_runtime_root,
        "ast": ast,
        "hashlib": hashlib,
        "json": json,
    }
    guard = _extract_function("test_arc_profile_incidence.py", INCIDENCE_GUARD, namespace)
    guard()  # History is absent from the live tree; primitives are current bytes.
    target = historical_runtime_root / "src/mechanical_cad/model.py"
    original = target.read_bytes()
    try:
        target.write_bytes(original + b"\n# unreviewed historical target mutation\n")
        with pytest.raises(AssertionError):
            guard()  # A pristine archive substitution would incorrectly pass.
    finally:
        target.write_bytes(original)
    guard()
    live.write_bytes(live.read_bytes() + b"\n# unreviewed live primitive mutation\n")
    with pytest.raises(AssertionError):
        guard()  # Historical primitives must not substitute for the live leaf.
