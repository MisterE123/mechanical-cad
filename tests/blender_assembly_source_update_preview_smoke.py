"""Native all-instance source-update preview; no GUI qualification claimed."""

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
from mechanical_cad_blender import (  # noqa: E402
    assembly_display,
    assembly_pending,
    assembly_state,
    document_state,  # noqa: E402
    execution_lease,
    register,  # noqa: E402
)
from mechanical_cad_blender import assembly_source_update_preview as source_preview  # noqa: E402

register()
checks = []
OUT = Path(
    os.environ.get(
        "MCAD_SOURCE_PREVIEW_OUT",
        str(ROOT / "evidence/assembly-source-preview-20261026/native-owner"),
    )
)
OUT.mkdir(exist_ok=True)
MODE = os.environ.get("MCAD_SOURCE_PREVIEW_MODE", "create")


def check(value, label):
    assert value, label
    checks.append(label)
    print("SOURCE_UPDATE_CHECK", label, flush=True)


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


def watch(owner):
    show = owner._show_response

    def capture(response):
        owner.test_response = copy.deepcopy(response)
        show(response)

    owner._show_response = capture
    return owner


def geometry(response, volume):
    check(
        set(response["report"]["base_pose"]["transforms"]) == {"root", "a", "b"},
        "Full three-instance pose",
    )
    parts = response["result"]["parts"]
    check(
        len(parts) == 1
        and math.isclose(parts[0]["geometry_check"]["brep"]["volume"], volume, abs_tol=1e-8),
        "Exact block source volume " + str(volume),
    )


if MODE == "face":
    call(
        bpy.ops.mcad.assembly_load, filepath=str(ROOT / "examples/reused_blocks.mcad-assembly.json")
    )
    fixture = copy.deepcopy(data())
    frame = copy.deepcopy(fixture["parts"][0]["mate_frames"][0])
    frame.update(id="top", name="Top face", support_face="pad/face/cap.end")
    fixture["parts"][0]["mate_frames"].append(frame)
    fixture["joints"][0]["parent_frame"] = "top"
    assembly_state.commit_candidate(
        bpy.context, fixture, expected_json=bpy.context.scene.mechanical_cad_assembly.document_json
    )
    initial = assembly_state.current_display_response(bpy.context)
    working = copy.deepcopy(fixture["part_sources"][0]["document"])
    working["features"][-1]["params"]["length"] = 20
    check(
        document_state._commit_candidate(bpy.context, working),
        "Prepare taller source without editing joint coordinates",
    )
    baseline = accepted()
    with viewport() as context:
        owner = watch(source_preview.SourceUpdatePreview(context)).start(context)
        finish(owner, context)
        geometry(owner.test_response, 2000)
        old, new = (
            initial["report"]["base_pose"]["transforms"],
            owner.test_response["report"]["base_pose"]["transforms"],
        )
        check(
            old["a"]["xyz_mm"] == [5, 5, 110] and new["a"]["xyz_mm"] == [5, 5, 120],
            "Face-attached parent mate moves child ghost10 mm before Apply",
        )
        check(
            old["root"] == new["root"] and old["b"] == new["b"],
            "Literal root/b poses remain unchanged",
        )
        top = owner.test_response["result"]["parts"][0]["resolved_mate_frames"]["top"]
        check(top["xyz_mm"] == [5, 5, 20], "Exact resolved top-face mate follows new source height")
        check(
            accepted() == baseline,
            "Associative preview leaves accepted source/mates/display untouched",
        )
        (OUT / "face-ready-response.json").write_text(json.dumps(owner.test_response, indent=2))
        owner.cancel()
        reap()
        check(
            accepted() == baseline, "Associative preview Cancel never publishes changed placement"
        )
    working["features"][-1]["id"] = "old_pad"
    working["features"].append(
        {
            "id": "pad",
            "kind": "transform",
            "label": "Identity output",
            "params": {key: 0 for key in ("x", "y", "z", "rx", "ry", "rz")},
            "inputs": {"base": "old_pad"},
        }
    )
    check(
        document_state._commit_candidate(bpy.context, working),
        "Prepare valid solid whose old semantic support face is gone",
    )
    baseline = accepted()
    with viewport() as context:
        owner = source_preview.SourceUpdatePreview(context).start(context)
        deadline = time.monotonic() + 60
        while owner.pending is not None and not owner.error and time.monotonic() < deadline:
            owner.tick(context)
            time.sleep(0.02)
        face_error = owner.error
        print("SOURCE_UPDATE_FACE_ERROR", repr(face_error), flush=True)
        check(bool(face_error), "Missing face preview reports refusal")
        check(
            not owner.ready() and not owner.expectation and not owner.ghost_positions,
            "Missing face produces no ready ghost or acceptance expectation",
        )
        check(not owner.apply(context), "Missing face cannot Apply")
        check(
            accepted() == baseline,
            "Missing face refusal preserves accepted canonical/report/object identities and poses",
        )
        owner.cancel()
        reap()
    check(
        {j["id"]: j["coordinate"] for j in data()["joints"]} == {"slide_a": 100, "slide_b": 100},
        "Face fixture never changes slider coordinates",
    )
    check("face" in face_error.lower(), "Missing face preview preserves repair diagnosis")
    marker = "SOURCE_UPDATE_FACE_PREVIEW_OK"
