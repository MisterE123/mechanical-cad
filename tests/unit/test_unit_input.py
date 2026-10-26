"""Typed UI unit literals never expand the saved expression language."""

import ast
import copy
import importlib
import json
import math
import sys
import types
from pathlib import Path

import pytest

from mechanical_cad.errors import CADException
from mechanical_cad.expressions import evaluate

ROOT = Path(__file__).resolve().parents[2]
ADDON = ROOT / "blender_addon/mechanical_cad_blender"
package = types.ModuleType("unit_input_test_addon")
package.__path__ = [str(ADDON)]
sys.modules[package.__name__] = package
units = importlib.import_module(package.__name__ + ".unit_input")
solid = importlib.import_module(package.__name__ + ".solid_feature_edit")
values = importlib.import_module(package.__name__ + ".solid_dialog_values")
drafts = importlib.import_module(package.__name__ + ".general_sketch_draft")
rectangle = importlib.import_module(package.__name__ + ".sketch_draft")
endings = importlib.import_module(package.__name__ + ".extrusion_end_condition")
linked = importlib.import_module(package.__name__ + ".linked_extrusion_edit")


@pytest.mark.parametrize(
    "text, dimension, expected",
    [
        ("10 mm", "length", 10),
        ("2cm", "length", 20),
        ("1e-3 m", "length", 1),
        (".5 in", "length", 12.7),
        ("-2 ft", "length", -609.6),
        ("+0mm", "length", 0),
        ("  +2.5e1 mm  ", "length", 25),
        ("45 deg", "angle", 45),
        ("1 rad", "angle", 180 / math.pi),
        ("-0 deg", "angle", -0.0),
        ("-1e-2rad", "angle", -0.01 * 180 / math.pi),
    ],
)
def test_literal_converts_only_to_declared_ui_units(text, dimension, expected):
    result = units.normalize_unit_input(text, dimension)
    assert type(result) is float
    assert result == pytest.approx(expected)
    if text == "-0 deg":
        assert math.copysign(1, result) == -1


@pytest.mark.parametrize(
    "value",
    [
        0,
        10,
        2.3456789012345,
        "0xFF",
        "  0xFF ",
        "  1_000 ",
        "1_000",
        "1e3",
        "2 * mm",
        "slot10mm + gap",
        "rad",
        " min(width, 2) ",
        "width / 2",
        "__import__('os')",
    ],
)
def test_legacy_values_and_formula_text_are_not_rewritten_or_evaluated(value):
    for dimension in ("length", "angle", "scalar"):
        actual = units.normalize_unit_input(value, dimension)
        assert type(actual) is type(value) and actual == value


@pytest.mark.parametrize(
    "text, dimension, message",
    [
        ("1 deg", "length", "length field"),
        ("2 cm", "angle", "angle field"),
        ("2 mm", "scalar", "no declared"),
        ("2 rad", "scalar", "no declared"),
        ("10 MM", "length", "Unknown unit"),
        ("10 yd", "length", "Unknown unit"),
        ("nan mm", "length", "finite"),
        ("-inf deg", "angle", "finite"),
        ("1e999 in", "length", "finite"),
        ("1e12 ft", "length", "within"),
        ("10 mm + 2 cm", "length", "one number"),
        ("width + 2 mm", "length", "one number"),
        ("2 * (5 mm)", "length", "one number"),
        ("1mm/2", "length", "one number"),
        ("10 mm cm", "length", "one number"),
        ("2" * 257 + " mm", "length", "256"),
    ],
)
def test_wrong_mixed_unknown_untyped_and_unbounded_units_fail(text, dimension, message):
    with pytest.raises(ValueError, match=message):
        units.normalize_unit_input(text, dimension)


def test_canonical_evaluator_stays_unchanged_and_unit_like_parameters_still_work():
    assert evaluate("2 * mm", {"mm": 3}) == 6
    with pytest.raises(CADException):
        evaluate("10 mm", {})
    with pytest.raises(CADException):
        evaluate(units.normalize_unit_input("__import__('os')", "length"), {})


def test_feature_fields_do_not_infer_units_for_counts_axes_or_flags():
    for kind, field in (
        ("linear_pattern", "count"),
        ("revolve", "axis_x"),
        ("loft", "ruled"),
        ("extrude_through", "direction"),
    ):
        with pytest.raises(ValueError, match="no declared"):
            units.normalize_feature_inputs(kind, {field: "1 mm"})
    assert units.normalize_feature_inputs("transform", {"x": "1 in", "rx": "1 rad"}) == {
        "x": 25.4,
        "rx": 180 / math.pi,
    }


