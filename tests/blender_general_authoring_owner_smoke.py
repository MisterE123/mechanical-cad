"""General v2 dispatch through the unchanged shared native-headless owner.

This test-only subclass is not a registered editor and installs no handlers.
Native timers, scene identity, Undo, save/independent reopen and disable exercise
the shared lifecycle only. Picking, text focus and viewport usability are not
qualified here. Run native Blender with --python-exit-code 1.
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
EVIDENCE = Path(
    os.environ.get(
        "MCAD_GENERAL_OWNER_EVIDENCE",
        ROOT.parent / "cad_engineering_evidence/general_authoring_owner",
    )
).resolve()
EVIDENCE.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / "blender_addon"))
import mechanical_cad_blender as addon  # noqa: E402
from mechanical_cad_blender import (  # noqa: E402
    draft_dispatch,
    draft_store,
    general_authoring_store,
    general_draft_store,
    registration,
    sketch_session,
    viewport_sketch,
)
from mechanical_cad_blender.general_authoring import GeneralSketchAuthoringState  # noqa: E402
from mechanical_cad_blender.general_sketch_draft import (  # noqa: E402
    AddCircle,
    AddLine,
    AddRelation,
    GeneralSketchDraft,
    PointRef,
    PointSeed,
)
from mechanical_cad_blender.sketch_draft import DraftError, RectangleDraft  # noqa: E402

BASE = '{"schema_version":1,"id":"doc","name":"Part","units":"mm","parameters":{},"features":[],"active_feature":null}\n'
RAW_INPUT = " \t invalid + ( 半径 🛠 \n"
MARKER = "MCAD_GENERAL_AUTHORING_OWNER_RESULT="
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


def authoring(base=BASE, *, proposal="line", pending=True):
    command = GeneralSketchDraft(base)
    first, second, line = command.execute(AddLine(PointSeed(0, 0), PointSeed(3, 4))).entity_ids
    center, circle = command.execute(AddCircle(PointSeed(8, 9), 4.125)).entity_ids
    distance = command.execute(AddRelation("distance", (first, second), value=5)).constraint_id
    radius = command.execute(AddRelation("radius", (circle,), value="4 + 0.125")).constraint_id
    result = GeneralSketchAuthoringState(command)
    result.select((("line", line), ("circle", circle)))
    result.place_annotation(distance, (2, -3))
    result.place_annotation(radius, (7.25, -8))
    if proposal == "line":
        result.begin_line(PointRef(second), (12.25, -3))
    else:
        result.begin_circle(PointRef(center), 6.25)
    result.select_tool("Dimension")
    if pending:
        result.command_draft.begin_edit(radius)
        result.command_draft.update_edit(RAW_INPUT)
    return result


class HeadlessAuthoringOwner(sketch_session.SketchSession):
    """Test-only owner; no modal input, native editor or extra lifecycle route."""

    detach_count = 0

    def start(self):
        self.start_resources((), "General authoring headless lifecycle test")

    def _detach_input(self):
        check(not self.alive, "Test owner is retired before input detach")
        check(sketch_session.active_session() is None, "Detach sees no active shared owner")
        self.detach_count += 1


def cleaned(owner):
    check(not owner.alive and owner.timer is None and not owner.handles, "Owner resources retired")
    check(
        owner.detach_count == 1 and not owner.cleanup_errors, "Input detach runs once without error"
    )
    check(sketch_session.active_session() is None, "Shared active registry is empty")
    owner.cleanup()
    check(owner.detach_count == 1, "Repeated cleanup does not reenter input teardown")


def restored(snapshot, base):
    before = snapshot
    result = draft_dispatch.restore(snapshot, base)
    check(
        type(result) is GeneralSketchAuthoringState, "V2 restores the exact authoring wrapper type"
    )
    check(draft_dispatch.dumps(result) == before, "Restored v2 command/UI snapshot remains exact")
    check(
        not result.command_draft.has_current_solution
        and not result.command_draft.has_verified_trial,
        "Restoration carries no solver or trial authority",
    )
    check(
        result.tool == "Dimension" and len(result.annotations) == 2, "Tool and placements retained"
    )
    check(len(result.selection) == 2, "Stable selection retained")
    check(
        result.command_draft.pending_edit.raw_text == RAW_INPUT, "Invalid Unicode raw text is exact"
    )
    check(
        sketch_session.active_session() is None,
        "Restoring intent does not start input capture or native ownership",
    )
    return result


def available_editor():
    status = viewport_sketch.suspended_draft(bpy.context)
    check(status["compatible"] and status["editor_available"], "General editor route is available")
    reports = []
    fake = SimpleNamespace(report=lambda _level, message: reports.append(message))
    snapshot = state().sketch_draft_json
    with patch.object(viewport_sketch, "_begin_in_sketch") as begin:
        check(
            viewport_sketch.MCAD_OT_resume_sketch.execute(fake, bpy.context) == {"FINISHED"},
            "Production Resume selects the supported general editor",
        )
        check(
            begin.call_args.kwargs == {"editor": "mcad.general_sketch", "resume_saved": True},
            "General Resume uses exact kind dispatch",
        )
    check(not reports, "Supported Resume needs no unavailable-editor warning")
    check(state().sketch_draft_json == snapshot, "Dispatch preserves saved snapshot bytes")


addon.register()
phase = os.environ.get("MCAD_GENERAL_OWNER_PHASE", "save")
if phase == "reopen":
    path = Path(os.environ["MCAD_GENERAL_OWNER_BLEND"])
    expected = json.loads(path.with_suffix(".expected.json").read_text())
    check(bpy.ops.wm.open_mainfile(filepath=str(path)) == {"FINISHED"}, "Native reopen succeeds")
    scene = bpy.data.scenes[expected["scene_name"]]
    bpy.context.window.scene = scene
    check(state().document_json == expected["document"], "Fresh process keeps exact committed base")
    check(
        state().sketch_draft_json == expected["snapshot"], "Fresh process keeps exact v2 slot bytes"
    )
    check(
        state().sketch_draft_scene_id == expected["scene_id"],
        "Saved scene identity survives without binding to an old runtime UID",
    )
    check(sketch_session.active_session() is None, "File reopen creates no live owner")
    check("unverified" in state().sketch_notice, "Reopen visibly marks evidence unverified")
    check(
        bpy.data.scenes[expected["unrelated_scene"]].mechanical_cad.sketch_draft_json
        == expected["unrelated_snapshot"],
        "Unrelated saved scene slot remains independent",
    )
    with override():
        available_editor()
        intent = restored(state().sketch_draft_json, state().document_json)
        check(intent.ui_payload() == expected["ui"], "Fresh process retains all UI intent")
        check(
            intent.candidate() == expected["candidate"], "Fresh process retains accepted geometry"
        )
        check(intent.revision == expected["revision"], "Fresh process retains command revision")
        intent.command_draft.cancel_edit()
        before = draft_dispatch.dumps(intent)
        for _ in range(3):
            check(
                intent.resume_proposal() == expected["ui"]["proposal"],
                "Continue is observation only",
            )
        check(
            draft_dispatch.dumps(intent) == before,
            "Continue never replays commands or accepts input",
        )
        check(sketch_session.active_session() is None, "Continue does not capture native input")
        # Explicit test-only owner construction is independent of modal UI dispatch.
        owner = HeadlessAuthoringOwner(
            bpy.context,
            draft_dispatch.restore(state().sketch_draft_json, state().document_json),
            restored=True,
        )
        owner.start()
        check(owner.valid_context(), "Shared original-base guard accepts wrapper on explicit start")
        check(owner.suspend("Fresh-process test"), "Restored wrapper suspends through shared owner")
        cleaned(owner)
        check(
            state().sketch_draft_json == expected["snapshot"],
            "Suspend never rewrites restored intent",
        )
elif phase == "save":
    state().document_json = BASE
    scene = bpy.context.scene
    scene.name = "General authoring original"
    original_uid = scene.session_uid
    with override():
        # Inspect coexisting payloads; only rectangle-v1 has a production editor.
        rectangle = RectangleDraft(BASE)
        rectangle.first_point((1, 2))
        rectangle.second_point((11, 22))
        v1 = authoring().command_draft
        snapshots = [
            draft_dispatch.dumps(rectangle),
            draft_dispatch.dumps(v1),
            draft_dispatch.dumps(authoring()),
            draft_dispatch.dumps(authoring(proposal="circle", pending=False)),
        ]
        check(snapshots[0] == draft_store.dumps(rectangle), "Rectangle-v1 codec bytes unchanged")
        check(snapshots[1] == general_draft_store.dumps(v1), "General-v1 codec bytes unchanged")
        check(
            type(draft_dispatch.restore(snapshots[1], BASE)) is GeneralSketchDraft,
            "General-v1 never becomes a wrapper implicitly",
        )
        other_scenes = []
        for index, snapshot in enumerate(snapshots):
            other = bpy.data.scenes.new(f"Saved codec {index}")
            other.mechanical_cad.document_json = BASE
            other.mechanical_cad.sketch_draft_json = snapshot
            other_scenes.append(other)
        for index in (2, 0, 3, 1, 2):
            bpy.context.window.scene = other_scenes[index]
            info = draft_dispatch.inspect(state().sketch_draft_json)
            check(
                info.schema_version == (1 if index < 2 else 2),
                "Mixed slot version inspected exactly",
            )
            status = viewport_sketch.suspended_draft(bpy.context)
            check(status["compatible"], "Mixed saved slot has its exact base")
            check(
                status["editor_available"],
                "Rectangle and general v1/v2 have explicit editor routes",
            )
            if index:
                available_editor()
        bpy.context.window.scene = scene

        intent = authoring()
        owner = HeadlessAuthoringOwner(bpy.context, intent)
        owner.start()
        check(owner.valid_context(), "Wrapper document_json satisfies shared context guard")
        check(
            owner.draft.candidate() == intent.command_draft.candidate(),
            "Wrapper candidate delegates",
        )
        check(
            owner.draft.revision == intent.command_draft.revision,
            "Wrapper command revision delegates",
        )
        check(
            not viewport_sketch.MCAD_OT_finish_sketch.poll(bpy.context)
            and not viewport_sketch.MCAD_OT_sketch_dimensions.poll(bpy.context),
            "Headless owner grants no rectangle editor capabilities",
        )
        snapshot = owner.checkpoint()
        check(
            snapshot == general_authoring_store.dumps(intent),
            "Shared checkpoint selects exact v2 codec",
        )
        check(
            scene.session_uid == original_uid,
            "Checkpoint preserves original runtime scene identity",
        )
        check(state().document_json == BASE, "Checkpoint never publishes candidate geometry")
        command_revision, candidate = intent.revision, intent.candidate()
        intent.move_annotation(next(iter(intent.annotations)), (11.25, -19))
        newer = owner.checkpoint()
        check(newer != snapshot, "UI-only change is retained by same reserved slot")
        check(
            intent.revision == command_revision and intent.candidate() == candidate,
            "UI leaves geometry intact",
        )
        check(owner.checkpoint() == newer, "Repeated checkpoint is an exact-byte no-op")
        check(
            owner.suspend("Suspend pending raw text"), "Wrapper suspends through shared lifecycle"
        )
        cleaned(owner)
        restored(newer, BASE)
        available_editor()

        # Whitespace-only base changes must not silently rebase either payload.
        state().document_json = BASE.rstrip()
        check(
            not viewport_sketch.suspended_draft(bpy.context)["compatible"],
            "Exact-base mismatch is visible",
        )
        try:
            draft_dispatch.restore(newer, state().document_json)
        except draft_dispatch.SnapshotError:
            pass
        else:
            raise AssertionError("V2 silently rebased onto different committed bytes")
        check(
            state().sketch_draft_json == newer, "Failed exact-base restoration retains raw snapshot"
        )
        state().document_json = BASE
        sketch_session._discard_stored(scene)

        # Invalid escaped Unicode and unknown versions stay untouched in the native slot.
        for invalid_kind in ("surrogate", "version"):
            envelope = json.loads(newer)
            if invalid_kind == "surrogate":
                envelope["draft"]["pending_edit"]["raw_text"] = "broken\ud800"
            else:
                envelope["schema_version"] = 3
            raw = json.dumps(envelope, ensure_ascii=True)
            state().sketch_draft_json = raw
            status = viewport_sketch.suspended_draft(bpy.context)
            check(status["present"] and not status["compatible"], "Invalid saved slot fails closed")
            check(not status["editor_available"], "Invalid slot cannot advertise an editor")
            check(
                state().sketch_draft_json == raw,
                "Invalid original saved bytes stay available for Discard",
            )
            sketch_session._discard_stored(scene)

        owner = HeadlessAuthoringOwner(bpy.context, authoring(proposal="circle"))
        owner.start()
        owner.checkpoint()
        expected_recovery = draft_dispatch.dumps(owner.draft)
        state().sketch_draft_json = snapshots[1]
        try:
            owner.checkpoint()
        except DraftError:
            pass
        else:
            raise AssertionError("Checkpoint overwrote external scene slot")
        check(
            state().sketch_draft_json == snapshots[1], "Checkpoint CAS preserves external v1 bytes"
        )
        check(
            not owner.suspend("External slot conflict"),
            "Suspension reports checkpoint CAS conflict",
        )
        cleaned(owner)
        recovery = sketch_session._RECOVERY_DRAFTS[owner.session_id]
        check(recovery["snapshot"] == expected_recovery, "Conflicted v2 intent retained separately")
        check(
            recovery["scene_uid"] == original_uid,
            "Recovery binds to original scene runtime identity",
        )
        check(state().sketch_draft_json == snapshots[1], "Recovery never overwrites external draft")
        del sketch_session._RECOVERY_DRAFTS[owner.session_id]
        sketch_session._discard_stored(scene)

        owner = HeadlessAuthoringOwner(bpy.context, authoring())
        owner.start()
        source_snapshot = draft_dispatch.dumps(owner.draft)
        destination = other_scenes[1]
        destination_snapshot = destination.mechanical_cad.sketch_draft_json
        bpy.context.window.scene = destination
        check(not owner.valid_context(), "Scene switch invalidates active original-scene context")
        check(owner.suspend("Different scene"), "Scene switch saves only the original slot")
        cleaned(owner)
        check(
            scene.mechanical_cad.sketch_draft_json == source_snapshot,
            "Source scene retains exact v2 bytes",
        )
        check(
            state().sketch_draft_json == destination_snapshot,
            "Destination's v1 slot is never replaced",
        )
        check(state().document_json == BASE, "Destination canonical bytes remain untouched")
        bpy.context.window.scene = scene

        owner = HeadlessAuthoringOwner(bpy.context, restored(source_snapshot, BASE), restored=True)
        owner.start()
        path = EVIDENCE / "general_authoring_owner.blend"
        check(
            bpy.ops.wm.save_as_mainfile(filepath=str(path)) == {"FINISHED"},
            "Native save checkpoints v2",
        )
        check(owner.alive, "Saving leaves explicit active ownership intact")
        expected = {
            "scene_name": scene.name,
            "scene_id": state().sketch_draft_scene_id,
            "document": BASE,
            "snapshot": draft_dispatch.dumps(owner.draft),
            "ui": owner.draft.ui_payload(),
            "candidate": owner.draft.candidate(),
            "revision": owner.draft.revision,
            "unrelated_scene": destination.name,
            "unrelated_snapshot": destination_snapshot,
        }
        check(
            state().sketch_draft_json == expected["snapshot"],
            "Save handler uses shared v2 dispatch",
        )
        path.with_suffix(".expected.json").write_text(json.dumps(expected, ensure_ascii=False))
        completed = subprocess.run(
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
            env=dict(
                os.environ,
                MCAD_ROOT=str(ROOT),
                MCAD_GENERAL_OWNER_PHASE="reopen",
                MCAD_GENERAL_OWNER_BLEND=str(path),
                MCAD_GENERAL_OWNER_EVIDENCE=str(EVIDENCE),
            ),
            text=True,
            capture_output=True,
            timeout=180,
        )
        (EVIDENCE / "native_reopen.log").write_text(completed.stdout + completed.stderr)
        print(completed.stdout)
        print(completed.stderr)
        results = [
            line[len(MARKER) :] for line in completed.stdout.splitlines() if line.startswith(MARKER)
        ]
        check(
            completed.returncode == 0
            and len(results) == 1
            and json.loads(results[0])["phase"] == "reopen"
            and json.loads(results[0])["ok"],
            "Independent native Blender process validates v2 persistence",
        )
        owner.draft.select_tool("Circle")
        disable_snapshot = draft_dispatch.dumps(owner.draft)
        # A synthetic failed-report label checks storage only, never geometry evidence.
        state().geometry_report_json = '{"fixture":"unverified storage regression"}'
        state().geometry_document_json = BASE
        state().geometry_status = "FAILED"
        state().geometry_message = "Fixture failure; no geometry was verified."
        geometry_fields = (
            "geometry_report_json",
            "geometry_document_json",
            "geometry_status",
            "geometry_message",
        )
        geometry_before = tuple(getattr(state(), name) for name in geometry_fields)
        addon.unregister()
        cleaned(owner)
        addon.register()
        check(
            state().sketch_draft_json == disable_snapshot,
            "Disable retains latest UI rather than old saved UI",
        )
        check(state().document_json == BASE, "Disable/reenable preserves committed base")
        check(
            tuple(getattr(state(), name) for name in geometry_fields[:2]) == geometry_before[:2],
            "RNA callback rebind preserves exact historical failed-report bytes and source",
        )
        check(
            state().geometry_status == "OUTDATED"
            and "fresh verification" in state().geometry_message,
            "Re-enabled historical report explicitly requires fresh verification",
        )
        check(
            not addon.document_state.geometry_report_is_current(bpy.context),
            "Saved failed-report storage cannot recreate runtime geometry authority",
        )
        check(
            state().sketch_draft_scene_id == expected["scene_id"],
            "Disable preserves saved scene identity",
        )
        sketch_session._discard_stored(bpy.context.scene)

        # Real Undo/Redo replaces Scene RNA, preserving current draft by runtime UID.
        bpy.ops.ed.undo_push(message="Before general committed change")
        changed = json.loads(BASE)
        changed["name"] = "General native history revision"
        changed_base = json.dumps(changed)
        state().document_json = changed_base
        bpy.ops.ed.undo_push(message="After general committed change")
        owner = HeadlessAuthoringOwner(bpy.context, authoring(changed_base))
        owner.start()
        history_snapshot = draft_dispatch.dumps(owner.draft)
        check(bpy.ops.ed.undo() == {"FINISHED"}, "Native Undo runs with active v2 owner")
        cleaned(owner)
        check(
            bpy.context.scene.session_uid == original_uid,
            "Undo restores exact runtime scene identity",
        )
        check(
            state().sketch_draft_json == history_snapshot,
            "Native Undo keeps latest UI and invalid raw text",
        )
        check(
            not viewport_sketch.suspended_draft(bpy.context)["compatible"],
            "Undo mismatch remains explicitly stale",
        )
        check(bpy.ops.ed.redo() == {"FINISHED"}, "Native Redo restores original draft base")
        check(state().sketch_draft_json == history_snapshot, "Native Redo retains exact v2 intent")
        available_editor()
        restored(history_snapshot, changed_base)
        for _ in range(3):
            registration._before_history_change(None)
            registration._after_history_change(None)
        check(
            state().sketch_draft_json == history_snapshot,
            "Repeated shared history hooks retain v2 bytes",
        )
        sketch_session._discard_stored(bpy.context.scene)

        # A same-named replacement cannot inherit a deleted original's authoring intent.
        main_scene = bpy.context.scene
        removed = bpy.data.scenes.new("Removed authoring source")
        removed.mechanical_cad.document_json = BASE
        bpy.context.window.scene = removed
        removed_uid, removed_name = removed.session_uid, removed.name
        bpy.ops.ed.undo_push(message="General original scene exists")
        owner = HeadlessAuthoringOwner(bpy.context, authoring())
        owner.start()
        missing_snapshot = draft_dispatch.dumps(owner.draft)
        bpy.context.window.scene = main_scene
        bpy.data.scenes.remove(removed)
        replacement = bpy.data.scenes.new(removed_name)
        replacement.mechanical_cad.document_json = BASE
        check(
            replacement.session_uid != removed_uid,
            "Same name does not create original scene identity",
        )
        check(
            not owner.suspend("Original scene deleted"),
            "Missing original scene retains recovery intent",
        )
        cleaned(owner)
        check(
            not replacement.mechanical_cad.sketch_draft_json,
            "Same-named replacement receives no v2 draft",
        )
        check(
            not state().sketch_draft_json, "Unrelated active scene receives no deleted-scene draft"
        )
        check(
            sketch_session._RECOVERY_DRAFTS[owner.session_id]["scene_uid"] == removed_uid,
            "Deleted-scene recovery keeps original runtime UID",
        )
        bpy.ops.ed.undo_push(message="General original scene deleted")
        check(bpy.ops.ed.undo() == {"FINISHED"}, "Native Undo restores deleted original scene")
        recovered = next(
            (item for item in bpy.data.scenes if item.session_uid == removed_uid), None
        )
        check(recovered is not None, "Restored original scene has its exact runtime UID")
        check(
            recovered.mechanical_cad.sketch_draft_json == missing_snapshot,
            "Only original scene recovers exact v2 bytes",
        )
        check(
            owner.session_id not in sketch_session._RECOVERY_DRAFTS,
            "Persisted exact restoration releases backup",
        )
        bpy.context.window.scene = recovered
        restored(missing_snapshot, BASE)
        sketch_session._discard_stored(recovered)
else:
    raise AssertionError(f"Unsupported test phase: {phase}")

check(
    not any(name == "OCP" or name.startswith("OCP.") or name == "slvs" for name in sys.modules),
    "Native backend never imports into Blender",
)
addon.unregister()
check(sketch_session.active_session() is None, "Final disable has no active owner")
print(
    MARKER
    + json.dumps(
        {"ok": True, "phase": phase, "checks": len(checks), "blender": bpy.app.version_string}
    )
)
