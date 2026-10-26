"""Endpoint edits retain exact IDs and journal through the real sketch draft."""

import copy
import importlib
import json
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "trim_extend_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
sys.modules[PACKAGE] = package
d = importlib.import_module(PACKAGE + ".general_sketch_draft")
c = importlib.import_module(PACKAGE + ".general_sketch_commands")
t = importlib.import_module(PACKAGE + ".line_trim_extend")


def setup(boundary_x=5, journal_version=2):
    owner = d.GeneralSketchDraft(
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
        journal_version=journal_version,
    )
    a, b, line = owner.execute(c.AddLine(c.PointSeed(0, 0), c.PointSeed(10, 0))).entity_ids
    _, _, boundary = owner.execute(
        c.AddLine(c.PointSeed(boundary_x, -3), c.PointSeed(boundary_x, 3))
    ).entity_ids
    return owner, a, b, line, boundary


def preview(owner, line, boundary, near=(9, 0), mode="Trim"):
    points = {p["id"]: (p["u"], p["v"]) for p in owner.sketch["points"]}
    return t.prepare_line_edit(owner.sketch, points, line, boundary, near, mode)


@pytest.mark.parametrize(
    "x,near,mode,expected",
    [
        (5, (9, 0), "Trim", (5, 0)),
        (5, (1, 0), "Trim", (5, 0)),
        (15, (9, 0), "Extend", (15, 0)),
        (-5, (1, 0), "Extend", (-5, 0)),
    ],
)
def test_edit_preview_apply_and_persistent_undo(x, near, mode, expected):
    owner, a, b, line, boundary = setup(x)
    before = copy.deepcopy(owner.sketch)
    edit = preview(owner, line, boundary, near, mode)
    assert edit.target == expected
    assert owner.sketch == before  # Preview/Cancel cannot mutate canonical geometry.
    owner.execute(c.MovePoint(edit.point_id, edit.target))
    after = owner.sketch
    assert after["lines"] == before["lines"]
    assert after["constraints"] == before["constraints"]
    assert [p for p in after["points"] if p["id"] != edit.point_id] == [
        p for p in before["points"] if p["id"] != edit.point_id
    ]
    restored = d.GeneralSketchDraft.from_checkpoint_payload(owner.checkpoint_payload())
    assert restored.sketch == after
    restored.undo()
    assert restored.sketch == before
    restored.redo()
    assert restored.sketch == after


@pytest.mark.parametrize(
    "x,near,mode,message",
    [
        (15, (9, 0), "Trim", "inside"),
        (5, (9, 0), "Extend", "facing"),
        (15, (1, 0), "Extend", "facing"),
        (5, (5, 0), "Trim", "closer"),
        (0, (9, 0), "Trim", "inside"),
    ],
)
def test_wrong_side_noop_and_ambiguous_endpoint_refused(x, near, mode, message):
    owner, _, _, line, boundary = setup(x)
    with pytest.raises(t.LineEditError, match=message):
        preview(owner, line, boundary, near, mode)


def test_relations_are_not_silently_removed():
    owner, _, _, line, boundary = setup()
    owner.execute(c.AddRelation("horizontal", (line,)))
    before = copy.deepcopy(owner.sketch)
    with pytest.raises(t.LineEditError, match="Release.*relations"):
        preview(owner, line, boundary)
    assert owner.sketch == before


def test_shared_endpoint_cannot_move_connected_geometry():
    owner, _, b, line, boundary = setup()
    owner.execute(c.AddLine(c.PointRef(b), c.PointSeed(12, 2)))
    with pytest.raises(t.LineEditError, match="shared"):
        preview(owner, line, boundary)


