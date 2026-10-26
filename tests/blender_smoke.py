"""Real Blender/OCP integration test, not a bpy mock.

MCAD_ROOT=/path/to/repo MCAD_PYTHON=/path/to/repo/.venv/bin/python \
    blender --background --factory-startup --python tests/blender_smoke.py

Requires the repository sidecar environment; Blender imports no native CAD code.
"""

import json
import math
import os
import sys
import tempfile
from pathlib import Path

import bpy

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
os.environ["MCAD_ROOT"] = str(ROOT)
os.environ.setdefault("MCAD_PYTHON", str(ROOT / ".venv" / "bin" / "python"))
sys.path.insert(0, str(ROOT / "blender_addon"))
import mechanical_cad_blender as addon  # noqa: E402 - add-on path is configured above

checks = []


def check(condition, message):
    if not condition:
        raise AssertionError(message)
    checks.append(message)


def call(operator, **kwargs):
    outcome = operator(**kwargs)
    check(outcome == {"FINISHED"}, f"{operator.idname()} finished")


def cancelled(operator, **kwargs):
    try:
        result = operator(**kwargs)
    except RuntimeError:
        # bpy converts report({'ERROR'}, ...) into a Python exception in scripts.
        result = {"CANCELLED"}
    check(result == {"CANCELLED"}, f"{operator.idname()} rejected invalid input")


def state():
    return bpy.context.scene.mechanical_cad


def owned():
    return addon._owned_objects(bpy.context.scene)


def extent(axis):
    vertices = owned()[0].data.vertices
    return max(vertex.co[axis] for vertex in vertices) - min(vertex.co[axis] for vertex in vertices)


def parameter(name):
    return next(row for row in state().parameters if row.key == name)


def assert_close(actual, expected):
    check(
        math.isclose(actual, expected, rel_tol=1e-5, abs_tol=1e-7),
        f"{actual:g} matches {expected:g}",
    )


addon.register()
addon.register()
check(hasattr(bpy.types.Scene, "mechanical_cad"), "Repeated register is safe")
user_objects = {obj.name for obj in bpy.context.scene.objects}

call(bpy.ops.mcad.new_demo)
check(state().status == "READY", "Demo replay succeeds")
check(len(owned()) == 1, "Demo owns exactly one display object")
check(len(state().features) == 5, "Demo exposes five history entries")
check(
    all(row.status == "ok" for row in state().features),
    "All demo feature statuses are visible and successful",
)
check(
    owned()[0][addon.FEATURE_KEY] == "body", "Display is associated with stable active feature ID"
)
assert_close(extent(0), 0.04)
assert_close(extent(1), 0.03)
assert_close(extent(2), 0.01)
assert_close(state().volume, (40 * 30 - math.pi * 4 * 4) * 10)
object_identity = owned()[0].as_pointer()

parameter("width").value = 60
check(state().status == "DIRTY", "Parameter edit marks document dirty")
check(owned()[0].hide_viewport, "Dirty display is hidden until regenerated")
call(bpy.ops.mcad.regenerate)
assert_close(extent(0), 0.06)
check(len(owned()) == 1, "Editing and replay do not accumulate displays")
check(
    owned()[0].as_pointer() == object_identity,
    "Successful replay preserves display object identity",
)
assert_close(state().volume, (60 * 30 - math.pi * 4 * 4) * 10)

