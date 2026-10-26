"""Registered visual-joint owner journey with real guarded native publication.

Run native Blender with --background --factory-startup --python-exit-code 1,
MCAD_ROOT, MCAD_PYTHON, a fresh MCAD_VISUAL_JOINT_DIRECTORY and
MCAD_VISUAL_JOINT_PHASE=save/reopen in two serial processes. The owner is driven
through its adapter methods in a real VIEW_3D context; this is not a mouse/GUI
usability claim. No native evidence is fabricated or imported into Blender.
Explicit Undo pushes verify history restoration, not modal Undo-step creation.

The emitted files also support the existing, independent exact STEP reader:
tests/integration/test_assembly_step_workflow.py --read-owner DIRECTORY
"""

import hashlib
import json
import os
import signal
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

sys.dont_write_bytecode = True
import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

ROOT = Path(os.environ["MCAD_ROOT"]).resolve()
DIRECTORY = Path(os.environ["MCAD_VISUAL_JOINT_DIRECTORY"]).resolve()
PHASE = os.environ.get("MCAD_VISUAL_JOINT_PHASE", "save")
sys.path.insert(0, str(ROOT / "blender_addon"))
sys.path.insert(0, str(ROOT / "tests"))
import mechanical_cad_blender as addon  # noqa: E402
from blender_async_helpers import replay_assembly  # noqa: E402
from mechanical_cad_blender import (  # noqa: E402
    assembly_display,
    assembly_state,
    execution_lease,
    sidecar_job,
)
from mechanical_cad_blender import (  # noqa: E402
    assembly_joint_viewport as visual,
)

checks, jobs = [], []


def check(value, label):
    assert value, label
    checks.append(label)
    print("VISUAL_JOINT_CHECK", label, flush=True)


def persist(name, value):
    with (DIRECTORY / name).open("x") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def state():
    return bpy.context.scene.mechanical_cad_assembly


def data():
    return assembly_state.read_assembly(state())


def by_id(rows, identity):
    return next(row for row in rows if row["id"] == identity)


def call(operation, **kwargs):
    check(operation(**kwargs) == {"FINISHED"}, operation.idname() + " completes")
    check(not execution_lease.is_busy(), "Native lease collected")


@contextmanager
def viewport():
    window = bpy.context.window
    area = next(area for area in window.screen.areas if area.type == "VIEW_3D")
    region = next(region for region in area.regions if region.type == "WINDOW")
    with bpy.context.temp_override(window=window, area=area, region=region):
        yield bpy.context


def new_session(context, *, joint_id=""):
    session = visual.JointViewportSession(context, joint_id=joint_id)
    session.start()
    check(visual.active(context) is session, "Single registered visual owner is active")
    return session


def instance_matrices():
    # New display objects have freshly assigned RNA transforms. matrix_world is
    # evaluated data and can still be identity until the view layer updates.
    bpy.context.view_layer.update()
    return {
        obj[assembly_display.INSTANCE_KEY]: [list(row) for row in obj.matrix_world]
        for obj in assembly_display.owned_objects(bpy.context.scene, state().owner_id)
        if obj.get(assembly_display.ROLE_KEY) == "instance"
    }


def display_observation(identifier):
    obj = next(
        obj
        for obj in assembly_display.owned_objects(bpy.context.scene, state().owner_id)
        if obj.get(assembly_display.ROLE_KEY) == "instance"
        and obj.get(assembly_display.INSTANCE_KEY) == identifier
    )
    return {
        "location_blender": list(obj.location),
        "rotation_wxyz": list(obj.rotation_quaternion),
        "mesh_origin_mm": list(obj[assembly_display.ORIGIN_KEY]),
        "matrix_world": [list(row) for row in obj.matrix_world],
    }


def display_cad_origin_mm(observation):
    """Undo mesh recentering; matrix translation alone is not the CAD origin."""
    scale = 0.001 / bpy.context.scene.unit_settings.scale_length
    matrix, origin = observation["matrix_world"], observation["mesh_origin_mm"]
    return [
        matrix[axis][3] / scale - sum(matrix[axis][column] * origin[column] for column in range(3))
        for axis in range(3)
    ]


