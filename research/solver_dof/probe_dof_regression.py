"""Read-only real-adapter DoF regression probes, isolated by source/process.

These tests intentionally record known incorrect baseline results; a passing
probe is evidence that the defect was reproduced, not a solver qualification.
No production source or release artifact is changed.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import io
import itertools
import json
import os
import platform
import subprocess
import sys
import tarfile
import types
from dataclasses import replace
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def fixtures():
    from mechanical_cad.sketch_solver import Circle, Constraint, Line, Point, Sketch

    def coincidence(n=3, *, tree=False, seed=0, fixed=None, circle=False):
        points = tuple(Point(f"p{i}", seed * i, seed * i) for i in range(n))
        pairs = (
            [(i, i + 1) for i in range(n - 1)]
            if tree
            else list(itertools.combinations(range(n), 2))
        )
        constraints = tuple(
            Constraint(f"join{i}{j}", "coincident", (f"p{i}", f"p{j}")) for i, j in pairs
        )
        if fixed is not None:
            constraints += (Constraint("anchor", "fixed", ("p0",), target=fixed),)
        return Sketch(
            "probe",
            points,
            (),
            constraints,
            schema_version=2 if circle else 1,
            circles=(Circle("circle", "p0", 5),) if circle else (),
        )

    def axes(kind="horizontal", *, tree=False, seed=0, fixed=None, parallel=False):
        points = tuple(
            Point(f"p{i}", i * 5, seed * i)
            if kind == "horizontal"
            else Point(f"p{i}", seed * i, i * 5)
            for i in range(3)
        )
        pairs = [(0, 1), (1, 2)] if tree else [(0, 1), (0, 2), (1, 2)]
        if parallel:
            pairs = [(0, 1), (1, 0)]
            points = points[:2]
        lines = tuple(Line(f"l{i}", f"p{a}", f"p{b}") for i, (a, b) in enumerate(pairs))
        constraints = tuple(
            Constraint(f"axis{i}", kind, (line.id,)) for i, line in enumerate(lines)
        )
        if fixed is not None:
            constraints += (Constraint("anchor", "fixed", ("p0",), target=fixed),)
        return Sketch("probe", points, lines, constraints)

    cases = {}

    def add(name, sketch, dof, *, consistent=True):
        cases[name] = {"sketch": sketch, "expected_dof": dof, "consistent": consistent}

    add("coincidence_pair_control", coincidence(2), 2)
    add("coincidence_tree_control", coincidence(tree=True), 2)
    add("coincidence_triangle_minimal", coincidence(), 2)
    add("coincidence_triangle_offset_seeds", coincidence(seed=0.2), 2)
    add("coincidence_triangle_anchored", coincidence(fixed=(0, 0)), 0)
    add("coincidence_triangle_offset_seeds_anchored", coincidence(seed=0.2, fixed=(0, 0)), 0)
    add(
        "coincidence_tree_offset_seeds_anchored_control",
        coincidence(tree=True, seed=0.2, fixed=(0, 0)),
        0,
    )
    for n in (4, 5, 8, 16):
        add(f"coincidence_complete_{n}", coincidence(n), 2)
    base = coincidence(tree=True)
    add(
        "coincidence_exact_duplicate_control",
        replace(
            base,
            constraints=base.constraints + (Constraint("duplicate", "coincident", ("p1", "p0")),),
        ),
        2,
    )
    for kind in ("horizontal", "vertical"):
        add(f"{kind}_tree_control", axes(kind, tree=True), 4)
        add(f"{kind}_triangle", axes(kind), 4)
        add(f"{kind}_triangle_offset_seeds", axes(kind, seed=0.2), 4)
        add(f"{kind}_triangle_anchored", axes(kind, fixed=(0, 0)), 2)
        add(f"{kind}_parallel_lines", axes(kind, parallel=True), 3)
    for fixed in (False, True):
        for offset in (False, True):
            add(
                f"circle_coincidence_cycle_fixed_{fixed}_offset_{offset}",
                coincidence(
                    seed=0.2 if offset else 0, fixed=(0, 0) if fixed else None, circle=True
                ),
                1 if fixed else 3,
            )
    # Repeated fixed targets never connect two active native parameters.
    fixed_base = coincidence(2)
    add(
        "coincidence_pair_both_fixed_control",
        replace(
            fixed_base,
            constraints=fixed_base.constraints
            + tuple(Constraint(f"fixed{i}", "fixed", (f"p{i}",), target=(0, 0)) for i in range(2)),
        ),
        0,
    )
    add(
        "fixed_only_same_target_control",
        Sketch(
            "probe",
            (Point("p0", 0, 0), Point("p1", 0, 0)),
            (),
            tuple(Constraint(f"fixed{i}", "fixed", (f"p{i}",), target=(0, 0)) for i in range(2)),
        ),
        0,
    )
    add(
        "fixed_only_incompatible_control",
        Sketch(
            "probe",
            (Point("p0", 0, 0),),
            (),
            (
                Constraint("fixed0", "fixed", ("p0",), target=(0, 0)),
                Constraint("fixed1", "fixed", ("p0",), target=(1, 0)),
            ),
        ),
        None,
        consistent=False,
    )
    # Distinct constraints can be redundant with a valid positive native DoF.
    add(
        "native_redundant_distances_correct_control",
        Sketch(
            "probe",
            (Point("p0", 0, 0), Point("p1", 5, 0), Point("p2", 5, 0)),
            (),
            (
                Constraint("join", "coincident", ("p1", "p2")),
                Constraint("d1", "distance", ("p0", "p1"), 5),
                Constraint("d2", "distance", ("p0", "p2"), 5),
            ),
        ),
        3,
    )
    # A scalar equality cycle may mix two relation families.
    mixed = axes(tree=True)
    add(
        "mixed_horizontal_coincidence_cycle",
        replace(
            mixed,
            constraints=mixed.constraints + (Constraint("join02", "coincident", ("p0", "p2")),),
        ),
        3,
    )
    return cases


def scalar_cycles(sketch):
    """Research-only preflight candidate, never delete or compile fewer relations."""
    from mechanical_cad.sketch_solver import _unique_relations

    unique, _ = _unique_relations(sketch)
    parents = {}
    lines = {line.id: line for line in sketch.lines}
    cycles = []

    def root(node):
        parents.setdefault(node, node)
        while parents[node] != node:
            node = parents[node]
        return node

    for c in unique:
        if c.kind == "coincident":
            a, b = c.refs
            axes = ("u", "v")
        elif c.kind in ("horizontal", "vertical"):
            line = lines[c.refs[0]]
            a, b = line.start, line.end
            axes = ("v",) if c.kind == "horizontal" else ("u",)
        else:
            continue
        for axis in axes:
            left, right = root((a, axis)), root((b, axis))
            if left == right:
                cycles.append({"constraint": c.id, "axis": axis})
            else:
                parents[left] = right
    return cycles


def adapter_case(name, diagnose):
    import slvs

    import mechanical_cad.sketch_solver as ss

    item = fixtures()[name]
    sketch = item["sketch"]
    original = sketch.to_json()
    native = []
    native_solve = slvs.solve_sketch

    def capture(*args, **kwargs):
        result = native_solve(*args, **kwargs)
        native.append(result)
        return result

    slvs.solve_sketch = capture
    try:
        result = ss.solve(sketch, diagnose=diagnose)
        report = {
            "status": result.status.name,
            "success": result.success,
            "remaining_dof": result.remaining_dof,
            "failed_constraints": result.failed_constraints,
            "redundant_constraints": result.redundant_constraints,
            "max_residual": result.max_residual,
            "persistent_constraints_preserved": result.sketch.constraints == sketch.constraints,
            "solved": result.sketch.to_dict(),
        }
    except Exception as exc:
        report = {
            "exception": type(exc).__name__,
            "code": getattr(exc, "code", None),
            "message": str(exc),
        }
    finally:
        slvs.solve_sketch = native_solve
    return {
        "adapter": ss.__file__,
        "diagnose": diagnose,
        "fixture": sketch.to_dict(),
        "expected_dof": item["expected_dof"],
        "mathematically_consistent": item["consistent"],
        "native": native,
        "report": report,
        "original_unchanged": sketch.to_json() == original,
        "scalar_equality_cycles": scalar_cycles(sketch),
        "successful_wrong_dof": report.get("success", False)
        and report.get("remaining_dof") != item["expected_dof"],
    }


def ui_witness(source, addon_source=None):
    """Exercise actual UI data/picker seams, without claiming real GUI review."""
    import importlib

    from mechanical_cad.sidecar import process_request

    addon_source = (addon_source or source).resolve()
    package = types.ModuleType("dof_ui_witness")
    package.__path__ = [str(addon_source / "blender_addon/mechanical_cad_blender")]
    sys.modules[package.__name__] = package

    def load(name):
        return importlib.import_module(package.__name__ + "." + name)

    draft_module = load("general_sketch_draft")
    authoring = load("general_authoring")
    store = load("general_authoring_store")
    geometry = load("general_view_geometry")
    selection = load("constraint_selection")
    base = json.dumps(
        {
            "schema_version": 1,
            "id": "ui_probe",
            "name": "UI probe",
            "units": "mm",
            "parameters": {},
            "features": [],
            "active_feature": None,
        }
    )
    draft = draft_module.GeneralSketchDraft(base)
    p0, p1, line0 = draft.execute(
        draft_module.AddLine(draft_module.PointSeed(0, 0), draft_module.PointSeed(40, 20))
    ).entity_ids
    p2, line1 = draft.execute(
        draft_module.AddLine(draft_module.PointRef(p1), draft_module.PointSeed(80, 5))
    ).entity_ids
    (line2,) = draft.execute(
        draft_module.AddLine(draft_module.PointRef(p2), draft_module.PointRef(p0))
    ).entity_ids
    for line in (line0, line1):
        assert (
            selection.selection_contract(draft.sketch, [{"kind": "line", "id": line}])
            .action("horizontal")
            .state
            == "eligible"
        )
        draft.execute(draft_module.AddRelation("horizontal", (line,)))
    request = draft.solve_request()
    before = process_request(request)
    accepted_before = draft.record_validated_solution(request, before, draft.revision)
    state = authoring.GeneralSketchAuthoringState(draft)
    restored = store.restore(store.dumps(state), base)
    resume_unverified = not restored.command_draft.has_current_solution
    authored = geometry.build_geometry(restored.command_draft.sketch, source="authored")
    # Resume deliberately revokes solved display and shows these unchanged seeds.
    pick = geometry.pick_geometry(authored, (160, 10), lambda point: (point[0] * 4, point[1] * 4))
    assert pick.unique is not None and pick.unique.identifier == line2
    restored.select((("line", pick.unique.identifier),))
    action = selection.selection_contract(restored.command_draft.sketch, restored.selection).action(
        "horizontal"
    )
    assert action.state == "eligible"
    restored.command_draft.execute(draft_module.AddRelation("horizontal", action.refs))
    request = restored.command_draft.solve_request()
    after = process_request(request)
    accepted_after = restored.command_draft.record_validated_solution(
        request, after, restored.revision
    )
    loaded_modules = {}
    for name, module in tuple(sys.modules.items()):
        filename = getattr(module, "__file__", None)
        if filename and name.startswith(("dof_ui_witness.", "mechanical_cad.")):
            path = Path(filename)
            if path.is_file():
                loaded_modules[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "loaded_modules_sha256": loaded_modules,
        "method": "actual authoring, persistence, picker, selection, sidecar and strict bridge seams; no native Blender GUI",
        "addon_source_path_at_capture": str(addon_source),
        "sidecar_source_path_at_capture": str(source),
        "initial_authored_points": draft.sketch["points"],
        "restored_authored_points": list(authored.points.items()),
        "before_cycle": {"bridge_accepted": accepted_before, "response": before},
        "after_cycle": {"bridge_accepted": accepted_after, "response": after},
        "resume_starts_without_current_solution": resume_unverified,
        "authored_constraint_count_after": len(restored.command_draft.sketch["constraints"]),
        "current_solution_after": restored.command_draft.has_current_solution,
        "pick": {"status": pick.status, "line": pick.unique.identifier},
        "action": {"state": action.state, "refs": action.refs},
        "expected_dof_before_and_after": 4,
    }


def source_identity(source, reference_revision=None):
    """Verify a restored source against local Git objects without changing it."""
    paths = ("src/mechanical_cad/sketch_model.py", "src/mechanical_cad/sketch_solver.py")
    identity = {
        "path_at_capture": str(source),
        "sha256": {
            name: hashlib.sha256((source / name).read_bytes()).hexdigest() for name in paths
        },
    }
    if reference_revision:
        revision = subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", reference_revision], text=True
        ).strip()
        archive = subprocess.check_output(
            ["git", "-C", str(ROOT), "archive", revision, "src", "blender_addon"]
        )
        mismatches, count = [], 0
        with tarfile.open(fileobj=io.BytesIO(archive)) as files:
            for member in files:
                if not member.isfile():
                    continue
                count += 1
                actual = source / member.name
                expected = files.extractfile(member).read()
                if not actual.is_file() or actual.read_bytes() != expected:
                    mismatches.append(member.name)
        identity.update(
            reference_revision=revision,
            compared_files=count,
            source_tree_matches_reference=not mismatches,
            mismatches=mismatches,
        )
        if mismatches:
            raise RuntimeError(f"Source differs from {revision}: {mismatches}")
    return identity


def verify(evidence, expectation):
    checks = {}
    for name, case in evidence["cases"].items():
        if "process_error" in case:
            checks[name] = False
            continue
        report = case["report"]
        cycles = case["scalar_equality_cycles"]
        if expectation == "guarded" and cycles:
            valid = report.get("code") == "solver_dof_indeterminate" and case["native"] == []
        elif not cycles:
            valid = (
                report.get("success") == case["mathematically_consistent"]
                and report.get("remaining_dof") == case["expected_dof"]
            )
        else:
            # Baseline cyclic outcomes are recorded, not generally certified.
            valid = bool(case["native"]) and "exception" not in report
        checks[name] = valid and case["original_unchanged"]
    witness = evidence["ui_witness"]
    checks["ui_resume_and_pick"] = (
        witness.get("resume_starts_without_current_solution") is True
        and witness.get("pick", {}).get("status") == "unique"
        and witness.get("action", {}).get("state") == "eligible"
        and witness.get("before_cycle", {}).get("bridge_accepted") is True
        and witness.get("before_cycle", {})
        .get("response", {})
        .get("result", {})
        .get("sketch", {})
        .get("remaining_dof")
        == 4
    )
    if expectation == "baseline":
        for name, expected, observed in (
            ("coincidence_triangle_minimal", 2, 0),
            ("horizontal_triangle", 4, 3),
        ):
            for diagnose in ("true", "false"):
                value = evidence["cases"][f"{name}:diagnose={diagnose}"]
                checks[f"known_defect:{name}:{diagnose}"] = (
                    value["expected_dof"] == expected
                    and value["report"].get("status") == "OKAY"
                    and value["report"].get("remaining_dof") == observed
                    and value["report"].get("max_residual") == 0.0
                )
        checks["ui_baseline_defect_reproduced"] = (
            witness.get("after_cycle", {}).get("bridge_accepted") is True
            and witness.get("after_cycle", {})
            .get("response", {})
            .get("result", {})
            .get("sketch", {})
            .get("remaining_dof")
            == 3
        )
    else:
        checks["ui_guarded_failure"] = (
            witness.get("after_cycle", {}).get("bridge_accepted") is False
            and witness.get("after_cycle", {}).get("response", {}).get("error", {}).get("code")
            == "solver_dof_indeterminate"
            and witness.get("current_solution_after") is False
            and witness.get("authored_constraint_count_after") == 3
        )
    return checks


def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case")
    parser.add_argument("--diagnose", choices=("true", "false"), default="true")
    parser.add_argument(
        "--output",
        type=Path,
        help="Output JSON for a full run; required unless running one case/UI witness",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=ROOT,
        help="Explicit Mechanical CAD source root; defaults to this checkout",
    )
    parser.add_argument(
        "--reference-revision",
        help="Verify all selected source/add-on files against a local Git revision",
    )
    parser.add_argument("--expect", choices=("baseline", "guarded"), default="guarded")
    parser.add_argument(
        "--addon-source",
        type=Path,
        help="Optional separate add-on root for a deliberate sidecar mismatch witness",
    )
    parser.add_argument("--ui-witness", action="store_true")
    args = parser.parse_args()
    source = args.source.resolve()
    sys.path.insert(0, str(source / "src"))
    if importlib.metadata.version("slvs") != "3.2":
        raise SystemExit("This evidence requires exactly slvs==3.2")
    if args.ui_witness:
        print(json.dumps(ui_witness(source, args.addon_source), allow_nan=False))
        return
    if args.case:
        print(json.dumps(adapter_case(args.case, args.diagnose == "true"), allow_nan=False))
        return
    if args.output is None:
        parser.error("--output is required for a full run")
    evidence = {
        "python": sys.version,
        "platform": platform.platform(),
        "slvs_version": importlib.metadata.version("slvs"),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "expectation": args.expect,
        "source": source_identity(source, args.reference_revision),
        "cases": {},
    }
    for name in fixtures():
        for diagnose in ("true", "false"):
            command = [
                sys.executable,
                str(Path(__file__).resolve()),
                "--case",
                name,
                "--diagnose",
                diagnose,
                "--source",
                str(source),
            ]
            child = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=20,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )
            value = (
                {"process_error": child.returncode, "stderr": child.stderr}
                if child.returncode
                else json.loads(child.stdout)
            )
            key = name + ":diagnose=" + diagnose
            evidence["cases"][key] = value
            report = value.get("report", {})
            print(
                key,
                report.get("status", report.get("code")),
                report.get("remaining_dof"),
                flush=True,
            )
    child = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--ui-witness", "--source", str(source)]
        + (["--addon-source", str(args.addon_source.resolve())] if args.addon_source else []),
        capture_output=True,
        text=True,
        timeout=20,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    evidence["ui_witness"] = (
        json.loads(child.stdout)
        if child.returncode == 0
        else {"stderr": child.stderr, "process_error": child.returncode}
    )
    evidence["checks"] = verify(evidence, args.expect)
    evidence["checks_passed"] = all(evidence["checks"].values())
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print("WROTE", args.output, "checks_passed=", evidence["checks_passed"])
    if not evidence["checks_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    run()
