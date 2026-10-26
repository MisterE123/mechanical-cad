"""Gate B pure envelope dispatch and exact, phase-aware point-input transactions."""

import copy
import importlib
import json
import math
import subprocess
import sys
import types
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "mcad_arc_dispatch_proposals_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
sys.modules[PACKAGE] = package
dispatch = importlib.import_module(PACKAGE + ".draft_dispatch")
a = importlib.import_module(PACKAGE + ".general_authoring")
d = importlib.import_module(PACKAGE + ".general_sketch_draft")
p = importlib.import_module(PACKAGE + ".general_proposals")
s = importlib.import_module(PACKAGE + ".general_arc_authoring_store")
layout = importlib.import_module(PACKAGE + ".sketch_annotation_store")
BASE = '{ "schema_version":1, "id":"Part_arc", "name":"Part 🛠", "units":"mm", "parameters":{}, "features":[], "active_feature":null } \n\t'


def empty(*, capable=True):
    state = a.GeneralSketchAuthoringState(d.GeneralSketchDraft(BASE))
    return state.promote_arc_capability() if capable else state


def arc():
    state = empty()
    ids = state.command_draft.execute(
        d.AddArc(d.PointSeed(-0.0, 0), d.PointSeed(5, 0), d.PointSeed(0, 7.0), "ccw")
    ).entity_ids
    return state, ids


def pick(state, point, **kwargs):
    return p.prepare_point_input(state, point, **kwargs).replacement(state)


@pytest.mark.parametrize("phase", ["empty", "center", "start", "end", "accepted", "undone"])
def test_explicit_dispatch_and_clone_retain_capability_without_saved_authority(phase):
    state = empty()
    if phase != "empty":
        state.select_tool("Arc")
    if phase in {"start", "end", "accepted", "undone"}:
        state.begin_arc(d.PointSeed(-0.0, 0))
    if phase in {"end", "accepted", "undone"}:
        state.choose_arc_start(d.PointSeed(5, 0))
        state.observe_arc(d.PointSeed(0, 7.0))
    if phase in {"accepted", "undone"}:
        state = p.prepare_proposal(state).replacement(state)
    if phase == "undone":
        state.command_draft.undo()
    raw = dispatch.dumps(state)
    assert raw == s.dumps(state)
    info = dispatch.inspect(raw)
    assert info.kind == dispatch.GENERAL and info.schema_version == 3
    assert info.document_json == BASE and info.phase == "EDITING"
    cloned = dispatch.clone(state)
    assert cloned is not state and cloned.command_draft is not state.command_draft
    assert dispatch.dumps(cloned) == raw
    assert cloned.ui_version == 2 and cloned.command_draft.journal_version == 3
    assert cloned.command_draft.has_current_solution is False
    assert cloned.command_draft.has_verified_trial is False
    assert cloned.proposal == state.proposal
    assert not any("capture" in key or "evidence" in key for key in json.loads(raw))
    if phase == "undone":
        assert cloned.command_draft.sketch["schema_version"] == 2
        assert "arcs" not in cloned.command_draft.sketch
        cloned.command_draft.redo()
        assert cloned.command_draft.sketch["arcs"]
        assert state.command_draft.sketch["schema_version"] == 2
    with pytest.raises(dispatch.SnapshotError):
        dispatch.dumps(state.command_draft)  # There is no journal3 envelope1 route.
    with pytest.raises(dispatch.SnapshotError):
        dispatch.restore(raw, BASE.rstrip())
    assert dispatch.dumps(state) == raw


def test_dispatch_preserves_every_frozen_legacy_envelope_and_base_byte():
    frozen = json.loads(
        (ROOT / "tests/fixtures/arc_authoring/legacy_codec_ce5b50b.json").read_text()
    )
    assert len(frozen["cases"]) == 39
    for name, case in frozen["cases"].items():
        keys = ("envelope_v1", "envelope_v2") if case["kind"] == "general" else ("envelope_v1",)
        for key in keys:
            raw = case[key]
            info = dispatch.inspect(raw)
            assert info.document_json == case["base_json"], (name, key)
            restored = dispatch.restore(raw, case["base_json"])
            assert dispatch.dumps(restored) == raw, (name, key)
            assert dispatch.dumps(dispatch.clone(restored)) == raw, (name, key)


