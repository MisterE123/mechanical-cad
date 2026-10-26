"""Embedded-v2 circles opt in without changing historical sketch identity."""

import copy
import json
import subprocess
import sys
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from mechanical_cad.assembly_model import (
    AssemblyDocument,
    Instance,
    PartDefinition,
    PartSource,
)
from mechanical_cad.errors import CADException
from mechanical_cad.model import Document, Feature, load_document
from mechanical_cad.sketch_model import (
    MAX_ACTIVE_SCALARS,
    MAX_CIRCLES,
    MAX_CONSTRAINTS,
    MAX_CURVES,
    MAX_JSON_DEPTH,
    MAX_NUMBER_CHARACTERS,
    MAX_POINTS,
    MAX_SKETCH_BYTES,
    SKETCH_SCHEMA_VERSION,
    Circle,
    Constraint,
    Line,
    Plane,
    Point,
    Sketch,
    SketchDefinition,
    SketchError,
    active_scalar_count,
    migrate_to_v2,
    resolve_sketch,
    validate,
    validate_definition,
)

ROOT = Path(__file__).resolve().parents[2]


def circle_definition(value="shaft_radius + clearance"):
    return SketchDefinition(
        "circle-sketch",
        (Point("center", 3, 4),),
        (),
        (Constraint("radius", "radius", ("circle",), value),),
        schema_version=2,
        circles=(Circle("circle", "center", 7),),
    )


def numeric_circle():
    return resolve_sketch(circle_definition(), {"shaft_radius": 9, "clearance": 1})


def circle_document():
    return Document(
        "circle-part",
        "Circle",
        {"shaft_radius": 9, "clearance": 1},
        (Feature("sketch", "sketch_constrained", "Sketch", sketch=circle_definition()),),
        "sketch",
        schema_version=2,
    )


@pytest.mark.parametrize(
    "name,digest,assembly_digest",
    [
        (
            "constrained_plate",
            "0c68f787945e27be09169fba8c576d9abc44394e0daf2b3cb2e9eefd85e24434",
            "511c6d7be62df4d1db020c1f9a169a71df3e4e8c52ec5275531e25d204765167",
        ),
        (
            "viewport_rectangle",
            "c01ff8fc476f9eaf9d314df4c3aae607cca15da6a6075d902b5aa30054ba48c7",
            "59efbe0570b61f7a96c3b0f3cff69d791414548df651cb1023d7191491f9a72e",
        ),
    ],
)
def test_existing_schema_two_v1_sketch_and_accepted_assembly_hashes_are_frozen(
    name, digest, assembly_digest
):
    # Fixtures captured from the pre-circle implementation, not recomputed expectations.
    document = load_document(ROOT / "examples" / f"{name}.mcad.json")
    assert document.content_hash == digest
    assert document.features[0].sketch.schema_version == SKETCH_SCHEMA_VERSION == 1
    assert "circles" not in document.features[0].sketch.to_dict()
    assert Document.from_json(document.to_json()).content_hash == digest
    assembly = AssemblyDocument(
        "legacy-assembly",
        "Accepted v1 sketch",
        (PartSource.from_document(document),),
        (PartDefinition("part", digest, document.id, document.active_feature, ()),),
        (Instance("instance", "part"),),
        (),
        "instance",
    )
    assert assembly.content_hash == assembly_digest
    restored = AssemblyDocument.from_json(assembly.to_json())
    assert restored.content_hash == assembly_digest
    assert restored.part_sources[0].source_digest == digest
    assert restored.part_sources[0].document.to_json() == document.to_json()


