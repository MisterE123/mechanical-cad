"""Native support review and two-process persistence; not mouse/Undo GUI qualification.

Create:
  MCAD_ROOT=<repo> MCAD_PYTHON=<sidecar-python> PYTHONPATH=<repo>/src \
  blender --background --factory-startup --python-exit-code 1 \
  --python tests/blender_support_intent_smoke.py -- --blend <output.blend>
Reopen in a separate process:
  (same environment) blender --background <output.blend> --python-exit-code 1 \
  --python tests/blender_support_intent_smoke.py -- --blend <output.blend> --verify-reopen

Dialog opening and layout use a bounded harness, while registration, guarded
backend replay, canonical publication and file persistence use native Blender.
"""

import argparse
import json
import os
import sys
from pathlib import Path
from types import MethodType, SimpleNamespace

import bpy

if not bpy.app.background:
    raise RuntimeError("Use an isolated native Blender background process")
root = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(root / "blender_addon"))
import mechanical_cad_blender as addon  # noqa: E402
from mechanical_cad_blender import document_state, support_intent_ui  # noqa: E402
from mechanical_cad_blender.support_intent_edit import support_decision  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("--blend", required=True, type=Path)
parser.add_argument("--verify-reopen", action="store_true")
args = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else [])
addon.register()
assert bpy.ops.mcad.edit_sketch_support.get_rna_type()
state = bpy.context.scene.mechanical_cad
checks = []

ASSUMED = {
    "active_feature": "boss",
    "features": [
        {
            "id": "footprint",
            "inputs": {},
            "kind": "sketch_rectangle",
            "label": "Footprint",
            "params": {"height": 20, "width": 20, "x": 0, "y": 0, "z": 0},
        },
        {
            "id": "block",
            "inputs": {"profile": "footprint"},
            "kind": "extrude",
            "label": "Block",
            "params": {"length": "depth"},
        },
        {
            "id": "slot_profile",
            "inputs": {},
            "kind": "sketch_rectangle",
            "label": "slot_profile",
            "params": {"height": 22, "width": 2, "x": 9, "y": -1, "z": 7},
        },
        {
            "id": "slot_tool",
            "inputs": {"profile": "slot_profile"},
            "kind": "extrude",
            "label": "slot_tool",
            "params": {"length": 5},
        },
        {
            "id": "slotted",
            "inputs": {"base": "block", "tool": "slot_tool"},
            "kind": "cut",
            "label": "slotted",
            "params": {},
        },
        {
            "id": "attached",
            "inputs": {"support": "slotted"},
            "kind": "sketch_constrained",
            "label": "Drawn face sketch",
            "params": {},
            "sketch": {
                "circles": [{"center": "center", "id": "circle", "radius": 2.0}],
                "constraints": [
                    {
                        "id": "anchor",
                        "kind": "fixed",
                        "refs": ["center"],
                        "target": [0.0, 0.0],
                        "value": None,
                    },
                    {
                        "id": "size",
                        "kind": "radius",
                        "refs": ["circle"],
                        "target": None,
                        "value": 2.0,
                    },
                ],
                "id": "drawn",
                "lines": [],
                "plane": {
                    "id": "workplane",
                    "origin": [0.0, 0.0, 0.0],
                    "quaternion": [1.0, 0.0, 0.0, 0.0],
                },
                "points": [{"id": "center", "u": 0.0, "v": 0.0}],
                "schema_version": 2,
                "units": "mm",
            },
            "support_face": "block/face/cap.end",
            "support_intent": {
                "policy": "preserve_plane",
                "signature": {
                    "area": 400,
                    "centroid": [10, 10, 10],
                    "normal": [0, 0, 1],
                    "surface": "plane",
                },
                "version": 1,
            },
        },
        {
            "id": "boss",
            "inputs": {"profile": "attached"},
            "kind": "extrude",
            "label": "boss",
            "params": {"length": 2},
        },
    ],
    "id": "d",
    "name": "Attached constrained pocket",
    "parameters": {"depth": 10},
    "schema_version": 2,
    "units": "mm",
}


