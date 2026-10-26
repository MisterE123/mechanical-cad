"""Real constrained-draft transactions and modal lifecycle under Blender.

Run with MCAD_ROOT/MCAD_PYTHON and --background --factory-startup
--python-exit-code 1 --python tests/blender_viewport_sketch_smoke.py, or standalone
bpy Python. Native mouse/keyboard rendering is a separate GUI acceptance gate.
"""

import json
import math
import os
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
os.environ["MCAD_ROOT"] = str(ROOT)
os.environ.setdefault("MCAD_PYTHON", str(ROOT / ".venv" / "bin" / "python"))
sys.path.insert(0, str(ROOT / "blender_addon"))
import mechanical_cad_blender as addon  # noqa: E402
from mechanical_cad_blender import (  # noqa: E402
    geometry_operations,
    guarded_transport,
    registration,
    viewport_sketch,
    workspace,
)
from mechanical_cad_blender.sketch_draft import DraftError, RectangleDraft  # noqa: E402

checks = []
timings = {}


def check(condition, message):
    assert condition, message
    checks.append(message)


def state():
    return bpy.context.scene.mechanical_cad


def feature():
    return next(row for row in state().features if row.feature_id == "sketch_1")


def start(context, edit=False):
    session = viewport_sketch.RectangleSession(context, "sketch_1" if edit else "")
    session.start()
    check(
        viewport_sketch.active_session(context) is session,
        "Draft is owned by the current window and scene",
    )
    check(session.valid_context(), "Draft context starts valid")
    return session


def cleaned(session):
    check(
        not session.alive and not session.handles and session.timer is None,
        "Cleanup removes preview handles and modal timer",
    )
    check(viewport_sketch.active_session() is None, "Cleanup releases global draft ownership")


