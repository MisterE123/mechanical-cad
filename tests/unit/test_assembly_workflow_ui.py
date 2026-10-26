"""The connected project actions stay visible without running CAD from draw."""

import ast
import copy
import json
from pathlib import Path
from types import SimpleNamespace

from test_assembly_gears import gears, mechanism

ROOT = Path(__file__).resolve().parents[2]


class Layout:
    def __init__(self, events=None):
        self.events = [] if events is None else events
        self.enabled = True

    def box(self):
        return Layout(self.events)

    def row(self, **_kwargs):
        return Layout(self.events)

    def column(self, **_kwargs):
        return Layout(self.events)

    def label(self, **values):
        self.events.append(("label", values))

    def operator(self, identifier, **values):
        properties = SimpleNamespace()
        self.events.append(("operator", identifier, values, self.enabled, properties))
        return properties


def draw_controls(reason="", *, display_current=True, assembly=None):
    source = ROOT / "blender_addon/mechanical_cad_blender/assembly_ui.py"
    tree = ast.parse(source.read_text())
    names = {"_part_details", "_instance_details", "_joint_details"}
    body = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    data = json.loads((ROOT / "examples/reused_blocks.mcad-assembly.json").read_text())
    if assembly is not None:
        data = copy.deepcopy(assembly)
    current = SimpleNamespace(
        selected_part_id=data["parts"][0]["id"],
        selected_instance_id=data["grounded_instance"],
        selected_joint_id="",
        report_json="",
    )
    coordinates = {}
    coordinate_source = ROOT / "blender_addon/mechanical_cad_blender/assembly_coordinates.py"
    exec(compile(coordinate_source.read_text(), str(coordinate_source), "exec"), coordinates)
    namespace = {
        "NO_SCALAR_COORDINATE": coordinates["NO_SCALAR_COORDINATE"],
        "extra_names": coordinates["extra_names"],
        "json": json,
        "saved_coordinates": gears.saved_coordinates,
        "controlling_joint": gears.controlling_joint,
        "state": lambda _context: current,
        "selected_component": lambda _context, rows: next(
            (row for row in rows["instances"] if row["id"] == current.selected_instance_id), None
        ),
        "assembly_operators": SimpleNamespace(working_part_capture_reason=lambda _: reason),
        "assembly_state": SimpleNamespace(display_is_current=lambda _: display_current),
        "message": lambda layout, _context, text: layout.label(text=text),
        "unit_text": lambda value, _kind: str(value),
    }
    exec(compile(ast.Module(body=body, type_ignores=[]), str(source), "exec"), namespace)
    layout = Layout()
    for name in sorted(names):
        namespace[name](layout, object(), data)
    return layout.events, data


def test_project_actions_expose_capture_reuse_source_edit_and_joint_position():
    events, data = draw_controls()
    operators = [event for event in events if event[0] == "operator"]
    capture = next(event for event in operators if event[2].get("text") == "Add Working Part")
    reuse = next(event for event in operators if event[2].get("text") == "Reuse a Part")
    source = next(event for event in operators if event[2].get("text") == "Edit Part / Export Part")
    assert capture[1] == reuse[1] == "mcad.assembly_insert"
    assert capture[3] is True and capture[4].use_working_part is True
    assert not hasattr(reuse[4], "use_working_part")
    assert source[1] == "mcad.assembly_open_part"
    assert source[4].part_id == data["parts"][0]["id"]
    assert any(
        event[1] == "mcad.assembly_joint" and event[2]["text"] == "Edit" for event in operators
    )
    labels = [event[1]["text"] for event in events if event[0] == "label"]
    assert any("Update All Instances" in label for label in labels)
    assert any(label.startswith("Frames:") for label in labels)


def test_unsupported_working_part_does_not_disable_accepted_part_reuse():
    events, _ = draw_controls("This source has no supported solid output")
    operators = {event[2].get("text"): event for event in events if event[0] == "operator"}
    assert operators["Add Working Part"][3] is False
    assert operators["Reuse a Part"][3] is True
    assert operators["Edit Part / Export Part"][3] is True
    explanation = next(
        e for e in events if e[0] == "operator" and e[1] == "mcad.assembly_status_details"
    )
    assert explanation[3] is True  # Explanation stays clickable beside disabled Add.


def test_visual_joint_controls_require_current_display_and_retain_advanced_joint_edit():
    for current in (False, True):
        events, data = draw_controls(display_current=current)
        operators = [event for event in events if event[0] == "operator"]
        placement = next(
            event for event in operators if event[2].get("text") == "Place Joint in Viewport"
        )
        assert placement[1] == "mcad.assembly_visual_joint"
        assert placement[3] is current
        edits = [
            event for event in operators if event[2].get("text") == "Edit Connectors in Viewport"
        ]
        assert len(edits) == len(data["joints"])
        for event, joint in zip(edits, data["joints"], strict=True):
            assert event[4].joint_id == joint["id"]
            assert event[3] is (current and joint["kind"] in {"fixed", "slider"})
        assert any(event[1] == "mcad.assembly_joint" for event in operators)