class Context:
    def __getattr__(self, key):
        return getattr(bpy.context, key)

    window_manager = SimpleNamespace(invoke_props_dialog=lambda *a, **k: {"RUNNING_MODAL"})


class Layout:
    def __init__(self):
        self.labels = []
        self.properties = []

    def label(self, *, text="", **kwargs):
        self.labels.append(text)

    def prop(self, _operator, name, **kwargs):
        self.properties.append(name)

    def box(self):
        return self

    def row(self, **kwargs):
        return self


def review():
    operator = SimpleNamespace(
        feature_id="attached",
        original_json="",
        show_help=False,
        help_page=1,
        help_topic="sketch.support_intent",
        help_summary=("Help", "Undo"),
        layout=Layout(),
    )
    operator.report = lambda levels, text: print("UI_REPORT", levels, text)
    for name in ("_release", "_review"):
        setattr(
            operator,
            name,
            MethodType(getattr(support_intent_ui.MCAD_OT_edit_sketch_support, name), operator),
        )
    outcome = support_intent_ui.MCAD_OT_edit_sketch_support.invoke(operator, Context(), None)
    assert outcome == {"RUNNING_MODAL"}, outcome
    return operator


if args.verify_reopen:
    assert state.document_json == state["support_smoke_expected_json"]
    assert document_state.current_part_result(bpy.context) is None
    assert document_state.regenerate(bpy.context), state.error
    result = document_state.current_part_result(bpy.context)
    feature = json.loads(state.document_json)["features"][-2]
    assert support_decision(feature, result)["status"] == "assumed"
    assert feature["support_intent"]["source_signature"]["centroid"] == [10, 10, 10]
    assert feature["support_intent"]["orientation"] == {
        "policy": "minimal_twist",
        "tangent": [1, 0, 0],
    }
    checks.append(
        "Separate Blender process reopened exact canonical support; fresh replay proves assumption"
    )
