"""Real OCCT assembly queries: analytic solids, honest ambiguity and failure gates."""

import json
import math
from types import SimpleNamespace

import pytest

pytest.importorskip("OCP")

from OCP.BRep import BRep_Builder, BRep_Tool
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeSolid
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCP.gp import gp_Pnt
from OCP.TopAbs import TopAbs_FACE, TopAbs_VERTEX
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS, TopoDS_Compound, TopoDS_Shape, TopoDS_Shell

from mechanical_cad import kernel_ocp
from mechanical_cad.kernel_ocp import KernelError, OCPKernel

pytestmark = pytest.mark.kernel


def frame(xyz=(0, 0, 0), wxyz=(1, 0, 0, 0)):
    # Deliberately native-free structural frame interface, not coupled to parser.
    return SimpleNamespace(xyz_mm=xyz, wxyz=wxyz)


def box(kernel, xyz=(0, 0, 0), dimensions=(10, 10, 10)):
    x, y, z = xyz
    width, height, length = dimensions
    return kernel.extrude(kernel.rectangle(width, height, x, y, z), length)


def vertices(shape):
    explorer, result = TopExp_Explorer(shape, TopAbs_VERTEX), set()
    while explorer.More():
        result.add(tuple(BRep_Tool.Pnt_s(TopoDS.Vertex(explorer.Current())).Coord()))
        explorer.Next()
    return sorted(result)


def compound(*shapes):
    builder, result = BRep_Builder(), TopoDS_Compound()
    builder.MakeCompound(result)
    for shape in shapes:
        builder.Add(result, shape)
    return result


def assert_report_finite(result):
    json.dumps(result, allow_nan=False)
    if result["witness_points_mm"] is not None:
        assert len(result["witness_points_mm"]) == 2
        assert all(len(point) == 3 for point in result["witness_points_mm"])
        assert math.dist(*result["witness_points_mm"]) == pytest.approx(
            result["minimum_distance_mm"], abs=1e-6
        )


@pytest.mark.parametrize(
    "position,relation,volume,gap,verdict",
    [
        ((12, 0, 0), "separated", 0, 2, "pass_at_pose"),
        ((10, 0, 0), "contact_or_near", 0, 0, "at_threshold"),
        ((10, 10, 0), "contact_or_near", 0, 0, "at_threshold"),
        ((10, 10, 10), "contact_or_near", 0, 0, "at_threshold"),
        ((5, 0, 0), "interference", 500, 0, "fail_interference"),
        ((0, 0, 0), "interference", 1000, 0, "fail_interference"),
        ((12, 13, 14), "separated", 0, math.sqrt(29), "pass_at_pose"),
    ],
)
def test_analytic_box_pair_cases(position, relation, volume, gap, verdict):
    kernel = OCPKernel()
    a = box(kernel)
    b = kernel.transformed(a, frame(position))
    before = (vertices(a), vertices(b), kernel.inspect(a), kernel.inspect(b))
    result = kernel.pair_check(a, b)
    assert result["complete"], result
    assert result["relation"] == relation
    assert result["common_volume_mm3"] == pytest.approx(volume, abs=1e-10)
    assert result["minimum_distance_mm"] == pytest.approx(gap, abs=1e-10)
    assert result["clearance_verdict"] == verdict
    assert result["known_interference"] is (volume > 0)
    assert not result["known_clearance_violation"]
    assert (vertices(a), vertices(b), kernel.inspect(a), kernel.inspect(b)) == before
    assert_report_finite(result)


@pytest.mark.parametrize("reverse", [False, True])
def test_containment_reports_true_surface_distance_not_solid_set_distance(reverse):
    kernel = OCPKernel()
    outer, inner = box(kernel), box(kernel, (2, 2, 2), (2, 2, 2))
    a, b = (inner, outer) if reverse else (outer, inner)
    result = kernel.pair_check(a, b)
    assert result["complete"]
    assert result["common_volume_mm3"] == pytest.approx(8)
    assert result["minimum_distance_mm"] == pytest.approx(2)
    assert result["clearance_verdict"] == "fail_interference"
    assert result["known_interference"]
    assert_report_finite(result)


