"""Actual native load/Undo/disable for detached general sketch work.

No general viewport editor is registered. A tiny shared owner exercises the
publication/input retirement contract; controlled completion makes the native
lifecycle race deterministic. Real owned-child quit is tested separately.
Run with native Blender --background --factory-startup --python-exit-code 1.
"""

import copy
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import bpy

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
os.environ["MCAD_ROOT"] = str(ROOT)
os.environ.setdefault("MCAD_PYTHON", str(ROOT / ".venv/bin/python"))
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import (  # noqa: E402
    assembly_job_ui as ui,
)
from mechanical_cad_blender import (  # noqa: E402
    assembly_pending,
    bridge,
    document_state,
    draft_dispatch,
    execution_lease,
    general_authoring,
    part_publication,
    register,
    registration,
    sketch_session,
    unregister,
    viewport_sketch,
)
from mechanical_cad_blender import (  # noqa: E402
    general_sketch_draft as drafts,
)
from mechanical_cad_blender import (  # noqa: E402
    sketch_pending as pending,
)

BASE = '{"schema_version":1,"id":"doc","name":"Part","units":"mm","parameters":{},"features":[],"active_feature":null}\n'
RAW = " \tunknown_radius + ( 🛠\n"
checks = []
cancel_owner = None


def check(condition, label):
    assert condition, label
    checks.append(label)


class SlowCleanup:
    """Detached fake process, never a successful solver/evidence fixture."""

    def __init__(self, prepared, selection, *, owner_token):
        self.request = prepared.guarded_request()
        self.selection = selection
        self.owner_token = owner_token
        self.state = "created"
        self.consumed = 0
        self.waits = []

    @property
    def done(self):
        return self.state in {"ready", "cancelled"}

    def start(self, current_selection):
        self.selection.assert_current(current_selection)
        self.state = "running"
        return self

    def cancel(self):
        if cancel_owner is not None:
            assert not cancel_owner.alive, "process cancelled before owner retirement"
            assert cancel_owner.intent.retired, "process cancelled before intent retirement"
            assert cancel_owner.intent._binding is None, "native publication binding retained"
        if self.done:
            self.state = "cancelled"
        else:
            self.state = "cancelling"
        return True

    def poll(self, current_selection):
        self.selection.assert_current(current_selection)
        return self.state

    def wait(self, timeout=None):
        self.waits.append(timeout)
        return self.done

    def result(self, current_selection, *, owner_token):
        self.consumed += 1
        raise AssertionError("Lifecycle maintenance must never consume a response")

    def request_snapshot(self):
        return copy.deepcopy(self.request)


class TestSession(sketch_session.SketchSession):
    """Only the future editor's required async-detach seam, not an editor."""

    def __init__(self, context, draft):
        super().__init__(context, draft)
        self.intent = None
        self.pending = None
        self.detach_count = 0

    def _detach_input(self):
        self.detach_count += 1
        check(
            not self.alive and sketch_session.active_session() is None,
            "Input detachment observes the retired sole owner",
        )
        if self.intent is not None:
            self.intent.retire()
        if self.pending is not None:
            pending.cancel(self.pending, "Test editor input retired")
            ui.ensure_supervisor()


def new_owner():
    global cancel_owner
    scene = bpy.context.scene
    scene.mechanical_cad.sketch_draft_json = ""
    scene.mechanical_cad.document_json = BASE
    commands = drafts.GeneralSketchDraft(BASE)
    _, circle = commands.execute(drafts.AddCircle(drafts.PointSeed(2, 3), 4)).entity_ids
    driver = commands.execute(drafts.AddRelation("radius", (circle,), value=4)).constraint_id
    commands.begin_edit(driver)
    commands.update_edit(RAW)
    wrapper = general_authoring.GeneralSketchAuthoringState.from_v1_draft(commands)
    wrapper.select_tool("Dimension")
    wrapper.place_annotation(driver, (14, 9))
    window = bpy.context.window
    area = next(item for item in window.screen.areas if item.type == "VIEW_3D")
    region = next(item for item in area.regions if item.type == "WINDOW")
    with bpy.context.temp_override(window=window, area=area, region=region):
        owner = TestSession(bpy.context, wrapper)
        owner.start_resources((), "Async lifecycle fixture")
        owner.intent = part_publication.prepare(bpy.context, wrapper.candidate())
        with patch.object(pending, "_GUARDED_JOB_FACTORY", SlowCleanup):
            owner.pending = pending.prepare_guarded(
                owner.intent.prepared,
                {
                    "session": owner.session_id,
                    "base": BASE,
                    "draft": draft_dispatch.dumps(wrapper),
                },
                selection=owner.intent.selection,
                owner_token=owner.intent.owner_token,
            )
    cancel_owner = owner
    ui.ensure_supervisor()
    ui.ensure_supervisor()
    check(bpy.app.timers.is_registered(ui._supervise), "One shared supervisor is registered")
    check(execution_lease.is_busy(), "Sketch transport owns the shared execution lease")
    return owner


