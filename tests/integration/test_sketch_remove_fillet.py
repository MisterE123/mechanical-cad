"""Exact corner restoration and refusal contracts, without native execution."""

import importlib
import json

import pytest
from test_sketch_corner_fillet import PACKAGE, adjacent_rectangle, c, d, positions, setup

remove = importlib.import_module(PACKAGE + ".sketch_remove_fillet")


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("angle", [30, 90, 160, -60, -90])
def test_isolated_remove_restores_exact_geometry_and_history(reverse, angle):
    draft, lines, _, _ = setup(angle, reverse)
    original = draft.sketch
    draft.execute(c.CornerFillet(lines, 2, positions(draft)))
    rounded = draft.sketch
    allocation = draft.checkpoint_payload()["next_id"]
    draft.execute(c.RemoveCornerFillet(rounded["arcs"][0]["id"]))
    sharp = draft.sketch
    for collection in ("points", "lines", "constraints"):
        assert sharp[collection] == original[collection]
    assert sharp["arcs"] == []
    assert draft.checkpoint_payload()["next_id"] == allocation
    restored = d.GeneralSketchDraft.from_checkpoint_payload(draft.checkpoint_payload(), expected_journal_version=3)
    assert restored.sketch == sharp
    restored.undo()
    assert restored.sketch == rounded
    restored.redo()
    assert restored.sketch == sharp


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("index", [0, 1, 2, 3])
def test_four_corners_remove_one_preserves_other_corners_and_dimensions(reverse, index):
    from mechanical_cad.fillet_intent import validate_solved
    from mechanical_cad.sketch_model import Sketch

    draft = adjacent_rectangle((1, 2, 3, 2), reverse)
    before = draft.sketch
    arc = before["arcs"][index]
    record = remove.make_record(before, arc["id"])
    draft.execute(c.RemoveCornerFillet(arc["id"]))
    after = draft.sketch
    deleted = {r["id"] for r in record["constraints"]}
    assert after["constraints"] == [r for r in before["constraints"] if r["id"] not in deleted]
    private = {p["id"] for p in record["points"]}
    assert after["points"] == [p for p in before["points"] if p["id"] not in private]
    for line in after["lines"]:
        if line["id"] not in arc["fillet_intent"]["lines"]:
            assert line == next(old for old in before["lines"] if old["id"] == line["id"])
    assert len(after["arcs"]) == 3
    assert all(arc["id"] not in a["fillet_intent"]["neighbors"] for a in after["arcs"])
    assert Sketch.from_dict(after).to_dict()["arcs"]
    validate_solved(after)
    draft.undo()
    assert draft.sketch == before
    draft.redo()
    assert draft.sketch == after
    for remaining in list(after["arcs"]):
        draft.execute(c.RemoveCornerFillet(remaining["id"]))
    assert draft.sketch["arcs"] == []
    assert len(draft.sketch["points"]) == 4
    assert len(draft.sketch["constraints"]) == 7


@pytest.mark.parametrize("mutation", [
    lambda r: r.update(source_schema_version=3.0),
    lambda r: r["arc"]["fillet_intent"].update(version=True),
    lambda r: r.update(points=tuple(r["points"])),
    lambda r: r["constraints"][0].update(refs=tuple(r["constraints"][0]["refs"])),
    lambda r: r["line_updates"][0]["after"].update(extra=1),
    lambda r: r["peer_updates"][0]["after"].update(version=2.0),
    lambda r: r["points"][0].update(u=True),
    lambda r: r["peer_updates"][0]["after"].update(neighbors=[None, None]),
])
def test_strict_record_corruption_refuses_before_mutation(mutation):
    draft = adjacent_rectangle((1, 2, 3, 2))
    original = draft.sketch
    record = remove.make_record(original, original["arcs"][0]["id"])
    mutation(record)
    with pytest.raises(ValueError):
        remove.apply_record(original, record)
    assert original == draft.sketch