def test_legacy_serializer_exact_bytes_and_positional_constructor_are_unchanged():
    original = Sketch("sketch", (Point("p", 1, -2),), (), (), Plane((0, 0, 0), (1, 0, 0, 0)), "mm")
    expected = (
        '{"constraints":[],"id":"sketch","lines":[],"plane":{"id":"workplane",'
        '"origin":[0.0,0.0,0.0],"quaternion":[1.0,0.0,0.0,0.0]},'
        '"points":[{"id":"p","u":1.0,"v":-2.0}],"schema_version":1,"units":"mm"}'
    )
    assert original.to_json() == expected
    assert list(original.to_dict()) == [
        "id",
        "points",
        "lines",
        "constraints",
        "plane",
        "units",
        "schema_version",
    ]
    with pytest.raises(TypeError):
        Sketch("sketch", (), (), (), Plane(), "mm", 2)


@pytest.mark.parametrize("record_type", [Sketch, SketchDefinition])
def test_explicit_migration_preserves_every_record_and_does_not_downgrade(record_type):
    original = record_type(
        "sketch",
        (Point("a", 0, 0), Point("b", 7, 1)),
        (Line("line", "a", "b"),),
        (
            Constraint(
                "length",
                "distance",
                ("a", "b"),
                "width + 1" if record_type is SketchDefinition else 8,
            ),
        ),
    )
    before = original.to_json()
    migrated = migrate_to_v2(original)
    assert type(migrated) is record_type
    expected = original.to_dict() | {"schema_version": 2, "circles": []}
    assert migrated.to_dict() == expected
    assert migrated.points is original.points
    assert migrated.lines is original.lines
    assert migrated.constraints is original.constraints
    assert migrated.plane is original.plane
    assert migrated.migrate_to_v2() is migrated
    assert original.to_json() == before
    assert record_type.from_json(migrated.to_json()).schema_version == 2


def test_migrating_one_embedded_sketch_keeps_document_and_feature_intent_reversible():
    document = load_document(ROOT / "examples/constrained_plate.mcad.json")
    original_json = document.to_json()
    feature = document.features[0]
    changed = replace(
        document,
        features=(replace(feature, sketch=feature.sketch.migrate_to_v2()), *document.features[1:]),
    )
    expected = document.to_dict()
    expected["features"][0]["sketch"].update(schema_version=2, circles=[])
    assert changed.to_dict() == expected
    assert changed.content_hash != document.content_hash
    assert document.to_json() == original_json
    assert Document.from_json(original_json).to_json() == original_json


def test_embedded_v2_still_requires_document_schema_two():
    raw = circle_document().to_dict()
    raw["schema_version"] = 1
    with pytest.raises(CADException) as error:
        Document.from_dict(raw)
    assert error.value.code == "migration_required"


@pytest.mark.parametrize("record_type", [Sketch, SketchDefinition])
def test_versioned_roundtrip_detaches_and_normalizes_numeric_circle_seeds(record_type):
    original = numeric_circle() if record_type is Sketch else circle_definition()
    raw = original.to_dict()
    raw["circles"][0]["radius"] = 7
    before = copy.deepcopy(raw)
    loaded = record_type.from_dict(raw)
    assert raw == before
    assert loaded.to_json() == original.to_json()
    assert type(loaded.to_dict()["circles"][0]["radius"]) is float
    raw["circles"][0]["center"] = "other"
    raw["circles"][0]["radius"] = 999
    output = loaded.to_dict()
    output["circles"][0]["radius"] = 100
    assert loaded.circles == (Circle("circle", "center", 7),)
    assert record_type.from_json(loaded.to_json()).to_json() == loaded.to_json()
    with pytest.raises(FrozenInstanceError):
        loaded.circles[0].radius = 9