def test_cylinder_overlap_has_analytic_common_volume():
    kernel = OCPKernel()
    a = kernel.extrude(kernel.circle(2), 10)
    b = kernel.transformed(a, frame((0, 0, 4)))
    result = kernel.pair_check(a, b)
    assert result["complete"], result
    assert result["common_volume_mm3"] == pytest.approx(math.pi * 4 * 6, rel=1e-11)
    assert result["minimum_distance_mm"] == pytest.approx(0, abs=1e-10)
    assert result["known_interference"]


@pytest.mark.parametrize(
    "x,expected_gap,relation", [(4, 0, "contact_or_near"), (4.5, 0.5, "separated")]
)
def test_tangent_and_disjoint_cylinders(x, expected_gap, relation):
    kernel = OCPKernel()
    a = kernel.extrude(kernel.circle(2), 10)
    b = kernel.transformed(a, frame((x, 0, 0)))
    result = kernel.pair_check(a, b)
    assert result["complete"], result
    assert result["common_volume_mm3"] == 0
    assert result["minimum_distance_mm"] == pytest.approx(expected_gap, abs=1e-8)
    assert result["relation"] == relation
    assert_report_finite(result)


def test_arbitrary_rotation_uses_part_origin_preserves_source_and_has_no_topology_claim():
    kernel = OCPKernel()
    shape = box(kernel, (17, -9, 4), (2, 3, 5))
    source_vertices, stats = vertices(shape), kernel.inspect(shape)
    kernel.topology(shape, "body", "extrude", {})
    axis = (1 / math.sqrt(14), 2 / math.sqrt(14), 3 / math.sqrt(14))
    angle, origin = 0.73, (80, -61, 7)
    quaternion = (math.cos(angle / 2), *(v * math.sin(angle / 2) for v in axis))
    placement = frame(origin, quaternion)
    result = kernel.transformed(shape, placement)
    expected = []
    c, s = math.cos(angle), math.sin(angle)
    for point in source_vertices:
        dot = sum(a * p for a, p in zip(axis, point, strict=True))
        cross = (
            axis[1] * point[2] - axis[2] * point[1],
            axis[2] * point[0] - axis[0] * point[2],
            axis[0] * point[1] - axis[1] * point[0],
        )
        expected.append(
            tuple(
                c * point[i] + s * cross[i] + (1 - c) * axis[i] * dot + origin[i] for i in range(3)
            )
        )
    for actual, target in zip(vertices(result), sorted(expected), strict=True):
        assert actual == pytest.approx(target, abs=1e-10)
    assert kernel.inspect(result)["volume"] == pytest.approx(stats["volume"], rel=1e-12)
    assert not result.IsSame(shape)
    assert vertices(shape) == source_vertices
    assert placement.wxyz == quaternion and placement.xyz_mm == origin
    topology = kernel.topology(result, "placed", "extrude", {})
    assert all(candidate["provenance"]["semantic_status"] == "unknown" for candidate in topology)


@pytest.mark.parametrize("sign", [-1, 1])
def test_near_unit_quaternion_is_temporarily_normalized_only(sign):
    kernel = OCPKernel()
    shape = box(kernel, (4, 5, 6), (2, 3, 4))
    q = tuple(sign * v * (1 + 2e-10) for v in (math.sqrt(0.5), 0, 0, math.sqrt(0.5)))
    placement = {"xyz_mm": [10, 20, 30], "wxyz": list(q)}
    saved = json.dumps(placement)
    result = kernel.transformed(shape, placement)
    expected = sorted((10 - y, 20 + x, 30 + z) for x, y, z in vertices(shape))
    assert len(vertices(result)) == len(expected)
    for actual in vertices(result):
        assert min(math.dist(actual, target) for target in expected) < 1e-10
    assert kernel.inspect(result)["volume"] == pytest.approx(24, abs=1e-11)
    assert json.dumps(placement) == saved


