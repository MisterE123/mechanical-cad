"""Native-free generalized arc intent and exact journal capability gates."""

import copy
import importlib
import json
import subprocess
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "mcad_general_arc_command_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
sys.modules[PACKAGE] = package
d = importlib.import_module(PACKAGE + ".general_sketch_draft")
c = importlib.import_module(PACKAGE + ".general_sketch_commands")
j = importlib.import_module(PACKAGE + ".general_sketch_journal")
store = importlib.import_module(PACKAGE + ".general_draft_store")


def source_draft(schema=2, *, points=(), journal_version=3, extras=()):
    sketch = {
        "schema_version": schema,
        "id": "geometry",
        "units": "mm",
        "plane": {"id": "xy", "origin": [0, 0, 0], "quaternion": [1, 0, 0, 0]},
        "points": copy.deepcopy(list(points)),
        "lines": [],
        "constraints": [],
    }
    if schema >= 2:
        sketch["circles"] = []
    if schema == 3:
        sketch["arcs"] = []
    document = {
        "schema_version": 2,
        "id": "part",
        "name": "Untouched Part",
        "units": "mm",
        "parameters": {"radius": 5, "formula": "radius + 0.125"},
        "features": [
            {
                "id": "sketch",
                "kind": "sketch_constrained",
                "label": "Raw sketch",
                "params": {},
                "inputs": {},
                "sketch": sketch,
            },
            *copy.deepcopy(extras),
        ],
        "active_feature": "sketch",
    }
    return d.GeneralSketchDraft(
        json.dumps(document, indent=3) + "\n", "sketch", True, journal_version=journal_version
    )


def add_arc(draft, direction="ccw"):
    return draft.execute(
        d.AddArc(d.PointSeed(-0.0, 0), d.PointSeed(5, 0.0), d.PointSeed(0, 7), direction)
    ).entity_ids[-1]


def restore(draft):
    return d.GeneralSketchDraft.from_checkpoint_payload(
        draft.checkpoint_payload(), expected_journal_version=3
    )


def exact(draft):
    return d._json(draft.checkpoint_payload())


@pytest.mark.parametrize("schema", [1, 2, 3])
@pytest.mark.parametrize("direction", ["ccw", "cw"])
@pytest.mark.parametrize("mode", ["new", "existing", "mixed"])
def test_add_arc_is_one_raw_seed_migration_with_role_order_and_exact_undo(schema, direction, mode):
    seeds = [(-0.0, 0), (5, 0.0), (0, 7)]
    existing = set(range(3)) if mode == "existing" else {0, 2} if mode == "mixed" else set()
    points = [{"id": f"original{n}", "u": seeds[n][0], "v": seeds[n][1]} for n in existing]
    draft = source_draft(schema, points=points)
    original, raw = draft.sketch, draft.document_json
    inputs = [
        d.PointRef(f"original{n}") if n in existing else d.PointSeed(*seeds[n]) for n in range(3)
    ]
    result = draft.execute(d.AddArc(*inputs, direction))
    command = draft.checkpoint_payload()["journal"]["entries"][0]["command"]
    assert set(command) == {"op", "points", "arc", "source_schema_version"}
    assert command["op"] == "add_arc" and command["source_schema_version"] == schema
    assert [(p["u"], p["v"]) for p in command["points"]] == [
        seeds[n] for n in range(3) if n not in existing
    ]
    assert [p["id"] for p in command["points"]] == list(result.entity_ids[:-1])
    assert result.entity_ids[-1] == f"a_d{4 - len(existing)}"
    assert command["arc"] == {
        "id": result.entity_ids[-1],
        **{
            role: f"original{n}"
            if n in existing
            else command["points"][sum(k not in existing for k in range(n))]["id"]
            for n, role in enumerate(("center", "start", "end"))
        },
        "direction": direction,
    }
    assert draft.sketch["schema_version"] == 3
    assert draft.document_json == raw
    assert draft.sketch["points"][: len(points)] == points
    assert not draft.sketch["constraints"] and not draft.sketch["circles"]
    end = next(point for point in draft.sketch["points"] if point["id"] == command["arc"]["end"])
    assert end["v"] == 7  # Never projected to start radius 5, including an existing endpoint.
    actual_positions = {point["id"]: (point["u"], point["v"]) for point in draft.sketch["points"]}
    assert d._json(
        [actual_positions[command["arc"][role]] for role in ("center", "start", "end")]
    ) == d._json(seeds)
    accepted = d._json(draft.sketch)
    clone = restore(draft)
    assert exact(clone) == exact(draft)
    clone.undo()
    assert d._json(clone.sketch) == d._json(original)
    assert clone.journal_version == 3
    clone.redo()
    assert d._json(clone.sketch) == accepted


