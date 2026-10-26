"""Native owner/adapter sector authoring; manual installed pointer use is separate.

Starts from a blank Part and uses the same bound gesture/point adapters as UI.
No saved native evidence or prepared geometry fixture supplies the positive path.
"""

import copy
import json
import math
import os
import struct
import sys
import time
from pathlib import Path
from unittest.mock import patch

import bpy

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
os.environ["MCAD_ROOT"] = str(ROOT)
sys.path.insert(0, str(ROOT / "blender_addon"))
import mechanical_cad_blender as addon  # noqa: E402
from mechanical_cad_blender import (  # noqa: E402
    document_state as doc,
)
from mechanical_cad_blender import (  # noqa: E402
    draft_dispatch,
    execution_lease,
    general_session,
    guarded_transport,
    sketch_session,
    viewport_sketch,
    workspace,
    workspace_ui,
)
from mechanical_cad_blender.general_sketch_commands import (  # noqa: E402
    AddRelation,
    PointRef,
    PointSeed,
)

checks = []


def check(value, label):
    assert value, label
    checks.append(label)
    print("ARC_EDITOR_CHECK", len(checks), label, flush=True)


def wait(owner, context):
    deadline = time.monotonic() + 60
    while owner.pending is not None and time.monotonic() < deadline:
        owner.tick(context)
        time.sleep(0.01)
    check(owner.pending is None and not execution_lease.is_busy(), "Native work is collected")
    check(not owner.error, "Real editor operation succeeded: " + owner.error)


def rejects(callback, label):
    try:
        callback()
    except (ValueError, RuntimeError):
        check(True, label)
    else:
        raise AssertionError(label)


def shape(document):
    source = document["features"][0]["sketch"]
    return copy.deepcopy({key: source[key] for key in ("points", "lines", "circles", "arcs")})


def current_volume(context):
    result = doc.current_part_result(context)
    assert result is not None, "Volume requires current guarded native evidence"
    volume = result["features"][1]["stats"]["volume"]
    display_volume = context.scene.mechanical_cad.volume
    print("ARC_EDITOR_VOLUME", json.dumps({"native": volume, "rna": display_volume}), flush=True)
    check(
        display_volume == struct.unpack("f", struct.pack("f", volume))[0],
        "RNA volume is the exact float32 presentation of current native volume",
    )
    return volume


def exact_point(owner, context, identifier, phase, arc, role):
    binding = owner.prepare_gesture("point")
    result = owner.accept_point_input(
        context,
        PointRef(identifier),
        expected_phase=phase,
        source_kind="arc",
        source_id=arc,
        role=role,
        picker=binding,
    )
    check(not owner.proposal_capture, "Exact point selection never restores pointer capture")
    rejects(
        lambda: owner.accept_point_input(
            context, PointRef(identifier), expected_phase=phase, picker=binding
        ),
        "The exact point confirmation is once-only",
    )
    return result


