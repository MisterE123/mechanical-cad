"""Current component selection outranks stale presentation IDs at UI/invoke seams."""

import ast
import copy
import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from test_assembly_workflow_ui import Layout

ROOT = Path(__file__).resolve().parents[2]


class BaseEdit:
    def invoke(self, context, event):
        return {"RUNNING_MODAL"}

    def capture_dialog(self, context):
        pass

    def report(self, level, text):
        self.error = text


@pytest.fixture
def routes():
    data = json.loads((ROOT / "examples/reused_blocks.mcad-assembly.json").read_text())
    state = NS(selected_instance_id="a", selected_part_id="block", selected_joint_id="slide_a")
    selected = [next(row for row in data["instances"] if row["id"] == "b")]
    removed, resolved = [], []

    def component(context, document):
        assert document is data
        resolved.append(1)
        return selected[0]

    def remove(document, identifier):
        removed.append(identifier)
        return copy.deepcopy(document), {"removed": identifier}

    namespace = {
        "AssemblyEdit": BaseEdit,
        "Operator": type("Operator", (), {}),
        "assembly": lambda context: data,
        "state": lambda context: state,
        "selected_component": component,
        "bridge": NS(BridgeError=ValueError),
        "edit": NS(remove_component=remove),
        "reject": lambda *args: {"CANCELLED"},
        "rows": lambda context, name: data[name],
        "saved_coordinates": lambda document: {
            j["id"]: j["coordinate"] for j in document["joints"]
        },
        "unit_text": lambda value, kind: str(value),
        "load_extra_joint_fields": lambda *args: None,
        "message": lambda layout, context, text: layout.label(text=text),
        "assembly_state": NS(display_is_current=lambda context: True),
        "assembly_operators": NS(working_part_capture_reason=lambda context: ""),
    }
    path = ROOT / "blender_addon/mechanical_cad_blender/assembly_operators.py"
    tree = ast.parse(path.read_text())
    classes = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name in {
            "MCAD_OT_assembly_insert",
            "MCAD_OT_assembly_remove_component",
            "MCAD_OT_assembly_joint",
        }:
            node.body = [
                item
                for item in node.body
                if isinstance(item, ast.FunctionDef) and item.name in {"invoke", "prepare"}
            ]
            node.decorator_list = []
            classes.append(node)
    exec(compile(ast.Module(body=classes, type_ignores=[]), str(path), "exec"), namespace)
    path = ROOT / "blender_addon/mechanical_cad_blender/assembly_ui.py"
    draw = next(
        node
        for node in ast.parse(path.read_text()).body
        if isinstance(node, ast.FunctionDef) and node.name == "_instance_details"
    )
    exec(compile(ast.Module(body=[draw], type_ignores=[]), str(path), "exec"), namespace)
    context = NS(window_manager=NS(invoke_props_dialog=lambda *args, **kwargs: {"RUNNING_MODAL"}))
    return NS(
        ns=namespace,
        data=data,
        state=state,
        selected=selected,
        removed=removed,
        resolved=resolved,
        context=context,
    )


def test_instances_panel_follows_current_b_not_cached_a_without_writes(routes):
    r = routes
    before, cached = copy.deepcopy(r.data), vars(r.state).copy()
    layout = Layout()
    r.ns["_instance_details"](layout, r.context, r.data)
    buttons = [event for event in layout.events if event[0] == "operator"]
    selected = [
        event[4].instance_id
        for event in buttons
        if event[1] == "mcad.assembly_select" and event[2]["depress"]
    ]
    assert selected == ["b"]
    remove = next(event for event in buttons if event[1] == "mcad.assembly_remove_component")
    assert remove[4].instance_id == "b"
    move = next(event for event in buttons if event[2].get("text") == "Place / Edit Component")
    assert move[4].joint_id == "slide_b"
    assert r.data == before and vars(r.state) == cached and len(r.resolved) == 1


@pytest.mark.parametrize("selected", [True, False])
def test_generic_operator_defaults_follow_current_component_not_cache(routes, selected):
    r = routes
    if not selected:
        r.selected[0] = None
    before, cached = copy.deepcopy(r.data), vars(r.state).copy()
    insert = r.ns["MCAD_OT_assembly_insert"]()
    insert.part_id, insert.parent = "", "a"
    insert.properties = NS(is_property_set=lambda key: False)
    assert insert.invoke(r.context, None) == {"RUNNING_MODAL"}
    assert insert.parent == ("b" if selected else "root")
    assert insert.part_id == "block"
    remove = r.ns["MCAD_OT_assembly_remove_component"]()
    remove.instance_id = ""
    assert remove.invoke(r.context, None) == ({"RUNNING_MODAL"} if selected else {"CANCELLED"})
    assert r.removed == (["b"] if selected else [])
    joint = r.ns["MCAD_OT_assembly_joint"]()
    joint.joint_id, joint.lower, joint.upper = "", "", ""
    assert joint.invoke(r.context, None) == ({"RUNNING_MODAL"} if selected else {"CANCELLED"})
    assert joint.joint_id == ("slide_b" if selected else "")
    assert r.data == before and vars(r.state) == cached


def test_named_row_explicit_targets_still_work_without_viewport_component(routes):
    r = routes
    r.selected[0] = None
    before, cached = copy.deepcopy(r.data), vars(r.state).copy()
    insert = r.ns["MCAD_OT_assembly_insert"]()
    insert.part_id, insert.parent = "explicit_part", "a"
    insert.properties = NS(is_property_set=lambda key: True)
    assert insert.invoke(r.context, None) == {"RUNNING_MODAL"}
    assert (insert.part_id, insert.parent) == ("explicit_part", "a")
    remove = r.ns["MCAD_OT_assembly_remove_component"]()
    remove.instance_id = "a"
    assert remove.invoke(r.context, None) == {"RUNNING_MODAL"} and r.removed == ["a"]
    joint = r.ns["MCAD_OT_assembly_joint"]()
    joint.joint_id, joint.lower, joint.upper = "slide_a", "", ""
    assert joint.invoke(r.context, None) == {"RUNNING_MODAL"} and joint.joint_id == "slide_a"
    assert len(r.resolved) == 1  # Insert checks context; explicit Remove/Joint do not need it.
    assert r.data == before and vars(r.state) == cached
