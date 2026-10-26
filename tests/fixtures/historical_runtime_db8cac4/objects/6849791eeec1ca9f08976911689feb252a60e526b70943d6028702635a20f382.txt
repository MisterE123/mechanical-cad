"""Native draft lifecycle and fresh-process .blend UI-state persistence checks.

Run with --background --factory-startup --python-exit-code 1. This deliberately
exercises native RNA, event timers, handlers, file I/O, Undo and the real sidecar;
interactive workspace clicks and popup typing have a separate GUI acceptance gate.
"""

import copy
import json
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
os.environ["MCAD_ROOT"] = str(ROOT)
os.environ.setdefault("MCAD_PYTHON", str(ROOT / ".venv/bin/python"))
sys.path.insert(0, str(ROOT / "blender_addon"))
import mechanical_cad_blender as addon  # noqa: E402
from mechanical_cad_blender import (  # noqa: E402
    document_state,
    draft_store,
    geometry_operations,
    registration,
    workspace,  # noqa: E402
)
from mechanical_cad_blender import viewport_sketch as viewport  # noqa: E402
from mechanical_cad_blender.sketch_draft import DraftError, RectangleDraft  # noqa: E402

checks = []


def check(condition, message):
    assert condition, message
    checks.append(message)


def state():
    return bpy.context.scene.mechanical_cad


def override():
    window = bpy.context.window
    area = next(area for area in window.screen.areas if area.type == "VIEW_3D")
    region = next(region for region in area.regions if region.type == "WINDOW")
    return bpy.context.temp_override(window=window, area=area, region=region)


def begin(edit=True):
    session = viewport.RectangleSession(bpy.context, "sketch_1" if edit else "")
    session.start()
    return session


def resume():
    restored = draft_store.restore(state().sketch_draft_json, state().document_json, RectangleDraft)
    session = viewport.RectangleSession(bpy.context, restored=restored)
    session.start()
    return session


def cleaned(session):
    check(not session.alive, "Suspension releases session lifetime")
    check(not session.handles and session.timer is None, "No draw handler or modal timer leaks")
    check(session.popup_close_timer is None, "No popup-close timer leaks")
    check(viewport.active_session() is None, "No global live session leaks")


addon.register()
phase = os.environ.get("MCAD_DRAFT_PHASE", "save")
if phase == "reopen":
    path = Path(os.environ["MCAD_DRAFT_BLEND"])
    bpy.ops.wm.open_mainfile(filepath=str(path))
    expected = json.loads(path.with_suffix(".expected.json").read_text())
    check(
        state().document_json == expected["document"], "Fresh process retains exact committed base"
    )
    check(
        state().sketch_draft_json == expected["draft"],
        "Fresh process retains exact UI snapshot bytes",
    )
    check(viewport.active_session() is None, "File load never starts a modal session")
    check("unverified" in state().sketch_notice, "Load visibly labels the saved draft unverified")
    with override():
        session = resume()
        check(
            session.draft.width_text == expected["width"],
            "Invalid width whitespace survives fresh process",
        )
        check(
            session.draft.height_text == expected["height"], "Invalid height survives fresh process"
        )
        check(
            session.draft.pending_dimensions == expected["pending"],
            "Unapplied dialog raw input survives fresh process",
        )
        check(
            session.draft.seed_override == expected["seeds"],
            "Released anchor seeds survive fresh process",
        )
        check(
            session.draft.solver_report is None and not session.draft.validated_json,
            "Loaded draft cannot reuse a saved DoF claim",
        )
        check(
            session.draft.base_hash == expected["hash"], "Expected base hash survives fresh process"
        )
        session.discard()
        cleaned(session)
        check(not state().sketch_draft_json, "Explicit Cancel clears the fresh-process draft slot")
        check(
            state().document_json == expected["document"],
            "Fresh-process Cancel preserves canonical JSON",
        )
