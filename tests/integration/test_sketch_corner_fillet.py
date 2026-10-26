"""Atomic corner intent and strict replay, without importing Blender or native code."""

import copy
import importlib
import json
import math
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "corner_fillet_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
sys.modules[PACKAGE] = package
c = importlib.import_module(PACKAGE + ".general_sketch_commands")
d = importlib.import_module(PACKAGE + ".general_sketch_draft")
f = importlib.import_module(PACKAGE + ".sketch_corner_fillet")


def setup(angle=90, reverse=False):
    draft = d.GeneralSketchDraft(
        json.dumps(
            {
                "schema_version": 1,
                "id": "doc",
                "name": "Part",
                "units": "mm",
                "parameters": {},
                "features": [],
                "active_feature": None,
            }
        ),
        journal_version=3,
    )
    corner, outer, first = draft.execute(
        c.AddLine(c.PointSeed(0, 0), c.PointSeed(20, 0))
    ).entity_ids
    point = c.PointSeed(20 * math.cos(math.radians(angle)), 20 * math.sin(math.radians(angle)))
    _, second = draft.execute(
        c.AddLine(point, c.PointRef(corner)) if reverse else c.AddLine(c.PointRef(corner), point)
    ).entity_ids
    return draft, (first, second), corner, outer


def positions(draft):
    return {p["id"]: (p["u"], p["v"]) for p in draft.sketch["points"]}


@pytest.mark.parametrize("angle", [30, 60, 90, 120, 160, -30, -90, -160])
@pytest.mark.parametrize("reverse", [False, True])
def test_geometry_identity_history(angle, reverse):
    draft, lines, corner, outer = setup(angle, reverse)
    before = draft.sketch
    pts = positions(draft)
    plan = f.prepare_corner(before, lines, 2, pts)
    assert draft.sketch == before
    for point, endpoint in zip((plan.start, plan.end), plan.outer, strict=True):
        radial = [point[k] - plan.center[k] for k in (0, 1)]
        tangent = [pts[endpoint][k] - point[k] for k in (0, 1)]
        assert math.dist(point, plan.center) == pytest.approx(2)
        assert sum(a * b for a, b in zip(radial, tangent, strict=True)) == pytest.approx(
            0, abs=1e-10
        )
    assert plan.direction == ("cw" if angle > 0 else "ccw")
    draft.execute(c.CornerFillet(lines, 2, pts))
    after = draft.sketch
    assert after["points"][: len(before["points"])] == before["points"]
    assert [line["id"] for line in after["lines"]] == list(lines)
    assert [r["kind"] for r in after["constraints"]] == [
        "radius",
        "tangent",
        "tangent",
        "point_on_line",
        "point_on_line",
    ]
    restored = d.GeneralSketchDraft.from_checkpoint_payload(
        draft.checkpoint_payload(), expected_journal_version=3
    )
    assert restored.sketch == after
    restored.undo()
    assert restored.sketch == before
    restored.redo()
    assert restored.sketch == after


def test_rectangle_retains_dimensions_and_hv():
    draft, _, _, _ = setup()
    draft.execute(c.AddRectangle(c.PointSeed(40, 0), c.PointSeed(60, 10)))
    # Select consecutive rectangle edges from the actual records, not allocator conventions.
    lines = tuple(line["id"] for line in draft.sketch["lines"][-4:-2])
    before = draft.sketch
    corner = next(
        iter(
            set((before["lines"][-4]["start"], before["lines"][-4]["end"]))
            & set((before["lines"][-3]["start"], before["lines"][-3]["end"]))
        )
    )
    draft.execute(c.AddRelation("fixed", (corner,), target=positions(draft)[corner]))
    prior = draft.sketch
    draft.execute(c.CornerFillet(lines, 2, positions(draft)))
    assert draft.sketch["constraints"][: len(prior["constraints"])] == prior["constraints"]