addon.register()
window = bpy.context.window
area = next(item for item in window.screen.areas if item.type == "VIEW_3D")
region = next(item for item in area.regions if item.type == "WINDOW")
window.workspace[workspace.OWNER_KEY] = workspace.OWNER
window.workspace[workspace.ROLE_KEY] = "SKETCH"
with bpy.context.temp_override(window=window, area=area, region=region):
    context = bpy.context
    doc._populate_document(
        context.scene,
        {
            "schema_version": 1,
            "id": "arc_editor_blank",
            "name": "Arc editor native adapter",
            "units": "mm",
            "parameters": {},
            "features": [],
            "active_feature": None,
        },
    )
    state = context.scene.mechanical_cad
    canonical_before = state.document_json
    owner = general_session.GeneralSession(context)
    owner.start()
    initial_slot = state.sketch_draft_json
    initial_sketch = copy.deepcopy(owner.commands.sketch)
    cancelled = owner.prepare_gesture("arc")
    owner.cancel_gesture(cancelled)
    check(state.sketch_draft_json == initial_slot, "Opt-in cancellation keeps exact saved bytes")
    check(owner.commands.sketch == initial_sketch, "Opt-in cancellation keeps authored geometry")
    with patch.object(
        guarded_transport, "GuardedJob", side_effect=AssertionError("Unexpected native work")
    ):
        binding = owner.prepare_gesture("arc")
        owner.enable_arc(binding)
        check(
            draft_dispatch.inspect(state.sketch_draft_json).schema_version == 3,
            "Explicit opt-in writes envelope3",
        )
        check(
            owner.commands.sketch == initial_sketch, "Opt-in alone does not migrate model geometry"
        )
        owner.accept_point_input(context, PointSeed(0, 0), expected_phase=("arc", "center"))
        owner.accept_point_input(context, PointSeed(5, 0), expected_phase=("arc", "start"))
        check(not owner.commands.sketch["points"], "Two initial inputs allocate no point IDs")
        owner.draft.observe_arc(PointSeed(0, 6))
        owner.checkpoint()
        check(
            owner.draft.proposal["observation"]["position"] == [0, 6],
            "Off-circle observed seed is kept without projection",
        )
    owner.accept_point_input(context, PointSeed(0, 5), expected_phase=("arc", "end"))
    wait(owner, context)
    arc = owner.commands.sketch["arcs"][0]
    arc_id = arc["id"]
    center, start, end = (arc[key] for key in ("center", "start", "end"))
    authored_points = copy.deepcopy(owner.commands.sketch["points"])
    check(owner.commands.sketch["schema_version"] == 3, "One accepted AddArc migrates geometry")
    check(
        len(authored_points) == 3 and len({center, start, end}) == 3,
        "Center/start/end have distinct stable IDs",
    )
    check(not owner.can_finish, "Open arc solves but cannot Finish as a sector")
    check(state.document_json == canonical_before, "Draft authoring has not committed the Part")

    check(
        bpy.ops.mcad.general_tool(tool="Line") == {"FINISHED"},
        "Registered Line action selects tool",
    )
    exact_point(owner, context, center, ("line", "start"), arc_id, "center")
    exact_point(owner, context, start, ("line", "end"), arc_id, "start")
    wait(owner, context)
    exact_point(owner, context, center, ("line", "start"), arc_id, "center")
    exact_point(owner, context, end, ("line", "end"), arc_id, "end")
    wait(owner, context)
    sketch = owner.commands.sketch
    check(
        sketch["points"] == authored_points, "Radial lines reuse exact existing point IDs and seeds"
    )
    check(len(sketch["lines"]) == 2, "Exactly two radial lines accepted")
    check(
        not owner.can_use_tool("Line")
        and not owner.can_use_tool("Arc")
        and not owner.can_use_tool("Circle"),
        "Bounded tools refuse third line, second arc and full circle",
    )
    lines = {line["end"]: line["id"] for line in sketch["lines"]}
    for command in (
        AddRelation("fixed", (center,), target=(0, 0)),
        AddRelation("horizontal", (lines[start],)),
        AddRelation("vertical", (lines[end],)),
    ):
        owner.execute(context, command)
        wait(owner, context)
    outcome = owner.execute(
        context, AddRelation("radius", (arc_id,), value=5), annotation_offset=(6, 6)
    )
    radius_id = outcome.constraint_id
    wait(owner, context)
    response = owner.current_solution_response()
    check(
        response["result"]["sketch"]["remaining_dof"] == 0,
        "Explicit fixed/H/V/radius gives genuine zero DoF",
    )
    check(owner.can_finish, "The checked shared-ID sector is ready to Finish")
    saved_shape = shape(owner.commands.candidate())
    owner.draft.select((("arc", arc_id),))
    owner.checkpoint()
    reverse = owner.prepare_gesture("reverse")
    owner.reverse_arc(context, reverse)
    wait(owner, context)
    check(
        owner.commands.sketch["arcs"][0]["direction"] == "cw",
        "Reverse changes only authored direction",
    )
    check(
        owner.commands.sketch["points"] == authored_points, "Reverse preserves exact endpoint seeds"
    )
    owner.local_history(context)
    wait(owner, context)
    check(
        shape(owner.commands.candidate()) == saved_shape, "Undo restores original directed sector"
    )
    owner.local_history(context, redo=True)
    wait(owner, context)
    check(
        owner.commands.sketch["arcs"][0]["direction"] == "cw",
        "Redo keeps stable arc identity and complementary branch",
    )
    owner.local_history(context)
    wait(owner, context)
    feature_id = owner.commands.feature_id
    owner.request_finish(context)
    wait(owner, context)
    check(
        owner.finished and sketch_session.active_session() is None,
        "Fresh Finish publishes and closes the shared owner",
    )
    check(doc.part_is_current(context), "Finished profile has current guarded evidence")
    check(bool(state.sketch_annotation_json), "Accepted radius layout persists separately")
    check(bpy.ops.mcad.add_extrude.poll(), "First sole extrusion is visibly available")
    check(
        bpy.ops.mcad.add_extrude(profile=feature_id, length=10) == {"FINISHED"},
        "Existing Extrude operator builds the new sector",
    )
    check(
        math.isclose(current_volume(context), 196.34954084936206, abs_tol=1e-10),
        "Drawn radius5 sector has qualified native volume",
    )
    check(not bpy.ops.mcad.add_extrude.poll(), "Second extrusion is visibly unavailable")
    check(workspace_ui.available(context, "EXPORT"), "Eligible sector export is visibly available")
    check(bpy.ops.mcad.check_geometry.poll(), "Eligible sector Geometry Check is available")
    check(
        not doc.geometry_report_is_current(context),
        "Replay is never labeled Geometry Check authority",
    )
    before = doc._read_document(state)
    state.feature_index = next(
        index for index, row in enumerate(state.features) if row.feature_id == feature_id
    )
    check(
        viewport_sketch._selected_editor(state) == "mcad.general_sketch",
        "Schema3 Edit routes to General",
    )
    owner = general_session.GeneralSession(context, feature_id)
    owner.start()
    owner.check(context)
    wait(owner, context)
    owner.begin_dimension(radius_id)
    owner.update_raw(" 7 + 0 ")
    owner.request_driver_accept(context)
    wait(owner, context)
    check(
        shape(owner.commands.candidate()) == shape(before),
        "Radius edit preserves exact authored seeds and IDs",
    )
    owner.request_finish(context)
    wait(owner, context)
    check(
        math.isclose(current_volume(context), 384.84510006474966, abs_tol=1e-10),
        "Same sector and sole extrusion rebuild at radius7",
    )
    after = doc._read_document(state)
    check(
        [item["id"] for item in after["features"]] == [item["id"] for item in before["features"]],
        "Radius edit keeps the same feature identities",
    )
    if os.environ.get("MCAD_ARC_EDITOR_EVIDENCE"):
        directory = Path(os.environ["MCAD_ARC_EDITOR_EVIDENCE"])
        directory.mkdir(parents=True, exist_ok=False)
        (directory / "drawn-sector-radius7.mcad.json").write_text(state.document_json)
        (directory / "radius-layout.json").write_text(state.sketch_annotation_json)
        (directory / "checks.json").write_text(json.dumps(checks, indent=2) + "\n")
    check(not execution_lease.is_busy(), "No native work leaks from editor workflow")
check(
    not any(name == "OCP" or name.startswith("OCP.") or name == "slvs" for name in sys.modules),
    "Native CAD remains outside Blender",
)
addon.unregister()
print("ARC_EDITOR_SMOKE_OK", len(checks))
