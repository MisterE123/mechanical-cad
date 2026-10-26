"""Native connected modeling, not tessellation-only feature proofs."""

import math

import pytest

from mechanical_cad.engine import regenerate
from mechanical_cad.kernel_ocp import KernelError, OCPKernel
from mechanical_cad.model import Document, Feature


def box(kernel, x=0):
    return kernel.extrude(kernel.rectangle(10, 10, x=x), 10)


def test_union_and_intersection_exact_volumes():
    kernel = OCPKernel()
    a, b = box(kernel), box(kernel, 5)
    assert kernel.inspect(kernel.union(a, b))["volume"] == pytest.approx(1500)
    assert kernel.inspect(kernel.intersection(a, b))["volume"] == pytest.approx(500)
    with pytest.raises(KernelError):
        kernel.union(a, box(kernel, 20))
    with pytest.raises(KernelError):
        kernel.intersection(a, box(kernel, 20))


@pytest.mark.parametrize("angle, fraction", [(360, 1), (180, 0.5), (-90, 0.25)])
def test_revolve_offset_rectangle_produces_annular_solid(angle, fraction):
    kernel = OCPKernel()
    profile = kernel.rectangle(2, 5, x=3)
    solid = kernel.revolve(profile, angle, axis_y=1, axis_z=0)
    stats = kernel.inspect(solid)
    assert stats["valid"] and stats["solids"] == 1
    assert stats["volume"] == pytest.approx(math.pi * (25 - 9) * 5 * fraction)


def test_revolve_rejects_zero_axis():
    kernel = OCPKernel()
    with pytest.raises(KernelError, match="nonzero"):
        kernel.revolve(kernel.rectangle(2, 3), 360, axis_z=0)


@pytest.mark.parametrize("kind, parameter", [("fillet", "radius"), ("chamfer", "distance")])
def test_whole_edge_blends_are_real_valid_smaller_solids(kind, parameter):
    kernel = OCPKernel()
    solid = box(kernel)
    shape = getattr(kernel, kind)(solid, **{parameter: 1})
    stats = kernel.inspect(shape)
    assert stats["valid"] and stats["solids"] == 1
    assert 900 < stats["volume"] < 1000
    topology = kernel.topology(shape, kind, kind, {})
    assert any(face["provenance"]["semantic_status"] != "stable" for face in topology)
    with pytest.raises(KernelError):
        getattr(kernel, kind)(solid, **{parameter: 100})


def test_transform_then_boolean_connects_whole_feature_history():
    features = (
        Feature("p", "sketch_rectangle", "Profile", {"width": 10, "height": 10}),
        Feature("a", "extrude", "Pad", {"length": 10}, {"profile": "p"}),
        Feature("b", "transform", "Moved copy", {"x": "offset", "rz": 90}, {"base": "a"}),
        Feature("u", "union", "Joined", {}, {"base": "a", "tool": "b"}),
        Feature("f", "fillet", "Rounded", {"radius": 0.5}, {"base": "u"}),
    )
    doc = Document("part", "Joined blocks", {"offset": 15}, features, "f")
    restored = Document.from_json(doc.to_json())
    result = regenerate(restored, OCPKernel())
    assert result.ok, result.result
    union = next(f for f in result.result["features"] if f["id"] == "u")
    assert union["stats"]["volume"] == pytest.approx(1500)
    assert result.result["features"][-1]["stats"]["volume"] < 1500


def test_invalid_feature_blocks_downstream_without_reusing_geometry():
    doc = Document(
        "p",
        "Failed blend",
        {},
        (
            Feature("p", "sketch_rectangle", "Profile", {"width": 10, "height": 10}),
            Feature("a", "extrude", "Pad", {"length": 10}, {"profile": "p"}),
            Feature("f", "fillet", "Bad radius", {"radius": 100}, {"base": "a"}),
            Feature("t", "transform", "Dependent", {"x": 5}, {"base": "f"}),
        ),
        "t",
    )
    replay = regenerate(doc, OCPKernel())
    assert not replay.ok
    assert [f["status"] for f in replay.result["features"]] == ["ok", "ok", "failed", "blocked"]
    assert "f" not in replay.shapes and "t" not in replay.shapes