def test_all_v2_record_orders_are_canonical_and_formula_text_is_exact():
    definition = replace(
        circle_definition("shaft_radius  +  clearance"),
        points=(Point("z", 9, 8), Point("center", 3, 4)),
        lines=(Line("z-line", "z", "center"), Line("a-line", "center", "z")),
        circles=(Circle("z-circle", "z", 1), Circle("circle", "center", 7)),
        constraints=(
            Constraint("z-fixed", "fixed", ("z",), target=(9, 8)),
            *circle_definition().constraints,
        ),
    )
    reordered = replace(
        definition,
        points=tuple(reversed(definition.points)),
        lines=tuple(reversed(definition.lines)),
        circles=tuple(reversed(definition.circles)),
        constraints=tuple(reversed(definition.constraints)),
    )
    assert reordered.to_json() == definition.to_json()
    source = circle_definition("shaft_radius  +  clearance")
    assert (
        SketchDefinition.from_json(source.to_json()).constraints[0].value
        == source.constraints[0].value
    )


def test_resolved_radius_is_detached_authored_radius_not_native_diameter():
    definition = circle_definition()
    before = definition.to_json()
    numeric = resolve_sketch(definition, {"shaft_radius": 9, "clearance": 1})
    assert numeric.constraints[0].value == 10
    assert numeric.circles == (Circle("circle", "center", 7),)
    assert numeric.schema_version == definition.schema_version == 2
    assert definition.to_json() == before
    with pytest.raises(SketchError):
        validate(definition)
    with pytest.raises(SketchError):
        Sketch.from_dict(definition.to_dict())


@pytest.mark.parametrize(
    "expression,names,code",
    [
        ("missing", {}, "unknown_parameter"),
        ("1 / zero", {"zero": 0}, "invalid_expression"),
        ("sqrt(-1)", {}, "invalid_expression"),
        ("0", {}, "invalid_number"),
        ("-1", {}, "invalid_number"),
        ("1e7", {}, "invalid_number"),
        ("__import__('os').system('unsafe')", {}, "invalid_expression"),
        ("2**13", {}, "invalid_expression"),
    ],
)
def test_radius_formula_errors_name_the_constraint_and_leave_seed_unchanged(
    expression, names, code
):
    definition = circle_definition(expression)
    before = definition.to_json()
    with pytest.raises(CADException) as error:
        resolve_sketch(definition, names)
    assert error.value.code == code
    assert "'radius'" in str(error.value)
    assert definition.to_json() == before


@pytest.mark.parametrize("expression", ["", "(", "x" * 257, "+".join(["1"] * 81)])
def test_radius_syntax_resources_have_named_errors(expression):
    with pytest.raises(CADException, match="'radius'"):
        validate_definition(circle_definition(expression))


@pytest.mark.parametrize("version", [True, False, 2.0, "2", 0, 4, None, [], {}])
def test_unknown_or_noninteger_versions_reject_in_parser_and_constructor(version):
    raw = numeric_circle().to_dict()
    raw["schema_version"] = version
    with pytest.raises(SketchError) as error:
        Sketch.from_dict(raw)
    assert error.value.code == "unsupported_schema"
    with pytest.raises(SketchError) as error:
        validate(replace(numeric_circle(), schema_version=version))
    assert error.value.code == "unsupported_schema"


def test_v2_circles_field_is_required_and_v1_never_accepts_even_an_empty_array():
    raw = numeric_circle().to_dict()
    del raw["circles"]
    with pytest.raises(SketchError, match="missing"):
        Sketch.from_dict(raw)
    raw = Sketch("old", (), (), ()).to_dict() | {"circles": []}
    with pytest.raises(SketchError, match="unknown"):
        Sketch.from_dict(raw)
    with pytest.raises(SketchError) as error:
        validate(replace(numeric_circle(), schema_version=1))
    assert error.value.code == "migration_required"
    old_radius = Sketch("old", (), (), (Constraint("radius", "radius", ("circle",), 1),))
    with pytest.raises(SketchError) as error:
        validate(old_radius)
    assert error.value.code == "migration_required"


@pytest.mark.parametrize("field", ["id", "center", "radius"])
def test_circle_required_fields_are_exact(field):
    raw = numeric_circle().to_dict()
    del raw["circles"][0][field]
    with pytest.raises(SketchError, match="missing"):
        Sketch.from_dict(raw)


