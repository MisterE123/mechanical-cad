"""Native full-assembly driver ghosts; no GUI qualification claimed."""

import copy
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
OUT = Path(os.environ.get("MCAD_MOTION_OUT", "/tmp/mcad-geared-motion"))
OUT.mkdir(exist_ok=True)
MODE = os.environ.get("MCAD_MOTION_MODE", "create")


def check(value, label):
    assert value, label
    checks.append(label)
    print("GEARED_MOTION_CHECK", label, flush=True)


def call(op, **kwargs):
    check(op(**kwargs) == {"FINISHED"}, op.idname())


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


if MODE == "reopen":
    call(bpy.ops.wm.open_mainfile, filepath=str(OUT / "motion.blend"))
    expected_json = (OUT / "accepted.json").read_text()
    check(
        bpy.context.scene.mechanical_cad_assembly.document_json == expected_json,
        "Fresh process preserves exact accepted JSON",
    )
    check(visual.active() is None, "Fresh process has no restored transient motion owner")
    check(
        not assembly_state.display_is_current(bpy.context),
        "Fresh process requires explicit assembly Replay",
    )
    call(replay_assembly)
    before = accepted()
    with viewport() as context:
        owner = visual.MotionViewportSession(context, data()["joints"][0]["id"]).start()
        owner.set_distance(context, 25)
        finish(owner, context)
        owner.cancel()
        check(
            accepted() == before,
            "Fresh process preview/Cancel preserves accepted fields and objects",
        )
    print("GEARED_MOTION_REOPEN_OK", len(checks), flush=True)
