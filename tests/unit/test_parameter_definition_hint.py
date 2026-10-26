"""Stored parameter cues are read-only source labels, never evaluation results."""

import ast
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_parameter_depth_edit import helper


@pytest.mark.parametrize(("value", "expected"), [
    (10, "Stored value: depth = 10 mm"),
    (2.5, "Stored value: depth = 2.5 mm"),
    ("10", "Stored expression: depth = 10"),
    ("other * 2", "Stored expression: depth = other * 2"),
    ("missing / 0", "Stored expression: depth = missing / 0"),
    ("  other\n *\t2  ", "Stored expression: depth = other * 2"),
    (True, ""),
    (None, ""),
    ({"value": 10}, ""),
])
def test_stored_hint_distinguishes_source_types_without_evaluation(value, expected):
    document = {"parameters": {"depth": value}}
    before = copy.deepcopy(document)
    assert helper.parameter_definition_hint(document, "depth") == expected
    assert document == before


def test_stored_hint_is_bounded_and_missing_link_is_empty():
    document = {"parameters": {"depth": "other + " * 30}}
    before = copy.deepcopy(document)
    label = helper.parameter_definition_hint(document, "depth")
    assert len(label) == 70 and label.endswith("…")
    assert helper.parameter_definition_hint(document, "missing") == ""
    assert helper.parameter_definition_hint(document, "") == ""
    assert helper.parameter_definition_hint({}, "depth") == ""
    assert document == before


class Layout:
    def __init__(self):
        self.labels = []

    def label(self, *, text, **kwargs):
        self.labels.append(text)

    def prop(self, operator, name, **kwargs):
        getattr(operator, name)  # Read-only widgets, with real field existence.

    def box(self):
        return self

    def row(self, **kwargs):
        return self

    def column(self, **kwargs):
        return self


def actual_draw():
    """Use production draw bodies with only presentation ports; no backend exists."""
    source = Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender/solid_operators.py"
    tree = ast.parse(source.read_text())
    dimensions = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_draw_dimensions")
    dialog = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "_SolidDialog")
    draw = next(node for node in dialog.body if isinstance(node, ast.FunctionDef) and node.name == "draw")
    namespace = {
        "json": json,
        "FEATURE_FIELDS": {"sketch_circle": ("radius",), "cut": ()},
        "FEATURE_INPUTS": {},
        "_FIELD_LABELS": {"radius": "Radius (mm)"},
        "parameter_definition_hint": helper.parameter_definition_hint,
        "_draw_feature_help": lambda *args: None,
    }
    exec(compile(ast.Module(body=[dimensions, draw], type_ignores=[]), str(source), "exec"), namespace)
    return namespace["draw"]


@pytest.mark.parametrize("branch", ["radius", "depth", "linked"])
@pytest.mark.parametrize("stored", [10, "base * 2"])
def test_local_draw_uses_canonical_source_not_pending_shared_widget(branch, stored):
    canonical = {"parameters": {"size": stored}}
    layout = Layout()
    operator = SimpleNamespace(
        layout=layout, kind={"radius": "sketch_circle", "depth": "extrude", "linked": "cut"}[branch],
        feature_id="edited", feature_label="Edited", original_json=json.dumps(canonical),
        radius_parameter_name="size" if branch == "radius" else "",
        depth_parameter_name="size" if branch != "radius" else "",
        radius_edit_scope="FEATURE", depth_edit_scope="FEATURE", linked_depth_scope="FEATURE",
        radius="size", length="size", linked_length="size",
        radius_parameter_value="UNAPPLIED_RADIUS", depth_parameter_value="UNAPPLIED_DEPTH",
        extrude_end_condition="BLIND", linked_end_condition="BLIND",
        linked_tool_id="tool" if branch == "linked" else "", tool="tool",
        linked_tool_label="Tool", linked_consumers="", linked_profile="profile",
    )
    before = {key: copy.deepcopy(value) for key, value in vars(operator).items() if key != "layout"}
    actual_draw()(operator, SimpleNamespace())
    expected = helper.parameter_definition_hint(canonical, "size")
    assert layout.labels.count(expected) == 1
    assert not any("UNAPPLIED" in text for text in layout.labels)
    assert {key: value for key, value in vars(operator).items() if key != "layout"} == before
    assert json.loads(operator.original_json) == canonical