def test_feature_and_linked_edits_normalize_without_changing_parameters_or_inputs():
    source = {
        "parameters": {"depth": 10},
        "features": [
            {
                "id": "tool",
                "kind": "extrude",
                "label": "Tool",
                "params": {"length": "depth"},
                "inputs": {"profile": "p"},
            },
            {
                "id": "cut",
                "kind": "cut",
                "label": "Cut",
                "params": {},
                "inputs": {"base": "base", "tool": "tool"},
            },
        ],
        "active_feature": "cut",
    }
    before = copy.deepcopy(source)
    result = solid.edit_feature(
        source, "tool", label="Tool", params={"length": "1 in"}, inputs={"profile": "p"}
    )
    assert result["features"][0]["params"]["length"] == 25.4
    assert result["parameters"] == source["parameters"] and source == before
    result = linked.edit_linked_extrusion(
        source, source, "cut", tool_id="tool", length="2 cm", profile="p"
    )
    assert result["features"][0]["params"]["length"] == 20
    assert result["parameters"] == before["parameters"] and source == before


def test_directional_depth_and_face_offset_use_lengths_before_direction():
    assert values.extrusion_depth("1 in", "REVERSE") == -25.4
    assert values.extrusion_depth("-2 cm", "SIGNED") == -20
    for value in ("-1 cm", "0 mm"):
        with pytest.raises(ValueError, match="positive"):
            values.extrusion_depth(value, "NORMAL")
    feature = {"params": {}}
    endings.set_up_to_face(
        feature, profile="p", target="s", end_face="s:top", direction=-1, offset="-2 cm"
    )
    assert feature["params"] == {"direction": -1, "offset": -20}


def blank():
    return json.dumps(
        {
            "schema_version": 1,
            "id": "part",
            "name": "Part",
            "units": "mm",
            "parameters": {},
            "features": [],
            "active_feature": None,
        }
    )


def test_sketch_units_normalize_only_in_candidate_and_keep_recoverable_raw_text():
    draft = drafts.GeneralSketchDraft(blank())
    _, circle = draft.execute(drafts.AddCircle(drafts.PointSeed(0, 0), 10)).entity_ids
    driver = draft.execute(drafts.AddRelation("radius", (circle,), value="1 in")).constraint_id
    assert draft.sketch["constraints"][0]["value"] == 25.4
    draft.begin_edit(driver)
    draft.update_edit("2 cm")
    candidate = draft.trial_candidate()
    assert candidate["features"][0]["sketch"]["constraints"][0]["value"] == 20
    assert draft.pending_edit.raw_text == "2 cm"
    draft.update_edit("2 deg")
    with pytest.raises(drafts.DraftError, match="length field"):
        draft.trial_candidate()
    assert draft.pending_edit.raw_text == "2 deg"
    assert draft.sketch["constraints"][0]["value"] == 25.4
    draft.cancel_edit()
    assert draft.pending_edit is None


def test_rectangle_candidate_normalizes_lengths_but_preserves_raw_input():
    draft = rectangle.RectangleDraft(blank())
    draft.first_point((0, 0))
    assert draft.second_point((20, 20))
    draft.set_dimensions("1 in", "2 cm")
    candidate = draft.candidate()
    assert candidate["parameters"][draft.width_key] == 25.4
    assert candidate["parameters"][draft.height_key] == 20
    assert draft.width_text == "1 in" and draft.height_text == "2 cm"


def test_assembly_converts_ui_degrees_to_saved_radians_exactly_once():
    source = ADDON / "assembly_operator_helpers.py"
    functions = {"number", "vector", "unit_value", "quaternion_from_degrees"}
    body = [
        node
        for node in ast.parse(source.read_text()).body
        if isinstance(node, ast.FunctionDef) and node.name in functions
    ]
    namespace = {
        "math": math,
        "normalize_unit_input": units.normalize_unit_input,
        "bridge": types.SimpleNamespace(BridgeError=ValueError),
    }
    exec(compile(ast.Module(body=body, type_ignores=[]), str(source), "exec"), namespace)
    assert namespace["unit_value"]("1 rad", "revolute") == pytest.approx(1)
    assert namespace["unit_value"]("90 deg", "revolute") == pytest.approx(math.pi / 2)
    assert namespace["unit_value"]("1 in", "slider") == 25.4
    assert namespace["vector"]("1 in, 2 cm, 3 mm", 3, "length") == [25.4, 20, 3]
    assert namespace["quaternion_from_degrees"]("0, 0, 1 rad") == pytest.approx(
        [math.cos(0.5), 0, 0, math.sin(0.5)]
    )
    with pytest.raises(ValueError, match="no declared"):
        namespace["vector"]("1 rad, 0, 0, 0", 4)
    with pytest.raises(ValueError, match="angle field"):
        namespace["unit_value"]("1 cm", "revolute")


