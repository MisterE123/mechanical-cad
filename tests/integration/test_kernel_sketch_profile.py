"""Actual B-rep construction from solved line regions and stable entity IDs."""

import math

import pytest

pytest.importorskip("OCP")

from mechanical_cad.kernel_ocp import KernelError, OCPKernel
from mechanical_cad.topology import resolve_reference

POINTS = [(0, 0), (40, 0), (40, 30), (0, 30)]
IDS = ["bottom", "right", "top", "left"]


def build(points=POINTS, ids=IDS, **plane):
    kernel = OCPKernel()
    profile = kernel.polygon(points, ids, **plane)
    candidates = kernel.topology(profile, "sketch", "sketch_constrained", {})
    assert candidates[0]["role"] == "profile"
    shape = kernel.extrude(profile, 10)
    return kernel, shape, kernel.topology(shape, "pad", "extrude", {})


def test_polygon_extrusion_is_valid_watertight_exact_solid():
    kernel, shape, topology = build()
    assert kernel.inspect(shape)["volume"] == pytest.approx(12000)
    assert kernel.manufacturing_check(shape)["mesh"]["watertight"] is True
    assert {item["role"] for item in topology} == {
        "cap.start",
        "cap.end",
        *[f"side.line.{i}" for i in IDS],
    }
    assert all(item["provenance"]["semantic_status"] == "stable" for item in topology)


def test_dimension_changes_and_boundary_order_keep_semantic_line_provenance():
    _, _, first = build()
    _, _, second = build([(0, 0), (0, 30), (60, 30), (60, 0)], ["left", "top", "right", "bottom"])
    by_role = {item["role"]: item for item in second}
    for candidate in first:
        reference = {key: candidate[key] for key in ("feature_id", "role", "kind")}
        resolution = resolve_reference(reference, second)
        assert resolution.status == "resolved"
        assert resolution.candidate.id == candidate["id"]
    assert by_role["side.line.right"]["signature"]["centroid"][0] == pytest.approx(60)


def test_extrusion_follows_explicit_sketch_plane_normal():
    kernel, shape, topology = build(
        origin=(10, 20, 30), quaternion=(math.sqrt(0.5), math.sqrt(0.5), 0, 0)
    )
    assert kernel.inspect(shape)["volume"] == pytest.approx(12000)
    by_role = {item["role"]: item for item in topology}
    assert by_role["cap.start"]["signature"]["centroid"] == pytest.approx((30, 20, 45))
    assert by_role["cap.end"]["signature"]["centroid"] == pytest.approx((30, 10, 45))
    assert kernel.manufacturing_check(shape)["mesh"]["consistently_oriented"]


def test_self_intersection_and_invalid_plane_do_not_make_solids():
    kernel = OCPKernel()
    with pytest.raises(KernelError):
        kernel.polygon([(0, 0), (40, 30), (0, 30), (40, 0)], IDS)
    with pytest.raises(KernelError, match="unit length"):
        kernel.polygon(POINTS, IDS, quaternion=(2, 0, 0, 0))
