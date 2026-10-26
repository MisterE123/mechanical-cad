"""Annotation layout is UI-only, atomically published, and survives real reopen."""

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import bpy

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
os.environ["MCAD_ROOT"] = str(ROOT)
os.environ.setdefault("MCAD_PYTHON", str(ROOT / ".venv/bin/python"))
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import (  # noqa: E402
    document_state,
    general_session,
    part_publication,
    register,
    sketch_annotation_store,
    sketch_session,
    unregister,
    workspace,
)
from mechanical_cad_blender.general_sketch_commands import AddRelation, PointSeed  # noqa: E402

checks = []


def check(value, label):
    assert value, label
    checks.append(label)


def wait(owner, context):
    deadline = time.monotonic() + 20
    while owner.pending is not None and time.monotonic() < deadline:
        owner.tick(context)
        time.sleep(0.01)
    check(owner.pending is None, "Native annotation transaction reaches a terminal state")
    return not owner.error


def finish(owner, context):
    with patch.object(workspace, "request_workspace"):
        owner.request_finish(context)
        return wait(owner, context)


register()
if os.environ.get("MCAD_ANNOTATION_REOPEN"):
    path = os.environ["MCAD_ANNOTATION_REOPEN"]
    expected = json.loads(Path(path + ".json").read_text())
    bpy.ops.wm.open_mainfile(filepath=path)
    state = bpy.context.scene.mechanical_cad
    check(
        state.sketch_annotation_json == expected["layout"], "Fresh process preserves exact layout"
    )
    check(
        state.document_json == expected["document"], "Fresh process preserves exact canonical Part"
    )
    check(
        state.sketch_draft_json == expected["draft"],
        "Fresh process preserves failed draft separately",
    )
    sketch_session._discard_stored(bpy.context.scene)  # explicit test recovery choice
    window = bpy.context.window
    area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
    region = next(r for r in area.regions if r.type == "WINDOW")
    with bpy.context.temp_override(window=window, area=area, region=region):
        owner = general_session.GeneralSession(bpy.context, expected["feature"])
        check(
            owner.draft.annotations[expected["constraint"]]["offset"] == [12.0, -3.0],
            "New edit restores saved placement",
        )
        owner.cleanup()
    unregister()
    print("SKETCH_ANNOTATION_REOPEN_OK", len(checks))
