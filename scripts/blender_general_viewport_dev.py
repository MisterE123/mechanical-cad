"""Isolated QA launcher for the production general-sketch entry points.

Launch factory-startup in a distinct QA profile. Normal add-on registration owns
all operators. No geometry is scripted; use the actual viewport and CAD palette.
"""

import json
import os
import sys
from pathlib import Path

import bpy
from mathutils import Quaternion, Vector

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT.parent / "cad_engineering_evidence/general_viewport_gui"
EVIDENCE.mkdir(parents=True, exist_ok=True)
os.environ["MCAD_ROOT"] = str(ROOT)
os.environ["MCAD_PYTHON"] = str(ROOT / ".venv/bin/python")
sys.path.insert(0, str(ROOT / "blender_addon"))
import mechanical_cad_blender as addon  # noqa: E402
from mechanical_cad_blender import (  # noqa: E402
    document_state,
    general_viewport,
    sketch_session,
    workspace,
)

addon.register()


def ready(context):
    area = context.area
    space = area.spaces.active
    space.region_3d.view_rotation = Quaternion((1, 0, 0, 0))
    space.region_3d.view_perspective = "ORTHO"
    space.region_3d.view_location = Vector((0, 0, 0))
    space.region_3d.view_distance = 0.1
    space.clip_start = 0.00001
    space.show_region_ui = True
    space.overlay.show_floor = False
    space.overlay.show_axis_x = False
    space.overlay.show_axis_y = False
    for region in area.regions:
        if region.type == "UI":
            try:
                region.active_panel_category = "CAD"
            except (AttributeError, RuntimeError):
                # Background/initial-layout contexts expose this as read-only.
                # The CAD panel remains available without forcing tab selection.
                pass
    # Already inside the staged ready callback: start the registered viewport
    # operator directly, rather than enqueue another request on the same job.
    bpy.ops.mcad.general_sketch("INVOKE_DEFAULT")
    print("GENERAL_VIEWPORT_DEVELOPMENT_READY", flush=True)


def launch():
    context = bpy.context
    document_state._populate_document(
        context.scene,
        {
            "schema_version": 1,
            "id": "general_gui",
            "name": "Line and Circle QA",
            "units": "mm",
            "parameters": {"radius": 5},
            "features": [],
            "active_feature": None,
        },
    )
    workspace.request_workspace(context, "SKETCH", on_ready=ready)
    return None


def receipt():
    try:
        owner = sketch_session.active_session()
        state = bpy.context.scene.mechanical_cad
        data = {
            "blender": bpy.app.version_string,
            "status": state.status,
            "document": state.document_json,
            "saved_draft": state.sketch_draft_json,
            "filepath": bpy.data.filepath,
            "volume": state.volume,
        }
        if owner is not None and type(owner) is general_viewport.GeneralSession:
            data["owner"] = {
                "alive": owner.alive,
                "kind": "general",
                "error": owner.error,
                "message": owner.message,
                "intent": owner.draft.checkpoint_payload()
                if hasattr(owner.draft, "checkpoint_payload")
                else owner.draft.command_draft.checkpoint_payload(),
                "ui": owner.draft.ui_payload(),
                "pending": owner.pending_kind,
                "current_solution": owner.commands.has_current_solution,
                "input": owner.input_controller.snapshot() if owner.input_controller else None,
            }
        (EVIDENCE / "state.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception as exc:
        print("General GUI receipt:", str(exc), flush=True)
    return 0.5


bpy.app.timers.register(launch, first_interval=0.5)
bpy.app.timers.register(receipt, first_interval=1.0)