def test_explicit_promotion_preserves_base_redo_pending_and_all_legacy_records():
    old = source_draft(1, journal_version=2)
    center, endpoint, line = old.execute(
        d.AddLine(d.PointSeed(-0.0, 0), d.PointSeed(5, 0))
    ).entity_ids
    distance = old.execute(
        d.AddRelation("distance", (center, endpoint), value="radius + 0")
    ).constraint_id
    old.execute(d.AddPoint(d.PointSeed(9, 2)))
    old.undo()
    old.begin_edit(distance)
    old.update_edit(" invalid + (  ")
    before = old.checkpoint_payload()
    old_bytes = store.dumps(old)
    promoted = old.promote_arc_capability()
    expected = copy.deepcopy(before)
    expected["journal"]["schema_version"] = 3
    assert promoted.checkpoint_payload() == expected
    assert store.dumps(old) == old_bytes
    assert promoted.pending_edit.raw_text == " invalid + (  "
    assert promoted.sketch["lines"][0]["id"] == line
    assert promoted.sketch["schema_version"] == 1 and "arcs" not in promoted.sketch
    assert not promoted.has_current_solution and not promoted.has_verified_trial
    assert promoted.promote_arc_capability() is not promoted
    assert exact(promoted.promote_arc_capability()) == exact(promoted)
    with pytest.raises(AttributeError):
        promoted.journal_version = 2
    with pytest.raises(store.SnapshotError, match="journal version"):
        store.dumps(promoted)


@pytest.mark.parametrize("version", [None, True, False, 2.0, 3.0, "3", 0, 1, 4])
def test_journal_capability_is_an_exact_known_integer(version):
    with pytest.raises(d.DraftError, match="journal version"):
        source_draft(journal_version=version)
    with pytest.raises(d.DraftError, match="journal version"):
        d.GeneralSketchDraft.from_checkpoint_payload(
            source_draft().checkpoint_payload(), expected_journal_version=version
        )


def test_legacy_constructor_restoration_reducer_and_writer_stay_closed():
    capable = source_draft(3)
    for draft in (capable, source_draft().promote_arc_capability()):
        state = draft.checkpoint_payload()
        with pytest.raises(d.DraftError, match="journal version"):
            d.GeneralSketchDraft.from_checkpoint_payload(state)
        with pytest.raises(store.SnapshotError):
            store.dumps(draft)
    with pytest.raises(d.DraftError, match="journal 3"):
        d.GeneralSketchDraft(capable.document_json, capable.feature_id, True)
    old = source_draft(journal_version=2)
    before = exact(old)
    with pytest.raises(d.DraftError, match="journal 3"):
        add_arc(old)
    assert exact(old) == before
    add_arc(capable)
    command = capable.checkpoint_payload()["journal"]["entries"][0]["command"]
    with pytest.raises(d.DraftError):
        c._apply_record(source_draft().sketch, command)