@pytest.mark.parametrize("radius", [0, -1, 20, 30, float("nan"), float("inf"), True])
def test_invalid_radius_is_atomic(radius):
    draft, lines, _, _ = setup()
    before = draft.checkpoint_payload()
    with pytest.raises(c.DraftError):
        draft.execute(c.CornerFillet(lines, radius, positions(draft)))
    assert draft.checkpoint_payload() == before


@pytest.mark.parametrize("kind", ["perpendicular", "equal", "parallel", "angle"])
def test_selected_line_relations_are_not_silently_removed(kind):
    draft, lines, _, _ = setup()
    draft.execute(c.AddRelation(kind, lines, value=90 if kind == "angle" else None))
    before = draft.checkpoint_payload()
    with pytest.raises(c.DraftError, match="relations"):
        draft.execute(c.CornerFillet(lines, 2, positions(draft)))
    assert draft.checkpoint_payload() == before


def test_shared_and_coincident_corner_refused():
    draft, lines, corner, _ = setup()
    draft.execute(c.AddLine(c.PointRef(corner), c.PointSeed(-10, 0)))
    with pytest.raises(c.DraftError, match="third"):
        draft.execute(c.CornerFillet(lines, 2, positions(draft)))
    draft.undo()
    other = draft.execute(c.AddPoint(c.PointSeed(0, 0))).entity_ids[0]
    draft.execute(c.AddRelation("coincident", (corner, other)))
    with pytest.raises(c.DraftError, match="coincidence"):
        draft.execute(c.CornerFillet(lines, 2, positions(draft)))


@pytest.mark.parametrize(
    "field", ["radius", "positions", "points", "arc", "constraints", "source_schema_version"]
)
def test_tampered_journal_rejected(field):
    draft, lines, _, _ = setup()
    draft.execute(c.CornerFillet(lines, 2, positions(draft)))
    payload = copy.deepcopy(draft.checkpoint_payload())
    record = payload["journal"]["entries"][-1]["command"]
    record[field] = None
    with pytest.raises((c.DraftError, ValueError)):
        d.GeneralSketchDraft.from_checkpoint_payload(payload, expected_journal_version=3)


@pytest.mark.parametrize("angle", [0, 180, 0.00000058, 179.99999942])
def test_near_collinear_never_divides_by_zero(angle):
    draft, lines, _, _ = setup(angle)
    with pytest.raises(c.DraftError):
        f.prepare_corner(draft.sketch, lines, 2, positions(draft))


@pytest.mark.parametrize("angle", [30, 90, 150, -30, -90, -150])
def test_native_exact_tangent_geometry(angle):
    pytest.importorskip("slvs")
    from mechanical_cad.arc_geometry import arc_geometry
    from mechanical_cad.sketch_model import Sketch
    from mechanical_cad.sketch_solver import solve

    draft, lines, _, _ = setup(angle)
    for identifier, position in positions(draft).items():
        draft.execute(c.AddRelation("fixed", (identifier,), target=position))
    original = positions(draft)
    draft.execute(c.CornerFillet(lines, 2, original))
    report = solve(Sketch.from_dict(draft.sketch))
    assert report.success, report
    assert report.remaining_dof == 0
    solved = {p.id: (p.u, p.v) for p in report.sketch.points}
    for identifier, point in original.items():
        assert solved[identifier] == pytest.approx(point, abs=1e-8)
    arc = report.sketch.arcs[0]
    geometry = arc_geometry(
        solved[arc.center],
        solved[arc.start],
        solved[arc.end],
        arc.direction,
        require_equal_radii=True,
    )
    assert geometry.start_radius == pytest.approx(2, abs=1e-9)
    assert abs(geometry.sweep_radians) == pytest.approx(
        math.pi - abs(math.radians(angle)), abs=1e-8
    )