@pytest.mark.parametrize(
    "placement",
    [
        None,
        {},
        {"xyz_mm": [0, 0, 0], "wxyz": [1, 0, 0, 0], "extra": 1},
        frame((0, 0)),
        frame((0, 0, 0, 0)),
        frame((True, 0, 0)),
        frame(("0", 0, 0)),
        frame((float("nan"), 0, 0)),
        frame((float("inf"), 0, 0)),
        frame((1e6 + 1, 0, 0)),
        frame((10**400, 0, 0)),
        frame(wxyz=(1, 0, 0)),
        frame(wxyz=(0, 0, 0, 0)),
        frame(wxyz=(1.00001, 0, 0, 0)),
        frame(wxyz=(True, 0, 0, 0)),
        frame(wxyz=(float("nan"), 0, 0, 0)),
        frame(wxyz=(1, "0", 0, 0)),
    ],
)
def test_malformed_frames_fail_before_native_transform(placement, monkeypatch):
    kernel = OCPKernel()
    shape = box(kernel)
    monkeypatch.setattr(
        kernel_ocp, "BRepBuilderAPI_Transform", lambda *args: pytest.fail("must validate first")
    )
    with pytest.raises(KernelError):
        kernel.transformed(shape, placement)


@pytest.mark.parametrize(
    "keyword", ["linear_tolerance_mm", "volume_tolerance_mm3", "minimum_required_mm"]
)
@pytest.mark.parametrize(
    "value", [True, False, "0.1", None, float("nan"), float("inf"), -1, 10**400]
)
def test_malformed_query_parameters_fail_before_native_work(keyword, value, monkeypatch):
    kernel = OCPKernel()
    monkeypatch.setattr(
        kernel, "_require_single_solid", lambda *args, **kwargs: pytest.fail("must validate first")
    )
    with pytest.raises(KernelError):
        kernel.pair_check(None, None, **{keyword: value})


@pytest.mark.parametrize("keyword", ["linear_tolerance_mm", "volume_tolerance_mm3"])
@pytest.mark.parametrize("value", [0, 1.00001])
def test_query_tolerances_are_positive_and_bounded(keyword, value):
    with pytest.raises(KernelError):
        OCPKernel().pair_check(None, None, **{keyword: value})


@pytest.mark.parametrize(
    "required,verdict",
    [
        (1.9, "pass_at_pose"),
        (2, "at_threshold"),
        (2 + 5e-7, "at_threshold"),
        (2.1, "fail_clearance"),
    ],
)
def test_clearance_threshold_is_never_silently_passed(required, verdict):
    kernel = OCPKernel()
    result = kernel.pair_check(box(kernel), box(kernel, (12, 0, 0)), minimum_required_mm=required)
    assert result["complete"]
    assert result["clearance_verdict"] == verdict
    assert result["known_clearance_violation"] is (verdict == "fail_clearance")


def test_positive_subthreshold_overlap_is_retained_and_never_clear():
    kernel = OCPKernel()
    a = box(kernel, dimensions=(0.01, 0.01, 0.01))
    b = box(kernel, (0.0099, 0, 0), (0.01, 0.01, 0.01))
    result = kernel.pair_check(a, b, volume_tolerance_mm3=1e-7)
    assert result["common_volume_mm3"] == pytest.approx(1e-8, abs=1e-14)
    assert result["relation"] == "indeterminate_small_overlap"
    assert result["clearance_verdict"] == "indeterminate"
    assert not result["complete"]
    assert not result["known_interference"]
    assert result["diagnostics"][0]["code"] == "small_positive_overlap"


def test_near_contact_is_not_a_clear_pass():
    kernel = OCPKernel()
    result = kernel.pair_check(box(kernel), box(kernel, (10 + 5e-7, 0, 0)))
    assert result["relation"] == "contact_or_near"
    assert result["clearance_verdict"] == "at_threshold"
    assert result["minimum_distance_mm"] == pytest.approx(5e-7, abs=1e-10)


def test_single_solid_boolean_wrappers_are_valid_but_loose_geometry_is_not(tmp_path):
    kernel = OCPKernel()
    solid = box(kernel)
    hole = kernel.extrude(kernel.circle(1, 5, 5, -1), 12)
    cut = kernel.cut(solid, hole)
    assert kernel.pair_check(cut, box(kernel, (12, 0, 0)))["complete"]
    wrapped = compound(compound(solid))
    assert kernel.pair_check(wrapped, box(kernel, (12, 0, 0)))["complete"]
    loose = compound(solid, kernel.rectangle(2, 2, 30, 0, 0))
    result = kernel.pair_check(loose, solid)
    assert result["relation"] == "unknown" and not result["complete"]
    assert result["common_volume_mm3"] is None
    # The same gate protects existing exports, rather than a divergent validator.
    with pytest.raises(KernelError, match="loose"):
        kernel.export_step(loose, tmp_path / "must-not-exist.step")
    assert not (tmp_path / "must-not-exist.step").exists()


