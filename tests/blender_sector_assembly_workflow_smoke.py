"""One native project: box, drawn constrained sectors, reuse, edit, check, reopen.

Run only in an authorized native slot, with MCAD_ROOT, MCAD_PYTHON and a new
MCAD_SECTOR_ASSEMBLY_DIRECTORY, using --background --factory-startup
--python-exit-code 1. Run save then reopen as two separately owned Blender
lifetimes with the same directory and MCAD_SECTOR_ASSEMBLY_PHASE=reopen for
the second. The outer process collector owns both; this script launches no Blender.
Part exports reuse the existing same-invocation STEP/STL observation utility;
there is no assembly export, separate reader process or manual-GUI claim.
"""

import copy
import json
import math
import os
import signal
import sys
import time
from pathlib import Path
from unittest.mock import patch

import bpy

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
DIRECTORY = Path(os.environ["MCAD_SECTOR_ASSEMBLY_DIRECTORY"]).resolve()
PHASE = os.environ.get("MCAD_SECTOR_ASSEMBLY_PHASE", "save")
os.environ["MCAD_ROOT"] = str(ROOT)
sys.path.insert(0, str(ROOT / "blender_addon"))
sys.path.insert(0, str(ROOT / "tests"))
from blender_async_helpers import replay_assembly  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))
import blender_geometry3_owner_smoke as geometry_tools  # noqa: E402
import mechanical_cad_blender as addon  # noqa: E402
from mechanical_cad_blender import (  # noqa: E402
    assembly_bridge,
    assembly_display,
    assembly_state,
    document_state,
    execution_lease,
    general_session,
    sidecar_job,
    sketch_session,
    workspace,
)
from mechanical_cad_blender.general_sketch_commands import (  # noqa: E402
    AddRelation,
    PointRef,
    PointSeed,
)

checks = []
jobs = []


def check(value, label):
    assert value, label
    checks.append(label)
    print("SECTOR_ASSEMBLY_CHECK", label, flush=True)


def call(operator, **arguments):
    check(operator(**arguments) == {"FINISHED"}, operator.idname() + " completes")
    check(not execution_lease.is_busy(), "Synchronous operation releases native lease")


def reject(operation, label):
    try:
        result = operation()
    except (RuntimeError, ValueError):
        check(True, label)
    else:
        check(result == {"CANCELLED"}, label)


def write(name, value):
    geometry_tools.persist(DIRECTORY / name, value)


def part_state():
    return bpy.context.scene.mechanical_cad


def state():
    return bpy.context.scene.mechanical_cad_assembly


def assembly():
    return assembly_state.read_assembly(state())


def report():
    return json.loads(state().report_json)


def wait(owner):
    deadline = time.monotonic() + 90
    while owner.pending is not None and time.monotonic() < deadline:
        owner.tick(bpy.context)
        time.sleep(0.01)
    if owner.pending is not None:
        owner.cancel_native("Integrated project test timed out")
        raise AssertionError("Sector authoring did not finish within 90 seconds")
    check(not owner.error and not execution_lease.is_busy(), "Sector owner collected native work")


def part_volume(expected, version):
    result = document_state.current_part_result(bpy.context)
    check(result is not None and result["result_version"] == version, "Current typed Part result")
    row = next(item for item in result["features"] if item["id"] == result["active_feature"])
    check(row["status"] == "ok", "Selected output is a fresh successful solid")
    check(math.isclose(row["stats"]["volume"], expected, rel_tol=1e-11), "Exact Part volume")


