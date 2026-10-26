"""Real OCCT geometric/provenance tests; no numerical or mesh-only stand-ins."""

import math

import pytest

pytest.importorskip("OCP")

from mechanical_cad.kernel_ocp import KernelError, OCPKernel, check_watertight_mesh
from mechanical_cad.topology import resolve_reference


def _box(kernel, width=40, height=30, length=5, feature_id="pad"):
    profile = kernel.rectangle(width, height)
    kernel.topology(profile, "sketch", "rectangle", {})
    solid = kernel.extrude(profile, length)
    candidates = kernel.topology(solid, feature_id, "extrude", {})
    return solid, candidates


def _hole(kernel, radius=3, x=12, y=15):
    profile = kernel.circle(radius, x=x, y=y, z=-1)
    kernel.topology(profile, "hole_sketch", "circle", {})
    solid = kernel.extrude(profile, 7)
    kernel.topology(solid, "hole_tool", "extrude", {})
    return solid


def test_rectangle_extrusion_is_valid_solid_with_exact_volume():
    kernel = OCPKernel()
    shape, _ = _box(kernel)
    stats = kernel.inspect(shape)
    assert stats["valid"] is True
    assert stats["solids"] == 1
    assert stats["faces"] == 6
    assert stats["volume"] == pytest.approx(6000)
    assert stats["area"] == pytest.approx(2 * (40 * 30 + 40 * 5 + 30 * 5))


def test_circle_extrusion_and_negative_length_have_expected_volume():
    kernel = OCPKernel()
    for length in (8, -8):
        shape = kernel.extrude(kernel.circle(3, x=4, y=9, z=2), length)
        assert kernel.inspect(shape)["volume"] == pytest.approx(math.pi * 3**2 * 8)
        candidates = kernel.topology(shape, "round_pad", "extrude", {})
        assert {item["role"] for item in candidates} == {"cap.start", "cap.end", "side.circle"}
        assert all(item["provenance"]["semantic_status"] == "stable" for item in candidates)


def test_extrude_semantic_roles_survive_dimension_change():
    snapshots = []
    for width, height, length in ((40, 30, 5), (55, 30, 8)):
        kernel = OCPKernel()
        _, candidates = _box(kernel, width, height, length)
        snapshots.append({item["role"]: item for item in candidates})
    assert set(snapshots[0]) == {
        "cap.start",
        "cap.end",
        "side.x_min",
        "side.x_max",
        "side.y_min",
        "side.y_max",
    }
    for role in snapshots[0]:
        assert snapshots[0][role]["id"] == snapshots[1][role]["id"]
        assert snapshots[1][role]["provenance"]["semantic_status"] == "stable"
    assert snapshots[0]["cap.end"]["signature"]["centroid"][2] == pytest.approx(5)
    assert snapshots[1]["cap.end"]["signature"]["centroid"][2] == pytest.approx(8)


def test_through_hole_cut_valid_volume_and_one_to_one_cap_provenance():
    for radius, x in ((3, 12), (4, 20)):
        kernel = OCPKernel()
        base, _ = _box(kernel)
        result = kernel.cut(base, _hole(kernel, radius, x))
        stats = kernel.inspect(result)
        assert stats["solids"] == 1
        assert stats["volume"] == pytest.approx(6000 - math.pi * radius**2 * 5)
        candidates = kernel.topology(result, "cut", "cut", {})
        caps = [item for item in candidates if item["role"].startswith("cap.")]
        assert len(caps) == 2
        assert all(item["feature_id"] == "pad" for item in caps)
        assert all(item["provenance"]["semantic_status"] == "stable" for item in caps)
        assert all(item["provenance"]["evolution"] == "modified" for item in caps)
        walls = [item for item in candidates if item["role"] == "cut.wall"]
        assert len(walls) == 1
        assert walls[0]["provenance"]["semantic_status"] == "generated"
        assert walls[0]["signature"]["surface"] == "cylinder"


def test_crossing_slot_marks_split_caps_instead_of_renumbering():
    kernel = OCPKernel()
    base, _ = _box(kernel)
    tool = kernel.extrude(kernel.rectangle(2, 32, x=19, y=-1, z=-1), 7)
    kernel.topology(tool, "slot_tool", "extrude", {})
    result = kernel.cut(base, tool)
    assert kernel.inspect(result)["solids"] == 2
    candidates = kernel.topology(result, "slot_cut", "cut", {})
    top = [item for item in candidates if item["role"] == "cap.end"]
    assert len(top) == 2
    assert all(item["provenance"]["semantic_status"] == "split" for item in top)
    assert len({item["id"] for item in top}) == 2


