"""Source-bound, native-free conversion of typed open sketches to display wires."""

import copy
import importlib.util
import json
import math
import subprocess
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "blender_addon/mechanical_cad_blender/sketch_display.py"
PACKAGE = "mcad_sketch_display_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(MODULE.parent)]
sys.modules[PACKAGE] = package
SPEC = importlib.util.spec_from_file_location(PACKAGE + ".sketch_display", MODULE)
sketch_display = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = sketch_display
SPEC.loader.exec_module(sketch_display)


def _example(name="open_line_sketch"):
    return json.loads((ROOT / "examples" / f"{name}.mcad.json").read_text())


def _replay_open(document):
    """Use the real native solver; any accidental shape/kernel work must fail."""
    pytest.importorskip("slvs")
    from mechanical_cad.engine import regenerate
    from mechanical_cad.model import Document

    parsed = Document.from_dict(document)
    replay = regenerate(parsed, object(), result_version=2)
    assert replay.ok, replay.result
    assert replay.shapes == {}
    feature = replay.result["features"][0]
    assert feature["output"]["profile"]["state"] == "unavailable"
    assert feature["sketch"]["solver"] == "libslvs"
    return feature, parsed.to_dict()["features"][0]


@pytest.fixture(scope="module")
def open_evidence():
    return _replay_open(_example())


@pytest.fixture
def evidence(open_evidence):
    return copy.deepcopy(open_evidence)


def _fixed_chain(points, lines, *, plane=None, constraints=None):
    document = _example()
    document["parameters"] = {}
    sketch = document["features"][0]["sketch"]
    sketch.update(points=points, lines=lines)
    if plane is not None:
        sketch["plane"] = plane
    sketch["constraints"] = (
        constraints
        if constraints is not None
        else [
            {
                "id": "fix_" + point["id"],
                "kind": "fixed",
                "refs": [point["id"]],
                "target": [point["u"], point["v"]],
            }
            for point in points
        ]
    )
    return document


@pytest.mark.parametrize("requested", [None, 1, 2])
@pytest.mark.parametrize("name", ["drilled_plate", "viewport_rectangle"])
def test_legacy_documents_keep_default_result_version(name, requested):
    document = _example(name)
    before = copy.deepcopy(document)
    assert sketch_display.negotiated_result_version(document, requested) == (requested or 1)
    assert document == before


@pytest.mark.parametrize("requested", [None, 2])
def test_any_embedded_schema_two_requires_typed_results(requested):
    document = _example("drilled_plate")
    document["features"].extend(_example()["features"])
    before = copy.deepcopy(document)
    assert sketch_display.negotiated_result_version(document, requested) == 2
    assert document == before


def test_explicit_legacy_results_cannot_downgrade_schema_two():
    with pytest.raises(ValueError, match="version 2"):
        sketch_display.negotiated_result_version(_example(), 1)


@pytest.mark.parametrize("requested", [True, False, 0, -1, 3, 1.0, 2.0, "2", [], {}])
def test_requested_result_version_is_a_known_integer(requested):
    with pytest.raises(ValueError):
        sketch_display.negotiated_result_version(_example("drilled_plate"), requested)


@pytest.mark.parametrize("version", [True, False, None, 0, 3, 1.0, 2.0, "2", [], {}])
@pytest.mark.parametrize("requested", [None, 2])
def test_unknown_embedded_versions_fail_even_with_explicit_typed_results(version, requested):
    document = _example()
    document["features"][0]["sketch"]["schema_version"] = version
    with pytest.raises(ValueError):
        sketch_display.negotiated_result_version(document, requested)


@pytest.mark.parametrize(
    "document",
    [None, [], {}, {"features": None}, {"features": [None]}, {"features": [{"sketch": None}]}],
)
def test_negotiation_rejects_malformed_feature_containers(document):
    with pytest.raises(ValueError):
        sketch_display.negotiated_result_version(document)