def native_assembly(radius, base, children):
    response = report()
    check(response["ok"] and response["result_version"] == 3, "Mixed Assembly uses result3")
    sources = response["result"]["source_replays"]
    check(len(sources) == 2, "Each of the two sources has one retained full replay")
    for source in sources:
        check(source["replay"]["result_version"] == 3, "Full source evidence is genuine replay3")
        check(source["status"] == "ok", "Both accepted sources replay successfully")
    parts = {row["id"]: row for row in response["result"]["parts"]}
    definitions = {row["id"]: row["part_id"] for row in assembly()["instances"]}
    for identifier, expected in (
        (base, 40 * 30 * 10),
        *((identifier, math.pi * radius**2 * 10 / 4) for identifier in children),
    ):
        geometry = parts[definitions[identifier]]["geometry_check"]
        check(
            geometry["brep"]["valid"]
            and geometry["brep"]["solids"] == 1
            and geometry["mesh"]["watertight"],
            "Every Assembly definition passes its fresh Part check",
        )
        check(
            math.isclose(geometry["brep"]["volume"], expected, rel_tol=1e-11),
            "Assembly exact volume matches accepted source revision",
        )
    bpy.context.view_layer.update()
    transforms = response["report"]["base_pose"]["transforms"]
    objects = {
        obj[assembly_display.INSTANCE_KEY]: obj
        for obj in assembly_display.owned_objects(bpy.context.scene, state().owner_id)
        if obj.get(assembly_display.ROLE_KEY) == "instance"
    }
    check(objects[children[0]].data == objects[children[1]].data, "Sector instances share one mesh")
    scale = 0.001 / bpy.context.scene.unit_settings.scale_length
    for identifier in (base, *children):
        payload = parts[definitions[identifier]]["mesh"]["vertices"]
        obj = objects[identifier]
        pose = transforms[identifier]
        for vertex, source in zip(obj.data.vertices, payload, strict=True):
            rotated = assembly_display._rotate(pose["wxyz"], source)
            expected = [scale * (v + t) for v, t in zip(rotated, pose["xyz_mm"], strict=True)]
            actual = obj.matrix_world @ vertex.co
            assert all(
                math.isclose(a, b, abs_tol=2e-7) for a, b in zip(actual, expected, strict=True)
            )
    check(True, "Every displayed vertex agrees with exact explicit Assembly placement")
    check(transforms[base]["xyz_mm"] == [0, 0, 0], "Box is explicitly grounded at origin")
    check(transforms[children[0]]["xyz_mm"] == [10, 10, 20], "Sector A uses literal seat and slide")
    check(transforms[children[1]]["xyz_mm"] == [25, 10, 20], "Sector B uses its own literal seat")


def draw_sector():
    """Use the existing live owner and exact point/constraint UI adapters."""
    call(bpy.ops.mcad.new_document, name="Reusable quarter sector R5 H10")
    bpy.context.window.workspace[workspace.ROLE_KEY] = "SKETCH"
    owner = general_session.GeneralSession(bpy.context)
    owner.start()
    owner.enable_arc(owner.prepare_gesture("arc"))
    for role, point in (("center", (0, 0)), ("start", (5, 0)), ("end", (0, 5))):
        owner.accept_point_input(bpy.context, PointSeed(*point), expected_phase=("arc", role))
    wait(owner)
    arc = owner.commands.sketch["arcs"][0]
    call(bpy.ops.mcad.general_tool, tool="Line")
    for end_role in ("start", "end"):
        for phase, role in (("start", "center"), ("end", end_role)):
            owner.accept_point_input(
                bpy.context,
                PointRef(arc[role]),
                expected_phase=("line", phase),
                source_kind="arc",
                source_id=arc["id"],
                role=role,
                picker=owner.prepare_gesture("point"),
            )
        wait(owner)
    lines = {line["end"]: line["id"] for line in owner.commands.sketch["lines"]}
    for relation in (
        AddRelation("fixed", (arc["center"],), target=(0, 0)),
        AddRelation("horizontal", (lines[arc["start"]],)),
        AddRelation("vertical", (lines[arc["end"]],)),
    ):
        owner.execute(bpy.context, relation)
        wait(owner)
    outcome = owner.execute(
        bpy.context, AddRelation("radius", (arc["id"],), value=5), annotation_offset=(6, 6)
    )
    radius_id = outcome.constraint_id
    wait(owner)
    check(
        owner.current_solution_response()["result"]["sketch"]["remaining_dof"] == 0,
        "Fixed center, H/V radii and radius dimension fully constrain the sector",
    )
    profile = owner.commands.feature_id
    owner.request_finish(bpy.context)
    wait(owner)
    check(owner.finished and sketch_session.active_session() is None, "Finish closes live sketch")
    bpy.context.window.workspace[workspace.ROLE_KEY] = "PART"
    call(bpy.ops.mcad.add_extrude, profile=profile, length=10)
    part_volume(math.pi * 25 * 10 / 4, 3)
    return profile, radius_id