@pytest.mark.parametrize("ui,journal", [(1, 3), (2, 2), (True, 3), (2, 3.0), (2, "3")])
def test_envelope3_mismatched_ui_journal_pairs_reject_without_rewrite(ui, journal):
    raw = json.loads(dispatch.dumps(empty()))
    raw["ui"]["schema_version"] = ui
    raw["draft"]["journal"]["schema_version"] = journal
    encoded = json.dumps(raw)
    for action in (dispatch.inspect, lambda text: dispatch.restore(text, BASE)):
        with pytest.raises(dispatch.SnapshotError):
            action(encoded)
    assert json.loads(encoded) == raw


@pytest.mark.parametrize("direction", ["ccw", "cw"])
@pytest.mark.parametrize("existing", [(), (0, 1, 2), (0,), (1,), (2,), (0, 2)])
def test_arc_acceptance_is_one_command_plus_clear_with_exact_raw_refs_and_seeds(
    direction, existing
):
    state = empty()
    coordinates = ((-0.0, 0), (5, 0), (0, 7.0))
    inputs = []
    for role, xy in enumerate(coordinates):
        if role in existing:
            point_id = state.command_draft.execute(d.AddPoint(d.PointSeed(*xy))).entity_ids[0]
            inputs.append(d.PointRef(point_id))
        else:
            inputs.append(d.PointSeed(*xy))
    state.begin_arc(inputs[0], direction=direction)
    state.choose_arc_start(inputs[1])
    state.observe_arc(inputs[2])
    before = dispatch.dumps(state)
    prior = state.command_draft.checkpoint_payload()
    staged = p.prepare_proposal(state)
    accepted = staged.replacement(state)
    assert dispatch.dumps(state) == before
    assert accepted.revision == state.revision + 1
    assert accepted.ui_revision == state.ui_revision + 1
    assert accepted.proposal is None and accepted.tool == "Arc"
    assert accepted.command_draft.sketch["schema_version"] == 3
    assert accepted.command_draft.sketch["constraints"] == []
    assert (
        len(accepted.command_draft.checkpoint_payload()["journal"]["entries"])
        == len(prior["journal"]["entries"]) + 1
    )
    record = accepted.command_draft.sketch["arcs"][0]
    points = {item["id"]: item for item in accepted.command_draft.sketch["points"]}
    assert record["direction"] == direction
    for index, role in enumerate(("center", "start", "end")):
        point = points[record[role]]
        assert (point["u"], point["v"]) == coordinates[index]
        if index in existing:
            assert record[role] == inputs[index].id
    assert math.copysign(1, points[record["center"]]["u"]) == -1
    assert type(points[record["end"]]["v"]) is float
    # End radius 7 stays authored 7, even though start radius is 5.
    assert points[record["end"]]["v"] == 7.0
    assert not accepted.command_draft.has_current_solution
    assert len(staged.entity_ids) == 4 - len(existing)
    accepted.command_draft.undo()
    assert accepted.command_draft.sketch == prior["accepted_sketch"]
    accepted.command_draft.redo()
    assert accepted.command_draft.sketch["arcs"][0] == record


@pytest.mark.parametrize("capable", [False, True])
def test_initial_and_terminal_line_point_inputs_preserve_duplicate_position_id(capable):
    state = empty(capable=capable)
    ids = [
        state.command_draft.execute(d.AddPoint(d.PointSeed(*xy))).entity_ids[0]
        for xy in ((0, 0), (0, 0), (5, 0))
    ]
    state.select_tool("Line")
    before = state.command_draft.checkpoint_payload()
    initial = p.prepare_point_input(state, d.PointRef(ids[1]), expected_phase=("line", "start"))
    assert initial.entity_ids == ()
    current = initial.replacement(state)
    assert current.command_draft.checkpoint_payload() == before
    assert current.proposal["anchor"] == {"kind": "existing", "point_id": ids[1]}
    assert initial.point_input.point == d.PointRef(ids[1])
    final = p.prepare_point_input(current, d.PointRef(ids[2]), expected_phase=("line", "end"))
    accepted = final.replacement(current)
    assert len(accepted.command_draft.sketch["points"]) == 3
    assert accepted.command_draft.sketch["lines"][-1]["start"] == ids[1]
    assert accepted.command_draft.sketch["lines"][-1]["end"] == ids[2]
    assert len(final.entity_ids) == 1
    assert accepted.proposal is None
    assert json.loads(dispatch.dumps(accepted))["schema_version"] == (3 if capable else 2)
    for prepared, newer in ((initial, current), (final, accepted)):
        with pytest.raises(d.DraftError, match="changed"):
            prepared.replacement(newer)