@pytest.mark.parametrize(
    "which", ["null", "not_native", "face", "multiple", "reversed", "open_solid"]
)
def test_invalid_or_non_solid_geometry_is_indeterminate(which):
    kernel = OCPKernel()
    good = box(kernel)
    if which == "null":
        bad = TopoDS_Shape()
    elif which == "not_native":
        bad = object()
    elif which == "face":
        bad = kernel.rectangle(2, 2)
    elif which == "multiple":
        bad = compound(good, box(kernel, (20, 0, 0)))
    elif which == "reversed":
        bad = good.Reversed()
    else:
        builder, shell = BRep_Builder(), TopoDS_Shell()
        builder.MakeShell(shell)
        explorer = TopExp_Explorer(good, TopAbs_FACE)
        explorer.Next()  # Deliberately leave one missing face.
        while explorer.More():
            builder.Add(shell, explorer.Current())
            explorer.Next()
        bad = BRepBuilderAPI_MakeSolid(shell).Solid()
    result = kernel.pair_check(bad, good)
    assert result["relation"] == "unknown"
    assert result["clearance_verdict"] == "indeterminate"
    assert not result["complete"]
    assert not result["known_interference"]
    assert result["common_volume_mm3"] is None
    assert result["minimum_distance_mm"] is None
    assert result["diagnostics"]
    assert_report_finite(result)


def test_excessive_stored_tolerances_are_not_used_to_claim_clearance():
    kernel = OCPKernel()
    a, b = box(kernel), box(kernel, (12, 0, 0))
    vertex = TopExp_Explorer(a, TopAbs_VERTEX).Current()
    BRep_Builder().UpdateVertex(TopoDS.Vertex(vertex), 1e-3)
    result = kernel.pair_check(a, b)
    assert not result["complete"]
    assert result["diagnostics"][0]["code"] == "excessive_shape_tolerance"


@pytest.mark.parametrize("offset", [(0, 0, 0), (999000, -999000, 888000)])
def test_small_solids_far_from_origin_preserve_pair_quantities(offset):
    kernel = OCPKernel()
    a = box(kernel, dimensions=(0.02, 0.03, 0.04))
    b = box(kernel, (0.015, 0, 0), (0.02, 0.03, 0.04))
    a, b = (kernel.transformed(s, frame(offset)) for s in (a, b))
    result = kernel.pair_check(a, b)
    assert result["complete"], result
    assert result["common_volume_mm3"] == pytest.approx(0.005 * 0.03 * 0.04, rel=1e-7)
    assert result["known_interference"]
    assert_report_finite(result)


def test_unresolvable_world_coordinates_fail_closed():
    kernel = OCPKernel()
    a = BRepPrimAPI_MakeBox(gp_Pnt(1e12, 0, 0), 10, 10, 10).Shape()
    result = kernel.pair_check(a, a)
    assert not result["complete"]
    assert result["diagnostics"][0]["code"] == "coordinate_resolution"
    assert result["clearance_verdict"] == "indeterminate"


class Proxy:
    def __init__(self, native, overrides):
        self.native, self.overrides = native, overrides

    def __getattr__(self, name):
        if name in self.overrides:
            return self.overrides[name]
        return getattr(self.native, name)


@pytest.mark.parametrize(
    "overrides", [{"IsDone": lambda: False}, {"Shape": lambda: TopoDS_Shape()}]
)
def test_common_failure_does_not_fabricate_zero_overlap(overrides, monkeypatch):
    kernel = OCPKernel()
    native = kernel_ocp.BRepAlgoAPI_Common
    monkeypatch.setattr(kernel_ocp, "BRepAlgoAPI_Common", lambda: Proxy(native(), overrides))
    result = kernel.pair_check(box(kernel), box(kernel, (12, 0, 0)))
    assert result["common_volume_mm3"] is None
    assert result["minimum_distance_mm"] == pytest.approx(2)
    assert result["relation"] == "unknown"
    assert result["clearance_verdict"] == "indeterminate"
    assert not result["complete"]


