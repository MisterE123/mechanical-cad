"""Actual registered OperatorProperties adapter regression; no popup or native CAD.

Run with native Blender --background --factory-startup --python-exit-code 1.
This uses an explicitly declared pure point/line fixture, not GUI-authored
geometry. The separate installed-GUI gate must prove popup and mouse usability.
"""

import gc
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
os.environ["MCAD_ROOT"] = str(ROOT)
sys.path.insert(0, str(ROOT / "blender_addon"))
import mechanical_cad_blender as addon  # noqa: E402
from mechanical_cad_blender import (  # noqa: E402
    document_state,
    execution_lease,
    general_session,
    general_viewport,
    guarded_transport,
    sketch_session,
    workspace,
)
from mechanical_cad_blender.general_sketch_commands import (  # noqa: E402
    AddLine,
    AddPoint,
    PointRef,
    PointSeed,
)

checks = []


def check(value, label):
    assert value, label
    checks.append(label)
    print("POINT_PICKER_RNA_CHECK", len(checks), label, flush=True)


def forbidden(*args, **kwargs):
    raise AssertionError("Enum presentation performed currentness or native work")


def reject(callback, label):
    try:
        result = callback()
    except (TypeError, ValueError, RuntimeError):
        check(True, label)
    else:
        check(result == {"CANCELLED"}, label)


addon.register()
window = bpy.context.window
area = next(item for item in window.screen.areas if item.type == "VIEW_3D")
region = next(item for item in area.regions if item.type == "WINDOW")
window.workspace[workspace.OWNER_KEY] = workspace.OWNER
window.workspace[workspace.ROLE_KEY] = "SKETCH"
owner = None
try:
    with (
        bpy.context.temp_override(window=window, area=area, region=region),
        patch.object(guarded_transport, "GuardedJob", side_effect=forbidden),
    ):
        context = bpy.context
        document_state._populate_document(
            context.scene,
            {
                "schema_version": 1,
                "id": "point_picker_rna_fixture",
                "name": "Declared RNA adapter fixture",
                "units": "mm",
                "parameters": {},
                "features": [],
                "active_feature": None,
            },
        )
        owner = general_session.GeneralSession(context)
        owner.start()
        check(sketch_session.active_session(context) is owner, "Existing lifecycle owns fixture")
        ids = [
            owner.commands.execute(AddPoint(PointSeed(*xy))).entity_ids[0]
            for xy in ((0, 0), (5, 0), (0, 5))
        ]
        line = owner.commands.execute(AddLine(PointRef(ids[0]), PointRef(ids[1]))).entity_ids[0]
        owner.draft.select_tool("Line")
        owner.checkpoint()
        saved = context.scene.mechanical_cad.sketch_draft_json
        first = owner.prepare_gesture("point")
        catalog = first.point_catalog
        props = context.window_manager.operator_properties_last("mcad.use_existing_point")
        check(isinstance(props, bpy.types.OperatorProperties), "Carrier is real OperatorProperties")
        print(
            "POINT_PICKER_RNA_CARRIER",
            type(props).__name__,
            bpy.app.version_string,
            "id_data_type",
            type(props.id_data).__name__,
            "id_data_is_window_manager",
            props.id_data == context.window_manager,
            flush=True,
        )
        check(
            not hasattr(props, "owner") and not hasattr(props, "point_items"),
            "Carrier does not expose Python-only operator state",
        )
        with (
            patch.object(owner, "_backend_current_selection", side_effect=forbidden),
            patch.object(owner, "_require_current", side_effect=forbidden),
        ):
            props.picker_token = catalog.token
            props.point_id = catalog.sentinel
            props.source = "point"
            check(
                props.point_id == catalog.sentinel and props.source == "point",
                "Real RNA accepts explicit no-selection sentinel",
            )
            props.point_id = ids[0]
            props.source = f"line:{line}:start"
            check(props.source == f"line:{line}:start", "Real RNA accepts exact source role")
            props.point_id = ids[1]
            check(props.source == "point", "Real update callback resets source on point change")
            props.source = f"line:{line}:end"
            for _ in range(3):
                gc.collect()
                check(
                    general_viewport._point_items(props, context) is catalog.point_items,
                    "Callback returns the same frozen point tuple after GC",
                )
                check(
                    general_viewport._source_items(props, context) is catalog.source_items[ids[1]],
                    "Callback returns the same retained source strings after GC",
                )
            check(
                general_viewport._point_items(props, None) is general_session.POINT_PICKER_EMPTY,
                "Absent context uses static fallback without guessing an owner",
            )
            foreign = SimpleNamespace(
                window=context.window,
                scene=context.scene,
                area=object(),
                workspace=context.workspace,
                view_layer=context.view_layer,
            )
            check(
                general_viewport._point_items(props, foreign) is general_session.POINT_PICKER_EMPTY,
                "Foreign viewport cannot resolve display catalog",
            )
        owner.cancel_gesture(first)
        check(
            general_viewport._point_items(props, context) is general_session.POINT_PICKER_EMPTY,
            "Cancelled token cannot resolve display catalog",
        )
        reject(lambda: setattr(props, "point_id", ids[0]), "Real RNA rejects retired point choice")
        second = owner.prepare_gesture("point")
        check(second.point_catalog.token != catalog.token, "Reopened dialog has fresh token")
        reject(lambda: setattr(props, "point_id", ids[0]), "Old token cannot reuse new catalog")
        props.picker_token = second.point_catalog.token
        props.point_id = ids[0]
        props.source = "point"
        reject(
            lambda: bpy.ops.mcad.use_existing_point(
                "EXEC_DEFAULT",
                picker_token=second.point_catalog.token,
                point_id=ids[0],
                source="point",
            ),
            "Copied live token cannot admit unprepared registered execute",
        )
        check(owner.gesture_intent is second, "Rejected forged execute preserves original dialog")
        check(
            context.scene.mechanical_cad.sketch_draft_json == saved,
            "RNA presentation and rejection preserve exact authored draft",
        )
        props.picker_token = ""
        owner.cancel_gesture(second)
        check(not execution_lease.is_busy() and owner.pending is None, "No native work started")
finally:
    if owner is not None:
        owner.cleanup()
    addon.unregister()

print("POINT_PICKER_RNA_SMOKE_OK", len(checks), flush=True)
