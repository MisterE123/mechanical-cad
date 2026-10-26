"""Exact completed-request publication without a duplicate native Part replay.

Uses a real SidecarJob and native Blender5.2.2. This is the publication seam only;
no general editor or new lifecycle registration is installed by this test.
"""

import copy
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
os.environ["MCAD_ROOT"] = str(ROOT)
os.environ.setdefault("MCAD_PYTHON", str(ROOT / ".venv/bin/python"))
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import (  # noqa: E402
    backend_runtime,
    bridge,
    display,
    execution_lease,
    general_authoring,
    general_sketch_draft,
    guarded_transport,
    part_publication,
    register,
    unregister,
    workspace,
)
from mechanical_cad_blender import document_state as doc  # noqa: E402

checks = []


def check(value, label):
    assert value, label
    checks.append(label)


def reject(operation, text=None):
    try:
        operation()
    except bridge.BridgeError as exc:
        if text:
            check(text in str(exc), "Rejection explains " + text)
        checks.append("Rejected without an unhandled exception")
        return
    raise AssertionError("Expected publication rejection")


def objects():
    return tuple(
        (obj.as_pointer(), obj.data.as_pointer() if obj.data else 0) for obj in scene.objects
    )


def snapshot():
    return doc._snapshot_fields(scene.mechanical_cad), objects()


def no_launch():
    return patch.object(doc, "_run_sidecar", side_effect=AssertionError("Duplicate native replay"))


def retire_check(intent):
    check(
        intent.retired and intent._binding is None and intent._workspace is None,
        "Consumed intent drops native bindings",
    )
    check(intent._owner_snapshot is None, "Consumed intent drops owner capture")
    check(not execution_lease.is_busy(), "Publication releases execution")


def execute_request(intent):
    token = execution_lease.try_acquire()
    check(token is not None, "Actual transport owns execution")
    job = guarded_transport.GuardedJob(
        intent.prepared,
        intent.selection,
        owner_token=intent.owner_token,
    )
    try:
        job.start(backend_runtime.capture(context))
        check(job.wait(30) and job.done, "Actual child is reaped before publication")
        return job.result(backend_runtime.capture(context), owner_token=intent.owner_token)
    finally:
        job.cancel()
        check(job.wait(5), "Transport cleanup completes")
        execution_lease.release(token)


def prepared(context, document):
    intent = part_publication.prepare(context, document)
    return intent, execute_request(intent)


register()
context, scene = bpy.context, bpy.context.scene
open_document = json.loads((ROOT / "examples/open_line_sketch.mcad.json").read_text())
blank = {
    "schema_version": 1,
    "id": "blank",
    "name": "Part",
    "units": "mm",
    "parameters": {},
    "features": [],
    "active_feature": None,
}
doc._populate_document(scene, blank)
original = copy.deepcopy(open_document)
intent, response = prepared(context, open_document)
request = intent.request
check(
    request["result_version"] == 2 and request["options"]["linear_deflection"] == 0.1,
    "Exact output version and tolerance captured",
)
check(response.successful, "Actual open replay succeeds")
open_document["name"] = "External caller mutation"
request["options"]["linear_deflection"] = 9
check(intent.request["document"] == original, "Candidate detached from caller")
check(
    intent.request["options"]["linear_deflection"] == 0.1,
    "Request getter cannot change captured options",
)
with (
    no_launch(),
    patch.object(bridge, "_exchange_raw", side_effect=AssertionError("Duplicate exchange")),
):
    check(intent.publish(context, response), "Completed native open replay publishes once")
check(
    json.loads(scene.mechanical_cad.document_json) == original,
    "Exact captured candidate becomes canonical",
)
check(
    scene.mechanical_cad.status == "READY" and scene.mechanical_cad.volume == 0,
    "Open publication remains volume-free",
)
check(
    len(display._owned_objects(scene)) == 1 and not display._owned_objects(scene)[0].data.polygons,
    "Published open sketch is a wire",
)
retire_check(intent)
before = snapshot()
reject(lambda: intent.publish(context, response), "retired")
check(snapshot() == before, "Second acceptance cannot publish twice")
open_document = original