def test_native_exception_preserves_independently_proven_clearance_violation(monkeypatch):
    kernel = OCPKernel()

    def fail_common():
        raise RuntimeError("injected Boolean exception")

    monkeypatch.setattr(kernel_ocp, "BRepAlgoAPI_Common", fail_common)
    result = kernel.pair_check(box(kernel), box(kernel, (12, 0, 0)), minimum_required_mm=3)
    assert not result["complete"]
    assert result["known_clearance_violation"]
    assert result["clearance_verdict"] == "fail_clearance"
    assert result["common_volume_mm3"] is None
    assert "injected Boolean exception" in result["diagnostics"][0]["message"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"IsDone": lambda: False},
        {"NbSolution": lambda: 0},
        {"Value": lambda: float("nan")},
        {"Value": lambda: -1},
        {"InnerSolution": lambda: True},
        {"PointOnShape1": lambda _: gp_Pnt(float("nan"), 0, 0)},
        {"PointOnShape1": lambda _: gp_Pnt(123, 456, 789)},
        {
            "PointOnShape1": lambda _: gp_Pnt(123, 456, 789),
            "PointOnShape2": lambda _: gp_Pnt(123, 456, 789),
        },
    ],
)
def test_distance_failures_never_erase_known_overlap(overrides, monkeypatch):
    kernel = OCPKernel()
    native = kernel_ocp.BRepExtrema_DistShapeShape
    monkeypatch.setattr(
        kernel_ocp, "BRepExtrema_DistShapeShape", lambda *args: Proxy(native(*args), overrides)
    )
    result = kernel.pair_check(box(kernel), box(kernel, (5, 0, 0)))
    assert not result["complete"]
    assert result["relation"] == "interference"
    assert result["common_volume_mm3"] == pytest.approx(500)
    assert result["known_interference"]
    assert result["clearance_verdict"] == "fail_interference"
    assert result["minimum_distance_mm"] is None
    assert result["witness_points_mm"] is None
    assert result["diagnostics"]
    assert_report_finite(result)


def test_rigid_transform_failure_is_explicit_and_preserves_source(monkeypatch):
    kernel = OCPKernel()
    shape = box(kernel)
    original = vertices(shape)
    native = kernel_ocp.BRepBuilderAPI_Transform
    monkeypatch.setattr(
        kernel_ocp,
        "BRepBuilderAPI_Transform",
        lambda *args: Proxy(native(*args), {"IsDone": lambda: False}),
    )
    with pytest.raises(KernelError, match="transform failed"):
        kernel.transformed(shape, frame((1, 2, 3)))
    assert vertices(shape) == original


def test_runtime_versions_are_actual_and_json_safe():
    result = OCPKernel.runtime_versions()
    assert result["adapter"] == "assembly-brep-1"
    assert result["ocp"] == kernel_ocp.OCP.__version__
    assert result["cadquery_ocp_novtk"] == "8.0.1.1.0"
    assert result["occt_runtime"] == "not_exposed_by_binding"
    json.dumps(result, allow_nan=False)


def test_pair_measurements_are_invariant_under_shared_arbitrary_rigid_placement():
    kernel = OCPKernel()
    a, b = box(kernel, (17, -9, 4), (2, 3, 5)), box(kernel, (20, -9, 4), (2, 3, 5))
    angle = 1.234
    q = (math.cos(angle / 2), *(math.sin(angle / 2) * v / math.sqrt(14) for v in (1, 2, 3)))
    placed = frame((880000, -570000, 610000), q)
    result = kernel.pair_check(*(kernel.transformed(shape, placed) for shape in (a, b)))
    assert result["complete"], result
    assert result["relation"] == "separated"
    assert result["common_volume_mm3"] == 0
    assert result["minimum_distance_mm"] == pytest.approx(1, abs=1e-8)
    assert_report_finite(result)


def test_pin_inside_tube_void_is_separated_not_contained_material():
    kernel = OCPKernel()
    outer = kernel.extrude(kernel.circle(5), 10)
    bore = kernel.extrude(kernel.circle(2, z=-1), 12)
    tube = kernel.cut(outer, bore)
    pin = kernel.extrude(kernel.circle(1, z=1), 8)
    result = kernel.pair_check(tube, pin)
    assert result["complete"], result
    assert result["common_volume_mm3"] == 0
    assert result["minimum_distance_mm"] == pytest.approx(1, abs=1e-10)
    assert result["relation"] == "separated"
    assert result["clearance_verdict"] == "pass_at_pose"


