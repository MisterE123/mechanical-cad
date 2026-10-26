"""Standalone slvs==3.2 defect reproduction, with no Mechanical CAD dependency.

Passing confirms the recorded native defect and controls, not solver correctness.
SPDX-License-Identifier: GPL-3.0-or-later
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
from pathlib import Path


def cases():
    output = {}
    for kind in ("coincident", "horizontal", "vertical"):
        seeds = [[0.0, 0.0], [0.0, 0.0], [0.0, 0.0]]
        expected = 2
        wrong = 0
        if kind == "horizontal":
            seeds = [[0.0, 0.0], [5.0, 0.0], [10.0, 0.0]]
            expected, wrong = 4, 3
        elif kind == "vertical":
            seeds = [[0.0, 0.0], [0.0, 5.0], [0.0, 10.0]]
            expected, wrong = 4, 3
        for cycle in (False, True):
            name = f"{kind}_{'cycle' if cycle else 'tree'}"
            output[name] = {
                "kind": kind,
                "seeds": seeds,
                "pairs": [[0, 1], [0, 2], [1, 2]] if cycle else [[0, 1], [1, 2]],
                "mathematical_dof": expected,
                "expected_native_status": 0,
                "expected_native_dof": wrong if cycle else expected,
            }
    output["horizontal_parallel_lines"] = {
        "kind": "horizontal",
        "seeds": [[0.0, 0.0], [5.0, 0.0]],
        "pairs": [[0, 1], [1, 0]],
        "mathematical_dof": 3,
        "expected_native_status": 0,
        "expected_native_dof": 2,
    }
    output["fixed_same_target_control"] = {
        "kind": "coincident",
        "seeds": [[0.0, 0.0], [0.0, 0.0]],
        "pairs": [],
        "fixed": [[0, 0.0, 0.0], [1, 0.0, 0.0]],
        "mathematical_dof": 0,
        "expected_native_status": 0,
        "expected_native_dof": 0,
    }
    return output


def native_case(spec, diagnose):
    import slvs

    slvs.clear_sketch()
    try:
        origin = slvs.add_point_3d(1, 0, 0, 0)
        normal = slvs.add_normal_3d(1, 1, 0, 0, 0)
        workplane = slvs.add_workplane(1, origin, normal)
        points = [slvs.add_point_2d(2, *seed, workplane) for seed in spec["seeds"]]
        for left, right in spec["pairs"]:
            if spec["kind"] == "coincident":
                slvs.coincident(2, points[left], points[right], workplane)
            else:
                line = slvs.add_line_2d(2, points[left], points[right], workplane)
                getattr(slvs, spec["kind"])(2, line, workplane)
        for index, u, v in spec.get("fixed", []):
            target = slvs.add_point_2d(1, u, v, workplane)
            slvs.coincident(2, points[index], target, workplane)
        raw = slvs.solve_sketch(2, diagnose)
        info, failed = raw if diagnose else (raw, [])
        positions = [
            [slvs.get_param_value(point["param"][axis]) for axis in (0, 1)] for point in points
        ]
        residuals = [0.0]
        for left, right in spec["pairs"]:
            axes = (
                (0, 1)
                if spec["kind"] == "coincident"
                else (1,)
                if spec["kind"] == "horizontal"
                else (0,)
            )
            residuals.extend(abs(positions[left][axis] - positions[right][axis]) for axis in axes)
        for index, u, v in spec.get("fixed", []):
            residuals.extend((abs(positions[index][0] - u), abs(positions[index][1] - v)))
        return {
            "native": info,
            "failed_handles": failed,
            "positions": positions,
            "max_coordinate_residual": max(residuals),
            "input": spec,
            "diagnose": diagnose,
            "reproduced_recorded_observation": (
                info["result"] == spec["expected_native_status"]
                and info["dof"] == spec["expected_native_dof"]
                and max(residuals) == 0.0
            ),
        }
    finally:
        slvs.clear_sketch()


def runtime_identity():
    import slvs

    native = Path(slvs.__file__).parent / "solvespace.so"
    return {
        "slvs_version": importlib.metadata.version("slvs"),
        "python": sys.version,
        "platform": platform.platform(),
        "native_binary_sha256": (
            hashlib.sha256(native.read_bytes()).hexdigest() if native.exists() else None
        ),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=tuple(cases()))
    parser.add_argument("--diagnose", choices=("true", "false"), default="true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if importlib.metadata.version("slvs") != "3.2":
        raise SystemExit("This evidence requires exactly slvs==3.2")
    if args.case:
        print(json.dumps(native_case(cases()[args.case], args.diagnose == "true"), allow_nan=False))
        return
    if args.output is None:
        parser.error("--output is required for a full run")
    evidence = {"runtime": runtime_identity(), "cases": {}}
    for name in cases():
        for diagnose in ("true", "false"):
            result = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "--case",
                    name,
                    "--diagnose",
                    diagnose,
                ],
                capture_output=True,
                text=True,
                timeout=20,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                check=True,
            )
            value = json.loads(result.stdout)
            evidence["cases"][f"{name}:diagnose={diagnose}"] = value
            print(name, diagnose, value["native"], flush=True)
    evidence["recorded_observations_reproduced"] = all(
        case["reproduced_recorded_observation"] for case in evidence["cases"].values()
    )
    args.output.write_text(json.dumps(evidence, sort_keys=True, indent=2, allow_nan=False) + "\n")
    if not evidence["recorded_observations_reproduced"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
