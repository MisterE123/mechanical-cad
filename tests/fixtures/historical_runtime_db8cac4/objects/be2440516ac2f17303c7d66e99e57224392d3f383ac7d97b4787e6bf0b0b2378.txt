"""Pure general authoring contracts. Synthetic reports are protocol fixtures only."""

import copy
import hashlib
import importlib
import json
import subprocess
import sys
import types
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "mcad_general_draft_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
sys.modules[PACKAGE] = package
d = importlib.import_module(PACKAGE + ".general_sketch_draft")
bridge = importlib.import_module(PACKAGE + ".sketch_action_bridge")
store = importlib.import_module(PACKAGE + ".general_draft_store")


def blank():
    return {
        "schema_version": 1,
        "id": "doc",
        "name": "Part",
        "units": "mm",
        "parameters": {},
        "features": [],
        "active_feature": None,
    }


def circle_draft():
    draft = d.GeneralSketchDraft(json.dumps(blank()))
    center, circle = draft.execute(d.AddCircle(d.PointSeed(0, 0), 5)).entity_ids
    return draft, center, circle


def response_for(request, *, points=None, radii=None, dimensions=None):
    """Strict valid fixture, never a claim of an executed native solver."""
    canonical = bridge.snapshots._expected_document(request["document"])
    feature = next(item for item in canonical["features"] if item["id"] == request["feature_id"])
    solved = d._normalized_sketch(feature["sketch"])
    for point in solved["points"]:
        if points and point["id"] in points:
            point["u"], point["v"] = points[point["id"]]
    for circle in solved.get("circles", []):
        if radii and circle["id"] in radii:
            circle["radius"] = radii[circle["id"]]
    values = {}
    for relation in solved["constraints"]:
        if relation["kind"] in {"distance", "radius"}:
            value = (dimensions or {}).get(relation["id"], relation["value"])
            relation["value"] = values[relation["id"]] = value
    return {
        "protocol_version": 1,
        "action": "solve_sketch",
        "result_version": 2,
        "input_fingerprint": bridge.snapshots.input_fingerprint(request),
        "ok": True,
        "error": None,
        "result": {
            "document_id": canonical["id"],
            "feature_id": request["feature_id"],
            "document_hash": hashlib.sha256(
                (json.dumps(canonical, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
            ).hexdigest(),
            "sketch": {
                "solver": "libslvs",
                "solver_version": "3.2",
                "status": "okay",
                "remaining_dof": 0,
                "failed_constraints": [],
                "redundant_constraints": [],
                "max_residual_mm": 0.0,
                "solved": solved,
                "dimensions": values,
            },
            "profile_check": {"ready": True, "error": None},
        },
    }


def check(draft, **kwargs):
    request = draft.solve_request()
    response = response_for(request, **kwargs)
    assert draft.record_validated_solution(request, response, draft.revision)
    return request, response


def test_atomic_line_acceptance_explicit_join_and_coordinate_snap_are_distinct():
    draft = d.GeneralSketchDraft(json.dumps(blank()))
    first, shared, line = draft.execute(d.AddLine(d.PointSeed(0, 0), d.PointSeed(4, 0))).entity_ids
    other, joined = draft.execute(d.AddLine(d.PointRef(shared), d.PointSeed(4, 3))).entity_ids
    coincident, endpoint, separate = draft.execute(
        d.AddLine(d.PointSeed(4, 3), d.PointSeed(0, 3))
    ).entity_ids
    sketch = draft.sketch
    assert len(sketch["points"]) == 5 and len(sketch["lines"]) == 3
    assert sketch["lines"][1] == {"id": joined, "start": shared, "end": other}
    assert coincident != other and not sketch["constraints"]
    assert draft.document_json == json.dumps(blank())
    assert draft.revision == 3 and not draft.has_current_solution
    assert {
        first,
        shared,
        line,
        other,
        joined,
        coincident,
        endpoint,
        separate,
    } <= draft._allocated_ids


@pytest.mark.parametrize(
    "command",
    [
        d.AddLine(d.PointSeed(0, 0), d.PointSeed(0, 0)),
        d.AddLine(d.PointSeed(0, 0), d.PointSeed(1e-7, 0)),
        d.AddLine(d.PointRef("missing"), d.PointSeed(1, 1)),
        d.AddCircle(d.PointSeed(0, 0), 0),
        d.AddCircle(d.PointSeed(0, 0), -1),
        d.AddCircle(d.PointSeed(0, 0), True),
        d.AddPoint(d.PointSeed(float("nan"), 0)),
        d.AddPoint(d.PointSeed(10**1000, 0)),
        d.AddRelation("horizontal", ("missing",)),
    ],
)
def test_rejected_commands_allocate_nothing_and_leave_no_history(command):
    draft = d.GeneralSketchDraft(json.dumps(blank()))
    before = draft.checkpoint_payload()
    with pytest.raises(d.DraftError):
        draft.execute(command)
    assert draft.checkpoint_payload() == before


def test_supported_relations_keep_explicit_ids_and_exact_duplicates_are_idempotent():
    draft = d.GeneralSketchDraft(json.dumps(blank()))
    a, b, line = draft.execute(d.AddLine(d.PointSeed(0, 0), d.PointSeed(3, 4))).entity_ids
    for relation in [
        d.AddRelation("horizontal", (line,)),
        d.AddRelation("vertical", (line,)),
        d.AddRelation("coincident", (a, b)),
        d.AddRelation("fixed", (a,), target=(0, 0)),
        d.AddRelation("distance", (a, b), value="width"),
    ]:
        result = draft.execute(relation)
        revision = draft.revision
        again = draft.execute(relation)
        assert not again.changed and again.constraint_id == result.constraint_id
        assert draft.revision == revision
    duplicate = draft.execute(d.AddRelation("distance", (b, a), value="width"))
    assert not duplicate.changed
    assert draft.execute(d.AddRelation("distance", (a, b), value="width + 0")).changed
    assert not draft.has_current_solution


def test_circle_center_can_be_shared_without_implicit_fixed_or_radius_relation():
    draft, center, circle = circle_draft()
    second = draft.execute(d.AddCircle(d.PointRef(center), 7)).entity_ids[0]
    assert len(draft.sketch["points"]) == 1
    assert [c["center"] for c in draft.sketch["circles"]] == [center, center]
    assert circle != second and not draft.sketch["constraints"]


def test_detached_candidate_preserves_unrelated_fields_sources_ids_and_active_output():
    draft, _, circle = circle_draft()
    driver = draft.execute(d.AddRelation("radius", (circle,), value="width + 0.125")).constraint_id
    document = draft.candidate()
    document["parameters"] = {"width": 4.876543210987654, "untouched": "width * 3"}
    document["features"].append(
        {
            "id": "pad",
            "kind": "extrude",
            "label": "Original",
            "params": {"length": "width * 2"},
            "inputs": {"profile": draft.feature_id},
        }
    )
    document["active_feature"] = "pad"
    raw = json.dumps(document, indent=3) + "\n"
    edit = d.GeneralSketchDraft(raw, draft.feature_id, True)
    assert edit.candidate() == document and edit.document_json == raw
    edit.execute(d.AddPoint(d.PointSeed(1, 2)))
    candidate = edit.candidate()
    assert candidate["active_feature"] == "pad"
    assert candidate["features"][1] == document["features"][1]
    assert candidate["parameters"] == document["parameters"]
    assert candidate["features"][0]["sketch"]["constraints"][0] == {
        "id": driver,
        "kind": "radius",
        "refs": [circle],
        "value": "width + 0.125",
    }
    candidate["features"][0]["sketch"]["points"][0]["u"] = 300
    assert edit.candidate() != candidate and edit.document_json == raw
    with pytest.raises(d.DraftError, match="exact original"):
        edit.require_current(raw + " ")
    with pytest.raises(AttributeError):
        edit.document_json = "changed"


def test_new_independent_sketch_does_not_replace_existing_active_output():
    document = blank()
    document["features"] = [
        {"id": "rectangle", "kind": "rectangle", "params": {"width": 5, "height": 4}, "inputs": {}}
    ]
    document["active_feature"] = "rectangle"
    draft = d.GeneralSketchDraft(json.dumps(document))
    draft.execute(d.AddCircle(d.PointSeed(0, 0), 2))
    assert draft.candidate()["active_feature"] == "rectangle"


def test_line_v1_noop_remains_v1_and_circle_command_is_explicit_draft_migration():
    source = d.GeneralSketchDraft(json.dumps(blank()))
    a, _, _ = source.execute(d.AddLine(d.PointSeed(0, 0), d.PointSeed(5, 0))).entity_ids
    document = source.candidate()
    sketch = document["features"][0]["sketch"]
    sketch["schema_version"] = 1
    del sketch["circles"]
    raw = json.dumps(document)
    edit = d.GeneralSketchDraft(raw, source.feature_id, True)
    assert edit.candidate() == document
    edit.execute(d.AddCircle(d.PointRef(a), 3))
    assert edit.sketch["schema_version"] == 2
    edit.undo()
    assert edit.candidate() == document and edit.document_json == raw


def test_undo_redo_are_local_revision_bound_and_ids_survive_undo_branch():
    draft, _, old_circle = circle_draft()
    check(draft)
    draft.undo()
    assert not draft.has_current_solution and draft.can_redo and draft.revision == 2
    draft.redo()
    assert draft.revision == 3 and not draft.has_current_solution
    draft.undo()
    _, new_circle = draft.execute(d.AddCircle(d.PointSeed(1, 2), 5)).entity_ids
    assert new_circle != old_circle and not draft.can_redo
    assert draft.document_json == json.dumps(blank())


def test_delete_preview_lists_only_explicit_points_and_dependent_constraints():
    draft, center, circle = circle_draft()
    second = draft.execute(d.AddCircle(d.PointRef(center), 7)).entity_ids[0]
    radius = draft.execute(d.AddRelation("radius", (circle,), value=5)).constraint_id
    fixed = draft.execute(d.AddRelation("fixed", (center,), target=(0, 0))).constraint_id
    plan = draft.preview_delete((("circle", circle),))
    assert plan.points == () and plan.circles == (circle,) and plan.constraints == (radius,)
    point_plan = draft.preview_delete((("point", center),))
    assert set(point_plan.circles) == {circle, second}
    assert set(point_plan.constraints) == {radius, fixed}
    before = draft.checkpoint_payload()
    with pytest.raises(d.DraftError, match="Check the current sketch"):
        draft.execute(d.DeleteBatch(plan))
    assert draft.checkpoint_payload() == before


def test_constraint_release_seeds_last_current_solved_coordinates_and_radii():
    draft, center, circle = circle_draft()
    fixed = draft.execute(d.AddRelation("fixed", (center,), target=(12, -7))).constraint_id
    radius = draft.execute(d.AddRelation("radius", (circle,), value=9)).constraint_id
    request, response = check(draft, points={center: (12, -7)}, radii={circle: 9})
    assert draft.sketch["points"][0]["u"] == 0
    response["result"]["sketch"]["solved"]["points"][0]["u"] = 999
    draft.execute(d.DeleteBatch(draft.preview_delete((("constraint", fixed),))))
    assert draft.sketch["points"] == [{"id": center, "u": 12, "v": -7}]
    assert draft.sketch["circles"] == [{"id": circle, "center": center, "radius": 9}]
    assert [r["id"] for r in draft.sketch["constraints"]] == [radius]
    assert not draft.has_current_solution and request["document"] != draft.candidate()
    draft.undo()
    assert draft.sketch["points"][0]["u"] == 0
    with pytest.raises(d.DraftError, match="Check the current sketch"):
        draft.execute(d.DeleteBatch(draft.preview_delete((("constraint", fixed),))))
    draft.redo()
    assert draft.sketch["points"][0]["u"] == 12 and not draft.has_current_solution


def test_delete_geometry_keeps_shared_and_orphan_points_until_explicitly_announced():
    draft, center, circle = circle_draft()
    radius = draft.execute(d.AddRelation("radius", (circle,), value=5)).constraint_id
    check(draft)
    plan = draft.preview_delete((("circle", circle),))
    draft.execute(d.DeleteBatch(plan))
    assert not draft.sketch["circles"] and not draft.sketch["constraints"]
    assert draft.sketch["points"][0]["id"] == center and plan.constraints == (radius,)
    draft.execute(d.DeleteBatch(draft.preview_delete((("point", center),))))
    assert not draft.sketch["points"]


def test_stale_or_tampered_delete_preview_cannot_change_intent():
    draft, center, circle = circle_draft()
    plan = draft.preview_delete((("circle", circle),))
    draft.execute(d.AddPoint(d.PointSeed(2, 3)))
    with pytest.raises(d.DraftError, match="stale"):
        draft.execute(d.DeleteBatch(plan))
    plan = draft.preview_delete((("circle", circle),))
    with pytest.raises(d.DraftError, match="differs"):
        draft.execute(d.DeleteBatch(d.replace(plan, points=(center,))))


def test_pending_invalid_raw_is_not_accepted_and_cancel_preserves_original_source_type():
    draft, _, circle = circle_draft()
    driver = draft.execute(
        d.AddRelation("radius", (circle,), value=5.123456789012345)
    ).constraint_id
    accepted = draft.candidate()
    draft.begin_edit(driver)
    assert draft.pending_edit.raw_text == "5.123456789012345"
    draft.update_edit(" \tbad + ( 🛠\n")
    assert draft.candidate() == accepted
    assert (
        draft.trial_candidate()["features"][0]["sketch"]["constraints"][0]["value"] == "bad + ( 🛠"
    )
    with pytest.raises(d.DraftError, match="Check this exact"):
        draft.accept_edit()
    with pytest.raises(d.DraftError, match="pending"):
        draft.undo()
    with pytest.raises(d.DraftError, match="pending"):
        draft.execute(d.AddPoint(d.PointSeed(1, 2)))
    draft.cancel_edit()
    assert draft.candidate() == accepted


def test_dimension_accept_requires_exact_trial_and_preserves_link_until_explicit_edit():
    draft, _, circle = circle_draft()
    driver = draft.execute(d.AddRelation("radius", (circle,), value="width")).constraint_id
    draft.begin_edit(driver)
    assert draft.pending_edit.raw_text == "width"
    draft.cancel_edit()
    assert draft.sketch["constraints"][0]["value"] == "width"
    # The test's source parameter is explicit, not manufactured by the draft.
    document = draft.candidate()
    document["parameters"]["width"] = 5
    draft = d.GeneralSketchDraft(json.dumps(document), draft.feature_id, True)
    draft.begin_edit(driver)
    draft.update_edit("  7.5  ")
    request = draft.solve_request(trial=True)
    response = response_for(request, radii={circle: 7.5}, dimensions={driver: 7.5})
    assert draft.record_validated_solution(
        request, response, draft.revision, expected_input_revision=1
    )
    assert draft.has_verified_trial and not draft.has_current_solution
    assert draft.accept_edit().changed
    assert draft.sketch["constraints"][0]["value"] == "7.5"
    assert draft.candidate()["parameters"]["width"] == 5
    assert draft.has_current_solution and draft.pending_edit is None
    assert draft.sketch["circles"][0]["radius"] == 5  # Solve never silently rewrites seeds.


def test_late_revision_input_and_wrong_request_cannot_install_evidence():
    draft, _, circle = circle_draft()
    request, response = check(draft)
    draft.execute(d.AddRelation("radius", (circle,), value=5))
    with pytest.raises(d.DraftError, match="Stale"):
        draft.record_validated_solution(request, response, 1)
    with pytest.raises(d.DraftError, match="exact current"):
        draft.record_validated_solution(request, response, draft.revision)
    assert not draft.has_current_solution
    driver = draft.sketch["constraints"][0]["id"]
    draft.begin_edit(driver)
    draft.update_edit("7")
    request = draft.solve_request(trial=True)
    response = response_for(request, radii={circle: 7}, dimensions={driver: 7})
    draft.update_edit("8")
    with pytest.raises(d.DraftError, match="input revision"):
        draft.record_validated_solution(
            request, response, draft.revision, expected_input_revision=1
        )
    assert not draft.has_verified_trial and draft.pending_edit.raw_text == "8"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda r: r.update(input_fingerprint="forged"),
        lambda r: r["result"]["sketch"].update(solver_version="invented"),
        lambda r: r["result"]["sketch"].update(remaining_dof=100),
        lambda r: r["result"]["sketch"]["solved"]["points"][0].update(id="forged"),
        lambda r: r["result"].update(document_hash="forged"),
    ],
)
def test_shared_bridge_rejects_forged_evidence(mutate):
    draft, _, _ = circle_draft()
    request = draft.solve_request()
    response = response_for(request)
    mutate(response)
    with pytest.raises(d.DraftError, match="evidence was rejected"):
        draft.record_validated_solution(request, response, draft.revision)
    assert not draft.has_current_solution


