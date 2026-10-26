"""Registered multi-source authoring, native picks and draft Resume; no GUI claims.

Background Blender uses a saved view and deterministic event-region routing.
Geometry, native scene rays, exact catalogs, operator admission, solves and
publication remain real. Earlier solids are picked without leaving the draft.
"""

import copy
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy
from bpy_extras import view3d_utils
from mathutils import Matrix, Vector

ROOT = Path(os.environ["MCAD_ROOT"])
sys.path[:0] = [str(ROOT / "blender_addon"), str(ROOT / "tests")]
from mechanical_cad_blender import (  # noqa: E402
    document_state,
    draft_dispatch,
    face_pick,
    general_session,
    register,
    solid_projection_picker,
    solid_review,
    unregister,
    workspace,
)
from mechanical_cad_blender.common import OWNER_KEY  # noqa: E402

captured = []
original_execute = solid_projection_picker.MCAD_OT_use_solid_edge.execute


def capture_execute(self, context):
    result = original_execute(self, context)
    if result == {"RUNNING_MODAL"}:
        captured.append(self)
    return result


solid_projection_picker.MCAD_OT_use_solid_edge.execute = capture_execute


def wait(owner, context):
    deadline = time.monotonic() + 45
    while owner.pending is not None and time.monotonic() < deadline:
        owner.tick(context)
        time.sleep(0.01)
    assert owner.pending is None and not owner.error, owner.error


def finish(owner, context):
    with patch.object(workspace, "request_workspace"):
        owner.request_finish(context)
        wait(owner, context)
    assert owner.finished


def source(identifier, x):
    return {
        "id": identifier,
        "kind": "sketch_constrained",
        "label": identifier,
        "params": {},
        "inputs": {},
        "sketch": {
            "schema_version": 2,
            "id": identifier + "_geometry",
            "units": "mm",
            "plane": {"id": "xy", "origin": [0, 0, 0], "quaternion": [1, 0, 0, 0]},
            "points": [{"id": "center", "u": x, "v": 5}],
            "lines": [],
            "circles": [{"id": "circle", "center": "center", "radius": 2}],
            "constraints": [
                {"id": "fixed", "kind": "fixed", "refs": ["center"], "target": [x, 5]},
                {"id": "radius", "kind": "radius", "refs": ["circle"], "value": 2},
            ],
        },
    }


def scene_capture(context):
    return (
        {
            obj: (obj.hide_get(), obj.select_get(), obj.hide_viewport, obj.hide_render)
            for obj in context.scene.objects
        },
        context.view_layer.objects.active,
        context.scene.mechanical_cad.document_json,
        document_state.current_part_evidence(context),
    )


def assert_scene(context, expected):
    actual = scene_capture(context)
    assert actual == expected, (actual, expected)
    assert not solid_review._REVIEWS and not face_pick._PICKERS


def open_picker(context, owner, source_id):
    before_intent = draft_dispatch.dumps(owner.draft)
    before_saved = context.scene.mechanical_cad.sketch_draft_json
    assert bpy.ops.mcad.use_solid_edge.poll()
    assert bpy.ops.mcad.use_solid_edge(source_solid=source_id) == {"RUNNING_MODAL"}
    operator = captured[-1]
    picker = operator._picker
    assert picker.snapshot.source_id == source_id
    assert picker.snapshot.obj.get(OWNER_KEY) != context.scene.mechanical_cad.owner_id
    assert picker.snapshot.obj.get("mechanical_cad_display_only")
    assert (
        picker.snapshot.bound_feature(
            context, picker.snapshot.obj, picker.snapshot.result(context, accepting=True)
        )["id"]
        == source_id
    )
    deadline = time.monotonic() + 45
    while picker.pending is not None:
        assert time.monotonic() < deadline
        picker.poll_catalog(context)
        time.sleep(0.01)
    assert draft_dispatch.dumps(owner.draft) == before_intent
    assert context.scene.mechanical_cad.sketch_draft_json == before_saved
    return operator, picker