def test_common_can_have_multiple_valid_solid_pieces():
    kernel = OCPKernel()
    base = box(kernel)
    through_tool = box(kernel, (3, 3, -1), (4, 4, 12))
    ring = kernel.cut(base, through_tool)
    bridge = box(kernel, (0, 4, 0), (10, 2, 10))
    result = kernel.pair_check(ring, bridge)
    assert result["complete"], result
    assert result["common_volume_mm3"] == pytest.approx(120, abs=1e-10)
    assert result["known_interference"]


def test_empty_common_disagrees_with_containment_and_cannot_claim_clear(monkeypatch):
    kernel = OCPKernel()
    native = kernel_ocp.BRepAlgoAPI_Common
    monkeypatch.setattr(
        kernel_ocp, "BRepAlgoAPI_Common", lambda: Proxy(native(), {"Shape": lambda: compound()})
    )
    result = kernel.pair_check(box(kernel), box(kernel, (2, 2, 2), (2, 2, 2)))
    assert result["common_volume_mm3"] == 0
    assert result["minimum_distance_mm"] == pytest.approx(2)
    assert result["relation"] == "indeterminate_kernel_disagreement"
    assert result["clearance_verdict"] == "indeterminate"
    assert not result["complete"]
    assert result["diagnostics"][0]["code"] == "kernel_disagreement"


def test_fake_positive_common_disagrees_with_separation(monkeypatch):
    kernel = OCPKernel()
    native, fake_common = kernel_ocp.BRepAlgoAPI_Common, box(kernel, dimensions=(2, 2, 2))
    monkeypatch.setattr(
        kernel_ocp, "BRepAlgoAPI_Common", lambda: Proxy(native(), {"Shape": lambda: fake_common})
    )
    result = kernel.pair_check(box(kernel), box(kernel, (12, 0, 0)))
    assert result["common_volume_mm3"] == pytest.approx(8)
    assert result["minimum_distance_mm"] == pytest.approx(2)
    assert result["relation"] == "indeterminate_kernel_disagreement"
    assert result["clearance_verdict"] == "indeterminate"
    assert not result["known_interference"]
    assert not result["complete"]


def test_impossible_common_volume_is_indeterminate(monkeypatch):
    kernel = OCPKernel()
    native, fake_common = kernel_ocp.BRepAlgoAPI_Common, box(kernel, dimensions=(100, 100, 100))
    monkeypatch.setattr(
        kernel_ocp, "BRepAlgoAPI_Common", lambda: Proxy(native(), {"Shape": lambda: fake_common})
    )
    result = kernel.pair_check(box(kernel), box(kernel, (12, 0, 0)))
    assert result["common_volume_mm3"] is None
    assert result["clearance_verdict"] == "indeterminate"
    assert not result["complete"]
    assert result["diagnostics"][0]["code"] == "common_invalid"


def test_identity_transform_is_a_deep_geometry_copy():
    kernel = OCPKernel()
    original = box(kernel)
    copied = kernel.transformed(original, frame())
    source_vertex = TopoDS.Vertex(TopExp_Explorer(original, TopAbs_VERTEX).Current())
    copied_vertex = TopoDS.Vertex(TopExp_Explorer(copied, TopAbs_VERTEX).Current())
    source_tolerance = BRep_Tool.Tolerance_s(source_vertex)
    BRep_Builder().UpdateVertex(copied_vertex, 1e-3)
    assert not copied_vertex.IsSame(source_vertex)
    assert BRep_Tool.Tolerance_s(source_vertex) == source_tolerance
    assert BRep_Tool.Tolerance_s(copied_vertex) == pytest.approx(1e-3)


def test_common_volume_exactly_at_policy_threshold_is_indeterminate():
    kernel = OCPKernel()
    a = box(kernel, dimensions=(0.01, 0.01, 0.01))
    b = box(kernel, (0.005, 0, 0), (0.01, 0.01, 0.01))
    measured = kernel.pair_check(a, b)["common_volume_mm3"]
    result = kernel.pair_check(a, b, volume_tolerance_mm3=measured)
    assert result["common_volume_mm3"] == measured
    assert result["relation"] == "indeterminate_small_overlap"
    assert not result["complete"]
    assert result["clearance_verdict"] == "indeterminate"
