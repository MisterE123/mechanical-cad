"""Cross-adapter native execution ownership, failures and process-only cleanup.

Run native Blender --background --factory-startup --python-exit-code 1.
No replacement lifecycle hooks or general sketch adapter are installed.
"""

import copy
import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
os.environ["MCAD_ROOT"] = str(ROOT)
os.environ.setdefault("MCAD_PYTHON", str(ROOT / ".venv/bin/python"))
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import (  # noqa: E402
    assembly_bridge,
    assembly_job_ui,
    assembly_operator_helpers,
    backend_runtime,
    bridge,
    guarded_operations,
    guarded_transport,
    operators,
    register,
    sidecar_job,
    unregister,
)
from mechanical_cad_blender import (  # noqa: E402
    assembly_pending as pending,
)
from mechanical_cad_blender import (  # noqa: E402
    assembly_state as assembly,
)
from mechanical_cad_blender import (  # noqa: E402
    document_state as part,
)
from mechanical_cad_blender import (  # noqa: E402
    execution_lease as lease,
)

checks = []


def check(value, label):
    assert value, label
    checks.append(label)


def reject(operation, label, contains=None):
    try:
        operation()
    except (bridge.BridgeError, RuntimeError, ValueError) as exc:
        if contains is not None:
            assert contains in str(exc), (contains, str(exc))
        checks.append(label)
        return exc
    raise AssertionError(label)


def part_operation():
    with part.replay_guard(bpy.context):
        raise AssertionError("A blocked Part operation entered its body")


register()
context, scene = bpy.context, bpy.context.scene
canonical = json.loads((ROOT / "examples/reused_blocks.mcad-assembly.json").read_text())
part._populate_document(scene, canonical["part_sources"][0]["document"])
assembly.commit_candidate(context, canonical)
context.view_layer.update()
saved = assembly._capture(context, scene)
scene_key = scene.as_pointer()


def reset():
    check(pending.cancel_all("Test reset"), "reset reaps all pending jobs")
    check(not lease.is_busy(), "reset has no execution lease")
    assembly._restore_fields(scene.mechanical_cad_assembly, saved["fields"])
    assembly._RUNTIME[scene_key] = copy.copy(saved["runtime"])
    assembly._EPOCHS[scene_key] = saved["epoch"]
    context.view_layer.update()


def synchronous_assembly():
    snapshot = assembly._capture(context, scene)
    assembly._prepare_operation(snapshot, canonical)
    return assembly._run_sidecar(context, snapshot=snapshot)


def unlocked(label):
    check(not lease.is_busy() and not part._REPLAY_RUNNING, label + ": execution free")
    check(not pending._ACTIVE and not assembly._BUSY, label + ": transaction free")


# Disabled buttons are advisory; direct execute/racing poll still fails before
# any canonical selection or display mutation and returns the normal error path.
reports = []
reporter = SimpleNamespace(report=lambda levels, message: reports.append((levels, message)))
part_state = scene.mechanical_cad
part_before = part._snapshot_fields(part_state)
objects_before = tuple(
    (obj.as_pointer(), obj.data.as_pointer() if obj.data else 0) for obj in scene.objects
)
check(operators.MCAD_OT_regenerate.poll(context), "Regenerate is available before external work")
check(
    operators.MCAD_OT_activate_feature.poll(context), "Activate is available before external work"
)
blocker = lease.try_acquire()
try:
    check(not bpy.ops.mcad.regenerate.poll(), "Native Regenerate poll is disabled by shared lease")
    check(
        not bpy.ops.mcad.activate_feature.poll(), "Native Activate poll is disabled by shared lease"
    )
    check(
        not bpy.ops.mcad.check_geometry.poll(), "Native geometry poll is disabled by shared lease"
    )
    check(not bpy.ops.mcad.add_rectangle.poll(), "Native feature poll is disabled by shared lease")
    with patch.object(part, "_run_sidecar") as launch:
        for operator in (operators.MCAD_OT_regenerate, operators.MCAD_OT_activate_feature):
            check(
                operator.execute(reporter, context) == {"CANCELLED"},
                "Direct late busy execute returns Cancelled",
            )
            check(
                reports[-1][1] == lease.BUSY_MESSAGE,
                "Direct busy execute gives structured explanation",
            )
            after = part._snapshot_fields(part_state)
            after["last_action_error"] = part_before["last_action_error"]
            check(after == part_before, "Busy execute changes no canonical/display metadata")
        check(not launch.called, "Busy operator never launches a sidecar")
    check(
        tuple((obj.as_pointer(), obj.data.as_pointer() if obj.data else 0) for obj in scene.objects)
        == objects_before,
        "Busy operator preserves exact scene objects and meshes",
    )
    check(lease.is_busy(), "Rejected operator never releases the actual owner's lease")