def test_rounded_part_check_step_and_stl_replay_after_save(tmp_path):
    from mechanical_cad.actions import run_geometry_action

    doc = Document(
        "rounded",
        "Rounded block",
        {"corner": 1},
        (
            Feature("p", "sketch_rectangle", "Rectangle", {"width": 10, "height": 10}),
            Feature("e", "extrude", "Block", {"length": 10}, {"profile": "p"}),
            Feature("f", "fillet", "Rounded edges", {"radius": "corner"}, {"base": "e"}),
        ),
        "f",
    )
    saved = tmp_path / "rounded.mcad.json"
    saved.write_text(doc.to_json())
    reopened = Document.from_json(saved.read_text())
    for action, extension in [
        ("check_geometry", None),
        ("export_step", "step"),
        ("export_stl", "stl"),
    ]:
        destination = tmp_path / ("rounded." + extension) if extension else None
        result = run_geometry_action(reopened, action, destination=destination, kernel=OCPKernel())
        assert result["ok"], result
        if destination:
            assert destination.stat().st_size > 100


def test_linear_and_circular_patterns_build_connected_exact_solids():
    kernel = OCPKernel()
    base = box(kernel)
    linear = kernel.linear_pattern(base, 3, dx=5)
    assert kernel.inspect(linear)["volume"] == pytest.approx(2000)
    radial = kernel.circular_pattern(base, 4, 360)
    assert kernel.inspect(radial)["volume"] == pytest.approx(4000)
    with pytest.raises(KernelError, match="connected"):
        kernel.linear_pattern(base, 3, dx=20)
    with pytest.raises(KernelError, match="integer"):
        kernel.linear_pattern(base, 3.5)


def test_shell_keeps_exact_wall_volume_and_checks_closed_manifold():
    kernel = OCPKernel()
    hollow = kernel.shell(box(kernel), 1)
    assert kernel.inspect(hollow)["volume"] == pytest.approx(1000 - 8**3)
    assert kernel.manufacturing_check(hollow)["mesh"]["watertight"]
    opening = kernel.extrude(kernel.circle(2, 5, 5, z=8), 3)
    opened = kernel.cut(hollow, opening)
    assert kernel.inspect(opened)["volume"] == pytest.approx(488 - math.pi * 4)
    assert kernel.manufacturing_check(opened)["mesh"]["watertight"]


def test_patterns_and_shell_persist_and_replay_as_connected_history():
    doc = Document(
        "housing",
        "Patterned hollow housing",
        {},
        (
            Feature("p", "sketch_rectangle", "Profile", {"width": 10, "height": 10}),
            Feature("e", "extrude", "Block", {"length": 10}, {"profile": "p"}),
            Feature(
                "pattern", "linear_pattern", "Three copies", {"count": 3, "dx": 5}, {"base": "e"}
            ),
            Feature("shell", "shell", "Walls", {"thickness": 1}, {"base": "pattern"}),
        ),
        "shell",
    )
    replay = regenerate(Document.from_json(doc.to_json()), OCPKernel())
    assert replay.ok, replay.result
    assert replay.result["features"][-1]["stats"]["volume"] == pytest.approx(2000 - 18 * 8 * 8)


def test_analytic_capsule_with_circular_hole_exact_volume_and_provenance():
    from types import SimpleNamespace as Record

    kernel = OCPKernel()

    def line(start, end, name):
        return Record(start=start, end=end, entity_id=name)

    def arc(center, start, end, sweep, name, kind="arc"):
        return Record(center=center, start=start, end=end, sweep=sweep, entity_id=name, kind=kind)

    capsule = Record(
        boundaries=(
            line((-3, -2), (3, -2), "bottom"),
            arc((3, 0), (3, -2), (3, 2), math.pi, "right"),
            line((3, 2), (-3, 2), "top"),
            arc((-3, 0), (-3, 2), (-3, -2), math.pi, "left"),
        )
    )
    hole = Record(boundaries=(arc((0, 0), (1, 0), (1, 0), 2 * math.pi, "hole", "circle"),))
    profile = kernel.analytic_region_profile((Record(outer=capsule, holes=(hole,)),))
    kernel.topology(profile, "sketch", "sketch_constrained", {})
    solid = kernel.extrude(profile, 5)
    assert kernel.inspect(solid)["volume"] == pytest.approx((24 + 3 * math.pi) * 5)
    faces = kernel.topology(solid, "pad", "extrude", {})
    assert {face["role"] for face in faces} >= {
        "side.arc.right",
        "side.arc.left",
        "side.circle.hole",
    }
    assert kernel.manufacturing_check(solid)["mesh"]["watertight"]


