"""Creation-only Sweep preview through the existing guarded native owner.

Headless exact geometry/cancellation checks, not GPU or interactive GUI proof.
"""

import json
import math
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy

ROOT = Path(os.environ["MCAD_ROOT"])
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import (  # noqa: E402
    backend_runtime,
    document_state,
    execution_lease,
    register,
    registration,
    sketch_pending,
    unregister,
)
from mechanical_cad_blender import extrusion_preview as preview  # noqa: E402
from mechanical_cad_blender.extrusion_preview_geometry import boundary_edges  # noqa: E402
from mechanical_cad_blender.solid_operators import MCAD_OT_add_solid_feature  # noqa: E402

register()
assert bpy.ops.mcad.new_document() == {"FINISHED"}
assert bpy.ops.mcad.add_rectangle(width=40, height=30) == {"FINISHED"}
state = bpy.context.scene.mechanical_cad
assert bpy.ops.mcad.add_extrude(profile=state.active_feature, length=10) == {"FINISHED"}
base = state.active_feature
source = json.loads(state.document_json)
source["schema_version"] = 2


def sketch(identifier, points, lines, *, arcs=(), version=2):
    return dict(
        id=identifier,
        kind="sketch_constrained",
        label=identifier,
        params={},
        inputs={},
        sketch={
            "schema_version": version,
            "id": identifier,
            "units": "mm",
            "plane": {"id": "plane", "origin": [0, 0, 0], "quaternion": [1, 0, 0, 0]},
            "points": [{"id": name, "u": u, "v": v} for name, u, v in points],
            "lines": [{"id": name, "start": a, "end": b} for name, a, b in lines],
            "circles": [],
            **({"arcs": list(arcs)} if version == 3 else {}),
            "constraints": [
                {"id": "fix_" + name, "kind": "fixed", "refs": [name], "target": [u, v]}
                for name, u, v in points
            ],
        },
    )


source["features"] += [
    sketch(
        "section",
        (("a", 100, 200), ("b", 104, 200), ("c", 100, 202)),
        (("ab", "a", "b"), ("bc", "b", "c"), ("ca", "c", "a")),
    ),
    sketch(
        "path",
        (("a", 20, 0), ("z", 0, 20), ("center", 0, 0)),
        (),
        version=3,
        arcs=({"id": "curve", "center": "center", "start": "a", "end": "z", "direction": "ccw"},),
    ),
]
assert document_state._commit_candidate(bpy.context, source, state.document_path)
assert state.active_feature == base and abs(state.volume - 12000) < 1e-8
area = next(a for a in bpy.context.window.screen.areas if a.type == "VIEW_3D")


def operator():
    op = SimpleNamespace(
        kind="sweep",
        profile="section",
        path="path",
        feature_label="Preview Sweep",
        sweep_placement_mode="AUTO",
        sweep_roll="0",
        sweep_reverse=False,
        original_json=state.document_json,
        properties=SimpleNamespace(is_property_set=lambda key: True),
    )
    op.preview_candidate = lambda context: MCAD_OT_add_solid_feature.preview_candidate(op, context)
    return op


def reap():
    deadline = time.monotonic() + 15
    while execution_lease.is_busy() and time.monotonic() < deadline:
        sketch_pending.reap()
        time.sleep(0.01)
    assert not execution_lease.is_busy()


def complete(owner, context):
    owner.changed = 0
    deadline = time.monotonic() + 45
    while not owner.completed and time.monotonic() < deadline:
        owner.tick(context)
        time.sleep(0.02)
    assert owner.completed, owner.message


def launch(owner, context):
    owner.tick(context)
    owner.changed = 0
    owner.tick(context)
    assert owner.pending is not None
    return owner.pending