def test_reverse_changes_only_direction_without_reseeding_roles_or_relations():
    draft = source_draft()
    arc_id = add_arc(draft)
    radius = draft.execute(d.AddRelation("radius", (arc_id,), value="radius + 0.125")).constraint_id
    before = draft.sketch
    ids, next_id = draft._allocated_ids.copy(), draft._next_id
    draft.execute(d.ReverseArcSweep(arc_id))
    expected = copy.deepcopy(before)
    expected["arcs"][0]["direction"] = "cw"
    assert d._json(draft.sketch) == d._json(expected)
    assert draft._allocated_ids == ids and draft._next_id == next_id
    assert draft.sketch["constraints"][0]["id"] == radius
    assert draft.checkpoint_payload()["journal"]["entries"][-1]["command"] == {
        "op": "reverse_arc",
        "arc_id": arc_id,
        "from_direction": "ccw",
        "to_direction": "cw",
    }
    draft.execute(d.ReverseArcSweep(arc_id))
    assert d._json(draft.sketch) == d._json(before)
    clone = restore(draft)
    clone.undo()
    assert d._json(clone.sketch) == d._json(expected)
    clone.redo()
    assert d._json(clone.sketch) == d._json(before)


@pytest.mark.parametrize("target", ["arc", "center", "start", "end", "constraint"])
def test_delete_v3_discloses_complete_cascade_and_preserves_unselected_shared_geometry(target):
    draft = source_draft()
    arc_id = add_arc(draft)
    arc = draft.sketch["arcs"][0]
    first = draft.execute(
        d.AddLine(d.PointRef(arc["center"]), d.PointRef(arc["start"]))
    ).entity_ids[0]
    second = draft.execute(d.AddLine(d.PointRef(arc["end"]), d.PointRef(arc["center"]))).entity_ids[
        0
    ]
    radius = draft.execute(d.AddRelation("radius", (arc_id,), value="radius")).constraint_id
    kind, identifier = (
        ("arc", arc_id)
        if target == "arc"
        else ("constraint", radius)
        if target == "constraint"
        else ("point", arc[target])
    )
    plan = draft.preview_delete(((kind, identifier),))
    assert plan.constraints == (radius,)
    assert plan.arcs == (() if target == "constraint" else (arc_id,))
    assert plan.lines == tuple(
        sorted({"center": [first, second], "start": [first], "end": [second]}.get(target, []))
    )
    before = draft.sketch
    seeds = {"points": copy.deepcopy(before["points"]), "circles": []}
    state = exact(draft)
    with pytest.raises(d.DraftError, match="Check the current"):
        draft.execute(d.DeleteBatch(plan))
    assert exact(draft) == state
    prepared = c.prepare_command(
        draft.sketch,
        d.DeleteBatch(plan),
        draft.revision,
        draft._allocated_ids,
        draft._next_id,
        journal_version=3,
        release_seeds=seeds,
    )
    assert prepared.record["op"] == "delete_v3"
    assert set(prepared.record["removed"]) == {"points", "lines", "circles", "arcs", "constraints"}
    draft._commit(prepared.record)
    assert len(draft.sketch["points"]) == 3 - bool(plan.points)
    assert [line["id"] for line in draft.sketch["lines"]] == [
        line for line in (first, second) if line not in plan.lines
    ]
    if target == "constraint":
        assert draft.sketch["arcs"] == before["arcs"]
    else:
        assert not draft.sketch["arcs"]
    restored = restore(draft)
    restored.undo()
    assert d._json(restored.sketch) == d._json(before)
    restored.redo()
    assert d._json(restored.sketch) == d._json(draft.sketch)


def test_recover_radius_removes_one_relation_with_authored_points_and_no_arc_radius_seed():
    draft = source_draft()
    arc_id = add_arc(draft)
    radius = draft.execute(d.AddRelation("radius", (arc_id,), value="radius")).constraint_id
    before = draft.sketch
    draft.execute(d.RecoverRemoveRelation(draft.preview_delete((("constraint", radius),))))
    assert draft.sketch["points"] == before["points"]
    assert draft.sketch["arcs"] == before["arcs"]
    assert not draft.sketch["constraints"]
    command = draft.checkpoint_payload()["journal"]["entries"][-1]["command"]
    assert command["op"] == "delete_v3"
    assert command["seeds"] == {"points": before["points"], "circles": []}
    assert exact(restore(draft)) == exact(draft)


