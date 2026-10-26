"""Run against the audited source selected by PYTHONPATH; emit JSON to stdout."""

import json

import slvs

from mechanical_cad.sketch_model import Arc, Constraint, Point, Sketch
from mechanical_cad.sketch_solver import Status, solve

cases = [
    ("angular_only", "ccw", ((0.0, 0.0), (1000.0, 0.0), (1000.0, 1e-6)), None),
    ("full_turn_only", "cw", ((0.0, 0.0), (1000.0, 0.0), (1000.0, 1e-6)), None),
    ("chord_only", "ccw", ((0.0, 0.0), (1.0, 0.0), (1.0, 5e-7)), None),
    (
        "small_radius_residual",
        "ccw",
        ((0.0, 0.0), (1e-6, 0.0), (0.0, 1e-6 + 2e-14)),
        None,
    ),
    ("driver_residual", "ccw", ((0.0, 0.0), (7.0, 0.0), (0.0, 7.0)), 5.0),
    (
        "coordinate_domain",
        "ccw",
        ((1e6 + 1.0, 0.0), (1e6 + 6.0, 0.0), (1e6 + 1.0, 5.0)),
        None,
    ),
    ("derived_radius_domain", "ccw", ((-1.0, 0.0), (1e6, 0.0), (-1.0, 5.0)), None),
    ("collapsed", "ccw", ((0.0, 0.0), (5.0, 0.0), (5.0, 0.0)), None),
]
results = []
for name, direction, (c, s, e), radius in cases:
    original = Sketch(
        "fault",
        (Point("c", 0.0, 0.0), Point("s", 5.0, 0.0), Point("e", 0.0, 5.0)),
        (),
        () if radius is None else (Constraint("radius", "radius", ("arc",), radius),),
        schema_version=3,
        arcs=(Arc("arc", "c", "s", "e", direction),),
    )
    add, get = slvs.add_point_2d, slvs.get_param_value
    replacements = {}
    values = iter((*c, *e, *s))

    def patched_add(*args, _add=add, _replacements=replacements, _values=values):
        entity = _add(*args)
        if args[0] == 2:
            for param in entity["param"][:2]:
                _replacements[param] = next(_values)
        return entity

    def patched_get(param, _get=get, _replacements=replacements):
        return _replacements.get(param, _get(param))

    slvs.add_point_2d = patched_add
    slvs.get_param_value = patched_get
    try:
        r = solve(original)
    finally:
        slvs.add_point_2d = add
        slvs.get_param_value = get
    assert (
        not r.success
        and r.status == Status.DIDNT_CONVERGE
        and r.sketch is original
        and r.remaining_dof is None
    ), name
    results.append(
        {
            "case": name,
            "status": r.status.name,
            "max_residual": r.max_residual,
            "original_identity_preserved": r.sketch is original,
        }
    )
print(json.dumps(results, indent=2))