def test_geared_motion_controls_name_and_target_independent_driver_only():
    for current in (False, True):
        events, data = draw_controls(display_current=current, assembly=mechanism().to_dict())
        controls = [
            event
            for event in events
            if event[0] == "operator" and event[1] == "mcad.assembly_visual_joint"
        ]
        motions = [event for event in controls if getattr(event[4], "motion_only", False)]
        assert len(motions) == 3
        assert all(event[4].joint_id == "driver" and event[3] is current for event in motions)
        assert motions[0][2]["text"] == "Preview Driver Motion"
        assert all("Preview Driver: driver" in event[2]["text"] for event in motions[1:])
        assert all(not event[3] for event in controls if event not in motions)
        labels = [event[1]["text"] for event in events if event[0] == "label"]
        assert sum("read-only" in text for text in labels) == 2


def test_geared_motion_omits_unavailable_connector_tutorial_and_buttons():
    events, _ = draw_controls(assembly=mechanism().to_dict())
    labels = [e[1]["text"] for e in events if e[0] == "label"]
    controls = [e for e in events if e[0] == "operator"]
    assert any("Gear-coupled motion: edit the driver below." in text for text in labels)
    assert not any("Pick parent" in text or "Flip, Roll" in text for text in labels)
    assert not any(
        e[2].get("text")
        in {"Place Joint in Viewport", "Mate by Faces", "Edit Connectors in Viewport"}
        for e in controls
    )
    assert any(e[1] == "mcad.assembly_joint" for e in controls)


def test_pair_actions_are_drawn_once_before_instances_with_details_closed():
    source = ROOT / "blender_addon/mechanical_cad_blender/assembly_ui.py"
    node = next(
        n
        for n in ast.parse(source.read_text()).body
        if isinstance(n, ast.FunctionDef) and n.name == "draw_assembly_history"
    )

    class WithoutImports(ast.NodeTransformer):
        def visit_ImportFrom(self, node):
            return None

    node = WithoutImports().visit(node)
    calls = []
    current = SimpleNamespace(document_json="accepted", owner_id="owner")
    namespace = {
        "state": lambda _: current,
        "assembly_joint_viewport": SimpleNamespace(active=lambda _: False),
        "assembly_source_update_preview": SimpleNamespace(active=lambda _: False),
        "draw_pending": lambda *_: False,
        "draw_cancel": lambda *_: False,
        "workspace": SimpleNamespace(active_draft=lambda: False, has_draft=lambda _: False),
        "assembly": lambda _: {"name": "Pair"},
        "_primary_actions": lambda *_: calls.append("primary"),
        "assembly_display": SimpleNamespace(owned_objects=lambda *_: []),
        "draw_gear_parts": lambda *_: calls.append("gear"),
        "_instance_details": lambda *_: calls.append("instances"),
        "_section": lambda *args: calls.append(args[2]),
    }
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), "exec"), namespace)
    namespace["draw_assembly_history"](Layout(), SimpleNamespace(scene=object()))
    assert calls == [
        "primary",
        "gear",
        "instances",
        "show_parts",
        "show_joints",
        "show_checks",
        "show_options",
    ]


def test_ordinary_assembly_keeps_visual_connector_actions_and_guidance():
    events, _ = draw_controls()
    labels = [e[1]["text"] for e in events if e[0] == "label"]
    controls = [e for e in events if e[0] == "operator"]
    assert any("Pick parent and child" in text for text in labels)
    assert any("Flip, Roll" in text for text in labels)
    assert not any("Gear-coupled motion" in text for text in labels)
    for label in ("Place Joint in Viewport", "Mate by Faces", "Edit Connectors in Viewport"):
        assert any(e[2].get("text") == label for e in controls)


def test_slider_motion_control_uses_exact_joint_and_current_display_only():
    data = mechanism(relations=False).to_dict()
    data["joints"][1]["kind"] = "slider"
    before = copy.deepcopy(data)
    for current in (False, True):
        events, _ = draw_controls(display_current=current, assembly=data)
        controls = [event for event in events if event[0] == "operator" and getattr(event[4], "motion_only", False)]
        sliders = [event for event in controls if event[2]["text"] == "Preview Slider Motion"]
        assert len(sliders) == 1
        assert sliders[0][1] == "mcad.assembly_visual_joint"
        assert sliders[0][4].joint_id == data["joints"][1]["id"] and sliders[0][3] is current
        assert len([event for event in controls if event[2]["text"] == "Preview Driver Motion"]) == 2
    assert data == before