def test_imported_arc_prefix_collision_and_branch_tombstones_never_recycle():
    imported = {"id": "a_d4", "u": 44, "v": 55}
    draft = source_draft(points=[imported])
    arc_id = add_arc(draft)
    assert arc_id == "a_d5" and draft.sketch["points"][0] == imported
    used = draft._allocated_ids.copy()
    draft.undo()
    replacement = add_arc(draft, "cw")
    assert replacement == "a_d9"
    assert used <= draft._allocated_ids
    assert exact(restore(draft)) == exact(draft)
    draft.execute(d.DeleteBatch(draft.preview_delete((("arc", replacement),))))
    points = draft.sketch["points"][-3:]
    new_id = draft.execute(
        d.AddArc(*(d.PointRef(point["id"]) for point in points), "ccw")
    ).entity_ids[0]
    assert new_id == "a_d10" and not {arc_id, replacement} & {new_id}
    assert exact(restore(draft)) == exact(draft)


def test_pruned_arc_anchor_retains_allocation_and_bounded_history():
    draft = source_draft(1)
    arc_id = add_arc(draft)
    for _ in range(70):
        draft.execute(d.ReverseArcSweep(arc_id))
    state = draft.checkpoint_payload()
    assert len(state["journal"]["entries"]) == 64
    assert state["journal"]["anchor_sequence"] == 7
    assert state["journal"]["anchor"]["schema_version"] == 3
    assert state["journal"]["anchor_next_id"] == 5
    assert state["next_id"] == 5
    restored = restore(draft)
    assert exact(restored) == exact(draft)
    for _ in range(64):
        restored.undo()
    assert not restored.can_undo
    assert restored._allocated_ids == draft._allocated_ids
    restored.execute(d.AddPoint(d.PointSeed(8, 9)))
    assert restored.sketch["points"][-1]["id"] == "p_d5"
    assert exact(restore(restored)) == exact(restored)


def test_mixed_journal_keeps_old_add_driver_fixed_and_delete_shapes_exact():
    draft = source_draft(1, journal_version=2)
    point = draft.execute(d.AddPoint(d.PointSeed(-0.0, 2))).entity_ids[0]
    fixed = draft.execute(d.AddRelation("fixed", (point,), target=(0, 2))).constraint_id
    draft.execute(d.EditFixedTarget(fixed, (0, 3)))
    draft.execute(d.RecoverRemoveRelation(draft.preview_delete((("constraint", fixed),))))
    draft.execute(d.DeleteBatch(draft.preview_delete((("point", point),))))
    legacy_entries = draft.checkpoint_payload()["journal"]["entries"]
    capable = draft.promote_arc_capability()
    arc_id = add_arc(capable)
    assert capable.checkpoint_payload()["journal"]["entries"][:-1] == legacy_entries
    assert all("arcs" not in entry["before"] for entry in legacy_entries)
    assert all("arcs" not in entry["after"] for entry in legacy_entries)
    assert legacy_entries[3]["command"]["op"] == "delete"
    assert "arcs" not in legacy_entries[3]["command"]["removed"]
    assert arc_id == "a_d6"
    assert exact(restore(capable)) == exact(capable)


