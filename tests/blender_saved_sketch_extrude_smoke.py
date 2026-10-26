"""Native selected-sketch replay/readiness and existing Extrude apply path.

Background Blender plus native sidecar; does not certify interactive dialog UX.
"""
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy

ROOT = Path(os.environ["MCAD_ROOT"])
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import document_state, register, unregister, workspace_ui  # noqa: E402
from mechanical_cad_blender.feature_history_draw import capture_presentation  # noqa: E402

register()
state = bpy.context.scene.mechanical_cad


class Layout:
    def __init__(self):
        self.enabled = True
        self.buttons = []
        self.labels = []

    def row(self, **kwargs):
        return self

    def operator(self, name, **kwargs):
        op = SimpleNamespace(name=name, enabled=self.enabled)
        self.buttons.append(op)
        return op

    def label(self, **kwargs):
        self.labels.append(kwargs["text"])


def show():
    layout = Layout()
    area = next(area for area in bpy.context.screen.areas if area.type == "VIEW_3D")
    region = next(region for region in area.regions if region.type == "WINDOW")
    with bpy.context.temp_override(area=area, region=region), patch.object(workspace_ui, "available", return_value=bpy.ops.mcad.add_extrude.poll()):
        workspace_ui._draw_selected_sketch_extrude(layout, bpy.context, capture_presentation(bpy.context))
    return layout


def load(name):
    document = json.loads((ROOT / "examples" / name).read_text())
    # Keep the authored saved sketch only, with its existing stable identity.
    document["parameters"].pop("extrude_1_length", None)
    document["features"] = document["features"][:1]
    document["active_feature"] = document["features"][0]["id"]
    document_state._populate_document(bpy.context.scene, document)
    assert bpy.ops.mcad.regenerate() == {"FINISHED"}
    assert state.status == "READY", state.error
    state.feature_index = 0
    return document


original = load("viewport_rectangle.mcad.json")
before = state.document_json
layout = show()
assert layout.buttons[0].enabled and "Closed profile available" in layout.labels
assert layout.buttons[0].profile == original["features"][0]["id"]
assert state.document_json == before
# Dispatch exactly the existing operator and profile offered by the contextual UI.
button = layout.buttons[0]
assert bpy.ops.mcad.add_extrude(profile=button.profile, length=10) == {"FINISHED"}
assert state.status == "READY" and abs(state.volume - 12000) < 1e-5
current = json.loads(state.document_json)
assert current["features"][0] == original["features"][0]
assert current["features"][-1]["inputs"]["profile"] == button.profile
assert current["active_feature"] == current["features"][-1]["id"]
# A retained stale cache must not advertise a ready profile.
state.feature_index = 0
state.document_json += " "
layout = show()
assert not layout.buttons[0].enabled and any("Rebuild" in text for text in layout.labels)
load("open_line_sketch.mcad.json")
layout = show()
assert not layout.buttons[0].enabled
assert any("Close" in text or "open" in text.lower() for text in layout.labels), layout.labels
unregister()
print("SAVED_SKETCH_EXTRUDE_SMOKE_OK", flush=True)