def test_default_wire_is_detached_and_contains_only_oriented_lines(evidence):
    feature, source = evidence
    before = copy.deepcopy(evidence)
    wire = sketch_display.solved_line_wire(feature, source)
    assert set(wire) == {"vertices", "edges", "triangles", "point_ids", "line_ids"}
    assert wire["point_ids"] == ["corner", "end_u", "end_v"]
    assert wire["line_ids"] == ["horizontal_leg", "vertical_leg"]
    assert [tuple(edge) for edge in wire["edges"]] == [(0, 1), (1, 2)]
    assert wire["triangles"] == []
    assert [tuple(vertex) for vertex in wire["vertices"]] == [
        (0, 0, 0),
        (0.03, 0, 0),
        (0.03, 0.02, 0),
    ]
    assert evidence == before
    wire["point_ids"][0] = "display_only"
    wire["line_ids"].clear()
    wire["vertices"].clear()
    wire["edges"].clear()
    assert evidence == before


def test_wire_uses_solved_coordinates_instead_of_authored_seeds():
    document = _example()
    document["parameters"].update(width=70, height=45)
    feature, source = _replay_open(document)
    assert source["sketch"]["points"][1]["u"] == 30
    wire = sketch_display.solved_line_wire(feature, source, scale=1)
    assert wire["vertices"][1] == pytest.approx((70, 0, 0))
    assert wire["vertices"][2] == pytest.approx((70, 45, 0))


@pytest.mark.parametrize("norm_factor", [1.0, 1 + 2e-10])
def test_arbitrary_wxyz_workplane_normalizes_accepted_near_unit_quaternions(norm_factor):
    document = _example()
    quaternion = [value * norm_factor / math.sqrt(30) for value in (1, 2, 3, 4)]
    document["features"][0]["sketch"]["plane"].update(origin=[17, -29, 41], quaternion=quaternion)
    feature, source = _replay_open(document)
    before = copy.deepcopy((feature, source))
    wire = sketch_display.solved_line_wire(feature, source, scale=0.002)
    # Independent exact columns for normalized WXYZ=(1, 2, 3, 4)/sqrt(30).
    u_axis, v_axis = (-2 / 3, 2 / 3, 1 / 3), (2 / 15, -1 / 3, 14 / 15)
    for vertex, point in zip(wire["vertices"], feature["sketch"]["solved"]["points"], strict=True):
        expected = tuple(
            0.002 * (origin + point["u"] * u + point["v"] * v)
            for origin, u, v in zip((17, -29, 41), u_axis, v_axis, strict=True)
        )
        assert vertex == pytest.approx(expected, rel=0, abs=1e-14)
    assert (feature, source) == before
    assert source["sketch"]["plane"]["quaternion"] == quaternion


def test_ids_and_endpoint_orientation_do_not_follow_input_or_traversal_order():
    document = _fixed_chain(
        [
            {"id": "z_tail", "u": 0, "v": 0},
            {"id": "m_elbow", "u": 30, "v": 0},
            {"id": "a_tip", "u": 30, "v": 20},
        ],
        [
            {"id": "z_bottom", "start": "z_tail", "end": "m_elbow"},
            {"id": "a_upright", "start": "a_tip", "end": "m_elbow"},
        ],
    )
    feature, source = _replay_open(document)
    # The wire contract remains deterministic for valid unsorted JSON evidence.
    source["sketch"]["points"].reverse()
    source["sketch"]["lines"].reverse()
    feature["sketch"]["solved"]["points"].reverse()
    feature["sketch"]["solved"]["lines"].reverse()
    wire = sketch_display.solved_line_wire(feature, source, scale=1)
    assert wire["point_ids"] == ["a_tip", "m_elbow", "z_tail"]
    assert wire["line_ids"] == ["a_upright", "z_bottom"]
    assert [tuple(edge) for edge in wire["edges"]] == [(0, 1), (2, 1)]
    assert [tuple(vertex) for vertex in wire["vertices"]] == [(30, 20, 0), (30, 0, 0), (0, 0, 0)]


