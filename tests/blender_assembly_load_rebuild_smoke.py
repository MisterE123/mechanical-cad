"""Fresh-process accepted Assembly cache rebuilding, never report resurrection.

Run writer then reader (MCAD_ASSEMBLY_REOPEN=1), same MCAD_ASSEMBLY_LOAD_DIRECTORY.
Background timer pumping is not GUI or installed-package qualification.
"""

import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import patch

import bpy

ROOT = Path(os.environ["MCAD_ROOT"])
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import (  # noqa: E402
    assembly_display,
    assembly_export_owner,
    assembly_pending,
    backend_runtime,
    document_state,
    execution_lease,
    register,
    sketch_pending,
    workspace,
)
from mechanical_cad_blender import (  # noqa: E402
    assembly_state as state_api,
)
from mechanical_cad_blender import (  # noqa: E402
    history_rebuild as rebuild,
)

OUT = Path(os.environ["MCAD_ASSEMBLY_LOAD_DIRECTORY"])
REPORT = (
    "report_json",
    "report_document_json",
    "report_request_json",
    "report_working_part_json",
    "report_preset_id",
)
PART = ("document_json", "repair_intent_json", "sketch_draft_json", "sketch_annotation_json")
checks = []
register()


def check(value, label):
    assert value, label
    checks.append(label)
    print("ASSEMBLY_LOAD_CHECK", label, flush=True)


def snapshot():
    scene = bpy.context.scene
    return {
        "assembly": scene.mechanical_cad_assembly.document_json,
        "owner": scene.mechanical_cad_assembly.owner_id,
        "report": {key: getattr(scene.mechanical_cad_assembly, key) for key in REPORT},
        "part": {key: getattr(scene.mechanical_cad, key) for key in PART},
    }


def drain():
    deadline = time.monotonic() + 60
    while rebuild._PENDING is not None or execution_lease.is_busy():
        assert time.monotonic() < deadline, "Restoration cleanup timed out"
        # Real panels poll Export eligibility while load rebuilding is queued.
        assembly_export_owner.availability_reason(bpy.context)
        rebuild._tick()
        assembly_pending.reap(bpy.context)
        sketch_pending.reap()
        time.sleep(0.01)
    if bpy.app.timers.is_registered(rebuild._tick):
        bpy.app.timers.unregister(rebuild._tick)


def open_file(name="assembly"):
    bpy.ops.wm.open_mainfile(filepath=str(OUT / (name + ".blend")))
    expected = json.loads((OUT / (name + ".expected.json")).read_text())
    check(snapshot() == expected, "Load preserved exact source/report/dormant bytes")
    return expected


def fresh(expected):
    state = bpy.context.scene.mechanical_cad_assembly
    check(snapshot() == expected, "Rebuild preserved exact canonical/source/report/dormant bytes")
    check(state_api.display_is_current(bpy.context), "Fresh accepted Assembly display authority")
    check(not state_api.report_is_current(bpy.context), "Saved report remains noncurrent")
    check(
        state.verification_status == "STALE" and "historical" in state.verification_message,
        "Historical check status is explicit",
    )
    check(
        state_api._RUNTIME[state_api._key(bpy.context.scene)]["report_binding"] is None,
        "No report authority binding restored",
    )
    response = state_api.current_display_response(bpy.context)
    check(
        response["report"]["base_pose"]["status"] == "evaluated",
        "Fresh full authoritative assembly pose",
    )
    check(
        response["result"]["canonical_assembly"]["part_sources"]
        == json.loads(expected["assembly"])["part_sources"],
        "Embedded source digests unchanged",
    )
    check(tuple(bpy.data.objects["Cube"].location) == (7, 8, 9), "Unrelated object preserved")
    check(
        bpy.data.objects["Foreign assembly cache"].get(assembly_display.OWNER_KEY)
        == "foreign-owner",
        "Unrelated Assembly cache preserved",
    )
    check(not document_state.part_is_current(bpy.context), "No competing Part rebuild")


if not os.environ.get("MCAD_ASSEMBLY_REOPEN"):
    data = json.loads((ROOT / "examples/reused_blocks.mcad-assembly.json").read_text())
    document_state._populate_document(bpy.context.scene, data["part_sources"][0]["document"])
    check(document_state.regenerate(bpy.context), "Seed accepted working Part")
    state_api.commit_candidate(bpy.context, data)
    state_api.check(bpy.context)
    bpy.data.objects["Cube"].location = (7, 8, 9)
    foreign = bpy.data.objects.new("Foreign assembly cache", None)
    foreign[assembly_display.OWNER_KEY] = "foreign-owner"
    bpy.context.scene.collection.objects.link(foreign)
    state = bpy.context.scene.mechanical_cad_assembly
    state.document_json = " \n" + state.document_json + "\n"
    part = bpy.context.scene.mechanical_cad
    part.repair_intent_json = "  unknown malformed dormant repair {\n"
    part.sketch_draft_json = "  unknown malformed dormant draft [\n"
    part.sketch_annotation_json = "  exact dormant annotation bytes\n"
    bpy.context.workspace[workspace.OWNER_KEY] = workspace.OWNER
    bpy.context.workspace[workspace.ROLE_KEY] = "ASSEMBLY"
    for name in ("assembly", "assembly_only"):
        if name == "assembly_only":
            part.document_json = ""
        expected = snapshot()
        (OUT / (name + ".expected.json")).write_text(json.dumps(expected))
        bpy.ops.wm.save_as_mainfile(filepath=str(OUT / (name + ".blend")))
        check(snapshot() == expected, name + " saved unchanged")
    print("ASSEMBLY_LOAD_WRITE_OK", len(checks), flush=True)