def test_journal3_keeps_earlier_circle_schema_migration_and_driver_records_unchanged():
    old = source_draft(1, journal_version=2)
    _, circle_id = old.execute(d.AddCircle(d.PointSeed(-0.0, 0), 5)).entity_ids
    radius = old.execute(d.AddRelation("radius", (circle_id,), value="radius")).constraint_id
    # This directly exercises the deterministic pure reducer, never fabricates
    # successful trial/native evidence or calls an acceptance/publication sink.
    old._commit({"op": "driver", "constraint_id": radius, "value": "radius + 1"})
    old.execute(d.RecoverRemoveRelation(old.preview_delete((("constraint", radius),))))
    old.execute(d.DeleteBatch(old.preview_delete((("circle", circle_id),))))
    entries = old.checkpoint_payload()["journal"]["entries"]
    capable = old.promote_arc_capability()
    add_arc(capable)
    assert capable.checkpoint_payload()["journal"]["entries"][:-1] == entries
    assert entries[0]["before"]["schema_version"] == 1
    assert "circles" not in entries[0]["before"]
    assert entries[0]["after"]["schema_version"] == 2
    assert entries[2]["command"] == {"op": "driver", "constraint_id": radius, "value": "radius + 1"}
    assert exact(restore(capable)) == exact(capable)


def test_arc_tombstones_require_new_capability_even_after_all_arc_history_is_pruned():
    draft = source_draft()
    arc_id = add_arc(draft)
    draft.undo()
    draft.execute(d.AddPoint(d.PointSeed(1, 2)))
    for number in range(64):
        draft.execute(d.AddPoint(d.PointSeed(10, number)))
    state = draft.checkpoint_payload()
    assert state["accepted_sketch"]["schema_version"] == 2
    assert arc_id in state["allocated_ids"]
    assert all(entry["command"]["op"] == "add" for entry in state["journal"]["entries"])
    assert exact(restore(draft)) == exact(draft)
    state["journal"]["schema_version"] = 2
    with pytest.raises(d.DraftError, match="allocated sketch identity"):
        d.GeneralSketchDraft.from_checkpoint_payload(state)


def test_imported_literal_arc_prefix_remains_permitted_in_legacy_identity_space():
    draft = source_draft(1, points=[{"id": "a_d4", "u": 0, "v": 0}], journal_version=2)
    draft.execute(d.AddLine(d.PointRef("a_d4"), d.PointSeed(5, 0)))
    encoded = store.dumps(draft)
    assert store.dumps(store.restore(encoded, draft.document_json)) == encoded


@pytest.mark.parametrize("transition", ["undo", "redo"])
def test_history_transition_admission_is_atomic_on_missing_arc_candidate_reference(transition):
    draft = source_draft()
    arc_id = add_arc(draft)
    draft.execute(d.ReverseArcSweep(arc_id))
    if transition == "redo":
        draft.undo()
        snapshot = draft._journal[draft._cursor]["after"]
    else:
        snapshot = draft._journal[draft._cursor - 1]["before"]
    snapshot["circles"].append({"id": "invalid", "center": "missing_point", "radius": 2})
    before = exact(draft)
    with pytest.raises(d.DraftError):
        getattr(draft, transition)()
    assert exact(draft) == before


@pytest.mark.parametrize("case", ["second_arc", "circle", "third_line"])
@pytest.mark.parametrize("invalid_reference", [False, True])
def test_imported_generalized_arc_drafts_preserve_data_and_reject_missing_references(
    case, invalid_reference
):
    draft = source_draft()
    arc_id = add_arc(draft)
    document = draft.candidate()
    sketch = document["features"][0]["sketch"]
    arc = sketch["arcs"][0]
    if case == "second_arc":
        sketch["arcs"].append({**arc, "id": "other_arc"})
    elif case == "circle":
        sketch["circles"].append({"id": "circle", "center": arc["center"], "radius": 2})
    else:
        sketch["lines"] = [
            {"id": f"line{number}", "start": arc["center"], "end": arc["start"]}
            for number in range(3)
        ]
    if invalid_reference:
        key, role = {
            "second_arc": ("arcs", "end"),
            "circle": ("circles", "center"),
            "third_line": ("lines", "end"),
        }[case]
        sketch[key][-1][role] = "missing_point"
    raw = json.dumps(document, indent=2)
    if invalid_reference:
        with pytest.raises(d.DraftError):
            d.GeneralSketchDraft(raw, "sketch", True, journal_version=3)
    else:
        imported = d.GeneralSketchDraft(raw, "sketch", True, journal_version=3)
        assert imported.document_json == raw
        assert imported.sketch == sketch
        assert not imported.has_current_solution and not imported.has_verified_trial
        assert exact(restore(imported)) == exact(imported)
    assert arc_id == draft.sketch["arcs"][0]["id"] and raw == json.dumps(document, indent=2)