def test_failed_trial_keeps_raw_error_without_acceptance():
    draft, _, circle = circle_draft()
    driver = draft.execute(d.AddRelation("radius", (circle,), value=5)).constraint_id
    draft.begin_edit(driver)
    draft.update_edit("unknown + (")
    request = draft.solve_request(trial=True)
    response = {
        "protocol_version": 1,
        "action": "solve_sketch",
        "result_version": 2,
        "input_fingerprint": bridge.snapshots.input_fingerprint(request),
        "ok": False,
        "result": None,
        "error": {"code": "invalid_expression", "message": "Invalid radius expression."},
    }
    assert not draft.record_validated_solution(
        request, response, draft.revision, expected_input_revision=1
    )
    assert draft.pending_edit.raw_text == "unknown + ("
    assert draft.pending_edit.error == "Invalid radius expression."
    assert draft.sketch["constraints"][0]["value"] == 5


def test_fixed_target_edit_is_explicit_and_rejected_after_target_is_removed():
    draft, center, _ = circle_draft()
    fixed = draft.execute(d.AddRelation("fixed", (center,), target=(0, 0))).constraint_id
    draft.execute(d.EditFixedTarget(fixed, (10, 20)))
    assert draft.sketch["constraints"][0]["target"] == [10, 20]
    assert draft.sketch["points"][0]["u"] == 0
    with pytest.raises(d.DraftError):
        draft.execute(d.EditFixedTarget("missing", (10, 20)))