with tempfile.TemporaryDirectory(prefix="mechanical_cad_blender_") as directory:
    path = Path(directory) / "roundtrip.mcad.json"
    call(bpy.ops.mcad.save_document, filepath=str(path))
    saved = json.loads(path.read_text())
    check(saved["parameters"]["width"] == 60, "Save records edited parameter")
    check("mesh" not in path.read_text(), "Saved history contains no disposable mesh")
    saved_id = saved["id"]
    parameter("width").value = 80
    call(bpy.ops.mcad.regenerate)
    call(bpy.ops.mcad.load_document, filepath=str(path))
    check(json.loads(state().document_json)["id"] == saved_id, "Reload preserves document ID")
    assert_close(parameter("width").value, 60)
    assert_close(extent(0), 0.06)
    check(len(owned()) == 1, "Reload leaves one owned display")

    owned()[0].data.vertices[0].co.x += 1.0
    owned()[0].delta_scale = (20, 20, 20)
    parameter("width").value = -1
    call(bpy.ops.mcad.regenerate)
    check(state().status == "FAILED", "Invalid dimension produces a failure state")
    check(
        len(owned()) == 1 and owned()[0].get("mechanical_cad_stale"),
        "Failed replay preserves a clearly marked last-good cache",
    )
    check(
        owned()[0].display_type == "WIRE" and owned()[0].name.startswith("STALE"),
        "Last-good cache is unmistakably wireframe and named stale",
    )
    check(
        owned()[0].hide_render and state().volume == 0,
        "Failed cache is not rendered or reported as current volume",
    )
    assert_close(extent(0), 0.06)
    check(
        tuple(owned()[0].delta_scale) == (1.0, 1.0, 1.0),
        "Stale cache restores canonical geometry and transforms despite manual display edits",
    )
    check(bool(state().error), "Failure has a user-readable error")
    check(any(row.status == "failed" for row in state().features), "Failed feature is identified")
    check(
        any(row.status == "blocked" for row in state().features),
        "Dependent features are shown blocked",
    )
    parameter("width").value = 60
    call(bpy.ops.mcad.regenerate)
    check(len(owned()) == 1, "Correcting a dimension recovers the model")
    check(
        not owned()[0].get("mechanical_cad_stale") and owned()[0].display_type == "TEXTURED",
        "Successful replay restores normal display",
    )

    document_before = state().document_json
    bad = Path(directory) / "invalid.mcad.json"
    bad.write_text('{"schema_version": 900, "bad": true}')
    cancelled(bpy.ops.mcad.load_document, filepath=str(bad))
    check(
        state().document_json == document_before,
        "Rejected load preserves previous authoritative document",
    )
    check(
        len(owned()) == 1 and state().status == "READY",
        "Rejected load preserves valid current display",
    )
    call(bpy.ops.mcad.regenerate)

    for invalid_json, expected_message in [
        ('{"schema_version":1,"schema_version":1}', "Duplicate JSON key"),
        ('{"value":NaN}', "Non-finite JSON"),
    ]:
        strict_path = Path(directory) / "strict_invalid.mcad.json"
        strict_path.write_text(invalid_json)
        previous_document = state().document_json
        cancelled(bpy.ops.mcad.load_document, filepath=str(strict_path))
        check(
            expected_message in state().last_action_error,
            "Strict file loader rejects ambiguous or non-finite JSON",
        )
        check(
            state().document_json == previous_document and len(owned()) == 1,
            "Strict file rejection preserves current model",
        )

    # Edit-mode geometry is never the CAD source of truth.
    owned()[0].data.vertices[0].co.x += 1.0
    call(bpy.ops.mcad.regenerate)
    assert_close(extent(0), 0.06)

    # Build a fresh part using only UI operators, with explicit operand selection.
    call(bpy.ops.mcad.new_document, name="Fresh UI part")
    check(state().status == "READY" and len(state().features) == 0, "Blank document is usable")
    call(bpy.ops.mcad.add_rectangle, width=40, height=30, x=0, y=0, z=0)
    rectangle_id = state().active_feature
    # Help controls are properties on the same authoring operator. Exercise
    # real OperatorProperties callbacks, where Python-only class attrs vanish.
    draft = bpy.context.window_manager.operator_properties_last("mcad.add_rectangle")
    draft.width = 100
    before_help = state().document_json
    draft.show_help = True
    draft.help_next = True
    check(
        draft.help_page == 2 and draft.width == 100,
        "In-dialog help Next preserves draft dimensions",
    )
    draft.help_previous = True
    draft.show_help = False
    check(
        draft.help_page == 1 and draft.width == 100,
        "In-dialog help Previous and collapse preserve draft dimensions",
    )
    check(state().document_json == before_help, "Help controls never alter saved CAD history")
    check(len(owned()) == 1, "New sketch has a viewport preview")
    call(bpy.ops.mcad.add_extrude, profile=rectangle_id, length=10)
    pad_id = state().active_feature
    call(bpy.ops.mcad.add_circle, radius=4, x=20, y=15, z=0)
    circle_id = state().active_feature
    call(bpy.ops.mcad.add_extrude, profile=circle_id, length=10)
    tool_id = state().active_feature
    call(bpy.ops.mcad.add_cut, base=pad_id, tool=tool_id)
    valid_document = state().document_json
    valid_identity = owned()[0].as_pointer()
    cancelled(bpy.ops.mcad.add_cut, base=tool_id, tool=pad_id)
    check(
        state().document_json == valid_document,
        "Rejected feature creation leaves no broken history",
    )
    check(
        owned()[0].as_pointer() == valid_identity and state().status == "READY",
        "Rejected feature creation preserves current solid",
    )
    check(state().status == "READY", "Fresh rectangle/extrude/circle/extrude/cut workflow succeeds")
    assert_close(state().volume, (40 * 30 - math.pi * 4 * 4) * 10)
    parameter(f"{rectangle_id}_width").value = 50
    call(bpy.ops.mcad.regenerate)
    assert_close(extent(0), 0.05)
    bpy.context.scene.unit_settings.scale_length = 0.01
    call(bpy.ops.mcad.regenerate)
    assert_close(extent(0), 5.0)
    assert_close(extent(0) * bpy.context.scene.unit_settings.scale_length, 0.05)
    bpy.context.scene.unit_settings.scale_length = 1.0
    call(bpy.ops.mcad.regenerate)
    assert_close(extent(0), 0.05)
    check(len(owned()) == 1, "Fresh feature edits preserve a single output")
    fresh_path = Path(directory) / "fresh.mcad.json"
    call(bpy.ops.mcad.save_document, filepath=str(fresh_path))
    call(bpy.ops.mcad.new_demo)
    call(bpy.ops.mcad.load_document, filepath=str(fresh_path))
    check(state().document_name == "Fresh UI part", "Fresh authored part saves and reopens")
    assert_close(extent(0), 0.05)

    state().feature_index = 0
    call(bpy.ops.mcad.activate_feature)
    check(
        owned()[0][addon.FEATURE_KEY] == rectangle_id, "History selection can show a prior sketch"
    )
    state().feature_index = len(state().features) - 1
    call(bpy.ops.mcad.activate_feature)
    assert_close(extent(2), 0.01)

    # Object transforms and deformations cannot masquerade as canonical CAD.
    display = owned()[0]
    parent = next(
        obj for obj in bpy.context.scene.objects if obj.name in user_objects and obj.type == "MESH"
    )
    display.parent = parent
    display.delta_scale = (20, 20, 20)
    display.modifiers.new("Non-authoritative array", "ARRAY")
    display.constraints.new("COPY_SCALE").target = parent
    call(bpy.ops.mcad.regenerate)
    check(
        display.parent is None and not display.constraints and not display.modifiers,
        "Replay removes non-authoritative parenting and deformations",
    )
    check(tuple(display.delta_scale) == (1.0, 1.0, 1.0), "Replay resets delta transforms")
    bpy.context.view_layer.update()
    assert_close(display.dimensions.x, 0.05)

    # Sharing the output into another scene must not authorize its deletion.
    other_scene = bpy.data.scenes.new("Unrelated linked scene")
    shared_display = owned()[0]
    shared_data = shared_display.data
    other_scene.collection.objects.link(shared_display)
    call(bpy.ops.mcad.regenerate)
    check(
        shared_display.name in other_scene.objects,
        "Regeneration preserves another scene's linked object",
    )
    check(
        shared_display.data == shared_data,
        "Regeneration does not replace another scene's linked mesh",
    )
    check(owned()[0] != shared_display, "Current scene gets an independent regenerated display")
    bpy.data.scenes.remove(other_scene)

    # Formula rows remain formula text; numeric edits cannot silently flatten them.
    document = json.loads(state().document_json)
    document["parameters"][f"{rectangle_id}_height"] = f"{rectangle_id}_width / 2"
    formula_path = Path(directory) / "formula.mcad.json"
    formula_path.write_text(json.dumps(document))
    call(bpy.ops.mcad.load_document, filepath=str(formula_path))
    formula = parameter(f"{rectangle_id}_height")
    check(formula.is_expression, "Expression-valued parameters are preserved")
    assert_close(extent(1), 0.025)
    formula.expression = f"{rectangle_id}_width / 2 + 5"
    call(bpy.ops.mcad.regenerate)
    assert_close(extent(1), 0.03)

    # Blender FloatProperty is float32: untouched numbers must stay exact in JSON.
    precise = 12.3456789012345
    document = json.loads(state().document_json)
    document["parameters"]["untouched_precision"] = precise
    precise_path = Path(directory) / "precision.mcad.json"
    precise_path.write_text(json.dumps(document))
    call(bpy.ops.mcad.load_document, filepath=str(precise_path))
    parameter(f"{rectangle_id}_width").value = 60
    check(
        json.loads(state().document_json)["parameters"]["untouched_precision"] == precise,
        "Editing one parameter preserves other JSON numeric precision",
    )
    call(bpy.ops.mcad.regenerate)

    # Formula toggle preserves meaning instead of introducing blank/zero values.
    width_parameter = parameter(f"{rectangle_id}_width")
    width_parameter.is_expression = True
    check(width_parameter.expression == "60.0", "Numeric to formula toggle preserves its value")
    call(bpy.ops.mcad.regenerate)
    width_parameter.is_expression = False
    assert_close(json.loads(state().document_json)["parameters"][width_parameter.key], 60)
    call(bpy.ops.mcad.regenerate)

    width_parameter.value = 70
    width_parameter.is_expression = True
    check(
        width_parameter.expression == "70.0",
        "Numeric-to-formula always uses the latest numeric value",
    )
    call(bpy.ops.mcad.regenerate)
    dependent = parameter(f"{rectangle_id}_height")
    width_parameter.expression = "80.0"
    before_formula = dependent.expression
    dependent.is_expression = False
    check(
        dependent.is_expression and dependent.expression == before_formula,
        "Dirty upstream dependency blocks stale formula-to-number conversion",
    )
    call(bpy.ops.mcad.regenerate)

    # Shared collections reject replacement before canonical state changes.
    collection = bpy.data.collections.new("Shared CAD test collection")
    bpy.context.scene.collection.children.link(collection)
    display = owned()[0]
    bpy.context.scene.collection.objects.unlink(display)
    collection.objects.link(display)
    second_scene = bpy.data.scenes.new("Shared collection scene")
    second_scene.collection.children.link(collection)
    before_document = state().document_json
    cancelled(bpy.ops.mcad.new_document, name="Must not replace")
    check(
        state().document_json == before_document,
        "Shared collection conflict preserves canonical document",
    )
    check(
        display.name in second_scene.objects,
        "Shared collection conflict preserves other scene's display",
    )
    second_scene.collection.children.unlink(collection)
    bpy.data.scenes.remove(second_scene)
    bpy.context.scene.collection.objects.link(display)
    collection.objects.unlink(display)
    bpy.context.scene.collection.children.unlink(collection)
    bpy.data.collections.remove(collection)

    # A document may have features without a selected active output.
    no_active = json.loads(state().document_json)
    no_active["active_feature"] = None
    no_active_path = Path(directory) / "no_active.mcad.json"
    no_active_path.write_text(json.dumps(no_active))
    call(bpy.ops.mcad.load_document, filepath=str(no_active_path))
    check(
        state().status == "READY" and not owned(),
        "Nonempty document with no active output loads validly",
    )
    state().feature_index = len(state().features) - 1
    call(bpy.ops.mcad.activate_feature)

    # Simulate saved .blend restoration without starting a second UI process.
    addon._on_blend_load(None)
    check(
        state().status == "DIRTY" and owned()[0].hide_viewport,
        "Blend restore requires regeneration before trusting cached display",
    )
    call(bpy.ops.mcad.regenerate)

