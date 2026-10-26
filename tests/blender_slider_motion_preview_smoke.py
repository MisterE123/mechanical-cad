"""Native full-assembly slider ghosts; no GUI qualification claimed."""

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
from blender_async_helpers import replay_assembly  # noqa: E402
from mechanical_cad_blender import (  # noqa: E402
    assembly_display,
    assembly_pending,
    assembly_state,
    execution_lease,
    register,  # noqa: E402
)
from mechanical_cad_blender import assembly_joint_viewport as visual  # noqa: E402

register()
checks = []
OUT = Path(os.environ.get("MCAD_MOTION_OUT", str(ROOT / "evidence/slider-motion-20261025/native")))
OUT.mkdir(exist_ok=True)
MODE = os.environ.get("MCAD_MOTION_MODE", "create")


def check(value, label):
    assert value, label
    checks.append(label)
    print("SLIDER_MOTION_CHECK", label, flush=True)


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
    deadline = time.monotonic() + 60
    while not owner.ready() and not owner.error and time.monotonic() < deadline:
        owner.tick(context)
        time.sleep(0.02)
    check(owner.ready(), "Exact full motion preview ready: " + owner.error)


def reap():
    deadline = time.monotonic() + 20
    while execution_lease.is_busy() and time.monotonic() < deadline:
        assembly_pending.reap(bpy.context)
        time.sleep(0.02)
    check(not execution_lease.is_busy(), "Cancelled native lease reaped")


def exact_report(response):
    check(set(response["report"]["base_pose"]["transforms"]) == {"root", "a", "b"}, "Full report includes all three instances")
    parts = response["result"]["parts"]
    check(len(parts) == 1, "Reused source has one exact part payload")
    check(math.isclose(parts[0]["geometry_check"]["brep"]["volume"], 1000, abs_tol=1e-8), "OCP block volume remains 1000 cubic mm")


def watch(owner):
    show = owner._show_response

    def capture(response):
        owner.test_response = copy.deepcopy(response)
        show(response)

    owner._show_response = capture
    return owner


if MODE == "revolute":
    call(bpy.ops.mcad.assembly_load, filepath=str(ROOT / "examples/reused_blocks.mcad-assembly.json"))
    canonical = data()
    joint = next(j for j in canonical["joints"] if j["id"] == "slide_a")
    joint.update(kind="revolute", coordinate=0.1, limits=[-1, 1])
    assembly_state.commit_candidate(bpy.context, canonical,
                                    expected_json=bpy.context.scene.mechanical_cad_assembly.document_json)
    baseline = accepted()
    with viewport() as context:
        owner = watch(visual.MotionViewportSession(context, "slide_a").start())
        owner.set_distance(context, 30)
        finish(owner, context)
        exact_report(owner.test_response)
        check(math.isclose(owner._ready_pose["effective_coordinates"]["slide_a"], math.radians(30), abs_tol=1e-12), "Revolute30 degrees still stores canonical radians")
        check(math.isclose(owner._ready_pose["transforms"]["a"]["wxyz"][3], math.sin(math.radians(15)), abs_tol=1e-12), "Revolute exact rotation remains unchanged")
        owner.cancel()
        check(accepted() == baseline, "Revolute preview Cancel preserves accepted fields and objects")
    marker = "REVOLUTE_MOTION_REGRESSION_OK"
elif MODE == "reopen":
    call(bpy.ops.wm.open_mainfile, filepath=str(OUT / "motion.blend"))
    check(bpy.context.scene.mechanical_cad_assembly.document_json == (OUT / "accepted.json").read_text(), "Separate process preserves exact accepted slider document")
    check(visual.active() is None, "No transient owner restored")
    check(not assembly_state.display_is_current(bpy.context), "Reopen requires explicit Replay")
    call(replay_assembly)
    response = assembly_state.current_display_response(bpy.context)
    exact_report(response)
    check(response["report"]["base_pose"]["effective_coordinates"]["slide_a"] == 125.5, "Reopened slider is 125.5 mm")
    check(response["report"]["base_pose"]["transforms"]["a"]["xyz_mm"] == [0, 0, 125.5], "Reopened exact child displacement")
    baseline = accepted()
    with viewport() as context:
        owner = watch(visual.MotionViewportSession(context, "slide_a").start())
        owner.set_distance(context, 130)
        finish(owner, context)
        exact_report(owner.test_response)
        owner.cancel()
        check(accepted() == baseline, "Reopened preview Cancel leaves accepted document/report/display intact")
    marker = "SLIDER_MOTION_REOPEN_OK"
