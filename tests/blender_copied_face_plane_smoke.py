"""Native imported-plane sampling, transient guards and unlinked sketch persistence.

Run with MCAD_COPIED_STEP pointing to a rotated native box STEP and optional
MCAD_COPIED_BLEND output. This is headless lifecycle evidence, not real GUI QA.
"""

import copy
import json
import math
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy
from mathutils import Vector

ROOT = Path(os.environ["MCAD_ROOT"])
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import (  # noqa: E402
    copied_face_plane as copied,
)
from mechanical_cad_blender import (  # noqa: E402
    document_state,
    face_pick,
    general_viewport,
    register,
    sketch_session,
    unregister,
    workspace,
)
from mechanical_cad_blender.display import _owned_objects  # noqa: E402
from mechanical_cad_blender.general_sketch_commands import PointSeed  # noqa: E402


def rejects(action, text=""):
    try:
        action()
    except (ValueError, RuntimeError) as exc:
        assert text in str(exc), str(exc)
    else:
        raise AssertionError("Unsafe copied-plane action accepted")


def wait(owner):
    deadline = time.monotonic() + 30
    while owner.pending is not None and time.monotonic() < deadline:
        owner.tick(bpy.context)
        time.sleep(0.01)
    assert owner.pending is None and not owner.error, owner.error