def current_check():
    call(bpy.ops.mcad.assembly_check)
    response = json.loads(state().report_json)
    check(assembly_state.report_is_current(bpy.context), "Current guarded pose report")
    check(response["report"]["passed"], "Both sectors meet saved base-clearance requirements")


def same_position(actual, expected):
    return all(abs(a - b) < 1e-9 for a, b in zip(actual, expected, strict=True))


def picker_journey():
    """Actual local-view visibility and Object.ray_cast with a fixed ray adapter."""
    with viewport() as context:
        space = context.area.spaces.active
        objects = list(context.view_layer.objects)
        cube = bpy.data.objects["Cube"]
        owned = assembly_display.owned_objects(context.scene, state().owner_id)
        base = next(
            obj
            for obj in owned
            if obj.get(assembly_display.ROLE_KEY) == "instance"
            and obj.get(assembly_display.INSTANCE_KEY) == "base"
        )
        selected = {obj.name: obj.select_get() for obj in objects}
        active = context.view_layer.objects.active
        previous_local = space.local_view is not None
        membership = (
            {obj.name: obj.local_view_get(space) for obj in objects} if previous_local else {}
        )
        canonical, report, before_jobs = state().document_json, state().report_json, len(jobs)
        flags = {
            obj.name: (obj.hide_viewport, obj.hide_get(), list(obj.location)) for obj in objects
        }
        session = None

        def snapshot():
            return {
                "canonical": state().document_json,
                "active": getattr(context.view_layer.objects.active, "name", None),
                "objects": {
                    obj.name: {
                        "selected": obj.select_get(),
                        "local": obj.local_view_get(space),
                        "visible": obj.visible_get(view_layer=context.view_layer, viewport=space),
                        "hidden": obj.hide_get(),
                    }
                    for obj in objects
                },
            }

        try:
            for obj in objects:
                obj.select_set(obj is base)
            context.view_layer.objects.active = base
            if not previous_local:
                call(bpy.ops.view3d.localview, frame_selected=False)
            check(space.local_view is not None, "Native picker fixture owns a real local view")
            for obj in owned:
                obj.local_view_set(space, True)
            cube.local_view_set(space, False)
            context.view_layer.update()
            session = new_session(context)
            # Only screen-to-ray conversion is adapted. Native visibility,
            # evaluated object transforms and each Object.ray_cast remain real.
            with (
                patch.object(
                    visual.view3d_utils,
                    "region_2d_to_origin_3d",
                    return_value=Vector((0.02, 0.015, 2.0)),
                ),
                patch.object(
                    visual.view3d_utils,
                    "region_2d_to_vector_3d",
                    return_value=Vector((0.0, 0.0, -1.0)),
                ),
            ):
                hidden = snapshot()
                check(
                    hidden["objects"][base.name]["visible"]
                    and not hidden["objects"][cube.name]["visible"],
                    "Local view shows the owned base while excluding the nearer foreign Cube",
                )
                check(
                    session.pick_instance(context, (100, 100)) == "base",
                    "Actual object ray casts select the visible owned base through a local-hidden Cube",
                )
                check(
                    snapshot() == hidden,
                    "Successful pick changes no selection, visibility or model",
                )
                cube.local_view_set(space, True)
                context.view_layer.update()
                visible = snapshot()
                check(
                    visible["objects"][cube.name]["visible"], "Foreign Cube is now locally visible"
                )
                try:
                    session.pick_instance(context, (100, 100))
                except visual.BridgeError as exc:
                    check(
                        "not an instance" in str(exc),
                        "Actual nearer foreign Cube blocks the owned instance pick",
                    )
                else:
                    raise AssertionError("Visible foreign occluder was ignored")
                check(
                    snapshot() == visible, "Rejected pick changes no selection, visibility or model"
                )
                persist(
                    "picker-result.json",
                    {
                        "real_object_ray_cast": True,
                        "screen_to_ray_adapter": True,
                        "manual_gui": False,
                        "hidden_foreign_pick": "base",
                        "visible_foreign_pick": "rejected",
                    },
                )
        finally:
            if session is not None:
                session.cancel("Picker regression complete")
            if previous_local:
                for obj in objects:
                    obj.local_view_set(space, membership[obj.name])
            elif space.local_view is not None:
                call(bpy.ops.view3d.localview, frame_selected=False)
            for obj in objects:
                obj.select_set(selected[obj.name])
            context.view_layer.objects.active = active
            context.view_layer.update()
        check(
            flags
            == {
                obj.name: (obj.hide_viewport, obj.hide_get(), list(obj.location)) for obj in objects
            }
            and cube["keep"] == "unrelated user object",
            "Picker fixture preserves every unrelated object transform and hide flag",
        )
        check(
            state().document_json == canonical
            and state().report_json == report
            and len(jobs) == before_jobs,
            "Native picker path performs no CAD publication, verification or sidecar launch",
        )