@pytest.mark.parametrize("path", [(), ("circles", 0), ("constraints", 0)])
def test_new_boundaries_reject_unknown_fields(path):
    raw = numeric_circle().to_dict()
    target = raw
    for key in path:
        target = target[key]
    target["native_handle"] = 1
    with pytest.raises(SketchError, match="unknown"):
        Sketch.from_dict(raw)


@pytest.mark.parametrize(
    "value",
    [0, -1, 1e-7, 1_000_001, True, None, "radius", [], {}, float("nan"), float("inf"), 10**1000],
)
@pytest.mark.parametrize("location", ["seed", "dimension"])
def test_radius_seed_and_numeric_dimension_bounds_reject_bad_values(value, location):
    sketch = numeric_circle()
    if location == "seed":
        sketch = replace(sketch, circles=(replace(sketch.circles[0], radius=value),))
    else:
        sketch = replace(sketch, constraints=(replace(sketch.constraints[0], value=value),))
    with pytest.raises(SketchError):
        validate(sketch)
    raw = numeric_circle().to_dict()
    raw["circles" if location == "seed" else "constraints"][0][
        "radius" if location == "seed" else "value"
    ] = value
    with pytest.raises(SketchError):
        Sketch.from_dict(raw)


@pytest.mark.parametrize("radius", [1e-6, 1e6])
def test_radius_boundaries_and_independent_center_domain_are_accepted(radius):
    sketch = replace(
        numeric_circle(),
        points=(Point("center", 1e6, -1e6),),
        circles=(Circle("circle", "center", radius),),
        constraints=(Constraint("radius", "radius", ("circle",), radius),),
    )
    validate(sketch)
    assert Sketch.from_json(sketch.to_json()) == sketch


@pytest.mark.parametrize("collision", ["center", "line", "radius", "workplane", "other-circle"])
def test_circle_ids_share_namespace_with_points_lines_constraints_plane_and_circles(collision):
    sketch = replace(
        numeric_circle(),
        points=(Point("center", 3, 4), Point("end", 4, 4)),
        lines=(Line("line", "center", "end"),),
        circles=(Circle(collision, "center", 7), Circle("other-circle", "end", 2)),
    )
    with pytest.raises(SketchError) as error:
        validate(sketch)
    assert error.value.code == "duplicate_id"


@pytest.mark.parametrize("center", ["missing", "circle", "radius", "workplane", [], {}, True, None])
def test_circle_center_requires_point_identity(center):
    sketch = replace(numeric_circle(), circles=(Circle("circle", center, 7),))
    with pytest.raises(SketchError):
        validate(sketch)


@pytest.mark.parametrize(
    "refs", [(), ("center",), ("missing",), ("circle", "circle"), ("workplane",), ["circle"]]
)
def test_radius_references_require_exactly_one_existing_circle(refs):
    sketch = replace(numeric_circle(), constraints=(Constraint("radius", "radius", refs, 10),))
    with pytest.raises(SketchError):
        validate(sketch)


def test_radius_cannot_carry_a_fixed_target_or_formula_seed():
    sketch = numeric_circle()
    with pytest.raises(SketchError, match="target"):
        validate(replace(sketch, constraints=(replace(sketch.constraints[0], target=(0, 0)),)))
    with pytest.raises(SketchError):
        validate_definition(
            replace(circle_definition(), circles=(Circle("circle", "center", "shaft_radius"),))
        )


@pytest.mark.parametrize("circles", [[], None, (None,), (Point("circle", 3, 4),)])
def test_direct_constructor_requires_an_immutable_circle_tuple(circles):
    with pytest.raises(SketchError):
        validate(replace(numeric_circle(), circles=circles))