def pick_solid(context, owner, source_id, *, faces=None):
    before_scene = scene_capture(context)
    operator, picker = open_picker(context, owner, source_id)
    faces = faces or ["rim/face/cap.end", "rim/face/side.circle"]
    entry = next(row for row in picker.catalog[source_id] if row["faces"] == faces)
    saved = json.loads((ROOT / "examples/edge_projection_view.json").read_text())
    view = copy.deepcopy(saved["view"])
    center = (
        entry["circle"]["center"]
        if "circle" in entry
        else [(a + b) / 2 for a, b in zip(entry["points"][0], entry["points"][-1], strict=True)]
    )
    delta = (center[0] + 8) * 0.001
    delta_y = center[1] * 0.001
    translation = Matrix.Translation((-delta, -delta_y, 0))
    view["view_matrix"] = Matrix(view["view_matrix"]) @ translation
    view["window_matrix"] = Matrix(view["window_matrix"])
    view["perspective_matrix"] = view["window_matrix"] @ view["view_matrix"]
    view["view_location"][0] += delta
    view["view_location"][1] += delta_y
    picker.region = SimpleNamespace(**saved["region"])
    picker.rv3d = SimpleNamespace(**view)
    context.view_layer.update()
    selected = None
    for a, b in zip(entry["points"], entry["points"][1:], strict=False):
        point = (Vector(a) + Vector(b)) * 0.0005
        pixel = view3d_utils.location_3d_to_region_2d(picker.region, picker.rv3d, point)
        if pixel is None:
            continue
        with patch.object(picker, "hover_coordinates", return_value=pixel):
            picker.hover(context, None, accepting=True)
        if picker.hit == (source_id, *faces):
            selected = pixel
            break
    assert selected is not None, (source_id, picker.message)
    before = len(owner.commands.candidate()["features"][-1].get("projections", []))
    with patch.object(picker, "hover_coordinates", return_value=selected):
        assert operator.modal(context, SimpleNamespace(type="LEFTMOUSE", value="PRESS")) == {
            "FINISHED"
        }
    assert_scene(context, before_scene)
    wait(owner, context)
    target = next(
        f for f in owner.commands.candidate()["features"] if f["id"] == owner.commands.feature_id
    )
    assert len(target["projections"]) == before + 1
    return target["projections"][-1]["target"]


register()
if os.environ.get("MCAD_EARLIER_SOLID_REOPEN"):
    saved_path = Path(os.environ["MCAD_EARLIER_SOLID_REOPEN"])
    bpy.ops.wm.open_mainfile(filepath=str(saved_path))
    expected = json.loads(saved_path.with_suffix(".json").read_text())
    state = bpy.context.scene.mechanical_cad
    assert state.document_json == expected["document"]
    assert state.sketch_draft_json == expected["draft"]
    assert state.status == "DIRTY"
    assert not any(str(obj.get(OWNER_KEY, "")).startswith("review:") for obj in bpy.data.objects)
    assert not solid_review._REVIEWS and not face_pick._PICKERS
    window = bpy.context.window
    area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
    region = next(r for r in area.regions if r.type == "WINDOW")
    with bpy.context.temp_override(window=window, area=area, region=region):
        context = bpy.context
        document_state.regenerate(context)
        restored = draft_dispatch.restore(state.sketch_draft_json, state.document_json)
        owner = general_session.GeneralSession(context, restored=restored)
        owner.start()
        owner.check(context)
        wait(owner, context)
        assert owner.commands.candidate() == json.loads(expected["document"])
        target = next(
            f
            for f in owner.commands.candidate()["features"]
            if f["id"] == owner.commands.feature_id
        )
        assert target["inputs"] == expected["inputs"]
        geometry = owner.geometry()
        circles = {circle["id"]: circle for circle in owner.commands.sketch["circles"]}
        for identifier, coordinates in expected["centers"].items():
            assert geometry.points[circles[identifier]["center"]] == tuple(coordinates)
        # Active output is now the target sketch. Earlier-solid selection still
        # works, with no final solid mesh required and no hidden output switch.
        previous = scene_capture(context)
        operator, picker = open_picker(context, owner, "moved_two")
        assert operator.modal(context, SimpleNamespace(type="ESC")) == {"CANCELLED"}
        assert_scene(context, previous)
        owner.discard("Persistence verified")
    unregister()
    print("MCAD_EARLIER_SOLID_REOPEN_OK", flush=True)
    raise SystemExit(0)