@pytest.mark.parametrize(
    "bad", ["direction", "repeat", "missing", "zero", "tiny", "same_ray", "nan", "boolean", "huge"]
)
def test_bad_arc_commands_are_atomic_and_consume_no_ids(bad):
    draft = source_draft(points=[{"id": "existing", "u": 0, "v": 0}])
    inputs = [d.PointSeed(0, 0), d.PointSeed(5, 0), d.PointSeed(0, 7)]
    direction = "ccw"
    if bad == "direction":
        direction = "CCW"
    elif bad == "repeat":
        inputs[0] = inputs[1] = d.PointRef("existing")
    elif bad == "missing":
        inputs[2] = d.PointRef("missing")
    elif bad == "zero":
        inputs[1] = d.PointSeed(0, 0)
    elif bad == "tiny":
        inputs[1] = d.PointSeed(1e-7, 0)
    elif bad == "same_ray":
        inputs[2] = d.PointSeed(6, 0)
    elif bad == "nan":
        inputs[2] = d.PointSeed(0, float("nan"))
    elif bad == "boolean":
        inputs[2] = d.PointSeed(0, True)
    else:
        inputs[2] = d.PointSeed(0, 10**1000)
    before = exact(draft)
    with pytest.raises(d.DraftError):
        draft.execute(d.AddArc(*inputs, direction))
    assert exact(draft) == before


@pytest.mark.parametrize("bad", ["second_arc", "circle", "third_line"])
def test_arc_bearing_commands_preserve_generalized_geometry_and_exact_history(bad):
    draft = source_draft()
    arc_id = add_arc(draft)
    arc = draft.sketch["arcs"][0]
    if bad == "third_line":
        draft.execute(d.AddLine(d.PointRef(arc["center"]), d.PointRef(arc["start"])))
        draft.execute(d.AddLine(d.PointRef(arc["end"]), d.PointRef(arc["center"])))
        command = d.AddLine(d.PointSeed(10, 0), d.PointSeed(10, 2))
    elif bad == "circle":
        command = d.AddCircle(d.PointSeed(10, 0), 1)
    else:
        command = d.AddArc(d.PointSeed(10, 0), d.PointSeed(15, 0), d.PointSeed(10, 7), "ccw")
    before, raw = d._json(draft.sketch), draft.document_json
    draft.execute(command)
    accepted = d._json(draft.sketch)
    assert accepted != before and draft.sketch["arcs"][0]["id"] == arc_id
    assert draft.document_json == raw and not draft.has_current_solution
    clone = restore(draft)
    assert exact(clone) == exact(draft)
    clone.undo()
    assert d._json(clone.sketch) == before
    clone.redo()
    assert d._json(clone.sketch) == accepted


def test_arc_empty_schema3_retains_legacy_curves_when_adding_mixed_arc():
    draft = source_draft(3)
    draft.execute(d.AddCircle(d.PointSeed(0, 0), 5))
    for y in range(3):
        draft.execute(d.AddLine(d.PointSeed(10, y), d.PointSeed(15, y)))
    assert len(draft.sketch["lines"]) == 3 and len(draft.sketch["circles"]) == 1
    before = copy.deepcopy(draft.sketch)
    add_arc(draft)
    assert draft.sketch["lines"] == before["lines"]
    assert draft.sketch["circles"] == before["circles"]
    assert draft.sketch["points"][: len(before["points"])] == before["points"]
    clone = restore(draft)
    assert exact(clone) == exact(draft)
    accepted = d._json(clone.sketch)
    clone.undo()
    assert clone.sketch == before
    clone.redo()
    assert d._json(clone.sketch) == accepted


