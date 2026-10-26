"""Native two-process Mate by Faces adapter/raycast, Apply/Cancel and persistence check.
MCAD_ROOT, MCAD_PYTHON, MCAD_FACE_DIRECTORY and MCAD_FACE_PHASE=save/reopen.
Headless adapter coverage, not manual GUI usability qualification.
"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import bpy
from mathutils import Vector

ROOT = Path(os.environ["MCAD_ROOT"])
OUT = Path(os.environ["MCAD_FACE_DIRECTORY"])
sys.path.insert(0, str(ROOT / "blender_addon"))
sys.path.insert(0, str(ROOT / "tests"))
import mechanical_cad_blender as addon  # noqa: E402
from blender_async_helpers import replay_assembly  # noqa: E402
from mechanical_cad_blender import assembly_joint_viewport as visual  # noqa: E402
from mechanical_cad_blender import assembly_state as state_api  # noqa: E402
from mechanical_cad_blender.assembly_joint_draft import local_to_world, rotate  # noqa: E402

addon.register()
state = bpy.context.scene.mechanical_cad_assembly
window = bpy.context.window
area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
region = next(r for r in area.regions if r.type == "WINDOW")
phase = os.environ.get("MCAD_FACE_PHASE", "save")
try:
    with bpy.context.temp_override(window=window, area=area, region=region):
        context = bpy.context
        if phase == "save":
            OUT.mkdir(parents=True, exist_ok=True)
            bpy.data.objects["Cube"].hide_set(True)
            assert bpy.ops.mcad.assembly_load(
                filepath=str(ROOT / "examples/reused_blocks.mcad-assembly.json")
            ) == {"FINISHED"}
            # Ordinary origin/origin insertion can produce coincident components.
            coincident = json.loads(state.document_json)
            for joint in coincident["joints"]:
                joint["kind"] = "fixed"
                joint["parent_frame"] = joint["child_frame"] = "origin"
                joint.pop("coordinate", None)
                joint.pop("limits", None)
            state_api.commit_candidate(context, coincident, expected_json=state.document_json)
            context.view_layer.update()
            original = state.document_json
            probe = visual.JointViewportSession(context, mate_faces=True)
            probe.owned_meshes["b"].hide_set(True)
            baseline = {key: obj.hide_get() for key, obj in probe.owned_meshes.items()}
            probe.start()
            assert probe.pick_target == "root"
            assert probe.owned_meshes["a"].hide_get()
            probe.cancel()
            assert {key: obj.hide_get() for key, obj in probe.owned_meshes.items()} == baseline
            stale = visual.JointViewportSession(context, mate_faces=True).start()
            state.document_json += " "
            assert not stale.apply(context)
            assert {key: obj.hide_get() for key, obj in stale.owned_meshes.items()} == baseline
            state.document_json = original
            owner = visual.JointViewportSession(context, mate_faces=True).start()
            owner.isolate_target(1)
            assert owner.pick_target == "a"
            owner.isolate_target(-1)
            assert owner.pick_target == "root"
            # A failed hit releases all temporary visibility; retry isolates again.
            with patch.object(visual, "_nearest_visible_mesh", return_value=None):
                try:
                    owner.pick_face(context, (500, 400))
                except Exception:
                    pass
                else:
                    raise AssertionError("Empty pick must fail")
            assert {key: obj.hide_get() for key, obj in owner.owned_meshes.items()} == baseline
            for identifier in ("root", "a"):
                row = owner.parts[owner.instances[identifier]["part_id"]]
                face = next(
                    f
                    for f in row["topology"]
                    if f["signature"]["surface"] == "plane" and f["signature"]["normal"][0] > 0.99
                )
                frame = local_to_world(
                    owner.accepted_transforms[identifier],
                    {"xyz_mm": face["signature"]["centroid"], "wxyz": [1, 0, 0, 0]},
                )
                normal = Vector(
                    rotate(
                        owner.accepted_transforms[identifier]["wxyz"], face["signature"]["normal"]
                    )
                )
                origin = Vector(frame["xyz_mm"]) * owner.scale + normal * 0.03
                with (
                    patch.object(
                        visual.view3d_utils, "region_2d_to_origin_3d", return_value=origin
                    ),
                    patch.object(
                        visual.view3d_utils, "region_2d_to_vector_3d", return_value=-normal
                    ),
                ):
                    owner.pick_face(context, (500, 400))
            assert {key: obj.hide_get() for key, obj in owner.owned_meshes.items()} == baseline
            assert owner.parent_id == "root" and owner.child_id == "a"
            assert state.document_json == original
            assert owner.draft.support_id("parent") and owner.draft.support_id("child")
            owner.clear_motion(context)
            owner.set_kind(context, "fixed")
            owner.flip_connector(context)
            owner.roll_connector(context)
            owner.translate_connector(context, "parent", "Z", 2.5)
            assert owner.apply(context), owner.error
            # Exercise each existing multi-axis kind with nonzero authored values.
            from mechanical_cad_blender.assembly_coordinates import extra_names

            for kind in ("cylindrical", "planar", "spherical"):
                seed = visual.JointViewportSession(context, joint_id="slide_a").start()
                seed.clear_motion(context)
                seed.set_kind(context, kind)
                candidate = seed.draft.candidate()
                seed.cancel()
                joint = next(j for j in candidate["joints"] if j["id"] == "slide_a")
                for n, name in enumerate(extra_names(kind)):
                    joint[name], joint[name + "_limits"] = (n + 1) * 0.15, [-2, 2]
                state_api.commit_candidate(context, candidate, expected_json=state.document_json)
                edit = visual.JointViewportSession(context, joint_id="slide_a").start()
                edit.translate_connector(context, "parent", "X", 0.5)
                assert edit.apply(context), edit.error
                published = next(
                    j for j in json.loads(state.document_json)["joints"] if j["id"] == "slide_a"
                )
                for name in extra_names(kind):
                    assert published[name] == joint[name]
                    assert published[name + "_limits"] == joint[name + "_limits"]
            accepted = state.document_json
            edit = visual.JointViewportSession(context, joint_id="slide_a").start()
            assert edit.mate_faces and edit.draft.candidate() == json.loads(accepted)
            edit.translate_connector(context, "child", "X", 3)
            edit.cancel()
            assert state.document_json == accepted
            # Canonical changes make the pending draft stale before publication.
            edit = visual.JointViewportSession(context, joint_id="slide_a").start()
            state.document_json += " "
            assert not edit.apply(context)
            state.document_json = accepted
            (OUT / "accepted.json").write_text(accepted)
            bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "faces.blend"))
        else:
            assert state.document_json == (OUT / "accepted.json").read_text()
            assert not state_api.display_is_current(context)
            assert replay_assembly() == {"FINISHED"}
            edit = visual.JointViewportSession(context, joint_id="slide_a").start()
            assert edit.draft.candidate() == json.loads(state.document_json)
            edit.translate_connector(context, "parent", "X", 1)
            assert edit.apply(context), edit.error
            frames = json.loads(state.document_json)["parts"][0]["mate_frames"]
            assert len([f for f in frames if "support_face" in f]) == 2
        print("FACE_MATING_SMOKE_OK", phase, flush=True)
finally:
    addon.unregister()