# Sub-millimetre dimensions must survive Blender float32 far from the origin.
call(bpy.ops.mcad.new_document, name="Distant small part")
call(bpy.ops.mcad.add_rectangle, width=0.1, height=0.1, x=1_000_000, y=1_000_000, z=1_000_000)
distant_profile = state().active_feature
call(bpy.ops.mcad.add_extrude, profile=distant_profile, length=0.1)
bpy.context.view_layer.update()
for size in owned()[0].dimensions:
    assert_close(size * 1000, 0.1)
check(
    bool(state().last_action_error), "Distant small part surfaces global viewport precision warning"
)

check(
    user_objects.issubset({obj.name for obj in bpy.context.scene.objects}),
    "Every unrelated user object is preserved",
)
check(
    not any(name == "OCP" or name.startswith("OCP.") for name in sys.modules),
    "Blender never imports OCP",
)
check(
    not any(name == "mechanical_cad" or name.startswith("mechanical_cad.") for name in sys.modules),
    "Core code remains isolated outside Blender",
)
count_before = len(bpy.data.objects)
addon.unregister()
addon.unregister()
check(not hasattr(bpy.types.Scene, "mechanical_cad"), "Repeated unregister is safe")
# A late registration failure must leave no partial property/handler/timer.
original_rebind = addon._rebind_existing_documents