def test_coincident_distinct_points_are_never_welded_or_renamed():
    points = [
        {"id": f"p{index}", "u": u, "v": v}
        for index, (u, v) in enumerate(((0, 0), (10, 0), (10, 0), (10, 10)))
    ]
    constraints = [
        {"id": "fix_" + p["id"], "kind": "fixed", "refs": [p["id"]], "target": [p["u"], p["v"]]}
        for p in points
        if p["id"] != "p2"
    ] + [{"id": "join", "kind": "coincident", "refs": ["p1", "p2"]}]
    document = _fixed_chain(
        points,
        [
            {"id": "z_first", "start": "p0", "end": "p1"},
            {"id": "a_second", "start": "p2", "end": "p3"},
        ],
        constraints=constraints,
    )
    feature, source = _replay_open(document)
    wire = sketch_display.solved_line_wire(feature, source)
    assert wire["point_ids"] == ["p0", "p1", "p2", "p3"]
    assert wire["line_ids"] == ["a_second", "z_first"]
    assert [tuple(edge) for edge in wire["edges"]] == [(2, 3), (0, 1)]
    assert len(wire["vertices"]) == 4
    assert wire["vertices"][1] == wire["vertices"][2]


def test_far_origin_preserves_tiny_line_dimensions_without_float32_rounding():
    document = _fixed_chain(
        [
            {"id": "a", "u": 0, "v": 0},
            {"id": "b", "u": 1e-5, "v": 0},
            {"id": "c", "u": 1e-5, "v": 2e-5},
        ],
        [{"id": "ab", "start": "a", "end": "b"}, {"id": "bc", "start": "b", "end": "c"}],
        plane={"id": "workplane", "origin": [1e6, -1e6, 1e6], "quaternion": [1, 0, 0, 0]},
    )
    feature, source = _replay_open(document)
    wire = sketch_display.solved_line_wire(feature, source)
    a, b, c = wire["vertices"]
    assert tuple(a) == (1000, -1000, 1000)
    assert b[0] - a[0] == pytest.approx(1e-8, rel=0, abs=2e-13)
    assert c[1] - b[1] == pytest.approx(2e-8, rel=0, abs=2e-13)
    assert len({tuple(vertex) for vertex in wire["vertices"]}) == 3


@pytest.mark.parametrize(
    "scale",
    [
        True,
        False,
        None,
        0,
        -1,
        float("nan"),
        float("inf"),
        "0.001",
        [],
        pytest.param(10**1000, id="oversized-integer"),
    ],
)
def test_invalid_display_scale_is_a_value_error(evidence, scale):
    feature, source = evidence
    with pytest.raises(ValueError):
        sketch_display.solved_line_wire(feature, source, scale=scale)


@pytest.mark.parametrize("scale", [1e38, 1e308])
def test_scaled_coordinates_must_fit_finite_blender_float32_range(evidence, scale):
    feature, source = evidence
    with pytest.raises(ValueError):
        sketch_display.solved_line_wire(feature, source, scale=scale)


def test_large_but_representable_scaled_coordinates_remain_valid(evidence):
    feature, source = evidence
    wire = sketch_display.solved_line_wire(feature, source, scale=1e36)
    assert wire["vertices"][2] == pytest.approx((3e37, 2e37, 0))


@pytest.mark.parametrize(
    "change",
    [
        lambda f: f.pop("output"),
        lambda f: f.update(output=None),
        lambda f: f.update(id="another_feature"),
        lambda f: f.update(error={"code": "failed", "message": "Contradiction"}),
        lambda f: f.update(mesh={"vertices": [], "triangles": []}),
        lambda f: f.update(stats={"volume": 1}),
        lambda f: f.update(topology=[{"id": "invented_face"}]),
        lambda f: f.update(sketch=None),
        lambda f: f["output"].update(display="mesh"),
        lambda f: f["output"]["profile"]["reason"].update(code="invalid_profile"),
        lambda f: f["sketch"].update(remaining_dof=True),
        lambda f: f["sketch"].update(max_residual_mm=1e-3),
        lambda f: f["sketch"].update(solver="invented"),
        lambda f: f["sketch"]["dimensions"].update(width=99),
        lambda f: f["sketch"]["solved"]["plane"].update(origin=[1, 0, 0]),
        lambda f: f["sketch"]["solved"]["points"][0].update(u=1),
        lambda f: f["sketch"]["solved"]["points"][0].update(id="other_point"),
        lambda f: f["sketch"]["solved"]["points"].append(
            copy.deepcopy(f["sketch"]["solved"]["points"][0])
        ),
        lambda f: f["sketch"]["solved"]["lines"][0].update(id="other_line"),
        lambda f: f["sketch"]["solved"]["lines"][0].update(start="absent"),
        lambda f: f["sketch"]["solved"]["lines"][0].update(start="end_u", end="corner"),
        lambda f: f["sketch"]["solved"]["lines"].append(
            copy.deepcopy(f["sketch"]["solved"]["lines"][0])
        ),
        lambda f: f["sketch"]["solved"]["lines"].__setitem__(0, ["not", "a", "record"]),
        lambda f: f["sketch"]["solved"]["constraints"][0].update(refs=["corner", "end_v"]),
    ],
)
def test_forged_evidence_and_malformed_record_mapping_fail_closed(evidence, change):
    feature, source = evidence
    change(feature)
    with pytest.raises(ValueError):
        sketch_display.solved_line_wire(feature, source)


