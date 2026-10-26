"""Exact-path guards for native sectors and the dormant v3 leaf extension."""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path

import pytest

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


def _run_guard(root: Path, guard: tuple[str, str]) -> None:
    filename, function = guard
    tree = ast.parse((ROOT / "tests/unit" / filename).read_text())
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == function)
    namespace = {"ROOT": root, "ast": ast, "hashlib": hashlib}
    exec(compile(ast.Module(body=[node], type_ignores=[]), filename, "exec"), namespace)
    namespace[function]()


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


@pytest.mark.parametrize("guard", GUARDS)
def test_exact_reviewed_dependency_paths_pass(guarded_root, guard):
    files = {
        "src/mechanical_cad/arc_profile_incidence.py": "from .arc_profile_primitives import PrimitiveContext\n",
        "src/mechanical_cad/arc_profile_intervals.py": "from .arc_profile_primitives import Dyadic\n",
        "src/mechanical_cad/arc_profile_sector_source.py": "from .arc_profile_primitives import Dyadic\n",
        "src/mechanical_cad/arc_profile_sector_policy.py": (
            "from . import arc_profile_sector_source, arc_profile_intervals, arc_profile_primitives\n"
        ),
        "src/mechanical_cad/arc_profile_sector.py": (
            "from . import arc_profile_incidence, arc_profile_primitives, arc_profile_intervals, arc_profile_sector_source, arc_profile_sector_policy\n"
        ),
        "src/mechanical_cad/profile_adapter_v3.py": "from .arc_profile_sector import classify_sector\n",
        "blender_addon/mechanical_cad_blender/arc_profile_intervals.py": (
            "from .arc_profile_primitives import Dyadic\n"
        ),
        "blender_addon/mechanical_cad_blender/arc_profile_sector_source.py": (
            "from .arc_profile_primitives import Dyadic\n"
        ),
        "blender_addon/mechanical_cad_blender/arc_profile_sector_policy.py": (
            "from . import arc_profile_primitives, arc_profile_intervals, arc_profile_sector_source\n"
        ),
        "blender_addon/mechanical_cad_blender/sketch_contracts_v3.py": (
            "from . import arc_profile_primitives, arc_profile_sector_source, arc_profile_sector_policy\n"
        ),
    }
    for name, source in files.items():
        target = guarded_root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source)
    _run_guard(guarded_root, guard)


@pytest.mark.parametrize("guard", GUARDS)
@pytest.mark.parametrize("leaf", LEAVES)
@pytest.mark.parametrize(
    "style",
    (
        "import mechanical_cad.{leaf}\n",
        "from mechanical_cad import {leaf}\n",
        "from .{leaf} import evidence\n",
    ),
)
@pytest.mark.parametrize(
    "path",
    (
        "src/mechanical_cad/engine.py",
        "src/impostor/arc_profile_sector.py",
        "blender_addon/arc_profile_sector.py",
    ),
)
def test_runtime_and_basename_impostor_imports_reject(guarded_root, guard, leaf, style, path):
    target = guarded_root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(style.format(leaf=leaf))
    with pytest.raises(AssertionError):
        _run_guard(guarded_root, guard)


@pytest.mark.parametrize("guard", GUARDS)
@pytest.mark.parametrize(
    "path,leaf",
    (
        ("src/mechanical_cad/arc_profile_incidence.py", "arc_profile_sector"),
        ("src/mechanical_cad/arc_profile_incidence.py", "arc_profile_intervals"),
        ("src/mechanical_cad/arc_profile_intervals.py", "arc_profile_incidence"),
        ("src/mechanical_cad/arc_profile_intervals.py", "arc_profile_sector"),
        ("src/mechanical_cad/arc_profile_sector.py", "arc_profile_sector"),
        ("src/mechanical_cad/arc_profile_sector_source.py", "arc_profile_sector_policy"),
        ("src/mechanical_cad/arc_profile_sector_source.py", "arc_profile_sector"),
        ("src/mechanical_cad/arc_profile_sector_source.py", "arc_profile_incidence"),
        ("src/mechanical_cad/arc_profile_sector_policy.py", "arc_profile_sector"),
        ("src/mechanical_cad/arc_profile_sector_policy.py", "arc_profile_incidence"),
        ("src/mechanical_cad/arc_profile_intervals.py", "arc_profile_sector_source"),
        ("src/mechanical_cad/arc_profile_intervals.py", "arc_profile_sector_policy"),
        ("src/mechanical_cad/profile_adapter_v3.py", "arc_profile_native_plan"),
        ("src/mechanical_cad/profile_adapter_v3.py", "arc_profile_native_evidence"),
        ("blender_addon/mechanical_cad_blender/sketch_contracts_v3.py", "arc_profile_incidence"),
        ("blender_addon/mechanical_cad_blender/sketch_contracts_v3.py", "arc_profile_native_plan"),
        (
            "blender_addon/mechanical_cad_blender/sketch_contracts_v3.py",
            "arc_profile_native_evidence",
        ),
        (
            "blender_addon/mechanical_cad_blender/arc_profile_sector_source.py",
            "arc_profile_sector_policy",
        ),
    ),
)
def test_allowed_leaf_paths_cannot_add_unreviewed_or_cyclic_edges(guarded_root, guard, path, leaf):
    target = guarded_root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(f"from . import {leaf}\n")
    with pytest.raises(AssertionError):
        _run_guard(guarded_root, guard)
