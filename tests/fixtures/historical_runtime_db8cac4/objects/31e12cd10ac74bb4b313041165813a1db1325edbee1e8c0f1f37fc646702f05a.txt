"""Real analytic circle B-reps, source identity, exact workplanes and export gates."""

import math
from dataclasses import replace

import pytest

pytest.importorskip("OCP")

from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.GeomAbs import GeomAbs_Circle
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
from OCP.TopoDS import TopoDS

from mechanical_cad import kernel_ocp
from mechanical_cad.kernel_ocp import KernelError, OCPKernel, _shape_bounds, _subshapes
from mechanical_cad.profile_region import classify_profile
from mechanical_cad.sketch_model import Circle, Point, Sketch
from mechanical_cad.topology import resolve_reference


def build(center=(3, 4), radius=7, circle_id="bore", length=5, **plane):
    kernel = OCPKernel()
    profile = kernel.circle_profile(center, radius, circle_id, **plane)
    profile_topology = kernel.topology(profile, "sketch", "sketch_constrained", {})
    assert len(profile_topology) == 1
    assert profile_topology[0]["role"] == "profile"
    assert profile_topology[0]["provenance"]["semantic_status"] == "stable"
    solid = kernel.extrude(profile, length)
    topology = kernel.topology(solid, "pad", "extrude", {})
    return kernel, profile, solid, topology


def rotate(vector, quaternion):
    """Independent quaternion-vector product, without the adapter's basis matrix."""
    norm = math.sqrt(sum(value * value for value in quaternion))
    w, *q = [value / norm for value in quaternion]
    dot = sum(a * b for a, b in zip(q, vector, strict=True))
    cross = (
        q[1] * vector[2] - q[2] * vector[1],
        q[2] * vector[0] - q[0] * vector[2],
        q[0] * vector[1] - q[1] * vector[0],
    )
    return tuple(2 * dot * q[i] + (2 * w * w - 1) * vector[i] + 2 * w * cross[i] for i in range(3))


@pytest.mark.parametrize("length", [5, -5])
def test_circle_is_exact_single_solid_with_analytic_boundary_and_watertight_mesh(length):
    kernel, profile, solid, topology = build(length=length)
    stats = kernel.inspect(solid)
    assert stats["valid"] and stats["solids"] == 1 and stats["faces"] == 3
    assert stats["volume"] == pytest.approx(math.pi * 7**2 * abs(length))
    assert stats["area"] == pytest.approx(2 * math.pi * 7 * (7 + abs(length)))
    edges = _subshapes(profile, TopAbs_EDGE)
    assert len(edges) == 1
    curve = BRepAdaptor_Curve(TopoDS.Edge(edges[0]))
    assert curve.GetType() == GeomAbs_Circle
    assert curve.Circle().Radius() == 7
    assert {item["role"] for item in topology} == {"cap.start", "cap.end", "side.circle.bore"}
    assert all(item["kind"] == "face" for item in topology)
    assert all(item["provenance"]["semantic_status"] == "stable" for item in topology)
    check = kernel.manufacturing_check(solid, 0.03)
    assert check["mesh"]["watertight"]
    assert check["mesh"]["consistently_oriented"]
    assert check["mesh"]["vertex_manifold"]
    assert check["mesh"]["signed_volume"] == pytest.approx(stats["volume"], rel=0.01)
    mesh = kernel.tessellate(solid, 0.03)
    assert set(mesh["triangle_face_ids"]) == {item["id"] for item in topology}