def test_trimming_cut_does_not_retarget_deleted_side():
    kernel = OCPKernel()
    base, _ = _box(kernel)
    tool = kernel.extrude(kernel.rectangle(10, 32, x=-1, y=-1, z=-1), 7)
    kernel.topology(tool, "trim_tool", "extrude", {})
    result = kernel.cut(base, tool)
    candidates = kernel.topology(result, "trim_cut", "cut", {})
    assert not [
        item for item in candidates if item["feature_id"] == "pad" and item["role"] == "side.x_min"
    ]
    assert any(item["provenance"]["semantic_status"] == "generated" for item in candidates)


def test_tessellation_has_finite_vertices_valid_triangles_and_face_mapping():
    kernel = OCPKernel()
    shape, candidates = _box(kernel)
    mesh = kernel.tessellate(shape, 0.05)
    assert len(mesh["vertices"]) >= 8
    assert len(mesh["triangles"]) >= 12
    assert all(math.isfinite(value) for vertex in mesh["vertices"] for value in vertex)
    assert all(len(set(triangle)) == 3 for triangle in mesh["triangles"])
    assert all(
        0 <= index < len(mesh["vertices"]) for triangle in mesh["triangles"] for index in triangle
    )
    assert len(mesh["triangle_face_ids"]) == len(mesh["triangles"])
    assert set(mesh["triangle_face_ids"]) == {item["id"] for item in candidates}
    # Winding must give positive signed volume for an outward-oriented solid.
    signed_volume = 0
    for ia, ib, ic in mesh["triangles"]:
        a, b, c = [mesh["vertices"][index] for index in (ia, ib, ic)]
        cross = (b[1] * c[2] - b[2] * c[1], b[2] * c[0] - b[0] * c[2], b[0] * c[1] - b[1] * c[0])
        signed_volume += sum(a[index] * cross[index] for index in range(3)) / 6
    assert signed_volume == pytest.approx(6000)


def test_step_roundtrip_preserves_geometry_but_does_not_invent_history(tmp_path):
    kernel = OCPKernel()
    base, _ = _box(kernel)
    original = kernel.cut(base, _hole(kernel))
    path = tmp_path / "bracket.step"
    kernel.export_step(original, path)
    assert path.stat().st_size > 1000
    imported = kernel.import_step(path)
    assert kernel.inspect(imported)["volume"] == pytest.approx(kernel.inspect(original)["volume"])
    assert kernel.inspect(imported)["solids"] == 1
    candidates = kernel.topology(imported, "import", "import_step", {})
    assert all(item["provenance"]["semantic_status"] == "unknown" for item in candidates)


@pytest.mark.parametrize("value", [0, -1, math.nan, math.inf])
def test_invalid_profile_dimensions_are_rejected(value):
    kernel = OCPKernel()
    with pytest.raises(KernelError):
        kernel.rectangle(value, 3)
    with pytest.raises(KernelError):
        kernel.circle(value)


def test_empty_cut_and_zero_extrusion_are_rejected():
    kernel = OCPKernel()
    profile = kernel.rectangle(2, 2)
    with pytest.raises(KernelError, match="nonzero"):
        kernel.extrude(profile, 0)
    small = kernel.extrude(profile, 2)
    enclosing = kernel.extrude(kernel.rectangle(4, 4, x=-1, y=-1, z=-1), 4)
    with pytest.raises(KernelError, match="no solid"):
        kernel.cut(small, enclosing)


def test_planar_profile_mesh_is_displayable_but_cannot_export_as_part(tmp_path):
    kernel = OCPKernel()
    profile = kernel.circle(3)
    assert kernel.tessellate(profile)["triangles"]
    with pytest.raises(KernelError, match="exactly one"):
        kernel.export_step(profile, tmp_path / "profile.step")
    with pytest.raises(KernelError, match="exactly one"):
        kernel.export_stl(profile, tmp_path / "profile.stl")


def test_real_hole_mesh_and_encoded_stl_pass_watertight_gates(tmp_path):
    kernel = OCPKernel()
    base, _ = _box(kernel)
    shape = kernel.cut(base, _hole(kernel))
    path = tmp_path / "bracket.stl"
    checks = kernel.export_stl(shape, path, linear_deflection=0.03)
    assert checks["brep"]["solids"] == 1
    for stage in ("mesh", "encoded_mesh"):
        assert checks[stage]["watertight"] is True
        assert checks[stage]["vertex_manifold"] is True
        assert checks[stage]["signed_volume"] == pytest.approx(checks["brep"]["volume"], rel=0.01)
    assert path.stat().st_size == 84 + 50 * checks["encoded_mesh"]["triangles"]