def test_arc_point_input_all_three_phases_do_not_allocate_until_terminal_acceptance():
    state = empty()
    state.select_tool("Arc")
    original = state.command_draft.checkpoint_payload()
    for phase, xy in (("center", (-0.0, 0)), ("start", (5, 0))):
        before = dispatch.dumps(state)
        staged = p.prepare_point_input(state, d.PointSeed(*xy), expected_phase=("arc", phase))
        assert staged.entity_ids == ()
        assert dispatch.dumps(state) == before
        state = staged.replacement(state)
        assert state.command_draft.checkpoint_payload() == original
    final = p.prepare_point_input(state, d.PointSeed(0, 7.0), expected_phase=("arc", "end"))
    accepted = final.replacement(state)
    assert len(final.entity_ids) == 4
    assert accepted.revision == state.revision + 1
    assert accepted.ui_revision == state.ui_revision + 1
    assert len(accepted.command_draft.checkpoint_payload()["journal"]["entries"]) == 1
    assert accepted.command_draft.sketch["points"][-1]["v"] == 7.0
    assert accepted.proposal is None


def test_exact_arc_source_roles_form_shared_id_radial_lines_without_cursor_or_constraints():
    state, (center, start, end, arc_id) = arc()
    original_points = state.command_draft.sketch["points"]
    for first, second, first_role, second_role in (
        (center, start, "center", "start"),
        (end, center, "end", "center"),
    ):
        state.select_tool("Line")
        for phase, point_id, role in (("start", first, first_role), ("end", second, second_role)):
            prepared = p.prepare_point_input(
                state,
                d.PointRef(point_id),
                expected_phase=("line", phase),
                source_kind="arc",
                source_id=arc_id,
                role=role,
            )
            binding = prepared.point_input
            assert (binding.phase, binding.source_kind, binding.source_id, binding.role) == (
                ("line", phase),
                "arc",
                arc_id,
                role,
            )
            with pytest.raises(FrozenInstanceError):
                binding.role = "other"
            state = prepared.replacement(state)
    sketch = state.command_draft.sketch
    assert [(item["start"], item["end"]) for item in sketch["lines"]] == [
        (center, start),
        (end, center),
    ]
    assert sketch["points"] == original_points
    assert sketch["constraints"] == [] and len(sketch["arcs"]) == 1
    assert state.proposal is None
    assert not state.command_draft.has_current_solution


def test_arc_initial_start_end_existing_point_source_binding_is_exact():
    state = empty()
    center = state.command_draft.execute(d.AddPoint(d.PointSeed(0, 0))).entity_ids[0]
    start, end, line = state.command_draft.execute(
        d.AddLine(d.PointSeed(5, 0), d.PointSeed(0, 7))
    ).entity_ids
    state.select_tool("Arc")
    original_points = state.command_draft.sketch["points"]
    state = pick(state, d.PointRef(center), expected_phase=("arc", "center"))
    for phase, point_id in (("start", start), ("end", end)):
        state = pick(
            state,
            d.PointRef(point_id),
            expected_phase=("arc", phase),
            source_kind="line",
            source_id=line,
            role=phase,
        )
    assert state.command_draft.sketch["arcs"] == [
        {
            "id": state.command_draft.sketch["arcs"][0]["id"],
            "center": center,
            "start": start,
            "end": end,
            "direction": "ccw",
        }
    ]
    assert state.command_draft.sketch["points"] == original_points


@pytest.mark.parametrize("phase", ["initial", "later"])
@pytest.mark.parametrize(
    "metadata",
    [
        {"source_kind": "line", "role": "center"},
        {"source_kind": "circle", "role": "center"},
        {"source_kind": "arc", "role": "start"},
        {"source_kind": "arc", "role": "Center"},
        {"source_kind": "arc", "role": None},
        {"source_kind": None, "role": "center"},
    ],
)
def test_wrong_or_partial_curve_source_roles_reject_before_any_intent_change(phase, metadata):
    state, (center, start, _end, arc_id) = arc()
    state.select_tool("Line")
    if phase == "later":
        state.begin_line(d.PointRef(start))
    before = dispatch.dumps(state)
    with pytest.raises(d.DraftError):
        p.prepare_point_input(state, d.PointRef(center), source_id=arc_id, **metadata)
    assert dispatch.dumps(state) == before


