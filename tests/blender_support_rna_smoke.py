"""Exercise Review Support's actual Blender RNA enum lifecycle.

MCAD_ROOT=<repo> MCAD_PYTHON=<sidecar-python> PYTHONPATH=<repo>/src \
  blender --background --factory-startup --python-exit-code 1 \
  --python tests/blender_support_rna_smoke.py

Background Blender routes INVOKE_DEFAULT to execute, so a registered execute
trampoline calls the unchanged invoke body. Only the final dialog presentation
is intercepted. Operator, OperatorProperties, enum callbacks/updates, guarded
replay and Apply/Cancel are real Blender paths, not a SimpleNamespace owner.
This is not mouse, dialog drawing or Undo qualification.
"""

import copy
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import bpy

if not bpy.app.background:
    raise RuntimeError("Run in an isolated background Blender")
root = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(root / "blender_addon"))
import mechanical_cad_blender as addon  # noqa: E402
from mechanical_cad_blender import document_state  # noqa: E402
from mechanical_cad_blender import support_intent_ui as ui  # noqa: E402


class DialogContext:
    def __getattr__(self, key):
        return getattr(bpy.context, key)

    window_manager = SimpleNamespace(invoke_props_dialog=lambda *a, **k: {"RUNNING_MODAL"})


original_execute = ui.MCAD_OT_edit_sketch_support.execute
checks = []
mode = "cancel"


def exercise(self, context):
    original_json = context.scene.mechanical_cad.document_json
    assert isinstance(self, bpy.types.Operator)
    assert isinstance(self.properties, bpy.types.OperatorProperties)
    assert ui.MCAD_OT_edit_sketch_support.invoke(self, DialogContext(), None) == {"RUNNING_MODAL"}
    assert self.support_source == "slotted"
    assert self.support_face == "block/face/cap.end"
    assert "slotted" in {item[0] for item in ui._sources(self.properties, context)}
    if example.startswith("minimal_twist"):
        assert self.orientation == "MINIMAL_TWIST"
    else:
        saved_label = next(
            item[1] for item in ui._faces(self.properties, context) if item[0] == self.support_face
        )
        assert saved_label == "Saved logical support"
        strict = copy.deepcopy(self._document)
        attached = next(f for f in strict["features"] if f["id"] == self.feature_id)
        attached.pop("support_intent")
        strict_label = next(
            item[1]
            for item in ui._face_items(
                strict, self.feature_id, self._review_result, self.support_source
            )
            if item[0] == self.support_face
        )
        assert strict_label == "Saved support (needs review)"
    # The RNA callback wrapper deliberately does not have invoke's Python attrs.
    assert not hasattr(self.properties, "_document")
    if mode == "cancel":
        self.support_source = "block"
        assert self.support_face in {item[0] for item in ui._faces(self.properties, context)}
        self.support_face = "block/face/cap.end"
        self.support_source = "slotted"
        self.support_face = "block/face/cap.end"
        self.orientation = "WORLD_AXES"
        ui.MCAD_OT_edit_sketch_support.cancel(self, context)
        assert self._review_evidence is None
        assert context.scene.mechanical_cad.document_json == original_json
        checks.append(
            "Real RNA invoke and source/face callbacks; changed selection Cancel is atomic"
        )
        return {"CANCELLED"}
    assert original_execute(self, context) == {"FINISHED"}
    assert self._review_evidence is None
    assert context.scene.mechanical_cad.document_json == original_json
    checks.append("Fresh RNA invoke and unchanged Apply preserve canonical intent")
    return {"FINISHED"}


ui.MCAD_OT_edit_sketch_support.execute = exercise
addon.register()
for example in ("minimal_twist_after", "minimal_twist_before", "split_plane_preserved"):
    document = json.loads((root / f"examples/topology_support/{example}.mcad.json").read_text())
    assert document_state._commit_candidate(bpy.context, document)
    for mode in ("cancel", "apply"):
        expected = {"CANCELLED"} if mode == "cancel" else {"FINISHED"}
        assert bpy.ops.mcad.edit_sketch_support("EXEC_DEFAULT", feature_id="attached") == expected
print("MCAD_SUPPORT_RNA_RESULT=" + json.dumps({"ok": True, "checks": checks}))