@pytest.mark.parametrize(
    "extra",
    [
        {
            "id": "other",
            "kind": "sketch_circle",
            "label": "Other",
            "params": {"radius": 2},
            "inputs": {},
        },
        {
            "id": "first",
            "kind": "extrude",
            "label": "First",
            "params": {"length": 10},
            "inputs": {"profile": "sketch"},
        },
    ],
)
def test_first_arc_preserves_connected_graph_and_all_redo_states(extra):
    extras = [extra]
    if extra["kind"] == "extrude":
        extras.append({**extra, "id": "second"})
    draft = source_draft(extras=extras)
    raw = draft.document_json
    add_arc(draft)
    assert draft.candidate()["features"][1:] == extras
    assert draft.document_json == raw and not draft.has_current_solution
    accepted = d._json(draft.sketch)
    draft.undo()
    clone = restore(draft)
    assert exact(clone) == exact(draft)
    clone.redo()
    assert d._json(clone.sketch) == accepted
    assert clone.candidate()["features"][1:] == extras


def test_restoration_rejects_missing_profile_in_connected_graph_without_mutation():
    draft = source_draft(
        extras=[
            {
                "id": "solid",
                "kind": "extrude",
                "label": "Solid",
                "params": {"length": 10},
                "inputs": {"profile": "sketch"},
            }
        ]
    )
    add_arc(draft)
    draft.undo()
    state = draft.checkpoint_payload()
    document = json.loads(state["document_json"])
    document["features"][1]["inputs"]["profile"] = "missing_profile"
    state["document_json"] = json.dumps(document)
    before = copy.deepcopy(state)
    with pytest.raises(d.DraftError):
        d.GeneralSketchDraft.from_checkpoint_payload(state, expected_journal_version=3)
    assert state == before


def test_solo_extrusion_selects_explicit_result3_without_native_activation():
    draft = source_draft(
        extras=[
            {
                "id": "solid",
                "kind": "extrude",
                "label": "Solid",
                "params": {"length": 10},
                "inputs": {"profile": "sketch"},
            }
        ]
    )
    add_arc(draft)
    assert draft.consumed_by == ("solid",)
    assert draft.solve_request()["result_version"] == 3
    assert draft.replay_request()["result_version"] == 3
    assert not draft.has_current_solution
    assert exact(restore(draft)) == exact(draft)


@pytest.mark.parametrize(
    "case",
    [
        "source_float",
        "source_mismatch",
        "unknown",
        "extra_arc_field",
        "extra_point",
        "point_order",
        "arc_prefix",
        "allocation",
        "ledger",
        "reverse_noop",
        "legacy_delete",
        "delete_missing_arcs",
    ],
)
def test_journal3_replays_every_redo_record_with_exact_shapes_and_allocator_provenance(case):
    draft = source_draft()
    arc_id = add_arc(draft)
    if case == "reverse_noop":
        draft.execute(d.ReverseArcSweep(arc_id))
    elif case in {"legacy_delete", "delete_missing_arcs"}:
        draft.execute(d.DeleteBatch(draft.preview_delete((("arc", arc_id),))))
    draft.undo()  # Malformed redo must fail even when current sketch looks legacy/valid.
    state = draft.checkpoint_payload()
    entry = state["journal"]["entries"][-1]
    command = entry["command"]
    if case == "source_float":
        command["source_schema_version"] = 2.0
    elif case == "source_mismatch":
        command["source_schema_version"] = 1
    elif case == "unknown":
        command["new_field"] = False
    elif case == "extra_arc_field":
        command["arc"]["radius"] = 5
    elif case == "extra_point":
        command["points"].append({"id": "p_d8", "u": 10, "v": 20})
    elif case == "point_order":
        command["points"].reverse()
    elif case == "arc_prefix":
        command["arc"]["id"] = "c_d4"
    elif case == "allocation":
        entry["allocation_after"] += 1
        state["next_id"] += 1
    elif case == "ledger":
        state["allocated_ids"].remove(arc_id)
    elif case == "reverse_noop":
        command["to_direction"] = command["from_direction"]
    elif case == "legacy_delete":
        command["op"] = "delete"
    else:
        del command["removed"]["arcs"]
    with pytest.raises(d.DraftError):
        d.GeneralSketchDraft.from_checkpoint_payload(state, expected_journal_version=3)