@pytest.mark.parametrize("kind", ["private_fixed", "arc_tangent", "line_length", "third_curve"])
def test_extra_attachments_refuse_atomically(kind):
    draft = adjacent_rectangle((2,))
    arc = draft.sketch["arcs"][0]
    if kind == "private_fixed":
        draft.execute(c.AddRelation("fixed", (arc["center"],), target=positions(draft)[arc["center"]]))
    elif kind == "arc_tangent":
        other = draft.execute(c.AddLine(c.PointRef(arc["start"]), c.PointSeed(60, 50))).entity_ids[-1]
        draft.execute(c.AddRelation("tangent", (arc["id"], other)))
    elif kind == "line_length":
        draft.execute(c.AddRelation("distance", (arc["start"], arc["end"]), 2))
    else:
        draft.execute(c.AddLine(c.PointRef(arc["center"]), c.PointSeed(50, 50)))
    before = draft.checkpoint_payload()
    with pytest.raises(ValueError, match="Remove Fillet refused"):
        draft.execute(c.RemoveCornerFillet(arc["id"]))
    assert draft.checkpoint_payload() == before


def test_remove_then_refillet_uses_original_corner_identity():
    draft = adjacent_rectangle((1, 2, 3, 2))
    arc = draft.sketch["arcs"][1]
    intent = arc["fillet_intent"]
    draft.execute(c.RemoveCornerFillet(arc["id"]))
    draft.execute(c.CornerFillet(tuple(intent["lines"]), 1, positions(draft)))
    assert draft.sketch["arcs"][-1]["fillet_intent"]["corner"] == intent["corner"]
    assert draft.sketch["arcs"][-1]["id"] != arc["id"]


def test_annotation_retirement_is_visible_and_survives_resume_undo_redo():
    author = importlib.import_module(PACKAGE + ".general_authoring")
    dispatch = importlib.import_module(PACKAGE + ".draft_dispatch")
    draft = adjacent_rectangle((1, 2, 3, 2))
    ui = author.GeneralSketchAuthoringState(draft, ui_version=2)
    arc = ui.command_draft.sketch["arcs"][0]
    radius = next(r for r in ui.command_draft.sketch["constraints"]
                  if r["kind"] == "radius" and r["refs"] == [arc["id"]])
    ui.place_annotation(radius["id"], (4, 5), display="diameter")
    ui.place_reference("length", "line", arc["fillet_intent"]["lines"][0], (6, 7))
    ui.select((("arc", arc["id"]),))
    annotations = ui.annotations
    record = remove.validate_annotation_attachments(ui, arc["id"])
    ui.command_draft.execute(c.RemoveCornerFillet(arc["id"]))
    remove.retain_removal_ui(ui, record)
    assert ui.selection == []
    assert ui.annotations == annotations
    status = {s.identifier: s for s in ui.status.annotations}
    assert status[radius["id"]].state == "missing"
    assert sum(s.available for s in ui.status.annotations) == 1
    restored = dispatch.restore(dispatch.dumps(ui), ui.document_json)
    assert restored.annotations == annotations
    restored.command_draft.undo()
    assert all(s.available for s in restored.status.annotations)
    assert restored.annotations == annotations
    restored.command_draft.redo()
    remove.retain_removal_ui(restored, record)
    assert restored.annotations == annotations
    assert sum(s.available for s in restored.status.annotations) == 1