def save():
    DIRECTORY.mkdir()
    bpy.data.objects["Cube"]["keep"] = "unrelated user object"
    call(
        bpy.ops.mcad.assembly_load,
        filepath=str(ROOT / "examples/box_sector/assembly.mcad-assembly.json"),
    )
    current_check()
    picker_journey()
    original, canonical = data(), state().document_json
    working_part = bpy.context.scene.mechanical_cad.document_json
    original_pose = assembly_state.current_display_response(bpy.context)["report"]["base_pose"]
    sibling_before_raw = display_observation("sector_b")
    matrices = instance_matrices()
    sibling_before = display_observation("sector_b")
    before_jobs = len(jobs)
    with viewport() as context:
        session = new_session(context)
        session.choose_instance(context, "base")
        session.choose_instance(context, "sector_a")
        check(session.draft.joint_id == "slide_a", "Selected child retains its incoming joint ID")
        session.clear_motion(context)
        session.set_kind(context, "fixed")
        check(
            same_position(session.preview_transforms["sector_a"]["xyz_mm"], [10, 10, 10]),
            "Fixed preview aligns the literal connectors",
        )
        session.set_kind(context, "slider")
        session.set_distance(context, 12.0)
        session.translate_connector(context, "parent", "X", 2.0)
        session.translate_connector(context, "child", "X", 1.0)
        session.refresh_preview()
        check(
            same_position(session.preview_transforms["sector_a"]["xyz_mm"], [11, 10, 22]),
            "Slider preview uses parent +Z and both edited literal connectors",
        )
        check(
            same_position(session.preview_transforms["sector_b"]["xyz_mm"], [25, 10, 20]),
            "Unrelated reused sibling stays in its accepted pose during preview",
        )
        check(
            len(jobs) == before_jobs
            and state().document_json == canonical
            and instance_matrices() == matrices,
            "Selection and all previews are native-free and leave accepted data/display unchanged",
        )
        check(session.apply(context), "Visual Apply publishes through the guarded Assembly owner")
        check(visual.active(context) is None, "Successful Apply releases the visual owner")
    accepted = data()
    joint = by_id(accepted["joints"], "slide_a")
    check(
        joint["child"] == "sector_a" and joint["kind"] == "slider" and joint["coordinate"] == 12,
        "Apply preserves child and incoming joint identity with an editable slider",
    )
    check(
        accepted["part_sources"] == original["part_sources"]
        and accepted["instances"] == original["instances"]
        and by_id(accepted["joints"], "slide_b") == by_id(original["joints"], "slide_b"),
        "Connector Apply preserves reusable sources, instances and sibling joint bytes",
    )
    old_origin = by_id(by_id(original["parts"], "sector")["mate_frames"], "origin")
    new_sector = by_id(accepted["parts"], "sector")
    check(
        joint["child_frame"] != "origin"
        and by_id(new_sector["mate_frames"], "origin") == old_origin,
        "Edited child gets a dedicated literal connector without moving the shared origin",
    )
    sibling_after_raw = display_observation("sector_b")
    bpy.context.view_layer.update()
    sibling_after = display_observation("sector_b")
    accepted_pose = assembly_state.current_display_response(bpy.context)["report"]["base_pose"]
    diagnostic = {
        "before_evaluation": sibling_before_raw,
        "before": sibling_before,
        "after_before_evaluation": sibling_after_raw,
        "after": sibling_after,
        "before_cad_origin_mm": display_cad_origin_mm(sibling_before),
        "after_cad_origin_mm": display_cad_origin_mm(sibling_after),
        "original_guarded_pose": original_pose["transforms"]["sector_b"],
        "accepted_guarded_pose": accepted_pose["transforms"]["sector_b"],
        "working_part_unchanged": bpy.context.scene.mechanical_cad.document_json == working_part,
    }
    persist("sibling-display-after-apply.json", diagnostic)
    print("VISUAL_JOINT_SIBLING_DISPLAY", json.dumps(diagnostic, sort_keys=True), flush=True)
    check(
        accepted_pose["transforms"]["sector_b"] == original_pose["transforms"]["sector_b"]
        and accepted_pose["transforms"]["sector_b"]["xyz_mm"] == [25, 10, 20]
        and accepted_pose["transforms"]["sector_b"]["wxyz"] == [1, 0, 0, 0],
        "Fresh guarded replay preserves the sibling's exact canonical world pose",
    )
    check(
        assembly_state.display_is_current(bpy.context)
        and sibling_after["matrix_world"] == sibling_before["matrix_world"],
        "Evaluated trusted sibling display matrix is exactly unchanged after Apply",
    )
    check(
        same_position(accepted_pose["transforms"]["sector_a"]["xyz_mm"], [11, 10, 22]),
        "Fresh guarded replay agrees with the edited child's preview placement",
    )
    check(
        bpy.context.scene.mechanical_cad.document_json == working_part,
        "Visual joint Apply preserves exact working Part bytes",
    )
    check(
        assembly_state.display_is_current(bpy.context)
        and not assembly_state.report_is_current(bpy.context)
        and not bpy.ops.mcad.assembly_export_step.poll(),
        "Applied display is current; prior check cannot authorize export",
    )
    accepted_json = state().document_json
    accepted_display = instance_matrices()
    with viewport() as context:
        session = new_session(context, joint_id="slide_a")
        session.set_distance(context, 14.0)
        session.select_connector("child")
        session.roll_connector(context)
        session.cancel("Explicit test Cancel")
        session.cancel("Repeated Cancel is harmless")
        check(
            visual.active(context) is None
            and state().document_json == accepted_json
            and instance_matrices() == accepted_display,
            "Cancel discards coordinate/orientation preview without changing accepted state",
        )
        session = new_session(context, joint_id="slide_a")
        session.set_distance(context, 13.0)

        def fail_publication(*_args, **_kwargs):
            raise RuntimeError("Controlled publication failure after actual guarded replay")

        with patch.object(assembly_state, "_write_fields", fail_publication):
            check(not session.apply(context), "Failed Apply is reported rather than accepted")
        check(
            state().document_json == accepted_json
            and instance_matrices() == accepted_display
            and assembly_state.display_is_current(context),
            "Failed native Apply preserves accepted canonical data and trusted display",
        )
        check(visual.active(context) is session, "Failed current Apply retains an editable draft")
        session.cancel("Leave failed draft explicitly")
    history_journey(accepted_json)
    current_check()
    call(bpy.ops.mcad.assembly_export_step, filepath=str(DIRECTORY / "assembly.step"))
    receipt = json.loads(state().export_receipt_json)
    check(
        receipt["outcome"] == "WRITTEN"
        and receipt["export"]["definition_count"] == 2
        and receipt["export"]["instance_count"] == 3,
        "Checked STEP preserves two reusable definitions and three named instances",
    )
    check(visual.active() is None, "No visual draft remains before save")
    persist(
        "expected.json",
        {
            "assembly": data(),
            "canonical": state().document_json,
            "part": working_part,
            "receipt": state().export_receipt_json,
            "files": {"assembly.step": digest(DIRECTORY / "assembly.step")},
        },
    )
    call(bpy.ops.wm.save_as_mainfile, filepath=str(DIRECTORY / "project.blend"))