def retired(owner, label):
    check(not owner.alive and owner.detach_count == 1, label + ": input retired exactly once")
    check(sketch_session.active_session() is None, label + ": no active owner remains")
    check(not owner.cleanup_errors, label + ": native resources cleanly removed")
    check(not owner.handles and owner.timer is None, label + ": no late modal/draw resources")
    check(
        owner.intent.retired
        and owner.intent._binding is None
        and owner.intent._workspace is None
        and owner.intent._owner_snapshot is None,
        label + ": publication retains no native bindings",
    )
    check(not owner.pending.done, label + ": delayed process still retained")
    check(execution_lease.is_busy(), label + ": delayed cleanup keeps its execution lease")
    check(bpy.app.timers.is_registered(ui._supervise), label + ": cleanup timer survives")
    check(ui._supervise() == 0.1, label + ": supervisor continues without acceptance")
    check(owner.pending._job.consumed == 0, label + ": successful response never consumed")
    # A cancelled operation cannot accept even if a fake late response appears.
    check(
        pending.poll(owner.pending, owner.pending.identity_snapshot()) is None,
        label + ": late caller poll cannot accept retired work",
    )
    try:
        pending.prepare_guarded(
            owner.intent.prepared,
            {"new": True},
            selection=owner.intent.selection,
            owner_token=owner.intent.owner_token,
        )
    except bridge.BridgeError as exc:
        check(execution_lease.BUSY_MESSAGE in str(exc), label + ": busy rejection stays explicit")
    else:
        raise AssertionError("New native work started before cleanup")
    owner.cleanup()
    check(owner.detach_count == 1, label + ": repeated owner cleanup is inert")


def finish(owner, label):
    global cancel_owner
    owner.pending._job.state = "cancelled"
    with patch.object(
        document_state, "_publish_candidate_locked", side_effect=AssertionError("Late publication")
    ):
        check(ui._supervise() is None, label + ": terminal cleanup stops supervision")
    check(owner.pending.done and not pending._ACTIVE, label + ": retained process removed")
    check(not execution_lease.is_busy(), label + ": no stuck busy lease")
    check(owner.pending._job.consumed == 0, label + ": terminal result never consumed")
    if bpy.app.timers.is_registered(ui._supervise):
        bpy.app.timers.unregister(ui._supervise)
    cancel_owner = None


def saved_raw(expected, label):
    state = bpy.context.scene.mechanical_cad
    check(state.sketch_draft_json == expected, label + ": exact wrapper bytes retained")
    wrapper = draft_dispatch.restore(state.sketch_draft_json, BASE)
    check(wrapper.command_draft.pending_edit.raw_text == RAW, label + ": invalid raw text exact")
    check(not wrapper.command_draft.has_verified_trial, label + ": no solver acceptance restored")
    check(state.document_json == BASE, label + ": canonical Part unchanged")
    check(
        viewport_sketch.suspended_draft(bpy.context)["editor_available"],
        label + ": retained general intent has an explicit editor route",
    )


register()
check(bpy.app.version == (5, 2, 2), "Qualified native Blender 5.2.2 runtime")
# Configuration revocation must not create an idle timer after disable, while
# any unfinished or uncertain cleanup still retains the one existing supervisor.
ui.cancel_for_configuration("Idle configuration revocation")
check(not bpy.app.timers.is_registered(ui._supervise), "Idle revocation creates no supervisor")
ui.ensure_supervisor()
ui.cancel_for_configuration("Terminal configuration cleanup")
check(not bpy.app.timers.is_registered(ui._supervise), "Confirmed idle cleanup removes its timer")
for assembly_active, sketch_complete in ((True, True), (False, False)):
    with (
        patch.object(
            assembly_pending, "cancel_for_configuration", return_value=assembly_active
        ) as assembly_cancel,
        patch.object(pending, "cancel_all", return_value=sketch_complete) as sketch_cancel,
    ):
        ui.cancel_for_configuration("Retained configuration cleanup")
        check(assembly_cancel.called and sketch_cancel.called, "Both adapters receive revocation")
        check(
            sketch_cancel.call_args.kwargs["wait_timeout"] == 0.0,
            "Configuration cleanup never waits for native completion",
        )
        check(
            bpy.app.timers.is_registered(ui._supervise),
            "Either unfinished adapter retains supervision",
        )
    ui.cancel_for_configuration("Retained fixture cleanup")