@pytest.mark.parametrize("change", ["command", "tool", "phase", "observation", "source_deleted"])
def test_prepared_point_binding_rejects_stale_source_and_phase_without_mutating_it(change):
    state, (center, start, _end, arc_id) = arc()
    state.begin_line(d.PointRef(start))
    prepared = p.prepare_point_input(
        state, d.PointRef(center), source_kind="arc", source_id=arc_id, role="center"
    )
    if change == "command":
        state.command_draft.execute(d.AddPoint(d.PointSeed(10, 20)))
    elif change == "tool":
        state.select_tool("Select")
    elif change == "phase":
        state.cancel_proposal()
    elif change == "observation":
        state.update_line((10, 20))
    else:
        state.command_draft.execute(
            d.DeleteBatch(state.command_draft.preview_delete((("arc", arc_id),)))
        )
    before = dispatch.dumps(state)
    with pytest.raises(d.DraftError, match="changed"):
        prepared.replacement(state)
    assert dispatch.dumps(state) == before


@pytest.mark.parametrize(
    "kind,phase",
    [("Line", ("arc", "center")), ("Arc", ("line", "start")), ("Select", None), ("Circle", None)],
)
def test_no_implicit_point_phase_or_stale_phase_acceptance(kind, phase):
    state = empty()
    state.select_tool(kind)
    before = dispatch.dumps(state)
    with pytest.raises(d.DraftError):
        p.prepare_point_input(state, d.PointSeed(0, 0), expected_phase=phase)
    assert dispatch.dumps(state) == before


@pytest.mark.parametrize(
    "endpoint", [None, d.PointSeed(0, 0), d.PointSeed(5, 0), d.PointSeed(float("nan"), 2), "p_d1"]
)
def test_failed_arc_final_acceptance_retains_original_observation_and_allocation(endpoint):
    state = empty()
    state.begin_arc(d.PointSeed(0, 0))
    state.choose_arc_start(d.PointSeed(5, 0))
    before = dispatch.dumps(state)
    with pytest.raises(d.DraftError):
        p.prepare_proposal(state, endpoint=endpoint)
    assert dispatch.dumps(state) == before


def test_repeated_existing_arc_role_observation_survives_failed_acceptance_and_resume():
    state = empty()
    center, start = [
        state.command_draft.execute(d.AddPoint(d.PointSeed(*xy))).entity_ids[0]
        for xy in ((0, 0), (5, 0))
    ]
    state.begin_arc(d.PointRef(center))
    state.choose_arc_start(d.PointRef(start))
    state.observe_arc(d.PointRef(start))
    before = dispatch.dumps(state)
    with pytest.raises(d.DraftError):
        p.prepare_proposal(state)
    resumed = dispatch.restore(before, BASE)
    assert resumed.proposal["observation"] == {"kind": "existing", "point_id": start}
    assert dispatch.dumps(resumed) == before
    assert not resumed.command_draft.has_current_solution


def test_new_seed_cannot_claim_existing_source_metadata():
    state, (_, _, _, arc_id) = arc()
    state.select_tool("Line")
    before = dispatch.dumps(state)
    with pytest.raises(d.DraftError):
        p.prepare_point_input(
            state, d.PointSeed(0, 0), source_kind="arc", source_id=arc_id, role="center"
        )
    assert dispatch.dumps(state) == before


def test_arc_final_envelope_failure_preserves_live_proposal_and_counter():
    state = empty()
    state.begin_arc(d.PointSeed(0, 0))
    state.choose_arc_start(d.PointSeed(5, 0))
    state.observe_arc(d.PointSeed(0, 7))
    before = dispatch.dumps(state)
    real = s.dumps

    def reject_final(value):
        if value is not state:
            raise s.SnapshotError("Injected combined arc envelope limit")
        return real(value)

    with patch.object(s, "dumps", side_effect=reject_final):
        with pytest.raises(p.SnapshotError, match="envelope limit"):
            p.prepare_proposal(state)
    assert dispatch.dumps(state) == before


