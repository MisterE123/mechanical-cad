"""Native Assembly guarded publication, revocation and corrected-settings gates.

Run with native Blender --background --factory-startup --python-exit-code 1.
All successful evidence below comes from the configured real guarded sidecar.
"""

import copy
import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import patch

import bpy

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
os.environ["MCAD_ROOT"] = str(ROOT)
os.environ.setdefault("MCAD_PYTHON", str(ROOT / ".venv/bin/python"))
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import assembly_display as display  # noqa: E402
from mechanical_cad_blender import assembly_pending as pending  # noqa: E402
from mechanical_cad_blender import assembly_state as state_api  # noqa: E402
from mechanical_cad_blender import (  # noqa: E402
    backend_runtime,
    bridge,
    document_state,
    guarded_evidence,
    guarded_operations,
    register,
    unregister,
)

checks = []


def check(value, label):
    assert value, label
    checks.append(label)


def reject(operation, label):
    try:
        operation()
    except (ValueError, RuntimeError, bridge.BridgeError):
        checks.append(label)
        return
    raise AssertionError(label)


register()
addon = bpy.context.preferences.addons.new()
addon.module = "mechanical_cad_blender"
prefs = addon.preferences
context, scene = bpy.context, bpy.context.scene
state = scene.mechanical_cad_assembly
key = scene.as_pointer()
assembly = json.loads((ROOT / "examples/reused_blocks.mcad-assembly.json").read_text())
document_state._populate_document(scene, assembly["part_sources"][0]["document"])
accepted = state_api.commit_candidate(context, assembly)
state_api.check(context)
canonical, part = state.document_json, scene.mechanical_cad.document_json
unrelated = bpy.data.objects.new("Capability test unrelated object", None)
scene.collection.objects.link(unrelated)
unrelated["untouched"] = "yes"


def current():
    return backend_runtime.capture(context)


def recover():
    state_api.replay(context)
    state_api.check(context)
    check(state_api.display_is_current(context), "fresh replay restores current display")
    check(state_api.report_is_current(context), "fresh check restores exact report authority")


def stale(label):
    check(not state_api.display_is_current(context), label + ": display rejected")
    check(not state_api.report_is_current(context), label + ": report rejected")
    check(state.display_status == "STALE", label + ": display visibly stale")
    check(state.verification_status == "STALE", label + ": report visibly stale")
    check(key not in state_api._RUNTIME, label + ": no restored runtime association")
    check(state.document_json == canonical, label + ": canonical bytes preserved")
    check(scene.mechanical_cad.document_json == part, label + ": working Part preserved")
    check(unrelated["untouched"] == "yes", label + ": unrelated object preserved")


# Neither ordinary JSON nor a legacy validated subclass can authorize production.
for label, value in (
    ("ordinary result", dict(accepted)),
    ("legacy projection", accepted),
    ("mutated public result", copy.deepcopy(accepted)),
    ("mutated private request", copy.deepcopy(accepted)),
):
    if label == "mutated public result":
        value["ok"] = False
    if label == "mutated private request":
        value._request["policy"] = None
    reject(lambda value=value: display.stage(scene, state.owner_id, value), label + " cannot stage")
    transaction = state_api._prepare_report(context)
    try:
        reject(
            lambda value=value, transaction=transaction: state_api._publish_report(
                context, transaction, value
            ),
            label + " cannot publish a report",
        )
    finally:
        state_api._BUSY.discard(key)

# A guarded canonical snapshot retains serialization authority only.
snapshot = state_api._capture(context, scene)
snapshot_evidence = guarded_operations.canonical_snapshot_guarded(
    assembly["part_sources"][0]["document"],
    selection=snapshot["selection"],
    owner_token=snapshot["owner_token"],
    current_selection=current,
)
check(type(snapshot_evidence) is guarded_evidence.GuardedEvidence, "snapshot is truly guarded")
reject(
    lambda: display.stage(
        scene,
        state.owner_id,
        snapshot_evidence,
        owner_token=snapshot["owner_token"],
        current_selection=current,
    ),
    "pure snapshot cannot stage native geometry",
)
reject(
    lambda: state_api._projection(context, snapshot, snapshot_evidence, actions="assembly_check"),
    "pure snapshot cannot become assembly check authority",
)