def save_project():
    DIRECTORY.mkdir(parents=True, exist_ok=False)
    geometry = geometry_tools.NativeGate(
        DIRECTORY / "part_geometry",
        (
            "box_check",
            "box_step",
            "box_stl",
            "sector_r5_check",
            "sector_r7_check",
            "sector_step",
            "sector_stl",
        ),
    )
    scene = bpy.context.scene
    scene.name = "Box and reusable sectors"
    units = (scene.unit_settings.system, scene.unit_settings.scale_length)
    unrelated = bpy.data.objects.new("Unrelated project annotation", None)
    scene.collection.objects.link(unrelated)
    unrelated.location = (1, 2, 3)
    unrelated["keep"] = "unrelated user content"
    call(bpy.ops.mcad.new_document, name="Box base 40 x 30 x 10")
    call(bpy.ops.mcad.add_rectangle, width=40, height=30, x=0, y=0, z=0)
    call(bpy.ops.mcad.add_extrude, profile=part_state().active_feature, length=10)
    part_volume(12000, 2)
    call(bpy.ops.mcad.save_document, filepath=str(DIRECTORY / "base.mcad.json"))
    for label, action, filename in (
        ("box_check", "check_geometry", None),
        ("box_step", "export_step", "base.step"),
        ("box_stl", "export_stl", "base.stl"),
    ):
        geometry.call(label, action, destination=DIRECTORY / filename if filename else None)
        geometry_tools.current(action, 2)
    call(
        bpy.ops.mcad.assembly_new,
        name="Box and reusable sectors",
        instance_name="Box base",
        grounded=True,
    )
    base = assembly()["grounded_instance"]
    base_part = assembly()["parts"][0]["id"]
    seats = []
    for name, xyz in (("Seat A", "10,10,10"), ("Seat B", "25,10,10")):
        call(
            bpy.ops.mcad.assembly_frame,
            part_id=base_part,
            name=name,
            xyz=xyz,
            rotation_degrees="0,0,0",
        )
        seats.append(assembly()["parts"][0]["mate_frames"][-1]["id"])
    profile, radius_id = draw_sector()
    geometry.call("sector_r5_check", "check_geometry")
    geometry_tools.current("check_geometry", 3)
    radius5 = json.loads(part_state().document_json)
    call(bpy.ops.mcad.save_document, filepath=str(DIRECTORY / "sector-radius5.mcad.json"))
    call(
        bpy.ops.mcad.assembly_insert,
        use_working_part=True,
        parent=base,
        parent_frame=seats[0],
        child_frame="origin",
        kind="slider",
        coordinate="10",
        use_limits=True,
        lower="-10",
        upper="30",
        name="Sector A",
        joint_name="Sector A slide",
    )
    sector_part = assembly()["instances"][-1]["part_id"]
    call(
        bpy.ops.mcad.assembly_insert,
        part_id=sector_part,
        parent=base,
        parent_frame=seats[1],
        child_frame="origin",
        kind="slider",
        coordinate="10",
        use_limits=True,
        lower="-10",
        upper="30",
        name="Sector B",
        joint_name="Sector B slide",
    )
    children = [row["id"] for row in assembly()["instances"] if row["part_id"] == sector_part]
    slide = next(row["id"] for row in assembly()["joints"] if row["child"] == children[0])
    native_assembly(5, base, children)
    call(bpy.ops.mcad.assembly_check)
    check(not report()["report"]["passed"], "Measurements without explicit intent never pass")
    preset = ""
    for child in children:
        call(
            bpy.ops.mcad.assembly_preset,
            preset_id=preset,
            name="Both sectors clear the base",
            kind="clearance",
            pair_a=base,
            pair_b=child,
            requirement_name="Base to " + child + " gap",
            minimum_mm="2",
            activate=False,
        )
        preset = assembly()["verification_presets"][0]["id"]
    check(assembly()["active_verification_preset"] is None, "Saving intent does not activate it")
    call(bpy.ops.mcad.assembly_select_preset, preset_id=preset)
    call(bpy.ops.mcad.assembly_check)
    check(
        report()["report"]["complete"] and report()["report"]["passed"],
        "Explicit R5 clearance passes",
    )

    accepted = state().document_json
    call(bpy.ops.mcad.assembly_open_part, part_id=base_part, confirmed=True)
    reject(
        lambda: bpy.ops.mcad.assembly_open_part(part_id=sector_part, confirmed=False),
        "Replacing the working Part needs the explicit existing confirmation",
    )
    call(bpy.ops.mcad.assembly_open_part, part_id=sector_part, confirmed=True)
    check(state().document_json == accepted, "Opening the embedded sector leaves Assembly exact")
    owner = general_session.GeneralSession(bpy.context, profile)
    owner.start()
    owner.check(bpy.context)
    wait(owner)
    owner.begin_dimension(radius_id)
    owner.update_raw("7")
    owner.request_driver_accept(bpy.context)
    wait(owner)
    owner.request_finish(bpy.context)
    wait(owner)
    radius7 = json.loads(part_state().document_json)
    check(
        geometry_tools.shape(radius5) == geometry_tools.shape(radius7)
        and [row["id"] for row in radius5["features"]]
        == [row["id"] for row in radius7["features"]],
        "Radius5 to radius7 preserves authored seeds, entities and feature IDs",
    )
    part_volume(math.pi * 49 * 10 / 4, 3)
    check(state().document_json == accepted, "Working edit does not silently update Assembly")
    updates = assembly_state.source_updates(bpy.context)
    check(
        len(updates) == 1 and set(updates[0]["instance_ids"]) == set(children),
        "Update names both sector instances",
    )
    literal_frames = [copy.deepcopy(row["mate_frames"]) for row in assembly()["parts"]]
    call(bpy.ops.mcad.assembly_update_source)
    check(
        not assembly_state.source_updates(bpy.context),
        "Both instances accept the same revised source",
    )
    check(
        [row["mate_frames"] for row in assembly()["parts"]] == literal_frames,
        "Literal frames remain unchanged",
    )
    check(
        not assembly_state.report_is_current(bpy.context),
        "Source update invalidates earlier verification",
    )
    native_assembly(7, base, children)

    # One failed source update: preserve both accepted instances and their meshes.
    accepted = state().document_json
    owned = {obj.as_pointer() for obj in assembly_display.owned_objects(scene, state().owner_id)}
    height = next(row for row in part_state().parameters if "length" in row.key)
    height.value = -1
    reject(
        lambda: bpy.ops.mcad.assembly_update_source(), "Invalid extrusion source update is rejected"
    )
    check(
        state().document_json == accepted,
        "Failed source update preserves accepted canonical Assembly",
    )
    check(
        owned
        == {obj.as_pointer() for obj in assembly_display.owned_objects(scene, state().owner_id)},
        "Failed source update preserves both instance displays",
    )
    height.value = 10
    call(bpy.ops.mcad.regenerate)
    check(
        not assembly_state.source_updates(bpy.context),
        "Correcting height restores the accepted source",
    )

    call(
        bpy.ops.mcad.assembly_joint,
        joint_id=slide,
        coordinate="-5",
        use_limits=True,
        lower="-10",
        upper="30",
    )
    check(not assembly_state.report_is_current(bpy.context), "Joint edit invalidates old check")
    call(bpy.ops.mcad.assembly_sample, joint_id=slide, values="-5, 10")
    sampled = report()
    check(
        sampled["report"]["known_interference"] and not sampled["report"]["passed"],
        "Listed colliding pose remains a known violation",
    )
    check(
        sampled["report"]["continuous_collision_guarantee"] is False,
        "Listed poses do not certify continuous motion",
    )
    check(
        next(row["coordinate"] for row in assembly()["joints"] if row["id"] == slide) == -5,
        "Sampling never changes saved joint coordinate",
    )
    write("sampled-collision-report.json", sampled)
    call(
        bpy.ops.mcad.assembly_joint,
        joint_id=slide,
        coordinate="10",
        use_limits=True,
        lower="-10",
        upper="30",
    )
    call(bpy.ops.mcad.assembly_check)
    check(report()["report"]["passed"], "Restored explicit clear pose passes")
    native_assembly(7, base, children)

    # Wrong-version and late-completion controls use the same accepted project.
    request = json.loads(state().report_request_json)
    altered = report()
    altered["result_version"] = 2
    reject(
        lambda: assembly_bridge.validate_response(request, altered),
        "Result2 cannot replace the mixed result3 response",
    )
    accepted, prior_report = state().document_json, state().report_json
    run = assembly_state._run_sidecar

    def late_completion(*args, **kwargs):
        evidence = run(*args, **kwargs)
        state().document_json = accepted + "\n"
        return evidence

    with patch.object(assembly_state, "_run_sidecar", late_completion):
        reject(
            lambda: bpy.ops.mcad.assembly_check(), "Late result cannot replace a changed Assembly"
        )
    check(
        state().document_json == accepted + "\n" and state().report_json == prior_report,
        "Late completion preserves newer bytes and old report",
    )
    state().document_json = accepted
    call(replay_assembly)
    call(bpy.ops.mcad.assembly_check)
    check(
        assembly_state.report_is_current(bpy.context) and report()["report"]["passed"],
        "Explicit replay/check restores current authority",
    )
    call(bpy.ops.mcad.save_document, filepath=str(DIRECTORY / "sector-radius7.mcad.json"))
    for label, action, filename in (
        ("sector_r7_check", "check_geometry", None),
        ("sector_step", "export_step", "sector-radius7.step"),
        ("sector_stl", "export_stl", "sector-radius7.stl"),
    ):
        geometry.call(label, action, destination=DIRECTORY / filename if filename else None)
        geometry_tools.current(action, 3)
        part_volume(math.pi * 49 * 10 / 4, 3)
        if filename:
            check(
                geometry_tools.report()["export"]["destination"] == str(DIRECTORY / filename),
                "Verified individual Part export uses the exact test-owned path",
            )
    geometry.finish()
    call(bpy.ops.mcad.assembly_save, filepath=str(DIRECTORY / "project.mcad-assembly.json"))
    check(
        json.loads((DIRECTORY / "project.mcad-assembly.json").read_text()) == assembly(),
        "Portable saved project embeds both accepted source snapshots",
    )
    check(
        unrelated["keep"] == "unrelated user content" and tuple(unrelated.location) == (1, 2, 3),
        "Unrelated object survives the whole project journey",
    )
    check(
        (scene.unit_settings.system, scene.unit_settings.scale_length) == units,
        "User unit settings are preserved",
    )
    write(
        "expected.json",
        {
            "assembly": state().document_json,
            "part": part_state().document_json,
            "report": state().report_json,
            "geometry_report": part_state().geometry_report_json,
            "base": base,
            "children": children,
            "files": {
                name: geometry_tools.digest(DIRECTORY / name)
                for name in ("base.step", "base.stl", "sector-radius7.step", "sector-radius7.stl")
            },
        },
    )
    call(bpy.ops.wm.save_as_mainfile, filepath=str(DIRECTORY / "project.blend"))