finally:
    lease.release(blocker)
    part_state.last_action_error = part_before["last_action_error"]
check(operators.MCAD_OT_regenerate.poll(context), "Regenerate becomes available after release")


with part.replay_guard(context):
    check(lease.is_busy() and part._REPLAY_RUNNING, "Part guard owns shared and legacy gates")
    reject(part_operation, "nested Part retains legacy rejection", "already in progress")
    with patch.object(guarded_transport, "execute") as execute:
        reject(
            lambda: synchronous_assembly(),
            "Part excludes synchronous assembly",
            lease.BUSY_MESSAGE,
        )
        check(not execute.called, "blocked synchronous assembly never executes")
    with patch.object(assembly, "_prepare_report") as prepare_report:
        reject(
            lambda: pending.prepare(context, "assembly_check"),
            "Part excludes async assembly before target capture",
            lease.BUSY_MESSAGE,
        )
        check(not prepare_report.called, "blocked async request neither captures nor queues")
    with patch.object(guarded_operations, "canonical_snapshot_guarded") as capture:
        reject(
            lambda: assembly_operator_helpers.canonical_working_part(context),
            "Part excludes canonical snapshot sidecar",
            lease.BUSY_MESSAGE,
        )
        check(not capture.called, "blocked canonical snapshot never launches")
unlocked("Part success")


def failing_part():
    with part.replay_guard(context):
        raise RuntimeError("injected Part failure")


reject(failing_part, "Part failure propagates", "injected Part")
unlocked("Part failure")
reject(
    lambda: part.replay_guard(SimpleNamespace(mode="EDIT_MESH")).__enter__(),
    "invalid Object Mode does not acquire",
    "Object Mode",
)
unlocked("Object Mode rejection")


execute_guarded = guarded_transport.execute
sync_results = []


def inside_sync(*args, **kwargs):
    check(lease.is_busy(), "synchronous assembly owns shared lease")
    reject(part_operation, "synchronous assembly excludes Part", lease.BUSY_MESSAGE)
    reject(
        lambda: pending.prepare(context, "assembly_check"),
        "synchronous assembly excludes async assembly",
        lease.BUSY_MESSAGE,
    )
    result = execute_guarded(*args, **kwargs)
    check(
        result.revalidate(
            kwargs["current_selection"](),
            owner_token=kwargs["owner_token"],
            expected_action="assembly_replay",
            require_success=True,
        )["ok"],
        "synchronous assembly returns fresh guarded evidence",
    )
    sync_results.append(result)
    return result


with patch.object(guarded_transport, "execute", side_effect=inside_sync):
    result = synchronous_assembly()
    check(result is sync_results[-1], "sync response passes through")
unlocked("synchronous success")
for target, name in [(assembly, "_configuration"), (guarded_transport, "execute")]:
    with patch.object(target, name, side_effect=RuntimeError("injected sync failure")):
        reject(
            lambda: synchronous_assembly(),
            name + " sync failure propagates",
            "injected sync",
        )
    unlocked(name + " sync failure")


capture_guarded = guarded_operations.canonical_snapshot_guarded


def inside_capture(*args, **kwargs):
    check(lease.is_busy(), "canonical capture owns shared lease")
    check(not part._REPLAY_RUNNING, "canonical capture does not change legacy Part flag")
    reject(part_operation, "canonical capture excludes Part", lease.BUSY_MESSAGE)
    reject(
        lambda: synchronous_assembly(),
        "canonical capture excludes synchronous assembly",
        lease.BUSY_MESSAGE,
    )
    reject(
        lambda: pending.prepare(context, "assembly_check"),
        "canonical capture excludes async assembly",
        lease.BUSY_MESSAGE,
    )
    return capture_guarded(*args, **kwargs)


with patch.object(guarded_operations, "canonical_snapshot_guarded", side_effect=inside_capture):
    check(
        assembly_operator_helpers.canonical_working_part(context)
        == canonical["part_sources"][0]["document"],
        "canonical snapshot result passes through",
    )
unlocked("canonical snapshot success")
for target, name in [
    (backend_runtime, "capture"),
    (guarded_operations, "canonical_snapshot_guarded"),
]:
    with patch.object(target, name, side_effect=RuntimeError("injected capture failure")):
        reject(
            lambda: assembly_operator_helpers.canonical_working_part(context),
            name + " canonical capture failure propagates",
            "injected capture",
        )
    unlocked(name + " canonical capture failure")


