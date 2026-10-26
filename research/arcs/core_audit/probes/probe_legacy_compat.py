"""Emit legacy evidence for an examples directory, using source on PYTHONPATH."""

import json
import random
import sys
from pathlib import Path

from mechanical_cad.errors import CADException
from mechanical_cad.model import Document
from mechanical_cad.part_snapshot import canonical_snapshot
from mechanical_cad.sidecar import process_request
from mechanical_cad.sketch_model import (
    Circle,
    Constraint,
    Line,
    Point,
    Sketch,
    SketchDefinition,
    resolve_sketch,
)
from mechanical_cad.sketch_solver import solve

rng = random.Random(20261017)
result = {"examples": {}, "synthetic": []}
for p in sorted(Path(sys.argv[1]).rglob("*.mcad.json")):
    raw = json.loads(p.read_text())
    d = Document.from_dict(raw)
    output = {
        "json": d.to_json(),
        "hash": d.content_hash,
        "snapshot": canonical_snapshot(raw),
    }
    for v in (1, 2):
        try:
            output["replay" + str(v)] = process_request(
                {
                    "protocol_version": 1,
                    "action": "replay",
                    "result_version": v,
                    "document": raw,
                }
            )
        except CADException as e:
            output["replay" + str(v)] = {
                "error": type(e).__name__,
                "code": getattr(e, "code", None),
                "message": str(e),
            }
    for f in d.features:
        if f.sketch is not None:
            output["solve_" + f.id] = process_request(
                {
                    "protocol_version": 1,
                    "action": "solve_sketch",
                    "result_version": 2,
                    "document": raw,
                    "feature_id": f.id,
                }
            )
    result["examples"][str(p.relative_to(Path(sys.argv[1])))] = output
for n in range(80):
    v = 1 + n % 2
    points = tuple(
        Point(f"p{i}", rng.uniform(-1e3, 1e3), rng.choice((-0.0, rng.uniform(-1e3, 1e3))))
        for i in range(6)
    )
    lines = (Line("l0", "p0", "p1"), Line("l1", "p2", "p3"))
    circles = (Circle("c0", "p4", rng.uniform(1, 40)),) if v == 2 else ()
    constraints = (
        Constraint("fixed", "fixed", ("p0",), target=(points[0].u, points[0].v)),
        Constraint("h", "horizontal", ("l0",)),
        Constraint("dist", "distance", ("p2", "p3"), rng.uniform(1, 30)),
    )
    if v == 2:
        constraints += (Constraint("r", "radius", ("c0",), rng.uniform(1, 50)),)
    s = Sketch(f"s{n}", points, lines, constraints, schema_version=v, circles=circles)
    definition = SketchDefinition.from_dict(s.to_dict())
    numeric = resolve_sketch(definition, {})
    r = solve(numeric, diagnose=bool(n % 2))
    result["synthetic"].append(
        {
            "json": s.to_json(),
            "definition": definition.to_json(),
            "resolved": numeric.to_json(),
            "status": r.status.name,
            "dof": r.remaining_dof,
            "solved": r.sketch.to_json(),
            "residual": r.max_residual,
            "failed": r.failed_constraints,
            "redundant": r.redundant_constraints,
        }
    )
print(json.dumps(result, sort_keys=True, separators=(",", ":")))