def test_circle_and_curve_record_budgets_are_independent_and_exact():
    points = (Point("a", 0, 0), Point("b", 1, 0))
    circles = tuple(Circle(f"c{i}", "a", 1) for i in range(MAX_CIRCLES))
    sketch = Sketch("limits", points, (), (), schema_version=2, circles=circles)
    validate(sketch)
    assert len(Sketch.from_json(sketch.to_json()).circles) == MAX_CIRCLES
    with pytest.raises(SketchError) as error:
        validate(replace(sketch, circles=circles + (Circle("one-more", "a", 1),)))
    assert error.value.code == "resource_limit"
    mixed = replace(sketch, circles=circles[:-1], lines=(Line("line", "a", "b"),))
    assert len(mixed.lines) + len(mixed.circles) == MAX_CURVES
    validate(mixed)
    with pytest.raises(SketchError) as error:
        validate(replace(mixed, circles=circles))
    assert error.value.code == "resource_limit"


def test_active_scalar_budget_exact_boundary_and_before_record_inspection():
    points = tuple(Point(f"p{i}", 0, 0) for i in range(MAX_POINTS - 1))
    circles = (Circle("c0", "p0", 1), Circle("c1", "p1", 1))
    sketch = Sketch("scalars", points, (), (), schema_version=2, circles=circles)
    assert active_scalar_count(sketch) == MAX_ACTIVE_SCALARS
    validate(sketch)
    raw = sketch.to_dict()
    raw["circles"].append(None)  # Aggregate limit must reject before inspecting this record.
    with pytest.raises(SketchError) as error:
        Sketch.from_dict(raw)
    assert error.value.code == "resource_limit"
    with pytest.raises(SketchError) as error:
        validate(replace(sketch, points=points + (Point("last", 0, 0),)))
    assert error.value.code == "resource_limit"
    legacy = Sketch("legacy", points + (Point("last", 0, 0),), (), ())
    validate(legacy)
    assert active_scalar_count(legacy) == MAX_ACTIVE_SCALARS


def test_v2_512_constraints_and_legacy_optional_null_defaults_remain_valid():
    sketch = replace(
        numeric_circle(),
        constraints=tuple(
            Constraint(f"r{i}", "radius", ("circle",), 10) for i in range(MAX_CONSTRAINTS)
        ),
    )
    raw = sketch.to_dict()
    for constraint in raw["constraints"]:
        del constraint["target"]
    assert Sketch.from_dict(raw).to_json() == sketch.to_json()
    raw["constraints"].append(None)
    with pytest.raises(SketchError) as error:
        Sketch.from_dict(raw)
    assert error.value.code == "resource_limit"


def test_v2_direct_dict_depth_cycles_and_expanded_alias_trees_are_bounded():
    for bad in ([],):
        bad.append(bad)
        raw = numeric_circle().to_dict() | {"extra": bad}
        with pytest.raises(SketchError) as error:
            Sketch.from_dict(raw)
        assert error.value.code == "resource_limit"
    shared = ["x" * 1000] * 100
    raw = numeric_circle().to_dict() | {"extra": [shared] * 3}
    with pytest.raises(SketchError) as error:
        Sketch.from_dict(raw)
    assert error.value.code == "sketch_too_large"


def test_v2_json_lexical_depth_long_numeric_tokens_and_duplicate_circle_keys():
    with pytest.raises(SketchError) as error:
        Sketch.from_json("[" * (MAX_JSON_DEPTH + 1) + "0" + "]" * (MAX_JSON_DEPTH + 1))
    assert error.value.code == "resource_limit"
    raw = (
        numeric_circle()
        .to_json()
        .replace('"radius":7.0', '"radius":1.' + "0" * MAX_NUMBER_CHARACTERS)
    )
    with pytest.raises(SketchError) as error:
        Sketch.from_json(raw)
    assert error.value.code == "resource_limit"
    raw = numeric_circle().to_json().replace('"radius":7.0', '"radius":7.0,"radius":8.0')
    with pytest.raises(SketchError) as error:
        Sketch.from_json(raw)
    assert error.value.code == "invalid_json"