def failing_rebind():
    raise RuntimeError("Injected registration failure")


addon._rebind_existing_documents = failing_rebind
try:
    addon.register()
except RuntimeError as exc:
    check("Injected registration failure" in str(exc), "Registration failure is surfaced")
else:
    raise AssertionError("Injected registration failure was not raised")
finally:
    addon._rebind_existing_documents = original_rebind
check(not hasattr(bpy.types.Scene, "mechanical_cad"), "Failed registration removes Scene property")
check(
    addon._on_blend_load not in bpy.app.handlers.load_post
    and not bpy.app.timers.is_registered(addon._deferred_rebind),
    "Failed registration removes handlers and deferred timer",
)
addon.register()
check(len(bpy.data.objects) == count_before, "Registration lifecycle does not duplicate objects")
check(bool(state().document_json), "Registration lifecycle preserves scene document data")
call(bpy.ops.mcad.regenerate)
check(len(owned()) == 1, "Regeneration after re-registration preserves one output")
parameter("rectangle_1_width").value = 0.2
check(state().status == "DIRTY", "Re-registered parameter callbacks mark retained documents dirty")
call(bpy.ops.mcad.regenerate)
assert_close(extent(0) * 1000, 0.2)
print(
    "MCAD_BLENDER_SMOKE_RESULT="
    + json.dumps(
        {
            "ok": True,
            "blender": bpy.app.version_string,
            "checks": checks,
            "check_count": len(checks),
        }
    )
)
addon.unregister()