def test_native_rounded_rectangle_dimension_edit_and_consumed_replay():
    pytest.importorskip("OCP")
    pytest.importorskip("slvs")
    from mechanical_cad.engine import regenerate
    from mechanical_cad.kernel_ocp import OCPKernel
    from mechanical_cad.model import Document

    draft = d.GeneralSketchDraft(
        json.dumps(
            {
                "schema_version": 1,
                "id": "doc",
                "name": "Part",
                "units": "mm",
                "parameters": {},
                "features": [],
                "active_feature": None,
            }
        ),
        journal_version=3,
    )
    draft.execute(c.AddRectangle(c.PointSeed(0, 0), c.PointSeed(20, 10)))
    pts = [p["id"] for p in draft.sketch["points"]]
    draft.execute(c.AddRelation("fixed", (pts[0],), target=(0, 0)))
    draft.execute(c.AddRelation("distance", (pts[0], pts[1]), value=20))
    draft.execute(c.AddRelation("distance", (pts[1], pts[2]), value=10))
    lines = tuple(line["id"] for line in draft.sketch["lines"][:2])
    draft.execute(c.CornerFillet(lines, 2, positions(draft)))
    doc = draft.candidate()
    doc["features"].append(
        {
            "id": "pad",
            "kind": "extrude",
            "label": "Plate",
            "params": {"length": 5},
            "inputs": {"profile": draft.feature_id},
        }
    )
    doc["active_feature"] = "pad"
    for radius in (2, 3):
        sketch = doc["features"][0]["sketch"]
        next(r for r in sketch["constraints"] if r["kind"] == "radius")["value"] = radius
        replay = regenerate(Document.from_dict(doc), OCPKernel(), result_version=3)
        assert replay.ok, replay.result
        assert replay.result["features"][-1]["stats"]["volume"] == pytest.approx(
            (200 - radius**2 * (1 - math.pi / 4)) * 5, abs=1e-6
        )
        assert replay.result["features"][-1]["stats"]["valid"]
    for radius in (10, 12, 25, 100):
        next(r for r in doc["features"][0]["sketch"]["constraints"] if r["kind"] == "radius")[
            "value"
        ] = radius
        snapshot = copy.deepcopy(doc)
        replay = regenerate(Document.from_dict(doc), OCPKernel(), result_version=3)
        assert not replay.ok, (radius, replay.result)
        assert replay.result["features"][-1]["status"] == "blocked"
        assert "pad" not in replay.shapes
        assert doc == snapshot
        if radius == 100:
            assert replay.result["features"][0]["error"]["code"] == "fillet_out_of_bounds"


@pytest.mark.parametrize(
    "mutation",
    [
        "version",
        "unknown",
        "turn",
        "outer",
        "missing_relation",
        "reverse",
        "construction",
        "endpoint",
    ],
)
def test_persistent_intent_rejects_structural_corruption(mutation):
    from mechanical_cad.sketch_model import SketchDefinition

    draft, lines, _, _ = setup()
    draft.execute(c.CornerFillet(lines, 2, positions(draft)))
    sketch = draft.sketch
    arc = sketch["arcs"][0]
    if mutation == "version":
        arc["fillet_intent"]["version"] = True
    elif mutation == "unknown":
        arc["fillet_intent"]["guess"] = True
    elif mutation == "turn":
        arc["fillet_intent"]["turn"] = arc["direction"]
    elif mutation == "outer":
        arc["fillet_intent"]["outer"].reverse()
    elif mutation == "missing_relation":
        sketch["constraints"].pop()
    elif mutation == "reverse":
        arc["direction"] = "ccw" if arc["direction"] == "cw" else "cw"
    elif mutation == "construction":
        sketch["lines"][0]["construction"] = True
    elif mutation == "endpoint":
        sketch["lines"][0]["end"] = arc["center"]
    with pytest.raises(ValueError):
        c._validate_sketch(sketch, journal_version=3)
    with pytest.raises(Exception) as failure:
        SketchDefinition.from_dict(sketch)
    assert "Fillet" in str(failure.value) or "fillet" in str(failure.value)


