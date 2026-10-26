"""Run against the audited source selected by PYTHONPATH; emit JSON to stdout."""

import itertools
import json

from mechanical_cad.arc_geometry import arc_geometry
from mechanical_cad.sketch_model import Arc, Constraint, Point, Sketch, SketchError
from mechanical_cad.sketch_solver import solve

results = []
for radius, origin, direction, minor in itertools.product(
    (1e-6, 1e-5, 1.0, 1e5, 1e6), (0.0, 999990.0), ("ccw", "cw"), (True, False)
):
    if origin + radius > 1e6:
        continue
    c = (origin, origin)
    s = (origin + radius, origin)
    e = (origin, origin + radius)
    a = Arc("arc", "c", "s", "e", direction)
    constraints = (
        Constraint("fix", "fixed", ("c",), target=c),
        Constraint("radius", "radius", ("arc",), radius),
    )
    if not minor:
        e = (origin, origin - radius)
    sketch = Sketch(
        "domain",
        (Point("c", *c), Point("s", *s), Point("e", *e)),
        (),
        constraints,
        schema_version=3,
        arcs=(a,),
    )
    try:
        report = solve(sketch)
        item = {
            "radius": radius,
            "origin": origin,
            "direction": direction,
            "upper_endpoint": minor,
            "status": report.status.name,
            "dof": report.remaining_dof,
            "residual": report.max_residual,
        }
        if report.success:
            points = {p.id: (p.u, p.v) for p in report.sketch.points}
            g = arc_geometry(
                points["c"],
                points["s"],
                points["e"],
                direction,
                require_equal_radii=True,
            )
            item.update(
                start_radius=g.start_radius,
                end_radius=g.end_radius,
                sweep=g.sweep_radians,
            )
        else:
            assert report.sketch is sketch and report.remaining_dof is None
    except SketchError as exc:
        item = {
            "radius": radius,
            "origin": origin,
            "direction": direction,
            "upper_endpoint": minor,
            "error": exc.code,
        }
    results.append(item)
print(json.dumps(results, indent=2))