addon.register()
check(
    bpy.ops.mcad.new_document(name="Viewport constrained plate") == {"FINISHED"},
    "Blank CAD document created",
)
window = bpy.context.window
area = next(area for area in window.screen.areas if area.type == "VIEW_3D")
region = next(region for region in area.regions if region.type == "WINDOW")
with bpy.context.temp_override(window=window, area=area, region=region):
    context = bpy.context
    original = state().document_json
    session = start(context)
    session.draft.first_point((0, 0))
    modal = viewport_sketch.MCAD_OT_rectangle_sketch.modal
    fake_operator = SimpleNamespace(session=session)
    move_event = SimpleNamespace(type="MOUSEMOVE", value="NOTHING", mouse_x=200, mouse_y=200)
    with (
        patch.object(session, "over_viewport", return_value=True),
        patch.object(session, "pointer_mm", return_value=(40, 30)),
        patch.object(
            workspace_ui := viewport_sketch.workspace_ui, "is_palette_event", return_value=False
        ),
        patch.object(viewport_sketch.document_state, "_run_sidecar") as sidecar,
    ):
        started = time.perf_counter()
        for _ in range(1000):
            modal(fake_operator, context, move_event)
        timings["pointer_1000_events_seconds"] = time.perf_counter() - started
        check(sidecar.call_count == 0, "Rapid pointer motion never starts a native sidecar")
        check(session.draft.solver_report is None, "Moving preview has no current DoF claim")
    check(session.draft.second_point((40, 30)), "Two clicks establish the rectangle draft")
    check(
        session.solve(context),
        "Real sidecar solves the uncommitted rectangle: " + session.draft.error,
    )
    check(session.draft.solver_report["remaining_dof"] == 0, "DoF comes from the real solver")
    check(
        state().document_json == original and not state().features,
        "Preview does not mutate canonical history",
    )
    check(
        not addon._owned_objects(context.scene),
        "Preview creates no display mesh or last-good cache",
    )
    modal = viewport_sketch.MCAD_OT_rectangle_sketch.modal
    fake_operator = SimpleNamespace(session=session)
    for event_type in ("MIDDLEMOUSE", "WHEELUPMOUSE", "TRACKPADPAN", "NUMPAD_7"):
        event = SimpleNamespace(type=event_type, value="RELEASE")
        check(
            modal(fake_operator, context, event) == {"PASS_THROUGH"},
            "Navigation event passes through the sketch modal",
        )
    with (
        patch.object(workspace, "request_workspace", return_value=True) as request,
        patch.object(
            viewport_sketch.document_state,
            "_run_sidecar",
            wraps=viewport_sketch.document_state._run_sidecar,
        ) as fresh_replay,
    ):
        started = time.perf_counter()
        check(session.finish(context), "Finish commits one constrained feature")
        check(fresh_replay.call_count == 1, "Successful Finish uses exactly one fresh replay")
        timings["create_commit_seconds"] = time.perf_counter() - started
        check(request.call_args.args[1] == "PART", "Finish requests the actual Part workspace")
    cleaned(session)
    document = json.loads(state().document_json)
    check(
        document["schema_version"] == 2 and len(document["features"]) == 1,
        "Finish explicitly creates schema-2 constrained history",
    )
    check(
        feature().sketch_report_status == "CURRENT",
        "Committed feature caches its actual solver report",
    )
    check(
        json.loads(feature().sketch_report_json)["remaining_dof"] == 0,
        "Committed history exposes actual zero DoF",
    )
    check(
        bpy.ops.mcad.add_extrude(profile="sketch_1", length=10) == {"FINISHED"},
        "Constrained profile extrudes through existing Part feature operator",
    )
    solid_id = state().active_feature
    check(
        math.isclose(state().volume, 12000, rel_tol=1e-6),
        "Initial solid has 40 × 30 × 10 mm volume",
    )
    committed = state().document_json
    original_seeds = json.loads(committed)["features"][0]["sketch"]["points"]
    session = start(context, edit=True)
    check(session.solve(context), "Original sketch is editable")
    session.draft.set_dimensions("60", session.draft.height_text)
    check(session.solve(context), "Changed width solves and validates downstream features")
    check(
        state().document_json == committed and math.isclose(state().volume, 12000),
        "Edited preview leaves committed solid unchanged until Finish",
    )
    with patch.object(workspace, "request_workspace", return_value=True):
        check(session.finish(context), "Finish accepts upstream sketch edit")
    cleaned(session)
    document = json.loads(state().document_json)
    check(
        len(document["features"]) == 2 and document["features"][0]["id"] == "sketch_1",
        "Upstream edit preserves feature identity and history length",
    )
    check(
        document["active_feature"] == solid_id, "Upstream edit preserves downstream active output"
    )
    check(
        document["features"][0]["sketch"]["points"] == original_seeds,
        "Dimension editing does not rewrite authoring seeds from solved coordinates",
    )
    check(
        math.isclose(state().volume, 18000, rel_tol=1e-6),
        "The same solid rebuilds to 60 × 30 × 10 mm",
    )
    session = start(context, edit=True)
    check(
        session.initialize_preview(context), "Position edit starts from current solver coordinates"
    )
    fixed_json = state().document_json
    before_release = session.draft.points()
    session.draft.set_dimensions("60", session.draft.height_text, fix_corner=False)
    check(session.solve(context), "Free-position rectangle remains a valid closed profile")
    check(
        all(
            math.isclose(a, b, abs_tol=1e-9)
            for old, new in zip(before_release, session.draft.points(), strict=True)
            for a, b in zip(old, new, strict=True)
        ),
        "Releasing only the anchor preserves the visible solved rectangle",
    )
    check(state().document_json == fixed_json, "Position reseeding stays transient until Finish")
    check(
        session.draft.solver_report["remaining_dof"] == 2,
        "Removing only anchor leaves two real translational DoF",
    )
    with patch.object(workspace, "request_workspace", return_value=True):
        check(
            session.finish(context), "Free-position upstream sketch commits and remains extrudable"
        )
    cleaned(session)
    free_document = json.loads(state().document_json)
    check(
        not any(
            item["id"] == "anchor" for item in free_document["features"][0]["sketch"]["constraints"]
        ),
        "Free-position history stores no anchor constraint",
    )
    check(
        math.isclose(state().volume, 18000),
        "Free-position rectangle rebuilds the same downstream volume",
    )
    with tempfile.TemporaryDirectory(prefix="mcad-free-position-") as directory:
        path = Path(directory) / "free.mcad.json"
        saved_free = state().document_json
        check(
            bpy.ops.mcad.save_document(filepath=str(path)) == {"FINISHED"},
            "Released-position sketch saves as authoritative JSON",
        )
        bpy.ops.mcad.new_document(name="Reopen free-position regression")
        check(
            bpy.ops.mcad.load_document(filepath=str(path)) == {"FINISHED"},
            "Released-position document reopens through a fresh native replay",
        )
        check(
            state().document_json == saved_free,
            "Reopen preserves the explicit position edit exactly",
        )
        report = json.loads(feature().sketch_report_json)
        check(
            report["remaining_dof"] == 2 and math.isclose(state().volume, 18000),
            "Reopened free rectangle retains genuine two DoF and downstream volume",
        )
        p0 = next(point for point in report["solved"]["points"] if point["id"] == "p0")
        check(
            math.isclose(p0["u"], before_release[0][0], abs_tol=1e-9)
            and math.isclose(p0["v"], before_release[0][1], abs_tol=1e-9),
            "Reopened free rectangle retains released placement",
        )
    state().document_path = ""
    session = start(context, edit=True)
    check(session.initialize_preview(context), "Free-position sketch can be edited again")
    session.draft.set_dimensions("75", session.draft.height_text, fix_corner=False)
    check(session.solve(context), "Changing a free rectangle dimension uses the real solver")
    solved_origin = next(
        point for point in session.draft.solver_report["solved"]["points"] if point["id"] == "p0"
    )
    check(
        session.draft.anchor == (solved_origin["u"], solved_origin["v"]),
        "Free preview position follows actual solved coordinates",
    )
    refix_origin = session.draft.anchor
    session.draft.set_dimensions("60", session.draft.height_text, fix_corner=True)
    check(
        session.solve(context) and session.draft.solver_report["remaining_dof"] == 0,
        "Re-fixing current position restores genuine zero DoF",
    )
    with patch.object(workspace, "request_workspace", return_value=True):
        check(session.finish(context), "Re-fixed rectangle commits without recreating features")
    cleaned(session)
    fixed_document = json.loads(state().document_json)
    check(
        fixed_document["features"][0]["sketch"]["constraints"][0]["target"] == list(refix_origin),
        "Re-fix saves the displayed solved corner rather than an old seed",
    )
    check(
        fixed_document["features"][0]["sketch"]["points"]
        == free_document["features"][0]["sketch"]["points"],
        "Re-fixing preserves the explicitly released-position seeds",
    )
    check(
        [point["id"] for point in fixed_document["features"][0]["sketch"]["points"]]
        == [point["id"] for point in original_seeds],
        "Explicit position reseeding preserves every point ID",
    )
    check(
        fixed_document["active_feature"] == solid_id and len(fixed_document["features"]) == 2,
        "Position toggle preserves feature identities and active downstream solid",
    )
    committed = state().document_json
    session = start(context, edit=True)
    check(session.initialize_preview(context), "Release cancellation starts from the current part")
    session.draft.set_dimensions(
        session.draft.width_text, session.draft.height_text, fix_corner=False
    )
    check(session.solve(context), "A transient anchor release solves before cancellation")
    session.cleanup()
    cleaned(session)
    check(
        state().document_json == committed,
        "Cancelling a release restores original JSON byte-for-byte",
    )
    session = start(context, edit=True)
    with patch.object(viewport_sketch.document_state, "_run_sidecar") as sidecar:
        check(
            session.initialize_preview(context),
            "Edit reuses an exact current successful solver report",
        )
        check(
            sidecar.call_count == 0,
            "A current cache avoids blocking on a second Edit-opening replay",
        )
    check(
        session.draft.width == 60,
        "Edit opening uses current solved dimensions rather than old seeds",
    )
    session.popup_open = True
    check(
        viewport_sketch.MCAD_OT_sketch_dimensions.poll(context),
        "Native dimension confirmation remains pollable while its own popup is open",
    )
    check(
        not viewport_sketch.MCAD_OT_finish_sketch.poll(context),
        "Finish cannot commit while dimensions are being edited",
    )
    popup = SimpleNamespace(
        session=session, width="60", height=session.draft.height_text, fix_position=True
    )
    popup._close_later = lambda: viewport_sketch.MCAD_OT_sketch_dimensions._close_later(popup)
    check(
        viewport_sketch.MCAD_OT_sketch_dimensions.execute(popup, context) == {"FINISHED"},
        "Dimensions Apply updates the draft and schedules modal release",
    )
    close_callback = session.popup_close_timer
    check(
        close_callback is not None and bpy.app.timers.is_registered(close_callback),
        "Popup cleanup is scheduled independently of operator lifetime",
    )
    bpy.app.timers.unregister(close_callback)
    close_callback()
    check(
        not session.popup_open and session.popup_close_timer is None,
        "Deferred popup close re-enables Finish and Dimensions",
    )
    last_good_outline = session.draft.points()
    session.draft.set_dimensions("-5", session.draft.height_text)
    check(
        session.draft.solver_report is None,
        "Changed dimensions invalidate the prior DoF report immediately",
    )
    check(not session.solve(context), "Invalid typed width is rejected by the backend")
    with tempfile.TemporaryDirectory(prefix="mcad-draft-export-") as directory:
        destination = Path(directory) / "blocked.step"
        try:
            geometry_operations.run_geometry_action(
                context, "export_step", destination=str(destination)
            )
        except RuntimeError as exc:
            check(
                "Finish or cancel" in str(exc),
                "Export explicitly requires finishing or cancelling the draft",
            )
        else:
            raise AssertionError(
                "Export must not silently export an older committed solid while a draft is active"
            )
        check(not destination.exists(), "Invalid transient sketch cannot create an export file")
    check(
        session.draft.width_text == "-5" and session.draft.points() == last_good_outline,
        "Invalid text and last valid outline are retained",
    )
    session.draft.set_dimensions("60mm", session.draft.height_text)
    check(
        not session.solve(context) and "not 60mm" in session.draft.error,
        "Rejected unit suffix gives actionable millimetre-only input guidance",
    )
    with patch.object(workspace, "request_workspace", return_value=True):
        check(not session.finish(context), "Invalid Finish cannot alter committed history")
    check(
        session.alive and state().document_json == committed,
        "Rejected Finish keeps the draft editable and the prior document intact",
    )
    session.cleanup()
    cleaned(session)
    check(math.isclose(state().volume, 18000), "Cancel preserves the committed solid")
    session = start(context, edit=True)
    check(
        session.initialize_preview(context),
        "Backend-failure case begins with a genuine current solver cache",
    )
    with patch.object(
        guarded_transport,
        "execute",
        side_effect=addon.bridge.BridgeError("Injected preview transport failure"),
    ):
        check(not session.solve(context), "Preview transport failure leaves an actionable error")
    check(
        session.draft.error and state().document_json == committed and state().status == "READY",
        "Preview backend failure does not destroy current valid CAD output",
    )
    check(
        viewport_sketch.document_state.part_is_current(context),
        "Ordinary preview failure preserves the original live committed evidence",
    )
    with patch.dict(os.environ, {"MCAD_PYTHON": str(ROOT / "missing-python")}):
        check(not session.solve(context), "Missing backend leaves an actionable draft error")
    check(
        session.draft.solver_report is None and not session.draft.validated_json,
        "Backend failure cannot leave an old DoF result looking current",
    )
    check(
        session.draft.error and state().document_json == committed and state().status == "DIRTY",
        "Observed backend change preserves canonical output but revokes its current status",
    )
    check(
        not viewport_sketch.document_state.part_is_current(context),
        "Restoring the backend path cannot revive old committed evidence",
    )
    session.cleanup()
    cleaned(session)
    check(addon.regenerate(context), "Explicit replay with corrected backend restores current CAD")
    check(
        state().document_json == committed, "Corrected-backend recovery preserves canonical bytes"
    )
    session = start(context, edit=True)
    other = bpy.data.scenes.new("Temporary context-loss test")
    window.scene = other
    check(
        modal(SimpleNamespace(session=session), context, SimpleNamespace(type="TIMER"))
        == {"CANCELLED"},
        "Scene context loss ends the modal without committing",
    )
    check(
        "No draft changes were committed" in other.mechanical_cad.sketch_notice,
        "Context-loss destination visibly records draft suspension as a notice",
    )
    window.scene = session.scene
    check(
        "suspended" in state().sketch_notice,
        "Source scene retains the nonerror suspension notice",
    )
    bpy.data.scenes.remove(other)
    cleaned(session)
    bpy.ops.mcad.discard_suspended_sketch()
    session = start(context, edit=True)
    check(
        not state().sketch_notice, "Starting after explicit Discard clears the prior draft notice"
    )
    bpy.ops.object.mode_set(mode="EDIT")
    check(
        modal(SimpleNamespace(session=session), context, SimpleNamespace(type="TIMER"))
        == {"CANCELLED"},
        "Entering Blender mesh Edit Mode suspends CAD modal ownership",
    )
    bpy.ops.object.mode_set(mode="OBJECT")
    cleaned(session)
    check(
        state().document_json == committed,
        "Blender mode context loss leaves canonical sketch unchanged",
    )
    bpy.ops.mcad.discard_suspended_sketch()
    session = start(context, edit=True)
    registration._before_history_change(None)
    cleaned(session)
    check(state().document_json == committed, "Undo/Redo cleanup itself does not mutate history")
    registration._after_history_change(None)
    bpy.ops.mcad.discard_suspended_sketch()
    next(row for row in state().parameters if row.key == "sketch_1_width").expression = "65"
    check(
        feature().sketch_report_status == "OUTDATED",
        "External parameter edits invalidate solver status",
    )
    check(bpy.ops.mcad.regenerate() == {"FINISHED"}, "External parameter edit regenerates")
    check(
        feature().sketch_report_status == "CURRENT",
        "Regeneration replaces the derived solver report",
    )
    check(
        feature().sketch_document_json == state().document_json,
        "Solver cache is bound to the exact current document",
    )
    # Imported constraints can solve to a mirrored distance branch even with
    # positive authoring seeds. This bounded editor must reject that branch in
    # both Apply and direct Finish, without changing the accepted CAD model.
    replay = viewport_sketch.document_state
    saved_before_branches = state().document_json
    seed_draft = RectangleDraft(original)
    seed_draft.first_point((5, 7))
    seed_draft.second_point((45, 37))
    positive_candidate = seed_draft.candidate()
    for axis, centre in (("u", 5), ("v", 7)):
        mirrored = json.loads(json.dumps(positive_candidate))
        for point in mirrored["features"][0]["sketch"]["points"]:
            point[axis] = 2 * centre - point[axis]
        check(replay._commit_candidate(context, mirrored), "Mirrored imported CAD remains valid")
        branch_json = state().document_json
        try:
            viewport_sketch.RectangleSession(context, "sketch_1")
        except DraftError as exc:
            check("+X/+Y" in str(exc), "Mirrored source ordering has a bounded editor diagnostic")
        else:
            raise AssertionError("Mirrored imported seeds must not enter the rectangle editor")
        check(state().document_json == branch_json, "Unsupported source ordering stays unchanged")
    for target in ([100, 7], [5, 100], [100, 100]):
        reversed_solution = json.loads(json.dumps(positive_candidate))
        reversed_solution["features"][0]["sketch"]["constraints"][0]["target"] = target
        check(
            replay._commit_candidate(context, reversed_solution),
            "Positive seeds with a reversed solved branch import as valid CAD",
        )
        branch_json = state().document_json
        session = start(context, edit=True)
        check(
            not session.initialize_preview(context),
            "A reversed actual solution has no verified preview",
        )
        check(
            "+X/+Y" in session.draft.error
            and session.draft.solver_report is None
            and not session.draft.validated_json,
            "Unsupported solved orientation clears cached DoF and validation",
        )
        session.cleanup()
        cleaned(session)
        session = start(context, edit=True)
        with patch.object(replay, "_run_sidecar", wraps=replay._run_sidecar) as fresh_replay:
            check(
                not session.finish(context),
                "Direct Finish without Apply rejects a reversed solution",
            )
            check(fresh_replay.call_count == 1, "Rejected Finish uses exactly one fresh replay")
        check(
            state().document_json == branch_json and state().status == "READY",
            "Rejected orientation leaves the exact canonical model and its valid status intact",
        )
        check(
            session.alive
            and session.draft.solver_report is None
            and not session.draft.validated_json,
            "Rejected Finish retains the draft but no false current solver claim",
        )
        session.cleanup()
        cleaned(session)
    replay._commit_candidate(context, json.loads(saved_before_branches))
    # A validator sees only the freshly replayed candidate. Neither candidate
    # mutation nor an intervening canonical edit may be accepted afterward.
    for mutate_base in (False, True):
        before_validation = state().document_json
        candidate = json.loads(before_validation)

        def change_snapshot(
            _result,
            _binding,
            mutate_base=mutate_base,
            before_validation=before_validation,
            candidate=candidate,
        ):
            if mutate_base:
                state().document_json = before_validation + " "
            else:
                candidate["name"] = "Changed after replay"

        try:
            with replay.replay_guard(context):
                replay._commit_candidate_locked(context, candidate, validate_result=change_snapshot)
        except replay.bridge.BridgeError as exc:
            check(
                "changed during validation" in str(exc),
                "Changed validation snapshots cannot commit",
            )
        else:
            raise AssertionError("A changed candidate/base must not consume the fresh result")
        check(
            state().document_json == before_validation + (" " if mutate_base else ""),
            "Snapshot rejection does not overwrite canonical state",
        )
        state().document_json = before_validation
    example = json.loads((ROOT / "examples" / "constrained_plate.mcad.json").read_text())
    check(
        viewport_sketch.document_state._commit_candidate(bpy.context, example),
        "A general schema-2 constrained example imports and replays",
    )
    example_json = state().document_json
    try:
        RectangleDraft(example_json, feature_id=example["features"][0]["id"], is_edit=True)
    except DraftError as exc:
        check(
            "four-corner rectangle" in str(exc),
            "Unsupported general constrained sketch has a clear editor limitation",
        )
    else:
        raise AssertionError(
            "The specialized rectangle editor must not rewrite an arbitrary constrained sketch"
        )
    check(
        state().document_json == example_json and math.isclose(state().volume, 12000),
        "Unsupported edit preserves imported identity and solid",
    )
    viewport_sketch.document_state._commit_candidate(context, json.loads(committed))
    next(row for row in state().parameters if row.key == "sketch_1_width").expression = "65"
    bpy.ops.mcad.regenerate()
    with tempfile.TemporaryDirectory(prefix="mcad-sketch-") as directory:
        path = Path(directory) / "constrained.blend"
        check(
            bpy.ops.wm.save_as_mainfile(filepath=str(path)) == {"FINISHED"},
            "Constrained document saves in .blend",
        )
        saved_json = state().document_json
        bpy.ops.wm.open_mainfile(filepath=str(path))
        check(state().document_json == saved_json, "Reopen preserves constrained JSON exactly")
        check(
            feature().sketch_report_status == "OUTDATED",
            "Reopen marks cached solver result unverified",
        )
        check(bpy.ops.mcad.regenerate() == {"FINISHED"}, "Reopened constrained part regenerates")
        check(
            math.isclose(state().volume, 19500, rel_tol=1e-6),
            "Saved edited part retains correct dimensions",
        )
check(
    not any(name == "OCP" or name.startswith("OCP.") or name == "slvs" for name in sys.modules),
    "Native kernel and solver remain isolated from Blender",
)
addon.unregister()
check(viewport_sketch.active_session() is None, "Unregister leaves no active draft")
print(
    "MCAD_VIEWPORT_SKETCH_RESULT="
    + json.dumps(
        {
            "ok": True,
            "blender": bpy.app.version_string,
            "check_count": len(checks),
            "timings": timings,
        }
    )
)