# A detached response remains readable, but publication is one-shot.
state_api._prepare_operation(snapshot, assembly)
evidence = state_api._run_sidecar(context, snapshot=snapshot)
projection = evidence.revalidate(current(), owner_token=snapshot["owner_token"])
projection._request["policy"] = None
reject(
    lambda: evidence.revalidate(
        current(), owner_token=snapshot["owner_token"], projection=projection
    ),
    "mutated private operation request fails retained-evidence validation",
)
transaction = display.stage(
    scene,
    state.owner_id,
    evidence,
    owner_token=snapshot["owner_token"],
    current_selection=current,
)
transaction.publish()
transaction.finalize()
transaction = display.stage(
    scene,
    state.owner_id,
    evidence,
    owner_token=snapshot["owner_token"],
    current_selection=current,
)
reject(transaction.publish, "same guarded operation cannot publish twice")
transaction.discard()
check(
    evidence.revalidate(current(), owner_token=snapshot["owner_token"]),
    "retained read survives consumption",
)

# Pure save validation cannot restore display/report authority.
backend_runtime.revoke("Test fresh save validation against retained historical display")
saved_report = state.report_json
check(state_api.validate_snapshot(context)["ok"], "save validates freshly through guarded sidecar")
stale("fresh save validation")
check(state.report_json == saved_report, "save validation does not replace historical report")
recover()

# Exact partial native evidence remains useful, visibly incomplete and never a pass.
partial_check = state_api._report_only(context, "assembly_check", coordinates={"slide_a": -1})
check(
    not partial_check["ok"] and not partial_check["report"]["complete"],
    "sync Check retains native partial failure",
)
check(state_api.report_is_current(context), "partial Check has current exact request binding")
check(
    "incomplete" in state.verification_message.lower(), "partial Check explicitly states incomplete"
)
partial_sample = state_api.sample(context, "slide_a", [-1, 100])
check(
    not partial_sample["ok"] and not partial_sample["report"]["complete"],
    "sync Sample retains native partial failure",
)
check(state_api.report_is_current(context), "partial Sample has current exact request binding")
handle = pending.prepare(context, "assembly_sample", joint_id="slide_a", values=[-1, 100])
deadline = time.monotonic() + 90
response = None
while not handle.done and time.monotonic() < deadline:
    response = pending.poll(context, handle)
    if not handle.done:
        time.sleep(0.01)
check(handle.done and response is not None, "async partial Sample completes through guarded job")
check(
    not response["ok"] and not response["report"]["complete"], "async partial diagnostics retained"
)
check(state_api.report_is_current(context), "async partial report has exact current association")
check(state.document_json == canonical, "partial checks never publish sampled poses")

# One owner/selection cannot substitute another operation, including a fresh
# nonce for byte-identical operation data. Build the replacement through a real
# guarded process, then inject it at the transport seam after intent capture.
for action in ("assembly_replay", "assembly_check", "assembly_sample"):
    for alter_source in (False, True):
        before_report = state.report_json
        before_objects = {obj.as_pointer() for obj in display.owned_objects(scene, state.owner_id)}

        def substitute(_context, *, snapshot, alter_source=alter_source):
            operation = snapshot["prepared"].operation_request()
            replacement = operation["assembly"]
            if alter_source:
                replacement["name"] = "UNREQUESTED ASSEMBLY"
            return guarded_operations.assembly_action_guarded(
                replacement,
                operation["action"],
                selection=snapshot["selection"],
                owner_token=snapshot["owner_token"],
                current_selection=current,
                **{
                    name: operation[name]
                    for name in ("coordinates", "requirements", "policy", "samples", "preset_id")
                },
            )

        def attempt(action=action):
            if action == "assembly_replay":
                return state_api.replay(context)
            if action == "assembly_sample":
                return state_api.sample(context, "slide_a", [30, 50])
            return state_api.check(context)

        with patch.object(state_api, "_run_sidecar", substitute):
            reject(
                attempt, f"{action} rejects substituted full request, source changed={alter_source}"
            )
        check(state.document_json == canonical, "substitution cannot change accepted assembly")
        check(state.report_json == before_report, "substitution cannot relabel another report")
        check(state_api.report_is_current(context), "substitution preserves old current report")
        check(
            {obj.as_pointer() for obj in display.owned_objects(scene, state.owner_id)}
            == before_objects,
            "substitution does not replace accepted display",
        )