else:
    call(bpy.ops.mcad.new_document, name="Motion fixture")
    call(bpy.ops.mcad.add_rectangle, width=12, height=8)
    call(
        bpy.ops.mcad.add_extrude, profile=bpy.context.scene.mechanical_cad.active_feature, length=4
    )
    call(bpy.ops.mcad.assembly_new, name="Cross branch motion", grounded=True)
    root, part = data()["grounded_instance"], data()["parts"][0]["id"]
    for index, angle in enumerate((10, 40, 15)):
        call(
            bpy.ops.mcad.assembly_frame,
            part_id=part,
            name=f"Axis {index + 1}",
            xyz=f"{30 * (index + 1)}, 0, 0",
            associative=True,
            support_face=bpy.context.scene.mechanical_cad.active_feature + "/face/cap.end",
        )
        frame = data()["parts"][0]["mate_frames"][-1]["id"]
        call(
            bpy.ops.mcad.assembly_insert,
            part_id=part,
            parent=root,
            parent_frame=frame,
            child_frame="origin",
            kind="revolute",
            name=f"Wheel {index + 1}",
            coordinate=str(angle),
        )
    joints = data()["joints"]
    call(
        bpy.ops.mcad.assembly_gear,
        name="Opposed 2:1",
        driver_joint=joints[0]["id"],
        driven_joint=joints[1]["id"],
        ratio="-2",
        keep_alignment=True,
    )
    call(
        bpy.ops.mcad.assembly_gear,
        name="Half speed",
        driver_joint=joints[1]["id"],
        driven_joint=joints[2]["id"],
        ratio="0.5",
        offset="-5",
        keep_alignment=False,
    )
    call(
        bpy.ops.mcad.assembly_joint,
        joint_id=joints[1]["id"],
        use_limits=True,
        lower="-90",
        upper="90",
    )
    call(bpy.ops.mcad.assembly_check)
    baseline = accepted()

    with viewport() as context:
        try:
            visual.MotionViewportSession(context, joints[1]["id"])
        except ValueError as exc:
            check(
                "read-only" in str(exc) and joints[0]["name"] in str(exc),
                "Controlled joint names independent driver",
            )
        else:
            raise AssertionError("Follower was editable")
        owner = visual.MotionViewportSession(context, joints[0]["id"]).start()
        check(
            not owner.ready() and not owner.ghost_positions, "Pending does not present an old ghost"
        )
        # Coalesce all changes before debounce; only the last is submitted.
        for angle in (11, 12, 20):
            owner.set_distance(context, angle)
        finish(owner, context)
        check(
            accepted() == baseline,
            "Preview preserves every accepted field, object and working Part",
        )
        expected = copy.deepcopy(owner._ready_pose)
        check(
            len(owner.preview_transforms) == 4 and bool(owner.ghost_positions),
            "Whole assembly ghost includes every branch",
        )
        for joint, angle in zip(joints, (20, 20, 5), strict=True):
            check(
                math.isclose(
                    expected["effective_coordinates"][joint["id"]],
                    math.radians(angle),
                    abs_tol=1e-12,
                ),
                "Derived cross-branch angle " + joint["name"],
            )
            check(
                math.isclose(
                    expected["transforms"][joint["child"]]["wxyz"][3],
                    math.sin(math.radians(angle) / 2),
                    abs_tol=1e-12,
                ),
                "Exact cross-branch transform " + joint["name"],
            )
        owner.cancel()
        check(
            accepted() == baseline,
            "Cancel preserves accepted canonical and report bytes and objects",
        )
        reap()

    with viewport() as context:
        owner = visual.MotionViewportSession(context, joints[0]["id"]).start()
        owner.set_distance(context, 20)
        finish(owner, context)
        expected = copy.deepcopy(owner._ready_pose)
        check(owner.apply(context), "Explicit exact-ready Apply succeeds: " + owner.error)
        check(
            assembly_state.current_display_response(context)["report"]["base_pose"] == expected,
            "Apply has no pose jump",
        )
        check(
            bpy.context.scene.mechanical_cad_assembly.verification_status == "UNCHECKED",
            "Apply does not claim contact verification",
        )

    baseline = accepted()
    with viewport() as context:
        owner = visual.MotionViewportSession(context, joints[0]["id"]).start()
        owner.set_distance(context, 21)
        owner._deadline = 0
        owner.tick(context)
        check(owner.pending is not None, "Native motion is running")
        owner.set_distance(context, 22)
        check(
            not owner.ghost_positions and not owner.ready(),
            "Superseded running result loses display/Apply permission",
        )
        finish(owner, context)
        check(
            math.isclose(
                owner._ready_pose["effective_coordinates"][joints[0]["id"]], math.radians(22)
            ),
            "Only latest running change wins",
        )
        try:
            owner.set_distance(context, 100)
        except ValueError as exc:
            check("limits" in str(exc), "Derived follower limit rejects entire preview")
        else:
            raise AssertionError("Derived limit accepted")
        check(
            not owner.ghost_positions and not owner.ready(),
            "Rejected angle clears old ghost and Apply",
        )
        check(accepted() == baseline, "Rejected preview preserves accepted report and objects")
        owner.cancel()
        reap()

    with viewport() as context:
        owner = visual.MotionViewportSession(context, joints[0]["id"]).start()
        owner._deadline = 0
        owner.tick(context)
        owner.cancel()
        reap()
        check(accepted() == baseline, "Cancel running job never publishes report or geometry")

    with viewport() as context:
        owner = visual.MotionViewportSession(context, joints[0]["id"]).start()
        owner._deadline = 0
        owner.tick(context)
        pending = owner.pending
        deadline = time.monotonic() + 60
        while pending._job.state == "running" and time.monotonic() < deadline:
            pending._job.poll(
                assembly_state._current_selection(context, pending._transaction["snapshot"])
            )
            time.sleep(0.02)
        check(pending._job.state == "ready", "Native response ready but not displayed")
        owner.cancel()
        reap()
        check(
            not owner.ghost_positions and accepted() == baseline,
            "Cancel rejects a ready unpublished native response",
        )

    # Saving transient motion never persists it. Load while a prior native job is
    # running must retire its UI owner and cleanup lease before a new scene can use it.
    expected_json = bpy.context.scene.mechanical_cad_assembly.document_json
    (OUT / "accepted.json").write_text(expected_json)
    with viewport() as context:
        owner = visual.MotionViewportSession(context, joints[0]["id"]).start()
        owner.set_distance(context, 23)
        call(bpy.ops.wm.save_as_mainfile, filepath=str(OUT / "motion.blend"))
        check(
            bpy.context.scene.mechanical_cad_assembly.document_json == expected_json,
            "Save while queued persists accepted pose only",
        )
        owner._deadline = 0
        owner.tick(context)
        check(owner.pending is not None, "Prior native motion running before load")
    # Do not retain a temp_override across native file load.
    call(bpy.ops.wm.open_mainfile, filepath=str(OUT / "motion.blend"))
    reap()
    check(
        not owner.alive and visual.active() is None,
        "Load retires motion owner before scene replacement",
    )
    check(
        bpy.context.scene.mechanical_cad_assembly.document_json == expected_json,
        "Load never applies transient driver angle",
    )
    check(
        not assembly_state.display_is_current(bpy.context),
        "Assembly load retains explicit Replay guard",
    )
    call(replay_assembly)
    with viewport() as context:
        owner = visual.MotionViewportSession(context, joints[0]["id"]).start()
        owner.set_distance(context, 24)
        finish(owner, context)
        owner.cancel()
        check(
            bpy.context.scene.mechanical_cad_assembly.document_json == expected_json,
            "New motion preview after load remains disposable",
        )

    check(
        not any(key == "OCP" or key.startswith("OCP.") for key in sys.modules),
        "No native kernel imported into Blender",
    )
    print("GEARED_MOTION_PREVIEW_OK", len(checks), flush=True)