else:
    assert document_state._commit_candidate(bpy.context, ASSUMED)
    assert state.status == "READY"
    original = state.document_json
    operator = review()
    assert state.document_json == original
    assert operator.orientation == "WORLD_AXES" and not operator.reset_frame
    assert (
        support_decision(operator._document["features"][-2], operator._review_result)["status"]
        == "assumed"
    )
    support_intent_ui.MCAD_OT_edit_sketch_support.draw(operator, bpy.context)
    assert any("ASSUMPTION" in line for line in operator.layout.labels)
    assert any("Undo" in line for line in operator.layout.labels)
    assert "orientation" in operator.layout.properties
    checks.append("registered; current assumption disclosed without canonical mutation")
    operator.orientation = "MINIMAL_TWIST"
    operator.reset_frame = True
    support_intent_ui.MCAD_OT_edit_sketch_support.draw(operator, bpy.context)
    assert "reset_frame" in operator.layout.properties
    assert any("rotate or move" in line for line in operator.layout.labels)
    support_intent_ui.MCAD_OT_edit_sketch_support.cancel(operator, bpy.context)
    assert state.document_json == original and operator._review_evidence is None
    checks.append("Changed orientation/reset preview warns; Cancel preserves exact canonical bytes")

    operator = review()
    assert operator.orientation == "WORLD_AXES" and not operator.reset_frame
    assert support_intent_ui.MCAD_OT_edit_sketch_support.execute(operator, bpy.context) == {
        "FINISHED"
    }
    assert state.document_json == original
    checks.append("Unchanged legacy World axes Apply preserves exact canonical bytes")

    operator = review()
    operator.orientation = "MINIMAL_TWIST"
    assert support_intent_ui.MCAD_OT_edit_sketch_support.execute(operator, bpy.context) == {
        "FINISHED"
    }
    oriented = json.loads(state.document_json)["features"][-2]
    assert oriented["support_intent"]["orientation"] == {
        "policy": "minimal_twist",
        "tangent": [1, 0, 0],
    }
    assert oriented["sketch"] == ASSUMED["features"][-2]["sketch"]
    checks.append(
        "Explicit Minimal twist choice publishes without changing local sketch coordinates"
    )

    antiparallel = json.loads(state.document_json)
    antiparallel["features"][-2]["support_intent"]["signature"]["normal"] = [0, 0, -1]
    document_state._populate_document(bpy.context.scene, antiparallel)
    assert not document_state.regenerate(bpy.context)
    assert state.status == "FAILED"
    failed_json = state.document_json
    operator = review()
    support_intent_ui.MCAD_OT_edit_sketch_support.draw(operator, bpy.context)
    assert any("antiparallel" in line for line in operator.layout.labels)
    assert not operator.reset_frame
    assert support_intent_ui.MCAD_OT_edit_sketch_support.execute(operator, bpy.context) == {
        "CANCELLED"
    }
    assert state.document_json == failed_json
    operator = review()
    operator.reset_frame = True
    support_intent_ui.MCAD_OT_edit_sketch_support.draw(operator, bpy.context)
    assert any("rotate or move" in line for line in operator.layout.labels)
    assert support_intent_ui.MCAD_OT_edit_sketch_support.execute(operator, bpy.context) == {
        "FINISHED"
    }
    assert state.status == "READY"
    reset = json.loads(state.document_json)["features"][-2]["support_intent"]
    assert reset["signature"]["normal"] == reset["source_signature"]["normal"] == [0, 0, 1]
    assert reset["orientation"] == {"policy": "minimal_twist", "tangent": [1, 0, 0]}
    checks.append(
        "Antiparallel baseline refuses Apply; explicit warned frame reset restores replay"
    )

    operator = review()
    operator.policy = "STRICT"
    operator.support_face = "block/face/cap.start"
    assert support_intent_ui.MCAD_OT_edit_sketch_support.execute(operator, bpy.context) == {
        "FINISHED"
    }
    corrected = json.loads(state.document_json)["features"][-2]
    assert "support_intent" not in corrected and corrected["support_face"] == "block/face/cap.start"
    assert state.status == "READY"
    checks.append("Strict replacement support publishes via canonical transaction")

    # Install a canonical legacy fixture, then use normal regeneration to expose its failure.
    legacy_document = json.loads(json.dumps(ASSUMED))
    legacy_document["features"][-2].pop("support_intent")
    document_state._populate_document(bpy.context.scene, legacy_document)
    assert not document_state.regenerate(bpy.context)
    assert state.status == "FAILED"
    legacy = state.document_json
    operator = review()
    assert state.document_json == legacy
    assert operator.policy == "STRICT"
    assert operator.orientation == "MINIMAL_TWIST"
    operator.policy = "PRESERVE_PLANE"
    support_intent_ui.MCAD_OT_edit_sketch_support.draw(operator, bpy.context)
    assert any("Explicit repair" in line for line in operator.layout.labels)
    assert support_intent_ui.MCAD_OT_edit_sketch_support.execute(operator, bpy.context) == {
        "FINISHED"
    }
    assert state.status == "READY"
    repaired = json.loads(state.document_json)["features"][-2]
    assert repaired["support_intent"]["signature"]["centroid"] == [10, 10, 10]
    assert repaired["support_intent"]["source_signature"]["centroid"] == [10, 10, 10]
    assert repaired["support_intent"]["orientation"] == {
        "policy": "minimal_twist",
        "tangent": [1, 0, 0],
    }
    checks.append("Failed legacy sketch repaired with explicit current source-plane disclosure")

    repaired_json = state.document_json
    operator = review()
    state.document_json += " "

    changed = state.document_json
    assert support_intent_ui.MCAD_OT_edit_sketch_support.execute(operator, bpy.context) == {
        "CANCELLED"
    }
    assert state.document_json == changed
    checks.append("Changed base rejects late Apply without canonical mutation")

    state.document_json = repaired_json
    assert document_state.regenerate(bpy.context)
    state["support_smoke_expected_json"] = state.document_json
    args.blend.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(args.blend))
    checks.append("Saved repaired support, orientation and source baseline in native .blend")

print(
    "MCAD_SUPPORT_UI_RESULT="
    + json.dumps(
        {
            "ok": True,
            "blender": bpy.app.version_string,
            "reopened": args.verify_reopen,
            "checks": checks,
        }
    )
)
addon.unregister()
