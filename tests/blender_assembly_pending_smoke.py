"""Deterministic async report races plus one real detached native job in Blender.

blender --background --factory-startup --python-exit-code 1 \
    --python tests/blender_assembly_pending_smoke.py
"""

import copy
import hashlib
import json
import os
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy
from bpy.props import PointerProperty

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
os.environ["MCAD_ROOT"] = str(ROOT)
os.environ.setdefault("MCAD_PYTHON", str(ROOT / ".venv/bin/python"))
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import assembly_bridge as boundary  # noqa: E402
from mechanical_cad_blender import assembly_display as display  # noqa: E402
from mechanical_cad_blender import assembly_pending as pending_api  # noqa: E402
from mechanical_cad_blender import assembly_state as state_api  # noqa: E402
from mechanical_cad_blender import bridge, document_state, guarded_evidence  # noqa: E402
from mechanical_cad_blender.assembly_properties import MCAD_AssemblyState  # noqa: E402
from mechanical_cad_blender.properties import MCAD_Feature, MCAD_Parameter, MCAD_State  # noqa: E402

checks = []


def assert_that(condition, label):
    if not condition:
        raise AssertionError(label)
    checks.append(label)


def reject(operation, label, contains=None):
    try:
        operation()
    except (bridge.BridgeError, RuntimeError, ValueError) as exc:
        if contains is not None:
            assert contains.lower() in str(exc).lower(), (contains, str(exc))
        checks.append(label)
        return exc
    raise AssertionError(label)


# Shared request preparation bounds Python alias graphs before recursive finite
# validation, while preserving ordinary protocol field order and numeric types.
request_input = {"kind": "assembly", "list": [{"value": 1.0}]}
prepared = boundary.build_request(request_input, "assembly_check")
expected_wire = {
    "protocol_version": 1,
    "kind": "assembly",
    "assembly_protocol_version": 1,
    "assembly": request_input,
    "action": "assembly_check",
    "coordinates": None,
    "requirements": None,
    "policy": None,
    "samples": None,
    "preset_id": None,
}
assert_that(
    json.dumps(prepared) == json.dumps(expected_wire), "shared builder preserves exact wire bytes"
)
request_input["list"][0]["value"] = 2.0
assert_that(
    prepared["assembly"]["list"][0]["value"] == 1.0, "shared builder detaches caller mutation"
)
expanded = [0]
for _index in range(40):
    expanded = [expanded, expanded]
reject(
    lambda: boundary.build_request({"expanded": expanded}),
    "shared builder bounds exponential alias graph",
)
cyclic = []
cyclic.append(cyclic)
reject(lambda: boundary.build_request({"cycle": cyclic}), "shared builder rejects cyclic graph")

for cls in (MCAD_Parameter, MCAD_Feature, MCAD_State, MCAD_AssemblyState):
    bpy.utils.register_class(cls)
bpy.types.Scene.mechanical_cad = PointerProperty(type=MCAD_State)
bpy.types.Scene.mechanical_cad_assembly = PointerProperty(type=MCAD_AssemblyState)
context, scene = bpy.context, bpy.context.scene
state = scene.mechanical_cad_assembly
canonical = json.loads((ROOT / "examples/reused_blocks.mcad-assembly.json").read_text())
canonical["joints"][1]["kind"] = "fixed"
canonical["joints"][1].pop("coordinate")
canonical["joints"][1].pop("limits")
canonical["verification_presets"] = [
    {
        "id": "clearance",
        "name": "Async clearance",
        "kind": "clearance",
        "requirements": [
            {"id": "gap", "name": "Root gap", "instances": ["a", "root"], "minimum_mm": 1.0}
        ],
        "policy": copy.deepcopy(boundary.DEFAULT_POLICY),
    }
]
canonical["active_verification_preset"] = "clearance"
document_state._populate_document(scene, canonical["part_sources"][0]["document"])
state_api.commit_candidate(context, canonical)
context.view_layer.update()
part_json, assembly_json = scene.mechanical_cad.document_json, state.document_json
objects = {obj.as_pointer() for obj in display.owned_objects(scene, state.owner_id)}
meshes = {
    obj.data.as_pointer()
    for obj in display.owned_objects(scene, state.owner_id)
    if obj.type == "MESH"
}
poses = {
    obj.as_pointer(): tuple(tuple(row) for row in obj.matrix_world)
    for obj in display.owned_objects(scene, state.owner_id)
}

