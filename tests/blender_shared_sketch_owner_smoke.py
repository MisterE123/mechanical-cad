"""Real Blender lifecycle invariants shared by rectangle/general pure drafts.

These tests exercise the shared owner seam and exact Resume dispatch without
launching a modal editor or claiming viewport usability.
"""

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
sys.path.insert(0, str(ROOT / "blender_addon"))
import mechanical_cad_blender as addon  # noqa: E402
from mechanical_cad_blender import draft_dispatch, registration, sketch_session, viewport_sketch  # noqa: E402
from mechanical_cad_blender.general_sketch_draft import AddCircle, GeneralSketchDraft, PointSeed  # noqa: E402
from mechanical_cad_blender.sketch_draft import DraftError, RectangleDraft  # noqa: E402

BASE = '{"schema_version":1,"id":"doc","name":"Part","units":"mm","parameters":{},"features":[],"active_feature":null}\n'
checks = []


def check(condition, message):
    assert condition, message
    checks.append(message)


def general():
    draft = GeneralSketchDraft(BASE)
    draft.execute(AddCircle(PointSeed(2, 3), 4))
    return draft


addon.register()
scene = bpy.context.scene
scene.mechanical_cad.document_json = BASE
area = next(area for area in bpy.context.window.screen.areas if area.type == "VIEW_3D")
region = next(region for region in area.regions if region.type == "WINDOW")
with bpy.context.temp_override(area=area, region=region):
    context = bpy.context
    session = sketch_session.SketchSession(context, general())
    second = sketch_session.SketchSession(context, RectangleDraft(BASE))
    session.start_resources((), "Shared owner regression")
    check(
        viewport_sketch.active_session() is session,
        "Compatibility API uses the one shared registry",
    )
    try:
        second.start_resources((), "Must not start")
    except DraftError:
        pass
    else:
        raise AssertionError("Two owners acquired the same registry")
    check(sketch_session.active_session() is session, "Rejected second start preserves first owner")
    # Unstarted cleanup cannot restore a cursor/status belonging to the first.
    second.window = SimpleNamespace(
        cursor_modal_restore=lambda: (_ for _ in ()).throw(AssertionError("unowned cursor"))
    )
    second.workspace = SimpleNamespace(
        status_text_set=lambda _x: (_ for _ in ()).throw(AssertionError("unowned status"))
    )
    second.cleanup()
    check(not second.cleanup_errors, "Unstarted owner touches no cursor or status ownership")
    check(
        sketch_session.active_session() is session,
        "Unstarted owner cleanup cannot clear another owner",
    )
    check(
        not viewport_sketch.MCAD_OT_finish_sketch.poll(context),
        "General owner has no rectangle Finish capability",
    )
    check(
        not viewport_sketch.MCAD_OT_sketch_dimensions.poll(context),
        "General owner has no rectangle dimension capability",
    )
    encoded = session.checkpoint()
    check(
        draft_dispatch.inspect(encoded).kind == draft_dispatch.GENERAL,
        "General codec shares existing slot",
    )
    check(session.suspend("Kind-independent test"), "Shared general owner suspends")
    check(session.timer is None and not session.alive, "General resources released")
    status = viewport_sketch.suspended_draft(context)
    check(
        status["compatible"] and status["editor_available"],
        "Supported general UI route is explicit",
    )
    reports = []
    fake_operator = SimpleNamespace(report=lambda level, message: reports.append(message))
    with patch.object(viewport_sketch, "_begin_in_sketch") as begin:
        result = viewport_sketch.MCAD_OT_resume_sketch.execute(fake_operator, context)
        check(result == {"FINISHED"} and not reports, "Resume accepts the supported general route")
        check(
            begin.call_args.kwargs == {"editor": "mcad.general_sketch", "resume_saved": True},
            "Resume cannot reinterpret general as rectangle",
        )
    check(
        scene.mechanical_cad.sketch_draft_json == encoded,
        "Dispatch leaves exact snapshot unchanged",
    )
    registration._before_history_change(None)
    scene.mechanical_cad.sketch_draft_json = ""
    registration._after_history_change(None)
    check(
        scene.mechanical_cad.sketch_draft_json == encoded,
        "One history hook restores general snapshot",
    )
    sketch_session._discard_stored(scene)

    # Original scene only: destination receives only the existing navigation notice.
    session = sketch_session.SketchSession(context, general())
    session.start_resources((), "Original scene")
    destination = bpy.data.scenes.new("Unrelated destination")
    destination.mechanical_cad.sketch_notice = "Keep unrelated notice"
    context.window.scene = destination
    check(session.suspend("Scene switch"), "Original scene accepts its own checkpoint")
    check(
        "No draft changes were committed" in destination.mechanical_cad.sketch_notice,
        "Destination receives only the existing navigation notice",
    )
    check(not destination.mechanical_cad.sketch_draft_json, "Destination slot untouched")
    context.window.scene = scene
    bpy.data.scenes.remove(destination)
    sketch_session._discard_stored(scene)

    # Slot CAS fails closed, cleanup still runs, recovery stays original-scene bound.
    session = sketch_session.SketchSession(context, general())
    session.start_resources((), "CAS")
    scene.mechanical_cad.sketch_draft_json = "external untouched bytes"
    check(not session.suspend("Conflict"), "External slot conflict is explicit")
    check(
        scene.mechanical_cad.sketch_draft_json == "external untouched bytes",
        "Conflict never overwrites saved bytes",
    )
    check(
        sketch_session._RECOVERY_DRAFTS[session.session_id]["snapshot"],
        "Pure recovery snapshot retained",
    )
    check(
        not session.alive and session.timer is None and sketch_session.active_session() is None,
        "Conflict still releases all ownership",
    )
    scene.mechanical_cad.sketch_draft_json = ""
    sketch_session._RECOVERY_DRAFTS.clear()

    # Discarding the external slot is not permission to replace an older
    # interrupted session's separate conflict copy on the next conflict.
    held = []
    for radius in (4, 8):
        draft = GeneralSketchDraft(BASE)
        draft.execute(AddCircle(PointSeed(2, 3), radius))
        interrupted = sketch_session.SketchSession(context, draft)
        interrupted.start_resources((), "Repeated CAS")
        held.append(draft_dispatch.dumps(draft))
        scene.mechanical_cad.sketch_draft_json = f"external {radius}"
        check(not interrupted.suspend("Repeated conflict"), "Repeated conflict stays explicit")
        if radius == 4:
            sketch_session._discard_stored(scene)
    saved = [record["snapshot"] for record in sketch_session._RECOVERY_DRAFTS.values()]
    check(
        all(snapshot in saved for snapshot in held),
        "Both interrupted sessions retain distinct conflict copies",
    )
    check(
        scene.mechanical_cad.sketch_draft_json == "external 8",
        "Latest external slot remains untouched",
    )
    sketch_session.after_file_load()
    check(
        all(record["previous_file"] for record in sketch_session._RECOVERY_DRAFTS.values()),
        "Conflict copies quarantine across file boundaries",
    )
    sketch_session._RECOVERY_DRAFTS.clear()
    scene.mechanical_cad.sketch_draft_json = ""

    # Encoding failure cannot skip retirement or destroy the in-memory pure draft.
    session = sketch_session.SketchSession(context, general())
    session.start_resources((), "Encoding failure")
    with patch.object(draft_dispatch, "dumps", side_effect=ValueError("injected encoder failure")):
        check(not session.suspend("Failed encoding"), "Failed checkpoint reports failure")
    record = sketch_session._UNENCODED_DRAFTS[session.session_id]
    check(
        record["draft"] is session.draft and "encoder" in record["error"],
        "Pure intent retained on encoding failure",
    )
    check(
        not session.alive and session.timer is None, "Double failure still cleans native resources"
    )
    sketch_session._RECOVERY_DRAFTS.clear()
    sketch_session._UNENCODED_DRAFTS.clear()

    # Owner retired before hook; one failing cleanup step cannot skip another.
    class BrokenInput(sketch_session.SketchSession):
        detach_count = 0

        def _detach_input(self):
            self.detach_count += 1
            check(
                not self.alive and sketch_session.active_session() is None,
                "Input detach observes retired owner",
            )
            raise RuntimeError("injected input failure")

    session = BrokenInput(context, general())
    session.start_resources((), "Cleanup injection")
    session.handles.append(object())  # invalid handle causes an independent removal failure
    session.cleanup()
    check(
        session.timer is None and not session.handles, "Cleanup continues after input/draw failures"
    )
    check(len(session.cleanup_errors) == 2, "Both cleanup diagnostics retained")
    session.cleanup()
    check(session.detach_count == 1, "Cleanup and token invalidation run once")

    # Native startup fail after registry acquisition must release ownership.
    session = sketch_session.SketchSession(context, general())
    session.manager = SimpleNamespace(
        event_timer_add=lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("timer startup"))
    )
    try:
        session.start_resources((), "Start failure")
    except RuntimeError:
        pass
    else:
        raise AssertionError("Injected startup did not fail")
    check(
        not session.alive and sketch_session.active_session() is None, "Partial start retires owner"
    )

    # Save/load callback routing remains singular and tears down before RNA removal.
    session = sketch_session.SketchSession(context, general())
    session.start_resources((), "Disable")
    registration._before_blend_save(None)
    encoded = scene.mechanical_cad.sketch_draft_json
    check(
        draft_dispatch.inspect(encoded).kind == draft_dispatch.GENERAL,
        "Save checkpoints general intent without a second handler",
    )
    addon.unregister()
    check(
        not session.alive and sketch_session.active_session() is None,
        "Disable releases shared owner before class removal",
    )
    addon.register()
    check(
        scene.mechanical_cad.sketch_draft_json == encoded,
        "Reenable retains exact saved general draft",
    )
    check(
        not any(name == "OCP" or name.startswith("OCP.") or name == "slvs" for name in sys.modules),
        "Shared owner imports no native backend",
    )


