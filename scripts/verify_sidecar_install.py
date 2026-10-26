#!/usr/bin/env python3
"""Verify the 1.17.0 source root and interpreter intended for Blender preferences.

This read-only check uses the same source-root precedence as the add-on bridge.
It cannot inspect or change another Blender process's saved preferences.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import sys
from pathlib import Path

EXPECTED_VERSION = "1.30.0"


def verify(root: Path) -> dict:
    root = root.resolve()
    expected_solver = root / "src/mechanical_cad/sketch_solver.py"
    if not expected_solver.is_file():
        raise RuntimeError("Project Root must contain src/mechanical_cad/sketch_solver.py")
    # The production bridge sets PYTHONPATH to this same directory before launch.
    sys.path.insert(0, str(root / "src"))
    core = importlib.import_module("mechanical_cad")
    solver = importlib.import_module("mechanical_cad.sketch_solver")
    if core.__version__ != EXPECTED_VERSION:
        raise RuntimeError(f"Expected core {EXPECTED_VERSION}; imported {core.__version__}")
    actual_solver = Path(solver.__file__).resolve()
    if actual_solver != expected_solver:
        raise RuntimeError(f"Imported an unexpected core: {actual_solver}")
    model = importlib.import_module("mechanical_cad.sketch_model")
    points = tuple(model.Point(name, 0, 0) for name in ("a", "b", "c"))
    relations = tuple(
        model.Constraint(f"join{i}", "coincident", pair)
        for i, pair in enumerate((("a", "b"), ("b", "c"), ("c", "a")))
    )
    cyclic = model.Sketch("install_cycle", points, (), relations, schema_version=2)
    before = cyclic.to_json()
    try:
        solver.solve(cyclic)
    except model.SketchError as error:
        if error.code != "solver_dof_indeterminate":
            raise RuntimeError(f"Unexpected cycle error: {error.code}") from error
    else:
        raise RuntimeError("The cyclic sketch was accepted; this core lacks the required guard")
    if cyclic.to_json() != before:
        raise RuntimeError("The cycle check changed the authored sketch")
    forest = model.Sketch("install_forest", points, (), relations[:2], schema_version=2)
    report = solver.solve(forest)
    if not report.success or report.remaining_dof != 2:
        raise RuntimeError("The acyclic native control did not return the expected two DoF")
    return {
        "ok": True,
        "core_version": core.__version__,
        "project_root": str(root),
        "python_executable": str(Path(sys.executable).absolute()),
        "solver_path": str(actual_solver),
        "solver_sha256": hashlib.sha256(actual_solver.read_bytes()).hexdigest(),
        "cyclic_equality": "rejected: solver_dof_indeterminate",
        "acyclic_native_control": "passed: 2 remaining DoF",
        "blender_preferences": "Use exactly this Project Root and Python executable",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        result = verify(args.project_root)
    except Exception as error:
        print(json.dumps({"ok": False, "error": str(error)}, indent=2), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