window = bpy.context.window
area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
region = next(r for r in area.regions if r.type == "WINDOW")
with bpy.context.temp_override(window=window, area=area, region=region):
    context = bpy.context
    for obj in list(context.scene.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    state = context.scene.mechanical_cad
    document = {
        "schema_version": 2,
        "id": "multi_source_authoring",
        "name": "Multi-source authoring",
        "units": "mm",
        "parameters": {},
        "active_feature": "moved_one",
        "features": [
            source("source_one", 4),
            source("source_two", 14),
            {
                "id": "rim_profile",
                "kind": "sketch_circle",
                "label": "Rim profile",
                "params": {"radius": 10, "x": -12},
                "inputs": {},
            },
            {
                "id": "rim",
                "kind": "extrude",
                "label": "Rim",
                "params": {"length": 10},
                "inputs": {"profile": "rim_profile"},
            },
            {
                "id": "moved_one",
                "kind": "transform",
                "label": "Moved one",
                "params": {"x": 20},
                "inputs": {"base": "rim"},
            },
            {
                "id": "moved_two",
                "kind": "transform",
                "label": "Moved two",
                "params": {"x": 40},
                "inputs": {"base": "rim"},
            },
            {
                "id": "box_profile",
                "kind": "sketch_rectangle",
                "label": "Line source profile",
                "params": {"width": 10, "height": 10, "x": 60, "y": -5},
                "inputs": {},
            },
            {
                "id": "box",
                "kind": "extrude",
                "label": "Line source",
                "params": {"length": 10},
                "inputs": {"profile": "box_profile"},
            },
        ],
    }
    document_state._populate_document(context.scene, document)
    document_state.regenerate(context)
    owner = general_session.GeneralSession(context)
    owner.start()
    # Unrelated objects must not be hidden, selected, transformed or removed.
    unrelated = bpy.data.objects.new("Unrelated sentinel", None)
    context.scene.collection.objects.link(unrelated)
    unrelated.location = (3, 4, 5)
    unrelated.select_set(True)
    context.view_layer.objects.active = unrelated
    before_scene = scene_capture(context)
    before_draft = state.sketch_draft_json
    operator, picker = open_picker(context, owner, "moved_two")
    assert (
        unrelated.location[:] == (3, 4, 5) and unrelated.select_get() and not unrelated.hide_get()
    )
    picker.snapshot.obj.location.x += 1
    context.view_layer.update()
    try:
        picker.snapshot.bound_feature(
            context, picker.snapshot.obj, picker.snapshot.result(context, accepting=True)
        )
        raise AssertionError("Transformed temporary body authorized a pick")
    except ValueError:
        pass
    assert operator.modal(context, SimpleNamespace(type="ESC")) == {"CANCELLED"}
    assert_scene(context, before_scene)
    assert state.sketch_draft_json == before_draft
    # Changing units expires the owned temporary body and releases the sketch
    # immediately, even when no new modal event is delivered.
    operator, picker = open_picker(context, owner, "moved_two")
    scale = context.scene.unit_settings.scale_length
    context.scene.unit_settings.scale_length = scale * 2
    assert not picker.current(context)
    solid_review._supervise()
    assert picker.snapshot.closed and owner.solid_projection_picker is None
    context.scene.unit_settings.scale_length = scale
    assert_scene(context, before_scene)
    assert state.sketch_draft_json == before_draft
    # Legacy single-active-display picker remains usable without an overlay.
    legacy = solid_projection_picker.SolidProjectionPicker(context, owner)
    deadline = time.monotonic() + 45
    while legacy.pending is not None:
        assert time.monotonic() < deadline
        legacy.poll_catalog(context)
        time.sleep(0.01)
    assert not hasattr(legacy.snapshot, "source_id") and "moved_one" in legacy.catalog
    legacy.close()
    assert_scene(context, before_scene)
    for identifier in ("source_one", "source_two"):
        assert bpy.ops.mcad.project_sketch_geometry(
            source_sketch=identifier, source_entity="circle"
        ) == {"FINISHED"}
        wait(owner, context)
    first_solid = pick_solid(context, owner, "moved_one")
    target_id = owner.commands.feature_id
    feature = next(f for f in owner.commands.candidate()["features"] if f["id"] == target_id)
    assert feature["inputs"] == {
        "external": "source_one",
        "external_2": "source_two",
        "external_3": "moved_one",
    }
    owner.local_history(context)
    wait(owner, context)
    assert "external_3" not in owner.commands.candidate()["features"][-1]["inputs"]
    owner.suspend("Resume a multi-source projection draft")
    restored = draft_dispatch.restore(state.sketch_draft_json, state.document_json)
    owner = general_session.GeneralSession(context, restored=restored)
    owner.start()
    owner.local_history(context, redo=True)
    wait(owner, context)
    before_pick = state.document_json
    runtime = document_state.current_part_evidence(context)
    second_solid = pick_solid(context, owner, "moved_two")
    assert state.document_json == before_pick and state.active_feature == "moved_one"
    assert document_state.current_part_evidence(context) == runtime
    feature = next(f for f in owner.commands.candidate()["features"] if f["id"] == target_id)
    assert feature["inputs"] == {
        "external": "source_one",
        "external_2": "source_two",
        "external_3": "moved_one",
        "external_4": "moved_two",
    }
    geometry = owner.geometry()
    circles = {c["id"]: c for c in owner.commands.sketch["circles"]}
    assert geometry.points[circles[first_solid]["center"]] == (8, 0)
    assert geometry.points[circles[second_solid]["center"]] == (28, 0)
    assert feature["projections"][-2]["faces"] == feature["projections"][-1]["faces"]
    line = pick_solid(context, owner, "box", faces=["box/face/cap.end", "box/face/side.y_min"])
    feature = next(f for f in owner.commands.candidate()["features"] if f["id"] == target_id)
    assert feature["inputs"]["external_5"] == "box"
    assert feature["projections"][-1]["target"] == line
    assert "endpoint_faces" in feature["projections"][-1]
    finish(owner, context)
    saved = json.loads(state.document_json)
    owner = general_session.GeneralSession(context, target_id)
    owner.start()
    owner.check(context)
    wait(owner, context)
    assert owner.commands.candidate() == saved
    owner.checkpoint()  # Save ordinarily checkpoints the current UI intent too.
    before_scene = scene_capture(context)
    before_draft = state.sketch_draft_json
    operator, picker = open_picker(context, owner, "moved_two")
    with tempfile.TemporaryDirectory(prefix="mcad-earlier-solid-") as directory:
        path = Path(directory) / "sources.blend"
        expected = {
            "document": state.document_json,
            "draft": before_draft,
            "inputs": feature["inputs"],
            "centers": {first_solid: [8, 0], second_solid: [28, 0]},
        }
        path.with_suffix(".json").write_text(json.dumps(expected))
        assert bpy.ops.wm.save_as_mainfile(filepath=str(path)) == {"FINISHED"}
        assert picker.snapshot.closed and owner.solid_projection_picker is None
        assert_scene(context, before_scene)
        assert state.sketch_draft_json == before_draft
        child = subprocess.run(
            [
                bpy.app.binary_path,
                "--background",
                "--factory-startup",
                "--python-exit-code",
                "1",
                "--python",
                str(Path(__file__).resolve()),
            ],
            env=dict(os.environ, MCAD_EARLIER_SOLID_REOPEN=str(path)),
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert child.returncode == 0, child.stdout + child.stderr
        assert "MCAD_EARLIER_SOLID_REOPEN_OK" in child.stdout, child.stdout
        print(child.stdout, flush=True)
    owner.discard("Multi-source authoring smoke complete")
    assert json.loads(state.document_json) == saved
unregister()
print("MCAD_MULTI_SOURCE_AUTHORING_SMOKE_OK", flush=True)
