"""Launch an ordinary interactive sketch for manual fractional-input QA.

Requires MCAD_ROOT and MCAD_FRACTION_GUI_OUTPUT. Does not simulate clicks or
claim GUI qualification: the operator must interact and capture observations.
Optional MCAD_FRACTION_GUI_BLEND opens a saved .blend; use Resume in the UI.
"""
import json
import math
import os
import sys
from pathlib import Path

import bpy
from mathutils import Quaternion, Vector

ROOT = Path(os.environ["MCAD_ROOT"])
OUT = Path(os.environ["MCAD_FRACTION_GUI_OUTPUT"])
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import document_state, register, sketch_session, workspace  # noqa: E402

register()


def watch():
    owner = sketch_session.active_session()
    if owner:
        geometry = owner.geometry()
        payload = {
            "source": geometry.source, "proposal": owner.draft.proposal,
            "pending_length": owner.draft.pending_length,
            "pending_diameter": owner.draft.pending_diameter,
            "sketch": owner.commands.sketch, "error": owner.error, "message": owner.message,
            "native_pending": owner.pending is not None,
            "input_active": bool(owner.input_controller and not owner.input_controller.closed),
            "line_lengths_mm": {key: math.dist(value.start_mm, value.end_mm)
                                for key, value in geometry.lines.items()},
            "circle_radii_mm": {key: value.radius_mm for key, value in geometry.circles.items()},
        }
        (OUT / "current.json").write_text(json.dumps(payload, indent=2))
    return .3


def ready(context):
    space = context.area.spaces.active
    space.region_3d.view_rotation = Quaternion((1, 0, 0, 0))
    space.region_3d.view_perspective = "ORTHO"
    space.region_3d.view_location = Vector((0, 0, 0))
    space.region_3d.view_distance = .05
    space.clip_start = .00001
    space.show_region_ui = True
    space.overlay.show_floor = False
    bpy.ops.mcad.general_sketch("INVOKE_DEFAULT")
    print("FRACTION_GUI_READY", flush=True)


def launch():
    saved = os.environ.get("MCAD_FRACTION_GUI_BLEND")
    if saved:
        bpy.ops.wm.open_mainfile(filepath=saved)
    else:
        document_state._populate_document(bpy.context.scene, {
            "schema_version": 1, "id": "fraction_gui", "name": "Fraction input QA", "units": "mm",
            "parameters": {"width": 8}, "features": [], "active_feature": None,
        })
        workspace.request_workspace(bpy.context, "SKETCH", on_ready=ready)
    bpy.app.timers.register(watch, first_interval=.3)


bpy.app.timers.register(launch, first_interval=1)