with bpy.context.temp_override(area=area):
    context = bpy.context
    before = state.document_json
    objects = [
        (o.as_pointer(), o.hide_viewport, o.data.as_pointer() if o.data else None)
        for o in context.scene.objects
    ]

    class DialogContext:
        window_manager = SimpleNamespace(invoke_props_dialog=lambda *a, **kw: {"RUNNING_MODAL"})

        def __getattr__(self, name):
            return getattr(context, name)

    # Production invocation starts the shared preview, not a parallel launch path.
    op = operator()
    with patch.object(preview, "start") as start:
        assert MCAD_OT_add_solid_feature.invoke(op, DialogContext(), None) == {"RUNNING_MODAL"}
        assert start.call_count == 1 and start.call_args.args[0] is op
    owner = preview.Preview(op, context)
    op._extrusion_preview = owner
    captured = []
    owner.overlay = lambda response, candidate: captured.append((response, candidate))
    owner.tick(context)
    assert owner.pending is None, "Initial preview must wait for debounce"
    complete(owner, context)
    first_response, first_candidate = captured[-1]
    result = first_response["result"]["features"][-1]
    assert result["kind"] == "sweep" and result["mesh"]
    assert abs(result["stats"]["volume"] - 40 * math.pi) < 1e-6
    assert boundary_edges(result["mesh"])
    assert all(f["provenance"]["semantic_status"] != "stable" for f in result["topology"])
    assert state.document_json == before and abs(state.volume - 12000) < 1e-8
    assert [
        (o.as_pointer(), o.hide_viewport, o.data.as_pointer() if o.data else None)
        for o in context.scene.objects
    ] == objects
    preview.changed(op, context)
    assert owner.completed and len(captured) == 1, "Passive redraw must not repeat exact work"
    op.sweep_roll = "37"
    preview.changed(op, context)
    assert owner.batch is None and not owner.completed
    complete(owner, context)
    assert captured[-1][0]["result"]["features"][-1]["mesh"] != result["mesh"]
    op.sweep_reverse = True
    preview.changed(op, context)
    complete(owner, context)
    assert captured[-1][1]["features"][-1]["sweep_placement"]["reverse"] is True
    assert (
        captured[-1][0]["result"]["features"][-1]["mesh"]
        != captured[-2][0]["result"]["features"][-1]["mesh"]
    )
    assert state.document_json == before
    owner.close()

    # A fully ready old response is retired before revised input can draw it.
    op = operator()
    owner = preview.Preview(op, context)
    op._extrusion_preview = owner
    captured = []
    owner.overlay = lambda response, candidate: captured.append(candidate)
    old_pending = launch(owner, context)
    deadline = time.monotonic() + 45
    while (
        old_pending._job.poll(owner.selection) not in {"ready", "failed"}
        and time.monotonic() < deadline
    ):
        time.sleep(0.02)
    assert old_pending._job.poll(owner.selection) == "ready"
    op.sweep_roll = "90"
    preview.changed(op, context)
    reap()
    assert owner.pending is None and not captured
    complete(owner, context)
    assert (
        len(captured) == 1 and captured[0]["features"][-1]["sweep_placement"]["roll_degrees"] == 90
    )
    owner.close()
    assert state.document_json == before

    # Cancel in flight and actual Undo pre-handler retain accepted data and reap native work.
    for undo in (False, True):
        op = operator()
        owner = preview.Preview(op, context)
        op._extrusion_preview = owner
        launch(owner, context)
        if undo:
            registration._before_history_change(None)
        else:
            preview.cancel(op, context)
        assert owner.closed and owner not in preview._OWNERS
        reap()
        assert state.document_json == before

    # Source edits and unit changes cause the timer to close rather than draw stale outlines.
    for change in ("source", "units", "view_layer"):
        op = operator()
        timers = []
        with patch.object(
            bpy.app.timers,
            "register",
            side_effect=lambda cb, timers=timers, **kw: timers.append(cb),
        ):
            owner = preview.start(op, context)
        owner.overlay = lambda *a: (_ for _ in ()).throw(AssertionError("Stale preview drawn"))
        launch(owner, context)
        old_layer = context.window.view_layer
        extra_layer = None
        if change == "source":
            state.document_json = before + " "
        elif change == "units":
            context.scene.unit_settings.scale_length = 2
        else:
            extra_layer = context.scene.view_layers.new("Sweep preview context test")
            context.window.view_layer = extra_layer
        assert timers[0]() is None and owner.closed
        if change == "source":
            state.document_json = before
        elif change == "units":
            context.scene.unit_settings.scale_length = 1
        else:
            context.window.view_layer = old_layer
            context.scene.view_layers.remove(extra_layer)
        reap()
        assert state.document_json == before

    # A dialog is backend-bound before its first debounced native launch.
    op = operator()
    owner = preview.Preview(op, context)
    op._extrusion_preview = owner
    backend_runtime.revoke("Test pre-debounce backend change")
    try:
        owner.tick(context)
        raise AssertionError("Pre-debounce backend change accepted")
    except ValueError:
        pass
    assert owner.closed and owner.pending is None
    assert state.document_json == before
    assert bpy.ops.mcad.regenerate() == {"FINISHED"}

    # Backend revocation cannot be hidden by simultaneously changing the roll.
    op = operator()
    owner = preview.Preview(op, context)
    op._extrusion_preview = owner
    launch(owner, context)
    backend_runtime.revoke("Test backend generation change")
    op.sweep_roll = "12"
    preview.changed(op, context)
    try:
        owner.tick(context)
        raise AssertionError("Backend-switched preview accepted")
    except ValueError:
        pass
    assert owner.closed
    reap()
    assert state.document_json == before
    assert bpy.ops.mcad.regenerate() == {"FINISHED"}

    # Invalid authored placement never draws a partial result and recovers after correction.
    op = operator()
    owner = preview.Preview(op, context)
    op._extrusion_preview = owner
    owner.overlay = lambda *a: (_ for _ in ()).throw(AssertionError("Invalid preview drawn"))
    op.sweep_placement_mode = "AUTHORED"
    try:
        complete(owner, context)
        raise AssertionError("Invalid Sweep accepted")
    except ValueError as exc:
        assert "Sweep" in str(exc) or "sweep" in str(exc)
    owner.invalidate()
    op.sweep_placement_mode = "AUTO"
    preview.changed(op, context)
    owner.overlay = lambda *a: None
    complete(owner, context)
    assert state.document_json == before
    owner.close()

    # Apply submits fresh guarded replay; the completed preview has no publication authority.
    op = operator()
    owner = preview.Preview(op, context)
    op._extrusion_preview = owner
    owner.overlay = lambda *a: None

    class ApplyContext:
        window_manager = SimpleNamespace(
            windows=context.window_manager.windows,
            event_timer_add=context.window_manager.event_timer_add,
            modal_handler_add=lambda operator: None,
        )

        def __getattr__(self, name):
            return getattr(context, name)

    with patch.object(
        sketch_pending, "prepare_guarded", wraps=sketch_pending.prepare_guarded
    ) as prepare:
        complete(owner, context)
        assert prepare.call_count == 1 and state.document_json == before
        op.sweep_roll, op.sweep_reverse = "25", True
        assert preview.apply(op, ApplyContext()) == {"RUNNING_MODAL"}
        complete(owner, context)
        assert prepare.call_count == 2
        assert prepare.call_args_list[0].args[0] is not prepare.call_args_list[1].args[0]
    assert owner.accepted and state.document_json != before
    saved = json.loads(state.document_json)["features"][-1]
    assert saved["kind"] == "sweep" and saved["sweep_placement"]["roll_degrees"] == 25
    assert saved["sweep_placement"]["reverse"] is True
    assert abs(state.volume - 40 * math.pi) < 1e-4  # Blender RNA is float32.
    exact = document_state.current_part_result(context)["features"][-1]["stats"]["volume"]
    assert abs(exact - 40 * math.pi) < 1e-6
    owner.close()
    reap()

assert not any(name == "OCP" or name.startswith("OCP.") for name in sys.modules)
unregister()
print("MCAD_SWEEP_PREVIEW_SMOKE_OK", flush=True)