elif MODE == "reopen":
    call(bpy.ops.wm.open_mainfile, filepath=str(OUT / "source-update.blend"))
    check(
        bpy.context.scene.mechanical_cad_assembly.document_json
        == (OUT / "accepted.json").read_text(),
        "Fresh process preserves accepted updated source",
    )
    check(source_preview.active() is None, "No transient source preview owner restored")
    check(
        not assembly_state.display_is_current(bpy.context), "Saved source requires explicit Replay"
    )
    call(replay_assembly)
    geometry(assembly_state.current_display_response(bpy.context), 2000)
    check(
        data()["part_sources"][0]["document"]["parameters"]["width"] == 20,
        "Updated embedded width20 persists",
    )
    check(
        {joint["id"]: joint["coordinate"] for joint in data()["joints"]}
        == {"slide_a": 100, "slide_b": 100},
        "No slider coordinates changed",
    )
    marker = "SOURCE_UPDATE_PREVIEW_REOPEN_OK"
else:
    call(
        bpy.ops.mcad.assembly_load, filepath=str(ROOT / "examples/reused_blocks.mcad-assembly.json")
    )
    original = copy.deepcopy(data())
    working = copy.deepcopy(original["part_sources"][0]["document"])
    working["parameters"]["width"] = 20
    check(
        document_state._commit_candidate(bpy.context, working),
        "Prepare independently edited working Part width20",
    )
    baseline = accepted()
    initial = assembly_state.current_display_response(bpy.context)
    geometry(initial, 1000)
    with viewport() as context:
        owner = watch(source_preview.SourceUpdatePreview(context)).start(context)
        check(
            not owner.ready() and owner.pending is not None and not owner.ghost_positions,
            "Pending has no ready ghost",
        )
        check(
            accepted() == baseline,
            "Pending leaves accepted assembly/report/display and working Part untouched",
        )
        finish(owner, context)
        geometry(owner.test_response, 2000)
        check(
            set(owner.affected) == {"root", "a", "b"}, "Preview lists all affected reused instances"
        )
        check(
            owner.test_response["report"]["base_pose"]["transforms"]
            == initial["report"]["base_pose"]["transforms"],
            "Geometry update does not move literal instance poses",
        )
        check(bool(owner.ghost_positions), "Changed full geometry ghost is present")
        check(
            accepted() == baseline, "Ready source preview never publishes canonical/report/display"
        )
        (OUT / "ready-response.json").write_text(json.dumps(owner.test_response, indent=2))
        owner.cancel()
        reap()
        check(
            accepted() == baseline and source_preview.active() is None,
            "Cancel discards ready ghost and keeps accepted source/objects",
        )
    with viewport() as context:
        owner = watch(source_preview.SourceUpdatePreview(context)).start(context)
        finish(owner, context)
        part = context.scene.mechanical_cad
        before_part = part.document_json
        part.document_json += " "
        check(not owner.apply(context), "Changed working-Part binding invalidates ready Apply")
        check(
            not owner.expectation and not owner.ghost_positions,
            "Invalidated input revokes preview authority",
        )
        part.document_json = before_part
        owner.cancel()
        reap()
        check(
            accepted() == baseline,
            "Rejected changed-input Apply leaves accepted assembly unchanged",
        )
    with viewport() as context:
        owner = watch(source_preview.SourceUpdatePreview(context)).start(context)
        finish(owner, context)
        expected = copy.deepcopy(owner.candidate)
        fingerprint = owner.expectation
        with patch.object(
            assembly_state, "commit_candidate", wraps=assembly_state.commit_candidate
        ) as commit:
            check(
                owner.apply(context),
                "Explicit ready all-instance source Apply succeeds: " + owner.error,
            )
            check(
                not owner.apply(context) and commit.call_count == 1,
                "Source update commits once only",
            )
            check(
                commit.call_args.kwargs["expected_source_preview"] == fingerprint,
                "Fresh commit is bound to exact displayed source projection",
            )
        check(data() == expected, "Canonical publication equals exact preview candidate")
        response = assembly_state.current_display_response(context)
        geometry(response, 2000)
        check(
            response["report"]["base_pose"]["transforms"]
            == initial["report"]["base_pose"]["transforms"],
            "Apply preserves all original instance poses",
        )
        check(
            data()["joints"] == original["joints"],
            "Source update preserves joints and slider coordinates",
        )
        check(
            context.scene.mechanical_cad_assembly.verification_status == "UNCHECKED",
            "Source update does not claim contact verification",
        )
        (OUT / "applied-response.json").write_text(json.dumps(response, indent=2))
    (OUT / "accepted.json").write_text(bpy.context.scene.mechanical_cad_assembly.document_json)
    call(bpy.ops.wm.save_as_mainfile, filepath=str(OUT / "source-update.blend"))
    marker = "SOURCE_UPDATE_PREVIEW_OWNER_OK"
check(not any(key == "OCP" or key.startswith("OCP.") for key in sys.modules), "No OCP in Blender")
(OUT / (MODE + "-checks.json")).write_text(json.dumps(checks, indent=2))
print(marker, len(checks), flush=True)