@pytest.mark.parametrize("kind, parameter", [("fillet", "radius"), ("chamfer", "distance")])
def test_selected_edge_uses_persistent_face_pair_and_survives_size_edit(kind, parameter):
    def document(width):
        return Document(
            "d",
            "Selected edge",
            {},
            (
                Feature("p", "sketch_rectangle", "Profile", {"width": width, "height": 10}),
                Feature("e", "extrude", "Block", {"length": 10}, {"profile": "p"}),
                Feature(
                    "blend",
                    kind,
                    "One edge",
                    {parameter: 1},
                    {"base": "e"},
                    edge_faces=("e/face/cap.end", "e/face/side.x_min"),
                ),
            ),
            "blend",
        )

    for width in (10, 20):
        doc = Document.from_json(document(width).to_json())
        replay = regenerate(doc, OCPKernel())
        assert replay.ok, replay.result
        volume = replay.result["features"][-1]["stats"]["volume"]
        assert width * 100 - 10 < volume < width * 100
    bad = document(10).to_dict()
    bad["features"][-1]["edge_faces"][1] = "e/face/cap.start"
    replay = regenerate(Document.from_dict(bad), OCPKernel())
    assert not replay.ok
    assert "exactly one edge" in replay.result["features"][-1]["error"]["message"]


def test_snapshot_edge_selection_rejected_before_native_work():
    from mechanical_cad.errors import CADException

    with pytest.raises(CADException, match="stable"):
        Feature.from_dict(
            {
                "id": "f",
                "kind": "fillet",
                "params": {"radius": 1},
                "inputs": {"base": "e"},
                "edge_faces": ["snapshot:e:face:0", "e/face/cap.end"],
            }
        )


def test_chained_selected_blends_preserve_only_unambiguous_face_lineage():
    doc = Document(
        "d",
        "Two selected edges",
        {},
        (
            Feature("p", "sketch_rectangle", "Profile", {"width": 20, "height": 20}),
            Feature("e", "extrude", "Block", {"length": 20}, {"profile": "p"}),
            Feature(
                "f",
                "fillet",
                "Left top",
                {"radius": 1},
                {"base": "e"},
                edge_faces=("e/face/cap.end", "e/face/side.x_min"),
            ),
            Feature(
                "c",
                "chamfer",
                "Right bottom",
                {"distance": 1},
                {"base": "f"},
                edge_faces=("e/face/cap.start", "e/face/side.x_max"),
            ),
        ),
        "c",
    )
    replay = regenerate(doc, OCPKernel())
    assert replay.ok, replay.result
    final = replay.result["features"][-1]
    assert final["stats"]["volume"] < 8000
    assert any(f["provenance"]["semantic_status"] == "unknown" for f in final["topology"])
    stable = {f["id"] for f in final["topology"] if f["provenance"]["semantic_status"] == "stable"}
    assert "e/face/cap.start" in stable


@pytest.mark.parametrize("ruled", [0, 1])
def test_loft_two_profiles_exact_frustum_volume(ruled):
    kernel = OCPKernel()
    a, b = kernel.circle(2), kernel.circle(4, z=10)
    shape = kernel.loft(a, b, ruled=ruled)
    assert kernel.inspect(shape)["volume"] == pytest.approx(math.pi * 10 * 28 / 3)
    assert kernel.manufacturing_check(shape)["mesh"]["watertight"]


def test_loft_canonical_replay_uses_both_named_profiles():
    doc = Document(
        "d",
        "Loft",
        {},
        (
            Feature("a", "sketch_circle", "Small", {"radius": 2}),
            Feature("b", "sketch_circle", "Large", {"radius": 4, "z": 10}),
            Feature("loft", "loft", "Transition", {"ruled": 0}, {"start": "a", "end": "b"}),
        ),
        "loft",
    )
    replay = regenerate(Document.from_json(doc.to_json()), OCPKernel())
    assert replay.ok, replay.result
    assert replay.result["features"][-1]["stats"]["volume"] == pytest.approx(math.pi * 10 * 28 / 3)


@pytest.mark.parametrize("schema", [2, 3])
def test_sweep_along_saved_open_solved_path_makes_checked_solid(schema):
    from mechanical_cad.sketch_model import Constraint, Line, Plane, Point, SketchDefinition

    path = SketchDefinition(
        "path",
        (Point("a", 0, 0), Point("b", 20, 0)),
        (Line("rail", "a", "b"),),
        (
            Constraint("anchor", "fixed", ("a",), target=(0, 0)),
            Constraint("end", "fixed", ("b",), target=(20, 0)),
        ),
        plane=Plane(quaternion=(math.sqrt(0.5), 0, -math.sqrt(0.5), 0)),
        schema_version=schema,
    )
    doc = Document(
        "d",
        "Swept rod",
        {},
        (
            Feature("profile", "sketch_circle", "Rod profile", {"radius": 2}),
            Feature("path", "sketch_constrained", "Solved path", sketch=path),
            Feature("sweep", "sweep", "Rod", {}, {"profile": "profile", "path": "path"}),
        ),
        "sweep",
        schema_version=2,
    )
    kernel = OCPKernel()
    replay = regenerate(Document.from_json(doc.to_json()), kernel, result_version=schema)
    assert replay.ok, replay.result
    assert replay.result["features"][1]["output"]["profile"]["state"] == "unavailable"
    assert replay.result["features"][-1]["stats"]["volume"] == pytest.approx(math.pi * 4 * 20)
    assert kernel.manufacturing_check(replay.shapes["sweep"])["mesh"]["watertight"]