for failure in ("assembly", "sketch"):
    with (
        patch.object(
            assembly_pending,
            "cancel_for_configuration",
            side_effect=RuntimeError("configuration assembly error")
            if failure == "assembly"
            else None,
            return_value=False,
        ) as assembly_cancel,
        patch.object(
            pending,
            "cancel_all",
            side_effect=RuntimeError("configuration sketch error") if failure == "sketch" else None,
            return_value=True,
        ) as sketch_cancel,
    ):
        try:
            ui.cancel_for_configuration("Uncertain configuration cleanup")
        except bridge.BridgeError:
            check(
                assembly_cancel.called and sketch_cancel.called,
                "Configuration adapter failure cannot skip the other adapter",
            )
            check(
                bpy.app.timers.is_registered(ui._supervise),
                "Uncertain cleanup retains supervision",
            )
        else:
            raise AssertionError("Configuration cleanup error was lost")
    ui.cancel_for_configuration("Uncertain fixture cleanup")
# A ready process is still its owner's explicit, unconsumed work.
owner = new_owner()
owner.pending._job.state = "ready"
check(ui._supervise() == 0.1, "Supervisor leaves ready successful work with its owner")
with patch.object(ui, "_redraw", side_effect=ReferenceError("old UI context")):
    check(ui._supervise() == 0.1, "Unavailable UI cannot drop active process supervision")
check(owner.pending._job.consumed == 0, "Supervisor never calls result on ready work")
check(execution_lease.is_busy(), "Ready unconsumed job still owns execution")
owner.cleanup()
check(owner.pending.done, "Cancelling ready work invalidates it immediately")
check(not execution_lease.is_busy(), "Ready cancellation releases confirmed-cleaned process")
ui.cancel_all("Ready fixture cleanup")
cancel_owner = None

# A single total deadline covers both adapters, rather than two five-second waits.
with (
    patch.object(ui.time, "monotonic", side_effect=[100.0, 100.0, 104.0]),
    patch.object(assembly_pending, "cancel_all", return_value=True) as assembly_cancel,
    patch.object(pending, "cancel_all", return_value=True) as sketch_cancel,
):
    check(ui.cancel_all("Deadline fixture"), "Both adapters report complete")
check(assembly_cancel.call_args.kwargs["wait_timeout"] == 5.0, "First wait uses total budget")
check(sketch_cancel.call_args.kwargs["wait_timeout"] == 1.0, "Second wait uses remaining budget")
with (
    patch.object(ui.time, "monotonic", side_effect=[100.0, 100.0, 106.0]),
    patch.object(assembly_pending, "cancel_all", return_value=False),
    patch.object(pending, "cancel_all", return_value=False) as sketch_cancel,
):
    check(not ui.cancel_all("Exhausted deadline"), "Expired total deadline stays incomplete")
check(
    sketch_cancel.call_args.kwargs["wait_timeout"] == 0.0,
    "Exhausted total budget cannot become a second wait",
)
ui.cancel_all("Deadline fixture cleanup")

# Failure in one adapter must not skip cancellation/detachment of another.
with (
    patch.object(assembly_pending, "cancel_all", side_effect=RuntimeError("assembly wait error")),
    patch.object(assembly_pending, "detach_all") as detach,
    patch.object(pending, "cancel_all", return_value=True) as sketch_cancel,
):
    check(not ui.cancel_all("Independent cleanup", detach=True), "Failed cleanup stays incomplete")
    check(detach.called and sketch_cancel.called, "Assembly failure cannot skip sketch cleanup")
    check(bpy.app.timers.is_registered(ui._supervise), "Failure retains cleanup supervision")
ui.cancel_all("Error fixture cleanup")
with (
    patch.object(assembly_pending, "cancel_all", return_value=True) as assembly_cancel,
    patch.object(assembly_pending, "detach_all") as detach,
    patch.object(pending, "cancel_all", side_effect=RuntimeError("sketch wait error")),
):
    check(
        not ui.cancel_all("Reverse independent cleanup", detach=True),
        "Sketch cleanup error also stays incomplete",
    )
    check(assembly_cancel.called and detach.called, "Sketch error preserves assembly cleanup")
    check(bpy.app.timers.is_registered(ui._supervise), "Sketch error retains cleanup timer")