def test_disconnected_solids_refuse_part_step_and_stl_export(tmp_path):
    kernel = OCPKernel()
    base, _ = _box(kernel)
    slot = kernel.extrude(kernel.rectangle(2, 32, x=19, y=-1, z=-1), 7)
    shape = kernel.cut(base, slot)
    assert kernel.inspect(shape)["solids"] == 2
    with pytest.raises(KernelError, match="exactly one"):
        kernel.export_step(shape, tmp_path / "invalid.step")
    with pytest.raises(KernelError, match="exactly one"):
        kernel.export_stl(shape, tmp_path / "invalid.stl")
    assert not (tmp_path / "invalid.stl").exists()


def test_watertight_gate_rejects_missing_reversed_and_collapsed_triangles():
    kernel = OCPKernel()
    shape, _ = _box(kernel)
    mesh = kernel.tessellate(shape)
    assert check_watertight_mesh(mesh)["watertight"]
    with pytest.raises(KernelError, match="watertight"):
        check_watertight_mesh({**mesh, "triangles": mesh["triangles"][1:]})
    with pytest.raises(KernelError, match="oriented"):
        check_watertight_mesh(
            {**mesh, "triangles": [mesh["triangles"][0][::-1], *mesh["triangles"][1:]]}
        )
    with pytest.raises(KernelError, match="collapsed"):
        check_watertight_mesh({**mesh, "triangles": [[0, 0, 1], *mesh["triangles"][1:]]})


def test_identical_replay_has_deterministic_snapshot_ids_and_mesh():
    outputs = []
    for _ in range(2):
        kernel = OCPKernel()
        base, _ = _box(kernel)
        result = kernel.cut(base, _hole(kernel))
        topology = kernel.topology(result, "cut", "cut", {})
        outputs.append((topology, kernel.tessellate(result)))
        assert all(
            item["provenance"].get("id_scope") == "evaluation_snapshot_only"
            for item in topology
            if item["provenance"]["semantic_status"] != "stable"
        )
    assert outputs[0] == outputs[1]


def test_shallow_slot_is_one_solid_but_cap_reference_fails_closed():
    kernel = OCPKernel()
    base, _ = _box(kernel)
    tool = kernel.extrude(kernel.rectangle(2, 32, x=19, y=-1, z=2), 4)
    kernel.topology(tool, "shallow_slot_tool", "extrude", {})
    shape = kernel.cut(base, tool)
    stats = kernel.inspect(shape)
    assert stats["solids"] == 1
    assert stats["volume"] == pytest.approx(5820)
    candidates = kernel.topology(shape, "shallow_slot", "cut", {})
    result = resolve_reference({"feature_id": "pad", "role": "cap.end"}, candidates)
    assert result.status == "ambiguous"
    assert not result.resolved
    assert len(result.candidates) == 2
    assert kernel.manufacturing_check(shape)["mesh"]["watertight"]


def test_real_bore_cap_reference_resolves_and_deleted_side_does_not():
    kernel = OCPKernel()
    base, _ = _box(kernel)
    bore = kernel.cut(base, _hole(kernel))
    candidates = kernel.topology(bore, "bore", "cut", {})
    assert resolve_reference({"feature_id": "pad", "role": "cap.end"}, candidates).resolved
    tool = kernel.extrude(kernel.rectangle(10, 32, x=-1, y=-1, z=-1), 7)
    kernel.topology(tool, "trim_tool", "extrude", {})
    trim = kernel.cut(bore, tool)
    candidates = kernel.topology(trim, "trim", "cut", {})
    result = resolve_reference({"feature_id": "pad", "role": "side.x_min"}, candidates)
    assert not result.resolved
    assert result.status == "missing"


def test_nonintersecting_cut_is_explicitly_rejected():
    kernel = OCPKernel()
    base, _ = _box(kernel)
    distant = kernel.extrude(kernel.circle(2, x=100, y=100), 5)
    with pytest.raises(KernelError, match="does not remove measurable material"):
        kernel.cut(base, distant)


@pytest.mark.parametrize("origin", [1e5, 1e6])
def test_stl_rejects_float32_precision_loss_without_replacing_destination(tmp_path, origin):
    kernel = OCPKernel()
    shape = kernel.extrude(kernel.rectangle(0.1, 0.1, x=origin, y=origin, z=origin), 0.1)
    mesh_check = kernel.manufacturing_check(shape, 0.001)
    assert mesh_check["mesh"]["signed_volume"] == pytest.approx(0.001, rel=1e-7)
    destination = tmp_path / "existing.stl"
    destination.write_bytes(b"preserve previous export")
    with pytest.raises(KernelError, match="coordinate error.*exceeds allowed"):
        kernel.export_stl(shape, destination, 0.001)
    assert destination.read_bytes() == b"preserve previous export"


def test_large_circle_tessellation_rejects_resource_budget_before_meshing():
    kernel = OCPKernel()
    profile = kernel.circle(1e6)
    with pytest.raises(KernelError, match="resource budget"):
        kernel.tessellate(profile, 0.001)