@pytest.mark.parametrize(
    "quaternion",
    [
        (1, 0, 0, 0),
        (math.sqrt(0.5), math.sqrt(0.5), 0, 0),
        (math.sqrt(0.5), 0, 0, math.sqrt(0.5)),
        (0.5, 0.5, 0.5, 0.5),
        (-0.5, -0.5, -0.5, -0.5),
        tuple(value / math.sqrt(0.94) for value in (0.7, 0.2, 0.4, 0.5)),
        tuple(0.5 * math.sqrt(1 + 5e-10) for _ in range(4)),
    ],
)
def test_circle_axis_seam_and_extrusion_follow_explicit_plane_without_rewriting_it(quaternion):
    origin = (10, 20, 30)
    original = tuple(quaternion)
    u, v, normal = (rotate(axis, quaternion) for axis in ((1, 0, 0), (0, 1, 0), (0, 0, 1)))
    center = tuple(origin[i] + 3 * u[i] + 4 * v[i] for i in range(3))
    kernel, profile, solid, topology = build(origin=origin, quaternion=quaternion)
    edge = _subshapes(profile, TopAbs_EDGE)[0]
    curve = BRepAdaptor_Curve(TopoDS.Edge(edge))
    circle = curve.Circle()
    assert circle.Location().Coord() == pytest.approx(center)
    assert circle.Axis().Direction().Coord() == pytest.approx(normal)
    assert circle.Position().XDirection().Coord() == pytest.approx(u)
    assert curve.Value(0).Coord() == pytest.approx(tuple(center[i] + 7 * u[i] for i in range(3)))
    assert curve.Value(math.pi / 2).Coord() == pytest.approx(
        tuple(center[i] + 7 * v[i] for i in range(3))
    )
    roles = {item["role"]: item for item in topology}
    assert roles["cap.start"]["signature"]["centroid"] == pytest.approx(center)
    assert roles["cap.end"]["signature"]["centroid"] == pytest.approx(
        tuple(center[i] + 5 * normal[i] for i in range(3))
    )
    extents = tuple(7 * math.sqrt(max(0, 1 - normal[i] ** 2)) for i in range(3))
    expected_bounds = tuple(center[i] - extents[i] + min(0, 5 * normal[i]) for i in range(3))
    expected_bounds += tuple(center[i] + extents[i] + max(0, 5 * normal[i]) for i in range(3))
    assert _shape_bounds(solid) == pytest.approx(expected_bounds, abs=1e-7)
    assert kernel.inspect(solid)["volume"] == pytest.approx(math.pi * 7**2 * 5)
    assert quaternion == original


def test_source_circle_edits_and_record_reordering_keep_face_roles_but_recreation_does_not():
    sketch = Sketch(
        "sketch",
        (Point("center", 3, 4), Point("unused", 20, 30)),
        (),
        (),
        circles=(Circle("bore", "center", 7),),
        schema_version=2,
    )
    first_region = classify_profile(sketch)
    _, _, _, first = build(first_region.center, first_region.radius, first_region.circle_id)
    edited = replace(
        sketch,
        points=(sketch.points[1], Point("center", 10, 12)),
        circles=(replace(sketch.circles[0], radius=9),),
    )
    region = classify_profile(edited)
    _, _, _, second = build(region.center, region.radius, region.circle_id)
    for candidate in first:
        reference = {key: candidate[key] for key in ("feature_id", "role", "kind")}
        resolution = resolve_reference(reference, second)
        assert resolution.status == "resolved"
        assert resolution.candidate.id == candidate["id"]
    side = next(candidate for candidate in second if candidate["role"].startswith("side."))
    assert side["signature"]["radius"] == 9
    assert side["signature"]["centroid"] == pytest.approx((10, 12, 2.5))
    assert side["provenance"]["source_boundary"] == "circle.bore"
    assert side["provenance"]["relation"] == "generated_from_profile_edge"
    _, _, _, recreated = build(region.center, region.radius, "replacement")
    reference = {"feature_id": "pad", "role": "side.circle.bore", "kind": "face"}
    assert resolve_reference(reference, recreated).status != "resolved"
    assert not any("seam" in item["role"] for item in second)
    seam_reference = {"feature_id": "pad", "role": "seam.circle.bore", "kind": "edge"}
    assert resolve_reference(seam_reference, second).status != "resolved"


