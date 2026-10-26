"""Source-loaded GUI fixture and read-only observer. All gestures are manual."""

import json
import os
import sys
from pathlib import Path

import bpy
from mathutils import Quaternion, Vector

ROOT = Path(os.environ["MCAD_ROOT"])
OUT = Path(os.environ["MCAD_ARC_OUTPUT"])
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import document_state, register, sketch_session, workspace  # noqa: E402

register()


def watch():
    state = bpy.context.scene.mechanical_cad
    owner = sketch_session.active_session()
    payload = {
        "document": json.loads(state.document_json),
        "status": state.status,
        "error": state.error,
        "draft": state.sketch_draft_json,
        "owner": None,
        "picker": None,
    }
    if owner:
        picker = getattr(owner, "solid_projection_picker", None)
        if picker is not None:
            choice = picker.edge_choice
            payload["picker"] = {
                "message": picker.message,
                "pending": picker.pending is not None,
                "hit": picker.hit,
                "overlap": [(row[1], row[2]["faces"])
                            for row in picker.overlap_candidates],
                "choice": None if choice is None else {
                    "rows": [(source, json.loads(raw)["faces"]) for source, raw in choice.rows],
                    "selected": choice.selected,
                    "released": choice.released,
                    "retired": choice.retired,
                },
            }
        geometry = owner.geometry()
        payload["owner"] = {
            "candidate": owner.commands.candidate(),
            "sketch": owner.commands.sketch,
            "feature_id": owner.commands.feature_id,
            "error": owner.error,
            "message": owner.message,
            "pending": owner.pending is not None,
            "arc_radii": {key: arc.radius_mm for key, arc in geometry.arcs.items()},
        }
    (OUT / "gui-current.json").write_text(json.dumps(payload, indent=2))
    return 0.5


def ready(context):
    bpy.ops.mcad.general_sketch("INVOKE_DEFAULT")
    for obj in context.scene.objects:
        if obj.name == "Cube":
            obj.hide_set(True)
    space = context.area.spaces.active
    rotation = ((1, 0, 0, 0) if os.environ.get("MCAD_ARC_GUI_TOP") else
                (0.880476, 0.279849, -0.115917, -0.364705))
    space.region_3d.view_rotation = Quaternion(rotation)
    space.region_3d.view_perspective = "ORTHO"
    space.region_3d.view_location = Vector((0.01, 0.005, 0.005))
    space.region_3d.view_distance = 0.04
    space.clip_start = 0.00001
    space.show_region_ui = True
    space.overlay.show_floor = False
    space.shading.type = "SOLID"
    print("MCAD_ARC_GUI_READY", flush=True)


def launch():
    if os.environ.get("MCAD_ARC_GUI_REOPEN"):
        bpy.ops.wm.open_mainfile(filepath=os.environ["MCAD_ARC_GUI_REOPEN"])
    else:
        source = json.loads((ROOT / "tests/fixtures/solid_arc_projection/source.json").read_text())
        document_state._populate_document(bpy.context.scene, source)
        document_state.regenerate(bpy.context)
        workspace.request_workspace(bpy.context, "SKETCH", on_ready=ready)
    bpy.app.timers.register(watch, first_interval=0.5)


bpy.app.timers.register(launch, first_interval=1)