else:
    window = bpy.context.window
    area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
    region = next(r for r in area.regions if r.type == "WINDOW")
    with bpy.context.temp_override(window=window, area=area, region=region):
        context = bpy.context
        state = context.scene.mechanical_cad
        document_state._populate_document(
            context.scene,
            {
                "schema_version": 1,
                "id": "layout_part",
                "name": "Layout Part",
                "units": "mm",
                "parameters": {},
                "features": [],
                "active_feature": None,
            },
        )
        owner = general_session.GeneralSession(context)
        owner.start()
        owner.draft.begin_circle(PointSeed(0, 0), 5)
        ids = owner.accept_proposal(context)
        check(wait(owner, context), owner.error)
        relation = owner.execute(context, AddRelation("radius", (ids[-1],), value=5))
        check(wait(owner, context), owner.error)
        owner.draft.place_annotation(relation.constraint_id, (8, 9))
        owner.checkpoint()
        feature = owner.draft.feature_id
        check(
            state.sketch_annotation_json == "",
            "Unfinished placement does not alter accepted layout",
        )
        check(finish(owner, context), owner.error)
        accepted = state.document_json
        first_layout = state.sketch_annotation_json
        check(bool(first_layout), "Finish publishes accepted layout")
        sketch_annotation_store.validate(first_layout)
        context.preferences.edit.use_global_undo = True
        bpy.ops.ed.undo_push(message="Original annotation layout")
        owner = general_session.GeneralSession(context, feature)
        check(
            owner.draft.annotations[relation.constraint_id]["offset"] == [8.0, 9.0],
            "Reopen finds stable annotation binding",
        )
        owner.start()
        owner.check(context)
        check(wait(owner, context), owner.error)
        revision = owner.commands.revision
        before_request = owner.commands.solve_request()
        owner.draft.move_annotation(relation.constraint_id, (12, -3))
        owner.checkpoint()
        check(owner.commands.revision == revision, "Moving annotation adds no command history")
        check(
            owner.commands.solve_request() == before_request,
            "Layout does not change native request or geometry identity",
        )
        check(state.document_json == accepted, "Moving annotation does not edit canonical Part")
        check(finish(owner, context), owner.error)
        check(state.document_json == accepted, "Layout-only Finish preserves canonical bytes")
        accepted_layout = state.sketch_annotation_json
        check(accepted_layout != first_layout, "New layout is saved independently")
        bpy.ops.ed.undo_push(message="Moved annotation layout")
        check(bpy.ops.ed.undo() == {"FINISHED"}, "Actual Undo restores annotation placement")
        state = context.scene.mechanical_cad
        check(state.sketch_annotation_json == first_layout, "Undo restores exact original layout")
        check(state.document_json == accepted, "Layout Undo preserves exact canonical geometry")
        check(bpy.ops.ed.redo() == {"FINISHED"}, "Actual Redo reapplies annotation placement")
        state = context.scene.mechanical_cad
        check(state.sketch_annotation_json == accepted_layout, "Redo restores exact moved layout")
        check(state.document_json == accepted, "Layout Redo preserves exact canonical geometry")

        owner = general_session.GeneralSession(context, feature)
        owner.start()
        owner.check(context)
        check(wait(owner, context), owner.error)
        owner.draft.move_annotation(relation.constraint_id, (99, 99))
        owner.checkpoint()
        before_objects = tuple(obj.as_pointer() for obj in context.scene.objects)
        original = part_publication.PartPublicationIntent._write_layout

        def partial_failure(state, raw):
            original(state, raw)
            raise RuntimeError("Injected layout write failure")

        with patch.object(
            part_publication.PartPublicationIntent, "_write_layout", staticmethod(partial_failure)
        ):
            check(not finish(owner, context), "Layout write failure rejects complete publication")
        check("Injected layout" in owner.error, "Failure remains explicit")
        check(state.document_json == accepted, "Layout failure restores canonical Part exactly")
        check(
            state.sketch_annotation_json == accepted_layout,
            "Layout failure restores old layout exactly",
        )
        check(
            tuple(obj.as_pointer() for obj in context.scene.objects) == before_objects,
            "Layout failure restores original display objects",
        )
        check(
            owner.alive
            and owner.draft.annotations[relation.constraint_id]["offset"] == [99.0, 99.0],
            "Rejected layout remains in editable draft",
        )

        # Fresh replay still needs exact old layout, even when geometry is identical.
        owner.request_finish(context)
        external = sketch_annotation_store.replace_annotations(
            accepted_layout, "other_part", "other_feature", {}
        )
        # {} alone normalizes to the same store, so explicitly use valid different text.
        external += "\n"
        state.sketch_annotation_json = external
        check(not wait(owner, context), "Late UI metadata change rejects publication")
        check(
            state.sketch_annotation_json == external, "New external layout text is not overwritten"
        )
        check(state.document_json == accepted, "Late layout conflict preserves canonical Part")
        state.sketch_annotation_json = accepted_layout  # restore fixture's accepted UI state
        owner.suspend("Annotation save/reopen test")
        with tempfile.TemporaryDirectory(prefix="mcad-layout-") as directory:
            path = str(Path(directory) / "annotations.blend")
            expected = {
                "layout": accepted_layout,
                "document": accepted,
                "draft": state.sketch_draft_json,
                "feature": feature,
                "constraint": relation.constraint_id,
            }
            Path(path + ".json").write_text(json.dumps(expected))
            bpy.ops.wm.save_as_mainfile(filepath=path)
            env = dict(os.environ, MCAD_ANNOTATION_REOPEN=path)
            process = subprocess.run(
                [
                    bpy.app.binary_path,
                    "--background",
                    "--factory-startup",
                    "--python-exit-code",
                    "1",
                    "--python-expr",
                    "import sys; sys.dont_write_bytecode = True",
                    "--python",
                    str(Path(__file__).resolve()),
                ],
                env=env,
                capture_output=True,
                text=True,
                timeout=45,
            )
            check(
                process.returncode == 0 and "SKETCH_ANNOTATION_REOPEN_OK 4" in process.stdout,
                process.stdout + process.stderr,
            )
            print(process.stdout)
    unregister()
    print("SKETCH_ANNOTATION_SMOKE_OK", len(checks))