def test_gear_ratio_does_not_reuse_a_length_input_seam():
    source = ast.parse((ADDON / "assembly_gear_ui.py").read_text())
    cls = next(
        node
        for node in source.body
        if isinstance(node, ast.ClassDef) and node.name == "MCAD_OT_assembly_gear"
    )
    candidate = next(
        node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == "candidate"
    )
    assignment = candidate.body[0]
    assert isinstance(assignment.value, ast.Call)
    assert assignment.value.func.id == "number"
    assert len(assignment.value.args) == 1
    with pytest.raises(ValueError, match="no declared"):
        units.normalize_unit_input("2 mm", "scalar")


@pytest.mark.parametrize("text, dimension, expected", [
    ("1/8in", "length", 3.175),
    ("1 1/2 in", "length", 38.1),
    ("-1 1/2 in", "length", -38.1),
    ("+1 1/2in", "length", 38.1),
    (" \t1\t1 / 2\tin\t", "length", 38.1),
    ("3/2 mm", "length", 1.5),
    ("0 0/2 mm", "length", 0),
    ("-0/2 deg", "angle", -0.0),
    ("1/2 rad", "angle", 90 / math.pi),
    ("1 1/2 deg", "angle", 1.5),
    ("1/2 cm", "length", 5),
    ("1/2 m", "length", 500),
    ("1/2 ft", "length", 152.4),
])
def test_explicit_fraction_and_mixed_number_literals(text, dimension, expected):
    actual = units.normalize_unit_input(text, dimension)
    assert type(actual) is float and actual == pytest.approx(expected)
    if text.startswith("-0"):
        assert math.copysign(1, actual) == -1


@pytest.mark.parametrize("text", [
    "1/0 in", "1 1/0 in", "1 2/2 in", "1 3/2 in", "1/-2 in", "1/+2 in",
    "1 -1/2 in", "1 +1/2 in", "1.5/2 in", "1/2.5 in", "1e1/2 in",
    "1/2e1 in", "1/2/3 in", "1//2 in", "1/2 IN", "1/2 yd", "1\n1/2 in",
    "1\u00a01/2 in", "1/2 in + 1 mm", "1/2 in 2 cm", "(1/2) in",
    "1/2 * in", "1/2 deg", "9" * 240 + "/1 in",
])
def test_malformed_or_out_of_scope_fraction_rejected_by_parser_or_existing_evaluator(text):
    # Legacy valid Python expressions still belong to the existing allowlist,
    # never to this literal parser (for example '1/2 * in' is invalid Python).
    with pytest.raises((ValueError, CADException)):
        normalized = units.normalize_unit_input(text, "length")
        if isinstance(normalized, str):
            evaluate(normalized, {})


@pytest.mark.parametrize("text", ["1/2", " -1 / 2 ", "1 + 1/2", "width / 2", "2 * mm", "1/2j"])
def test_bare_fraction_is_unchanged_formula_text(text):
    for dimension in ("length", "angle", "scalar"):
        assert units.normalize_unit_input(text, dimension) is text


@pytest.mark.parametrize("source", [7, 3.175, 2.3456789012345, "1/2", " width / 2 "])
def test_unchanged_driver_keeps_source_type_precision_and_formula(source):
    draft = drafts.GeneralSketchDraft(blank())
    _, circle = draft.execute(drafts.AddCircle(drafts.PointSeed(0, 0), 10)).entity_ids
    driver = draft.execute(drafts.AddRelation("radius", (circle,), value=source)).constraint_id
    draft.begin_edit(driver)
    result = draft.trial_candidate()["features"][0]["sketch"]["constraints"][0]["value"]
    assert type(result) is type(source) and result == source


def test_fractional_feature_and_driver_fields_normalize_once_and_reject_unitless_fields():
    assert units.normalize_feature_inputs("extrude", {"length": "1/8 in"}) == {"length": 3.175}
    assert units.normalize_driver_input("1/8 in", "radius") == 3.175
    assert units.normalize_driver_input("1/2 rad", "angle") == pytest.approx(90 / math.pi)
    for kind, field in (("linear_pattern", "count"), ("revolve", "axis_x")):
        with pytest.raises(ValueError, match="no declared"):
            units.normalize_feature_inputs(kind, {field: "1/2 mm"})
    with pytest.raises(ValueError, match="angle field"):
        units.normalize_unit_input("1/2 in", "angle")