@pytest.mark.parametrize("counter", ["ui", "command", "allocator"])
def test_arc_final_counter_failure_leaves_proposal_and_history_exact(counter):
    state = empty()
    state.begin_arc(d.PointSeed(0, 0))
    state.choose_arc_start(d.PointSeed(5, 0))
    state.observe_arc(d.PointSeed(0, 7))
    payload = json.loads(dispatch.dumps(state))
    if counter == "ui":
        payload["ui"]["revision"] = 2**53 - 1
    else:
        payload["draft"]["revision" if counter == "command" else "next_id"] = 2**53 - 1
    state = dispatch.restore(json.dumps(payload), BASE)
    before = dispatch.dumps(state)
    with pytest.raises(d.DraftError):
        p.prepare_proposal(state)
    assert dispatch.dumps(state) == before


def arc_layout():
    state, (_center, _start, _end, curve) = arc()
    relation = state.command_draft.execute(
        d.AddRelation("radius", (curve,), value="5 + 0")
    ).constraint_id
    binding = {"kind": "radius", "refs": [curve], "display": "radius", "offset": [-0.0, 2.125]}
    raw = layout.replace_annotations("", "Part Ω", state.feature_id, {relation: binding})
    return state, relation, curve, binding, raw


def test_layout1_arc_lookup_and_reversal_keep_exact_fields_and_source_bytes():
    state, relation, curve, binding, raw = arc_layout()
    before = dispatch.dumps(state)
    lookup = layout.annotations_for(raw, "Part Ω", state.feature_id, state.command_draft.sketch)
    assert lookup.annotations == {relation: binding} and not lookup.unavailable
    assert layout.VERSION == 1 and json.loads(raw)["schema_version"] == 1
    assert set(lookup.annotations[relation]) == {"kind", "refs", "display", "offset"}
    assert (
        layout.replace_annotations(raw, "Part Ω", state.feature_id, lookup.all_annotations) == raw
    )
    assert dispatch.dumps(state) == before
    state.command_draft.execute(d.ReverseArcSweep(curve))
    reversed_lookup = layout.annotations_for(
        raw, "Part Ω", state.feature_id, state.command_draft.sketch
    )
    assert reversed_lookup.annotations == lookup.annotations
    assert raw == layout.replace_annotations(
        raw, "Part Ω", state.feature_id, reversed_lookup.all_annotations
    )


def test_layout_arc_deleted_restored_and_changed_constraint_remain_quarantined():
    state, relation, curve, binding, raw = arc_layout()
    sketch = state.command_draft.sketch
    missing = copy.deepcopy(sketch)
    missing["constraints"] = []
    result = layout.annotations_for(raw, "Part Ω", state.feature_id, missing)
    assert result.annotations == {} and result.unavailable[relation].state == "missing"
    changed = copy.deepcopy(missing)
    changed["arcs"][0]["id"] = relation
    result = layout.annotations_for(raw, "Part Ω", state.feature_id, changed)
    assert result.annotations == {} and result.unavailable[relation].state == "changed"
    assert result.all_annotations == {relation: binding}
    assert layout.annotations_for(raw, "Part Ω", state.feature_id, sketch).annotations == {
        relation: binding
    }
    wrong_target = copy.deepcopy(sketch)
    wrong_target["constraints"][0]["refs"] = [sketch["points"][0]["id"]]
    with pytest.raises(layout.AnnotationStoreError):
        layout.annotations_for(raw, "Part Ω", state.feature_id, wrong_target)
    assert json.loads(raw)["documents"]["Part Ω"][state.feature_id] == {relation: binding}


@pytest.mark.parametrize("version", [True, 3.0, "3", 4, None])
def test_layout_does_not_infer_schema3_from_arc_fields(version):
    state, _, _, _, raw = arc_layout()
    sketch = state.command_draft.sketch
    sketch["schema_version"] = version
    with pytest.raises(layout.AnnotationStoreError):
        layout.annotations_for(raw, "Part Ω", state.feature_id, sketch)


def test_dispatch_proposal_layout_imports_are_native_and_blender_free():
    script = f"""import importlib, sys, types
p = types.ModuleType("isolated_arc_dispatch")
p.__path__ = [{str(ROOT / "blender_addon/mechanical_cad_blender")!r}]
sys.modules[p.__name__] = p
for name in ("draft_dispatch", "general_proposals", "sketch_annotation_store"):
    importlib.import_module(p.__name__ + "." + name)
assert not any(name == "bpy" or name.startswith(("OCP", "slvs", "mechanical_cad.")) or name.endswith((".sidecar_job", ".service_v3")) for name in sys.modules)
"""
    subprocess.run([sys.executable, "-S", "-c", script], check=True, capture_output=True, text=True)