def test_arc_reference_annotation_refuses_without_changing_ui_or_geometry():
    author = importlib.import_module(PACKAGE + ".general_authoring")
    dispatch = importlib.import_module(PACKAGE + ".draft_dispatch")
    ui = author.GeneralSketchAuthoringState(adjacent_rectangle((2,)), ui_version=2)
    arc = ui.command_draft.sketch["arcs"][0]
    ui.place_reference("radius", "arc", arc["id"], (5, 6))
    before = dispatch.dumps(ui)
    with pytest.raises(ValueError, match="reference annotation"):
        remove.validate_annotation_attachments(ui, arc["id"])
    assert dispatch.dumps(ui) == before


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("remove_all", [False, True])
def test_native_restored_corner_consumed_volume_and_dimension_edits(reverse, remove_all):
    import math

    pytest.importorskip("slvs")
    pytest.importorskip("OCP")
    from mechanical_cad.engine import regenerate
    from mechanical_cad.kernel_ocp import OCPKernel
    from mechanical_cad.model import Document

    radii = (1, 2, 3, 2)
    draft = adjacent_rectangle(radii, reverse)
    arcs = draft.sketch["arcs"]
    removed = arcs if remove_all else [arcs[1]]
    doc = draft.candidate()
    doc["features"].append({"id": "pad", "kind": "extrude", "label": "Plate",
                            "params": {"length": 5}, "inputs": {"profile": draft.feature_id}})
    doc["active_feature"] = "pad"
    original_doc = json.dumps(doc, sort_keys=True)
    draft = d.GeneralSketchDraft(json.dumps(doc), draft.feature_id, True, journal_version=3)
    assert draft.consumed_by == ("pad",)
    for arc in removed:
        draft.execute(c.RemoveCornerFillet(arc["id"]))
    assert json.dumps(doc, sort_keys=True) == original_doc
    doc = draft.candidate()
    sketch = doc["features"][0]["sketch"]
    remaining = () if remove_all else (1, 3, 2)
    assert len(sketch["arcs"]) == len(remaining)
    distances = [r for r in sketch["constraints"] if r["kind"] == "distance"]
    for width, height in ((20, 10), (24, 12)):
        for relation, value in zip(distances, (width, height), strict=True):
            relation["value"] = value
        before = Document.from_dict(doc).to_json()
        replay = regenerate(Document.from_dict(doc), OCPKernel(), result_version=3)
        assert replay.ok, replay.result
        stats = replay.result["features"][-1]["stats"]
        assert stats["valid"]
        assert stats["volume"] == pytest.approx(
            (width * height - sum(r*r for r in remaining) * (1 - math.pi / 4)) * 5, abs=1e-6)
        assert Document.from_dict(doc).to_json() == before


@pytest.mark.parametrize("axis_locked", [False, True])
def test_native_free_geometry_removal_preserves_placement_or_refuses(axis_locked):
    pytest.importorskip("slvs")
    from mechanical_cad.sketch_model import Sketch
    from mechanical_cad.sketch_solver import solve

    guard = importlib.import_module(PACKAGE + ".sketch_remove_fillet_session")
    draft, lines, _, _ = setup()
    if axis_locked:
        draft.execute(c.AddRelation("horizontal", (lines[0],)))
        draft.execute(c.AddRelation("vertical", (lines[1],)))
    draft.execute(c.CornerFillet(lines, 2, positions(draft)))
    original = draft.checkpoint_payload()
    before = solve(Sketch.from_dict(draft.sketch))
    assert before.success and before.remaining_dof > 0
    candidate = d.GeneralSketchDraft.from_checkpoint_payload(original, expected_journal_version=3)
    candidate.execute(c.RemoveCornerFillet(draft.sketch["arcs"][0]["id"]))
    after = solve(Sketch.from_dict(candidate.sketch))
    assert after.success and after.remaining_dof > 0
    retained = {p["id"] for p in candidate.sketch["points"]}
    if axis_locked:
        guard.same_retained_points(before.sketch.to_dict(), after.sketch.to_dict(), retained)
        # A fresh serialized canonical reopen/rebuild uses the same placement,
        # without retaining live evidence or adding fixed constraints.
        reopened = Sketch.from_dict(json.loads(Sketch.from_dict(candidate.sketch).to_json()))
        rebuilt = solve(reopened)
        assert rebuilt.success
        guard.same_retained_points(before.sketch.to_dict(), rebuilt.sketch.to_dict(), retained)
    else:
        with pytest.raises(ValueError, match="Constrain the sketch placement first"):
            guard.same_retained_points(before.sketch.to_dict(), after.sketch.to_dict(), retained)
    assert draft.checkpoint_payload() == original
