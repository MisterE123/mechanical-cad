"""Pure atomic literal-length line intent and strict local-journal coverage."""

import copy
import importlib
import json
import sys
import types
from pathlib import Path

import pytest

PACKAGE = "mcad_pending_length_command_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [
    str(Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender")
]
sys.modules[PACKAGE] = package
c = importlib.import_module(PACKAGE + ".general_sketch_commands")
d = importlib.import_module(PACKAGE + ".general_sketch_draft")


def draft(version=2):
    document = {
        "schema_version": 1,
        "id": "doc",
        "name": "Part",
        "units": "mm",
        "parameters": {},
        "features": [],
        "active_feature": None,
    }
    return d.GeneralSketchDraft(json.dumps(document), journal_version=version)


@pytest.mark.parametrize("version", [2, 3])
@pytest.mark.parametrize("axis", [None, "horizontal", "vertical"])
def test_atomic_length_line_undo_redo_restore_and_driver_binding(version, axis):
    state = draft(version)
    before = state.sketch
    end = (0, -5) if axis == "vertical" else (5, 0)
    result = state.execute(c.AddLengthLine(c.PointSeed(0, 0), c.PointSeed(*end), 5, axis))
    expected = state.sketch
    points = [p["id"] for p in expected["points"]]
    line = expected["lines"][0]
    constraints = expected["constraints"]
    assert result.entity_ids == tuple(points + [line["id"]] + [r["id"] for r in constraints])
    assert result.constraint_id == constraints[0]["id"]
    assert constraints[0] == {"id": "r_d4", "kind": "distance", "refs": points, "value": 5}
    assert len(constraints) == (1 if axis is None else 2)
    assert not any(r["kind"] == "fixed" for r in constraints)
    if axis:
        assert constraints[1] == {"id": "r_d5", "kind": axis, "refs": [line["id"]]}
    payload = state.checkpoint_payload()
    assert len(payload["journal"]["entries"]) == 1
    assert payload["journal"]["entries"][0]["command"]["op"] == "add_length_line"
    restored = d.GeneralSketchDraft.from_checkpoint_payload(
        payload, expected_journal_version=version
    )
    restored.undo()
    assert restored.sketch == before
    # A dormant redo branch also must replay and validate on restoration.
    restored = d.GeneralSketchDraft.from_checkpoint_payload(
        restored.checkpoint_payload(), expected_journal_version=version
    )
    restored.redo()
    assert restored.sketch == expected
    restored.begin_edit(result.constraint_id)
    restored.update_edit("7.5")
    trial = restored.solve_request(trial=True)
    edited = next(f for f in trial["document"]["features"] if f["id"] == restored.feature_id)
    assert edited["sketch"]["constraints"][0]["value"] == "7.5"
    assert restored.sketch == expected  # Trial is not accepted without evidence.
    restored.cancel_edit()


@pytest.mark.parametrize(
    "length",
    [True, False, "5", "2 + 3", None, 0, -1, 1e-7, 1e7, float("inf"), float("-inf"), float("nan")],
)
def test_invalid_literal_length_is_atomic(length):
    state = draft()
    before = state.checkpoint_payload()
    with pytest.raises(c.DraftError):
        state.execute(c.AddLengthLine(c.PointSeed(0, 0), c.PointSeed(5, 0), length))
    assert state.checkpoint_payload() == before


def test_explicit_endpoint_reuse_and_branch_allocations():
    state = draft()
    a = state.execute(c.AddPoint(c.PointSeed(0, 0))).entity_ids[0]
    b = state.execute(c.AddPoint(c.PointSeed(5, 0))).entity_ids[0]
    before = state.sketch
    first = state.execute(c.AddLengthLine(c.PointRef(a), c.PointRef(b), 5))
    assert state.sketch["points"] == before["points"]
    assert len(first.entity_ids) == 2
    state.undo()
    second = state.execute(c.AddLengthLine(c.PointRef(a), c.PointSeed(0, 5), 5, "vertical"))
    assert not set(first.entity_ids) & set(second.entity_ids)
    restored = d.GeneralSketchDraft.from_checkpoint_payload(state.checkpoint_payload())
    assert restored.sketch == state.sketch
    assert restored.sketch["points"][:2] == before["points"]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda r: r["constraints"][0].update(value="5"),
        lambda r: r["constraints"][0].update(value=True),
        lambda r: r["constraints"][0].update(value=0),
        lambda r: r["constraints"][0].update(kind="radius"),
        lambda r: r["constraints"][0].update(refs=[r["lines"][0]["id"]]),
        lambda r: r["constraints"][1].update(kind="fixed"),
        lambda r: r["constraints"][1].update(refs=[r["points"][0]["id"]]),
        lambda r: r["constraints"].reverse(),
        lambda r: r["points"].append({"id": "extra", "u": 8, "v": 9}),
        lambda r: r["lines"][0].update(construction=True),
        lambda r: r.update(op="add"),
    ],
)
def test_reducer_rejects_unrelated_or_malformed_compound_records(mutate):
    state = draft()
    state.execute(c.AddLengthLine(c.PointSeed(0, 0), c.PointSeed(5, 0), 5, "horizontal"))
    entry = state.checkpoint_payload()["journal"]["entries"][0]
    record = copy.deepcopy(entry["command"])
    mutate(record)
    with pytest.raises(c.DraftError):
        c._apply_record(entry["before"], record)


@pytest.mark.parametrize("axis,opcode", [(None, "add"), ("horizontal", "add_axis_line")])
def test_legacy_line_allocation_and_records_are_unchanged(axis, opcode):
    state = draft()
    result = state.execute(c.AddLine(c.PointSeed(0, 0), c.PointSeed(5, 0), axis))
    assert result.entity_ids == (
        ("p_d1", "p_d2", "l_d3") if axis is None else ("p_d1", "p_d2", "l_d3", "r_d4")
    )
    entry = state.checkpoint_payload()["journal"]["entries"][0]
    assert entry["command"]["op"] == opcode
    restored = d.GeneralSketchDraft.from_checkpoint_payload(state.checkpoint_payload())
    assert restored.sketch == state.sketch