class ControlledJob:
    start_failure = None
    instances = []

    def __init__(self, prepared, selection, *, owner_token):
        self.request = prepared.guarded_request()
        self.selection, self.owner_token = selection, owner_token
        self.state = "created"
        self.consumed = 0
        self.instances.append(self)

    @property
    def done(self):
        return self.state in {"failed", "cancelled"}

    def start(self, current_selection):
        self.selection.assert_current(current_selection)
        if self.start_failure == "before":
            raise RuntimeError("injected start before launch")
        self.state = "running"
        if self.start_failure == "after":
            raise RuntimeError("injected start after launch")
        return self

    def cancel(self):
        self.state = "cancelled" if self.state == "created" or self.done else "cancelling"
        return True

    def poll(self, current_selection):
        self.selection.assert_current(current_selection)
        return self.state

    def wait(self, timeout=None):
        return self.done

    def result(self, current_selection, *, owner_token):
        self.selection.assert_current(current_selection)
        assert owner_token is self.owner_token
        self.consumed += 1
        raise bridge.BridgeError("injected terminal start failure")

    def request_snapshot(self):
        return copy.deepcopy(self.request)


def launch():
    return pending.prepare(context, "assembly_check")


for target, name in [
    (assembly, "_prepare_report"),
    (assembly_bridge, "build_request"),
    (assembly, "_configuration"),
    (pending, "_JOB_FACTORY"),
    (pending, "PendingReport"),
]:
    reset()
    with patch.object(target, name, side_effect=RuntimeError("injected construction failure")):
        reject(launch, name + " construction failure propagates", "injected construction")
    unlocked(name + " construction failure")

reset()
with (
    patch.object(pending, "_JOB_FACTORY", side_effect=RuntimeError("injected construction")),
    patch.object(assembly, "_recover_report", side_effect=RuntimeError("injected recovery")),
):
    reject(launch, "compound construction and recovery failure propagates", "injected recovery")
unlocked("compound construction and recovery failure")
reject(
    lambda: pending.prepare(context, "assembly_sample", joint_id="slide_a", values=[]),
    "invalid sample request releases prepared ownership",
    "explicit list",
)
unlocked("invalid sample request")

reset()
with patch.object(pending, "_JOB_FACTORY", ControlledJob):
    ControlledJob.start_failure = "before"
    reject(launch, "pre-launch start failure propagates", "before launch")
    unlocked("pre-launch start failure")
    ControlledJob.start_failure = "after"
    reject(launch, "post-launch start failure propagates", "after launch")
    handle = pending.active_for_scene(scene)
    check(lease.is_busy() and handle._phase == "cancelling", "start cleanup retains lease")
    handle._job.state = "cancelled"
    check(not pending.reap(context), "start cleanup can be supervised without publication")
    unlocked("post-launch start failure cleanup")
    ControlledJob.start_failure = None

    reset()
    handle = launch()
    token = handle._lease_token
    check(type(token) is object, "pending owns only opaque pure execution token")
    reject(part_operation, "pending assembly excludes Part", lease.BUSY_MESSAGE)
    reject(
        lambda: synchronous_assembly(),
        "pending assembly excludes synchronous assembly",
        lease.BUSY_MESSAGE,
    )
    with patch.object(guarded_operations, "canonical_snapshot_guarded") as capture:
        reject(
            lambda: assembly_operator_helpers.canonical_working_part(context),
            "pending assembly excludes canonical snapshot sidecar",
            lease.BUSY_MESSAGE,
        )
        check(not capture.called, "pending assembly prevents capture launch")
    # This rejection is process-wide, before even resolving another scene's RNA.
    reject(
        lambda: pending.prepare(SimpleNamespace(scene=object()), "assembly_check"),
        "pending assembly excludes another scene",
        lease.BUSY_MESSAGE,
    )
    pending.cancel(handle, "User cancellation")
    pending._release(handle)
    check(lease.is_busy() and scene_key in assembly._BUSY, "early release cannot clear live job")
    check(not pending.cancel_all("Still cleaning up", wait_timeout=0), "bounded wait stays pending")
    check(lease.is_busy(), "bounded shutdown timeout retains lease")
    handle._job.state = "cancelled"
    check(not pending.reap(context), "cancel cleanup releases through supervisor")
    unlocked("cancel cleanup")

    reset()
    newer = launch()
    pending._release(handle)
    check(lease.is_busy(), "old finalizer cannot release newer execution lease")
    check(
        pending.active_for_scene(scene) is newer, "old finalizer cannot release newer transaction"
    )
    pending.cancel(newer)
    newer._job.state = "cancelled"
    pending.reap(context)
    unlocked("stale finalizer cleanup")

    reset()
    failed_cancel = launch()
    with patch.object(failed_cancel._job, "cancel", side_effect=RuntimeError("injected kill")):
        pending.cancel(failed_cancel)
    check(lease.is_busy(), "failed cancellation request retains shared execution ownership")
    reject(part_operation, "failed cancellation continues excluding Part", lease.BUSY_MESSAGE)
    failed_cancel._job.state = "cancelled"
    pending.reap(context)
    unlocked("failed cancellation cleanup")