def test_required_relation_release_and_reverse_are_atomic():
    draft, lines, _, _ = setup()
    result = draft.execute(c.CornerFillet(lines, 2, positions(draft)))
    before = draft.checkpoint_payload()
    with pytest.raises(c.DraftError, match="branch"):
        draft.execute(c.ReverseArcSweep(result.entity_ids[-1]))
    assert draft.checkpoint_payload() == before
    arc = draft.sketch["arcs"][0]
    assert arc["fillet_intent"]["version"] == 1
    assert all(p in positions(draft) for p in arc["fillet_intent"]["outer"])


def test_fillet_policy_mirror_matches_core():
    assert (ROOT / "src/mechanical_cad/fillet_intent.py").read_bytes() == (
        ROOT / "blender_addon/mechanical_cad_blender/fillet_intent.py"
    ).read_bytes()


@pytest.mark.parametrize("target", ["radius", "tangent", "point_on_line", "line", "corner"])
def test_protected_fillet_dependencies_cannot_be_deleted(target):
    draft, lines, corner, _ = setup()
    draft.execute(c.CornerFillet(lines, 2, positions(draft)))
    before = draft.checkpoint_payload()
    if target in {"radius", "tangent", "point_on_line"}:
        selection = (
            "constraint",
            next(r["id"] for r in draft.sketch["constraints"] if r["kind"] == target),
        )
    else:
        selection = ("line", lines[0]) if target == "line" else ("point", corner)
    with pytest.raises(c.DraftError):
        draft.execute(c.DeleteBatch(draft.preview_delete((selection,))))
    assert draft.checkpoint_payload() == before


def test_explicit_arc_deletion_removes_its_intent_with_the_arc():
    draft, lines, _, _ = setup()
    result = draft.execute(c.CornerFillet(lines, 2, positions(draft)))
    sketch = draft.sketch
    targets, removed = c._delete_sets(sketch, (("arc", result.entity_ids[-1]),), journal_version=3)
    reduced = c._apply_record(
        sketch,
        {
            "op": "delete_v3",
            "targets": [list(t) for t in targets],
            "removed": removed,
            "seeds": {"points": sketch["points"], "circles": []},
        },
        journal_version=3,
    )
    assert reduced["arcs"] == []


def test_adjacent_second_fillet_preserves_original_outer_identity():
    draft = d.GeneralSketchDraft(
        json.dumps(
            {
                "schema_version": 1,
                "id": "doc",
                "name": "Part",
                "units": "mm",
                "parameters": {},
                "features": [],
                "active_feature": None,
            }
        ),
        journal_version=3,
    )
    draft.execute(c.AddRectangle(c.PointSeed(0, 0), c.PointSeed(20, 10)))
    lines = [line["id"] for line in draft.sketch["lines"]]
    draft.execute(c.CornerFillet(tuple(lines[:2]), 2, positions(draft)))
    before = draft.sketch
    draft.execute(c.CornerFillet(tuple(lines[1:3]), 2, positions(draft)))
    after = draft.sketch
    first, second = after["arcs"]
    assert first["fillet_intent"]["outer"] == before["arcs"][0]["fillet_intent"]["outer"]
    assert first["fillet_intent"]["version"] == second["fillet_intent"]["version"] == 2
    restored = d.GeneralSketchDraft.from_checkpoint_payload(draft.checkpoint_payload(), expected_journal_version=3)
    assert restored.sketch == after
    restored.undo()
    assert restored.sketch == before
    restored.redo()
    assert restored.sketch == after