def test_journal_is_bounded_by_count_and_expanded_bytes(monkeypatch):
    draft, center, _ = circle_draft()
    fixed = draft.execute(d.AddRelation("fixed", (center,), target=(0, 0))).constraint_id
    monkeypatch.setattr(d, "MAX_JOURNAL_ENTRIES", 3)
    monkeypatch.setattr(d, "MAX_JOURNAL_BYTES", 4500)
    for value in range(1, 10):
        draft.execute(d.EditFixedTarget(fixed, (value, 0)))
    journal = draft.checkpoint_payload()["journal"]
    assert len(journal["entries"]) <= 3
    assert len(d._json(journal["entries"]).encode()) <= 4500
    assert journal["anchor_sequence"] > 0
    restored = d.GeneralSketchDraft.from_checkpoint_payload(draft.checkpoint_payload())
    assert restored.candidate() == draft.candidate()
    assert restored.revision == draft.revision


def test_rejected_history_budget_change_is_atomic(monkeypatch):
    draft, _, _ = circle_draft()
    before = draft.checkpoint_payload()
    monkeypatch.setattr(d, "MAX_JOURNAL_BYTES", 20)
    with pytest.raises(d.DraftError, match="history byte budget"):
        draft.execute(d.AddPoint(d.PointSeed(1, 2)))
    assert draft.checkpoint_payload() == before


