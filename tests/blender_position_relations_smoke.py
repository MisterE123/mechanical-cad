"""Actual constraint UI selection/apply/remove/Undo paths with native SolveSpace."""

import os
import sys
import time
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(os.environ["MCAD_ROOT"]) / "blender_addon"))
from mechanical_cad_blender import (  # noqa: E402
    constraint_ui,
    document_state,
    general_session,
    help_topics,
    register,
    unregister,
)


def wait(owner, context):
    deadline = time.monotonic() + 30
    while owner.pending is not None and time.monotonic() < deadline:
        owner.tick(context)
        time.sleep(0.01)
    assert owner.pending is None and not owner.error, owner.error


def fixture(kind):
    points = [
        {"id": "a", "u": 0, "v": 0},
        {"id": "b", "u": 10, "v": 0},
        {"id": "p", "u": 5, "v": 4},
    ]
    constraints = [
        {"id": "fix_a", "kind": "fixed", "refs": ["a"], "target": [0, 0]},
        {"id": "fix_b", "kind": "fixed", "refs": ["b"], "target": [10, 0]},
    ]
    circles = []
    if kind == "symmetry":
        points.append({"id": "q", "u": 7, "v": -3})
        constraints.append({"id": "fix_p", "kind": "fixed", "refs": ["p"], "target": [5, 4]})
    if kind in {"concentric", "circle_line_tangent"}:
        circles = [{"id": "circle", "center": "p", "radius": 2}]
        constraints.append({"id": "size", "kind": "radius", "refs": ["circle"], "value": 2})
    if kind == "concentric":
        circles.append({"id": "other", "center": "a", "radius": 3})
        constraints.append({"id": "other_size", "kind": "radius", "refs": ["other"], "value": 3})
    sketch = {
        "schema_version": 2,
        "id": "geometry",
        "units": "mm",
        "plane": {"id": "xy", "origin": [0, 0, 0], "quaternion": [1, 0, 0, 0]},
        "points": points,
        "lines": [{"id": "line", "start": "a", "end": "b", "construction": True}],
        "circles": circles,
        "constraints": constraints,
    }
    return {
        "schema_version": 2,
        "id": "part",
        "name": "Relations",
        "units": "mm",
        "parameters": {},
        "active_feature": "sketch",
        "features": [
            {
                "id": "sketch",
                "kind": "sketch_constrained",
                "label": "Sketch",
                "params": {},
                "inputs": {},
                "sketch": sketch,
            }
        ],
    }


register()
window = bpy.context.window
area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
region = next(r for r in area.regions if r.type == "WINDOW")
assert "sketch.position_relations" in help_topics.HELP_TOPICS
with bpy.context.temp_override(window=window, area=area, region=region):
    context = bpy.context
    for kind in ("point_on_line", "midpoint", "concentric", "circle_line_tangent", "symmetry"):
        document_state._populate_document(context.scene, fixture(kind))
        owner = general_session.GeneralSession(context, "sketch")
        owner.start()
        owner.check(context)
        wait(owner, context)
        selection = (
            (("line", "line"), ("point", "p"))
            if kind in {"point_on_line", "midpoint"}
            else (
                (("circle", "other"), ("circle", "circle"))
                if kind == "concentric"
                else (("line", "line"), ("circle", "circle"))
            )
        )
        if kind == "symmetry":
            selection = (("point", "p"), ("line", "line"), ("point", "q"))
        constraint_ui.select_bindings(owner, selection, context=context)
        assert constraint_ui.action_available(context, kind)
        assert bpy.ops.mcad.constraint_action(action=kind) == {"FINISHED"}
        wait(owner, context)
        relation = next(c for c in owner.commands.sketch["constraints"] if c["kind"] == kind)
        geometry = owner.geometry()
        u, v = geometry.points["p"]
        if kind == "point_on_line":
            assert abs(v) < 1e-7, (kind, u, v)
        elif kind == "midpoint":
            assert abs(u - 5) < 1e-7 and abs(v) < 1e-7, (kind, u, v)
        elif kind == "concentric":
            assert abs(u) < 1e-7 and abs(v) < 1e-7, (kind, u, v)
        elif kind == "symmetry":
            assert abs(u - 5) < 1e-7 and abs(v - 4) < 1e-7
            qu, qv = geometry.points["q"]
            assert abs(qu - 5) < 1e-7 and abs(qv + 4) < 1e-7
        else:
            assert abs(abs(v) - 2) < 1e-7, (kind, u, v)
        assert len(geometry.points) == (
            4 if kind == "symmetry" else 3
        )  # No native auxiliary contact point leaks.
        revision = owner.commands.revision
        constraint_ui.select_bindings(owner, selection[::-1], context=context)
        assert bpy.ops.mcad.constraint_action(action=kind) == {"FINISHED"}
        assert owner.commands.revision == revision
        constraint_ui.select_bindings(owner, (("constraint", relation["id"]),), context=context)
        assert bpy.ops.mcad.constraint_action(action="remove_relation") == {"FINISHED"}
        wait(owner, context)
        assert not any(c["kind"] == kind for c in owner.commands.sketch["constraints"])
        assert bpy.ops.mcad.constraint_history(direction="UNDO") == {"FINISHED"}
        wait(owner, context)
        assert any(c["id"] == relation["id"] for c in owner.commands.sketch["constraints"])
        assert bpy.ops.mcad.constraint_history(direction="REDO") == {"FINISHED"}
        wait(owner, context)
        assert not any(c["kind"] == kind for c in owner.commands.sketch["constraints"])
        owner.discard("Relation smoke complete")
print("MCAD_POSITION_RELATIONS_SMOKE_OK", flush=True)
unregister()
