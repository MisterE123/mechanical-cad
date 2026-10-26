"""Native exact preview/apply/cancel ownership for explicit face-plane end intent."""

import json
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import bpy

ROOT = Path(os.environ["MCAD_ROOT"])
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import execution_lease, register, sketch_pending, unregister  # noqa: E402
from mechanical_cad_blender import extrusion_preview as preview  # noqa: E402
from mechanical_cad_blender.document_state import _commit_candidate  # noqa: E402
from mechanical_cad_blender.extrusion_operators import MCAD_OT_extrude_boolean  # noqa: E402
from mechanical_cad_blender.operators import MCAD_OT_extrude  # noqa: E402

register()
assert bpy.ops.mcad.new_document() == {"FINISHED"}
state = bpy.context.scene.mechanical_cad
doc = json.loads(state.document_json)
doc["parameters"] = {"gap": 0}
doc["features"] = [
    dict(
        id="p",
        kind="sketch_rectangle",
        label="Base profile",
        params={"width": 10, "height": 10},
        inputs={},
    ),
    dict(id="base", kind="extrude", label="Base", params={"length": 10}, inputs={"profile": "p"}),
    dict(
        id="stop_p",
        kind="sketch_rectangle",
        label="Target profile",
        params={"width": 3, "height": 3, "x": 50, "z": 4},
        inputs={},
    ),
    dict(
        id="stop",
        kind="extrude",
        label="Independent target",
        params={"length": 1},
        inputs={"profile": "stop_p"},
    ),
    dict(
        id="other",
        kind="transform",
        label="Another exact source",
        params={"z": 2},
        inputs={"base": "stop"},
    ),
    dict(
        id="q",
        kind="sketch_rectangle",
        label="Tool profile",
        params={"width": 2, "height": 2, "x": 4, "y": 4, "z": 10},
        inputs={},
    ),
]
doc["active_feature"] = "base"
assert _commit_candidate(bpy.context, doc, state.document_path)
area = next(a for a in bpy.context.window.screen.areas if a.type == "VIEW_3D")


def operator(standalone=False):
    op = SimpleNamespace(
        mode="REMOVE",
        profile="q",
        base="base",
        end_condition="UP_TO_FACE",
        depth="4",
        length=4,
        direction="-1" if standalone else "REVERSE",
        feature_label="Preview cut",
        target="stop",
        end_face="stop/face/cap.end",
        offset="gap",
    )
    cls = MCAD_OT_extrude if standalone else MCAD_OT_extrude_boolean
    op.preview_candidate = lambda context: cls.preview_candidate(op, context)
    return op


def complete(owner, context):
    owner.changed = 0
    deadline = time.monotonic() + 40
    while not owner.completed and time.monotonic() < deadline:
        owner.tick(context)
        time.sleep(0.02)
    assert owner.completed, owner.message


def reap():
    deadline = time.monotonic() + 15
    while execution_lease.is_busy() and time.monotonic() < deadline:
        sketch_pending.reap()
        time.sleep(0.02)
    assert not execution_lease.is_busy()


with bpy.context.temp_override(area=area):
    context = bpy.context
    before = state.document_json
    objects = [(o.as_pointer(), o.hide_viewport) for o in context.scene.objects]
    for standalone, expected in [(True, 20), (False, 980)]:
        op = operator(standalone)
        owner = preview.Preview(op, context)
        op._extrusion_preview = owner
        captured = []
        owner.overlay = lambda response, candidate, captured=captured: captured.append(response)
        complete(owner, context)
        assert state.document_json == before
        assert [(o.as_pointer(), o.hide_viewport) for o in context.scene.objects] == objects
        result = captured[-1]["result"]
        active = next(f for f in result["features"] if f["id"] == result["active_feature"])
        assert abs(active["stats"]["volume"] - expected) < 1e-4
        assert active["mesh"]
        # Offset and exact-source changes invalidate old evidence, not the accepted Part.
        op.offset = "gap+1"
        preview.changed(op, context)
        complete(owner, context)
        assert len(captured) == 2 and state.document_json == before
        op.target = "other"
        preview.changed(op, context)
        complete(owner, context)
        assert len(captured) == 3 and state.document_json == before
        # Cancel while fresh sidecar work is pending cannot publish preview evidence.
        op.offset = "gap+2"
        preview.changed(op, context)
        owner.changed = 0
        owner.tick(context)
        owner.changed = 0
        owner.tick(context)
        assert owner.pending is not None
        owner.close()
        reap()
        assert state.document_json == before
    # No new draw or publication for a nonparallel face.
    op = operator()
    op.end_face = "stop/face/side.x_min"
    owner = preview.Preview(op, context)
    owner.overlay = lambda *args: (_ for _ in ()).throw(AssertionError("Invalid preview drawn"))
    try:
        complete(owner, context)
        raise AssertionError("Nonparallel end face accepted")
    except ValueError as exc:
        assert "parallel" in str(exc), str(exc)
    finally:
        owner.close()
    reap()
    assert state.document_json == before
    # Stale base document cancels before native work can be consumed.
    owner = preview.Preview(operator(), context)
    state.document_json = before + " "
    try:
        owner.tick(context)
        raise AssertionError("Stale preview accepted")
    except ValueError:
        pass
    finally:
        owner.close()
        state.document_json = before
    # Apply performs fresh exact work then atomically publishes canonical intent.
    owner = preview.Preview(operator(), context)
    owner.applying = True
    complete(owner, context)
    accepted = json.loads(state.document_json)
    assert accepted["features"][-2]["kind"] == "extrude_to_face"
    assert accepted["features"][-2]["inputs"] == {"profile": "q", "target": "stop"}
    assert accepted["features"][-2]["params"] == {"direction": -1, "offset": "gap"}
    assert accepted["features"][-2]["end_face"] == "stop/face/cap.end"
    assert abs(state.volume - 980) < 1e-4
    assert owner.accepted
    owner.close()
    reap()

unregister()
print("MCAD_UP_TO_FACE_PREVIEW_OK", flush=True)