def test_raw_input_and_identity_budgets_are_explicit(monkeypatch):
    draft, _, circle = circle_draft()
    driver = draft.execute(d.AddRelation("radius", (circle,), value=5)).constraint_id
    draft.begin_edit(driver)
    before = draft.pending_edit
    with pytest.raises(d.DraftError, match="too large"):
        draft.update_edit("🛠" * d.MAX_RAW_TEXT_BYTES)
    assert draft.pending_edit == before
    draft.cancel_edit()
    monkeypatch.setattr(d, "MAX_ALLOCATED_IDS", len(draft._allocated_ids))
    with pytest.raises(d.DraftError, match="stable-ID budget"):
        draft.execute(d.AddPoint(d.PointSeed(1, 2)))


def test_imports_need_no_blender_core_solver_or_kernel():
    script = f"""import importlib, sys, types
p=types.ModuleType("pure_general")
p.__path__=[{str(ROOT / "blender_addon/mechanical_cad_blender")!r}]
sys.modules[p.__name__]=p
importlib.import_module("pure_general.general_sketch_draft")
importlib.import_module("pure_general.general_draft_store")
assert not any(n in sys.modules for n in ("bpy", "mechanical_cad", "slvs", "OCP"))
"""
    result = subprocess.run([sys.executable, "-S", "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def consumed_trial():
    draft, _, circle = circle_draft()
    driver = draft.execute(d.AddRelation("radius", (circle,), value=5)).constraint_id
    document = draft.candidate()
    document["features"].append(
        {
            "id": "pad",
            "kind": "extrude",
            "params": {"length": 10},
            "inputs": {"profile": draft.feature_id},
        }
    )
    document["active_feature"] = "pad"
    draft = d.GeneralSketchDraft(json.dumps(document), draft.feature_id, True)
    draft.begin_edit(driver)
    draft.update_edit("7")
    request = draft.solve_request(trial=True)
    response = response_for(request, radii={circle: 7}, dimensions={driver: 7})
    draft.record_validated_solution(request, response, draft.revision, expected_input_revision=1)
    return draft, response


def test_consumed_driver_keeps_pending_until_exact_successful_full_replay(monkeypatch):
    draft, solve = consumed_trial()
    before = draft.candidate()
    with pytest.raises(d.DraftError, match="exact full replay"):
        draft.accept_driver()
    assert draft.candidate() == before and draft.pending_edit.raw_text == "7"
    calls = []

    def validate(request, response):
        calls.append((request, response))
        return {
            "ok": True,
            "result": {
                "status": "ok",
                "features": [{"id": draft.feature_id, "sketch": solve["result"]["sketch"]}],
            },
        }

    monkeypatch.setattr(d, "validate_replay_response", validate)
    replay = draft.replay_request(trial=True, options={"linear_deflection": 0.1})
    assert draft.accept_driver(
        replay_request=replay, replay_response={"fixture": "bound by stub"}
    ).changed
    assert len(calls) == 1 and calls[0][0] == replay
    assert draft.pending_edit is None and draft.has_current_solution
    assert draft.candidate()["active_feature"] == "pad"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda request: request.update(action="check_geometry"),
        lambda request: request.update(destination="part.step"),
        lambda request: request["document"]["features"][0]["sketch"]["constraints"][0].update(
            value="8"
        ),
        lambda request: request["document"].update(active_feature="sketch_1"),
    ],
)
def test_consumed_driver_cannot_accept_replay_for_another_action_or_candidate(mutate, monkeypatch):
    draft, _ = consumed_trial()
    request = draft.replay_request(trial=True)
    mutate(request)
    calls = []
    monkeypatch.setattr(d, "validate_replay_response", lambda *args: calls.append(args))
    with pytest.raises(d.DraftError, match="exact pending"):
        draft.accept_driver(replay_request=request, replay_response={})
    assert not calls and draft.pending_edit.raw_text == "7"


