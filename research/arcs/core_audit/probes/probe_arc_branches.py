"""Run against the audited source selected by PYTHONPATH; emit JSON to stdout."""

import itertools
import json

from mechanical_cad.arc_geometry import arc_geometry
from mechanical_cad.sketch_model import Arc, Constraint, Point, Sketch
from mechanical_cad.sketch_solver import solve

results = []
for seed_y, radius, direction in itertools.product(
    (0.0, 1e-8, 1e-4, -1e-4), (4.9, 5.0, 5.000000001, 7.0), ("ccw", "cw")
):
    points = (Point("c", 0.0, seed_y), Point("s", -5.0, 0.0), Point("e", 5.0, 0.0))
    constraints = (
        Constraint("fix_start", "fixed", ("s",), target=(-5.0, 0.0)),
        Constraint("fix_end", "fixed", ("e",), target=(5.0, 0.0)),
        Constraint("radius", "radius", ("arc",), radius),
    )
    sketch = Sketch(
        "branch",
        points,
        (),
        constraints,
        schema_version=3,
        arcs=(Arc("arc", "c", "s", "e", direction),),
    )
    report = solve(sketch)
    item = {
        "seed_center_y": seed_y,
        "radius": radius,
        "direction": direction,
        "status": report.status.name,
        "dof": report.remaining_dof,
        "residual": report.max_residual,
        "failed": report.failed_constraints,
    }
    assert set(report.failed_constraints) <= {c.id for c in constraints}
    if report.success:
        points = {p.id: (p.u, p.v) for p in report.sketch.points}
        g = arc_geometry(points["c"], points["s"], points["e"], direction, require_equal_radii=True)
        item.update(
            center=points["c"],
            start_radius=g.start_radius,
            end_radius=g.end_radius,
            sweep=g.sweep_radians,
        )
        assert abs(g.start_radius - radius) <= 1e-7
    else:
        assert report.sketch is sketch and report.remaining_dof is None
    results.append(item)
print(json.dumps(results, indent=2))
