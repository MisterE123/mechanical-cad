"""Atomic observed-proposal preparation, independent of viewport and solver."""

import importlib
import json
import sys
import types
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "mcad_general_proposals_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
sys.modules[PACKAGE] = package
p = importlib.import_module(PACKAGE + ".general_proposals")
a = importlib.import_module(PACKAGE + ".general_authoring")
d = importlib.import_module(PACKAGE + ".general_sketch_draft")
s = importlib.import_module(PACKAGE + ".general_authoring_store")
BASE = '{"schema_version":1,"id":"doc","name":"Part","units":"mm","parameters":{},"features":[],"active_feature":null}\n'


def empty():
    return a.GeneralSketchAuthoringState(d.GeneralSketchDraft(BASE))


def line():
    state = empty()
    state.begin_line(d.PointSeed(0, 0), (3, 4))
    return state


def circle():
    state = empty()
    state.begin_circle(d.PointSeed(5, 6), 7)
    return state


@pytest.mark.parametrize("factory,collection", [(line, "lines"), (circle, "circles")])
def test_acceptance_is_one_detached_command_and_one_ui_change(factory, collection):
    current = factory()
    before = s.dumps(current)
    staged = p.prepare_proposal(current)
    assert s.dumps(current) == before
    replacement = staged.replacement(current)
    assert replacement is not current and replacement.command_draft is not current.command_draft
    assert replacement.revision == current.revision + 1
    assert replacement.ui_revision == current.ui_revision + 1
    assert replacement.proposal is None
    assert len(replacement.command_draft.sketch[collection]) == 1
    assert replacement.command_draft.sketch["constraints"] == []
    assert not replacement.command_draft.has_current_solution
    assert len(replacement.command_draft.checkpoint_payload()["journal"]["entries"]) == 1
    assert s.dumps(current) == before
    # No gesture is restarted and no implicit point lock/axis relation is added.
    assert replacement.tool == current.tool


def test_explicit_endpoint_reuse_joins_by_id_without_proximity_inference():
    state = empty()
    first = state.command_draft.execute(d.AddLine(d.PointSeed(0, 0), d.PointSeed(3, 4)))
    start_id, shared_id, _line = first.entity_ids
    state.begin_line(d.PointRef(shared_id), (0, 0))
    staged = p.prepare_proposal(state, endpoint=d.PointRef(start_id))
    accepted = staged.replacement(state)
    assert len(accepted.command_draft.sketch["points"]) == 2
    assert accepted.command_draft.sketch["lines"][-1]["end"] == start_id
    assert len(staged.entity_ids) == 1  # The two existing IDs were not reallocated.
    other = p.prepare_proposal(state).replacement(state)
    assert len(other.command_draft.sketch["points"]) == 3
    assert other.command_draft.sketch["lines"][-1]["end"] != start_id


@pytest.mark.parametrize("kind", ["line", "circle"])
@pytest.mark.parametrize("value", [None, 0])
def test_missing_or_degenerate_observation_retains_whole_proposal(kind, value):
    state = empty()
    if kind == "line":
        state.begin_line(d.PointSeed(0, 0), None if value is None else (0, 0))
    else:
        state.begin_circle(d.PointSeed(0, 0), value)
    before = s.dumps(state)
    with pytest.raises(d.DraftError):
        p.prepare_proposal(state)
    assert s.dumps(state) == before


@pytest.mark.parametrize("endpoint", ["p_d1", (1, 2), {"id": "p_d1"}, 1, True])
def test_endpoint_binding_is_explicit(endpoint):
    state = line()
    before = s.dumps(state)
    with pytest.raises(d.DraftError):
        p.prepare_proposal(state, endpoint=endpoint)
    assert s.dumps(state) == before


def test_circle_rejects_endpoint_override():
    state = circle()
    before = s.dumps(state)
    with pytest.raises(d.DraftError):
        p.prepare_proposal(state, endpoint=d.PointSeed(8, 9))
    assert s.dumps(state) == before


@pytest.mark.parametrize("change", ["command", "tool", "observation", "raw"])
def test_exact_source_guard_rejects_every_changed_intent(change):
    state = line()
    staged = p.prepare_proposal(state)
    if change == "command":
        state.command_draft.execute(d.AddPoint(d.PointSeed(10, 10)))
    elif change == "tool":
        state.select_tool("Select")
    elif change == "observation":
        state.update_line((4, 5))
    else:
        state.command_draft.execute(d.AddCircle(d.PointSeed(0, 0), 4))
        cid = state.command_draft.sketch["circles"][0]["id"]
        relation = state.command_draft.execute(d.AddRelation("radius", (cid,), value=4))
        state.command_draft.begin_edit(relation.constraint_id)
        state.command_draft.update_edit("  invalid +( ")
    before = s.dumps(state)
    with pytest.raises(d.DraftError, match="changed"):
        staged.replacement(state)
    assert s.dumps(state) == before