@pytest.mark.parametrize("reverse", [False, True])
def test_four_corner_cycle_explicit_and_strict(reverse):
    from mechanical_cad.fillet_intent import validate_solved
    from mechanical_cad.sketch_model import Sketch

    draft, _, _, _ = setup()
    draft.execute(c.AddRectangle(c.PointSeed(40, 0), c.PointSeed(60, 10)))
    lines = [line["id"] for line in draft.sketch["lines"][-4:]]
    original = draft.sketch
    for index, radius in enumerate((1, 2, 3, 2)):
        pair = (lines[index], lines[(index + 1) % 4])
        draft.execute(c.CornerFillet(pair[::-1] if reverse else pair, radius, positions(draft)))
    after = draft.sketch
    assert after["points"][:len(original["points"])] == original["points"]
    assert after["constraints"][:len(original["constraints"])] == original["constraints"]
    assert all(all(a["fillet_intent"]["neighbors"]) for a in after["arcs"])
    canonical = Sketch.from_dict(after).to_dict()
    assert Sketch.from_dict(canonical).to_dict() == canonical
    validate_solved(after)
    restored = d.GeneralSketchDraft.from_checkpoint_payload(draft.checkpoint_payload(), expected_journal_version=3)
    assert restored.sketch == after
    for _ in range(4):
        restored.undo()
    assert restored.sketch == original
    for _ in range(4):
        restored.redo()
    assert restored.sketch == after
    damaged = copy.deepcopy(after)
    damaged["arcs"][0]["fillet_intent"]["neighbors"][0] = None
    with pytest.raises(ValueError):
        Sketch.from_dict(damaged)


def adjacent_rectangle(radii=(2, 2, 2, 2), reverse=False):
    draft = d.GeneralSketchDraft(json.dumps({"schema_version": 1, "id": "doc", "name": "Part",
        "units": "mm", "parameters": {}, "features": [], "active_feature": None}), journal_version=3)
    draft.execute(c.AddRectangle(c.PointSeed(0, 0), c.PointSeed(20, 10)))
    pts = [p["id"] for p in draft.sketch["points"]]
    draft.execute(c.AddRelation("fixed", (pts[0],), target=(0, 0)))
    draft.execute(c.AddRelation("distance", (pts[0], pts[1]), value=20))
    draft.execute(c.AddRelation("distance", (pts[1], pts[2]), value=10))
    lines = [line["id"] for line in draft.sketch["lines"]]
    for index, radius in enumerate(radii):
        pair = (lines[index], lines[(index + 1) % 4])
        draft.execute(c.CornerFillet(pair[::-1] if reverse else pair, radius, positions(draft)))
    return draft


@pytest.mark.parametrize("boundary", ["mechanical_cad.fillet_intent", PACKAGE + ".fillet_intent"])
def test_shared_span_overlap_rejected_even_with_individual_interior_points(boundary):
    validate = importlib.import_module(boundary).validate_solved
    sketch = adjacent_rectangle().sketch
    by_id = {p["id"]: p for p in sketch["points"]}
    for arc in sketch["arcs"]:
        corner = by_id[arc["fillet_intent"]["corner"]]
        for key in ("center", "start", "end"):
            point = by_id[arc[key]]
            for axis in ("u", "v"):
                point[axis] = corner[axis] + 3 * (point[axis] - corner[axis])
    with pytest.raises(ValueError, match="overlap"):
        validate(sketch)


def test_adjacent_peer_update_tamper_and_delete_are_atomic():
    draft = adjacent_rectangle((2, 3))
    before = draft.checkpoint_payload()
    corrupted = copy.deepcopy(before)
    corrupted["journal"]["entries"][-1]["command"]["peer_updates"][0]["after"]["neighbors"] = [None, None]
    with pytest.raises(ValueError):
        d.GeneralSketchDraft.from_checkpoint_payload(corrupted, expected_journal_version=3)
    arc_id = draft.sketch["arcs"][0]["id"]
    with pytest.raises(ValueError):
        draft.execute(c.DeleteBatch(draft.preview_delete((("arc", arc_id),))))
    assert draft.checkpoint_payload() == before