def test_consumed_driver_full_replay_failure_is_recoverable(monkeypatch):
    draft, _ = consumed_trial()
    monkeypatch.setattr(d, "validate_replay_response", lambda *args: {"ok": False, "result": None})
    before = draft.candidate()
    with pytest.raises(d.DraftError, match="full downstream replay failed"):
        draft.accept_driver(replay_request=draft.replay_request(trial=True), replay_response={})
    assert draft.candidate() == before and draft.pending_edit.raw_text == "7"
    assert draft.pending_edit.error


def test_equal_numeric_relation_values_are_idempotent_without_rewriting_source_type():
    draft, center, circle = circle_draft()
    result = draft.execute(d.AddRelation("radius", (circle,), value=5))
    assert not draft.execute(d.AddRelation("radius", (circle,), value=5.0)).changed
    assert draft.sketch["constraints"][0]["id"] == result.constraint_id
    assert type(draft.sketch["constraints"][0]["value"]) is int
    draft.execute(d.AddRelation("fixed", (center,), target=(0, 0)))
    assert not draft.execute(d.AddRelation("fixed", (center,), target=(0.0, 0.0))).changed
    with pytest.raises(d.DraftError):
        draft.execute(d.AddRelation("radius", (circle,), value=True))


def test_request_cycles_and_exponential_shared_trees_reject_before_serializing():
    draft, _, _ = circle_draft()
    request = draft.solve_request()
    request["loop"] = request
    with pytest.raises(d.DraftError, match="bounded sketch request"):
        draft.record_validated_solution(request, {}, draft.revision)
    request = draft.solve_request()
    tree = [0]
    for _ in range(30):
        tree = [tree, tree]
    request["tree"] = tree
    with pytest.raises(d.DraftError, match="bounded sketch request"):
        draft.record_validated_solution(request, {}, draft.revision)