# A retired owner must not inspect old RNA, even if lookup itself raises.
class InvalidWindow:
    @property
    def view_layer(self):
        raise AssertionError("retired owner accessed old window")


session.window = InvalidWindow()
check(session.valid_context() is False, "Retired context guard precedes every RNA lookup")

# Missing scene plus failed encoding keeps the sole pure draft through real Undo
# and subsequent history events. An empty tombstone is not a recovery snapshot.
window = bpy.context.window
area = next(area for area in window.screen.areas if area.type == "VIEW_3D")
region = next(region for region in area.regions if region.type == "WINDOW")
with bpy.context.temp_override(window=window, area=area, region=region):
    original = bpy.context.scene
    gone = bpy.data.scenes.new("Missing encoding source")
    gone.mechanical_cad.document_json = BASE
    window.scene = gone
    uid = gone.session_uid
    bpy.ops.ed.undo_push(message="Original source exists")
    stranded = sketch_session.SketchSession(bpy.context, general())
    stranded.start_resources((), "Compound history failure")
    window.scene = original
    bpy.data.scenes.remove(gone)
    with patch.object(
        draft_dispatch, "dumps", side_effect=ValueError("injected missing-scene encoding failure")
    ):
        check(
            not stranded.suspend("Missing and unencodable"),
            "Missing-scene encoding failure is explicit",
        )
    check(
        sketch_session._UNENCODED_DRAFTS[stranded.session_id]["draft"] is stranded.draft,
        "Missing-scene pure fallback retained",
    )
    check(
        "could not be encoded" in sketch_session.draft_recovery_notice(),
        "Unencoded missing draft is visible",
    )
    bpy.ops.ed.undo_push(message="Original source removed")
    bpy.ops.ed.undo()
    recovered = next(scene for scene in bpy.data.scenes if scene.session_uid == uid)
    previous_slot = recovered.mechanical_cad.sketch_draft_json
    for _ in range(3):
        registration._before_history_change(None)
        registration._after_history_change(None)
    check(
        sketch_session._UNENCODED_DRAFTS[stranded.session_id]["draft"] is stranded.draft,
        "Repeated history cannot erase sole pure fallback",
    )
    check(
        recovered.mechanical_cad.sketch_draft_json == previous_slot,
        "Unencoded fallback never overwrites restored slot",
    )
    check(
        "could not be encoded" in sketch_session.draft_recovery_notice(),
        "Restored original scene retains a recovery explanation",
    )
    check(
        "could not be encoded" in sketch_session.draft_recovery_notice(),
        "Recovery remains visible after original scene returns",
    )
    # A newer valid session has independent history-slot tracking. Keeping the
    # old pure fallback must not pin or suppress this subsequent draft's Undo.
    window.scene = recovered
    bpy.ops.ed.undo_push(message="Before subsequent valid draft")
    newer = sketch_session.SketchSession(bpy.context, general())
    newer.start_resources((), "Newer draft")
    newer_snapshot = newer.checkpoint()
    check(newer.suspend("Newer draft saved"), "Subsequent valid draft suspends normally")
    bpy.ops.ed.undo_push(message="After subsequent valid draft")
    bpy.ops.ed.undo()
    recovered = next(scene for scene in bpy.data.scenes if scene.session_uid == uid)
    check(
        recovered.mechanical_cad.sketch_draft_json == newer_snapshot,
        "Old unencoded fallback cannot suppress newer history slot",
    )
    check(
        sketch_session._UNENCODED_DRAFTS[stranded.session_id]["draft"] is stranded.draft,
        "Independent pure fallback still retained",
    )
    sketch_session._discard_stored(recovered)
    check(
        stranded.session_id in sketch_session._UNENCODED_DRAFTS,
        "Discarding newer saved slot does not delete older recovery intent",
    )
    sketch_session.after_file_load()
    check(
        sketch_session._UNENCODED_DRAFTS[stranded.session_id]["previous_file"],
        "Old-file pure fallback quarantined without scene rebinding",
    )
    sketch_session._UNENCODED_DRAFTS.clear()


