"""Retirement Finish, actual Part Undo/Redo, and fresh-process accepted-layout readback.

Start with the saved output of blender_sketch_remove_fillet_smoke.py. This is
source-loaded native lifecycle evidence, not interactive GUI or ZIP evidence.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

import bpy

ROOT = Path(os.environ["MCAD_ROOT"])
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import (  # noqa: E402
    general_session,
    register,
    sketch_session,
    unregister,
    workspace,
)


def wait(owner):
    deadline = time.monotonic() + 60
    while owner.pending is not None and time.monotonic() < deadline:
        owner.tick(bpy.context)
        time.sleep(0.01)
    assert owner.pending is None and not owner.error, owner.error


def enter(context, role, on_ready=None):
    context.workspace[workspace.OWNER_KEY] = workspace.OWNER
    context.workspace[workspace.ROLE_KEY] = role
    if on_ready:
        on_ready(context)
    return True


def finish(owner, context):
    with patch.object(workspace, "request_workspace"):
        owner.request_finish(context)
        wait(owner)


register()
readback = os.environ.get("MCAD_RETIRED_READBACK")
if readback:
    bpy.ops.wm.open_mainfile(filepath=readback)
window = bpy.context.window
area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
region = next(r for r in area.regions if r.type == "WINDOW")
with bpy.context.temp_override(window=window, area=area, region=region):
    context = bpy.context
    if readback:
        expected = json.loads(Path(readback + ".json").read_text())
        state = context.scene.mechanical_cad
        assert state.document_json == expected["document"]
        assert state.sketch_annotation_json == expected["layout"]
        assert not state.sketch_draft_json
        owner = general_session.GeneralSession(context, expected["feature"])
        assert owner.draft.annotations == expected["annotations"]
        assert owner.draft.retired_annotation_ids == (expected["radius"],)
        assert not owner.annotation_notice
        assert expected["radius"] not in owner.draft.display_annotations
        assert owner.current_solution_response() is None
        owner.cleanup()
    else:
        with patch.object(workspace, "request_workspace", side_effect=enter):
            assert bpy.ops.mcad.resume_sketch() == {"FINISHED"}
        owner = sketch_session.active_session(context)
        radius = owner.draft.retired_annotation_ids[0]
        arc = owner.draft.annotations[radius]["refs"][0]
        feature = owner.draft.feature_id
        owner.check(context)
        wait(owner)
        owner.local_history(context)
        wait(owner)
        original_annotations = owner.draft.annotations
        finish(owner, context)
        state = context.scene.mechanical_cad
        original_document, original_layout = state.document_json, state.sketch_annotation_json
        assert json.loads(original_layout)["schema_version"] == 1
        context.preferences.edit.use_global_undo = True
        bpy.ops.ed.undo_push(message="Accepted rounded corner and exact label")
        owner = general_session.GeneralSession(context, feature)
        owner.start()
        owner.check(context)
        wait(owner)
        owner.draft.select((("arc", arc),))
        owner.checkpoint()
        owner.request_fillet_removal(context, arc)
        wait(owner)
        retired_annotations = owner.draft.annotations
        assert owner.draft.retired_annotation_ids == (radius,)
        finish(owner, context)
        state = context.scene.mechanical_cad
        accepted_document, accepted_layout = state.document_json, state.sketch_annotation_json
        assert json.loads(accepted_layout)["schema_version"] == 2
        bpy.ops.ed.undo_push(message="Accepted sharp corner and retired label")
        assert bpy.ops.ed.undo() == {"FINISHED"}
        state = context.scene.mechanical_cad
        assert state.document_json == original_document
        assert state.sketch_annotation_json == original_layout
        original_owner = general_session.GeneralSession(context, feature)
        assert original_owner.draft.annotations == original_annotations
        assert not original_owner.draft.retired_annotation_ids
        assert not original_owner.annotation_notice
        original_owner.cleanup()
        assert bpy.ops.ed.redo() == {"FINISHED"}
        state = context.scene.mechanical_cad
        assert state.document_json == accepted_document
        assert state.sketch_annotation_json == accepted_layout
        owner = general_session.GeneralSession(context, feature)
        assert owner.draft.annotations == retired_annotations
        assert not owner.annotation_notice
        assert owner.draft.retired_annotation_ids == (radius,)
        owner.cleanup()
        path = str(Path(os.environ["TMPDIR"]) / "retired-annotation-finished.blend")
        Path(path + ".json").write_text(json.dumps({
            "document": accepted_document, "layout": accepted_layout,
            "feature": feature, "radius": radius, "annotations": retired_annotations,
        }))
        bpy.ops.wm.save_as_mainfile(filepath=path)
        process = subprocess.run([
            bpy.app.binary_path, "--background", "--factory-startup", "--python-exit-code", "1",
            "--python", str(Path(__file__).resolve()),
        ], env=dict(os.environ, MCAD_RETIRED_READBACK=path), capture_output=True, text=True, timeout=120)
        print(process.stdout, flush=True)
        assert process.returncode == 0 and "RETIRED_ANNOTATION_READBACK_OK" in process.stdout, process.stderr
unregister()
print("RETIRED_ANNOTATION_READBACK_OK" if readback else "RETIRED_ANNOTATION_FINISH_OK", flush=True)