@pytest.mark.parametrize("counter", ["ui", "command", "allocator"])
def test_overflow_fails_before_live_state_mutation(counter):
    state = line()
    payload = json.loads(s.dumps(state))
    if counter == "ui":
        payload["ui"]["revision"] = 2**53 - 1
    else:
        payload["draft"]["revision" if counter == "command" else "next_id"] = 2**53 - 1
    state = s.restore(json.dumps(payload), BASE)
    before = s.dumps(state)
    with pytest.raises(d.DraftError):
        p.prepare_proposal(state)
    assert s.dumps(state) == before


def test_final_serialization_failure_leaves_both_live_layers_exact():
    state = line()
    before = s.dumps(state)
    real = s.dumps
    calls = []

    def fail_candidate(value):
        calls.append(value)
        if value is not state:
            raise s.SnapshotError("Injected combined byte budget")
        return real(value)

    with patch.object(s, "dumps", side_effect=fail_candidate):
        with pytest.raises(s.SnapshotError, match="byte budget"):
            p.prepare_proposal(state)
    assert len(calls) == 2 and s.dumps(state) == before


def test_missing_anchor_stays_recoverable_and_never_rebinds():
    state = empty()
    point = state.command_draft.execute(d.AddPoint(d.PointSeed(0, 0))).entity_ids[0]
    state.begin_line(d.PointRef(point), (3, 4))
    state.command_draft.undo()
    state.command_draft.execute(d.AddPoint(d.PointSeed(0, 0)))
    before = s.dumps(state)
    with pytest.raises(d.DraftError, match="unavailable"):
        p.prepare_proposal(state)
    assert s.dumps(state) == before

@pytest.mark.parametrize("axis,end", [("horizontal", (10, 0)), ("vertical", (0, -10))])
def test_explicit_axis_line_is_one_atomic_command_with_recoverable_constraint(axis, end):
    state = empty()
    state.begin_line(d.PointSeed(0, 0))
    before = s.dumps(state)
    staged = p.prepare_point_input(state, d.PointSeed(*end), expected_phase=("line", "end"), axis=axis)
    accepted = staged.replacement(state)
    command = accepted.command_draft
    line = command.sketch["lines"][0]
    assert command.sketch["constraints"] == [{"id": staged.entity_ids[-1], "kind": axis, "refs": [line["id"]]}]
    assert len(command.checkpoint_payload()["journal"]["entries"]) == 1
    restored = p._restore(p._dumps(accepted), accepted.document_json)
    assert restored.command_draft.sketch == command.sketch
    command = restored.command_draft
    accepted_sketch = command.sketch
    command.undo()
    assert not command.sketch["points"] and not command.sketch["constraints"]
    command.redo()
    assert command.sketch == accepted_sketch
    assert s.dumps(state) == before


def test_axis_intent_rejected_outside_line_endpoint_without_mutation():
    state = empty()
    before = s.dumps(state)
    with pytest.raises(d.DraftError, match="Line or Arc point input phase"):
        p.prepare_point_input(state, d.PointSeed(0, 0), axis="horizontal")
    assert s.dumps(state) == before
    state.begin_line(d.PointSeed(0, 0))
    before = s.dumps(state)
    with pytest.raises(d.DraftError, match="Invalid line axis"):
        p.prepare_point_input(state, d.PointSeed(10, 0), axis="diagonal")
    assert s.dumps(state) == before


def test_axis_projection_is_local_and_off_axis_existing_points_are_rejected():
    axis_module = importlib.import_module(PACKAGE + ".line_axis")
    assert axis_module.project_axis((4, 7), (12, 9)) == ("horizontal", (12, 7))
    assert axis_module.project_axis((4, 7), (2, -9)) == ("vertical", (4, -9))
    assert axis_module.project_axis((0, 0), (-3, -3))[0] == "horizontal"
    with pytest.raises(d.DraftError, match="off axis"):
        axis_module.require_axis((4, 7), (12, 9), "horizontal")
    axis_module.require_axis((4, 7), (12, 7), "horizontal")


def test_legacy_free_line_record_remains_unchanged_and_reloadable():
    state = p.prepare_proposal(line()).replacement(line())
    payload = state.command_draft.checkpoint_payload()
    record = payload["journal"]["entries"][0]["command"]
    assert record["op"] == "add" and record["constraints"] == []
    restored = p._restore(p._dumps(state), state.document_json)
    expected = restored.command_draft.sketch
    restored.command_draft.undo()
    assert not restored.command_draft.sketch["lines"]
    restored.command_draft.redo()
    assert restored.command_draft.sketch == expected

@pytest.mark.parametrize("mutate", [
    lambda c: c["constraints"][0].update(kind="distance", value=10),
    lambda c: c["constraints"][0].update(refs=[c["points"][0]["id"]]),
    lambda c: c["points"].append({"id": "unrelated", "u": 8, "v": 9}),
])
def test_axis_journal_rejects_unrelated_compound_records(mutate):
    import copy

    commands = importlib.import_module(PACKAGE + ".general_sketch_commands")
    state = empty()
    state.begin_line(d.PointSeed(0, 0))
    accepted = p.prepare_point_input(state, d.PointSeed(10, 0), axis="horizontal").replacement(state)
    entry = accepted.command_draft.checkpoint_payload()["journal"]["entries"][0]
    record = copy.deepcopy(entry["command"])
    mutate(record)
    with pytest.raises(d.DraftError):
        commands._apply_record(entry["before"], record)
