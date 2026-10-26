"""Bounded, subprocess-isolated equation-budget feasibility; not production code."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
import platform

try:
    import resource
except ImportError:  # Resource metrics/core limits are optional outside POSIX.
    resource = None
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
MAX_POINTS = 256
MAX_SCALARS = 512
MAX_CURVES = 256
MAX_CONSTRAINTS = 512
MAX_EQUATIONS = 1024


def cases():
    return {
        "below_cap_1023": {"points": 256, "arcs": 255, "fixed": 384},
        "cap_authored_1024": {"points": 256, "arcs": 0, "fixed": 512},
        "cap_arc_few_scalars_1024": {"points": 3, "arcs": 256, "fixed": 384},
        "cap_arc_max_scalars_1024": {"points": 256, "arcs": 256, "fixed": 384},
        "cap_arc_max_scalars_unsolved_1024": {
            "points": 256,
            "arcs": 256,
            "fixed": 384,
            "unsolved": True,
        },
        "cap_arc_with_authored_dedup_1024": {
            "points": 256,
            "arcs": 256,
            "fixed": 384,
            "unsolved": True,
            "dedup": True,
        },
        "cap_underconstrained_coincidence_1024": {
            "points": 256,
            "arcs": 256,
            "fixed": 0,
            "coincident": 384,
        },
        "cap_underconstrained_dedup_1024": {
            "points": 256,
            "arcs": 256,
            "fixed": 0,
            "coincident": 384,
            "dedup": True,
        },
        "cap_distinct_coincidence_cycles_1024": {
            "points": 256,
            "arcs": 256,
            "fixed": 0,
            "coincident": 384,
            "cycles": True,
            "diagnose": True,
        },
        "cap_plus_one_1025": {"points": 256, "arcs": 256, "fixed": 384, "radius": 5},
        "cap_plus_256_1280": {"points": 256, "arcs": 256, "fixed": 512},
        "complement_intrinsic_only": {"points": 3, "arcs": 2, "fixed": 0, "diagnose": True},
        "complement_center_radius": {
            "points": 3,
            "arcs": 2,
            "fixed": 1,
            "radius": 7,
            "diagnose": True,
        },
        "complement_authored_conflict": {
            "points": 3,
            "arcs": 2,
            "fixed": 3,
            "radius": 7,
            "diagnose": True,
        },
        "cap_arc_dedup_diagnostics": {
            "points": 256,
            "arcs": 256,
            "fixed": 384,
            "dedup": True,
            "diagnose": True,
        },
    }


def counts(spec):
    # Fixed is a 2D coincidence to a group-1 target. No circles/H/V are
    # needed for these ceiling probes; general weights are in the report.
    authored = spec["fixed"] + spec.get("coincident", 0) + int("radius" in spec)
    return {
        "points": spec["points"],
        "active_scalars": 2 * spec["points"],
        "total_curves": spec["arcs"],
        "authored_constraints": authored,
        "intrinsic_equations": spec["arcs"],
        "authored_equations_upper_bound": 2 * (spec["fixed"] + spec.get("coincident", 0))
        + int("radius" in spec),
        "equation_upper_bound": 2 * (spec["fixed"] + spec.get("coincident", 0))
        + int("radius" in spec)
        + spec["arcs"],
    }


def gate(count):
    limits = {
        "points": MAX_POINTS,
        "active_scalars": MAX_SCALARS,
        "total_curves": MAX_CURVES,
        "authored_constraints": MAX_CONSTRAINTS,
        "equation_upper_bound": MAX_EQUATIONS,
    }
    return [key for key, limit in limits.items() if count[key] > limit]


def native_case(spec):
    count = counts(spec)
    rejected = gate(count)
    if rejected:
        # Deliberately precedes importing slvs or touching its global state.
        return {
            "counts": count,
            "stage": "rejected_before_native",
            "exceeded": rejected,
            "native_called": False,
        }
    import slvs

    if resource is not None:
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    slvs.clear_sketch()
    started = time.perf_counter()
    try:
        origin = slvs.add_point_3d(1, 0, 0, 0)
        normal = slvs.add_normal_3d(1, 1, 0, 0, 0)
        wp = slvs.add_workplane(1, origin, normal)
        targets = [(0.0, 0.0), (5.0, 0.0), (0.0, 5.0)]
        targets += [(float(i % 16), float(10 + i // 16)) for i in range(spec["points"] - 3)]
        if spec.get("coincident"):
            targets = targets[:64] * 4 if spec.get("cycles") else targets[:128] * 2
        shift = 0.2 if spec.get("unsolved") else 0.0
        points = [slvs.add_point_2d(2, x + shift, y + shift, wp) for x, y in targets]
        arcs = [
            slvs.add_arc(2, normal, points[0], points[1 + i % 2], points[2 - i % 2], wp)
            for i in range(spec["arcs"])
        ]
        ids, seen = {}, set()
        compiled_fixed = 0
        for i in range(spec["fixed"]):
            index = i % len(points)
            if spec.get("dedup") and index in seen:
                continue
            seen.add(index)
            target = slvs.add_point_2d(1, *targets[index], wp)
            constraint = slvs.coincident(2, points[index], target, wp)
            ids[constraint["h"]] = f"fixed.{i}"
            compiled_fixed += 1
        coincidence_seen = set()
        compiled_coincident = 0
        if spec.get("cycles"):
            pairs = [
                (i + a * 64, i + b * 64)
                for i in range(64)
                for a in range(4)
                for b in range(a + 1, 4)
            ]
        else:
            pairs = [(i % 128, i % 128 + 128) for i in range(spec.get("coincident", 0))]
        for i, (left, right) in enumerate(pairs):
            if spec.get("dedup") and (left, right) in coincidence_seen:
                continue
            coincidence_seen.add((left, right))
            constraint = slvs.coincident(2, points[left], points[right], wp)
            ids[constraint["h"]] = f"coincident.{i}"
            compiled_coincident += 1
        if "radius" in spec:
            constraint = slvs.diameter(2, arcs[0], spec["radius"] * 2)
            ids[constraint["h"]] = "radius"
        compiled = time.perf_counter()
        raw = slvs.solve_sketch(2, spec.get("diagnose", False))
        solved_at = time.perf_counter()
        info, failed = raw if spec.get("diagnose") else (raw, [])
        positions = [[slvs.get_param_value(p["param"][i]) for i in (0, 1)] for p in points]
        maximum_fixed_error = max(
            (math.dist(positions[index], targets[index]) for index in seen), default=0.0
        )
        return {
            "counts": count,
            "stage": "native_completed",
            "native_called": True,
            "native": info,
            "diagnose": spec.get("diagnose", False),
            "failed_constraints": [ids.get(h, f"unknown:{h}") for h in failed],
            "compiled_authored_constraints": len(ids),
            "compiled_equation_upper_bound": 2 * (compiled_fixed + compiled_coincident)
            + int("radius" in spec)
            + len(arcs),
            "maximum_fixed_error": maximum_fixed_error,
            "first_three_points": positions[:3],
            "compile_seconds": compiled - started,
            "solve_seconds": solved_at - compiled,
            "elapsed_seconds": solved_at - started,
            "max_rss_native_units": (
                resource.getrusage(resource.RUSAGE_SELF).ru_maxrss if resource is not None else None
            ),
        }
    finally:
        slvs.clear_sketch()


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument("--case")
    parser.add_argument("--output", required=False, type=Path)
    args = parser.parse_args()
    if importlib.metadata.version("slvs") != "3.2":
        raise SystemExit("This evidence requires exactly slvs==3.2")
    specs = cases()
    if args.case:
        print(json.dumps(native_case(specs[args.case]), sort_keys=True, allow_nan=False))
        return
    if args.output is None:
        parser.error("--output is required for a full run")
    evidence = {
        "python": sys.version,
        "platform": platform.platform(),
        "slvs_version": importlib.metadata.version("slvs"),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "cases": {},
        "scope": "Historical raw-native arc/resource probes; not a 0.5.1 capability or correctness guarantee",
    }
    for name, spec in specs.items():
        started = time.perf_counter()
        try:
            result = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), "--case", name],
                text=True,
                capture_output=True,
                timeout=20,
                check=False,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )
            value = (
                json.loads(result.stdout)
                if result.returncode == 0
                else {
                    "stage": "process_error",
                    "returncode": result.returncode,
                    "stderr": result.stderr,
                    "stdout": result.stdout,
                }
            )
        except subprocess.TimeoutExpired:
            value = {"stage": "timeout", "timeout_seconds": 20}
        value["input"] = spec
        value["process_wall_seconds"] = time.perf_counter() - started
        evidence["cases"][name] = value
        print(
            name,
            value["stage"],
            value.get("native"),
            f"{value['process_wall_seconds']:.3f}s",
            flush=True,
        )
    values = evidence["cases"]
    checks = {}
    for name in specs:
        value = values[name]
        if name in ("cap_plus_one_1025", "cap_plus_256_1280"):
            checks[name] = value.get("native_called") is False and value.get("exceeded") == [
                "equation_upper_bound"
            ]
        elif name == "complement_authored_conflict":
            checks[name] = value.get("native", {}).get("result") == 1 and value.get(
                "failed_constraints"
            ) == ["radius"]
        else:
            checks[name] = (
                value.get("native", {}).get("result") in (0, 4)
                and value.get("maximum_fixed_error", 1) <= 1e-7
            )
    intrinsic = values["complement_intrinsic_only"]
    checks["intrinsic_no_authored_failure"] = (
        intrinsic.get("native", {}).get("result") == 4
        and intrinsic.get("failed_constraints") == []
        and intrinsic.get("native", {}).get("nbad") == 0
    )
    checks["dedup_preserves_underconstrained_dof"] = (
        values["cap_underconstrained_dedup_1024"].get("native", {}).get("dof") == 255
    )
    checks["known_coincidence_cycle_dof_defect_reproduced"] = (
        values["cap_distinct_coincidence_cycles_1024"].get("native", {}).get("dof") == 0
    )
    evidence["known_defects"] = {
        "distinct_coincidence_cycles": {
            "case": "cap_distinct_coincidence_cycles_1024",
            "mathematical_dof": 127,
            "native_dof": values["cap_distinct_coincidence_cycles_1024"]
            .get("native", {})
            .get("dof"),
            "explanation": "64 free coincident point groups contribute 128 scalars; all arcs share one independent radial equality. Exact authored-equation dedup does not eliminate the distinct cycles.",
        },
    }
    evidence["checks"] = checks
    evidence["checks_passed"] = all(checks.values())
    Path(args.output).write_text(json.dumps(evidence, sort_keys=True, indent=2) + "\n")
    print(f"CHECKS: {sum(checks.values())}/{len(checks)} passed")
    if not evidence["checks_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    run()
