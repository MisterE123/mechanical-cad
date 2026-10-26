"""Native fixed face insertion owner; deterministic ray ports, not GUI gestures."""

import copy
import json
import math
import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import bpy

ROOT = Path(os.environ["MCAD_ROOT"])
sys.path.insert(0, str(ROOT / "blender_addon"))
sys.path.insert(0, str(ROOT / "tests"))
from unittest.mock import patch  # noqa: E402

from blender_async_helpers import replay_assembly  # noqa: E402
from mathutils import Vector  # noqa: E402
from mechanical_cad_blender import (  # noqa: E402
    assembly_display,
    assembly_pending,
    assembly_state,
    execution_lease,
    register,  # noqa: E402
)
from mechanical_cad_blender import assembly_insert_mate_preview as mate_preview  # noqa: E402
from mechanical_cad_blender import assembly_source_update_preview as source_preview  # noqa: E402
from mechanical_cad_blender.assembly_insert_mate_preview import InsertMateSession  # noqa: E402
from mechanical_cad_blender.assembly_insert_preview_draft import InsertPreviewDraft  # noqa: E402

register()
checks = []
OUT = Path(
    os.environ.get(
        "MCAD_INSERT_MATE_OUT",
        str(ROOT / "evidence/assembly-insert-face-20261026/native-owner"),
    )
)
OUT.mkdir(exist_ok=True)
MODE = os.environ.get("MCAD_INSERT_MATE_MODE", "create")


def check(value, label):
    assert value, label
    checks.append(label)
    print("INSERT_MATE_CHECK", label, flush=True)


def call(op, **kwargs):
    check(op(**kwargs) == {"FINISHED"}, op.idname() if hasattr(op, "idname") else op.__name__)


def data():
    return assembly_state.read_assembly(bpy.context.scene.mechanical_cad_assembly)


@contextmanager
def viewport():
    window = bpy.context.window
    area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
    region = next(r for r in area.regions if r.type == "WINDOW")
    with bpy.context.temp_override(window=window, area=area, region=region):
        yield bpy.context


def accepted():
    state = bpy.context.scene.mechanical_cad_assembly
    bpy.context.view_layer.update()
    return (
        tuple(getattr(state, field) for field in assembly_state._STATE_FIELDS),
        bpy.context.scene.mechanical_cad.document_json,
        [
            (
                o.as_pointer(),
                o.data.as_pointer() if o.data is not None else 0,
                list(o.location),
                list(o.rotation_quaternion),
            )
            for o in assembly_display.owned_objects(bpy.context.scene, state.owner_id)
        ],
    )


def finish(owner, context):
    deadline = time.monotonic() + 180
    while not owner.ready() and not owner.error and time.monotonic() < deadline:
        owner.tick(context)
        time.sleep(0.02)
    check(owner.ready(), "Exact insertion preview ready: " + owner.error)


def reap():
    deadline = time.monotonic() + 20
    while execution_lease.is_busy() and time.monotonic() < deadline:
        assembly_pending.reap(bpy.context)
        time.sleep(0.02)
    check(not execution_lease.is_busy(), "Cancelled native lease reaped")


def watch(owner):
    show = owner._show_response

    def capture(response):
        owner.test_response = copy.deepcopy(response)
        show(response)

    owner._show_response = capture
    return owner


def seed_ready(owner, context):
    deadline = time.monotonic() + 180
    while owner.pending is not None and not owner.error and time.monotonic() < deadline:
        owner.tick(context)
        time.sleep(0.02)
    check(owner.phase == "picking" and owner.projection is not None and not owner.error,
          "Verified insertion seed reaches picking: " + owner.error)


def pick_ray(owner, context, origin, direction):
    # Test-only deterministic viewport ray ports. Real owner.pick handles target
    # binding, semantic projection, atomic mate adoption and pending admission.
    with patch.object(mate_preview.view3d_utils, "region_2d_to_origin_3d",
                      return_value=Vector([v * owner.scale for v in origin])), \
         patch.object(mate_preview.view3d_utils, "region_2d_to_vector_3d",
                      return_value=Vector(direction)):
        owner.pick(context, (100, 100))


