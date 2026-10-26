"""Real solver, UI-only reference controls, scene Undo/Redo and fresh reopen.

This is headless native qualification, not GUI pointer-usability evidence.
MCAD_ROOT/MCAD_PYTHON select source/runtime; MCAD_REF_DIRECTORY holds evidence.
"""

import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import patch

import bpy

ROOT = Path(os.environ["MCAD_ROOT"])
DIRECTORY = Path(os.environ["MCAD_REF_DIRECTORY"])
DIRECTORY.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import (  # noqa: E402
    constraint_ui,
    document_state,
    draft_dispatch,
    general_session,
    general_sketch_overlay,
    general_viewport,
    register,
    sketch_session,
    unregister,
    workspace,
)
from mechanical_cad_blender.general_sketch_commands import (  # noqa: E402
    AddArc,
    AddCircle,
    AddLine,
    AddRelation,
    DeleteBatch,
    PointSeed,
    SetConstruction,
)
from mechanical_cad_blender.general_sketch_draft import GeneralSketchDraft  # noqa: E402

checks = []


def check(value, label):
    assert value, label
    checks.append(label)


def wait(owner, context):
    deadline = time.monotonic() + 30
    while owner.pending is not None and time.monotonic() < deadline:
        owner.tick(context)
        time.sleep(0.01)
    check(owner.pending is None and not owner.error, "Native work completes: " + owner.error)


def finish(owner, context):
    with patch.object(workspace, "request_workspace"):
        owner.request_finish(context)
        wait(owner, context)


def frame(owner):
    geometry = owner.geometry()
    return general_sketch_overlay.build_frame(
        geometry,
        lambda world: world[:2],
        annotations=owner.draft.annotations,
        current_request_fingerprint=geometry.request_fingerprint,
    )


def add(owner, context, mode, source_kind, identifier):
    constraint_ui.select_bindings(owner, ((source_kind, identifier),), context=context)
    request = owner.commands.solve_request()
    response = owner.current_solution_response()
    evidence = owner.guarded_evidence
    revision = owner.commands.revision
    check(
        bpy.ops.mcad.sketch_reference_dimension(mode=mode) == {"FINISHED"},
        "Add reference through registered operator",
    )
    check(
        owner.commands.solve_request() == request and owner.commands.revision == revision,
        "Reference adds no solver command or request change",
    )
    check(
        owner.current_solution_response() == response and owner.guarded_evidence is evidence,
        "Reference preserves exact native validation",
    )


register()
reopen = os.environ.get("MCAD_REF_REOPEN")
if reopen:
    bpy.ops.wm.open_mainfile(filepath=str(DIRECTORY / "references.blend"))