ui.cancel_all("Reverse error fixture cleanup")
with (
    patch.object(assembly_pending, "reap", side_effect=RuntimeError("assembly reap error")),
    patch.object(pending, "reap", return_value=False) as sketch_reap,
):
    check(ui._supervise() == 0.1 and sketch_reap.called, "One reap failure cannot skip the other")
with (
    patch.object(assembly_pending, "reap", return_value=False) as assembly_reap,
    patch.object(pending, "reap", side_effect=RuntimeError("sketch reap error")),
):
    check(
        ui._supervise() == 0.1 and assembly_reap.called,
        "Sketch reap failure still retains supervision",
    )

# A failing owner suspension still attempts input retirement and both adapters.
owner = new_owner()
with patch.object(
    viewport_sketch, "suspend_active", side_effect=RuntimeError("owner suspend error")
):
    registration._before_blend_load(None)
retired(owner, "Failed suspension fallback")
finish(owner, "Failed suspension fallback")
with (
    patch.object(viewport_sketch, "suspend_active", side_effect=RuntimeError("owner error")),
    patch.object(registration, "_cleanup_active_sketch", side_effect=RuntimeError("detach error")),
    patch.object(assembly_pending, "cancel_all", return_value=True) as assembly_cancel,
    patch.object(pending, "cancel_all", return_value=True) as sketch_cancel,
):
    registration._before_blend_load(None)
    check(
        assembly_cancel.called and sketch_cancel.called,
        "Even owner and fallback errors cannot skip either process adapter",
    )

# Real save/load: the shared owner retires before original RNA is replaced.
owner = new_owner()
expected = draft_dispatch.dumps(owner.draft)
with tempfile.TemporaryDirectory(prefix="mcad-sketch-lifecycle-") as directory:
    path = str(Path(directory) / "pending.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path)
    check(
        bpy.context.scene.mechanical_cad.sketch_draft_json == expected,
        "Save uses the shared owner checkpoint",
    )
    bpy.ops.wm.open_mainfile(filepath=path)
retired(owner, "Actual load")
saved_raw(expected, "Actual load")
loaded_fields = document_state._snapshot_fields(bpy.context.scene.mechanical_cad)
finish(owner, "Actual load")
check(
    document_state._snapshot_fields(bpy.context.scene.mechanical_cad) == loaded_fields,
    "Post-load reaping writes no loaded scene fields",
)

# Real Undo/Redo: retained raw input stays outside canonical Undo and never accepts.
bpy.context.preferences.edit.use_global_undo = True
bpy.context.scene.mechanical_cad.sketch_draft_json = ""
bpy.ops.ed.undo_push(message="Before async general sketch")
bpy.context.scene["unrelated_lifecycle_change"] = 1
bpy.ops.ed.undo_push(message="Unrelated native change")
owner = new_owner()
expected = draft_dispatch.dumps(owner.draft)
check(bpy.ops.ed.undo() == {"FINISHED"}, "Actual native Undo executes")
retired(owner, "Actual Undo")
saved_raw(expected, "Actual Undo")
finish(owner, "Actual Undo")
check(bpy.ops.ed.redo() == {"FINISHED"}, "Actual native Redo executes")
saved_raw(expected, "Actual Redo")

# Actual unregister frees addon RNA while delayed cleanup retains only pure data.
owner = new_owner()
expected = draft_dispatch.dumps(owner.draft)
unregister()
check(not hasattr(bpy.types.Scene, "mechanical_cad"), "Unregister removes Part RNA")
check(not hasattr(bpy.types.Scene, "mechanical_cad_assembly"), "Unregister removes assembly RNA")
retired(owner, "Actual unregister")
finish(owner, "Actual unregister")
register()
saved_raw(expected, "Actual reenable")
check(registration._before_blender_exit in bpy.app.handlers.exit_pre, "One exit hook reinstalled")
for handlers, callback in registration._HISTORY_HANDLERS:
    check(list(handlers).count(callback) == 1, "Lifecycle callback remains singular")
unregister()
check(not bpy.app.timers.is_registered(ui._supervise), "Idle unregister leaves no cleanup timer")
check(not execution_lease.is_busy(), "Complete suite leaves no native execution ownership")
print("SKETCH_JOB_LIFECYCLE_SMOKE_OK", len(checks), bpy.app.version_string)
