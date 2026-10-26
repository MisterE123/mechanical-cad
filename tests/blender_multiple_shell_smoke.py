"""Multiple Shell native authoring/edit/list/pick and two-process persistence.

Headless operator and modal-event tests do not establish interactive GUI usability.
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
from mechanical_cad_blender import (  # noqa: E402
    face_pick,
    register,
    shell_pick,
    solid_operators,
    solid_review,
    unregister,
    viewport_navigation,
)
from mechanical_cad_blender.display import _owned_objects  # noqa: E402

register()
state = bpy.context.scene.mechanical_cad
path = os.environ["MCAD_SHELL_BLEND"]


def run(operator, **kwargs):
    result = operator(**kwargs)
    assert result == {"FINISHED"}, (result, state.last_action_error)
    assert state.status == "READY", (state.status, state.last_action_error)
    return state.active_feature


def rejected(operator, **kwargs):
    before = state.document_json
    try:
        result = operator(**kwargs)
    except RuntimeError:
        result = {"CANCELLED"}
    assert result == {"CANCELLED"} and state.document_json == before


def check_selection_feedback(base, openings):
    """Real bound native display geometry; mocked GPU draw, not mouse/visual QA."""
    window = bpy.context.window
    area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
    region = next(r for r in area.regions if r.type == "WINDOW")
    before = state.document_json
    with bpy.context.temp_override(window=window, area=area, region=region):
        context = bpy.context
        obj = _owned_objects(context.scene)[0]
        picker = face_pick.FacePicker(context)
        picker.hover_object = obj
        picker.set_selected(context, base, openings)
        assert isinstance(picker.snapshot, face_pick.HoverSnapshot)
        assert picker.selected_object == obj and len(picker.selected_points) == 12
        captured = [tuple(point) for point in picker.selected_points]
        # Moving off geometry clears cyan hover feedback, never the explicit orange set.
        with patch.object(face_pick.workspace_ui, "is_palette_event", return_value=True):
            assert not picker.hover(context, SimpleNamespace(mouse_x=0, mouse_y=0))
        assert not picker.points and [tuple(p) for p in picker.selected_points] == captured
        owner = SimpleNamespace(_picker=picker)
        assert shell_pick.MCAD_OT_pick_shell_face.modal(
            owner, context, SimpleNamespace(type="MIDDLEMOUSE", value="PRESS")
        ) == {"PASS_THROUGH"}
        assert [tuple(p) for p in picker.selected_points] == captured
        # Native navigation UI wins before geometry hover, including a drag
        # that exits its footprint. Both creation and reselection preserve intent.
        left, bottom, right, top = viewport_navigation.navigation_bounds(context, region)
        nav_x, nav_y = (left + right) / 2, (bottom + top) / 2
        outside_x, outside_y = region.x + 1, region.y + 1
        for operator, nav_owner in (
            (
                shell_pick.MCAD_OT_pick_shell_face,
                SimpleNamespace(_picker=picker, _selected=list(openings), report=lambda *a: None),
            ),
            (
                solid_review.MCAD_OT_reselect_solid_input,
                SimpleNamespace(
                    _picker=picker,
                    kind="shell",
                    _selected_openings=list(openings),
                    values={"opening_faces_json": json.dumps(openings)},
                    report=lambda *a: None,
                ),
            ),
        ):
            with patch.object(picker, "hover") as hover:
                for kind, value, x, y in (
                    ("LEFTMOUSE", "PRESS", nav_x, nav_y),
                    ("MOUSEMOVE", "NOTHING", outside_x, outside_y),
                    ("INBETWEEN_MOUSEMOVE", "NOTHING", outside_x, outside_y),
                    ("LEFTMOUSE", "RELEASE", outside_x, outside_y),
                ):
                    assert operator.modal(
                        nav_owner,
                        context,
                        SimpleNamespace(type=kind, value=value, mouse_x=x, mouse_y=y),
                    ) == {"PASS_THROUGH"}
                    assert [tuple(p) for p in picker.selected_points] == captured
                assert not hover.called and not picker.navigation_drag
            selected = getattr(
                nav_owner, "_selected", getattr(nav_owner, "_selected_openings", None)
            )
            assert selected == openings and state.document_json == before
        # FacePicker itself also excludes that UI before computing any world ray.
        with (
            patch.object(face_pick.workspace_ui, "is_palette_event", return_value=False),
            patch.object(face_pick.view3d_utils, "region_2d_to_origin_3d") as ray_origin,
        ):
            assert not picker.hover(context, SimpleNamespace(mouse_x=nav_x, mouse_y=nav_y))
            assert not ray_origin.called
        assert [tuple(p) for p in picker.selected_points] == captured
        with patch.object(face_pick, "draw_highlight") as draw:
            picker.draw()
            assert draw.call_count == 1
            assert draw.call_args.args[1] == (1.0, 0.48, 0.08, 0.55)
            assert [tuple(p) for p in draw.call_args.args[0]] == captured
            picker.points = list(picker.selected_points[:3])
            draw.reset_mock()
            picker.draw()
            assert [call.args[1] for call in draw.call_args_list] == [
                (1.0, 0.48, 0.08, 0.55),
                (0.15, 0.8, 1.0, 0.4),
            ]
        # Deselect one cap, then all; no stale tint survives.
        picker.hover_object = obj
        picker.set_selected(context, base, openings[:1])
        assert len(picker.selected_points) == 6
        picker.set_selected(context, base, [])
        assert not picker.selected_points and picker.selected_object is None
        picker.set_selected(context, base, openings)
        vertex = obj.data.vertices[0].co.copy()
        obj.data.vertices[0].co.x += 0.001
        try:
            picker.set_selected(context, base, openings)
            raise AssertionError("Edited display accepted as selection feedback")
        except ValueError:
            pass
        with patch.object(face_pick, "draw_highlight") as draw:
            picker.draw()
            assert not draw.called
        assert not picker.selected_points and not picker.points and picker.selected_object is None
        obj.data.vertices[0].co = vertex
        picker.hover_object = obj
        picker.set_selected(context, base, openings)
        state.status = "DIRTY"
        with patch.object(face_pick, "draw_highlight") as draw:
            picker.draw()
            assert not draw.called
        assert not picker.selected_points and picker.selected_object is None
        state.status = "READY"
        picker.set_selected(context, base, openings)
        picker.close()
        assert not picker.selected_points and picker.selected_object is None
        assert picker.handler is None and picker.timer is None and picker not in face_pick._PICKERS
        assert state.document_json == before
    print("MCAD_MULTIPLE_SHELL_FEEDBACK_OK")


if os.environ.get("MCAD_SHELL_PHASE") == "reopen":
    bpy.ops.wm.open_mainfile(filepath=path)
    state = bpy.context.scene.mechanical_cad
    run(bpy.ops.mcad.regenerate)
    feature = json.loads(state.document_json)["features"][-1]
    assert len(feature["opening_faces"]) == 2
    assert abs(state.volume - 1240) < 1e-5
    print("MCAD_MULTIPLE_SHELL_REOPEN_OK")
else:
    run(bpy.ops.mcad.new_document, name="Two explicit shell openings")
    profile = run(bpy.ops.mcad.add_rectangle, width=20, height=15)
    base = run(bpy.ops.mcad.add_extrude, profile=profile, length=10)
    openings = [base + "/face/cap.end", base + "/face/cap.start"]
    check_selection_feedback(base, openings)
    shell = run(
        bpy.ops.mcad.add_solid_feature,
        kind="shell",
        base=base,
        shell_mode="OPEN",
        opening_faces_json=json.dumps(openings),
        thickness="1",
        original_json=state.document_json,
    )
    assert abs(state.volume - 660) < 1e-5

    class Rows(list):
        def add(self):
            row = SimpleNamespace()
            self.append(row)
            return row

    class Context:
        window_manager = SimpleNamespace(invoke_props_dialog=lambda *a, **k: {"RUNNING_MODAL"})

        def __getattr__(self, name):
            return getattr(bpy.context, name)

    picked = SimpleNamespace(
        kind="shell",
        picked_base=base,
        picked_opening_faces_json=json.dumps(openings),
        picked_opening_face="",
        picked_document_json=state.document_json,
        properties=SimpleNamespace(is_property_set=lambda key: False),
        shell_openings=Rows(),
        shell_choices_ready=False,
    )
    assert solid_operators.MCAD_OT_add_solid_feature.invoke(picked, Context(), None) == {
        "RUNNING_MODAL"
    }
    assert picked.shell_mode == "OPEN" and solid_operators._shell_values(picked) == openings
    assert state.document_json == picked.original_json

    owner = SimpleNamespace(
        feature_id=shell,
        resume_json="",
        shell_openings=Rows(),
        shell_choices_ready=False,
        report=lambda *a: None,
    )
    assert solid_operators.MCAD_OT_edit_solid_feature.invoke(owner, Context(), None) == {
        "RUNNING_MODAL"
    }
    assert solid_operators._shell_values(owner) == openings or set(
        solid_operators._shell_values(owner)
    ) == set(openings)
    assert len(owner.shell_openings) == 6
    assert all(row.available for row in owner.shell_openings)
    # Checkbox values, not a stale singleton field, control publication.
    for row in owner.shell_openings:
        row.selected = row.face_id == openings[0]
    assert solid_operators._shell_values(owner) == openings[:1]
    for row in owner.shell_openings:
        row.selected = False
    try:
        solid_operators._shell_values(owner)
        raise AssertionError("Empty checkbox selection accepted")
    except ValueError:
        pass
    # Switching bases preserves unavailable checked identities visibly, never guesses.
    owner.shell_openings[0].selected = True
    retained = owner.shell_openings[0].face_id
    owner.base = shell
    solid_operators._shell_choices(owner, Context())
    assert any(
        row.face_id == retained and row.selected and not row.available
        for row in owner.shell_openings
    )

    for encoded in ("[]", json.dumps([openings[0]] * 2), json.dumps([openings[0], "missing"])):
        rejected(
            bpy.ops.mcad.edit_solid_feature,
            kind="shell",
            feature_id=shell,
            base=base,
            shell_mode="OPEN",
            opening_faces_json=encoded,
            thickness="2",
            original_json=state.document_json,
        )
    rejected(
        bpy.ops.mcad.edit_solid_feature,
        kind="shell",
        feature_id=shell,
        base=base,
        shell_mode="OPEN",
        opening_faces_json=json.dumps(openings),
        thickness="100",
        original_json=state.document_json,
    )
    run(
        bpy.ops.mcad.edit_solid_feature,
        kind="shell",
        feature_id=shell,
        base=base,
        shell_mode="OPEN",
        opening_faces_json=json.dumps(openings),
        thickness="2",
        original_json=state.document_json,
    )
    assert abs(state.volume - 1240) < 1e-5

    # Shift-click accumulates, duplicate click toggles, Enter hands off only once.
    before = state.document_json
    calls = []
    view_area = next(a for a in bpy.context.window.screen.areas if a.type == "VIEW_3D")
    view_region = next(r for r in view_area.regions if r.type == "WINDOW")
    modal_context = SimpleNamespace(area=view_area, preferences=bpy.context.preferences)
    picker = SimpleNamespace(
        current=lambda c: True,
        hover=lambda *a, **k: True,
        hit=(base, openings[0]),
        close=lambda: calls.append("close"),
        set_selected=lambda context, source, ids: None,
        area=SimpleNamespace(header_text_set=lambda text: None, tag_redraw=lambda: None),
        region=view_region,
    )
    modal_owner = SimpleNamespace(
        _picker=picker,
        _selected=[],
        _source="",
        _review=lambda: calls.append("review") or {"FINISHED"},
        report=lambda *a: None,
    )
    click = SimpleNamespace(
        type="LEFTMOUSE",
        value="PRESS",
        shift=True,
        mouse_x=view_region.x + 1,
        mouse_y=view_region.y + 1,
    )
    modal = shell_pick.MCAD_OT_pick_shell_face.modal
    assert modal(modal_owner, modal_context, click) == {"RUNNING_MODAL"}
    picker.hit = (base, openings[1])
    assert modal(modal_owner, modal_context, click) == {"RUNNING_MODAL"}
    assert modal_owner._selected == openings
    assert modal(modal_owner, modal_context, click) == {"RUNNING_MODAL"}
    assert modal_owner._selected == openings[:1]
    assert modal(modal_owner, modal_context, SimpleNamespace(type="RET", value="PRESS")) == {
        "FINISHED"
    }
    assert calls == ["review"] and state.document_json == before
    calls.clear()
    assert modal(modal_owner, modal_context, SimpleNamespace(type="ESC", value="PRESS")) == {
        "CANCELLED"
    }
    assert calls == ["close"] and state.document_json == before
    # Review cancel must keep the original editor selection, not partially picked faces.
    cancel_owner = SimpleNamespace(
        _picker=picker,
        kind="shell",
        values={"opening_faces_json": json.dumps(openings)},
        _selected_openings=[openings[0]],
        _return_editor=lambda: calls.append("editor"),
    )
    assert solid_review.MCAD_OT_reselect_solid_input.modal(
        cancel_owner, bpy.context, SimpleNamespace(type="ESC", value="PRESS")
    ) == {"CANCELLED"}
    assert json.loads(cancel_owner.values["opening_faces_json"]) == openings
    assert state.document_json == before
    # Enter transfers the entire detached multi-selection, never a partial first face.
    cancel_owner._selected_openings = list(reversed(openings))
    assert solid_review.MCAD_OT_reselect_solid_input.modal(
        cancel_owner, bpy.context, SimpleNamespace(type="RET", value="PRESS")
    ) == {"FINISHED"}
    assert json.loads(cancel_owner.values["opening_faces_json"]) == list(reversed(openings))
    assert state.document_json == before
    bpy.ops.wm.save_as_mainfile(filepath=path)
    print("MCAD_MULTIPLE_SHELL_CREATE_OK")
unregister()