# Supported RNA preference A→B→A revokes already accepted evidence immediately.
report = state.report_json
before = backend_runtime.stamp()
prefs.timeout_seconds = 61
prefs.timeout_seconds = 60
check(backend_runtime.stamp() != before, "supported preference ABA advances generation")
stale("completed-evidence ABA")
check(state.report_json == report, "ABA retains diagnostic JSON as historical data")
reject(lambda: state_api.check(context), "Check preflight rejects backend-stale display")
recover()

# Ready but unconsumed native work is cancelled by the same configuration owner.
handle = pending.prepare(context, "assembly_check")
handle._job.wait(90)
check(handle._job.state == "ready", "native request reaches ready before publication")
report = state.report_json
prefs.timeout_seconds = 61
prefs.timeout_seconds = 60
reject(lambda: pending.poll(context, handle), "ready native result rejected after settings ABA")
check(
    handle.done and state.report_json == report, "ready cancellation preserves old diagnostic bytes"
)
check(
    not pending._ACTIVE and key not in state_api._BUSY, "ready cancellation releases existing owner"
)
stale("ready cancellation")
recover()

# Settings callbacks inside RNA publication cannot be rolled back into authority.
write = state_api._write_fields
candidate = state_api.read_assembly(state)
candidate["name"] = "Never accepted after settings change"
for action in ("replay", "report"):
    for throwing in (False, True):
        before_report = state.report_json
        before_objects = {obj.as_pointer() for obj in display.owned_objects(scene, state.owner_id)}

        def changing_write(target, values, throwing=throwing):
            write(target, values)
            prefs.timeout_seconds = 61
            prefs.timeout_seconds = 60
            if throwing:
                raise RuntimeError("Injected error after preference callback")

        with patch.object(state_api, "_write_fields", changing_write):
            reject(
                lambda action=action: (
                    state_api.commit_candidate(context, candidate)
                    if action == "replay"
                    else state_api.check(context)
                ),
                f"{action} rejects settings mutation during RNA publication, throw={throwing}",
            )
        stale(f"{action} rollback after ABA, throw={throwing}")
        check(state.report_json == before_report, "failed publication restores diagnostic bytes")
        check(
            {obj.as_pointer() for obj in display.owned_objects(scene, state.owner_id)}
            == before_objects,
            "failed publication restores exact retained display objects",
        )
        recover()


# Local runtime clear cannot collide with a prior numeric epoch during rollback.
def clearing_write(target, values):
    write(target, values)
    state_api.clear_runtime()
    raise RuntimeError("Injected runtime clear during RNA publication")


with patch.object(state_api, "_write_fields", clearing_write):
    reject(
        lambda: state_api.check(context), "runtime clear during publication rejects rollback trust"
    )
stale("runtime-clear rollback")
recover()

# The original replay capability, not just matching display bytes, owns a report.
transaction = state_api._prepare_report(context)
try:
    state_api._prepare_operation(transaction["snapshot"], transaction["assembly"], "assembly_check")
    report_evidence = state_api._run_sidecar(context, snapshot=transaction["snapshot"])
    runtime = state_api._RUNTIME[key]
    captured = runtime["display_evidence"]
    runtime["display_evidence"] = evidence
    reject(
        lambda: state_api._publish_report(context, transaction, report_evidence),
        "swapped display capability rejects report before RNA publication",
    )
    runtime["display_evidence"] = captured
finally:
    state_api._BUSY.discard(key)
check(state_api.report_is_current(context), "rejected display swap preserves accepted report")
check(
    not any(name == "OCP" or name.startswith("OCP.") for name in sys.modules),
    "native CAD stays outside Blender",
)
unregister()
print("ASSEMBLY_CAPABILITY_SMOKE_OK", len(checks))