def reopen_project():
    expected = json.loads((DIRECTORY / "expected.json").read_text())

    def no_work(*args, **kwargs):
        raise AssertionError("Reopening saved history must not launch native work")

    with (
        patch.object(sidecar_job.SidecarJob, "start", no_work),
        patch.object(execution_lease, "try_acquire", no_work),
    ):
        call(bpy.ops.wm.open_mainfile, filepath=str(DIRECTORY / "project.blend"))
        check(state().document_json == expected["assembly"], "Reopen preserves exact Assembly JSON")
        check(
            part_state().document_json == expected["part"],
            "Reopen preserves exact editable Part JSON",
        )
        check(
            state().report_json == expected["report"],
            "Saved Assembly report remains readable history",
        )
        check(
            part_state().geometry_report_json == expected["geometry_report"],
            "Saved Part export report remains readable history",
        )
        check(
            not assembly_state.display_is_current(bpy.context),
            "Saved Assembly display is historical",
        )
        check(
            not assembly_state.report_is_current(bpy.context), "Saved Assembly check is historical"
        )
        check(
            not document_state.geometry_report_is_current(bpy.context),
            "Saved Part export cannot restore current authority",
        )
    call(replay_assembly)
    check(assembly_state.display_is_current(bpy.context), "Explicit reopen replay restores display")
    check(not assembly_state.report_is_current(bpy.context), "Replay does not certify saved check")
    call(bpy.ops.mcad.assembly_check)
    check(
        assembly_state.report_is_current(bpy.context) and report()["report"]["passed"],
        "Explicit reopen Check restores exact clearance evidence",
    )
    native_assembly(7, expected["base"], expected["children"])
    call(bpy.ops.mcad.check_geometry)
    geometry_tools.current("check_geometry", 3)
    part_volume(math.pi * 49 * 10 / 4, 3)
    for name, digest in expected["files"].items():
        check(
            geometry_tools.digest(DIRECTORY / name) == digest, "Reopen/check never rewrites " + name
        )
    unrelated = bpy.context.scene.objects["Unrelated project annotation"]
    check(
        unrelated["keep"] == "unrelated user content",
        "Unrelated saved object survives second lifetime",
    )
    write("reopened-current-report.json", report())