# One fixed admission budget covers encoded conflicts and failed encoders. Every
# owner reserves a slot before accepting user intent; no old copy is evicted.
window = bpy.context.window
area = next(area for area in window.screen.areas if area.type == "VIEW_3D")
region = next(region for region in area.regions if region.type == "WINDOW")
with bpy.context.temp_override(window=window, area=area, region=region):
    scene = bpy.context.scene
    scene.mechanical_cad.document_json = BASE
    sketch_session._discard_stored(scene)
    uid = scene.session_uid
    bpy.ops.ed.undo_push(message="Before bounded recovery matrix")
    retained = {}
    for index in range(sketch_session.MAX_RECOVERY_SESSIONS):
        draft = GeneralSketchDraft(BASE)
        draft.execute(AddCircle(PointSeed(index, 3), index + 1))
        owner = sketch_session.SketchSession(bpy.context, draft)
        owner.start_resources((), "Bounded recovery")
        snapshot = draft_dispatch.dumps(draft)
        if index % 2:
            with patch.object(draft_dispatch, "dumps", side_effect=ValueError("matrix encoder")):
                check(not owner.suspend("Unencoded matrix"), "Unencoded matrix remains explicit")
            retained[owner.session_id] = ("pure", draft, snapshot)
        else:
            scene.mechanical_cad.sketch_draft_json = "external matrix " + str(index)
            check(not owner.suspend("Encoded matrix"), "Encoded matrix remains explicit")
            retained[owner.session_id] = ("encoded", None, snapshot)
        sketch_session._discard_stored(scene)
    check(
        len(sketch_session._RECOVERY_DRAFTS) + len(sketch_session._UNENCODED_DRAFTS)
        == sketch_session.MAX_RECOVERY_SESSIONS,
        "Capacity retains every distinct interrupted session",
    )
    before = scene.mechanical_cad.sketch_draft_json
    try:
        sketch_session.SketchSession(bpy.context, general())
    except DraftError as exc:
        check("capacity reached" in str(exc), "Capacity rejection gives actionable explanation")
    else:
        raise AssertionError("New owner exceeded recovery admission capacity")
    check(
        scene.mechanical_cad.sketch_draft_json == before
        and sketch_session.active_session() is None,
        "Admission failure changes no saved bytes or native ownership",
    )
    check(
        "capacity reached" in sketch_session.draft_recovery_notice(), "Capacity notice is visible"
    )
    bpy.ops.ed.undo_push(message="After bounded recovery matrix")
    bpy.ops.ed.undo()
    scene = next(scene for scene in bpy.data.scenes if scene.session_uid == uid)
    for _ in range(3):
        registration._before_history_change(None)
        registration._after_history_change(None)
        sketch_session._discard_stored(scene)
    for key, (kind, draft, snapshot) in retained.items():
        if kind == "pure":
            check(
                sketch_session._UNENCODED_DRAFTS[key]["draft"] is draft
                and draft_dispatch.dumps(draft) == snapshot,
                "Pure recovery survives slot discard and native Undo/repeated callbacks",
            )
        else:
            check(
                sketch_session._RECOVERY_DRAFTS[key]["snapshot"] == snapshot,
                "Encoded recovery survives slot discard and native Undo/repeated callbacks",
            )
    sketch_session._RECOVERY_DRAFTS.clear()
    sketch_session._UNENCODED_DRAFTS.clear()
    check(
        not sketch_session._RECOVERY_RESERVATIONS, "Retired owners release admission reservations"
    )

    # An unstarted owner also reserves its future recovery space. Only an
    # explicitly retired or no-longer-referenced owner releases that reservation.
    pending = [
        sketch_session.SketchSession(bpy.context, general())
        for _ in range(sketch_session.MAX_RECOVERY_SESSIONS)
    ]
    try:
        sketch_session.SketchSession(bpy.context, general())
    except DraftError:
        pass
    else:
        raise AssertionError("Unstarted owners bypassed admission bound")
    for owner in pending:
        owner.cleanup()
    check(not sketch_session._RECOVERY_RESERVATIONS, "Unstarted cleanup releases reserved capacity")

    # Encodable missing-scene recovery is independent of history's restoration
    # index too; opening another file must not erase the sole encoded copy.
    destination = bpy.context.scene
    missing = bpy.data.scenes.new("Encoded missing source")
    missing.mechanical_cad.document_json = BASE
    window.scene = missing
    owner = sketch_session.SketchSession(bpy.context, general())
    owner.start_resources((), "Encoded missing scene")
    snapshot = draft_dispatch.dumps(owner.draft)
    window.scene = destination
    bpy.data.scenes.remove(missing)
    check(not owner.suspend("Missing source"), "Missing encoded source reports recovery")
    sketch_session.after_file_load()
    check(
        sketch_session._RECOVERY_DRAFTS[owner.session_id]["snapshot"] == snapshot
        and sketch_session._RECOVERY_DRAFTS[owner.session_id]["previous_file"],
        "Encoded missing-scene copy survives file-boundary history clearing",
    )
    sketch_session._RECOVERY_DRAFTS.clear()

addon.unregister()
print(
    "MCAD_SHARED_SKETCH_OWNER_RESULT="
    + json.dumps({"ok": True, "checks": len(checks), "blender": bpy.app.version_string})
)