@pytest.mark.parametrize("unsupported", ["second_arc", "mixed_circle", "three_lines", "third_line"])
def test_general_graph_proposals_are_detached_atomic_candidates(unsupported):
    if unsupported in {"second_arc", "third_line"}:
        state, (center, start, end, _curve) = arc()
    else:
        state = empty()
    if unsupported == "mixed_circle":
        state.command_draft.execute(d.AddCircle(d.PointSeed(20, 20), 2))
    elif unsupported == "three_lines":
        for y in range(3):
            state.command_draft.execute(d.AddLine(d.PointSeed(20, y), d.PointSeed(21, y)))
    elif unsupported == "third_line":
        state.command_draft.execute(d.AddLine(d.PointRef(center), d.PointRef(start)))
        state.command_draft.execute(d.AddLine(d.PointRef(end), d.PointRef(center)))
    if unsupported == "third_line":
        state.begin_line(d.PointSeed(20, 20), (21, 21))
    else:
        state.begin_arc(d.PointSeed(20, 20))
        state.choose_arc_start(d.PointSeed(25, 20))
        state.observe_arc(d.PointSeed(20, 25))
    before = dispatch.dumps(state)
    candidate = p.prepare_proposal(state).replacement(state)
    assert dispatch.dumps(state) == before
    assert state.proposal is not None
    assert candidate.proposal is None
    assert candidate.revision == state.revision + 1
    assert (
        len(candidate.command_draft.sketch["lines"]) + len(candidate.command_draft.sketch["arcs"])
        == len(state.command_draft.sketch["lines"])
        + len(state.command_draft.sketch.get("arcs", []))
        + 1
    )


@pytest.mark.parametrize("phase", ["line_start", "line_end", "arc_start", "arc_end"])
def test_point_input_does_not_bypass_pending_raw_driver_barrier(phase):
    state = empty()
    p0, p1, _line = state.command_draft.execute(
        d.AddLine(d.PointSeed(0, 0), d.PointSeed(5, 0))
    ).entity_ids
    relation = state.command_draft.execute(
        d.AddRelation("distance", (p0, p1), value=5)
    ).constraint_id
    state.select_tool("Line" if phase.startswith("line") else "Arc")
    if phase == "line_end":
        state.begin_line(d.PointRef(p1))
    elif phase.startswith("arc"):
        state.begin_arc(d.PointRef(p0))
        if phase == "arc_end":
            state.choose_arc_start(d.PointRef(p1))
    state.command_draft.begin_edit(relation)
    state.command_draft.update_edit(" \tbad radius + ( Ω\n")
    before = dispatch.dumps(state)
    with pytest.raises(d.DraftError, match="Accept or cancel"):
        p.prepare_point_input(state, d.PointSeed(0, 7))
    assert dispatch.dumps(state) == before


def test_arc_start_repeated_existing_center_rejects_without_allocating_or_advancing_phase():
    state = empty()
    center = state.command_draft.execute(d.AddPoint(d.PointSeed(0, 0))).entity_ids[0]
    state.begin_arc(d.PointRef(center))
    before = dispatch.dumps(state)
    with pytest.raises(d.DraftError, match="distinct"):
        p.prepare_point_input(state, d.PointRef(center), expected_phase=("arc", "start"))
    assert dispatch.dumps(state) == before
    assert state.point_input_phase == ("arc", "start")

@pytest.mark.parametrize("axis,end", [("horizontal", (10, 0)), ("vertical", (0, 10))])
def test_axis_line_roundtrip_in_arc_capable_journal(axis, end):
    state = empty()
    state.select_tool("Line")
    state.begin_line(d.PointSeed(0, 0))
    state = pick(state, d.PointSeed(*end), axis=axis)
    restored = dispatch.restore(dispatch.dumps(state), state.document_json)
    command = restored.command_draft
    assert command.journal_version == 3
    expected = command.sketch
    assert expected["constraints"][0]["kind"] == axis
    command.undo()
    assert not command.sketch["lines"] and not command.sketch["constraints"]
    command.redo()
    assert command.sketch == expected