window = bpy.context.window
area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
region = next(r for r in area.regions if r.type == "WINDOW")
with bpy.context.temp_override(window=window, area=area, region=region):
    context = bpy.context
    state = context.scene.mechanical_cad
    if reopen:
        expected = json.loads((DIRECTORY / "expected.json").read_text())
        check(
            state.document_json == expected["document"],
            "Fresh reopen preserves canonical Part bytes",
        )
        check(
            state.sketch_annotation_json == expected["layout"],
            "Fresh reopen preserves accepted reference metadata",
        )
        check(
            state.sketch_draft_json == expected["draft"],
            "Fresh reopen preserves suspended reference UI",
        )
        draft = draft_dispatch.restore(state.sketch_draft_json, state.document_json)
        check(
            len(draft.annotations) == 5 and not draft.command_draft.has_current_solution,
            "Suspended references restore without solver authority",
        )
        sketch_session._discard_stored(context.scene)
        owner = general_session.GeneralSession(context, expected["feature"])
        owner.start()
        owner.check(context)
        wait(owner, context)
        check(
            len(frame(owner).labels) == 4, "Accepted references render after a fresh native Check"
        )
        check(
            any(label.text == "⌀ 12 mm (REF)" for label in frame(owner).labels),
            "Reopened measurement derives the fresh solved radius",
        )
        owner.cleanup()
        marker = "MCAD_REFERENCE_DIMENSION_REOPEN_OK"
    else:
        blank = {
            "schema_version": 1,
            "id": "reference_part",
            "name": "Reference Part",
            "units": "mm",
            "parameters": {},
            "features": [],
            "active_feature": None,
        }
        draft = GeneralSketchDraft(json.dumps(blank), journal_version=3)
        _, circle = draft.execute(AddCircle(PointSeed(0, 0), 5)).entity_ids
        driver = draft.execute(AddRelation("radius", (circle,), value=5)).constraint_id
        *_, line = draft.execute(AddLine(PointSeed(20, 0), PointSeed(23, 4))).entity_ids
        *_, arc = draft.execute(
            AddArc(PointSeed(40, 0), PointSeed(45, 0), PointSeed(40, 5), "ccw")
        ).entity_ids
        draft.execute(SetConstruction((("line", line), ("arc", arc)), True))
        document_state._populate_document(context.scene, draft.candidate())
        feature = draft.feature_id
        owner = general_session.GeneralSession(context, feature)
        owner.start()
        owner.check(context)
        wait(owner, context)
        before = owner.commands.checkpoint_payload()
        for mode, kind, target in (
            ("length", "line", line),
            ("radius", "circle", circle),
            ("diameter", "circle", circle),
            ("diameter", "arc", arc),
        ):
            add(owner, context, mode, kind, target)
        check(
            owner.commands.checkpoint_payload() == before,
            "All reference actions preserve complete command checkpoint",
        )
        labels = frame(owner).labels
        check(
            len(labels) == 4
            and all("(REF)" in label.text and "~" not in label.text for label in labels),
            "Native solved measurements are distinctly read-only",
        )
        check(
            sorted(label.measured_mm for label in labels) == [5, 5, 10, 10],
            "Native line/circle/arc measured values",
        )
        general_viewport._open_field(owner, labels[0].constraint_id, (10, 10))
        check(
            owner.commands.pending_edit is None and owner.input_controller is None,
            "Reference double-click never creates driving input",
        )
        check(
            "Read-only" in owner.message and "Dimension" in owner.message,
            "Read-only click explains driving alternative",
        )
        line_ref = next(
            key for key, binding in owner.draft.annotations.items() if binding["refs"] == [line]
        )
        owner.execute(context, DeleteBatch(owner.commands.preview_delete((("line", line),))))
        wait(owner, context)
        check(
            any(
                item.identifier == line_ref and item.state == "missing"
                for item in owner.draft.status.annotations
            ),
            "Deleted geometry leaves an unavailable stable-ID reference",
        )
        check(len(frame(owner).labels) == 3, "Deleted target cannot display a stale measurement")
        owner.local_history(context)
        wait(owner, context)
        check(
            len(frame(owner).labels) == 4,
            "Exact authored identity restored by geometry Undo revives reference",
        )
        owner.begin_dimension(driver)
        owner.update_raw("6")
        owner.request_driver_accept(context)
        wait(owner, context)
        check(
            any(label.text == "⌀ 12 mm (REF)" for label in frame(owner).labels),
            "Reference follows accepted native driver change",
        )
        owner.local_history(context)
        wait(owner, context)
        check(
            any(label.text == "⌀ 10 mm (REF)" for label in frame(owner).labels),
            "Existing geometry Undo updates reference value",
        )
        owner.local_history(context, redo=True)
        wait(owner, context)
        check(
            any(label.text == "⌀ 12 mm (REF)" for label in frame(owner).labels),
            "Existing geometry Redo updates reference value",
        )
        finish(owner, context)
        accepted, layout = state.document_json, state.sketch_annotation_json
        check(bool(layout), "Finish saves references separately from canonical Part")
        context.preferences.edit.use_global_undo = True
        bpy.ops.ed.undo_push(message="Accepted reference measurements")
        owner = general_session.GeneralSession(context, feature)
        owner.start()
        owner.check(context)
        wait(owner, context)
        for key in tuple(owner.draft.annotations):
            request, response = owner.commands.solve_request(), owner.current_solution_response()
            evidence = owner.guarded_evidence
            check(
                bpy.ops.mcad.remove_reference_dimension(annotation_id=key) == {"FINISHED"},
                "Remove Reference uses registered operator",
            )
            check(
                owner.commands.solve_request() == request
                and owner.current_solution_response() == response
                and owner.guarded_evidence is evidence,
                "Removal preserves native validation and geometry",
            )
        finish(owner, context)
        without = state.sketch_annotation_json
        check(
            state.document_json == accepted and without != layout,
            "Reference-only Finish preserves exact canonical bytes",
        )
        bpy.ops.ed.undo_push(message="Removed reference measurements")
        check(bpy.ops.ed.undo() == {"FINISHED"}, "Native scene Undo succeeds")
        state = context.scene.mechanical_cad
        check(
            state.sketch_annotation_json == layout and state.document_json == accepted,
            "Native scene Undo restores exact references and Part",
        )
        check(bpy.ops.ed.redo() == {"FINISHED"}, "Native scene Redo succeeds")
        state = context.scene.mechanical_cad
        check(
            state.sketch_annotation_json == without and state.document_json == accepted,
            "Native scene Redo removes references without changing Part",
        )
        check(bpy.ops.ed.undo() == {"FINISHED"}, "Restore accepted references for reopen")
        state = context.scene.mechanical_cad
        owner = general_session.GeneralSession(context, feature)
        owner.start()
        owner.check(context)
        wait(owner, context)
        add(owner, context, "radius", "arc", arc)
        owner.suspend("Reference persistence test")
        expected = {
            "feature": feature,
            "document": state.document_json,
            "layout": state.sketch_annotation_json,
            "draft": state.sketch_draft_json,
        }
        (DIRECTORY / "expected.json").write_text(json.dumps(expected))
        bpy.ops.wm.save_as_mainfile(filepath=str(DIRECTORY / "references.blend"))
        marker = "MCAD_REFERENCE_DIMENSION_SMOKE_OK"

unregister()
print(marker, len(checks), flush=True)
