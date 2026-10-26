"""Native Mirror preview/apply/cancel and two-process save/replay; no GUI claim."""

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
from mechanical_cad_blender import (  # noqa: E402
    document_state,
    execution_lease,
    mirror_plane_ui,  # noqa: E402
    register,
    sketch_pending,
    unregister,
)  # noqa: E402
from mechanical_cad_blender import extrusion_preview as preview  # noqa: E402
from mechanical_cad_blender.solid_operators import (  # noqa: E402
    MCAD_OT_add_solid_feature,  # noqa: E402
    MCAD_OT_edit_solid_feature,
    _draw_dimensions,  # noqa: E402
)

register()
state = bpy.context.scene.mechanical_cad
path = os.environ["MCAD_BLENDFILE"]
mode = os.environ.get("MCAD_MODE", "save")


def complete(owner, context):
    owner.changed = 0
    deadline = time.monotonic() + 45
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


def assert_result(z):
    result = document_state.current_part_result(bpy.context)["features"][-1]
    assert result["kind"] == "mirror" and result["stats"]["valid"]
    assert result["stats"]["solids"] == 1 and abs(result["stats"]["volume"] - 12000) < 1e-7
    assert min(v[2] for v in result["mesh"]["vertices"]) == 2 * z - 10
    assert max(v[2] for v in result["mesh"]["vertices"]) == 2 * z
    assert all(f["provenance"]["semantic_status"] == "stable" for f in result["topology"])


if mode == "save":
    assert bpy.ops.mcad.new_document() == {"FINISHED"}
    assert bpy.ops.mcad.add_rectangle(width=40, height=30) == {"FINISHED"}
    assert bpy.ops.mcad.add_extrude(profile=state.active_feature, length=10) == {"FINISHED"}
    base = state.active_feature
    area = next(a for a in bpy.context.window.screen.areas if a.type == "VIEW_3D")

    def operator():
        op = SimpleNamespace(
            kind="mirror",
            base=base,
            axis_x="0",
            axis_y="0",
            axis_z="1",
            x="0",
            y="0",
            z="0",
            feature_label="Mirror Result",
            original_json=state.document_json,
            properties=SimpleNamespace(is_property_set=lambda key: True),
        )
        op.preview_candidate = lambda context: MCAD_OT_add_solid_feature.preview_candidate(
            op, context
        )
        return op

    with bpy.context.temp_override(area=area):
        context = bpy.context
        before = state.document_json
        objects = [(o.as_pointer(), o.hide_viewport) for o in context.scene.objects]
        # Actual registered RNA preset update callbacks select native plane geometry.
        for plane_mode, axis in (("XY", 2), ("XZ", 1), ("YZ", 0)):
            assert bpy.ops.mcad.add_solid_feature(
                kind="mirror",
                base=base,
                x="3",
                y="3",
                z="3",
                mirror_plane=plane_mode,
            ) == {"FINISHED"}
            result = document_state.current_part_result(context)["features"][-1]
            normal = [result["resolved_params"][key] for key in ("axis_x", "axis_y", "axis_z")]
            assert normal == [int(i == axis) for i in range(3)], (plane_mode, normal)
            assert max(v[axis] for v in result["mesh"]["vertices"]) == 6
        assert document_state._commit_candidate(context, json.loads(before), state.document_path)
        objects = [(o.as_pointer(), o.hide_viewport) for o in context.scene.objects]
        op = operator()

        class Layout:
            def __init__(self):
                self.props = []

            def prop(self, owner, name, **kwargs):
                self.props.append(name)

            def label(self, **kwargs):
                pass

            def box(self):
                return self

            def row(self, **kwargs):
                return self

        # Repeated production dimension draws do not touch expressions or the model.
        for normal, plane_mode, expected in (
            (("0", "0", "1"), "XY", ["mirror_plane", "z"]),
            (("0", "1", "0"), "XZ", ["mirror_plane", "y"]),
            (("1", "0", "0"), "YZ", ["mirror_plane", "x"]),
            (
                ("1", "tilt", "0"),
                "CUSTOM",
                ["mirror_plane", "axis_x", "axis_y", "axis_z", "x", "y", "z"],
            ),
        ):
            op.axis_x, op.axis_y, op.axis_z = normal
            op.x, op.y, op.z = "position_x", "position_y", "height + 2"
            mirror_plane_ui.initialize(op, {})
            assert op.mirror_plane == plane_mode
            original = vars(op).copy()
            for _ in range(2):
                layout = Layout()
                _draw_dimensions(layout, op)
                assert layout.props == expected
                assert vars(op) == original and state.document_json == before
        op = operator()

        class DialogContext:
            window_manager = SimpleNamespace(invoke_props_dialog=lambda *a, **kw: {"RUNNING_MODAL"})

            def __getattr__(self, name):
                return getattr(context, name)

        with patch.object(preview, "start") as start:
            assert MCAD_OT_add_solid_feature.invoke(op, DialogContext(), None) == {"RUNNING_MODAL"}
            assert start.call_count == 1
        owner = preview.Preview(op, context)
        op._extrusion_preview = owner
        captured = []
        owner.overlay = lambda response, candidate: captured.append(response)
        complete(owner, context)
        assert captured[-1]["result"]["features"][-1]["kind"] == "mirror"
        assert state.document_json == before
        assert [(o.as_pointer(), o.hide_viewport) for o in context.scene.objects] == objects
        op.mirror_plane = "YZ"
        mirror_plane_ui.changed(op, context)
        op.x = "2"
        preview.changed(op, context)
        complete(owner, context)
        assert max(v[0] for v in captured[-1]["result"]["features"][-1]["mesh"]["vertices"]) == 4
        preview.cancel(op, context)
        reap()
        assert state.document_json == before and owner.closed

        # Invalid normal is rejected without replacing accepted canonical geometry.
        op = operator()
        op.axis_z = "0"
        owner = preview.Preview(op, context)
        op._extrusion_preview = owner
        owner.overlay = lambda *args: (_ for _ in ()).throw(AssertionError("Invalid preview drawn"))
        try:
            complete(owner, context)
            raise AssertionError("Zero normal accepted")
        except ValueError as exc:
            assert "normal" in str(exc).lower()
        owner.close()
        reap()
        assert state.document_json == before

        # Apply performs another guarded replay, rather than publishing preview evidence.
        op = operator()
        owner = preview.Preview(op, context)
        op._extrusion_preview = owner
        owner.overlay = lambda *args: None

        class ApplyContext:
            window_manager = SimpleNamespace(
                windows=context.window_manager.windows,
                event_timer_add=context.window_manager.event_timer_add,
                modal_handler_add=lambda op: None,
            )

            def __getattr__(self, name):
                return getattr(context, name)

        with patch.object(
            sketch_pending, "prepare_guarded", wraps=sketch_pending.prepare_guarded
        ) as prepare:
            complete(owner, context)
            op.z = "2"
            assert preview.apply(op, ApplyContext()) == {"RUNNING_MODAL"}
            complete(owner, context)
            assert prepare.call_count == 2
        assert owner.accepted
        owner.close()
        reap()
        assert_result(2)
    Path(path + ".json").write_text(state.document_json)
    assert bpy.ops.wm.save_as_mainfile(filepath=path) == {"FINISHED"}