@pytest.mark.parametrize(
    "operation", ["execute", "undo", "redo", "input", "allocation", "compound", "collision"]
)
def test_exhausted_counters_fail_before_any_live_mutation(operation):
    draft, center, circle = circle_draft()
    driver = draft.execute(d.AddRelation("radius", (circle,), value=5)).constraint_id
    if operation == "redo":
        draft.undo()
    if operation == "input":
        draft.begin_edit(driver)
        draft.update_edit("unparsed + (")
    state = draft.checkpoint_payload()
    limit = 2**53 - 1
    if operation in {"execute", "undo", "redo"}:
        state["revision"] = limit
    elif operation == "input":
        state["pending_edit"]["input_revision"] = limit
    else:
        state["next_id"] = limit - 2 if operation == "compound" else limit
    if operation == "collision":
        original = draft.candidate()
        original["features"][0]["sketch"]["points"].append(
            {"id": f"p_d{limit - 1}", "u": 4, "v": 8}
        )
        draft = d.GeneralSketchDraft(json.dumps(original), draft.feature_id, True)
        state = draft.checkpoint_payload()
        state["next_id"] = limit - 1
    restored = d.GeneralSketchDraft.from_checkpoint_payload(state)
    if operation != "input":
        check(restored)
    before = restored.checkpoint_payload()
    evidence = restored._solution, restored._trial_solution
    actions = {
        "execute": lambda: restored.execute(d.AddPoint(d.PointSeed(2, 3))),
        "undo": restored.undo,
        "redo": restored.redo,
        "input": lambda: restored.update_edit("replacement text"),
        "allocation": lambda: restored.execute(d.AddPoint(d.PointSeed(2, 3))),
        "compound": lambda: restored.execute(d.AddLine(d.PointSeed(2, 3), d.PointSeed(3, 4))),
        "collision": lambda: restored.execute(d.AddPoint(d.PointSeed(2, 3))),
    }
    with pytest.raises(d.DraftError, match="limit is reached"):
        actions[operation]()
    assert restored.checkpoint_payload() == before
    assert (restored._solution, restored._trial_solution) == evidence
    assert d.GeneralSketchDraft.from_checkpoint_payload(before).checkpoint_payload() == before


def test_noop_driver_acceptance_at_maximum_revision_does_not_need_an_increment():
    draft, _, circle = circle_draft()
    driver = draft.execute(d.AddRelation("radius", (circle,), value=5)).constraint_id
    state = draft.checkpoint_payload()
    state["revision"] = 2**53 - 1
    draft = d.GeneralSketchDraft.from_checkpoint_payload(state)
    draft.begin_edit(driver)
    request = draft.solve_request(trial=True)
    draft.record_validated_solution(
        request, response_for(request), draft.revision, expected_input_revision=0
    )
    before = draft.candidate()
    assert not draft.accept_edit().changed
    assert draft.revision == 2**53 - 1 and draft.candidate() == before
    assert draft.has_current_solution and draft.pending_edit is None
    assert (
        d.GeneralSketchDraft.from_checkpoint_payload(draft.checkpoint_payload()).candidate()
        == before
    )


def test_changed_driver_at_maximum_revision_keeps_raw_trial_and_evidence():
    draft, _, circle = circle_draft()
    driver = draft.execute(d.AddRelation("radius", (circle,), value=5)).constraint_id
    state = draft.checkpoint_payload()
    state["revision"] = 2**53 - 1
    draft = d.GeneralSketchDraft.from_checkpoint_payload(state)
    draft.begin_edit(driver)
    draft.update_edit(" 7.5 ")
    request = draft.solve_request(trial=True)
    response = response_for(request, radii={circle: 7.5}, dimensions={driver: 7.5})
    draft.record_validated_solution(request, response, draft.revision, expected_input_revision=1)
    before, evidence = draft.checkpoint_payload(), draft._trial_solution
    with pytest.raises(d.DraftError, match="limit is reached"):
        draft.accept_edit()
    assert draft.checkpoint_payload() == before and draft._trial_solution is evidence
    assert draft.pending_edit.raw_text == " 7.5 " and draft.has_verified_trial


def test_recovery_copies_exact_current_authored_seeds_not_retained_solved_positions():
    document = blank()
    document["parameters"]["width"] = 9
    draft = d.GeneralSketchDraft(json.dumps(document))
    center, circle = draft.execute(d.AddCircle(d.PointSeed(-0.0, 2), 5.125)).entity_ids
    fixed = draft.execute(
        d.AddRelation("fixed", (center,), target=(900_000, -800_000))
    ).constraint_id
    radius = draft.execute(d.AddRelation("radius", (circle,), value="width + 0.125")).constraint_id
    check(
        draft,
        points={center: (900_000, -800_000)},
        radii={circle: 9.125},
        dimensions={radius: 9.125},
    )
    retained = draft._solution
    conflict = draft.execute(d.AddRelation("fixed", (center,), target=(0, 0))).constraint_id
    # Simulate a retained old solved/display cache. Recovery must not read its
    # coordinates even if another owner mistakenly retains this stale object.
    draft._solution = retained
    before = draft.checkpoint_payload()
    expected = copy.deepcopy(before["accepted_sketch"])
    expected["constraints"] = [row for row in expected["constraints"] if row["id"] != conflict]
    preview = draft.preview_delete((("constraint", conflict),))
    command = d.RecoverRemoveRelation(preview)
    with pytest.raises(FrozenInstanceError):
        command.preview = None
    with pytest.raises(FrozenInstanceError):
        preview.constraints = ()
    result = draft.execute(command)
    assert result.changed and result.revision == before["revision"] + 1
    assert d._json(draft.sketch) == d._json(expected)
    assert not draft.has_current_solution and draft._solution is None
    state = draft.checkpoint_payload()
    assert state["allocated_ids"] == before["allocated_ids"]
    assert state["next_id"] == before["next_id"]
    assert len(state["journal"]["entries"]) == len(before["journal"]["entries"]) + 1
    entry = state["journal"]["entries"][-1]
    assert entry["command"] == {
        "op": "delete",
        "targets": [["constraint", conflict]],
        "removed": {"points": [], "lines": [], "circles": [], "constraints": [conflict]},
        "seeds": {
            "points": [{"id": center, "u": -0.0, "v": 2}],
            "circles": [{"id": circle, "radius": 5.125}],
        },
    }
    assert d._json(entry["command"]["seeds"]["points"]) == d._json(expected["points"])
    assert [row["id"] for row in draft.sketch["constraints"]] == [fixed, radius]
    entry["command"]["seeds"]["points"][0]["u"] = 999  # Returned copies are detached.
    expected_bytes = store.dumps(draft)
    restored = store.restore(expected_bytes, draft.document_json)
    assert store.dumps(restored) == expected_bytes
    restored.undo()
    assert d._json(restored.sketch) == d._json(before["accepted_sketch"])
    assert not restored.has_current_solution
    restored.redo()
    assert d._json(restored.sketch) == d._json(expected)
    assert not restored.has_current_solution


