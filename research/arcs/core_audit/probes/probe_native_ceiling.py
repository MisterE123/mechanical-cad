"""Probe a native ceiling: pass intrinsic256 or rows1024, with source on PYTHONPATH."""

import json
import resource
import sys
import time

from mechanical_cad.sketch_model import (
    Arc,
    Constraint,
    Point,
    Sketch,
    active_scalar_count,
    native_equation_count,
    validate,
)
from mechanical_cad.sketch_solver import solve

kind = sys.argv[1]
coords = ((0.0, 0.0), (5.0, 0.0), (0.0, 5.0))
if kind == "intrinsic256":
    points = tuple(Point(f"p{i}", *coords[i]) for i in range(3))
    constraints = ()
elif kind == "rows1024":
    points = tuple(Point(f"p{i}", *coords[i % 3]) for i in range(256))
    constraints = tuple(
        Constraint(f"f{i}", "fixed", (f"p{i}",), target=(p.u, p.v)) for i, p in enumerate(points)
    )
    constraints += tuple(
        Constraint(f"c{i}", "coincident", (f"p{i}", f"p{i + 3}")) for i in range(128)
    )
else:
    raise ValueError(kind)
s = Sketch(
    "ceiling",
    points,
    (),
    constraints,
    schema_version=3,
    arcs=tuple(Arc(f"a{i}", "p0", "p1", "p2", "ccw" if i % 2 else "cw") for i in range(256)),
)
validate(s)
print(
    json.dumps(
        {
            "case": kind,
            "rows": native_equation_count(s),
            "scalars": active_scalar_count(s),
        }
    ),
    flush=True,
)
t = time.monotonic()
r = solve(s)
print(
    json.dumps(
        {
            "seconds": time.monotonic() - t,
            "status": r.status.name,
            "success": r.success,
            "dof": r.remaining_dof,
            "residual": r.max_residual,
            "failed": r.failed_constraints,
            "rss": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        }
    ),
    flush=True,
)
