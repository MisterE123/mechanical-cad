"""Mixed true arcs/lines, closed holes and analytic intersection rejection."""

import copy
import math
from pathlib import Path

import pytest

from mechanical_cad.analytic_profile_geometry import area, classify, is_sector_form
from mechanical_cad.sketch_model import Arc, Circle, Line, Point, Sketch


def capsule(*, hole=True, clockwise=False):
    points = (
        Point("a", 0, -5),
        Point("b", 20, -5),
        Point("c", 20, 5),
        Point("d", 0, 5),
        Point("left", 0, 0),
        Point("right", 20, 0),
        Point("bore", 10, 0),
    )
    arcs = (Arc("right_arc", "right", "b", "c", "ccw"), Arc("left_arc", "left", "d", "a", "ccw"))
    if clockwise:
        arcs = tuple(Arc(arc.id, arc.center, arc.end, arc.start, "cw") for arc in arcs)
    return Sketch(
        "capsule",
        points,
        (Line("lower", "a", "b"), Line("upper", "c", "d")),
        (),
        schema_version=3,
        arcs=arcs,
        circles=(Circle("hole", "bore", 2),) if hole else (),
    )


def test_capsule_has_true_semicircles_hole_and_correct_area():
    result = classify(capsule().to_dict())
    assert len(result["regions"]) == 1
    region = result["regions"][0]
    assert len(region["outer"]) == 4 and len(region["holes"]) == 1
    assert area(region["outer"]) - area(region["holes"][0]) == pytest.approx(200 + 21 * math.pi)
    assert not is_sector_form(capsule().to_dict())
    assert classify(capsule(clockwise=True).to_dict()) == result


def test_semicircle_and_chord_is_closed_not_sector():
    sketch = capsule(hole=False).to_dict()
    sketch["lines"] = [{"id": "chord", "start": "c", "end": "b"}]
    sketch["arcs"] = [arc for arc in sketch["arcs"] if arc["id"] == "right_arc"]
    result = classify(sketch)
    assert area(result["regions"][0]["outer"]) == pytest.approx(12.5 * math.pi)


def test_hole_contact_and_inconsistent_radius_fail():
    sketch = capsule().to_dict()
    sketch["circles"][0]["radius"] = 5
    with pytest.raises(ValueError, match="touch"):
        classify(sketch)
    sketch = capsule().to_dict()
    next(point for point in sketch["points"] if point["id"] == "c")["v"] = 6
    with pytest.raises(ValueError, match="radii"):
        classify(sketch)


def test_crossing_and_open_arc_boundaries_fail():
    sketch = capsule(hole=False).to_dict()
    sketch["lines"][0]["end"] = "c"
    sketch["lines"][1]["start"] = "b"
    with pytest.raises(ValueError, match="intersect"):
        classify(sketch)
    sketch = capsule(hole=False).to_dict()
    sketch["arcs"].pop()
    with pytest.raises(ValueError, match="close"):
        classify(sketch)


def test_coincident_circle_arcs_overlap_rejected():
    sketch = capsule(hole=False).to_dict()
    sketch["lines"] = []
    arc = sketch["arcs"][0]
    sketch["arcs"] = [arc, {**arc, "id": "duplicate"}]
    with pytest.raises(ValueError, match="overlap"):
        classify(sketch)


def test_construction_crossing_is_excluded_and_vendor_matches_source():
    sketch = capsule().to_dict()
    sketch["lines"].append({"id": "axis", "start": "left", "end": "right", "construction": True})
    assert classify(sketch) == classify(capsule().to_dict())
    root = Path(__file__).resolve().parents[2]
    assert (root / "src/mechanical_cad/analytic_profile_geometry.py").read_bytes() == (
        root / "blender_addon/mechanical_cad_blender/analytic_profile_geometry.py"
    ).read_bytes()


def test_inner_arc_hole_and_disjoint_island():
    outer = capsule(hole=False).to_dict()
    inner = copy.deepcopy(outer)
    for point in inner["points"]:
        point["id"] = "inner_" + point["id"]
        point["u"] = point["u"] * 0.5 + 5
        point["v"] *= 0.5
    for kind in ("lines", "arcs"):
        for curve in inner[kind]:
            for field in ("id", "start", "end", "center"):
                if field in curve:
                    curve[field] = "inner_" + curve[field]
        outer[kind].extend(inner[kind])
    outer["points"].extend(inner["points"])
    result = classify(outer)
    assert len(result["regions"]) == 1
    assert len(result["regions"][0]["holes"]) == 1


def test_major_arc_and_chord_area_and_circle_inside():
    sketch = Sketch(
        "major",
        (Point("center", 0, 0), Point("start", 5, 0), Point("end", 0, -5)),
        (Line("chord", "end", "start"),),
        (),
        schema_version=3,
        arcs=(Arc("major", "center", "start", "end", "ccw"),),
        circles=(Circle("hole", "center", 1),),
    ).to_dict()
    region = classify(sketch)["regions"][0]
    assert len(region["holes"]) == 1
    assert area(region["outer"]) == pytest.approx(12.5 * (1.5 * math.pi + 1))


def test_small_translated_analytic_area_does_not_cancel():
    sketch = capsule().to_dict()
    for point in sketch["points"]:
        point["u"] += 100000
        point["v"] += 100000
    region = classify(sketch)["regions"][0]
    assert area(region["outer"]) == pytest.approx(200 + 25 * math.pi)