@pytest.mark.parametrize(
    "case",
    [
        "stale",
        "float_revision",
        "missing",
        "geometry",
        "multiple",
        "cascade",
        "extra_relation",
        "list_targets",
        "untyped",
    ],
)
def test_recovery_requires_exact_current_single_relation_preview_without_cascade(case):
    draft, center, circle = circle_draft()
    fixed = draft.execute(d.AddRelation("fixed", (center,), target=(0, 0))).constraint_id
    radius = draft.execute(d.AddRelation("radius", (circle,), value=5)).constraint_id
    preview = draft.preview_delete((("constraint", fixed),))
    previews = {
        "stale": d.replace(preview, revision=preview.revision - 1),
        "float_revision": d.replace(preview, revision=float(preview.revision)),
        "missing": d.replace(
            preview, targets=(("constraint", "missing"),), constraints=("missing",)
        ),
        "geometry": draft.preview_delete((("circle", circle),)),
        "multiple": draft.preview_delete((("constraint", fixed), ("constraint", radius))),
        "cascade": d.replace(preview, points=(center,)),
        "extra_relation": d.replace(preview, constraints=(fixed, radius)),
        "list_targets": d.replace(preview, targets=[["constraint", fixed]]),
        "untyped": None,
    }
    before = store.dumps(draft)
    with pytest.raises(d.DraftError):
        draft.execute(d.RecoverRemoveRelation(previews[case]))
    assert store.dumps(draft) == before


def test_recovery_rejects_current_solution_and_pending_input_without_losing_evidence():
    draft, center, circle = circle_draft()
    fixed = draft.execute(d.AddRelation("fixed", (center,), target=(12, -7))).constraint_id
    radius = draft.execute(d.AddRelation("radius", (circle,), value=9)).constraint_id
    check(draft, points={center: (12, -7)}, radii={circle: 9})
    command = d.RecoverRemoveRelation(draft.preview_delete((("constraint", fixed),)))
    before, evidence = store.dumps(draft), draft._solution
    with pytest.raises(d.DraftError, match="current solved placement"):
        draft.execute(command)
    assert store.dumps(draft) == before and draft._solution is evidence
    draft.begin_edit(radius)
    draft.update_edit(" invalid + ( ")
    before = store.dumps(draft)
    with pytest.raises(d.DraftError, match="pending dimension"):
        draft.execute(command)
    assert store.dumps(draft) == before


def test_recovery_preparation_rejects_supplied_release_seeds():
    draft, center, _ = circle_draft()
    fixed = draft.execute(d.AddRelation("fixed", (center,), target=(0, 0))).constraint_id
    command = d.RecoverRemoveRelation(draft.preview_delete((("constraint", fixed),)))
    before = store.dumps(draft)
    with pytest.raises(d.DraftError, match="only current authored"):
        d.prepare_command(
            draft.sketch,
            command,
            draft.revision,
            draft._allocated_ids,
            draft._next_id,
            release_seeds={"points": [], "circles": []},
        )
    assert store.dumps(draft) == before


def test_recovery_uses_current_authored_seeds_after_an_earlier_validated_release():
    draft, center, circle = circle_draft()
    fixed = draft.execute(d.AddRelation("fixed", (center,), target=(12, -7))).constraint_id
    draft.execute(d.AddRelation("radius", (circle,), value=9))
    check(draft, points={center: (12, -7)}, radii={circle: 9})
    draft.execute(d.DeleteBatch(draft.preview_delete((("constraint", fixed),))))
    draft.execute(d.AddRelation("fixed", (center,), target=(800_000, -700_000)))
    check(draft, points={center: (800_000, -700_000)}, radii={circle: 9})
    conflict = draft.execute(d.AddRelation("fixed", (center,), target=(0, 0))).constraint_id
    authored = draft.sketch
    draft.execute(d.RecoverRemoveRelation(draft.preview_delete((("constraint", conflict),))))
    assert draft.sketch["points"] == authored["points"] == [{"id": center, "u": 12, "v": -7}]
    assert draft.sketch["circles"] == authored["circles"]
    assert draft.sketch["circles"][0]["radius"] == 9


