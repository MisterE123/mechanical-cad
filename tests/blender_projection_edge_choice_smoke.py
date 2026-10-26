"""Registered chooser ownership/retirement with real catalog; not a ray/GUI test."""

import copy
import json
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import bpy
from mathutils import Vector

ROOT = Path(os.environ["MCAD_ROOT"])
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import (  # noqa: E402
    document_state,
    general_session,
    register,
    registration,
    solid_projection_picker,
    unregister,
)

captured = []
original = solid_projection_picker.MCAD_OT_use_solid_edge.execute


def capture(self, context):
    result = original(self, context)
    if result == {"RUNNING_MODAL"}:
        captured.append(self)
    return result


solid_projection_picker.MCAD_OT_use_solid_edge.execute = capture


def wait(owner, context):
    deadline = time.monotonic() + 60
    while owner.pending is not None:
        assert time.monotonic() < deadline
        owner.tick(context)
        time.sleep(0.01)
    assert not owner.error, owner.error


register()
window = bpy.context.window
area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
region = next(r for r in area.regions if r.type == "WINDOW")
with bpy.context.temp_override(window=window, area=area, region=region):
    context = bpy.context
    state = context.scene.mechanical_cad
    source = json.loads((ROOT / "tests/fixtures/solid_arc_projection/source.json").read_text())
    document_state._populate_document(context.scene, source)
    document_state.regenerate(context)
    assert state.status == "READY", state.error
    accepted = state.document_json
    owner = general_session.GeneralSession(context)
    owner.start()

    def chooser():
        assert bpy.ops.mcad.use_solid_edge(source_solid="pad") == {"RUNNING_MODAL"}
        picker = captured[-1]._picker
        deadline = time.monotonic() + 60
        while picker.pending is not None:
            assert time.monotonic() < deadline
            picker.poll_catalog(context)
            time.sleep(0.01)
        entries = sorted((e for e in picker.catalog["pad"] if "arc" in e),
                         key=lambda e: e["arc"]["center"][2])
        assert len(entries) == 2
        picker.overlap_candidates = tuple(
            (0, "pad", entry, [Vector(p) * 0.001 for p in entry["points"]], picker.snapshot.obj)
            for entry in entries)
        picker.begin_choice(context)
        return picker

    # Cancel: no raw reference or authority ever enters authored intent.
    before = state.sketch_draft_json
    picker = chooser()
    choice = picker.edge_choice
    assert choice.selected is None
    picker.close()
    assert choice.retired and state.sketch_draft_json == before
    assert state.document_json == accepted

    # Both actual exact cap identities can independently author the arc, then undo.
    for index in (0, 1):
        picker = chooser()
        choice = picker.edge_choice
        clone = copy.copy(choice)
        try:
            clone.require(picker)
            raise AssertionError("Copied choice admitted")
        except ValueError:
            pass
        picker.choice_event(context, SimpleNamespace(type="LEFTMOUSE", value="RELEASE"))
        picker.choice_event(context, SimpleNamespace(type=("ONE", "TWO")[index], value="PRESS"))
        raw = json.loads(choice.rows[index][1])
        picker.apply_choice(context)
        assert choice.retired
        wait(owner, context)
        target = owner.commands.candidate()["features"][-1]
        assert target["projections"][0]["faces"] == raw["faces"]
        assert target["projections"][0]["kind"] == "arc"
        assert state.document_json == accepted
        try:
            picker.apply_choice(context)
            raise AssertionError("Repeated Apply admitted")
        except ValueError:
            pass
        owner.local_history(context)
        wait(owner, context)
        assert not owner.commands.sketch.get("arcs")

    # Exact owner slot replacement cannot validate, and no draft gets overwritten.
    picker = chooser()
    before = state.sketch_draft_json
    state.sketch_draft_json = before + " "
    try:
        picker.validate_choice(context)
        raise AssertionError("Stale draft admitted")
    except ValueError:
        pass
    picker.close()
    state.sketch_draft_json = before

    # Legacy displayed-body path must reject hidden/unlinked/replaced display
    # even when geometry is identical. This is still authority, not ray evidence.
    for change in ("hidden", "unlinked", "data"):
        picker = solid_projection_picker.SolidProjectionPicker(context, owner)
        deadline = time.monotonic() + 60
        while picker.pending is not None:
            assert time.monotonic() < deadline
            picker.poll_catalog(context)
            time.sleep(0.01)
        obj = next(o for o in context.visible_objects if picker.snapshot.owns(context, o))
        entries = [e for e in picker.catalog["pad"] if "arc" in e]
        picker.overlap_candidates = tuple(
            (0, "pad", e, [Vector(p) * 0.001 for p in e["points"]], obj) for e in entries)
        picker.begin_choice(context)
        choice = picker.edge_choice
        original_data = obj.data
        collections = tuple(obj.users_collection)
        if change == "hidden":
            obj.hide_set(True, view_layer=context.view_layer)
        elif change == "unlinked":
            for collection in collections:
                collection.objects.unlink(obj)
        else:
            obj.data = original_data.copy()
        context.view_layer.update()
        assert not picker.current(context) and choice.retired
        if change == "hidden":
            obj.hide_set(False, view_layer=context.view_layer)
        elif change == "unlinked":
            for collection in collections:
                collection.objects.link(obj)
        else:
            obj.data = original_data
        context.view_layer.update()
        assert not picker.current(context), "Restored display revived chooser authority"
        picker.close()
        assert state.sketch_draft_json == before

    # Exercise real registered save lifecycle: no chooser authority survives.
    picker = chooser()
    choice = picker.edge_choice
    registration._before_blend_save(None)
    assert choice.retired and picker.edge_choice is None
    assert state.document_json == accepted
    assert owner.solid_projection_picker is None
    assert "Choose Edge" not in state.sketch_draft_json
    registration._after_blend_save(None)

    picker = chooser()
    choice = picker.edge_choice
    registration._before_blend_load(None)
    assert choice.retired and picker.edge_choice is None
    assert state.document_json == accepted
assert "OCP" not in sys.modules and "slvs" not in sys.modules
unregister()
print("MCAD_PROJECTION_EDGE_CHOICE_OWNER_OK", flush=True)