# No partial state publication when another operation wins reacquisition.
intent, response = prepared(context, open_document)
before = snapshot()
token = execution_lease.try_acquire()
try:
    reject(lambda: intent.publish(context, response), execution_lease.BUSY_MESSAGE)
    check(
        snapshot() == before and execution_lease.is_busy(),
        "Busy failure preserves data and actual owner's lease",
    )
    check(intent.retired and intent._binding is None, "Busy intent retires rather than queues")
finally:
    execution_lease.release(token)

# Every late native binding/configuration failure leaves externally changed state
# intact. No rollback should overwrite an edit made before publication begins.
for field in ("document", "owner", "units", "slot", "settings", "view_layer", "scene"):
    intent, response = prepared(context, open_document)
    old_fields = doc._snapshot_fields(scene.mechanical_cad)
    old_scale = scene.unit_settings.scale_length
    old_layer = context.view_layer
    clone = None
    if field == "document":
        scene.mechanical_cad.document_json += " "
    elif field == "owner":
        scene.mechanical_cad.owner_id += "_external"
    elif field == "units":
        scene.unit_settings.scale_length = 0.01
    elif field == "slot":
        scene.mechanical_cad.sketch_draft_json = "external retained bytes"
    elif field == "view_layer":
        context.window.view_layer = scene.view_layers.new("publication test layer")
    elif field == "scene":
        clone = scene.copy()
        context.window.scene = clone
    before = snapshot()
    if field == "settings":
        backend_runtime.revoke("test setting A to B")
        backend_runtime.revoke("test setting B to A")
        before = snapshot()
    with no_launch():
        reject(lambda intent=intent, response=response: intent.publish(context, response))
    check(snapshot() == before, "Late " + field + " preserves externally changed source")
    retire_check(intent)
    if clone:
        context.window.scene = scene
        bpy.data.scenes.remove(clone)
    if field == "view_layer":
        extra = context.view_layer
        context.window.view_layer = old_layer
        scene.view_layers.remove(extra)
    scene.unit_settings.scale_length = old_scale
    doc._restore_fields(scene.mechanical_cad, old_fields)

check(
    doc.regenerate(context), "Fresh replay restores authority after deliberate settings revocation"
)

# The Part seam binds pure sketch intent as well as its native context. An
# unchanged canonical Part must not permit a late Finish after a local UI edit.
for change in ("session", "ui", "command", "retired"):
    authoring = general_authoring.GeneralSketchAuthoringState(
        general_sketch_draft.GeneralSketchDraft(
            scene.mechanical_cad.document_json, open_document["active_feature"], True
        )
    )
    owner = SimpleNamespace(
        alive=True, session_id="test-owner", draft=authoring, valid_context=lambda: True
    )
    with patch.object(workspace, "active_draft", return_value=owner):
        intent, response = prepared(context, open_document)
        if change == "session":
            owner.session_id = "different-owner"
        elif change == "ui":
            authoring.select_tool("Circle")
        elif change == "command":
            authoring.command_draft.execute(
                general_sketch_draft.AddPoint(general_sketch_draft.PointSeed(77, 88))
            )
        else:
            owner.alive = False
        before = snapshot()
        with no_launch():
            reject(lambda intent=intent, response=response: intent.publish(context, response))
        check(snapshot() == before, "Late sketch " + change + " keeps canonical/display exact")
        retire_check(intent)

# The final publication check is still inside the rollback seam. An editor
# callback cannot change the accepted command intent during display creation.
authoring = general_authoring.GeneralSketchAuthoringState(
    general_sketch_draft.GeneralSketchDraft(
        scene.mechanical_cad.document_json, open_document["active_feature"], True
    )
)
owner = SimpleNamespace(
    alive=True, session_id="late-test-owner", draft=authoring, valid_context=lambda: True
)
real_apply = doc._apply_result


def change_editor_during_apply(*args):
    result = real_apply(*args)
    authoring.select_tool("Circle")
    return result


with patch.object(workspace, "active_draft", return_value=owner):
    intent, response = prepared(context, open_document)
    before = snapshot()
    with no_launch(), patch.object(doc, "_apply_result", change_editor_during_apply):
        reject(lambda: intent.publish(context, response), "sketch owner")
    check(snapshot() == before, "Post-publication editor change rolls back the whole Part")
    check(authoring.tool == "Circle", "Rollback preserves the newer pure editor intent")
    retire_check(intent)