else:
    assert mode == "reopen"
    bpy.ops.wm.open_mainfile(filepath=path)
    state = bpy.context.scene.mechanical_cad
    assert state.document_json == Path(path + ".json").read_text()
    assert bpy.ops.mcad.regenerate() == {"FINISHED"}
    assert_result(2)
    saved = json.loads(state.document_json)["features"][-1]
    edit_op = SimpleNamespace(feature_id=state.active_feature, resume_json="")
    edit_context = SimpleNamespace(
        scene=bpy.context.scene,
        window_manager=SimpleNamespace(
            invoke_props_dialog=lambda *args, **kwargs: {"RUNNING_MODAL"}
        ),
    )
    before = state.document_json
    assert MCAD_OT_edit_solid_feature.invoke(edit_op, edit_context, None) == {"RUNNING_MODAL"}
    assert edit_op.mirror_plane == "XY"
    assert all(getattr(edit_op, key) == str(value) for key, value in saved["params"].items())
    assert state.document_json == before
    # Switching the UI to Custom is not permission to rewrite the saved expressions.
    edit_op.mirror_plane = "CUSTOM"
    mirror_plane_ui.changed(edit_op, edit_context)
    assert all(getattr(edit_op, key) == str(value) for key, value in saved["params"].items())
    assert state.document_json == before
    # Edit Feature retains numeric expressions and changes only the explicit plane.
    identifier = state.active_feature
    assert bpy.ops.mcad.edit_solid_feature(
        feature_id=identifier,
        kind="mirror",
        feature_label="Edited mirror",
        base=json.loads(state.document_json)["features"][-1]["inputs"]["base"],
        axis_x="0",
        axis_y="0",
        axis_z="1",
        x="0",
        y="0",
        z="3",
        original_json=state.document_json,
    ) == {"FINISHED"}
    assert_result(3)
assert not any(name == "OCP" or name.startswith("OCP.") for name in sys.modules)
unregister()
print("MCAD_MIRROR_SMOKE_OK " + mode, flush=True)