else:
    call(bpy.ops.mcad.assembly_load, filepath=str(ROOT / "examples/reused_blocks.mcad-assembly.json"))
    if not assembly_state.display_is_current(bpy.context):
        call(replay_assembly)
    baseline = accepted()
    initial = assembly_state.current_display_response(bpy.context)
    exact_report(initial)
    initial_pose = initial["report"]["base_pose"]
    check(initial_pose["effective_coordinates"]["slide_a"] == 100, "Initial slider100 mm")
    with viewport() as context:
        owner = watch(visual.MotionViewportSession(context, "slide_a").start())
        owner.set_distance(context, 125.5)
        finish(owner, context)
        exact_report(owner.test_response)
        (OUT / "preview-report.json").write_text(json.dumps(owner.test_response, indent=2))
        pose = owner._ready_pose
        check(pose["effective_coordinates"]["slide_a"] == 125.5, "Slider input stays canonical125.5 mm, not radians")
        delta = [a - b for a, b in zip(pose["transforms"]["a"]["xyz_mm"], initial_pose["transforms"]["a"]["xyz_mm"], strict=True)]
        check(delta == [0, 0, 25.5], "Exact childa displacement25.5 mm")
        check(pose["transforms"]["a"]["wxyz"] == initial_pose["transforms"]["a"]["wxyz"], "Slider does not rotate child")
        for instance in ("root", "b"):
            check(pose["transforms"][instance] == initial_pose["transforms"][instance], "Unrelated transform unchanged: " + instance)
        check(bool(owner.ghost_positions) and len(owner.preview_transforms) == 3, "All-instance ghost available")
        check(accepted() == baseline, "Preview leaves canonical/report/object transforms untouched")
        owner.cancel()
        check(accepted() == baseline, "Cancel leaves accepted state and object identities untouched")
        reap()
    with viewport() as context:
        owner = watch(visual.MotionViewportSession(context, "slide_a").start())
        owner.set_distance(context, 125.5)
        finish(owner, context)
        try:
            owner.set_distance(context, 301)
        except ValueError as error:
            check("limits" in str(error), "301 mm exceeds authored300 mm limit")
        else:
            raise AssertionError("Out-of-limit slider accepted")
        check(not owner.ready() and not owner.ghost_positions, "Refusal revokes ghost and Apply permission")
        check(not owner.apply(context), "Refused slider cannot Apply")
        owner.cancel()
        check(accepted() == baseline, "Limit refusal preserves canonical/report/object transforms")
        reap()
    with viewport() as context:
        owner = watch(visual.MotionViewportSession(context, "slide_a").start())
        owner.set_distance(context, 125.5)
        finish(owner, context)
        expected_pose = copy.deepcopy(owner._ready_pose)
        check(owner.apply(context), "Explicit ready slider Apply succeeds")
        response = assembly_state.current_display_response(context)
        exact_report(response)
        check(response["report"]["base_pose"] == expected_pose, "Apply exactly matches ready full-assembly pose")
        check(bpy.context.scene.mechanical_cad_assembly.verification_status == "UNCHECKED", "Motion Apply does not imply contact verification")
        (OUT / "applied-report.json").write_text(json.dumps(response, indent=2))
    expected = json.loads(baseline[0][assembly_state._STATE_FIELDS.index("document_json")])
    next(j for j in expected["joints"] if j["id"] == "slide_a")["coordinate"] = 125.5
    check(data() == expected, "Apply changes only chosen coordinate, preserving links frames limits")
    (OUT / "accepted.json").write_text(bpy.context.scene.mechanical_cad_assembly.document_json)
    call(bpy.ops.wm.save_as_mainfile, filepath=str(OUT / "motion.blend"))
    check(visual.active() is None, "Save has no live motion owner")
    marker = "SLIDER_MOTION_PREVIEW_OK"
check(not any(key == "OCP" or key.startswith("OCP.") for key in sys.modules), "No OCP in Blender process")
(OUT / (MODE + "-checks.json")).write_text(json.dumps(checks, indent=2))
print(marker, len(checks), flush=True)