# Strict validation is repeated across this seam even if a previous caller
# thought the response was safe. Hashing alone cannot authorize forged output.
for mutation in ("fingerprint", "version", "geometry"):
    intent, response = prepared(context, open_document)
    forged = response.response_snapshot()
    if mutation == "fingerprint":
        forged["input_fingerprint"] = "0" * 64
    elif mutation == "version":
        forged["result_version"] = 1
    else:
        forged["result"]["features"][0]["output"]["profile"]["state"] = "future_variant"
    before = snapshot()
    with no_launch():
        reject(
            lambda intent=intent, forged=forged: intent.publish(context, forged),
            "evidence was rejected",
        )
    check(snapshot() == before, "Forged " + mutation + " preserves canonical/display")
    retire_check(intent)

# The existing acquisition-ledger rollback remains the only publication path.
intent, response = prepared(context, open_document)
before = snapshot()
old_meshes = set(bpy.data.meshes)
real_apply = doc._apply_result
foreign = bpy.data.meshes.new("Unrelated publication test mesh")


def late_failure(*args):
    real_apply(*args)
    scene.mechanical_cad.owner_id = "mutated after apply"
    scene.mechanical_cad.last_good_mesh = foreign
    raise RuntimeError("Injected late display failure")


with no_launch(), patch.object(doc, "_apply_result", late_failure):
    try:
        intent.publish(context, response)
    except RuntimeError as exc:
        check("late display" in str(exc), "Original publication failure stays explicit")
    else:
        raise AssertionError("Expected injected publication failure")
check(snapshot() == before, "Async seam restores exact prior state and display identities")
check(
    set(bpy.data.meshes) == old_meshes | {foreign},
    "Rollback preserves unrelated mesh without candidate leaks",
)
retire_check(intent)
bpy.data.meshes.remove(foreign)

# An unavailable consumed profile is a full replay failure. Its editable source
# remains the caller's candidate; it never replaces the accepted open document.
consumed = copy.deepcopy(open_document)
consumed["features"].append(
    {
        "id": "pad",
        "kind": "extrude",
        "label": "Pad",
        "params": {"length": 10},
        "inputs": {"profile": consumed["active_feature"]},
    }
)
consumed["active_feature"] = "pad"
intent = part_publication.prepare(context, consumed)
failed = execute_request(intent)
check(not failed.successful, "Actual unavailable-profile extrusion replay fails")
before = snapshot()
with no_launch():
    reject(lambda: intent.publish(context, failed))
check(
    snapshot() == before, "Failed downstream replay preserves editable candidate and accepted Part"
)
retire_check(intent)

# A live owner ordinarily reports invalid_context immediately after a successful
# canonical edit. The post-publication guard must compare its retained editor
# identity, not reject the intentional original-base-to-candidate transition.
authoring = general_authoring.GeneralSketchAuthoringState(
    general_sketch_draft.GeneralSketchDraft(
        scene.mechanical_cad.document_json, open_document["active_feature"], True
    )
)
owner = SimpleNamespace(
    alive=True,
    session_id="published-base-owner",
    draft=authoring,
    valid_context=lambda: scene.mechanical_cad.document_json == authoring.document_json,
)
candidate = copy.deepcopy(open_document)
candidate["name"] = "Accepted changed base"
with patch.object(workspace, "active_draft", return_value=owner):
    intent = part_publication.prepare(context, candidate)
    completed = execute_request(intent)
    with no_launch():
        check(
            intent.publish(context, completed), "Original owner survives intended base transition"
        )
    check(not owner.valid_context(), "Owner original base is intentionally old after publication")
    check(json.loads(scene.mechanical_cad.document_json) == candidate, "New base is accepted once")
    retire_check(intent)

# Explicit owner retirement makes late callbacks safe after native RNA removal.
intent, response = prepared(context, open_document)
intent.retire()
unregister()
reject(lambda: intent.publish(context, response), "retired")
retire_check(intent)
check(
    not any(name == "OCP" or name.startswith("OCP.") or name == "slvs" for name in sys.modules),
    "Native CAD imports remain outside Blender",
)
print("PART_PUBLICATION_SMOKE_OK", len(checks))