def test_actual_wire_edge_and_generated_face_are_the_only_circle_provenance():
    kernel, profile, solid, topology = build()
    profile_operation = kernel._operations[id(profile)]
    solid_operation = kernel._operations[id(solid)]
    edge = profile_operation.boundaries["circle.bore"]
    assert any(edge.IsSame(actual) for actual in _subshapes(profile, TopAbs_EDGE))
    generated = [
        shape
        for shape in solid_operation.builder.Generated(edge)
        if shape.ShapeType() == TopAbs_FACE
    ]
    assert len(generated) == 1
    resolved_face = next(
        face for face, candidate in solid_operation.faces if candidate["role"] == "side.circle.bore"
    )
    assert generated[0].IsSame(resolved_face)
    unknown = OCPKernel().topology(solid, "pad", "circle_profile", {})
    assert all(item["provenance"]["semantic_status"] == "unknown" for item in unknown)
    assert all(item["provenance"]["semantic_status"] == "stable" for item in topology)


def test_legacy_primitive_circle_keeps_its_original_side_role():
    kernel = OCPKernel()
    profile = kernel.circle(7, 3, 4)
    solid = kernel.extrude(profile, 5)
    roles = {item["role"] for item in kernel.topology(solid, "pad", "extrude", {})}
    assert roles == {"cap.start", "cap.end", "side.circle"}


def test_step_roundtrip_is_exact_and_stl_passes_source_and_encoded_fidelity_gates(tmp_path):
    kernel, _, solid, _ = build(origin=(10, 20, 30), quaternion=(0.5, 0.5, 0.5, 0.5))
    step, stl = tmp_path / "circle.step", tmp_path / "circle.stl"
    kernel.export_step(solid, step)
    imported = kernel.import_step(step)
    assert kernel.inspect(imported)["volume"] == pytest.approx(math.pi * 7**2 * 5)
    assert kernel.inspect(imported)["solids"] == 1
    assert _shape_bounds(imported) == pytest.approx(_shape_bounds(solid), abs=1e-7)
    assert all(
        item["provenance"]["semantic_status"] == "unknown"
        for item in kernel.topology(imported, "import", "circle_profile", {})
    )
    checks = kernel.export_stl(solid, stl, linear_deflection=0.03)
    assert checks["mesh"]["watertight"] and checks["encoded_mesh"]["watertight"]
    assert checks["encoded_mesh"]["consistently_oriented"]
    assert (
        checks["encoding"]["maximum_vertex_error_mm"]
        <= checks["encoding"]["allowed_vertex_error_mm"]
    )
    assert stl.stat().st_size == 84 + 50 * checks["encoded_mesh"]["triangles"]


def test_far_origin_separate_center_radius_bounds_keep_exact_geometry_and_stl_precision_gate(
    tmp_path,
):
    kernel, _, solid, topology = build(center=(1e6, -1e6), radius=7, origin=(1e6, 0, 0))
    assert kernel.inspect(solid)["volume"] == pytest.approx(math.pi * 7**2 * 5)
    assert _shape_bounds(solid) == pytest.approx((2e6 - 7, -1e6 - 7, 0, 2e6 + 7, -1e6 + 7, 5))
    assert all(item["provenance"]["semantic_status"] == "stable" for item in topology)
    step = tmp_path / "far.step"
    kernel.export_step(solid, step)
    assert kernel.inspect(kernel.import_step(step))["volume"] == pytest.approx(math.pi * 7**2 * 5)
    stl = tmp_path / "far.stl"
    with pytest.raises(KernelError, match="binary32 coordinate error"):
        kernel.export_stl(solid, stl, linear_deflection=0.03)
    assert not stl.exists()


@pytest.mark.parametrize("extruded", [False, True])
def test_new_circle_uses_shared_analytic_budget_before_any_native_meshing(monkeypatch, extruded):
    kernel = OCPKernel()
    shape = kernel.circle_profile((0, 0), 1e6, "large")
    if extruded:
        shape = kernel.extrude(shape, 1)
    called = []

    def unexpected_mesh(*args, **kwargs):
        called.append(True)
        pytest.fail("Resource preflight must reject before the native mesher is constructed")

    monkeypatch.setattr(kernel_ocp, "BRepMesh_IncrementalMesh", unexpected_mesh)
    with pytest.raises(KernelError, match="analytic-circle resource budget"):
        kernel.tessellate(shape, 0.001)
    assert not called