def test_parallel_and_finite_boundary_checks():
    owner, _, _, line, boundary = setup()
    points = {p["id"]: (p["u"], p["v"]) for p in owner.sketch["points"]}
    boundary_record = next(item for item in owner.sketch["lines"] if item["id"] == boundary)
    points[boundary_record["start"]] = (2, 3)
    points[boundary_record["end"]] = (8, 3)
    with pytest.raises(t.LineEditError, match="Parallel"):
        t.prepare_line_edit(owner.sketch, points, line, boundary, (9, 0), "Trim")
    points[boundary_record["end"]] = (2, 6)
    with pytest.raises(t.LineEditError, match="beyond"):
        t.prepare_line_edit(owner.sketch, points, line, boundary, (9, 0), "Trim")


def circle_setup(center=(5, 0), radius=2):
    owner, a, b, line, _ = setup()
    _, circle = owner.execute(c.AddCircle(c.PointSeed(*center), radius)).entity_ids
    return owner, a, b, line, circle


def circle_preview(owner, line, circle, near=(9, 0), mode="Trim", resolved=None):
    geometry_module = importlib.import_module(PACKAGE + ".general_view_geometry")
    geometry = geometry_module.build_geometry(owner.sketch, source="authored")
    return t.prepare_line_edit(
        owner.sketch,
        geometry.points,
        line,
        circle,
        near,
        mode,
        circles=geometry.circles if resolved is None else resolved,
    )


@pytest.mark.parametrize(
    "center,radius,near,mode,expected",
    [
        ((5, 0), 2, (9, 0), "Trim", (7, 0)),
        ((5, 0), 2, (1, 0), "Trim", (3, 0)),
        ((15, 0), 2, (9, 0), "Extend", (13, 0)),
        ((-5, 0), 2, (1, 0), "Extend", (-3, 0)),
        ((5, 0), 8, (9, 0), "Extend", (13, 0)),
        ((5, 0), 8, (1, 0), "Extend", (-3, 0)),
        ((5, 3), 5, (9, 0), "Trim", (9, 0)),
        ((10, 0), 2, (9, 0), "Trim", (8, 0)),
        ((10, 0), 2, (9, 0), "Extend", (12, 0)),
    ],
)
def test_circle_nearest_crossing_identity_checkpoint_and_undo(center, radius, near, mode, expected):
    owner, _, _, line, circle = circle_setup(center, radius)
    before = copy.deepcopy(owner.sketch)
    edit = circle_preview(owner, line, circle, near, mode)
    assert edit.target == pytest.approx(expected)
    assert owner.sketch == before
    owner.execute(c.MovePoint(edit.point_id, edit.target))
    after = owner.sketch
    for field in ("lines", "circles", "constraints"):
        assert after[field] == before[field]
    assert [p for p in after["points"] if p["id"] != edit.point_id] == [
        p for p in before["points"] if p["id"] != edit.point_id
    ]
    restored = d.GeneralSketchDraft.from_checkpoint_payload(owner.checkpoint_payload())
    assert restored.sketch == after
    restored.undo()
    assert restored.sketch == before
    restored.redo()
    assert restored.sketch == after


@pytest.mark.parametrize("center,message", [((5, 2), "Tangent"), ((5, 3), "does not intersect")])
def test_circle_tangent_and_disjoint_are_refused_without_mutation(center, message):
    owner, _, _, line, circle = circle_setup(center)
    before = copy.deepcopy(owner.sketch)
    with pytest.raises(t.LineEditError, match=message):
        circle_preview(owner, line, circle)
    assert owner.sketch == before


def test_circle_requires_resolved_geometry_and_uses_solved_not_authored_radius():
    owner, _, _, line, circle = circle_setup()
    with pytest.raises(t.LineEditError, match="unavailable"):
        circle_preview(owner, line, circle, resolved={})
    resolved = {circle: types.SimpleNamespace(center_mm=(5, 0), radius_mm=3)}
    assert circle_preview(owner, line, circle, resolved=resolved).target == (8, 0)