@pytest.mark.parametrize(
    "coordinate", [True, float("nan"), float("inf"), 1e6 + 1, -(1e6 + 1), 10**1000]
)
@pytest.mark.parametrize("field", ["origin", "point"])
def test_matching_source_and_result_cannot_bypass_coordinate_bounds(evidence, coordinate, field):
    feature, source = evidence
    for sketch in (source["sketch"], feature["sketch"]["solved"]):
        if field == "origin":
            sketch["plane"]["origin"][0] = coordinate
        else:
            sketch["points"][0]["u"] = coordinate
    with pytest.raises(ValueError):
        sketch_display.solved_line_wire(feature, source)


@pytest.mark.parametrize("quaternion", [[0, 0, 0, 0], [1.001, 0, 0, 0], [1, 0, 0], [True, 0, 0, 0]])
def test_matching_invalid_source_and_result_quaternions_are_rejected(evidence, quaternion):
    feature, source = evidence
    for sketch in (source["sketch"], feature["sketch"]["solved"]):
        sketch["plane"]["quaternion"] = quaternion
    with pytest.raises(ValueError):
        sketch_display.solved_line_wire(feature, source)


@pytest.mark.parametrize("status", ["failed", "blocked"])
def test_noncurrent_output_cannot_supply_a_wire(evidence, status):
    feature, source = evidence
    feature.update(status=status, output=None, error={"code": "unavailable", "message": "Retry"})
    with pytest.raises(ValueError):
        sketch_display.solved_line_wire(feature, source)


@pytest.mark.parametrize("name", ["viewport_rectangle", "circle_sketch_part", "drilled_plate"])
def test_real_closed_profiles_and_solids_are_not_open_wire_outputs(name):
    pytest.importorskip("slvs")
    pytest.importorskip("OCP")
    from mechanical_cad.engine import regenerate
    from mechanical_cad.kernel_ocp import OCPKernel
    from mechanical_cad.model import Document

    document = Document.from_dict(_example(name))
    replay = regenerate(document, OCPKernel(), result_version=2)
    assert replay.ok, replay.result
    sources = {feature["id"]: feature for feature in document.to_dict()["features"]}
    for feature in replay.result["features"]:
        with pytest.raises(ValueError):
            sketch_display.solved_line_wire(feature, sources[feature["id"]])


def test_module_import_and_negotiation_are_native_free_in_fresh_process():
    code = f"""
import builtins, importlib.util, sys, types
forbidden = {{'bpy', 'OCP', 'slvs', 'mechanical_cad'}}
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.split('.')[0] in forbidden:
        raise AssertionError('forbidden display dependency: ' + name)
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
package = types.ModuleType('display_import_probe')
package.__path__ = [{str(MODULE.parent)!r}]
sys.modules[package.__name__] = package
spec = importlib.util.spec_from_file_location('display_import_probe.sketch_display', {str(MODULE)!r})
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
assert callable(module.solved_line_wire)
assert module.negotiated_result_version({{'features': []}}) == 1
assert not forbidden.intersection(name.split('.')[0] for name in sys.modules)
"""
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=20
    )
    assert result.returncode == 0, result.stderr