def history_journey(before):
    """Actual Blender history, followed by explicit current-evidence recovery."""
    call(bpy.ops.ed.undo_push, message="Before visual slider distance edit")
    with viewport() as context:
        session = new_session(context, joint_id="slide_a")
        session.set_distance(context, 14.0)
        check(session.apply(context), "Existing visual slider distance remains editable")
    after = state().document_json
    check(after != before, "Second visual edit changes the accepted canonical coordinate")
    call(bpy.ops.ed.undo_push, message="After visual slider distance edit")
    with viewport() as context:
        discarded = new_session(context, joint_id="slide_a")
        discarded.set_distance(context, 18.0)
    call(bpy.ops.ed.undo)
    check(state().document_json == before, "Native Undo restores prior visual-joint bytes")
    check(
        visual.active() is None
        and not discarded.alive
        and not discarded.handlers
        and discarded.timer is None
        and discarded.watchdog is None
        and not assembly_state.display_is_current(bpy.context)
        and not bpy.ops.mcad.assembly_export_step.poll(),
        "Undo retires an active unsaved visual draft and all its resources before history changes",
    )
    call(bpy.ops.ed.redo)
    check(state().document_json == after, "Native Redo restores edited visual-joint bytes")
    check(
        not assembly_state.display_is_current(bpy.context)
        and not bpy.ops.mcad.assembly_export_step.poll(),
        "Redo does not revive historical backend evidence",
    )
    call(replay_assembly)
    check(
        assembly_state.display_is_current(bpy.context)
        and not bpy.ops.mcad.assembly_export_step.poll(),
        "Explicit replay restores display but still requires Check Pose",
    )