@pytest.mark.parametrize("version", [True, 1.0, 2.0])
def test_adjacent_journal_before_version_is_strict(version):
    draft = adjacent_rectangle((2, 3))
    corrupted = copy.deepcopy(draft.checkpoint_payload())
    corrupted["journal"]["entries"][-1]["command"]["peer_updates"][0]["before"]["version"] = version
    with pytest.raises(ValueError):
        d.GeneralSketchDraft.from_checkpoint_payload(corrupted, expected_journal_version=3)


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("radii", [(1, 3), (1, 2, 3, 2)])
def test_native_adjacent_rectangle_dimensions_volume_and_bounds(reverse, radii):
    pytest.importorskip("slvs")
    pytest.importorskip("OCP")
    from mechanical_cad.engine import regenerate
    from mechanical_cad.kernel_ocp import OCPKernel
    from mechanical_cad.model import Document

    draft = adjacent_rectangle(radii, reverse)
    doc = draft.candidate()
    doc["features"].append({"id": "pad", "kind": "extrude", "label": "Plate",
                            "params": {"length": 5}, "inputs": {"profile": draft.feature_id}})
    doc["active_feature"] = "pad"
    sketch = doc["features"][0]["sketch"]
    distances = [r for r in sketch["constraints"] if r["kind"] == "distance"]
    for width, height in ((20, 10), (24, 12), (18, 9)):
        for relation, value in zip(distances, (width, height), strict=True):
            relation["value"] = value
        replay = regenerate(Document.from_dict(doc), OCPKernel(), result_version=3)
        assert replay.ok, replay.result
        stats = replay.result["features"][-1]["stats"]
        assert stats["valid"]
        assert stats["volume"] == pytest.approx(
            (width * height - sum(r*r for r in radii) * (1 - math.pi / 4)) * 5, abs=1e-6)
    # Both individual radii fit within the original height, but their sum does not.
    for r in sketch["constraints"]:
        if r["kind"] == "radius":
            r["value"] = 6
    snapshot = copy.deepcopy(doc)
    replay = regenerate(Document.from_dict(doc), OCPKernel(), result_version=3)
    assert not replay.ok
    assert replay.result["features"][-1]["status"] == "blocked"
    assert "pad" not in replay.shapes
    assert doc == snapshot


@pytest.mark.parametrize("value", [None, [], 2, {"version": True}])
def test_malformed_later_peer_metadata_is_explicitly_rejected(value):
    draft = adjacent_rectangle((2,))
    sketch = draft.sketch
    sketch["arcs"].append(dict(sketch["arcs"][0], id="other", fillet_intent=value))
    from mechanical_cad.fillet_intent import FilletIntentError, validate_solved
    with pytest.raises(FilletIntentError):
        validate_solved(sketch)
    addon = importlib.import_module(PACKAGE + ".fillet_intent")
    with pytest.raises(addon.FilletIntentError):
        addon.validate_solved(sketch)


def test_adjacent_preview_uses_remaining_segment_not_original_witness():
    draft = adjacent_rectangle((2,))
    lines = [line["id"] for line in draft.sketch["lines"]]
    plan = f.prepare_corner(draft.sketch, lines[1:3], 3, positions(draft))
    assert plan.segment_ends[0] != plan.outer[0]
    assert plan.segment_ends[0] == draft.sketch["arcs"][0]["end"]
    assert plan.maximum_radius == pytest.approx(8)


@pytest.mark.parametrize("mutation", ["self", "missing", "nonreciprocal", "witness", "line_role", "third_line", "generic_arc"])
def test_adjacent_explicit_roles_reject_corruption_in_both_boundaries(mutation):
    from mechanical_cad.sketch_model import SketchDefinition

    sketch = adjacent_rectangle().sketch
    arc = sketch["arcs"][0]
    intent = arc["fillet_intent"]
    if mutation == "self":
        intent["neighbors"][0] = arc["id"]
    elif mutation == "missing":
        intent["neighbors"][0] = "missing"
    elif mutation == "nonreciprocal":
        intent["neighbors"][0] = None
    elif mutation == "witness":
        intent["outer"].reverse()
    elif mutation == "line_role":
        intent["lines"].reverse()
    elif mutation == "third_line":
        sketch["lines"].append({"id": "third", "start": arc["start"], "end": arc["center"]})
    elif mutation == "generic_arc":
        sketch["arcs"].append({"id": "generic", "center": arc["start"],
                              "start": arc["center"], "end": arc["end"], "direction": "ccw"})
    with pytest.raises(ValueError):
        c._validate_sketch(sketch, journal_version=3)
    with pytest.raises(ValueError):
        SketchDefinition.from_dict(sketch)
