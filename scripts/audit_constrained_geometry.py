#!/usr/bin/env python3
"""Bounded, deterministic independent checks for the constrained-sketch pipeline.

Run explicitly with the project's sidecar Python; this is not pytest-collected.
Expected areas, world coordinates and encoded STL volumes are computed without
using the production geometry helpers. Native OCCT may print export diagnostics.
Use --output for a clean JSON evidence file. Nothing in the source tree is edited.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import struct
import sys
from collections import Counter
from dataclasses import replace
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory

from mechanical_cad.actions import run_geometry_action
from mechanical_cad.engine import regenerate
from mechanical_cad.expressions import resolve_parameters
from mechanical_cad.kernel_ocp import OCPKernel
from mechanical_cad.model import Document, Feature, load_document
from mechanical_cad.profile_region import closed_profile
from mechanical_cad.sketch_model import (
    Constraint,
    Line,
    Plane,
    Point,
    Sketch,
    SketchDefinition,
    resolve_sketch,
)
from mechanical_cad.sketch_solver import Status, solve

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples/constrained_plate.mcad.json"
# SHA-256 of 500 newline-separated legacy document hashes, plus trailing newline.
# Independently obtained from model.py at commit e987f14 using schema_cases().
LEGACY_HASH_DIGEST = "0f685a275c2b87473f9d31572896fb3a0b8c57b12eba20e417c0313364655b15"


def require(condition, message):
    """Remain effective even if Python is invoked with optimization enabled."""
    if not condition:
        raise AssertionError(message)


def close(actual, expected, label, *, relative=1e-7, absolute=1e-10):
    require(
        math.isclose(actual, expected, rel_tol=relative, abs_tol=absolute),
        f"{label}: {actual!r} != {expected!r}",
    )


def rotate(vector, quaternion):
    """Independent quaternion multiplication, rather than kernel basis formulas."""

    def multiply(a, b):
        w, x, y, z = a
        bw, bx, by, bz = b
        return (
            w * bw - x * bx - y * by - z * bz,
            w * bx + x * bw + y * bz - z * by,
            w * by - x * bz + y * bw + z * bx,
            w * bz + x * by - y * bx + z * bw,
        )

    w, x, y, z = quaternion
    return multiply(multiply(quaternion, (0, *vector)), (w, -x, -y, -z))[1:]


def random_quaternion(rng):
    values = [rng.gauss(0, 1) for _ in range(4)]
    norm = math.sqrt(sum(value * value for value in values))
    return tuple(value / norm for value in values)


def audit_polygons():
    rng = random.Random(613817)
    for case in range(180):
        count = rng.randint(3, 14)
        points = []
        for index in range(count):
            radius = rng.uniform(5, 25)
            angle = index * 2 * math.pi / count
            points.append((math.cos(angle) * radius, math.sin(angle) * radius))
        area = (
            sum(
                a[0] * b[1] - b[0] * a[1]
                for a, b in zip(points, points[1:] + points[:1], strict=True)
            )
            / 2
        )
        quaternion = random_quaternion(rng)
        origin = tuple(rng.uniform(-300, 300) for _ in range(3))
        length = rng.uniform(0.01, 30)
        records = [Point(f"p{index:03}", *point) for index, point in enumerate(points)]
        lines = [
            Line(f"e{index:03}", f"p{index:03}", f"p{(index + 1) % count:03}")
            for index in range(count)
        ]
        if case % 3 == 0:
            lines = [replace(line, start=line.end, end=line.start) for line in reversed(lines)]
        rng.shuffle(records)
        rng.shuffle(lines)
        sketch = Sketch("s", tuple(records), tuple(lines), (), Plane(origin, quaternion))
        report = solve(sketch)
        require(report.success, f"Polygon {case}: {report.status}")
        require(report.remaining_dof == 2 * count, f"Polygon {case}: unexpected DoF")
        region = closed_profile(report.sketch)
        kernel = OCPKernel()
        profile = kernel.polygon(
            region.points, region.edge_ids, origin=origin, quaternion=quaternion
        )
        solid = kernel.extrude(profile, length)
        topology = kernel.topology(solid, "pad", "extrude", {})
        close(kernel.inspect(solid)["volume"], area * length, f"Polygon {case} B-rep volume")
        mesh = kernel.manufacturing_check(solid)["mesh"]
        close(mesh["signed_volume"], area * length, f"Polygon {case} mesh volume")
        require(len(topology) == count + 2, f"Polygon {case}: face count")
        for face in topology:
            require(face["provenance"]["semantic_status"] == "stable", "Unstable provenance")
            if not face["role"].startswith("side.line.e"):
                continue
            index = int(face["role"].removeprefix("side.line.e"))
            a, b = points[index], points[(index + 1) % count]
            local = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, length / 2)
            expected = tuple(
                offset + value
                for offset, value in zip(origin, rotate(local, quaternion), strict=True)
            )
            require(
                math.dist(expected, face["signature"]["centroid"]) < 1e-8,
                f"Polygon {case}: wrong stable edge-to-face assignment for {face['role']}",
            )
    return {"seed": 613817, "cases": 180, "failures": 0}


def schema_cases():
    rng = random.Random(1729)
    for index in range(500):
        width = rng.choice([1, 1.0, -0.0, 40.123, rng.uniform(0.001, 1e6), "length / 2"])
        yield {
            "schema_version": 1,
            "id": f"doc{index}",
            "name": "Doc ∑ A",
            "units": "mm",
            "parameters": {"length": rng.choice([10, 10.0, 0.01, 1000000])},
            "features": [
                {
                    "id": "s",
                    "kind": "sketch_rectangle",
                    "params": {"width": width, "height": "length"},
                },
                {
                    "id": "e",
                    "kind": "extrude",
                    "params": {"length": rng.choice([1, 1.0, "length / 3"])},
                    "inputs": {"profile": "s"},
                },
            ],
            "active_feature": "e",
        }


def audit_schema():
    hashes = []
    for raw in schema_cases():
        document = Document.from_dict(raw)
        before = document.to_json()
        hashes.append(document.content_hash)
        migrated = document.migrate_to_v2()
        expected = document.to_dict()
        expected["schema_version"] = 2
        require(migrated.to_dict() == expected, "Migration changed more than schema version")
        require(document.to_json() == before, "Migration mutated the previous snapshot")
        require(
            Document.from_json(migrated.to_json()).content_hash == migrated.content_hash,
            "Schema-2 roundtrip changed hash",
        )
    digest = hashlib.sha256(("\n".join(hashes) + "\n").encode()).hexdigest()
    require(digest == LEGACY_HASH_DIGEST, f"Legacy hash aggregate changed: {digest}")
    return {"seed": 1729, "cases": 500, "legacy_commit": "e987f14", "digest": digest}


def triangle(base, x, y, seeds):
    return Sketch(
        "triangle",
        tuple(Point(f"p{index}", *point) for index, point in enumerate(seeds)),
        (Line("base", "p0", "p1"), Line("s1", "p1", "p2"), Line("s2", "p2", "p0")),
        (
            Constraint("anchor", "fixed", ("p0",), target=(0.0, 0.0)),
            Constraint("hor", "horizontal", ("base",)),
            Constraint("d0", "distance", ("p0", "p1"), base),
            Constraint("d1", "distance", ("p0", "p2"), math.hypot(x, y)),
            Constraint("d2", "distance", ("p1", "p2"), math.hypot(x - base, y)),
        ),
    )


def audit_branches():
    rng = random.Random(6138)
    outcomes = Counter()
    successful_pairs = 0
    failures = []
    for case in range(1500):
        base = 10 ** rng.uniform(-2, 4)
        x, y = base * rng.uniform(-3, 3), base * 10 ** rng.uniform(-3, 1)
        seeds = (
            (0.0, 0.0),
            (base * rng.uniform(0.8, 1.2), 0.0),
            (x + base * rng.uniform(-0.2, 0.2), y * rng.uniform(0.8, 1.2)),
        )
        first_input = triangle(base, x, y, seeds)
        first = solve(first_input, diagnose=False)
        changed = (
            base * rng.uniform(0.95, 1.05),
            x + base * rng.uniform(-0.01, 0.01),
            y * rng.uniform(0.95, 1.05),
        )
        second_input = triangle(*changed, seeds)
        second = solve(second_input, diagnose=False)
        outcomes[f"{first.status.name}/{second.status.name}"] += 1
        if first.success and second.success:
            successful_pairs += 1
            require(
                first.sketch.points[2].v * second.sketch.points[2].v >= 0,
                f"Triangle {case}: mirror branch changed",
            )
            for report, (b, vx, vy) in ((first, (base, x, y)), (second, changed)):
                p0, p1, p2 = report.sketch.points
                close(
                    math.hypot(p1.u - p0.u, p1.v - p0.v),
                    b,
                    f"Triangle {case} base",
                    relative=0,
                    absolute=1e-7,
                )
                close(
                    math.hypot(p2.u - p0.u, p2.v - p0.v),
                    math.hypot(vx, vy),
                    f"Triangle {case} side one",
                    relative=0,
                    absolute=1e-7,
                )
                close(
                    math.hypot(p2.u - p1.u, p2.v - p1.v),
                    math.hypot(vx - b, vy),
                    f"Triangle {case} side two",
                    relative=0,
                    absolute=1e-7,
                )
        else:
            failures.append(case)
            for report, source in ((first, first_input), (second, second_input)):
                if not report.success:
                    require(
                        report.sketch is source and report.remaining_dof is None,
                        f"Triangle {case}: failed solve exposed changed geometry/DoF",
                    )
    # The initial fixed-seed audit produced one conservative DIDNT_CONVERGE pair.
    # Do not count failed solves as branch-preservation passes or allow broad failure.
    require(successful_pairs >= 1499, f"Unexpected convergence regression: {outcomes}")
    return {
        "seed": 6138,
        "pairs": 1500,
        "successful_pairs": successful_pairs,
        "mirror_flips": 0,
        "outcomes": dict(outcomes),
        "failed_case_indices": failures,
    }


def audit_duplicates():
    document = load_document(EXAMPLE)
    numeric = resolve_sketch(document.features[0].sketch, resolve_parameters(document.parameters))
    cases = 0
    for source in (
        numeric,
        replace(numeric, constraints=tuple(c for c in numeric.constraints if c.id != "anchor")),
    ):
        baseline = solve(source)
        require(baseline.success, "Duplicate audit baseline failed")
        for constraint in source.constraints:
            for identifier in ("000copy", "zzzcopy"):
                for reverse in (False, True):
                    duplicate = replace(
                        constraint,
                        id=identifier,
                        refs=constraint.refs[::-1] if reverse else constraint.refs,
                    )
                    candidate = replace(source, constraints=source.constraints + (duplicate,))
                    before = candidate.to_json()
                    report = solve(candidate)
                    require(
                        report.success and report.status == Status.REDUNDANT_OKAY,
                        f"Exact duplicate failed: {constraint.id}/{identifier}/{reverse}",
                    )
                    require(report.remaining_dof == baseline.remaining_dof, "Duplicate changed DoF")
                    require(
                        report.sketch.constraints == candidate.constraints,
                        "Duplicate mitigation deleted or rewrote saved relations",
                    )
                    require(candidate.to_json() == before, "Duplicate solve mutated source")
                    displacement = max(
                        math.hypot(a.u - b.u, a.v - b.v)
                        for a, b in zip(report.sketch.points, baseline.sketch.points, strict=True)
                    )
                    require(
                        displacement < 1e-7,
                        f"Redundant relation moved geometry: {constraint.id}, {displacement} mm",
                    )
                    cases += 1
    return {
        "cases": cases,
        "covers": "all example relations, anchored/free, reversed refs, early/late ID",
    }


def audit_quaternions():
    base = load_document(EXAMPLE)
    cases = 0
    for values in ((0.5, 0.5, 0.5, 0.5), (2, -3, 5, 7)):
        norm = math.sqrt(sum(value * value for value in values))
        unit = tuple(value / norm for value in values)
        for width in (40, 1000, 1e6):
            for error in (0, 5e-10, -5e-10, 9.9e-10):
                raw = base.with_parameter("width", width).to_dict()
                quaternion = [value * math.sqrt(1 + error) for value in unit]
                raw["features"][0]["sketch"]["plane"].update(
                    origin=[3.0, 4.0, 5.0], quaternion=quaternion
                )
                document = Document.from_dict(raw)
                before = document.to_json()
                replay = regenerate(document, OCPKernel())
                require(replay.ok, f"Near-unit plane failed: width={width}, error={error}")
                sketch, pad = replay.result["features"]
                require(document.to_json() == before, "Rebuild changed saved near-unit plane")
                require(
                    sketch["sketch"]["solved"]["plane"]["quaternion"] == quaternion,
                    "Solver result silently rewrote stored plane quaternion",
                )
                close(pad["stats"]["volume"], width * 30 * 10, "Near-unit plane volume")
                end = next(face for face in pad["topology"] if face["role"] == "cap.end")
                expected = tuple(
                    offset + value
                    for offset, value in zip(
                        (3, 4, 5), rotate((width / 2, 15, 10), unit), strict=True
                    )
                )
                require(
                    # Surface integration on million-mm edges has more rounding
                    # than the solver's local coordinates. This still detects
                    # the ~0.00025 mm error an unnormalized basis would introduce.
                    math.dist(expected, end["signature"]["centroid"]) < max(1e-7, width * 2e-12),
                    "Near-unit native/OCCT workplane disagreement",
                )
                cases += 1
    return {"cases": cases, "norm_squared_offsets": [0, 5e-10, -5e-10, 9.9e-10]}


def audit_topology():
    cases = [
        (
            "crossing",
            [(0, 0), (10, 10), (0, 10), (10, 0)],
            [(0, 1), (1, 2), (2, 3), (3, 0)],
            "self_intersecting_profile",
        ),
        ("open", [(0, 0), (10, 0), (10, 10), (0, 10)], [(0, 1), (1, 2), (2, 3)], "open_profile"),
        (
            "branch",
            [(0, 0), (10, 0), (10, 10), (0, 10)],
            [(0, 1), (1, 2), (2, 3), (3, 0), (0, 2)],
            "open_profile",
        ),
        (
            "hole",
            [(0, 0), (10, 0), (10, 10), (0, 10), (2, 2), (3, 2), (3, 3), (2, 3)],
            [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4)],
            "multiple_profile_regions",
        ),
        (
            "touch",
            [(0, 0), (10, 0), (10, 10), (5, 0), (0, 10)],
            [(0, 1), (1, 2), (2, 3), (3, 4), (4, 0)],
            "self_intersecting_profile",
        ),
    ]
    for label, points, edges, expected in cases:
        definition = SketchDefinition(
            "sk",
            tuple(Point(f"p{i}", *point) for i, point in enumerate(points)),
            tuple(Line(f"l{i}", f"p{a}", f"p{b}") for i, (a, b) in enumerate(edges)),
            tuple(
                Constraint(f"fix{i}", "fixed", (f"p{i}",), target=tuple(point))
                for i, point in enumerate(points)
            ),
        )
        document = Document(
            "d",
            "D",
            {},
            (
                Feature("s", "sketch_constrained", "S", sketch=definition),
                Feature("e", "extrude", "E", {"length": 1}, {"profile": "s"}),
            ),
            "e",
            schema_version=2,
        )
        replay = regenerate(document, OCPKernel())
        sketch, pad = replay.result["features"]
        require(sketch["sketch"]["status"] == "okay", f"{label}: solver unexpectedly failed")
        require(sketch["error"]["code"] == expected, f"{label}: incorrect region failure")
        require(
            pad["status"] == "blocked" and "e" not in replay.shapes,
            f"{label}: failed profile produced downstream geometry",
        )
    return {"cases": len(cases), "rejected": [case[0] for case in cases]}


def stl_volume(path):
    """Read actual binary32 triangles, independently of the production STL checker."""
    data = path.read_bytes()
    require(len(data) >= 84, "Truncated binary STL header")
    count = struct.unpack("<I", data[80:84])[0]
    require(len(data) == 84 + count * 50, "Invalid binary STL length")
    origin, volume = None, 0.0
    for index in range(count):
        fields = struct.unpack("<12fH", data[84 + 50 * index : 84 + 50 * (index + 1)])
        vertices = [fields[start : start + 3] for start in (3, 6, 9)]
        if origin is None:
            origin = vertices[0]
        a, b, c = [tuple(point[axis] - origin[axis] for axis in range(3)) for point in vertices]
        volume += (
            a[0] * (b[1] * c[2] - b[2] * c[1])
            + a[1] * (b[2] * c[0] - b[0] * c[2])
            + a[2] * (b[0] * c[1] - b[1] * c[0])
        ) / 6
    return volume


def audit_exports():
    rng, base = random.Random(53450), load_document(EXAMPLE)
    with TemporaryDirectory(prefix="mcad-constrained-audit-") as directory:
        for case in range(12):
            raw = base.to_dict()
            width, depth, length = rng.uniform(2, 100), rng.uniform(2, 100), rng.uniform(1, 10)
            raw["parameters"].update(width=width, depth=depth, height=length)
            quaternion = random_quaternion(rng)
            raw["features"][0]["sketch"]["plane"].update(
                origin=[rng.uniform(-20, 20) for _ in range(3)], quaternion=list(quaternion)
            )
            document = Document.from_dict(raw)
            before = document.to_json()
            step, stl = Path(directory) / f"case-{case}.step", Path(directory) / f"case-{case}.stl"
            result = run_geometry_action(document, "export_step", destination=step)
            require(result["ok"], f"STEP case {case}: {result['error']}")
            kernel = OCPKernel()
            close(
                kernel.inspect(kernel.import_step(step))["volume"],
                width * depth * length,
                f"STEP case {case} volume",
            )
            result = run_geometry_action(document, "export_stl", destination=stl)
            require(result["ok"], f"STL case {case}: {result['error']}")
            close(stl_volume(stl), width * depth * length, f"STL case {case} volume", relative=1e-5)
            require(document.to_json() == before, "Export mutated canonical document")
    return {"seed": 53450, "cases": 12, "step_roundtrips": 12, "binary_stl_volume_checks": 12}


CHECKS = {
    "polygons": audit_polygons,
    "schema": audit_schema,
    "branches": audit_branches,
    "duplicates": audit_duplicates,
    "quaternions": audit_quaternions,
    "topology": audit_topology,
    "exports": audit_exports,
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--section",
        action="append",
        choices=tuple(CHECKS),
        help="Run one section; repeat to select several. Default: all.",
    )
    parser.add_argument(
        "--output", type=Path, help="Write clean JSON evidence to this explicit path."
    )
    arguments = parser.parse_args()
    results = {}
    evidence = {
        "status": "running",
        "runtime": {
            "python": sys.version,
            "slvs": version("slvs"),
            "cadquery-ocp-novtk": version("cadquery-ocp-novtk"),
        },
        "sections": results,
    }
    try:
        for name in arguments.section or CHECKS:
            results[name] = CHECKS[name]()
            print(f"PASS {name}: {json.dumps(results[name], sort_keys=True)}", flush=True)
        evidence["status"] = "passed"
    except Exception as error:
        evidence.update(
            status="failed", failed_section=name, error=f"{type(error).__name__}: {error}"
        )
        raise
    finally:
        if arguments.output:
            arguments.output.write_text(
                json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
    print("CONSTRAINED_GEOMETRY_AUDIT_PASSED", flush=True)


if __name__ == "__main__":
    main()