# A real subprocess is asynchronous and acceptance is exclusively a main-thread poll.
real = pending_api.prepare(context, "assembly_check")
assert_that(state_api._key(scene) in state_api._BUSY, "real job owns scene transaction lock")
assert_that(pending_api.status(scene)["pair_query_count"] == 3, "real workload is three pairs")
deadline = time.monotonic() + 90.0
real_response = None
while not real.done and time.monotonic() < deadline:
    real_response = pending_api.poll(context, real)
    if not real.done:
        time.sleep(0.01)
assert_that(real.done and real_response is not None, "real detached job validates and publishes")
assert_that(real_response["report"]["passed"], "real configured check returns exact-pose pass")
assert_that(state_api.report_is_current(context), "real report has current runtime binding")
assert_that(pending_api.poll(context, real) is None, "real completion is delivered only once")
raw_check = copy.deepcopy(dict(real_response))
raw_sample = copy.deepcopy(dict(state_api.sample(context, "slide_a", [30.0, 50.0, 90.0])))
# Establish a distinct old sample report so a rejected static check cannot look new.
saved = state_api._capture(context, scene)
old_report = state.report_json
old_binding = state_api._binding(state)
old_runtime_binding = state_api._RUNTIME[state_api._key(scene)]["report_binding"]


class FakeJob:
    instances = []
    before_start = None
    start_error = None

    def __init__(self, prepared, selection, *, owner_token):
        self.prepared = prepared
        self.request = prepared.guarded_request()
        self.selection, self.owner_token = selection, owner_token
        self.state = "created"
        self.raw = None
        self.error = None
        self.consumed = 0
        self.cancelled = 0
        self.started = 0
        self.instances.append(self)

    @property
    def done(self):
        return self.state in {"ready", "failed", "cancelled", "consumed"}

    def start(self, current_selection):
        self.selection.assert_current(current_selection)
        if self.before_start:
            self.before_start()
        if self.start_error:
            raise self.start_error
        if self.state != "cancelled":
            self.started += 1
            self.state = "running"
        return self

    def poll(self, current_selection):
        self.selection.assert_current(current_selection)
        return self.state

    def ready(self, raw=raw_check):
        if self.state != "cancelling":
            self.raw = copy.deepcopy(raw)
            self.state = "ready"

    def fail(self, message):
        self.error = bridge.BridgeError(message)
        self.state = "failed"

    def result(self, current_selection, *, owner_token):
        self.selection.assert_current(current_selection)
        assert owner_token is self.owner_token
        assert self.done
        self.consumed += 1
        previous = self.state
        self.state = "consumed"
        if previous == "failed":
            raise self.error
        if previous == "cancelled":
            raise bridge.BridgeError("cancelled")
        # Controlled completion fixture: retain the real native operation payload
        # while independently binding its receipt to this fake transport request.
        required = self.request["backend_contract"]["required_capabilities"]
        selected = self.selection
        response = {
            **copy.deepcopy(self.raw),
            "backend_receipt": {
                "version": 1,
                "request_id": self.request["backend_contract"]["request_id"],
                "request_fingerprint": hashlib.sha256(
                    json.dumps(self.request, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest(),
                "required_capabilities": required,
                "confirmed_capabilities": required,
                "missing_capabilities": [],
                "phase": "dispatched",
                "backend": {
                    "core_version": "controlled-completion-fixture",
                    "project_root": selected.project_root,
                    "core_origin": str(ROOT / "src/mechanical_cad"),
                    "solver_origin": str(ROOT / "src/mechanical_cad/sketch_solver.py"),
                    "python_executable": selected.python_executable,
                    "python_executable_target": selected.python_executable_target,
                    "python_prefix": "/controlled/prefix",
                    "python_base_prefix": "/controlled/base",
                    "python_version": [3, 12, 14],
                },
            },
        }
        return guarded_evidence.accept_response(
            self.prepared, response, selected, owner_token=owner_token
        )

    def request_snapshot(self):
        return copy.deepcopy(self.request)

    def cancel(self):
        self.cancelled += 1
        self.raw = None
        self.state = "cancelled" if self.done or self.state == "created" else "cancelling"
        return True

    def finish_cleanup(self):
        if self.state == "cancelling":
            self.state = "cancelled"

    def wait(self, timeout=None):
        self.finish_cleanup()
        return self.done


def reset():
    pending_api.cancel_all("Test reset")
    context.window.scene = scene
    state_api._restore_fields(state, saved["fields"])
    scene.mechanical_cad.document_json = part_json
    scene.mechanical_cad.sketch_draft_json = ""
    scene.unit_settings.scale_length = saved["scale"]
    state_api._RUNTIME[state_api._key(scene)] = copy.copy(saved["runtime"])
    state_api._EPOCHS[state_api._key(scene)] = saved["epoch"]
    FakeJob.before_start = None
    FakeJob.start_error = None
    context.view_layer.update()


def unchanged(label, *, report_current=True):
    assert_that(state.document_json == assembly_json, label + ": canonical bytes intact")
    assert_that(scene.mechanical_cad.document_json == part_json, label + ": working Part intact")
    assert_that(state.report_json == old_report, label + ": previous report bytes intact")
    assert_that(state_api._binding(state) == old_binding, label + ": exact old evidence binding")
    assert_that(
        {obj.as_pointer() for obj in display.owned_objects(scene, state.owner_id)} == objects,
        label + ": object identities intact",
    )
    assert_that(
        {
            obj.data.as_pointer()
            for obj in display.owned_objects(scene, state.owner_id)
            if obj.type == "MESH"
        }
        == meshes,
        label + ": mesh identities intact",
    )
    assert_that(
        {
            obj.as_pointer(): tuple(tuple(row) for row in obj.matrix_world)
            for obj in display.owned_objects(scene, state.owner_id)
        }
        == poses,
        label + ": authored viewport pose intact",
    )
    if report_current:
        assert_that(state_api.report_is_current(context), label + ": old report remains current")
        assert_that(
            state_api._RUNTIME[state_api._key(scene)]["report_binding"] == old_runtime_binding,
            label + ": old runtime binding retained",
        )
    assert_that(state_api._key(scene) not in state_api._BUSY, label + ": busy lock released")
    assert_that(pending_api.active_for_scene(scene) is None, label + ": no active job remains")


def launch(**kwargs):
    return pending_api.prepare(context, "assembly_check", **kwargs)


with patch.object(pending_api, "_JOB_FACTORY", FakeJob):
    handle = launch()
    job = FakeJob.instances[-1]
    assert_that(pending_api.poll(context, handle) is None, "running poll never blocks or publishes")
    reject(lambda: state_api.check(context), "sync Check excluded by pending busy lock")
    reject(lambda: state_api.replay(context), "replay excluded by pending busy lock")
    reject(lambda: launch(), "second async Check excluded by busy lock")
    before_fields = {name: getattr(state, name) for name in state_api._STATE_FIELDS}
    info = pending_api.status(scene)
    info["base_coordinates"]["slide_a"] = -900
    assert_that(
        handle.status()["base_coordinates"]["slide_a"] == 100.0,
        "status is a detached read-only snapshot",
    )
    assert_that(
        before_fields == {name: getattr(state, name) for name in state_api._STATE_FIELDS},
        "status query performs no RNA writes",
    )
    assert_that("percent" not in info and "progress" not in info, "status invents no percentage")
    pending_api.cancel(handle, "User pressed Esc")
    assert_that(
        not handle.done and state_api._key(scene) in state_api._BUSY,
        "running cancellation retains lock until process reaped",
    )
    assert_that(
        pending_api.poll(context, handle) is None, "cancellation poll waits only by returning"
    )
    job.finish_cleanup()
    reject(
        lambda handle=handle: pending_api.poll(context, handle),
        "Esc cancellation raises after cleanup",
        "Esc",
    )
    assert_that(
        state.status == "CANCELLED" and "Esc" in state.last_action_error,
        "cancellation is explicit separate last-attempt state",
    )
    assert_that(job.consumed == 0, "cancelled result is never consumed")
    assert_that(pending_api.poll(context, handle) is None, "cancelled handle cannot later publish")
    unchanged("running cancellation")

    reset()
    handle = launch()
    job = FakeJob.instances[-1]
    job.ready()
    pending_api.cancel(handle, "Cancel after completion before publication")
    reject(
        lambda handle=handle: pending_api.poll(context, handle), "ready cancellation reports once"
    )
    assert_that(job.consumed == 0, "ready cancellation discards unconsumed response")
    unchanged("ready cancellation")

    reset()
    FakeJob.before_start = lambda self: pending_api.cancel_all("Cancel before start")
    handle = launch()
    job = FakeJob.instances[-1]
    assert_that(job.started == 0, "pre-start cancellation never launches native process")
    reject(
        lambda handle=handle: pending_api.poll(context, handle), "pre-start cancellation reported"
    )
    unchanged("pre-start cancellation")

    reset()
    FakeJob.start_error = bridge.BridgeError("injected launch failure")
    reject(lambda: launch(), "launch failure restores lock and report", "launch")
    unchanged("start failure")

    reset()
    handle = launch()
    job = FakeJob.instances[-1]
    job.fail("Sidecar timed out after 1 seconds.")
    reject(
        lambda handle=handle: pending_api.poll(context, handle),
        "timeout becomes failure, never evidence",
        "timed out",
    )
    unchanged("timeout")

    reset()
    values = [30.0, 50.0, 90.0]
    handle = pending_api.prepare(context, "assembly_sample", joint_id="slide_a", values=values)
    job = FakeJob.instances[-1]
    values[0] = 999.0
    info = handle.status()
    assert_that(
        info["pose_count"] == 3 and info["pair_query_count"] == 9,
        "requested sample workload is instance choose two times poses",
    )
    assert_that(
        info["base_coordinates"] == {"slide_a": 100.0, "slide_b": 0.0},
        "sample base retains all authored coordinates including fixed zeros",
    )
    assert_that(
        info["sample_coordinates"]
        == [{"slide_a": value, "slide_b": 0.0} for value in [30.0, 50.0, 90.0]],
        "status lists exactly requested full-base discrete poses",
    )
    job.ready(raw_sample)
    response = pending_api.poll(context, handle)
    assert_that(
        response is not None and response["action"] == "assembly_sample",
        "sample accepts validated exact request",
    )
    unchanged("accepted sample")

    for label, mutate in [
        (
            "working Part revision",
            lambda: setattr(scene.mechanical_cad, "document_json", part_json + " "),
        ),
        ("assembly revision", lambda: setattr(state, "document_json", assembly_json + " ")),
        (
            "preset revision",
            lambda: setattr(
                state,
                "document_json",
                assembly_json.replace('"minimum_mm": 1.0', '"minimum_mm": 2.0'),
            ),
        ),
        ("scene scale", lambda: setattr(scene.unit_settings, "scale_length", 0.01)),
        ("evidence tampering", lambda: setattr(state, "report_json", old_report + " ")),
    ]:
        reset()
        handle = launch()
        job = FakeJob.instances[-1]
        mutate()
        changed_fields = (
            state.document_json,
            scene.mechanical_cad.document_json,
            state.report_json,
        )
        job.ready()
        reject(
            lambda handle=handle: pending_api.poll(context, handle),
            label + " rejects late completion",
        )
        assert_that(job.consumed == 0, label + ": rejects before consuming response")
        assert_that(
            (state.document_json, scene.mechanical_cad.document_json, state.report_json)
            == changed_fields,
            label + ": does not overwrite newer external edit",
        )
        assert_that(
            state_api._key(scene) not in state_api._BUSY, label + ": releases old target lock"
        )

    reset()
    clone = scene.copy()
    clone_state = clone.mechanical_cad_assembly
    handle = launch()
    job = FakeJob.instances[-1]
    clone_fields = {name: getattr(clone_state, name) for name in state_api._STATE_FIELDS}
    context.window.scene = clone
    job.ready()
    reject(
        lambda handle=handle: pending_api.poll(context, handle),
        "matching clone scene rejects original completion",
        "scene",
    )
    assert_that(
        clone_fields == {name: getattr(clone_state, name) for name in state_api._STATE_FIELDS},
        "clone receives neither report nor original failure diagnostics",
    )
    assert_that(
        "scene" in state.last_action_error.lower(), "failure diagnostics target original scene"
    )
    context.window.scene = scene
    bpy.data.scenes.remove(clone)
    unchanged("clone switch")

    reset()
    handle = launch()
    job = FakeJob.instances[-1]
    job.ready()
    changed_context = SimpleNamespace(scene=scene, window=SimpleNamespace(as_pointer=lambda: -1))
    reject(
        lambda: pending_api.poll(changed_context, handle),
        "different window rejects exact scene",
        "window",
    )
    unchanged("window switch")

    for label, draft in [("active draft", True), ("suspended draft", False)]:
        reset()
        handle = launch()
        job = FakeJob.instances[-1]
        job.ready()
        if draft:
            with patch.object(state_api.workspace, "active_draft", return_value=True):
                reject(
                    lambda handle=handle: pending_api.poll(context, handle),
                    label + " rejects completion",
                    "draft",
                )
        else:
            other = bpy.data.scenes.new("Pending draft scene")
            other.mechanical_cad.sketch_draft_json = "{}"
            reject(
                lambda handle=handle: pending_api.poll(context, handle),
                label + " rejects completion",
                "draft",
            )
            bpy.data.scenes.remove(other)
        unchanged(label)

    reset()
    handle = launch()
    job = FakeJob.instances[-1]
    obj = next(obj for obj in display.owned_objects(scene, state.owner_id) if obj.type == "MESH")
    vertex = obj.data.vertices[0]
    original = vertex.co.copy()
    vertex.co.x += 0.1
    job.ready()
    reject(
        lambda handle=handle: pending_api.poll(context, handle),
        "display corruption rejects publication",
        "display",
    )
    assert_that(state.report_json == old_report, "display rejection preserves historical report")
    assert_that(
        not state_api.report_is_current(context), "display rejection revokes previous trust"
    )
    vertex.co = original
    context.view_layer.update()
    unchanged("display corruption", report_current=False)

    reset()
    handle = launch()
    job = FakeJob.instances[-1]
    corrupted = copy.deepcopy(raw_check)
    corrupted["input_fingerprint"] = "0" * 64
    job.ready(corrupted)
    reject(
        lambda handle=handle: pending_api.poll(context, handle),
        "raw request fingerprint validated strictly",
    )
    unchanged("malformed native response")

    reset()
    handle = launch()
    job = FakeJob.instances[-1]
    job.request["preset_id"] = "different"
    job.ready()
    reject(
        lambda handle=handle: pending_api.poll(context, handle),
        "detached request tampering rejected before consumption",
    )
    assert_that(job.consumed == 0, "tampered job request never consumed")
    unchanged("request tampering")

    reset()
    handle = launch()
    job = FakeJob.instances[-1]
    job.ready()

    def partial_write(target, values):
        target.report_json = values["report_json"]
        target.report_request_json = values["report_request_json"]
        raise RuntimeError("injected partial report RNA write")

    with patch.object(state_api, "_write_fields", side_effect=partial_write):
        reject(
            lambda handle=handle: pending_api.poll(context, handle),
            "partial RNA write rolls back exact evidence",
            "partial",
        )
    unchanged("partial report write")

    reset()
    handle = launch()
    job = FakeJob.instances[-1]
    job.ready()
    with (
        patch.object(state_api, "_write_fields", side_effect=partial_write),
        patch.object(
            state_api, "_restore_fields", side_effect=RuntimeError("injected restore failure")
        ),
    ):
        error = reject(
            lambda handle=handle: pending_api.poll(context, handle),
            "compound write and restoration failure visible",
        )
    assert_that(
        "partial report" in str(error) and "restore failure" in str(error),
        "compound failure preserves primary and recovery diagnostic",
    )
    assert_that(
        state.status == "FAILED" and not state_api.report_is_current(context),
        "incomplete recovery revokes trust rather than reporting success",
    )
    assert_that(
        state_api._key(scene) not in state_api._BUSY, "incomplete recovery still releases lock"
    )
    assert_that(
        pending_api.poll(context, handle) is None,
        "compound failure is reported only once and cannot be consumed later",
    )

    for name, hook in [
        ("load", state_api.after_file_load),
        ("history", state_api.before_history_change),
        ("runtime clear", state_api.clear_runtime),
    ]:
        reset()
        handle = launch()
        job = FakeJob.instances[-1]
        hook()
        job.ready()
        reject(
            lambda handle=handle: pending_api.poll(context, handle),
            name + " direct invalidation rejects completion",
        )
        unchanged(name + " invalidation", report_current=False)
        assert_that(
            not state_api.report_is_current(context), name + ": cannot resurrect old runtime trust"
        )

    reset()
    handle = launch()
    job = FakeJob.instances[-1]
    assert_that(
        pending_api.cancel_all("File load is starting"),
        "registered lifecycle cancellation kills/reaps",
    )
    assert_that(job.cancelled == 1 and job.done, "lifecycle waits for owned cleanup")
    unchanged("registered lifecycle cancellation")

    reset()
    handle = launch()
    job = FakeJob.instances[-1]
    no_windows = SimpleNamespace(window_manager=SimpleNamespace(windows=[]))
    assert_that(pending_api.reap(no_windows), "supervisor observes closed modal window")
    assert_that(job.cancelled == 1, "supervisor cancels orphaned job without publishing")
    job.finish_cleanup()
    assert_that(not pending_api.reap(no_windows), "supervisor reaps orphan and stops when idle")
    unchanged("orphan window cancellation")

    reset()
    handle = launch()
    job = FakeJob.instances[-1]
    job.ready()
    assert_that(pending_api.reap(context), "supervisor leaves valid ready response pending")
    assert_that(
        job.consumed == 0 and state.report_json == old_report,
        "supervisor cannot accept a ready response through unrelated context",
    )
    pending_api.cancel_all("Ready supervisor cleanup")
    unchanged("unpublished ready supervisor result")

    reset()
    handle = launch()
    job = FakeJob.instances[-1]
    with patch.object(job, "wait", return_value=False):
        assert_that(
            not pending_api.cancel_all("Shutdown", wait_timeout=0),
            "incomplete shutdown cleanup is never reported complete",
        )
    assert_that(
        state_api._key(scene) in state_api._BUSY and not handle.done,
        "incomplete cleanup keeps its busy capability",
    )
    assert_that(
        "cleanup is still pending" in handle.status()["message"],
        "incomplete cleanup appears in read-only status",
    )
    job.finish_cleanup()
    assert_that(
        not pending_api.reap(context), "later supervisor closes incomplete shutdown cleanup"
    )
    unchanged("delayed process cleanup")

    reset()
    handle = launch()
    job = FakeJob.instances[-1]
    with patch.object(job, "cancel", side_effect=RuntimeError("injected kill failure")):
        pending_api.cancel(handle, "Cancel needs cleanup")
    assert_that(
        state_api._key(scene) in state_api._BUSY,
        "failed cancellation cannot prematurely release running process",
    )
    assert_that(
        "kill failure" in handle.status()["message"], "cancellation cleanup error is visible"
    )
    job.ready()
    reject(
        lambda handle=handle: pending_api.poll(context, handle),
        "failed cancellation response still never published",
        "kill failure",
    )
    assert_that(job.consumed == 0, "response after cancellation error remains unconsumed")
    unchanged("cancellation cleanup error")

    reset()
    handle = launch()
    job = FakeJob.instances[-1]
    clone = scene.copy()
    context.window.scene = clone
    assert_that(pending_api.reap(context), "supervisor cancels a window's changed scene")
    assert_that(job.cancelled == 1, "supervisor cancellation remains tied to original window scene")
    job.finish_cleanup()
    pending_api.reap(context)
    context.window.scene = scene
    bpy.data.scenes.remove(clone)
    unchanged("supervisor scene change")

    reset()
    errors = []

    def wrong_thread():
        try:
            pending_api.prepare(context, "assembly_check")
        except bridge.BridgeError as exc:
            errors.append(str(exc))

    thread = threading.Thread(target=wrong_thread)
    thread.start()
    thread.join()
    assert_that(
        len(errors) == 1 and "main thread" in errors[0], "worker cannot access Blender boundary"
    )
    unchanged("thread rejection")

# A removed originating scene has no writable RNA; cleanup still releases its
# captured key and cannot send diagnostics to whichever scene became active.
reset()
deleted = bpy.data.scenes.new("Delete while checking")
context.window.scene = deleted
document_state._populate_document(deleted, canonical["part_sources"][0]["document"])
state_api.commit_candidate(context, canonical)
with patch.object(pending_api, "_JOB_FACTORY", FakeJob):
    handle = pending_api.prepare(context, "assembly_check")
    job = FakeJob.instances[-1]
    deleted_key = deleted.as_pointer()
    context.window.scene = scene
    before_fields = {name: getattr(state, name) for name in state_api._STATE_FIELDS}
    bpy.data.scenes.remove(deleted)
    assert_that(pending_api.reap(context), "removed scene causes orphan cancellation")
    job.finish_cleanup()
    assert_that(
        not pending_api.reap(context), "removed scene cleanup completes without writable RNA"
    )
    assert_that(deleted_key not in state_api._BUSY, "removed scene captured busy key released")
    assert_that(
        deleted_key not in state_api._RUNTIME, "removed scene cannot leave reusable runtime trust"
    )
    assert_that(
        before_fields == {name: getattr(state, name) for name in state_api._STATE_FIELDS},
        "removed scene diagnostics never target replacement current scene",
    )
    assert_that(job.consumed == 0, "removed scene native result never consumed")

reset()
assert_that(pending_api.cancel_all("Final cleanup"), "all jobs and scene locks cleaned up")
print("ASSEMBLY_PENDING_SMOKE_OK", len(checks))