else:
    expected = open_file()
    check(
        rebuild.active(bpy.context) and rebuild._PENDING.assembly_snapshot is not None,
        "Only Assembly restoration ticket queued",
    )
    part_objects = {
        o.name: o.as_pointer()
        for o in bpy.context.scene.objects
        if o.get("mechanical_cad_owner") == bpy.context.scene.mechanical_cad.owner_id
    }
    bpy.context.scene["user_marker"] = "before"
    bpy.ops.ed.undo_push(message="Before user change")
    bpy.context.scene["user_marker"] = "after"
    bpy.ops.ed.undo_push(message="User change")
    drain()
    fresh(expected)
    check(
        all(
            bpy.data.objects[name].as_pointer() == pointer for name, pointer in part_objects.items()
        ),
        "Dormant Part cache not replaced",
    )
    check(
        bpy.ops.ed.undo() == {"FINISHED"} and bpy.context.scene["user_marker"] == "before",
        "Automatic Assembly cache publication adds no Undo step",
    )
    drain()
    check(
        bpy.ops.ed.redo() == {"FINISHED"} and bpy.context.scene["user_marker"] == "after",
        "Automatic cache publication preserves Redo",
    )
    drain()
    check(snapshot() == expected, "Undo/Redo preserves canonical/source/report/dormant bytes")
    check(bpy.ops.wm.revert_mainfile() == {"FINISHED"}, "Native Revert")
    drain()
    fresh(expected)

    expected_only = open_file("assembly_only")
    check(rebuild.active(bpy.context), "Assembly-only file schedules without a Part document")
    drain()
    fresh(expected_only)

    # Cancel before launch is terminal, including after the backend becomes ready later.
    expected = open_file()
    rebuild.cancel("Cancelled by you")
    drain()
    check(
        snapshot() == expected and not state_api.display_is_current(bpy.context),
        "Queued Cancel retains exact bytes without granting authority",
    )
    check(
        "Replay" in bpy.context.scene.mechanical_cad_assembly.error,
        "Manual Replay fallback remains visible",
    )

    expected = open_file()
    rebuild._tick()
    check(rebuild._PENDING.pending is not None, "Assembly native replay started")
    rebuild.cancel("Cancelled running rebuild")
    drain()
    check(
        snapshot() == expected and not state_api.display_is_current(bpy.context),
        "Running Cancel cannot publish",
    )

    expected = open_file()
    rebuild._tick()
    pending = rebuild._PENDING.pending
    deadline = time.monotonic() + 60
    while pending._job.state == "running" and time.monotonic() < deadline:
        pending._job.poll(backend_runtime.capture(bpy.context))
        time.sleep(0.01)
    check(pending._job.state == "ready", "Native response ready before publication")
    rebuild.cancel("Cancelled ready rebuild")
    drain()
    check(
        snapshot() == expected and not state_api.display_is_current(bpy.context),
        "Ready Cancel cannot resurrect display",
    )

    for mutation in ("draft", "repair", "report", "workspace", "interaction"):
        expected = open_file()
        rebuild._tick()
        if mutation == "draft":
            bpy.context.scene.mechanical_cad.sketch_draft_json += "new"
        elif mutation == "repair":
            bpy.context.scene.mechanical_cad.repair_intent_json += "new"
        elif mutation == "report":
            bpy.context.scene.mechanical_cad_assembly.report_json += "new"
        elif mutation == "workspace":
            bpy.context.workspace[workspace.ROLE_KEY] = "PART"
        else:
            state_api.begin_interaction()
        changed = snapshot()
        drain()
        check(
            snapshot() == changed and not state_api.display_is_current(bpy.context),
            mutation + " revokes running restoration",
        )

    with patch.object(
        document_state, "_capture_binding", side_effect=RuntimeError("Backend preparing")
    ):
        expected = open_file()
    check(not rebuild.active(bpy.context), "Not-ready backend creates no later retry")
    drain()
    check(
        snapshot() == expected and not state_api.display_is_current(bpy.context),
        "Readiness later does not silently launch",
    )

    expected = open_file()
    rebuild._tick()
    old = rebuild._PENDING
    bpy.ops.wm.open_mainfile(filepath=str(OUT / "assembly_only.blend"))
    check(
        old.binding is None and old.assembly_snapshot is None,
        "New load drops prior RNA before cleanup",
    )
    drain()
    fresh(expected_only)
    print("ASSEMBLY_LOAD_REOPEN_OK", len(checks), flush=True)