def test_circle_boundary_does_not_relax_constraint_or_shared_endpoint_guards():
    owner, _, b, line, circle = circle_setup()
    owner.execute(c.AddRelation("horizontal", (line,)))
    with pytest.raises(t.LineEditError, match="Release.*relations"):
        circle_preview(owner, line, circle)
    owner.undo()
    owner.execute(c.AddCircle(c.PointRef(b), 1))
    with pytest.raises(t.LineEditError, match="shared"):
        circle_preview(owner, line, circle)


def test_circle_boundary_relations_are_preserved():
    owner, _, _, line, circle = circle_setup()
    owner.execute(c.AddRelation("radius", (circle,), value=2))
    before = copy.deepcopy(owner.sketch["constraints"])
    edit = circle_preview(owner, line, circle)
    owner.execute(c.MovePoint(edit.point_id, edit.target))
    assert owner.sketch["constraints"] == before


@pytest.mark.parametrize("offset,scale", [(0, 1e-4), (0, 1), (999000, 10)])
def test_circle_oblique_crossings_are_analytic_at_supported_scales(offset, scale):
    owner, a, b, line, circle = circle_setup()
    points = {p["id"]: (p["u"], p["v"]) for p in owner.sketch["points"]}
    points[a] = (offset, offset)
    points[b] = (offset + 6 * scale, offset + 8 * scale)
    resolved = {
        circle: types.SimpleNamespace(
            center_mm=(offset + 3 * scale, offset + 4 * scale),
            radius_mm=2 * scale,
        )
    }
    edit = t.prepare_line_edit(
        owner.sketch,
        points,
        line,
        circle,
        points[b],
        "Trim",
        circles=resolved,
    )
    assert edit.target == pytest.approx((offset + 4.2 * scale, offset + 5.6 * scale), abs=1e-8)


def test_circle_current_endpoint_is_not_a_noop_crossing():
    owner, _, _, line, circle = circle_setup((8, 0), 2)
    assert circle_preview(owner, line, circle).target == (6, 0)
    with pytest.raises(t.LineEditError, match="facing"):
        circle_preview(owner, line, circle, mode="Extend")


def test_circle_nearly_tangent_and_invalid_resolved_radius_fail_visibly():
    owner, _, _, line, circle = circle_setup((5, 2 - 1e-8))
    with pytest.raises(t.LineEditError, match="nearly tangent"):
        circle_preview(owner, line, circle)
    for radius in (float("nan"), float("inf"), 0, -2):
        resolved = {circle: types.SimpleNamespace(center_mm=(5, 0), radius_mm=radius)}
        with pytest.raises(t.LineEditError, match="finite positive radius"):
            circle_preview(owner, line, circle, resolved=resolved)


def arc_setup(start_degrees=-45, end_degrees=45, direction="ccw"):
    import math

    owner, a, b, line, _ = setup(journal_version=3)

    def seed(angle):
        angle = math.radians(angle)
        return c.PointSeed(5 + 2 * math.cos(angle), 2 * math.sin(angle))

    arc = owner.execute(
        c.AddArc(c.PointSeed(5, 0), seed(start_degrees), seed(end_degrees), direction)
    ).entity_ids[-1]
    return owner, a, b, line, arc


def arc_preview(owner, line, arc, near=(9, 0), mode="Trim", resolved=None):
    geometry_module = importlib.import_module(PACKAGE + ".general_view_geometry")
    geometry = geometry_module.build_geometry(owner.sketch, source="authored")
    return t.prepare_line_edit(
        owner.sketch,
        geometry.points,
        line,
        arc,
        near,
        mode,
        arcs=geometry.arcs if resolved is None else resolved,
    )


