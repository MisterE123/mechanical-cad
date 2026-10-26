"""Native exact-input review lifecycle; real popup/gesture GUI qualification is separate."""

import copy
import json
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy

ROOT = Path(os.environ["MCAD_ROOT"])
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import (  # noqa: E402
    direct_edge_pick,
    document_state,
    face_pick,
    register,
    registration,
    solid_operators,
    solid_review,
    unregister,
)
from mechanical_cad_blender.common import OWNER_KEY  # noqa: E402

register()
window = bpy.context.window
area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
region = next(r for r in area.regions if r.type == "WINDOW")
with bpy.context.temp_override(window=window, area=area, region=region):
    context = bpy.context
    state = context.scene.mechanical_cad
    assert bpy.ops.mcad.new_document(name="Reselect input") == {"FINISHED"}
    assert bpy.ops.mcad.add_rectangle(width=20, height=30) == {"FINISHED"}
    assert bpy.ops.mcad.add_extrude(profile=state.active_feature, length=10) == {"FINISHED"}
    base = state.active_feature
    assert bpy.ops.mcad.add_solid_feature(
        kind="shell",
        base=base,
        thickness="1",
        shell_mode="OPEN",
        opening_face=base + "/face/cap.end",
    ) == {"FINISHED"}
    shell = state.active_feature
    before = state.document_json
    accepted = document_state.current_part_evidence(context)
    original = list(context.scene.objects)
    visibility = {o: o.hide_get() for o in original}
    selection = tuple(context.selected_objects)
    active = context.view_layer.objects.active
    review = solid_review.InputReview(context, shell, base)
    assert state.document_json == before and state.active_feature == shell
    assert document_state.current_part_evidence(context) == accepted
    assert review.obj.get(OWNER_KEY) != state.owner_id
    assert not any(o.hide_get() is False for o in original if o.get(OWNER_KEY) == state.owner_id)
    assert (
        review.bound_feature(context, review.obj, review.result(context, accepting=True))["id"]
        == base
    )
    try:
        face_pick.bound_feature(context, review.obj, review.result(context))
        raise AssertionError("Ordinary picker accepted separately owned review")
    except ValueError:
        pass
    picker = face_pick.FacePicker(context, snapshot=review)
    assert picker.current(context)
    review.obj.location.x += 1
    context.view_layer.update()
    try:
        review.bound_feature(context, review.obj, review.result(context, accepting=True))
        raise AssertionError("Modified review geometry was accepted")
    except ValueError:
        pass
    picker.close()
    assert set(context.scene.objects) == set(original)
    assert {o: o.hide_get() for o in original} == visibility
    assert (
        tuple(context.selected_objects) == selection and context.view_layer.objects.active == active
    )
    assert not solid_review._REVIEWS
    assert (
        state.document_json == before and document_state.current_part_evidence(context) == accepted
    )

    # Integration lifecycle: retire the temporary owner before RNA history/load
    # replacement and before saving, rather than waiting for timer supervision.
    for retire in (
        lambda: registration._retire_native_jobs("Review regression", lambda: None),
        lambda: registration._before_blend_save(None),
    ):
        review = solid_review.InputReview(context, shell, base)
        retire()
        assert review.closed and not solid_review._REVIEWS
        assert set(context.scene.objects) == set(original)
        assert {o: o.hide_get() for o in original} == visibility
        assert state.document_json == before

    review = solid_review.InputReview(context, shell, base)
    registration._invalidate_backend_evidence("Review regression")
    assert review.closed and not solid_review._REVIEWS
    assert set(context.scene.objects) == set(original)
    assert state.document_json == before
    # Backend invalidation deliberately hides the now-outdated final display.
    assert all(o.hide_get() for o in original if o.get(OWNER_KEY) == state.owner_id)

    # Edge selection uses the saved feature's original input, never its final blend.
    candidate = json.loads(before)
    candidate["features"][-1] = {
        "id": shell,
        "label": "Blend",
        "kind": "fillet",
        "inputs": {"base": base},
        "params": {"radius": "1"},
        "edge_faces": [base + "/face/cap.end", base + "/face/side.y_min"],
    }
    assert document_state._commit_candidate(context, candidate, "")
    before = state.document_json
    review = solid_review.InputReview(context, shell, base)
    picker = direct_edge_pick.BlendEdgePicker(context, "fillet", snapshot=review)
    deadline = time.monotonic() + 40
    while picker.pending is not None:
        assert time.monotonic() < deadline
        picker.poll_catalog(context)
        time.sleep(0.01)
    assert len(picker.catalog[base]) == 12
    assert (
        review.bound_feature(context, review.obj, review.result(context, accepting=True))["id"]
        == base
    )
    # Transfer review ownership to the explicit two-face fallback without
    # restoring or substituting the final display in between.
    from mechanical_cad_blender.edge_pick import BlendFacePicker

    picker.close(retain_snapshot=True)
    assert review.current(context)
    picker = BlendFacePicker(context, "fillet", snapshot=review)
    assert picker.current(context)
    picker.close()
    assert state.document_json == before

    # Upstream input inspection is allowed even when downstream replay fails;
    # this read-only path does not recover/publish the failed whole document.
    failed = copy.deepcopy(candidate)
    failed["features"][-1]["params"]["radius"] = 1000
    state.document_json = json.dumps(failed)
    failed_bytes = state.document_json
    review = solid_review.InputReview(context, shell, base)
    assert review.result(context, accepting=True)["features"][-1]["status"] == "failed"
    assert review.bound_feature(context, review.obj, review.result(context))["id"] == base
    review.close()
    assert state.document_json == failed_bytes
    state.document_json = before
    review = solid_review.InputReview(context, shell, base)
    state.document_json += " "
    assert not review.current(context)
    try:
        review.result(context, accepting=True)
        raise AssertionError("Stale evidence accepted")
    except ValueError:
        pass
    review.close()
    state.document_json = before

    # Resume restores raw pending fields, including expressions and label, then
    # the real existing atomic editor applies all fields in one rebuild.
    class Manager:
        def invoke_props_dialog(self, owner, **kwargs):
            return {"RUNNING_MODAL"}

    class WrappedContext:
        window_manager = Manager()

        def __getattr__(self, key):
            return getattr(context, key)

    values = {
        "original_json": before,
        "feature_id": shell,
        "feature_label": "Reselected blend",
        "base": base,
        "radius": "1 + 0.25",
        "face_a": base + "/face/cap.start",
        "face_b": base + "/face/side.y_min",
        "edge_mode": "PAIR",
        "shell_mode": "CLOSED",
        "opening_face": "NONE",
    }
    owner = SimpleNamespace(
        feature_id=shell, resume_json=json.dumps(values), report=lambda *a: None
    )
    assert solid_operators.MCAD_OT_edit_solid_feature.invoke(owner, WrappedContext(), None) == {
        "RUNNING_MODAL"
    }
    assert owner.radius == "1 + 0.25" and owner.feature_label == "Reselected blend"
    owner.poll = lambda context: True
    with patch.object(
        solid_operators,
        "_report_result",
        side_effect=lambda op, ctx, result: {"FINISHED"} if result else {"CANCELLED"},
    ):
        assert solid_operators.MCAD_OT_edit_solid_feature.execute(owner, context) == {"FINISHED"}
    updated = json.loads(state.document_json)
    assert updated["active_feature"] == shell
    assert updated["features"][-1]["params"]["radius"] == "1 + 0.25"
    assert updated["features"][-1]["edge_faces"] == [values["face_a"], values["face_b"]]
    good = state.document_json
    owner.original_json = good
    owner.radius = "1000"
    with patch.object(
        solid_operators,
        "_report_result",
        side_effect=lambda op, ctx, result: {"FINISHED"} if result else {"CANCELLED"},
    ):
        assert solid_operators.MCAD_OT_edit_solid_feature.execute(owner, context) == {"CANCELLED"}
    assert state.document_json == good
    assert not solid_review._REVIEWS and not face_pick._PICKERS
unregister()
print("SOLID_RESELECTION_NATIVE_OK", flush=True)