@pytest.mark.parametrize("width,depth", [(10, 10), (20, 25)])
def test_associative_face_circle_follows_size_and_signed_extrusion_cuts_inward(width, depth):
    doc = Document(
        "d",
        "Face hole",
        {},
        (
            Feature("p", "sketch_rectangle", "Block profile", {"width": width, "height": 10}),
            Feature("block", "extrude", "Block", {"length": depth}, {"profile": "p"}),
            Feature(
                "hole",
                "sketch_face_circle",
                "Face hole",
                {"radius": 2},
                {"support": "block"},
                support_face="block/face/cap.end",
            ),
            Feature("tool", "extrude", "Inward tool", {"length": -3}, {"profile": "hole"}),
            Feature("cut", "cut", "Pocket", {}, {"base": "block", "tool": "tool"}),
        ),
        "cut",
    )
    kernel = OCPKernel()
    replay = regenerate(Document.from_json(doc.to_json()), kernel)
    assert replay.ok, replay.result
    hole = replay.result["features"][2]
    assert hole["topology"][0]["signature"]["centroid"] == pytest.approx([width / 2, 5, depth])
    assert replay.result["features"][-1]["stats"]["volume"] == pytest.approx(
        width * 10 * depth - math.pi * 4 * 3
    )
    assert kernel.manufacturing_check(replay.shapes["cut"])["mesh"]["watertight"]


def test_face_rectangle_uses_local_offsets_and_rejects_nonplanar_support():
    kernel = OCPKernel()
    solid = box(kernel)
    kernel.topology(solid, "block", "extrude", {})
    face = kernel.face_rectangle(solid, "block/face/side.x_min", 2, 3, x=-1, y=-1.5)
    extruded = kernel.extrude(face, 2)
    assert kernel.inspect(extruded)["volume"] == pytest.approx(12)
    cylinder = kernel.extrude(kernel.circle(5), 10)
    kernel.topology(cylinder, "cyl", "extrude", {})
    with pytest.raises(KernelError, match="planar"):
        kernel.face_circle(cylinder, "cyl/face/side.circle", 1)


def test_split_support_face_fails_without_nearest_face_rebinding():
    kernel = OCPKernel()
    solid = box(kernel)
    kernel.topology(solid, "block", "extrude", {})
    slot = kernel.extrude(kernel.rectangle(12, 2, x=-1, y=4, z=5), 6)
    kernel.topology(slot, "slot", "extrude", {})
    cut = kernel.cut(solid, slot)
    kernel.topology(cut, "cut", "cut", {})
    with pytest.raises(KernelError, match="split"):
        kernel.face_circle(cut, "block/face/cap.end", 1)


def test_support_dependency_cycle_rejected_before_geometry():
    from mechanical_cad.errors import CADException

    doc = Document(
        "d",
        "Cycle",
        {},
        (
            Feature(
                "face",
                "sketch_face_circle",
                "Face",
                {"radius": 1},
                {"support": "solid"},
                support_face="solid/face/cap.end",
            ),
            Feature("solid", "extrude", "Solid", {"length": 10}, {"profile": "face"}),
        ),
        "solid",
    )
    with pytest.raises(CADException, match="cycle"):
        doc.validate()


def test_schema3_sweep_does_not_flatten_arcs_or_skip_record_validation():
    from dataclasses import replace

    from mechanical_cad.errors import CADException
    from mechanical_cad.sketch_model import Arc, Constraint, Line, Point, Sketch

    kernel = OCPKernel()
    profile = kernel.circle(1)
    path = Sketch(
        "path",
        (Point("a", 0, 0), Point("b", 20, 0)),
        (Line("rail", "a", "b"),),
        (),
        schema_version=3,
    )
    invalid = replace(path, constraints=(Constraint("bad", "horizontal", ("missing",)),))
    with pytest.raises(CADException):
        kernel.sweep(profile, invalid)
    arc_path = replace(
        path,
        points=path.points + (Point("center", 30, 0), Point("start", 35, 0), Point("end", 30, 5)),
        arcs=(Arc("curve", "center", "start", "end", "ccw"),),
    )
    original = arc_path.to_json()
    with pytest.raises(CADException, match="close"):
        kernel.sweep(profile, arc_path)
    assert arc_path.to_json() == original
    unknown = path.to_dict()
    unknown["unsupported_curve"] = {"type": "spline"}
    with pytest.raises(CADException):
        Sketch.from_dict(unknown)