def prepare(context, insertion):
    baseline = accepted()
    owner = watch(InsertMateSession(context, insertion)).start(context)
    check(not owner.ready() and accepted() == baseline, "Pending seed cannot publish or authorize Apply")
    seed_ready(owner, context)
    check(not owner.ready() and owner.expectation is None, "Seed picking is not final Apply authority")
    check(not owner.apply(context) and accepted() == baseline, "Apply during picking is refused without mutation")
    owner.select_end("parent")  # Explicit retry resets the refusal notice.
    seed_digest = owner.mate.seed_fingerprint
    try:
        owner.projection.pick(owner.parent_id, [5, 5, 20], [0, 0, -1])
    except Exception as exc:
        check("overlap" in str(exc), "Default coincident root and new-child picking refuses")
    else:
        raise AssertionError("Coincident surfaces selected silently")
    hit = owner.projection.pick(owner.parent_id, [5, 5, 20], [0, 0, -1], target_only=True)
    check(hit["face_id"] == "pad/face/cap.end", "Explicit highlighted-only resolves real stable top face")
    owner.target_only = True
    pick_ray(owner, context, [5, 5, 20], [0, 0, -1])
    check(owner.faces["parent"] == "pad/face/cap.end" and owner.pick_end == "child",
          "Real owner pick adopts parent and advances to new child")
    check(not owner.target_only, "Changing target requires renewed explicit isolation")
    owner.target_only = True
    pick_ray(owner, context, [5, 5, -20], [0, 0, 1])
    check(owner.phase == "final_pending" and owner.pending is not None and not owner.ready(),
          "Second real owner pick schedules exact final mate replay")
    check(accepted() == baseline, "Face selection and pending final replay preserve accepted state")
    finish(owner, context)
    check(owner.phase == "final" and owner.expectation != seed_digest,
          "Final complete geometry digest is distinct from seed authority")
    response = owner.test_response
    poses = response["report"]["base_pose"]["transforms"]
    check(set(poses) == {"root", "a", "b", insertion.instance_id}, "Final replay has full four-instance pose")
    check(poses[insertion.instance_id]["xyz_mm"] == [0, 0, 10], "Face-mated new child lies atop parent at10mm")
    check(math.isclose(response["result"]["parts"][0]["geometry_check"]["brep"]["volume"],1000,abs_tol=1e-8),
          "Real complete source geometry retains exact volume1000")
    check(accepted() == baseline, "Ready final ghost never publishes accepted state")
    return owner


if MODE == "reopen":
    call(bpy.ops.wm.open_mainfile, filepath=str(OUT / "face-insertion.blend"))
    check(bpy.context.scene.mechanical_cad_assembly.document_json == (OUT / "accepted.json").read_text(),
          "Fresh process preserves exact face insertion graph")
    check(source_preview.active() is None and not assembly_state.display_is_current(bpy.context),
          "No saved preview authority; explicit replay required")
    call(replay_assembly)
    response = assembly_state.current_display_response(bpy.context)
    expected = json.loads((OUT / "applied-response.json").read_text())
    check(response["result"]["canonical_assembly"] == expected["result"]["canonical_assembly"],
          "Reopened canonical IDs and support references are exact")
    check(response["report"]["base_pose"]["transforms"] == expected["report"]["base_pose"]["transforms"],
          "Reopened complete geometry poses are exact")
    check(math.isclose(response["result"]["parts"][0]["geometry_check"]["brep"]["volume"],1000,abs_tol=1e-8),
          "Reopened source volume1000")
    marker = "INSERT_MATE_REOPEN_OK"
else:
    call(bpy.ops.mcad.assembly_load, filepath=str(ROOT / "examples/reused_blocks.mcad-assembly.json"))
    original = copy.deepcopy(data())
    original_poses = assembly_state.current_display_response(bpy.context)["report"]["base_pose"]["transforms"]
    insertion = InsertPreviewDraft(original, "block", parent="root", parent_frame="origin",
                                  child_frame="origin", kind="fixed", name="Face-mated insertion")
    with viewport() as context:
        baseline = accepted()
        owner = prepare(context, insertion)
        owner.cancel()
        reap()
        check(accepted() == baseline and source_preview.active() is None,
              "Cancel final insertion leaves no accepted orphan or display remnant")
        owner = prepare(context, insertion)
        final_candidate = copy.deepcopy(owner.candidate)
        with patch.object(assembly_state, "commit_candidate", wraps=assembly_state.commit_candidate) as commit:
            check(owner.apply(context), "Explicit final fixed insertion Apply succeeds: " + owner.error)
            check(not owner.apply(context) and commit.call_count == 1, "Final mate applies once")
            check(commit.call_args.kwargs["expected_json"] == baseline[0][0]
                  if assembly_state._STATE_FIELDS[0] == "document_json"
                  else commit.call_args.kwargs["expected_json"] == owner.snapshot["fields"]["document_json"],
                  "Apply bound to ORIGINAL accepted graph, not insertion seed")
        check(data() == final_candidate, "Only final face-mated child and incoming joint publish atomically")
        response = assembly_state.current_display_response(context)
        poses = response["report"]["base_pose"]["transforms"]
        check(all(poses[key] == value for key, value in original_poses.items()), "All original reused poses unchanged")
        check(data()["joints"][:-1] == original["joints"] and data()["part_sources"] == original["part_sources"],
              "All existing joints and source revisions unchanged")
        (OUT / "applied-response.json").write_text(json.dumps(response,indent=2))
    (OUT / "accepted.json").write_text(bpy.context.scene.mechanical_cad_assembly.document_json)
    call(bpy.ops.wm.save_as_mainfile, filepath=str(OUT / "face-insertion.blend"))
    marker = "INSERT_MATE_OWNER_OK"
check({j["id"]:j["coordinate"] for j in data()["joints"] if j["kind"] == "slider"}
      == {"slide_a":100,"slide_b":100}, "No existing slider coordinate changed")
check(not any(k == "OCP" or k.startswith("OCP.") for k in sys.modules), "No OCP in Blender")
(OUT / (MODE + "-checks.json")).write_text(json.dumps(checks,indent=2))
print(marker,len(checks),flush=True)
