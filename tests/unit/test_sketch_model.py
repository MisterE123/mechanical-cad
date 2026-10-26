"""Schema/resource tests do not import the native solver."""

import copy
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from mechanical_cad.sketch_model import (
    MAX_CONSTRAINTS,
    MAX_JSON_DEPTH,
    MAX_LINES,
    MAX_NUMBER_CHARACTERS,
    MAX_POINTS,
    MAX_SKETCH_BYTES,
    Constraint,
    Line,
    Plane,
    Point,
    Sketch,
    SketchError,
    validate,
)

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def data():
    return Sketch(
        "unit-sketch",
        (Point("p0", 0.0, 0.0), Point("p1", 40.0, 0.0)),
        (Line("l0", "p0", "p1"),),
        (
            Constraint("axis", "horizontal", ("l0",)),
            Constraint("width", "distance", ("p0", "p1"), 40.0),
            Constraint("anchor", "fixed", ("p0",), target=(0.0, 0.0)),
        ),
    ).to_dict()


def at(data, path):
    for key in path:
        data = data[key]
    return data


def assert_rejected(data, code=None):
    with pytest.raises(SketchError) as error:
        Sketch.from_dict(data)
    if code:
        assert error.value.code == code
    return error.value


def test_model_imports_without_site_packages_or_native_solver():
    result = subprocess.run(
        [
            sys.executable,
            "-S",
            "-c",
            f"import sys; sys.path.insert(0, {str(ROOT / 'src')!r}); import mechanical_cad.sketch_model, mechanical_cad.sketch_solver; assert 'slvs' not in sys.modules",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("path", [(), ("plane",), ("points", 0), ("lines", 0), ("constraints", 0)])
def test_unknown_keys_rejected_at_every_record_boundary(data, path):
    at(data, path)["ignored_typo"] = 123
    assert_rejected(data, "invalid_sketch")


@pytest.mark.parametrize(
    "path,key",
    [
        ((), "schema_version"),
        ((), "id"),
        ((), "units"),
        ((), "points"),
        ((), "lines"),
        ((), "constraints"),
        ((), "plane"),
        (("plane",), "origin"),
        (("plane",), "quaternion"),
        (("points", 0), "id"),
        (("points", 0), "u"),
        (("points", 0), "v"),
        (("lines", 0), "id"),
        (("lines", 0), "start"),
        (("lines", 0), "end"),
        (("constraints", 0), "id"),
        (("constraints", 0), "kind"),
        (("constraints", 0), "refs"),
    ],
)
def test_missing_fields_rejected_with_typed_error(data, path, key):
    del at(data, path)[key]
    assert_rejected(data, "invalid_sketch")


@pytest.mark.parametrize(
    "path,key,value",
    [
        ((), "schema_version", True),
        ((), "schema_version", 1.0),
        ((), "schema_version", "1"),
        ((), "schema_version", 2),
        ((), "points", {}),
        ((), "lines", None),
        ((), "constraints", "oops"),
        ((), "plane", []),
        (("plane",), "origin", "0,0,0"),
        (("plane",), "quaternion", [1, 0, 0]),
        (("points", 0), "id", []),
        (("points", 0), "u", True),
        (("points", 0), "v", "width"),
        (("points", 0), "u", {}),
        (("lines", 0), "start", []),
        (("lines", 0), "end", {}),
        (("constraints", 0), "kind", []),
        (("constraints", 0), "refs", "p0"),
        (("constraints", 0), "refs", [{}]),
        (("constraints", 0), "value", True),
        ((), "units", []),
        ((), "units", "inch"),
        ((), "id", ""),
        ((), "id", "bad/id"),
        ((), "id", "x" * 129),
        ((), "id", "@drag"),
        (("plane",), "origin", [0, 0, 1_000_001]),
        (("points", 0), "u", 1_000_001),
        (("points", 0), "u", 10**1000),
    ],
)
def test_wrong_types_versions_ids_and_ranges_rejected(data, path, key, value):
    at(data, path)[key] = value
    assert_rejected(data)


@pytest.mark.parametrize("value", [[], None, True, "text", 5])
def test_top_level_non_object_is_rejected(value):
    assert_rejected(value, "invalid_sketch")


@pytest.mark.parametrize(
    "payload",
    [
        '{"schema_version":1,"schema_version":1}',
        '{"plane":{"origin":[],"origin":[]}}',
        '{"points":[{"id":"p","u":1,"u":2,"v":3}]}',
        '{"constraints":[{"id":"c","value":1,"value":2}]}',
        '{"a":1,"\\u0061":2}',
    ],
)
def test_duplicate_json_keys_rejected_including_nested_and_escaped_names(payload):
    with pytest.raises(SketchError, match="Duplicate") as error:
        Sketch.from_json(payload)
    assert error.value.code == "invalid_json"


@pytest.mark.parametrize("text", ["", "{", "{} garbage", "[}", "\ufeff{}", "\ud800", b"{}"])
def test_malformed_json_unicode_or_wrong_input_type_has_typed_error(text):
    with pytest.raises(SketchError) as error:
        Sketch.from_json(text)
    assert error.value.code == "invalid_json"


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", "1e999", "-1e999"])
def test_non_finite_lexemes_are_rejected_everywhere(value):
    with pytest.raises(SketchError):
        Sketch.from_json('{"ignored":' + value + "}")


def test_long_number_token_rejected_before_large_integer_parse():
    with pytest.raises(SketchError) as error:
        Sketch.from_json('{"ignored":' + "1" * (MAX_NUMBER_CHARACTERS + 1) + "}")
    assert error.value.code == "resource_limit"


@pytest.mark.parametrize("text", [" " * (MAX_SKETCH_BYTES + 1), "é" * (MAX_SKETCH_BYTES // 2 + 1)])
def test_utf8_byte_budget_is_enforced_before_parse(text):
    with pytest.raises(SketchError) as error:
        Sketch.from_json(text)
    assert error.value.code == "sketch_too_large"


def test_exact_byte_budget_is_accepted_for_valid_document(data):
    text = json.dumps(data)
    padded = text + " " * (MAX_SKETCH_BYTES - len(text.encode("utf-8")))
    assert Sketch.from_json(padded).id == data["id"]


def test_depth_budget_precedes_json_recursion():
    text = "[" * 10000 + "0" + "]" * 10000
    assert len(text) < MAX_SKETCH_BYTES
    with pytest.raises(SketchError) as error:
        Sketch.from_json(text)
    assert error.value.code == "resource_limit"


def test_depth_guard_ignores_escaped_quotes_and_brackets_in_strings():
    text = json.dumps({"unknown": '[{\\"' * (MAX_JSON_DEPTH * 3)})
    with pytest.raises(SketchError) as error:
        Sketch.from_json(text)
    assert error.value.code == "invalid_sketch", "Must fail schema, not lexical depth budget"


@pytest.mark.parametrize(
    "field,limit", [("points", MAX_POINTS), ("lines", MAX_LINES), ("constraints", MAX_CONSTRAINTS)]
)
def test_record_limits_reject_before_inspecting_records(data, field, limit):
    data[field] = [None] * (limit + 1)
    assert_rejected(data, "resource_limit")


def test_exact_record_limits_are_accepted_by_schema_not_claimed_fast_to_solve():
    points = tuple(Point(f"p{i}", float(i), 0.0) for i in range(MAX_POINTS))
    lines = tuple(Line(f"l{i}", "p0", "p1") for i in range(MAX_LINES))
    constraints = tuple(Constraint(f"c{i}", "horizontal", ("l0",)) for i in range(MAX_CONSTRAINTS))
    sketch = Sketch("bounds", points, lines, constraints)
    loaded = Sketch.from_json(sketch.to_json())
    assert len(loaded.points) == MAX_POINTS and len(loaded.constraints) == MAX_CONSTRAINTS


@pytest.mark.parametrize("value", [0.0, -1.0, 1e-7, 1_000_001.0, float("nan"), float("inf"), True])
def test_invalid_distance_domain(data, value):
    next(c for c in data["constraints"] if c["id"] == "width")["value"] = value
    assert_rejected(data, "invalid_number")


@pytest.mark.parametrize("value", [1e-6, 1e6])
def test_distance_domain_endpoints_are_accepted(data, value):
    next(c for c in data["constraints"] if c["id"] == "width")["value"] = value
    assert Sketch.from_dict(data)


def test_fixed_target_is_strictly_checked(data):
    anchor = next(c for c in data["constraints"] if c["id"] == "anchor")
    for target in (None, "0,0", [0], [0, 0, 0], [0, True], [0, 1_000_001]):
        anchor["target"] = target
        assert_rejected(data)


def test_from_dict_to_dict_never_alias_mutable_external_data(data):
    original = copy.deepcopy(data)
    sketch = Sketch.from_dict(data)
    data["points"][0]["u"] = 999
    data["constraints"][0]["refs"].append("other")
    data["plane"]["origin"][0] = 999
    assert sketch.to_dict() == Sketch.from_dict(original).to_dict()
    output = sketch.to_dict()
    output["constraints"][0]["refs"].append("other")
    assert sketch.to_dict() != output


def test_direct_numeric_constructor_canonicalizes_ints_to_doubles():
    original = Sketch("integers", (Point("p", 1, 2),), (), (), Plane((0, 0, 0), (1, 0, 0, 0)))
    assert Sketch.from_json(original.to_json()).to_json() == original.to_json()


@pytest.mark.parametrize(
    "mutation",
    [
        lambda s: replace(s, points=list(s.points)),
        lambda s: replace(s, points=(None,)),
        lambda s: replace(s, lines=(Line("bad", [], {}),)),
        lambda s: replace(s, plane=Plane([0, 0, 0], (1, 0, 0, 0))),
        lambda s: replace(s, constraints=(Constraint("bad", "fixed", ["p0"], target=(0, 0)),)),
        lambda s: replace(s, constraints=(Constraint("bad", "fixed", ("p0",), target=[0, 0]),)),
        lambda s: replace(s, points=(Point("p", 10**1000, 0.0),)),
    ],
)
def test_direct_invalid_constructor_is_rejected_at_boundary(data, mutation):
    with pytest.raises(SketchError):
        validate(mutation(Sketch.from_dict(data)))


def test_definition_retains_formulas_and_resolves_detached_numeric_input(data):
    from mechanical_cad.sketch_model import SketchDefinition, resolve_sketch

    width = next(c for c in data["constraints"] if c["id"] == "width")
    width["value"] = "width * 2 + allowance"
    definition = SketchDefinition.from_dict(data)
    before = definition.to_json()
    resolved = resolve_sketch(definition, {"width": 25.0, "allowance": 0.25})
    assert type(resolved) is Sketch
    assert next(c.value for c in resolved.constraints if c.id == "width") == 50.25
    assert (
        next(c.value for c in definition.constraints if c.id == "width") == "width * 2 + allowance"
    )
    assert definition.to_json() == before
    assert SketchDefinition.from_json(before).to_json() == before
    assert [c.id for c in definition.constraints] == [c.id for c in resolved.constraints]
    with pytest.raises(SketchError):
        validate(definition)


@pytest.mark.parametrize(
    "expression,names,code",
    [
        ("missing", {}, "unknown_parameter"),
        ("1 / zero", {"zero": 0.0}, "invalid_expression"),
        ("0", {}, "invalid_number"),
        ("1e7", {}, "invalid_number"),
        ("__import__('os').system('echo unsafe')", {}, "invalid_expression"),
    ],
)
def test_resolution_errors_identify_constraint_without_mutating_definition(
    data, expression, names, code
):
    from mechanical_cad.errors import CADException
    from mechanical_cad.sketch_model import SketchDefinition, resolve_sketch

    next(c for c in data["constraints"] if c["id"] == "width")["value"] = expression
    definition = SketchDefinition.from_dict(data)
    before = definition.to_json()
    with pytest.raises(CADException) as error:
        resolve_sketch(definition, names)
    assert error.value.code == code
    assert "width" in str(error.value)
    assert definition.to_json() == before


def test_numeric_sketch_never_accepts_formula(data):
    next(c for c in data["constraints"] if c["id"] == "width")["value"] = "width"
    assert_rejected(data, "invalid_number")


def test_plane_has_required_valid_stable_identity(data):
    del data["plane"]["id"]
    assert_rejected(data, "invalid_sketch")
    data["plane"]["id"] = "p0"
    assert_rejected(data, "duplicate_id")


def test_missing_native_solver_is_actionable_at_solve_only(data, monkeypatch):
    import mechanical_cad.sketch_solver as adapter
    from mechanical_cad.errors import CADException

    def missing(name):
        raise ImportError("simulated missing optional dependency")

    monkeypatch.setattr(adapter, "import_module", missing)
    sketch = Sketch.from_dict(data)
    with pytest.raises(CADException) as error:
        adapter.solve(sketch)
    assert error.value.code == "solver_unavailable"
    assert "mechanical-cad[sketch]" in str(error.value)


def test_incompatible_solver_version_is_actionable(data, monkeypatch):
    import mechanical_cad.sketch_solver as adapter
    from mechanical_cad.errors import CADException

    monkeypatch.setattr(adapter, "import_module", lambda _: object())
    monkeypatch.setattr(adapter, "version", lambda _: "99.0")
    with pytest.raises(CADException) as error:
        adapter.solve(Sketch.from_dict(data))
    assert error.value.code == "solver_version"


@pytest.mark.parametrize("definition", [False, True])
@pytest.mark.parametrize("invalid", [False, True])
def test_from_dict_never_mutates_input_even_normalizing_numbers_or_failing(
    data, definition, invalid
):
    from mechanical_cad.sketch_model import SketchDefinition

    record_type = SketchDefinition if definition else Sketch
    data["points"][0]["u"] = 1
    data["points"][0]["v"] = 2
    data["plane"]["origin"] = [0, 0, 0]
    if invalid:
        data["constraints"][0]["kind"] = "unknown"
    before = json.dumps(data, sort_keys=True)
    if invalid:
        with pytest.raises(SketchError):
            record_type.from_dict(data)
    else:
        record_type.from_dict(data)
    assert json.dumps(data, sort_keys=True) == before
    assert type(data["points"][0]["u"]) is int
