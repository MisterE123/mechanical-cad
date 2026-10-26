"""Native projection operator + owner persistence, relation binding and upstream edits."""

import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import patch

import bpy

sys.path.insert(0, str(Path(os.environ["MCAD_ROOT"]) / "blender_addon"))
from mechanical_cad_blender import (  # noqa: E402
    document_state,
    draft_dispatch,
    general_session,
    register,
    unregister,
    workspace,
)
from mechanical_cad_blender.general_sketch_commands import AddCircle, PointRef  # noqa: E402


def wait(owner, context):
    deadline = time.monotonic() + 30
    while owner.pending is not None and time.monotonic() < deadline:
        owner.tick(context)
        time.sleep(0.01)
    assert owner.pending is None and not owner.error, owner.error


register()
window = bpy.context.window
area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
region = next(r for r in area.regions if r.type == "WINDOW")
with bpy.context.temp_override(window=window, area=area, region=region):
    context = bpy.context
    state = context.scene.mechanical_cad
    source = {
        "schema_version": 2,
        "id": "source_geometry",
        "units": "mm",
        "plane": {"id": "xy", "origin": [0, 0, 0], "quaternion": [1, 0, 0, 0]},
        "points": [{"id": "center", "u": 4, "v": 5}],
        "lines": [],
        "circles": [{"id": "circle", "center": "center", "radius": 2}],
        "constraints": [
            {"id": "fixed", "kind": "fixed", "refs": ["center"], "target": [4, 5]},
            {"id": "radius", "kind": "radius", "refs": ["circle"], "value": 2},
        ],
    }
    document = {
        "schema_version": 2,
        "id": "part",
        "name": "Projection",
        "units": "mm",
        "parameters": {},
        "active_feature": "source",
        "features": [
            {
                "id": "source",
                "kind": "sketch_constrained",
                "label": "Source sketch",
                "params": {},
                "inputs": {},
                "sketch": source,
            }
        ],
    }
    document_state._populate_document(context.scene, document)
    document_state.regenerate(context)
    owner = general_session.GeneralSession(context)
    owner.start()
    assert bpy.ops.mcad.project_sketch_geometry(source_sketch="source", source_entity="circle") == {
        "FINISHED"
    }
    wait(owner, context)
    target = owner.commands.candidate()["features"][-1]
    projected = target["projections"][0]["target"]
    point = next(c for c in owner.commands.sketch["circles"] if c["id"] == projected)["center"]
    assert owner.geometry().points[point] == (4, 5)
    assert owner.geometry().circles[projected].construction
    assert owner.commands.sketch["points"][0]["u"] == 0
    owner.local_history(context)
    wait(owner, context)
    assert "projections" not in owner.commands.candidate()["features"][-1]
    owner.local_history(context, redo=True)
    wait(owner, context)
    owner.execute(context, AddCircle(PointRef(point), 4))
    wait(owner, context)
    owner.suspend("Projection persistence")
    restored = draft_dispatch.restore(state.sketch_draft_json, state.document_json)
    owner = general_session.GeneralSession(context, restored=restored)
    owner.start()
    assert owner.geometry().source == "authored"
    assert owner.geometry().points[point] == (4, 5)
    owner.check(context)
    wait(owner, context)
    with patch.object(workspace, "request_workspace"):
        owner.request_finish(context)
        wait(owner, context)
    assert owner.finished
    candidate = json.loads(state.document_json)
    candidate["features"][0]["sketch"]["constraints"][0]["target"] = [8, 9]
    candidate["features"][0]["sketch"]["constraints"][1]["value"] = 3
    document_state._commit_candidate(context, candidate)
    assert state.status == "READY", state.error
    owner = general_session.GeneralSession(context, target["id"])
    owner.start()
    assert owner.geometry().points[point] == (8, 9)
    assert owner.geometry().circles[projected].radius_mm == 3
    assert owner.commands.sketch["points"][0]["u"] == 0
    owner.discard("Test complete")
    assert bpy.ops.mcad.add_extrude(profile="source", length=10) == {"FINISHED"}
    block = state.active_feature
    owner = general_session.GeneralSession(
        context, support={"feature_id": block, "face_id": block + "/face/cap.end"}
    )
    owner.start()
    assert bpy.ops.mcad.project_sketch_geometry.poll()
    assert bpy.ops.mcad.project_sketch_geometry(source_sketch="source", source_entity="circle") == {
        "FINISHED"
    }
    wait(owner, context)
    geometry = owner.geometry()
    assert all(
        abs(a - b) < 1e-8 for a, b in zip(geometry.plane.origin_mm, (8, 9, 10), strict=True)
    ), geometry.plane.origin_mm
    center = next(iter(geometry.points.values()))
    assert abs(center[0]) < 1e-8 and abs(center[1]) < 1e-8
    owner.discard("Attached projection test complete")
print("MCAD_PROJECTED_SKETCH_SMOKE_OK", flush=True)
unregister()
