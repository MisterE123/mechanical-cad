"""Real display/selection identity and reopen; no assembly geometry edits or motion Apply."""
import hashlib
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import bpy

ROOT = Path(os.environ["MCAD_ROOT"])
OUT = Path(os.environ["MCAD_SELECTION_OUT"])
MODE = os.environ.get("MCAD_SELECTION_MODE", "create")
sys.path.insert(0, str(ROOT / "blender_addon"))
sys.path.insert(0, str(ROOT / "tests"))
from blender_async_helpers import replay_assembly  # noqa: E402
from mechanical_cad_blender import assembly_component_context as component  # noqa: E402
from mechanical_cad_blender import assembly_display as display  # noqa: E402
from mechanical_cad_blender import assembly_operators, assembly_state, register  # noqa: E402

register()
OUT.mkdir(parents=True, exist_ok=True)
checks = []


def check(value, text):
    assert value, text
    checks.append(text)
    print("COMPONENT_SELECTION_CHECK", text, flush=True)


def state():
    return bpy.context.scene.mechanical_cad_assembly


def document():
    return json.loads(state().document_json)


def resolved():
    value = component.selected_component(bpy.context, document())
    return value["id"] if value else None


def meshes():
    return {obj.get(display.INSTANCE_KEY): obj for obj in display.owned_objects(bpy.context.scene, state().owner_id) if obj.get(display.ROLE_KEY) == "instance"}


def select(*objects, active=None):
    for obj in bpy.context.view_layer.objects:
        obj.select_set(False)
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = active
    bpy.context.view_layer.update()


def accepted():
    bpy.context.view_layer.update()
    rows = []
    for obj in display.owned_objects(bpy.context.scene, state().owner_id):
        mesh = None if obj.type != "MESH" else ([list(v.co) for v in obj.data.vertices], [list(p.vertices) for p in obj.data.polygons])
        rows.append((obj.name, [list(row) for row in obj.matrix_world], mesh))
    return state().document_json, state().report_json, hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()


if MODE == "reopen":
    check(bpy.ops.wm.open_mainfile(filepath=str(OUT / "selection.blend")) == {"FINISHED"}, "Fresh process loads selection file")
    check(state().document_json == (OUT / "accepted.json").read_text(), "Canonical model preserved on reopen")
    check(bpy.context.view_layer.objects.active.get(display.INSTANCE_KEY) == "b", "Native selected b persists")
    check(resolved() is None, "Reopened selection has no trusted currentness until Replay")
    check(replay_assembly() == {"FINISHED"}, "Explicit replay restores trusted display")
    # Replay replaces disposable objects; assert saved selected identity restoration
    # if supported, otherwise make a fresh native selection of its new b object.
    b = meshes()["b"]
    select(b, active=b)
    check(resolved() == "b", "Fresh native b selection resolves after replay")
    marker = "ASSEMBLY_COMPONENT_REOPEN_OK"
else:
    check(bpy.ops.mcad.assembly_load(filepath=str(ROOT / "examples/reused_blocks.mcad-assembly.json")) == {"FINISHED"}, "Load existing assembly baseline")
    check(assembly_state.display_is_current(bpy.context), "Baseline has trusted current display")
    baseline = accepted()
    objects = meshes()
    a, b = objects["a"], objects["b"]
    check(bpy.ops.mcad.assembly_select(part_id="block", instance_id="a") == {"FINISHED"}, "Named row selects a")
    check(state().selected_instance_id == "a" and resolved() == "a", "Row a resolves")
    select(b, active=b)
    check(state().selected_instance_id == "a" and resolved() == "b", "Native b wins over cached a")
    # Exercise real registered RNA invoke defaults without showing a headless popup
    # or executing the insert operation. The context forwards all real ports except WM.
    original_invoke = assembly_operators.MCAD_OT_assembly_insert.invoke
    original_execute = assembly_operators.MCAD_OT_assembly_insert.execute

    class DialogContext:
        window_manager = SimpleNamespace(invoke_props_dialog=lambda *args, **kwargs: {"RUNNING_MODAL"})

        def __getattr__(self, name):
            return getattr(bpy.context, name)

    def inspect_invoke(self, context):
        check(original_invoke(self, DialogContext(), None) == {"RUNNING_MODAL"}, "Registered Insert invoke prepares dialog only")
        check(self.parent == "b" and self.part_id == "block", "Insert defaults to current b not cached a")
        return {"CANCELLED"}

    assembly_operators.MCAD_OT_assembly_insert.execute = inspect_invoke
    try:
        check(bpy.ops.mcad.assembly_insert() == {"CANCELLED"}, "Inspected Insert cancels without executing geometry")
    finally:
        assembly_operators.MCAD_OT_assembly_insert.execute = original_execute
    check(accepted() == baseline, "Selection and dialog defaults preserve canonical/report/mesh poses")
    select(a, b, active=b)
    check(resolved() is None, "Multiple components refuse contextual target")
    foreign = bpy.data.objects["Cube"]
    select(b, foreign, active=b)
    check(resolved() is None, "Foreign selected mesh refuses contextual target")
    select(b, active=None)
    check(resolved() is None, "No active object refuses contextual target")
    select(active=b)
    check(resolved() is None, "Unselected active b refuses contextual target")
    select(b, active=b)
    original_json = state().document_json
    state().document_json += " "
    check(resolved() is None, "Stale document/display binding refuses target")
    state().document_json = original_json
    check(resolved() == "b", "Exact original binding restores current selection")
    # Spoof duplicate tags on the pre-existing foreign Cube, never duplicate or
    # modify accepted geometry. Restore every original property afterwards.
    old_tags = dict(foreign.items())
    for key, value in b.items():
        foreign[key] = value
    try:
        check(resolved() is None, "Unselected spoof duplicate invalidates trusted display")
    finally:
        for key in list(foreign.keys()):
            if key not in old_tags:
                del foreign[key]
        for key, value in old_tags.items():
            foreign[key] = value
    check(bpy.ops.mcad.assembly_select(part_id="block", instance_id="a") == {"FINISHED"}, "Named row selection remains available")
    check(resolved() == "a", "Named row a still resolves after refusal tests")
    select(b, active=b)
    check(resolved() == "b" and accepted() == baseline, "Final b selection preserves all accepted geometry and poses")
    (OUT / "accepted.json").write_text(state().document_json)
    check(bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "selection.blend")) == {"FINISHED"}, "Save selection-only fixture")
    marker = "ASSEMBLY_COMPONENT_SELECTION_OK"
check(not any(name == "OCP" or name.startswith("OCP.") for name in sys.modules), "No native kernel in Blender")
(OUT / (MODE + "-checks.json")).write_text(json.dumps(checks, indent=2))
print(marker, len(checks), flush=True)