def test_circle_profile_is_not_a_solid_for_export(tmp_path):
    kernel = OCPKernel()
    profile = kernel.circle_profile((0, 0), 5, "disk")
    assert kernel.tessellate(profile)["triangles"]
    for suffix, export in (("step", kernel.export_step), ("stl", kernel.export_stl)):
        path = tmp_path / f"profile.{suffix}"
        with pytest.raises(KernelError, match="exactly one"):
            export(profile, path)
        assert not path.exists()


@pytest.mark.parametrize(
    "arguments",
    [
        {"radius": 0},
        {"radius": 1e-7},
        {"radius": 1e6 + 1},
        {"radius": True},
        {"center": (float("nan"), 0)},
        {"center": (1e6 + 1, 0)},
        {"circle_id": "invalid/id"},
        {"quaternion": (2, 0, 0, 0)},
        {"quaternion": (True, 0, 0, 0)},
        {"origin": (float("inf"), 0, 0)},
    ],
)
def test_invalid_circle_adapter_inputs_fail_before_constructing_shape(arguments):
    values = {"center": (0, 0), "radius": 1, "circle_id": "circle", **arguments}
    kernel = OCPKernel()
    with pytest.raises(KernelError):
        kernel.circle_profile(**values)
    assert not kernel._operations


@pytest.mark.parametrize(
    "points,area",
    [
        (((0, 0), (5, 0), (7, 3), (2, 5), (0, 2)), 24),
        (((0, 0), (4, 0), (4, 3), (2, 1), (0, 3)), 8),
        (((0, 0), (2, 0), (4, 0), (4, 3), (0, 3)), 12),
    ],
)
def test_nonrectangle_winding_start_and_subdivision_keep_exact_source_sides(points, area):
    identifiers = tuple(f"boundary{i}" for i in range(len(points)))
    by_segment = {
        frozenset((points[i], points[(i + 1) % len(points)])): identifiers[i]
        for i in range(len(points))
    }
    expected_centers = {
        identifiers[i]: tuple(
            (points[i][axis] + points[(i + 1) % len(points)][axis]) / 2 for axis in range(2)
        )
        for i in range(len(points))
    }
    for vertices in (points, (*points[2:], *points[:2]), tuple(reversed(points))):
        edges = tuple(
            by_segment[frozenset((vertices[i], vertices[(i + 1) % len(vertices)]))]
            for i in range(len(vertices))
        )
        kernel = OCPKernel()
        profile = kernel.polygon(vertices, edges)
        solid = kernel.extrude(profile, 5)
        assert kernel.inspect(solid)["volume"] == pytest.approx(area * 5)
        topology = kernel.topology(solid, "pad", "extrude", {})
        roles = {item["role"]: item for item in topology}
        assert set(roles) == {"cap.start", "cap.end", *(f"side.line.{i}" for i in identifiers)}
        for identifier, center in expected_centers.items():
            side = roles[f"side.line.{identifier}"]
            assert side["signature"]["centroid"] == pytest.approx((*center, 2.5))
            assert side["provenance"]["source_boundary"] == f"line.{identifier}"
            assert side["provenance"]["semantic_status"] == "stable"


def test_minimum_accepted_circle_keeps_true_radius_without_tolerance_repair():
    kernel, profile, solid, _ = build(center=(0, 0), radius=1e-6, length=1)
    curve = BRepAdaptor_Curve(TopoDS.Edge(_subshapes(profile, TopAbs_EDGE)[0]))
    assert curve.Circle().Radius() == 1e-6
    assert kernel.inspect(solid)["volume"] == pytest.approx(math.pi * 1e-12, rel=1e-10, abs=0)