def reopen():
    expected = json.loads((DIRECTORY / "expected.json").read_text())
    call(bpy.ops.wm.open_mainfile, filepath=str(DIRECTORY / "project.blend"))
    check(
        state().document_json == expected["canonical"]
        and bpy.context.scene.mechanical_cad.document_json == expected["part"],
        "Both exact canonical documents survive a fresh process reopen",
    )
    check(
        visual.active() is None and state().export_receipt_json == expected["receipt"],
        "Reopen restores historical receipt with no active visual draft",
    )
    check(
        not assembly_state.display_is_current(bpy.context)
        and not bpy.ops.mcad.assembly_export_step.poll(),
        "Saved display and saved PASS cannot authorize an export",
    )
    call(replay_assembly)
    check(not bpy.ops.mcad.assembly_export_step.poll(), "Reopen replay still requires Check Pose")
    current_check()
    call(bpy.ops.mcad.assembly_export_step, filepath=str(DIRECTORY / "assembly-reopened.step"))
    check(
        bpy.data.objects["Cube"]["keep"] == "unrelated user object",
        "Unrelated user object survives all edits, history and both process lifetimes",
    )
    for name, expected_hash in expected["files"].items():
        check(digest(DIRECTORY / name) == expected_hash, "Recovery never rewrites " + name)
    persist(
        "reopened-export.json",
        {
            "file": "assembly-reopened.step",
            "sha256": digest(DIRECTORY / "assembly-reopened.step"),
            "receipt": json.loads(state().export_receipt_json),
        },
    )
    call(bpy.ops.wm.save_as_mainfile, filepath=str(DIRECTORY / "project-recovered.blend"))


def main():
    if PHASE not in {"save", "reopen"}:
        raise ValueError("MCAD_VISUAL_JOINT_PHASE must be save or reopen")
    addon.register()
    original = sidecar_job.SidecarJob.start

    def observe(job):
        jobs.append(json.loads(job._payload)["action"])
        return original(job)

    try:
        check(
            getattr(visual.MCAD_OT_assembly_visual_joint, "is_registered", False),
            "Visual joint operator is part of normal add-on registration",
        )
        with patch.object(sidecar_job.SidecarJob, "start", observe):
            (save if PHASE == "save" else reopen)()
        check(not execution_lease.is_busy(), "No final native lease")
        check(
            not any(
                name.split(".")[0] in {"OCP", "slvs", "mechanical_cad"} for name in sys.modules
            ),
            "Native CAD remains outside Blender",
        )
    finally:
        addon.unregister()
    check(visual.active() is None, "Unregister retires every visual owner")
    persist(PHASE + "-result.json", {"checks": checks, "sidecars": jobs, "manual_gui": False})
    print("VISUAL_JOINT_SMOKE_OK", PHASE, flush=True)


if __name__ == "__main__":

    def timeout(_signum, _frame):
        raise TimeoutError("Visual joint owner lifetime exceeded 600 seconds")

    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(600)
    try:
        main()
    finally:
        signal.alarm(0)
