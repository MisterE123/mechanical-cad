"""Native async preview ownership; headless does not certify GPU/dialog usability."""

import json
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy

ROOT = Path(os.environ["MCAD_ROOT"])
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import execution_lease, register, sketch_pending, unregister  # noqa: E402  # noqa: E402
from mechanical_cad_blender import extrusion_preview as preview  # noqa: E402
from mechanical_cad_blender.extrusion_operators import MCAD_OT_extrude_boolean  # noqa: E402

register()
assert bpy.ops.mcad.new_document() == {"FINISHED"}
assert bpy.ops.mcad.add_rectangle(width=40, height=30) == {"FINISHED"}
state = bpy.context.scene.mechanical_cad
profile = state.active_feature
assert bpy.ops.mcad.add_extrude(profile=profile, length=10) == {"FINISHED"}
base = state.active_feature
assert bpy.ops.mcad.add_circle(radius=2, x=10, y=10, z=10) == {"FINISHED"}
profile = state.active_feature
area = next(a for a in bpy.context.window.screen.areas if a.type == "VIEW_3D")


def reap():
    deadline = time.monotonic() + 15
    while execution_lease.is_busy() and time.monotonic() < deadline:
        sketch_pending.reap()
        time.sleep(0.02)
    assert not execution_lease.is_busy()


def operator():
    op = SimpleNamespace(
        mode="REMOVE",
        profile=profile,
        base=base,
        end_condition="THROUGH_ALL",
        depth="4",
        direction="REVERSE",
        feature_label="Preview cut",
    )
    op.preview_candidate = lambda context: MCAD_OT_extrude_boolean.preview_candidate(op, context)
    return op


def complete(owner, context):
    owner.changed = 0
    deadline = time.monotonic() + 40
    while not owner.completed and time.monotonic() < deadline:
        owner.tick(context)
        time.sleep(0.02)
    assert owner.completed, owner.message


with bpy.context.temp_override(area=area):
    context = bpy.context
    before = state.document_json
    objects = [(o.as_pointer(), o.hide_viewport) for o in context.scene.objects]
    op = operator()
    owner = preview.Preview(op, context)
    op._extrusion_preview = owner
    captured = []
    owner.overlay = lambda response, candidate: captured.append(response)
    complete(owner, context)
    assert state.document_json == before
    assert [(o.as_pointer(), o.hide_viewport) for o in context.scene.objects] == objects
    result = captured[-1]["result"]
    active = next(f for f in result["features"] if f["id"] == result["active_feature"])
    assert active["mesh"] and active["stats"]["volume"] < 12000
    # A changed symmetric intent launches a different exact replay, not old evidence.
    op.end_condition = "SYMMETRIC"
    preview.changed(op, context)
    complete(owner, context)
    assert len(captured) == 2 and state.document_json == before
    # Cancel during native work cannot publish, and its lease eventually reaps.
    op.depth = "6"
    preview.changed(op, context)
    owner.changed = 0
    owner.tick(context)
    owner.changed = 0
    owner.tick(context)
    assert owner.pending is not None
    owner.close()
    reap()
    assert state.document_json == before
    # Stale document is rejected before launching.
    op = operator()
    owner = preview.Preview(op, context)
    state.document_json = before + " "
    try:
        owner.tick(context)
        raise AssertionError("Stale preview accepted")
    except ValueError:
        pass
    finally:
        owner.close()
        state.document_json = before
    # A lost modal window is still supervised without accepting ready work.
    op = operator()
    timers = []
    with patch.object(
        bpy.app.timers, "register", side_effect=lambda callback, **kw: timers.append(callback)
    ):
        owner = preview.start(op, context)
    owner.applying = True
    owner.tick(context)
    owner.window = None
    assert timers[0]() is None
    assert owner.closed and owner not in preview._OWNERS
    reap()
    assert state.document_json == before
    # Exact kernel rejection never turns a zero depth into a current preview.
    op = operator()
    op.end_condition, op.depth = "SYMMETRIC", "0"
    owner = preview.Preview(op, context)
    owner.overlay = lambda *args: (_ for _ in ()).throw(AssertionError("Invalid preview drawn"))
    try:
        complete(owner, context)
        raise AssertionError("Invalid native result accepted")
    except ValueError:
        pass
    finally:
        owner.close()
    reap()
    assert state.document_json == before
    # Apply takes a fresh request and atomically publishes without sync replay.
    op = operator()
    owner = preview.Preview(op, context)
    owner.applying = True
    complete(owner, context)
    assert state.document_json != before
    assert json.loads(state.document_json)["features"][-2]["kind"] == "extrude_through"
    owner.close()
    assert not execution_lease.is_busy()

unregister()
print("MCAD_EXTRUSION_PREVIEW_SMOKE_OK", flush=True)