register()
window = bpy.context.window
area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
region = next(r for r in area.regions if r.type == "WINDOW")
with bpy.context.temp_override(window=window, area=area, region=region):
    context = bpy.context
    for obj in context.scene.objects:
        obj.hide_set(True)
    state = context.scene.mechanical_cad
    assert bpy.ops.mcad.import_step(filepath=os.environ["MCAD_COPIED_STEP"]) == {"FINISHED"}
    original = state.document_json
    result = document_state.current_part_result(context)
    obj = _owned_objects(context.scene)[0]
    feature = face_pick.bound_feature(context, obj, result)
    assert all(f["provenance"]["semantic_status"] == "unknown" for f in feature["topology"])
    face = copied.resolve_sample(feature, 0)
    signature = face["signature"]
    expected = copied.literal_plane(face)
    assert not any(abs(n) > 0.999 for n in signature["normal"]), "Fixture must be oblique"
    assert math.isclose(sum(x*x for x in expected["quaternion"]), 1, abs_tol=1e-12)
    rejects(lambda: face_pick.resolve_triangle(feature, 0), "stable identity")
    # Ray-cast the native centroid along its analytic normal; ray only selects a
    # candidate. The copied plane still derives exclusively from native signature.
    center = Vector(signature["centroid"]) * 0.001
    normal = Vector(signature["normal"])
    context.view_layer.update()
    hit, _, _, index, hit_obj, matrix = context.scene.ray_cast(
        context.evaluated_depsgraph_get(), center + normal, -normal
    )
    assert hit and hit_obj.original == obj and matrix == obj.matrix_world
    assert copied.resolve_sample(feature, index)["id"] == face["id"]

    def picker():
        selected = copied.CopiedPlanePicker(context)
        selected.resolve_face(feature, index)
        selected.hit = (feature["id"], face["id"])
        selected.hover_object = obj
        return selected

    pick = picker()
    capture = copied.PlaneCapture(context, pick)
    assert capture.plane(context) == expected
    original_coordinate = obj.data.vertices[0].co.copy()
    obj.data.vertices[0].co.x += 0.001
    rejects(lambda: capture.plane(context), "edited or transformed")
    obj.data.vertices[0].co = original_coordinate
    state.sketch_draft_json = "changed draft"
    rejects(lambda: capture.plane(context), "context changed")
    state.sketch_draft_json = ""
    state.status = "DIRTY"
    rejects(lambda: capture.plane(context), "Part changed")
    state.status = "READY"
    with patch.object(face_pick.backend_runtime, "assert_current", side_effect=ValueError("revoked")):
        rejects(lambda: capture.plane(context), "Part changed")
    with patch.object(document_state, "current_part_result", return_value=None):
        rejects(lambda: capture.plane(context), "unavailable")
    for mutation in ("ambiguous", "missing", "curved", "normal"):
        changed = copy.deepcopy(feature)
        target = next(f for f in changed["topology"] if f["id"] == face["id"])
        if mutation == "ambiguous":
            changed["topology"].append(copy.deepcopy(target))
        elif mutation == "missing":
            changed["mesh"]["triangle_face_ids"][index] = None
        elif mutation == "curved":
            target["signature"]["surface"] = "bsplinesurface"
        else:
            target["signature"]["normal"] = [0, 0, 0]
        rejects(lambda changed=changed: copied.resolve_sample(changed, index))
    selected = tuple(context.selected_objects)
    stub = SimpleNamespace(_picker=pick)
    assert general_viewport.MCAD_OT_copied_face_sketch.modal(
        stub, context, SimpleNamespace(type="ESC")
    ) == {"CANCELLED"}
    assert state.document_json == original and not state.sketch_draft_json
    assert tuple(context.selected_objects) == selected and not face_pick._PICKERS
    # Even an identical replay invalidates the exact captured receipt. Never
    # rematch unknown face IDs, ordinals or geometry across a rebuild.
    assert document_state.regenerate(context)
    rejects(lambda: capture.plane(context), "Part changed")
    obj = _owned_objects(context.scene)[0]
    feature = face_pick.bound_feature(context, obj, document_state.current_part_result(context))
    # Regeneration can replace display objects; deliberately reselect the new one.
    hit, _, _, index, hit_obj, _ = context.scene.ray_cast(
        context.evaluated_depsgraph_get(), center + normal, -normal
    )
    assert hit and hit_obj.original == obj
    face = copied.resolve_sample(feature, index)
    pick = picker()
    capture = copied.PlaneCapture(context, pick)
    pick.close()
    copied._PENDING["native-test"] = capture
    with patch.object(workspace, "get_role", return_value="SKETCH"):
        assert bpy.ops.mcad.general_sketch(copied_plane_token="native-test") == {"RUNNING_MODAL"}
    assert not copied._PENDING
    rejects(lambda: copied.consume(context, "native-test"), "expired")
    owner = sketch_session.active_session()
    assert owner.commands.sketch["plane"] == expected
    assert owner.commands.candidate()["features"][-1]["inputs"] == {}
    owner.discard()
    assert state.document_json == original and not state.sketch_draft_json
    # Pending workspace callback retains no permission to use a replaced replay.
    pick = picker()
    with patch.object(workspace, "request_workspace") as transition:
        pick.begin(context)
    callback = transition.call_args.kwargs["on_ready"]
    assert document_state.regenerate(context)
    rejects(lambda: callback(context), "Part changed")
    assert not copied._PENDING and sketch_session.active_session() is None
    obj = _owned_objects(context.scene)[0]
    feature = face_pick.bound_feature(context, obj, document_state.current_part_result(context))
    hit, _, _, index, hit_obj, _ = context.scene.ray_cast(
        context.evaluated_depsgraph_get(), center + normal, -normal
    )
    assert hit and hit_obj.original == obj
    face = copied.resolve_sample(feature, index)
    # Reselect after cancelling. The actual async authoring/Finish path creates
    # the canonical feature, not a test-only document-writing shortcut.
    pick = picker()
    capture = copied.PlaneCapture(context, pick)
    pick.close()
    # Exercise the actual delayed picker callback and token-consuming operator.
    pick = picker()
    with patch.object(workspace, "request_workspace") as transition:
        pick.begin(context)
    with patch.object(workspace, "get_role", return_value="SKETCH"):
        transition.call_args.kwargs["on_ready"](context)
    owner = sketch_session.active_session()
    assert owner is not None and not copied._PENDING
    bpy.ops.ed.undo_push(message="Before copied plane sketch")
    owner.draft.begin_circle(PointSeed(0, 0), 2)
    owner.proposal_capture = True
    owner.accept_proposal(context)
    wait(owner)
    with patch.object(workspace, "request_workspace"):
        owner.request_finish(context)
        wait(owner)
    assert owner.finished
    document = json.loads(state.document_json)
    sketch = document["features"][-1]
    assert sketch["inputs"] == {}
    assert not {"support_face", "support_intent"} & sketch.keys()
    assert sketch["sketch"]["plane"] == expected
    assert not sketch.get("projections")
    assert not sketch["sketch"].get("projections")
    accepted = state.document_json
    bpy.ops.ed.undo_push(message="After copied plane sketch")
    assert bpy.ops.ed.undo() == {"FINISHED"}
    state = bpy.context.scene.mechanical_cad
    assert state.document_json == original
    assert bpy.ops.ed.redo() == {"FINISHED"}
    state = bpy.context.scene.mechanical_cad
    assert state.document_json == accepted
    assert document_state.regenerate(context)
    # Replace the immutable source asset explicitly with different native
    # geometry. The saved literal plane must remain exactly unchanged.
    from mechanical_cad_blender.step_asset import encode_step

    document["features"][0]["step_data"] = encode_step(
        Path(os.environ["MCAD_COPIED_STEP_CHANGED"]).read_bytes()
    )
    assert document_state._commit_candidate(context, document)
    changed = json.loads(state.document_json)
    assert changed["features"][-1] == sketch
    replay = document_state.current_part_result(context)
    assert all(
        f["provenance"]["semantic_status"] == "unknown"
        and all(value > 60 for value in f["signature"]["centroid"])
        for f in replay["features"][0]["topology"]
    )
    assert replay["features"][-1]["sketch"]["solved"]["plane"] == expected
    output = os.environ.get("MCAD_COPIED_BLEND", "/tmp/mcad_copied_plane.blend")
    Path(output + ".plane.json").write_text(json.dumps(expected))
    bpy.ops.wm.save_as_mainfile(filepath=output)
    assert not copied._PENDING and not face_pick._PICKERS
unregister()
print("COPIED_FACE_PLANE_NATIVE_OK", flush=True)