@pytest.mark.parametrize(
    "start,end,direction,expected",
    [
        (-45, 45, "ccw", 7),
        (-45, 45, "cw", 3),
        (45, -45, "cw", 7),
        (45, -45, "ccw", 3),
        (135, 225, "ccw", 3),
        (135, 225, "cw", 7),
        (0, 90, "ccw", 7),
        (90, 180, "ccw", 3),
    ],
)
def test_finite_arc_minor_major_reversed_and_endpoint_crossings(start, end, direction, expected):
    owner, _, _, line, arc = arc_setup(start, end, direction)
    before = copy.deepcopy(owner.sketch)
    edit = arc_preview(owner, line, arc)
    assert edit.target == pytest.approx((expected, 0))
    assert owner.sketch == before
    owner.execute(c.MovePoint(edit.point_id, edit.target))
    after = owner.sketch
    for field in ("lines", "arcs", "constraints"):
        assert after[field] == before[field]
    restored = d.GeneralSketchDraft.from_checkpoint_payload(
        owner.checkpoint_payload(),
        expected_journal_version=3,
    )
    restored.undo()
    assert restored.sketch == before
    restored.redo()
    assert restored.sketch == after


def test_arc_reversal_changes_eligible_crossing_without_changing_ids():
    owner, _, _, line, arc = arc_setup()
    assert arc_preview(owner, line, arc).target == pytest.approx((7, 0))
    owner.execute(c.ReverseArcSweep(arc))
    assert arc_preview(owner, line, arc).target == pytest.approx((3, 0))


@pytest.mark.parametrize("start,end,direction", [(45, 135, "ccw"), (135, 45, "cw")])
def test_arc_supporting_circle_hits_outside_sweep_are_refused(start, end, direction):
    owner, _, _, line, arc = arc_setup(start, end, direction)
    before = copy.deepcopy(owner.sketch)
    with pytest.raises(t.LineEditError, match="outside.*finite arc sweep"):
        arc_preview(owner, line, arc)
    assert owner.sketch == before


def test_arc_endpoint_tolerance_is_spatial_and_does_not_admit_far_outside_hits():
    import math

    owner, _, _, line, arc = arc_setup(45, math.degrees(1e-8), "cw")
    assert arc_preview(owner, line, arc).target == pytest.approx((7, 0))
    owner, _, _, line, arc = arc_setup(45, math.degrees(1e-6), "cw")
    with pytest.raises(t.LineEditError, match="outside"):
        arc_preview(owner, line, arc)


def test_arc_missing_or_unsolved_unequal_radii_are_refused():
    owner, _, _, line, arc = arc_setup()
    with pytest.raises(t.LineEditError, match="unavailable"):
        arc_preview(owner, line, arc, resolved={})
    resolved = {
        arc: types.SimpleNamespace(
            center_mm=(5, 0),
            start_mm=(7, 0),
            end_mm=(5, 3),
            direction="ccw",
            radius_mm=2,
        )
    }
    with pytest.raises(t.LineEditError, match="equal-radius solve"):
        arc_preview(owner, line, arc, resolved=resolved)


def test_arc_boundary_keeps_target_constraint_and_shared_endpoint_guards():
    owner, _, b, line, arc = arc_setup()
    owner.execute(c.AddRelation("horizontal", (line,)))
    with pytest.raises(t.LineEditError, match="Release.*relations"):
        arc_preview(owner, line, arc)
    owner.undo()
    owner.execute(c.AddLine(c.PointRef(b), c.PointSeed(10, 5)))
    with pytest.raises(t.LineEditError, match="shared"):
        arc_preview(owner, line, arc)


@pytest.mark.parametrize("direction,expected", [("ccw", 7), ("cw", 3)])
@pytest.mark.parametrize("mode", ["Trim", "Extend"])
def test_arc_can_edit_start_endpoint_with_same_finite_sweep_policy(direction, expected, mode):
    owner, a, b, line, arc = arc_setup(direction=direction)
    geometry_module = importlib.import_module(PACKAGE + ".general_view_geometry")
    geometry = geometry_module.build_geometry(owner.sketch, source="authored")
    points = dict(geometry.points)
    if mode == "Extend":
        points[a], points[b] = (10, 0), (20, 0)
    edit = t.prepare_line_edit(
        owner.sketch,
        points,
        line,
        arc,
        points[a],
        mode,
        arcs=geometry.arcs,
    )
    assert edit.point_id == a
    assert edit.target == pytest.approx((expected, 0))