def main():
    addon.register()
    original_start = sidecar_job.SidecarJob.start

    def observe_start(job):
        request = json.loads(job._payload)
        jobs.append(
            {"action": request.get("action"), "result_version": request.get("result_version")}
        )
        return original_start(job)

    try:
        with patch.object(sidecar_job.SidecarJob, "start", observe_start):
            if PHASE == "save":
                window, area, region = geometry_tools.context_parts()
                with bpy.context.temp_override(window=window, area=area, region=region):
                    save_project()
            elif PHASE == "reopen":
                # Opening replaces window/area RNA: never retain an override across it.
                reopen_project()
            else:
                raise AssertionError("Unknown workflow phase")
        check(not execution_lease.is_busy(), "No final native lease remains")
        check(
            not any(
                name.split(".")[0] in {"OCP", "slvs", "mechanical_cad"} for name in sys.modules
            ),
            "Native CAD and core stay outside Blender",
        )
    finally:
        try:
            if DIRECTORY.is_dir():
                write(
                    PHASE + "-checks.json",
                    {"checks": checks, "sidecars": jobs, "gui_qualification": False},
                )
        finally:
            # The existing lifecycle owner cancels and joins any in-flight sidecar,
            # including when the bounded journey timer interrupts a failed check.
            addon.unregister()
    print("SECTOR_ASSEMBLY_WORKFLOW_OK", PHASE, len(checks), "sidecars", len(jobs), flush=True)


if __name__ == "__main__":
    if not sys.platform.startswith("linux"):
        raise SystemExit("This source-loaded lifetime regression is qualified on Linux only.")

    def journey_timeout(_signum, _frame):
        raise TimeoutError("The integrated project exceeded its 900-second lifetime limit")

    signal.signal(signal.SIGALRM, journey_timeout)
    signal.alarm(900)
    try:
        main()
    finally:
        signal.alarm(0)