else:
    check(
        bpy.ops.mcad.load_document(filepath=str(ROOT / "examples/viewport_rectangle.mcad.json"))
        == {"FINISHED"},
        "Load editable real-kernel fixture",
    )
    with override():
        context = bpy.context
        original = state().document_json
        session = begin()
        check(session.initialize_preview(context), "Initialize original real solver outline")
        # Real registered RNA wrapper regression: property callbacks do not
        # receive the Python Operator instance or its custom ``session`` field.
        # Bind the wrapper as invoke() binds a native popup, then let Blender
        # dispatch actual StringProperty/BoolProperty updates.
        properties = context.window_manager.operator_properties_last("mcad.sketch_dimensions")
        check(
            not hasattr(properties, "session"),
            "Native RNA callback wrapper has no Python session attribute",
        )
        properties.draft_input_token = ""
        properties.width = session.draft.width_text
        properties.height = session.draft.height_text
        properties.fix_position = session.draft.fix_corner
        session.popup_open = True
        session.dimensions_input_token = "native-rna-regression-token"
        properties.width = "ignored unowned input"
        check(
            session.draft.pending_dimensions is None,
            "Unowned native RNA updates cannot change live draft input",
        )
        properties.draft_input_token = session.dimensions_input_token
        applied_before_pending = session.draft.candidate()
        properties.width = "  64 + (  "
        properties.height = " invalid_height\t "
        properties.fix_position = False
        expected_pending = {
            "width": "  64 + (  ",
            "height": " invalid_height\t ",
            "fix_corner": False,
        }
        check(
            session.draft.pending_dimensions == expected_pending,
            "Real RNA callbacks retain exact invalid pending strings and position intent",
        )
        check(
            session.draft.candidate() == applied_before_pending,
            "Pending native RNA input does not silently apply to the draft",
        )
        check(
            state().document_json == original,
            "Pending native RNA input does not commit canonical changes",
        )
        check(
            session.draft.solver_report is None and not session.draft.validated_json,
            "Native pending edits clear all previous DoF currentness",
        )
        check(
            session.suspend("Real RNA pending-input regression"),
            "Real RNA pending input suspends safely",
        )
        cleaned(session)
        saved_pending = state().sketch_draft_json
        check(
            draft_store.loads(saved_pending)["pending_dimensions"] == expected_pending,
            "Snapshot contains exact real RNA pending input",
        )
        properties.width = "stale callback after suspension"
        check(
            state().sketch_draft_json == saved_pending,
            "Closed popup RNA cannot mutate a suspended snapshot",
        )
        session = resume()
        check(
            session.draft.pending_dimensions == expected_pending,
            "Resume preserves real RNA pending edits",
        )
        properties.height = "stale callback after resume"
        check(
            session.draft.pending_dimensions == expected_pending,
            "Old dialog RNA token cannot change a resumed session",
        )
        session.draft.pending_dimensions = None
        session.draft.set_dimensions("60", session.draft.height_text)
        check(session.solve(context), "Validate changed width against native solver")
        solved_points = copy.deepcopy(session.draft.last_solved_points)
        session.draft.set_dimensions("  malformed +(  ", " 30mm\t ", fix_corner=False)
        check(
            session.draft.seed_override == solved_points,
            "Release preserves the last solved point identities",
        )
        session.draft.pending_dimensions = {
            "width": "  pending invalid(( \n",
            "height": "unknown_height",
            "fix_corner": True,
        }
        before = draft_store.dumps(session.draft)
        other = bpy.data.scenes.new("Unrelated draft context")
        source = context.scene
        context.window.scene = other
        check(
            viewport.MCAD_OT_rectangle_sketch.modal(
                SimpleNamespace(session=session), context, SimpleNamespace(type="TIMER")
            )
            == {"CANCELLED"},
            "Native scene switch suspends modal without committing",
        )
        cleaned(session)
        check(
            not other.mechanical_cad.sketch_draft_json,
            "Scene switch never transfers another scene's draft",
        )
        context.window.scene = source
        check(
            state().sketch_draft_json == before,
            "Scene suspension preserves exact raw and seed state",
        )
        check(state().document_json == original, "Scene suspension preserves committed model")
        bpy.data.scenes.remove(other)
        try:
            begin()
        except DraftError as exc:
            check(
                "Resume or Discard" in str(exc),
                "Starting another draft cannot overwrite a suspended draft",
            )
        else:
            raise AssertionError("Starting a new draft replaced the suspended slot")
        # Every normal canonical authoring route is guarded while a suspended
        # draft reserves its exact base. Errors must preserve both byte strings.
        with patch.object(document_state, "_run_sidecar") as blocked_sidecar:
            for label, operation in (
                ("New", lambda: bpy.ops.mcad.new_document(name="Must not replace")),
                ("Demo", lambda: bpy.ops.mcad.new_demo()),
                (
                    "Open",
                    lambda: bpy.ops.mcad.load_document(
                        filepath=str(ROOT / "examples/drilled_plate.mcad.json")
                    ),
                ),
                ("Activate", lambda: bpy.ops.mcad.activate_feature()),
                ("Rectangle", lambda: bpy.ops.mcad.add_rectangle(width=9, height=8)),
                ("Extrude", lambda: bpy.ops.mcad.add_extrude(profile="sketch_1", length=8)),
                ("Check", lambda: bpy.ops.mcad.check_geometry()),
            ):
                try:
                    result = operation()
                except RuntimeError:
                    result = {"CANCELLED"}
                check(result == {"CANCELLED"}, label + " is blocked while draft is suspended")
                check(state().document_json == original, label + " preserves exact committed base")
                check(state().sketch_draft_json == before, label + " preserves exact raw snapshot")
            parameter = next(row for row in state().parameters if row.key == "sketch_1_width")
            parameter.expression = "999"
            check(
                state().document_json == original, "Parameter callback cannot change suspended base"
            )
            check(
                parameter.expression == json.loads(original)["parameters"][parameter.key],
                "Parameter UI restores exact original expression",
            )
            parameter.is_expression = not parameter.is_expression
            check(
                state().document_json == original,
                "Parameter mode callback cannot change suspended base",
            )
            check(
                state().sketch_draft_json == before,
                "Parameter callbacks preserve exact suspended input",
            )
            with tempfile.TemporaryDirectory(prefix="mcad-suspended-export-") as directory:
                destination = Path(directory) / "blocked.step"
                try:
                    geometry_operations.run_geometry_action(
                        context, "export_step", destination=str(destination)
                    )
                except RuntimeError as exc:
                    check("Resume" in str(exc), "Suspended export explains Resume/Discard recovery")
                else:
                    raise AssertionError("Suspended export was permitted")
                check(
                    not destination.exists(),
                    "Suspended draft cannot export a committed stale interpretation",
                )
            check(
                blocked_sidecar.call_count == 0,
                "Blocked canonical actions never replay the native kernel",
            )
        check(
            state().document_json == original and state().sketch_draft_json == before,
            "All action gates preserve model and draft byte-for-byte",
        )
        changed = json.loads(original)
        changed["name"] = "External committed edit"
        state().document_json = json.dumps(changed)
        status = viewport.suspended_draft(context)
        check(
            status["present"] and not status["compatible"],
            "Changed committed base is marked incompatible",
        )
        check(
            "No automatic rebase" in status["message"],
            "Stale-base recovery explains fail-closed behavior",
        )
        try:
            resume()
        except draft_store.SnapshotError:
            pass
        else:
            raise AssertionError("Changed base was silently rebased")
        check(state().sketch_draft_json == before, "Failed Resume retains exact original snapshot")
        check(
            state().document_json == json.dumps(changed),
            "Failed Resume does not overwrite external edits",
        )
        state().document_json = original
        session = resume()
        check(
            session.draft.solver_report is None and not session.draft.validated_json,
            "Resume requires fresh validation",
        )
        check(
            session.draft.pending_dimensions["width"] == "  pending invalid(( \n",
            "Pending dialog text is exact after Resume",
        )
        check(
            not viewport.MCAD_OT_finish_sketch.poll(context),
            "Finish cannot silently ignore unapplied restored input",
        )
        check(not session.finish(context), "Direct Finish rejects unapplied restored input")
        session.draft.set_dimensions("60", "30", fix_corner=False)
        check(session.solve(context), "Resumed released-position draft validates freshly")
        check(
            session.draft.solver_report["remaining_dof"] == 2,
            "Resumed free rectangle has real two translational DoF",
        )
        check(
            session.draft.seed_override == solved_points,
            "Resume and validation never rewrite released authoring seeds",
        )
        session.draft.set_dimensions("60", "30", fix_corner=True)
        fixed_target = session.draft.fixed_target
        check(
            viewport.suspend_active("Navigate away", context), "Explicit navigation hook suspends"
        )
        cleaned(session)
        session = resume()
        check(
            session.draft.fixed_target == fixed_target, "Refix target survives suspension exactly"
        )
        check(
            session.draft.seed_override == solved_points,
            "Refix retains original released seed override",
        )
        check(session.solve(context), "Resumed refixed rectangle validates freshly")
        check(
            session.draft.solver_report["remaining_dof"] == 0,
            "Refixed resumed rectangle has real zero DoF",
        )
        for index in range(12):
            session.popup_open = True
            popup = SimpleNamespace(session=session)
            viewport.MCAD_OT_sketch_dimensions._close_later(popup)
            callback = session.popup_close_timer
            check(
                callback is not None and bpy.app.timers.is_registered(callback),
                "Popup cleanup timer exists before navigation",
            )
            check(
                session.suspend(f"Repeated navigation {index}"),
                "Repeated navigation saves one exact slot",
            )
            cleaned(session)
            check(
                not bpy.app.timers.is_registered(callback),
                "Suspension unregisters pending popup callback",
            )
            session = resume()
        session.draft.set_dimensions("  invalid_expression (  ", "30mm\t", fix_corner=False)
        session.draft.pending_dimensions = {
            "width": " raw pending ( ",
            "height": " ",
            "fix_corner": True,
        }
        with tempfile.TemporaryDirectory(prefix="mcad-draft-persistence-") as directory:
            path = Path(directory) / "suspended.blend"
            check(
                bpy.ops.wm.save_as_mainfile(filepath=str(path)) == {"FINISHED"},
                "Native .blend save checkpoints active UI draft",
            )
            check(session.alive, "Saving does not unexpectedly leave active editing")
            expected = {
                "document": original,
                "draft": state().sketch_draft_json,
                "width": session.draft.width_text,
                "height": session.draft.height_text,
                "pending": session.draft.pending_dimensions,
                "seeds": session.draft.seed_override,
                "hash": session.draft.base_hash,
            }
            path.with_suffix(".expected.json").write_text(json.dumps(expected))
            command = [
                bpy.app.binary_path,
                "--background",
                "--factory-startup",
                "--python-exit-code",
                "1",
                "--python-expr",
                "import sys; sys.dont_write_bytecode = True",
                "--python",
                str(Path(__file__).resolve()),
            ]
            completed = subprocess.run(
                command,
                env=dict(os.environ, MCAD_DRAFT_PHASE="reopen", MCAD_DRAFT_BLEND=str(path)),
                text=True,
                capture_output=True,
                timeout=180,
            )
            print(completed.stdout)
            print(completed.stderr)
            check(
                completed.returncode == 0 and '"phase": "reopen"' in completed.stdout,
                "Independent native Blender process verifies saved draft",
            )
        current_snapshot = draft_store.dumps(session.draft)
        addon.unregister()
        cleaned(session)
        addon.register()
        check(
            state().sketch_draft_json == current_snapshot,
            "Disable/re-enable retains scene-owned draft data",
        )
        session = resume()
        session.discard()
        cleaned(session)
        check(not state().sketch_draft_json, "Cancel clears the saved slot after Resume")
        check(
            state().document_json == original,
            "Cancel never commits draft dimensions or anchor changes",
        )
        session = begin()
        session.draft.set_dimensions("65", session.draft.height_text)
        session.suspend("Finish test")
        session = resume()
        with patch.object(workspace, "request_workspace", return_value=True):
            check(session.finish(context), "Freshly validated Finish commits resumed draft once")
        cleaned(session)
        check(not state().sketch_draft_json, "Successful Finish clears the reserved draft slot")
        check(
            math.isclose(state().volume, 19500, rel_tol=1e-6),
            "Resumed upstream edit rebuilds exact 65 × 30 × 10 solid",
        )
        before_features = json.loads(original)["features"]
        after_features = json.loads(state().document_json)["features"]
        check(
            [f["id"] for f in after_features] == [f["id"] for f in before_features],
            "Resume/Finish preserves all feature IDs",
        )
        check(
            after_features[0]["sketch"]["lines"] == before_features[0]["sketch"]["lines"],
            "Resume/Finish preserves all line and endpoint IDs",
        )
        committed = state().document_json
        session = begin()
        session.draft.set_dimensions("  undo pending(( ", "30")
        registration._before_history_change(None)
        saved = state().sketch_draft_json
        # The real callbacks bracket Blender replacing RNA/scene storage. Simulate
        # that replacement here; actual ed.undo below exercises native ordering.
        state().sketch_draft_json = ""
        state().document_json = original
        registration._after_history_change(None)
        check(
            state().sketch_draft_json == saved,
            "Undo post restores draft independently of canonical scene data",
        )
        check(
            not viewport.suspended_draft(context)["compatible"],
            "Undo to another base leaves the retained draft stale",
        )
        state().document_json = committed
        check(
            viewport.suspended_draft(context)["compatible"],
            "Returning to exact base makes the same draft resumable",
        )
        bpy.ops.mcad.discard_suspended_sketch()
        # Actual native global Undo replaces Scene/RNA instances and must preserve
        # draft identity through Blender's session_uid, never a name guess.
        bpy.ops.ed.undo_push(message="Before committed name edit")
        changed = json.loads(committed)
        changed["name"] = "Native undo revision"
        state().document_json = json.dumps(changed)
        bpy.ops.ed.undo_push(message="After committed name edit")
        session = begin()
        session.draft.set_dimensions("  native undo raw ( ", "30")
        expected_snapshot = draft_store.dumps(session.draft)
        check(bpy.ops.ed.undo() == {"FINISHED"}, "Native Undo runs successfully with draft active")
        check(viewport.active_session() is None, "Native Undo releases active resources first")
        check(
            state().sketch_draft_json == expected_snapshot,
            "Native Undo preserves exact latest draft snapshot",
        )
        check(
            not viewport.suspended_draft(bpy.context)["compatible"],
            "Native Undo rejects changed-base Resume",
        )
        check(bpy.ops.ed.redo() == {"FINISHED"}, "Native Redo restores committed revision")
        check(state().sketch_draft_json == expected_snapshot, "Native Redo retains raw draft input")
        check(
            viewport.suspended_draft(bpy.context)["compatible"],
            "Native Redo to original revision allows Resume",
        )
        bpy.ops.mcad.discard_suspended_sketch()

        # Explicit terminal decisions remain terminal when canonical Undo
        # restores an older RNA snapshot that happened to contain a draft.
        registration._before_history_change(None)
        state().sketch_draft_json = expected_snapshot
        registration._after_history_change(None)
        check(
            not state().sketch_draft_json,
            "Canonical Undo cannot resurrect an explicitly discarded draft",
        )
        main_scene = bpy.context.scene
        orphan = bpy.data.scenes.new("Deleted original draft scene")
        orphan.mechanical_cad.document_json = committed
        bpy.context.window.scene = orphan
        original_uid = orphan.session_uid
        bpy.ops.ed.undo_push(message="Original draft scene exists")
        session = begin()
        session.draft.set_dimensions(" exact orphan raw ( ", "30")
        orphan_snapshot = draft_store.dumps(session.draft)
        bpy.context.window.scene = main_scene
        bpy.data.scenes.remove(orphan)
        check(
            viewport.MCAD_OT_rectangle_sketch.modal(
                SimpleNamespace(session=session), bpy.context, SimpleNamespace(type="TIMER")
            )
            == {"CANCELLED"},
            "Deleted scene ends modal safely even after RNA identity disappears",
        )
        cleaned(session)
        check(
            "original scene was removed" in viewport.draft_recovery_notice(),
            "Deleted-scene recovery is visible",
        )
        check(
            not state().sketch_draft_json, "Deleted-scene draft never transfers into another scene"
        )
        bpy.ops.ed.undo_push(message="Original scene deleted")
        check(bpy.ops.ed.undo() == {"FINISHED"}, "Native Undo restores deleted original scene")
        recovered = next(
            (scene for scene in bpy.data.scenes if scene.session_uid == original_uid), None
        )
        check(recovered is not None, "Native Undo preserves original scene runtime identity")
        check(
            recovered.mechanical_cad.sketch_draft_json == orphan_snapshot,
            "Deleted scene recovers its own exact snapshot",
        )
        check(
            not viewport.draft_recovery_notice(),
            "Recovery notice clears after original scene returns",
        )
        bpy.context.window.scene = recovered
        bpy.ops.mcad.discard_suspended_sketch()

check(
    not any(name == "OCP" or name.startswith("OCP.") or name == "slvs" for name in sys.modules),
    "Kernel and solver remain isolated from Blender",
)
addon.unregister()
check(viewport.active_session() is None, "Final disable has no live session")
print(
    "MCAD_DRAFT_SUSPENSION_RESULT="
    + json.dumps(
        {"ok": True, "phase": phase, "blender": bpy.app.version_string, "check_count": len(checks)}
    )
)
