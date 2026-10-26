# ruff: noqa: E402, F401, F403, F405
# Research-only direct native API probes; not imported by production.
"""Isolated slvs 3.2 feasibility probes; not production model/schema code.

Run with the pinned sidecar Python and --output /path/to/evidence.json.
Each native scenario has a fresh subprocess and ten-second limit.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import inspect
import json
import math
import os
import platform
import subprocess
import sys
from pathlib import Path

TAU = math.tau
HERE = Path(__file__).resolve().parent
REPO = Path(os.environ.get("MCAD_ROOT", str(HERE.parents[2]))).resolve()


def metrics(points, direction="ccw"):
    c, s, e = (points[key] for key in ("c", "s", "e"))
    a = (s[0] - c[0], s[1] - c[1])
    b = (e[0] - c[0], e[1] - c[1])
    ra, rb = math.hypot(*a), math.hypot(*b)
    if not ra or not rb:
        return {"start_radius": ra, "end_radius": rb, "sweep": None}
    cross = a[0] * b[1] - a[1] * b[0]
    dot = a[0] * b[0] + a[1] * b[1]
    principal = math.atan2(cross, dot)
    sweep = principal % TAU if direction == "ccw" else -((-principal) % TAU)
    return {
        "start_radius": ra,
        "end_radius": rb,
        "equal_radius_residual": abs(ra - rb),
        "chord": math.dist(s, e),
        "sweep": sweep,
        "sweep_degrees": math.degrees(sweep),
        "cross": cross,
        "dot": dot,
    }


def scenarios():
    quarter = {"c": (0, 0), "s": (5, 0), "e": (0, 5)}
    base = {"points": quarter}
    cases = {
        "points_without_arc": {**base, "omit_arc": True},
        "free_quarter": base,
        "free_quarter_cw": {**base, "direction": "cw"},
        "free_major": {"points": {**quarter, "e": (0, -5)}},
        "center_fixed": {**base, "fixed": ["c"]},
        "radius_only": {**base, "radius": 7},
        "center_fixed_radius": {**base, "fixed": ["c"], "radius": 7},
        "center_fixed_radius_cw": {**base, "fixed": ["c"], "radius": 7, "direction": "cw"},
        "all_points_fixed": {**base, "fixed": ["c", "s", "e"]},
        "all_points_fixed_conflicting_radius": {**base, "fixed": ["c", "s", "e"], "radius": 7},
        "unequal_radii_seed": {"points": {**quarter, "e": (0, 8)}},
        "line_shared_endpoint": {
            **base,
            "points": {**quarter, "z": (10, 0)},
            "fixed": ["c"],
            "radius": 7,
            "line": ("s", "z"),
        },
        "two_arcs_shared_endpoint": {
            **base,
            "points": {**quarter, "c2": (0, 10), "e2": (-5, 10)},
            "extra_arc": ("c2", "e", "e2"),
        },
        "distinct_endpoints_same_coordinates": {"points": {**quarter, "e": quarter["s"]}},
        "same_endpoint_handle": {**base, "same_endpoint_handle": True},
        "center_start_same_coordinates": {"points": {**quarter, "s": (0, 0)}},
        "all_zero": {"points": {key: (0, 0) for key in quarter}},
        "endpoint_coincidence_relation": {**base, "coincident_ends": True},
        "semicircle_free": {"points": {**quarter, "e": (-5, 0)}},
        "semicircle_center_fixed_radius": {
            "points": {**quarter, "e": (-5, 0)},
            "fixed": ["c"],
            "radius": 7,
        },
        "collinear_unequal_radii": {"points": {"c": (0, 0), "s": (3, 0), "e": (5, 0)}},
    }
    for side in (1, -1):
        for radius in (4, 3, 2):
            cases[f"fixed_chord_side_{side}_radius_{radius}"] = {
                "points": {"c": (0, side * 4), "s": (-3, 0), "e": (3, 0)},
                "fixed": ["s", "e"],
                "radius": radius,
            }
    for cy in (0, 1e-10, -1e-10):
        cases[f"fixed_chord_singular_seed_{cy}"] = {
            "points": {"c": (0, cy), "s": (-3, 0), "e": (3, 0)},
            "fixed": ["s", "e"],
            "radius": 5,
        }
    for angle in (1e-12, 1e-7, 1e-6, 1e-5, TAU - 1e-12, TAU - 1e-7):
        cases[f"sweep_{angle}"] = {
            "points": {**quarter, "e": (5 * math.cos(angle), 5 * math.sin(angle))}
        }
    # Existing fixed-point relations are the only endpoint constraints in this matrix.
    # A fixed center plus one fixed endpoint already fixes the radius geometrically.
    for kind in ("minor", "semicircle", "major"):
        for direction in ("ccw", "cw"):
            sign = 1 if direction == "ccw" else -1
            endpoint = {
                "minor": (0, sign * 5),
                "semicircle": (-5, 0),
                "major": (0, -sign * 5),
            }[kind]
            for fixed_name, fixed in (
                ("center", ["c"]),
                ("center_start", ["c", "s"]),
                ("all", ["c", "s", "e"]),
            ):
                for radius in (5, 7):
                    cases[f"matrix_{kind}_{direction}_{fixed_name}_r{radius}"] = {
                        "points": {**quarter, "e": endpoint},
                        "direction": direction,
                        "fixed": fixed,
                        "radius": radius,
                    }
    for radius in (1e-6, 1e-3, 1, 1e3, 5e5):
        cases[f"scale_center_fixed_r{radius}"] = {
            "points": {"c": (0, 0), "s": (radius, 0), "e": (0, radius)},
            "fixed": ["c"],
            "radius": radius * 1.5,
        }
    for kind in ("minor", "major"):
        for direction in ("ccw", "cw"):
            sign = (1 if direction == "ccw" else -1) * (1 if kind == "minor" else -1)
            cases[f"sector_{kind}_{direction}"] = {
                "points": {**quarter, "e": (0, sign * 5)},
                "direction": direction,
                "fixed": ["c"],
                "radius": 7,
                "radial_lines": True,
            }
    for kind, endpoint in (("quarter_complement", (0, 5)), ("semicircles", (-5, 0))):
        for mode in ("free", "radius", "center_radius", "unequal_seed"):
            points = {**quarter, "e": endpoint}
            if mode == "unequal_seed":
                points["e"] = (endpoint[0] * 1.6, endpoint[1] * 1.6)
            case = {"points": points, "extra_arc": ("c", "e", "s")}
            if mode in ("radius", "center_radius", "unequal_seed"):
                case["radius"] = 7
            if mode == "center_radius":
                case["fixed"] = ["c"]
            cases[f"two_arc_disk_{kind}_{mode}"] = case
    return cases


def native_case(case):
    import slvs

    slvs.clear_sketch()
    try:
        origin = slvs.add_point_3d(1, 0, 0, 0)
        normal = slvs.add_normal_3d(1, 1, 0, 0, 0)
        workplane = slvs.add_workplane(1, origin, normal)
        points = {
            key: slvs.add_point_2d(2, *case["points"][key], workplane)
            for key in sorted(case["points"])
        }
        direction = case.get("direction", "ccw")
        s, e = points["s"], points["e"]
        if case.get("same_endpoint_handle"):
            e = s
        if direction == "cw":
            s, e = e, s
        arc = None
        if not case.get("omit_arc"):
            arc = slvs.add_arc(2, normal, points["c"], s, e, workplane)
        extra_arc = None
        if "extra_arc" in case:
            extra_arc = slvs.add_arc(
                2, normal, *(points[key] for key in case["extra_arc"]), workplane
            )
        line = None
        if "line" in case:
            line = slvs.add_line_2d(2, *(points[key] for key in case["line"]), workplane)
        constraint_ids = {}
        radial_lines = {}
        if case.get("radial_lines"):
            for key, relation in (("s", slvs.horizontal), ("e", slvs.vertical)):
                radial = slvs.add_line_2d(2, points["c"], points[key], workplane)
                radial_lines[key] = radial
                constraint_ids[relation(2, radial, workplane)["h"]] = f"radial.{key}"
        for key in sorted(case.get("fixed", [])):
            target = slvs.add_point_2d(1, *case["points"][key], workplane)
            constraint_ids[slvs.coincident(2, points[key], target, workplane)["h"]] = f"fixed.{key}"
        if "radius" in case:
            assert arc is not None
            constraint_ids[slvs.diameter(2, arc, 2 * case["radius"])["h"]] = "radius"
        if case.get("coincident_ends"):
            constraint_ids[slvs.coincident(2, s, e, workplane)["h"]] = "coincident.ends"
        info, failed = slvs.solve_sketch(2, True)
        solved = {
            key: [slvs.get_param_value(point["param"][i]) for i in (0, 1)]
            for key, point in points.items()
        }
        return {
            "input": case,
            "native": info,
            "failed_constraints": [
                constraint_ids.get(handle, f"unknown:{handle}") for handle in failed
            ],
            "points": solved,
            "point_handles": {key: value["h"] for key, value in points.items()},
            "arc_entity": arc,
            "extra_arc_entity": extra_arc,
            "line_entity": line,
            "radial_lines": radial_lines,
            "before": metrics(case["points"], direction),
            "after": metrics(solved, direction),
        }
    finally:
        slvs.clear_sketch()


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument("--case")
    parser.add_argument("--output", default="evidence.json")
    args = parser.parse_args()
    cases = scenarios()
    if args.case:
        print(json.dumps(native_case(cases[args.case]), sort_keys=True, allow_nan=False))
        return
    import slvs

    evidence = {
        "python": sys.version,
        "platform": platform.platform(),
        "slvs_version": importlib.metadata.version("slvs"),
        "native_binary_sha256": hashlib.sha256(
            Path(slvs.solvespace.__file__).read_bytes()
        ).hexdigest(),
        "source_revision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO, text=True
        ).strip(),
        "source_hashes": {
            name: hashlib.sha256((REPO / "src/mechanical_cad" / name).read_bytes()).hexdigest()
            for name in ("sketch_model.py", "sketch_solver.py")
        },
        "api_signatures": {
            name: str(inspect.signature(getattr(slvs, name)))
            for name in ("add_arc", "diameter", "solve_sketch", "get_param_value")
        },
        "cases": {},
    }
    for name in cases:
        result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--case", name],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        if result.returncode:
            evidence["cases"][name] = {
                "process_returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        else:
            evidence["cases"][name] = json.loads(result.stdout)
        value = evidence["cases"][name]
        info, after = value.get("native", {}), value.get("after", {})
        print(
            f"{name}: status={info.get('result')} dof={info.get('dof')} "
            f"radius={after.get('start_radius')} sweep_deg={after.get('sweep_degrees')}"
        )
    checks = {}
    values = evidence["cases"]
    for name, dof in {
        "points_without_arc": 6,
        "free_quarter": 5,
        "free_quarter_cw": 5,
        "free_major": 5,
        "center_fixed": 3,
        "radius_only": 4,
        "center_fixed_radius": 2,
        "line_shared_endpoint": 4,
        "two_arcs_shared_endpoint": 8,
        "semicircle_free": 5,
    }.items():
        info = values[name]["native"]
        checks[f"dof.{name}"] = info["result"] == 0 and info["dof"] == dof
    checks["radius_target"] = math.isclose(
        values["center_fixed_radius"]["after"]["start_radius"], 7, abs_tol=1e-7
    )
    checks["implicit_equal_radii"] = (
        values["unequal_radii_seed"]["after"]["equal_radius_residual"] < 1e-7
    )
    shared = values["line_shared_endpoint"]
    checks["native_shared_endpoint"] = (
        shared["line_entity"]["point"][0]
        == shared["arc_entity"]["point"][1]
        == shared["point_handles"]["s"]
    )
    for side in (1, -1):
        solved = values[f"fixed_chord_side_{side}_radius_4"]
        checks[f"branch.side_{side}"] = solved["native"]["result"] == 0 and math.isclose(
            solved["points"]["c"][1], side * math.sqrt(7), abs_tol=1e-7
        )
        checks[f"impossible.side_{side}"] = values[f"fixed_chord_side_{side}_radius_2"]["native"][
            "result"
        ] not in (0, 4)
    for kind in ("minor", "semicircle", "major"):
        for direction in ("ccw", "cw"):
            target_sweep = {"minor": 90, "semicircle": 180, "major": 270}[kind]
            if direction == "cw":
                target_sweep *= -1
            for radius in (5, 7):
                prefix = f"matrix_{kind}_{direction}"
                solved = values[f"{prefix}_center_r{radius}"]
                checks[f"{prefix}_free_endpoints_r{radius}"] = (
                    solved["native"]["result"] == 0
                    and solved["native"]["dof"] == 2
                    and math.isclose(solved["after"]["start_radius"], radius, abs_tol=1e-7)
                    and math.isclose(solved["after"]["sweep_degrees"], target_sweep, abs_tol=1e-7)
                )
                for fixed_name, dof in (("center_start", 1), ("all", 0)):
                    info = values[f"{prefix}_{fixed_name}_r{radius}"]["native"]
                    checks[f"{prefix}_{fixed_name}_r{radius}"] = (
                        info["result"] == 4 and info["dof"] == dof
                        if radius == 5
                        else info["result"] not in (0, 4)
                    )
    for kind in ("minor", "major"):
        for direction in ("ccw", "cw"):
            name = f"sector_{kind}_{direction}"
            solved = values[name]
            target_sweep = (90 if kind == "minor" else 270) * (1 if direction == "ccw" else -1)
            checks[name] = (
                solved["native"]["result"] == 0
                and solved["native"]["dof"] == 0
                and math.isclose(solved["after"]["start_radius"], 7, abs_tol=1e-7)
                and math.isclose(solved["after"]["sweep_degrees"], target_sweep, abs_tol=1e-7)
                and solved["radial_lines"]["s"]["point"][:2]
                == [solved["point_handles"]["c"], solved["point_handles"]["s"]]
                and solved["radial_lines"]["e"]["point"][:2]
                == [solved["point_handles"]["c"], solved["point_handles"]["e"]]
            )
    for kind in ("quarter_complement", "semicircles"):
        for mode, dof in (("free", 5), ("radius", 4), ("center_radius", 2), ("unequal_seed", 4)):
            name = f"two_arc_disk_{kind}_{mode}"
            solved = values[name]
            checks[name] = (
                solved["native"]["result"] == 4
                and solved["native"]["dof"] == dof
                and solved["failed_constraints"] == []
                and solved["native"]["nbad"] == 0
                and solved["after"]["equal_radius_residual"] < 1e-7
                and (
                    mode == "free" or math.isclose(solved["after"]["start_radius"], 7, abs_tol=1e-7)
                )
            )
    evidence["checks"] = checks
    evidence["checks_passed"] = all(checks.values())
    Path(args.output).write_text(
        json.dumps(evidence, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    print(f"CHECKS: {sum(checks.values())}/{len(checks)} passed")
    if not evidence["checks_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    run()
