"""Native Blender operator routing; dialog adapter does not claim GUI usability."""

import copy
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import bpy

ROOT = Path(os.environ["MCAD_ROOT"])
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import (  # noqa: E402
    constraint_ui,
    document_state,
    general_session,
    register,
    unregister,
)
from mechanical_cad_blender.general_sketch_commands import AddCircle, AddLine, PointSeed  # noqa: E402


def wait(owner, context):
    until = time.monotonic() + 30
    while owner.pending and time.monotonic() < until:
        owner.tick(context)
        time.sleep(0.01)
    assert not owner.pending and not owner.error, owner.error


def numeric(owner, context, mode, value):
    operator = SimpleNamespace(mode=mode, reports=[])
    operator.report = lambda level, message: operator.reports.append(message)
    proxy = SimpleNamespace(
        window=context.window,
        scene=context.scene,
        area=context.area,
        workspace=context.workspace,
        view_layer=context.view_layer,
        window_manager=SimpleNamespace(invoke_props_dialog=lambda op: {"RUNNING_MODAL"}),
    )
    cls = constraint_ui.MCAD_OT_sketch_numeric_relation
    assert cls.invoke(operator, proxy, None) == {"RUNNING_MODAL"}, operator.reports
    operator.value = value
    assert cls.execute(operator, context) == {"FINISHED"}, operator.reports
    wait(owner, context)


register()
# Inspect registered RNA and both draw paths without claiming pixel-level GUI QA.
numeric_class = constraint_ui.MCAD_OT_sketch_numeric_relation
value_property = bpy.ops.mcad.sketch_numeric_relation.get_rna_type().properties["value"]
assert value_property.name == "Value"
assert "mm/cm/m/in/ft" in value_property.description
assert "deg/rad" in value_property.description
assert "formulas keep existing units" in value_property.description
for mode in ("ANGLE", "DIAMETER"):
    labels, fields = [], []
    layout = SimpleNamespace(
        label=lambda *, text, labels=labels: labels.append(text),
        prop=lambda operator, field, fields=fields: fields.append(field),
    )
    numeric_class.draw(SimpleNamespace(mode=mode, layout=layout), None)
    assert fields == ["value"]
    assert all(len(label) <= 38 for label in labels), labels
    copy_text = " ".join(labels)
    assert "Apply solves the draft; incompatible values remain recoverable." in copy_text
    if mode == "DIAMETER":
        assert labels[0] == "Diameter (mm)"
        assert "Stored as a driving radius = diameter / 2." in copy_text
    else:
        assert labels[0] == "Angle (degrees, >0 to 180)"
        assert "driving radius" not in copy_text
window = bpy.context.window
area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
region = next(r for r in area.regions if r.type == "WINDOW")
with bpy.context.temp_override(window=window, area=area, region=region):
    context = bpy.context
    document_state._populate_document(
        context.scene,
        {
            "schema_version": 1,
            "id": "doc",
            "name": "Part",
            "units": "mm",
            "parameters": {},
            "features": [],
            "active_feature": None,
        },
    )
    owner = general_session.GeneralSession(context)
    owner.start()
    first = owner.execute(context, AddLine(PointSeed(0, 0), PointSeed(10, 0))).entity_ids[-1]
    wait(owner, context)
    second = owner.execute(context, AddLine(PointSeed(0, 5), PointSeed(10, 8))).entity_ids[-1]
    wait(owner, context)
    constraint_ui.select_bindings(owner, (("line", first), ("line", second)), context=context)
    numeric(owner, context, "ANGLE", "60")
    angle = next(c for c in owner.commands.sketch["constraints"] if c["kind"] == "angle")
    constraint_ui.select_bindings(owner, (("constraint", angle["id"]),), context=context)
    numeric(owner, context, "ANGLE", "45")
    constraint_ui.select_bindings(owner, (("line", first), ("line", second)), context=context)
    assert bpy.ops.mcad.sketch_construction("EXEC_DEFAULT") == {"FINISHED"}
    wait(owner, context)
    assert all(line["construction"] for line in owner.commands.sketch["lines"])
    circle = owner.execute(context, AddCircle(PointSeed(30, 0), 5)).entity_ids[-1]
    wait(owner, context)
    constraint_ui.select_bindings(owner, (("circle", circle),), context=context)
    numeric(owner, context, "DIAMETER", "24")
    assert (
        owner.current_solution_response()["result"]["sketch"]["solved"]["circles"][0]["radius"]
        == 12
    )
    numeric(owner, context, "DIAMETER", "30")
    assert (
        owner.current_solution_response()["result"]["sketch"]["solved"]["circles"][0]["radius"]
        == 15
    )
    from mechanical_cad_blender import general_sketch_overlay as overlay

    geometry = owner.geometry()
    frame = overlay.build_frame(
        geometry,
        lambda world: (world[0] * 10, world[1] * 10),
        current_request_fingerprint=geometry.request_fingerprint,
        annotations=owner.draft.annotations,
    )
    assert any(stroke.construction and len(stroke.segments) > 1 for stroke in frame.strokes)
    angle_label = next(label for label in frame.labels if label.kind == "angle")
    assert "°" in angle_label.text and "mm" not in angle_label.text
    assert abs(angle_label.measured_mm - 45) < 1e-6
    assert not frame.unavailable, frame.unavailable
    from mechanical_cad_blender.general_sketch_commands import AddArc

    before_arc = copy.deepcopy(owner.commands.sketch)
    before_revision = owner.commands.revision
    assert owner.draft.ui_version == 1
    assert bpy.ops.mcad.general_tool("EXEC_DEFAULT", tool="Arc") == {"FINISHED"}
    assert owner.draft.ui_version == 2 and owner.draft.tool == "Arc"
    assert owner.commands.sketch == before_arc and owner.commands.revision == before_revision
    owner.execute(context, AddArc(PointSeed(50, 50), PointSeed(55, 50), PointSeed(50, 55), "ccw"))
    wait(owner, context)
    assert owner.commands.sketch["schema_version"] == 3 and len(owner.commands.sketch["arcs"]) == 1
    assert bpy.ops.mcad.constraint_history("EXEC_DEFAULT", direction="UNDO") == {"FINISHED"}
    wait(owner, context)
    assert owner.commands.sketch == before_arc
    assert bpy.ops.mcad.constraint_history("EXEC_DEFAULT", direction="REDO") == {"FINISHED"}
    wait(owner, context)
    assert owner.commands.sketch["schema_version"] == 3
    owner.cleanup()
unregister()
print("CONSTRUCTION_DIMENSION_SMOKE_OK")