# Exercise the real SidecarJob start path: worker start failure is a terminal
# state rather than an exception escaping start(). Poll must release the token.
reset()
with patch.object(sidecar_job.threading.Thread, "start", side_effect=RuntimeError("thread start")):
    terminal = launch()
check(terminal._job.done and lease.is_busy(), "terminal start failure retains lease until observed")
reject(
    lambda: pending.poll(context, terminal), "terminal failure reports and releases", "thread start"
)
unlocked("terminal start failure")

# A real sleeping owned child is killed and reaped before the transport can
# advertise completion. Delay that final advertisement to test cancellation's
# ownership boundary without depending on a scheduler race.
reset()
with tempfile.TemporaryDirectory(prefix="mcad-lease-child-") as folder:
    root = Path(folder)
    package = root / "src/mechanical_cad"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "sidecar.py").write_text(
        "import json, os, sys, time\n"
        "from pathlib import Path\n"
        "json.load(sys.stdin)\n"
        "Path('owned-pid').write_text(str(os.getpid()))\n"
        "time.sleep(60)\n"
    )
    cleanup_reached, allow_terminal = threading.Event(), threading.Event()
    exchange = sidecar_job.SidecarJob._exchange

    def delayed_terminal(job):
        try:
            return exchange(job)
        finally:
            cleanup_reached.set()
            if not allow_terminal.wait(10):
                raise RuntimeError("test cleanup barrier timed out")

    selected = backend_runtime.BackendSelection.capture(
        str(root),
        os.environ["MCAD_PYTHON"],
        60,
        generation=0,
        lifetime_id="execution-lease-controlled-child",
    )
    with (
        patch.object(sidecar_job.SidecarJob, "_exchange", delayed_terminal),
        patch.object(
            assembly,
            "_configuration",
            return_value=(selected, 0.1),
        ),
        patch.object(assembly, "_current_selection", return_value=selected),
    ):
        real = launch()
        try:
            deadline = time.monotonic() + 10
            while not (root / "owned-pid").exists():
                assert time.monotonic() < deadline, "owned sidecar did not launch"
                assert not real._job.done
                time.sleep(0.01)
            pid = int((root / "owned-pid").read_text())
            pending.cancel(real, "Real cancellation")
            check(cleanup_reached.wait(10), "real worker completed process and file cleanup")
            check(not Path(f"/proc/{pid}").exists(), "real owned child was reaped")
            check(
                lease.is_busy() and not real._job.done, "lease waits for confirmed terminal state"
            )
            reject(
                part_operation, "cancelled native cleanup still excludes Part", lease.BUSY_MESSAGE
            )
            pending.detach_all("Original RNA invalidated")
            check(real._lease_token is not None, "detach keeps pure token")
            check(set(real._transaction) == {"key", "snapshot"}, "detach retains only numeric keys")
            check(
                real._abort_error.__traceback__ is None
                and real._abort_error.__context__ is None
                and real._abort_error.__cause__ is None,
                "detach retains no exception traceback chain",
            )
            check(lease.is_busy(), "detach cannot release real cancelling job")
        finally:
            allow_terminal.set()
            real._job.wait(10)
            pending.cancel(real)
            pending.reap(context)
    unlocked("real native cleanup")

# Native disable removes RNA but must not reset the process-wide gate. The old
# no-publication supervisor remains its owner, without any new registrations.
assembly.replay(context)
with patch.object(pending, "_JOB_FACTORY", ControlledJob):
    disabled = launch()
unregister()
check(disabled._detached and lease.is_busy(), "unregister retains detached execution ownership")
check(not hasattr(bpy.types.Scene, "mechanical_cad"), "native unregister removes Part RNA")
check(
    not hasattr(bpy.types.Scene, "mechanical_cad_assembly"),
    "native unregister removes assembly RNA",
)
check(assembly_job_ui._supervise() == 0.1, "existing disabled supervisor waits for cleanup")
check(lease.try_acquire() is None, "disable does not let newer work overlap cleanup")
disabled._job.state = "cancelled"
check(assembly_job_ui._supervise() is None, "disabled cleanup releases via existing supervisor")
unlocked("disabled cleanup")
check(disabled._job.consumed == 0, "disabled cleanup never consumes a result")
if bpy.app.timers.is_registered(assembly_job_ui._supervise):
    bpy.app.timers.unregister(assembly_job_ui._supervise)
check(
    not any(name == "OCP" or name.startswith("OCP.") or name == "slvs" for name in sys.modules),
    "native CAD libraries remain outside Blender",
)
print("EXECUTION_LEASE_SMOKE_OK", len(checks))