@pytest.mark.parametrize("budget", ["MAX_ALLOCATED_IDS", "MAX_JOURNAL_BYTES", "MAX_DOCUMENT_BYTES"])
def test_arc_budget_failure_preserves_all_prior_intent_and_ids(monkeypatch, budget):
    draft = source_draft()
    before = exact(draft)
    monkeypatch.setattr(d, budget, 2)
    with pytest.raises(d.DraftError, match="budget|limit"):
        add_arc(draft)
    assert exact(draft) == before


def test_arc_radius_duplicate_and_pending_raw_trial_keep_source_identity():
    draft = source_draft()
    arc_id = add_arc(draft)
    driver = draft.execute(d.AddRelation("radius", (arc_id,), value="radius + 0")).constraint_id
    before = exact(draft)
    duplicate = draft.execute(d.AddRelation("radius", (arc_id,), value="radius + 0"))
    assert not duplicate.changed and duplicate.constraint_id == driver and exact(draft) == before
    draft.begin_edit(driver)
    draft.update_edit("  radius + 2  ")
    authored = draft.sketch
    trial = draft.trial_candidate()["features"][0]["sketch"]
    assert trial["constraints"][0] == {
        "id": driver,
        "kind": "radius",
        "refs": [arc_id],
        "value": "radius + 2",
    }
    assert trial["points"] == authored["points"] and trial["arcs"] == authored["arcs"]
    assert draft.sketch == authored and draft.pending_edit.raw_text == "  radius + 2  "
    restored = restore(draft)
    assert exact(restored) == exact(draft) and not restored.has_verified_trial
    with pytest.raises(d.DraftError, match="Check this exact"):
        restored.accept_edit()


def test_explicit_arc_commands_and_history_need_no_core_or_native_imports():
    script = f"""
import importlib, sys, types
class RejectNative:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {{'bpy', 'OCP', 'slvs', 'mechanical_cad'}}:
            raise AssertionError('Forbidden import: ' + fullname)
sys.meta_path.insert(0, RejectNative())
p = types.ModuleType('pure_arc')
p.__path__ = [{str(ROOT / "blender_addon/mechanical_cad_blender")!r}]
sys.modules['pure_arc'] = p
d = importlib.import_module('pure_arc.general_sketch_draft')
draft = d.GeneralSketchDraft({source_draft().document_json!r}, 'sketch', True, journal_version=3)
draft.execute(d.AddArc(d.PointSeed(0, 0), d.PointSeed(5, 0), d.PointSeed(0, 7), 'ccw'))
draft = d.GeneralSketchDraft.from_checkpoint_payload(draft.checkpoint_payload(), expected_journal_version=3)
draft.execute(d.ReverseArcSweep(draft.sketch['arcs'][0]['id']))
assert not any(n.split('.')[0] in {{'bpy', 'OCP', 'slvs', 'mechanical_cad'}} for n in sys.modules)
print('PURE_ARC_COMMANDS_NO_NATIVE_OK')
"""
    result = subprocess.run([sys.executable, "-S", "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PURE_ARC_COMMANDS_NO_NATIVE_OK" in result.stdout