def test_v2_standalone_exact_utf8_limit_and_nested_direct_dict_budget():
    raw = numeric_circle().to_json()
    padded = raw + " " * (MAX_SKETCH_BYTES - len(raw.encode()))
    assert Sketch.from_json(padded).to_json() == raw
    with pytest.raises(SketchError) as error:
        Sketch.from_json(padded + " ")
    assert error.value.code == "sketch_too_large"
    raw = circle_document().to_dict()
    raw["features"][0]["sketch"]["extra"] = "x" * MAX_SKETCH_BYTES
    before = copy.deepcopy(raw)
    with pytest.raises(SketchError) as error:
        Document.from_dict(raw)
    assert error.value.code == "sketch_too_large"
    assert raw == before


def test_new_schema_and_solver_imports_stay_native_free_until_solve():
    code = (
        f"import sys; sys.path.insert(0, {str(ROOT / 'src')!r}); "
        "from mechanical_cad.sketch_model import Circle, Sketch, Point; "
        "import mechanical_cad.sketch_solver; "
        "s = Sketch('s', (Point('p',0,0),), (), (), schema_version=2, circles=(Circle('c','p',1),)); "
        "assert Sketch.from_json(s.to_json()) == s; "
        "assert 'slvs' not in sys.modules and 'OCP' not in sys.modules"
    )
    result = subprocess.run(
        [sys.executable, "-S", "-c", code], capture_output=True, text=True, timeout=10
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("length", [MAX_NUMBER_CHARACTERS, MAX_NUMBER_CHARACTERS + 1])
@pytest.mark.parametrize("location", ["radius", "coordinate", "parameter"])
def test_document_and_file_nested_v2_enforce_original_numeric_lexemes(tmp_path, length, location):
    raw = circle_document().to_dict()
    if location == "radius":
        needle, value = '"radius":7.0', 7
    elif location == "coordinate":
        needle, value = '"u":3.0', 3
    else:
        needle, value = '"shaft_radius":9', 9
    token = str(value) + "." + "0" * (length - 2)
    text = json.dumps(raw, separators=(",", ":"))
    assert needle in text
    text = text.replace(needle, needle.split(":")[0] + ":" + token, 1)
    path = tmp_path / "circle.mcad.json"
    path.write_text(text)
    for load in (lambda: Document.from_json(text), lambda: load_document(path)):
        if length <= MAX_NUMBER_CHARACTERS:
            assert load().features[0].sketch.schema_version == 2
        else:
            with pytest.raises(SketchError) as error:
                load()
            assert error.value.code == "resource_limit"


def test_legacy_nested_sketch_keeps_its_accepted_long_float_spelling(tmp_path):
    original = load_document(ROOT / "examples/constrained_plate.mcad.json")
    raw = original.to_dict()
    raw["features"][0]["sketch"]["points"][0]["u"] = 3.0
    text = json.dumps(raw, separators=(",", ":"))
    token = "3." + "0" * (MAX_NUMBER_CHARACTERS + 100)
    assert '"u":3.0' in text
    text = text.replace('"u":3.0', '"u":' + token, 1)
    path = tmp_path / "legacy.mcad.json"
    path.write_text(text)
    canonical = Document.from_dict(raw).to_json()
    assert Document.from_json(text).to_json() == canonical
    assert load_document(path).to_json() == canonical


def test_oversized_valid_record_tree_is_rejected_by_v2_without_hardening_legacy_dicts():
    # All per-record bounds are valid, but their aggregate canonical JSON is too large.
    a, b = "a" * 128, "b" * 128
    legacy = SketchDefinition(
        "large",
        (Point(a, 0, 0), Point(b, 1, 0)),
        (),
        tuple(
            Constraint(f"c{i:0127d}", "distance", (a, b), "1" + " " * 255)
            for i in range(MAX_CONSTRAINTS)
        ),
    )
    raw = legacy.to_dict()
    assert len(json.dumps(raw, separators=(",", ":"))) > MAX_SKETCH_BYTES
    assert SketchDefinition.from_dict(raw).to_dict() == raw  # Frozen v1 dict behavior.
    with pytest.raises(SketchError) as error:
        legacy.to_json()
    assert error.value.code == "sketch_too_large"
    with pytest.raises(SketchError) as error:
        legacy.migrate_to_v2()
    assert error.value.code == "sketch_too_large"
    with pytest.raises(SketchError) as error:
        SketchDefinition.from_dict(raw | {"schema_version": 2, "circles": []})
    assert error.value.code == "sketch_too_large"


@pytest.mark.parametrize(
    "value,code",
    [(10**128, "resource_limit"), (10**20, "invalid_number"), (float("inf"), "invalid_number")],
)
def test_v2_document_all_numeric_fields_self_roundtrip_or_reject_at_every_boundary(value, code):
    document = circle_document()
    extrude = Feature("extrude", "extrude", "Extrude", {"length": value}, {"profile": "sketch"})
    raw = document.to_dict()
    raw["features"].append(extrude.to_dict())
    raw["active_feature"] = "extrude"
    with pytest.raises(SketchError) as error:
        Document.from_dict(raw)
    assert error.value.code == code
    with pytest.raises(SketchError) as error:
        replace(document, features=(*document.features, extrude), active_feature="extrude")
    assert error.value.code == code
    if isinstance(value, int):
        with pytest.raises(SketchError) as error:
            Document.from_json(json.dumps(raw))
        assert error.value.code == code


def test_legacy_document_retains_structurally_accepted_large_feature_number():
    legacy = load_document(ROOT / "examples/constrained_plate.mcad.json")
    raw = legacy.to_dict()
    raw["features"][1]["params"]["length"] = 10**128
    loaded = Document.from_dict(raw)
    # Structural legacy acceptance does not claim successful geometry replay.
    assert Document.from_json(loaded.to_json()).to_json() == loaded.to_json()


@pytest.mark.parametrize("location", ["parameters", "feature", "root"])
def test_v2_document_direct_dict_cycles_fail_before_copy_or_expansion(location):
    raw = circle_document().to_dict()
    cycle = []
    cycle.append(cycle)
    if location == "parameters":
        raw["parameters"]["bad"] = cycle
    elif location == "feature":
        raw["features"][0]["params"]["bad"] = cycle
    else:
        raw["extra"] = cycle
    with pytest.raises(SketchError) as error:
        Document.from_dict(raw)
    assert error.value.code == "resource_limit"


def test_v2_direct_document_constructor_guards_cyclic_parameters_before_deepcopy():
    parameters = {}
    parameters["cycle"] = parameters
    with pytest.raises(SketchError) as error:
        replace(circle_document(), parameters=parameters)
    assert error.value.code == "resource_limit"


def test_shared_tree_expansion_is_bounded_without_revisiting_every_alias(monkeypatch):
    import mechanical_cad.sketch_model as model

    raw = circle_document().to_dict()
    shared = [1] * 64
    for _ in range(4):
        shared = [shared] * 64
    raw["extra"] = shared  # Tiny object DAG, enormous serialized tree.
    calls = 0
    parse_number = model._parse_number

    def count(*args, **kwargs):
        nonlocal calls
        calls += 1
        return parse_number(*args, **kwargs)

    monkeypatch.setattr(model, "_parse_number", count)
    with pytest.raises(SketchError) as error:
        Document.from_dict(raw)
    assert error.value.code == "document_too_large"
    assert calls < 1000  # Memoized containers, rather than millions of expanded leaves.


def test_memoized_subtree_cannot_bypass_deeper_lexical_nesting_limit():
    shared = [[[]]]
    deep = shared
    for _ in range(MAX_JSON_DEPTH - 3):
        deep = [deep]
    raw = numeric_circle().to_dict() | {"shallow": shared, "deep": deep}
    with pytest.raises(SketchError) as error:
        Sketch.from_dict(raw)
    assert error.value.code == "resource_limit"


def test_direct_tree_budget_counts_exact_canonical_escaped_json_bytes():
    from mechanical_cad.sketch_model import _check_object_budget

    data = {
        "control": '\b\f\n\r\t\x01\\"',
        "unicode": "é😀",
        "items": [None, True, False, -1, 1e-6],
    }
    size = len(json.dumps(data, separators=(",", ":")))
    _check_object_budget(data, max_bytes=size)
    with pytest.raises(SketchError) as error:
        _check_object_budget(data, max_bytes=size - 1)
    assert error.value.code == "sketch_too_large"


def many_constraint_sketches(*, version=2, count=20):
    definition = SketchDefinition(
        "s",
        (Point("a", 0, 0), Point("b", 1, 0)),
        (),
        tuple(Constraint(f"c{i}", "distance", ("a", "b"), 1) for i in range(512)),
        schema_version=version,
    )
    raw = {
        "schema_version": 2,
        "id": "doc",
        "name": "Doc",
        "units": "mm",
        "parameters": {},
        "features": [
            {"id": f"f{i}", "kind": "sketch_constrained", "sketch": definition.to_dict()}
            for i in range(count)
        ],
        "active_feature": "f0",
    }
    return definition, raw


def test_compact_v2_input_that_exceeds_persisted_indent_budget_rejects_before_acceptance():
    from mechanical_cad.model import MAX_DOCUMENT_BYTES

    definition, raw = many_constraint_sketches()
    compact = json.dumps(raw, separators=(",", ":"))
    assert len(compact) == 771_478 < MAX_DOCUMENT_BYTES
    # Known normalized canonical size, measured independently of Document APIs.
    normalized = raw | {
        "features": [Feature.from_dict(feature).to_dict() for feature in raw["features"]]
    }
    assert len(json.dumps(normalized, sort_keys=True, indent=2) + "\n") == 2_163_641
    for construct in (
        lambda: Document.from_dict(raw),
        lambda: Document.from_json(compact),
        lambda: Document(
            "doc",
            "Doc",
            {},
            tuple(
                Feature(f"f{i}", "sketch_constrained", f"f{i}", sketch=definition)
                for i in range(20)
            ),
            "f0",
            schema_version=2,
        ),
    ):
        with pytest.raises(CADException) as error:
            construct()
        assert error.value.code == "document_too_large"


def test_persisted_v2_byte_limit_is_exact_and_validate_rechecks_it(monkeypatch):
    import mechanical_cad.model as model

    document = circle_document()
    canonical = document.to_json()
    size = len(canonical.encode("utf-8"))
    assert len(json.dumps(document.to_dict(), separators=(",", ":"))) < size - 1
    monkeypatch.setattr(model, "MAX_DOCUMENT_BYTES", size)
    document.validate()
    assert Document.from_dict(document.to_dict()).to_json() == canonical
    assert Document.from_json(canonical).to_json() == canonical
    monkeypatch.setattr(model, "MAX_DOCUMENT_BYTES", size - 1)
    for check in (document.validate, document.to_dict, document.to_json):
        with pytest.raises(CADException) as error:
            check()
        assert error.value.code == "document_too_large"


def test_persisted_byte_hardening_does_not_rewrite_legacy_v1_acceptance():
    from mechanical_cad.model import MAX_DOCUMENT_BYTES

    _, raw = many_constraint_sketches(version=1)
    document = Document.from_dict(raw)
    document.validate()
    # Frozen legacy acceptance: this slice does not retroactively harden v1-only
    # direct constructors/dicts that historically emit oversize pretty JSON.
    assert len(document.to_json().encode()) > MAX_DOCUMENT_BYTES
    assert all(feature.sketch.schema_version == 1 for feature in document.features)