@pytest.mark.parametrize("limit", ["revision", "journal_bytes", "document_bytes"])
def test_recovery_budget_failures_leave_the_entire_draft_unchanged(limit, monkeypatch):
    draft, center, _ = circle_draft()
    fixed = draft.execute(d.AddRelation("fixed", (center,), target=(0, 0))).constraint_id
    state = draft.checkpoint_payload()
    if limit == "revision":
        state["revision"] = 2**53 - 1
        draft = d.GeneralSketchDraft.from_checkpoint_payload(state)
    before = draft.checkpoint_payload()
    if limit == "journal_bytes":
        monkeypatch.setattr(d, "MAX_JOURNAL_BYTES", 20)
    if limit == "document_bytes":
        monkeypatch.setattr(d, "MAX_DOCUMENT_BYTES", 20)
    with pytest.raises(d.DraftError, match="limit|budget"):
        draft.execute(d.RecoverRemoveRelation(draft.preview_delete((("constraint", fixed),))))
    assert draft.checkpoint_payload() == before


def test_recovery_needs_no_new_identity_and_retains_embedded_schema_one():
    source = d.GeneralSketchDraft(json.dumps(blank()))
    _, _, line = source.execute(d.AddLine(d.PointSeed(0, -0.0), d.PointSeed(5, 0))).entity_ids
    relation = source.execute(d.AddRelation("horizontal", (line,))).constraint_id
    document = source.candidate()
    sketch = document["features"][0]["sketch"]
    sketch["schema_version"] = 1
    del sketch["circles"]
    draft = d.GeneralSketchDraft(json.dumps(document), source.feature_id, True)
    state = draft.checkpoint_payload()
    state["next_id"] = 2**53 - 1
    draft = d.GeneralSketchDraft.from_checkpoint_payload(state)
    assert not draft.can_undo
    draft.execute(d.RecoverRemoveRelation(draft.preview_delete((("constraint", relation),))))
    assert draft.sketch["schema_version"] == 1 and "circles" not in draft.sketch
    assert d._json(draft.sketch["points"]) == d._json(sketch["points"])
    assert draft.checkpoint_payload()["next_id"] == 2**53 - 1
    assert draft.checkpoint_payload()["allocated_ids"] == state["allocated_ids"]
    assert store.dumps(store.restore(store.dumps(draft), draft.document_json)) == store.dumps(draft)
    draft.undo()
    assert d._json(draft.sketch) == d._json(sketch)


@pytest.mark.parametrize("kind", ["horizontal", "vertical", "coincident", "fixed"])
def test_duplicate_relation_preserves_exact_pure_snapshot_and_current_evidence(kind):
    draft = d.GeneralSketchDraft(json.dumps(blank()))
    a, b, horizontal = draft.execute(d.AddLine(d.PointSeed(0, 0), d.PointSeed(5, 0))).entity_ids
    c, vertical = draft.execute(d.AddLine(d.PointRef(b), d.PointSeed(5, 5))).entity_ids
    draft.execute(d.AddLine(d.PointRef(c), d.PointRef(a)))
    (other,) = draft.execute(d.AddPoint(d.PointSeed(0, 0))).entity_ids
    command = {
        "horizontal": d.AddRelation("horizontal", (horizontal,)),
        "vertical": d.AddRelation("vertical", (vertical,)),
        "coincident": d.AddRelation("coincident", (a, other)),
        "fixed": d.AddRelation("fixed", (a,), target=(0, 0)),
    }[kind]
    relation = draft.execute(command).constraint_id
    check(draft)  # Synthetic bridge fixture; no native geometry claim.
    before, evidence = store.dumps(draft), draft._solution
    if kind == "coincident":
        command = d.AddRelation("coincident", (other, a))
    result = draft.execute(command)
    assert not result.changed and result.constraint_id == relation
    assert store.dumps(draft) == before and draft._solution is evidence
    assert draft.has_current_solution


def test_released_delete_snapshot_bytes_remain_exact():
    # Captured against immutable 0.4 (4b53129); these modules were byte-identical
    # at the pre-change HEAD 925f32f. Includes released solved-release semantics.
    draft, center, circle = circle_draft()
    fixed = draft.execute(d.AddRelation("fixed", (center,), target=(12, -7))).constraint_id
    draft.execute(d.AddRelation("radius", (circle,), value=9))
    check(draft, points={center: (12, -7)}, radii={circle: 9})
    stages = [
        (lambda: None, "46a49bd8c2f1a14b3aeb01c8dd01c5aa40f9a82b6da60c66893476ddbb67f04d"),
        (
            lambda: draft.execute(d.DeleteBatch(draft.preview_delete((("constraint", fixed),)))),
            "93d7567b412dd2267af335a61cdfd07a8131bf665f1302e29209c2f5f2cf9464",
        ),
        (draft.undo, "fbb87d9e994186606ae090ed2691ab46d95888a50c7f7c74ff2afe35bf194212"),
        (draft.redo, "2a80084f4ffe986d69d765efb68b0d1d552a19b8b7e40a89eee111902dbe0d26"),
    ]
    for action, expected in stages:
        action()
        encoded = store.dumps(draft)
        assert hashlib.sha256(encoded.encode()).hexdigest() == expected
        assert store.dumps(store.restore(encoded, draft.document_json)) == encoded


def test_invalidating_runtime_solution_preserves_exact_authored_checkpoint():
    draft, _, _ = circle_draft()
    request = draft.solve_request()
    draft.record_validated_solution(request, response_for(request), draft.revision)
    assert draft.has_current_solution
    before = draft.checkpoint_payload()
    draft.invalidate_solution()
    assert not draft.has_current_solution and not draft.has_verified_trial
    assert draft.checkpoint_payload() == before
    draft.invalidate_solution()
    assert draft.checkpoint_payload() == before
