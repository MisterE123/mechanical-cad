"""Command-authored general drafts exercised through real solver and B-rep replay.

These are core/state integration gates, not native Blender interaction evidence.
"""

import copy
import importlib
import json
import math
import sys
import types
from pathlib import Path

import pytest

pytest.importorskip("OCP")
pytest.importorskip("slvs")

from mechanical_cad.model import Document
from mechanical_cad.sidecar import process_request

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "mcad_general_native_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
sys.modules[PACKAGE] = package
d = importlib.import_module(PACKAGE + ".general_sketch_draft")
store = importlib.import_module(PACKAGE + ".general_draft_store")


def blank():
    return json.dumps(
        {
            "schema_version": 1,
            "id": "authored_part",
            "name": "Authored Part",
            "units": "mm",
            "parameters": {"radius": 5},
            "features": [],
            "active_feature": None,
        }
    )


def solve(draft, *, trial=False):
    request = draft.solve_request(trial=trial)
    response = process_request(request)
    options = {"expected_input_revision": draft.pending_edit.input_revision} if trial else {}
    accepted = draft.record_validated_solution(request, response, draft.revision, **options)
    return accepted, response


def authored_circle():
    draft = d.GeneralSketchDraft(blank())
    center, circle = draft.execute(d.AddCircle(d.PointSeed(2, 3), 8)).entity_ids
    driver = draft.execute(d.AddRelation("radius", (circle,), value="radius")).constraint_id
    fixed = draft.execute(d.AddRelation("fixed", (center,), target=(10, 20))).constraint_id
    return draft, center, circle, driver, fixed


def test_native_release_seeds_the_current_solution_and_resume_revokes_trust():
    draft, center, circle, _, fixed = authored_circle()
    success, response = solve(draft)
    assert success and response["result"]["sketch"]["remaining_dof"] == 0
    solved = response["result"]["sketch"]["solved"]
    assert solved["points"][0] == {"id": center, "u": 10.0, "v": 20.0}
    assert solved["circles"][0]["radius"] == pytest.approx(5)
    draft.execute(d.DeleteBatch(draft.preview_delete((("constraint", fixed),))))
    success, released = solve(draft)
    assert success and released["result"]["sketch"]["remaining_dof"] == 2
    assert released["result"]["sketch"]["solved"]["points"] == solved["points"]
    assert released["result"]["sketch"]["solved"]["circles"] == solved["circles"]
    restored = store.restore(store.dumps(draft), draft.document_json)
    assert restored.candidate() == draft.candidate()
    assert not restored.has_current_solution
    with pytest.raises(d.DraftError, match="Check the current sketch"):
        driver = next(
            row["id"] for row in restored.sketch["constraints"] if row["kind"] == "radius"
        )
        restored.execute(d.DeleteBatch(restored.preview_delete((("constraint", driver),))))
    assert solve(restored)[0]
    assert restored.sketch["circles"][0]["id"] == circle


def test_consumed_circle_formula_edit_requires_exact_full_native_replay():
    draft, _, circle, driver, _ = authored_circle()
    candidate = draft.candidate()
    candidate["features"].append(
        {
            "id": "pad",
            "kind": "extrude",
            "params": {"length": 10},
            "inputs": {"profile": draft.feature_id},
        }
    )
    candidate["active_feature"] = "pad"
    base = Document.from_dict(candidate).to_json()
    edited = d.GeneralSketchDraft(base, draft.feature_id, True)
    edited.begin_edit(driver)
    edited.update_edit("  radius * 2  ")
    assert solve(edited, trial=True)[0]
    with pytest.raises(d.DraftError, match="full replay"):
        edited.accept_driver()
    request = edited.replay_request(trial=True)
    response = process_request(request)
    assert response["ok"]
    assert response["result"]["features"][-1]["stats"]["volume"] == pytest.approx(
        math.pi * 100 * 10
    )
    assert edited.accept_driver(replay_request=request, replay_response=response).changed
    assert edited.pending_edit is None and edited.has_current_solution
    assert edited.document_json == base and edited.candidate()["active_feature"] == "pad"
    sketch = edited.sketch
    assert sketch["circles"][0]["id"] == circle
    assert (
        next(row["value"] for row in sketch["constraints"] if row["id"] == driver) == "radius * 2"
    )
    edited.undo()
    assert (
        next(row["value"] for row in edited.sketch["constraints"] if row["id"] == driver)
        == "radius"
    )
    edited.redo()
    assert not edited.has_current_solution
    replay = process_request(edited.replay_request())
    assert replay["ok"] and replay["result"]["active_feature"] == "pad"


def test_invalid_native_trial_preserves_verbatim_raw_input_and_old_intent():
    draft, _, _, driver, _ = authored_circle()
    before = draft.candidate()
    draft.begin_edit(driver)
    raw = " \tmissing + (  "
    draft.update_edit(raw)
    success, response = solve(draft, trial=True)
    assert not success and not response["ok"]
    assert draft.pending_edit.raw_text == raw and draft.candidate() == before
    assert draft.pending_edit.error
    restored = store.restore(store.dumps(draft), draft.document_json)
    assert restored.pending_edit.raw_text == raw and not restored.has_verified_trial
    restored.cancel_edit()
    assert restored.candidate() == before


def test_command_authored_open_chain_can_close_to_a_stable_triangle_extrusion():
    draft = d.GeneralSketchDraft(blank())
    a, b, first = draft.execute(d.AddLine(d.PointSeed(0, 0), d.PointSeed(30, 0))).entity_ids
    c, second = draft.execute(d.AddLine(d.PointRef(b), d.PointSeed(30, 20))).entity_ids
    draft.execute(d.AddRelation("fixed", (a,), target=(0, 0)))
    draft.execute(d.AddRelation("horizontal", (first,)))
    draft.execute(d.AddRelation("vertical", (second,)))
    draft.execute(d.AddRelation("distance", (a, b), value=30))
    draft.execute(d.AddRelation("distance", (b, c), value=20))
    success, opened = solve(draft)
    assert success and opened["result"]["sketch"]["remaining_dof"] == 0
    assert not opened["result"]["profile_check"]["ready"]
    open_replay = process_request(draft.replay_request())
    assert open_replay["ok"] and open_replay["result"]["features"][0]["mesh"] is None
    saved = Document.from_dict(draft.candidate()).to_json()
    assert Document.from_json(saved).features[0].sketch.schema_version == 2
    (third,) = draft.execute(d.AddLine(d.PointRef(c), d.PointRef(a))).entity_ids
    assert solve(draft)[0]
    candidate = draft.candidate()
    candidate["features"].append(
        {
            "id": "pad",
            "kind": "extrude",
            "params": {"length": 5},
            "inputs": {"profile": draft.feature_id},
        }
    )
    candidate["active_feature"] = "pad"
    request = {**draft.replay_request(), "document": candidate}
    response = process_request(request)
    assert response["ok"]
    solid = response["result"]["features"][-1]
    assert solid["stats"]["volume"] == pytest.approx(1500)
    assert {face["role"] for face in solid["topology"]} == {
        "cap.start",
        "cap.end",
        *("side.line." + line for line in (first, second, third)),
    }
    candidate["features"][0]["sketch"]["lines"].reverse()
    reordered = process_request(request)
    assert reordered["ok"]
    assert {face["id"] for face in reordered["result"]["features"][-1]["topology"]} == {
        face["id"] for face in solid["topology"]
    }


@pytest.mark.parametrize("conflict_kind", ["horizontal", "vertical", "fixed"])
@pytest.mark.parametrize("restored_import", [False, True])
def test_failed_native_relations_recover_with_authored_seeds_and_reversible_history(
    conflict_kind, restored_import
):
    draft = d.GeneralSketchDraft(blank())
    a, b, line = draft.execute(d.AddLine(d.PointSeed(0, 0), d.PointSeed(3, 4))).entity_ids
    orientation = "vertical" if conflict_kind == "horizontal" else "horizontal"
    fixed = d.AddRelation("fixed", (a,), target=(500_000, -400_000))
    aligned = d.AddRelation(orientation, (line,))
    distance = d.AddRelation("distance", (a, b), value="radius")
    for command in (fixed, aligned, distance):
        draft.execute(command)
    success, valid = solve(draft)
    assert success and valid["result"]["sketch"]["remaining_dof"] == 0
    assert valid["result"]["sketch"]["solved"]["points"] != draft.sketch["points"]
    before, evidence = store.dumps(draft), draft._solution
    for command in (fixed, aligned, d.AddRelation("distance", (b, a), value="radius")):
        assert not draft.execute(command).changed
        assert store.dumps(draft) == before and draft._solution is evidence
    conflict = draft.execute(
        d.AddRelation("fixed", (a,), target=(0, 0))
        if conflict_kind == "fixed"
        else d.AddRelation(conflict_kind, (line,))
    ).constraint_id
    assert not solve(draft)[0]
    assert not draft.has_current_solution
    if restored_import:
        # A saved inconsistent source can have no local action available to Undo.
        raw = Document.from_dict(draft.candidate()).to_json()
        draft = d.GeneralSketchDraft(raw, draft.feature_id, True)
        draft = store.restore(store.dumps(draft), raw)
        assert not draft.can_undo and not draft.can_redo
        assert not solve(draft)[0]
    before = store.dumps(draft)
    authored = draft.sketch
    preview = draft.preview_delete((("constraint", conflict),))
    with pytest.raises(d.DraftError, match="Check the current sketch"):
        draft.execute(d.DeleteBatch(preview))
    assert store.dumps(draft) == before
    assert draft.execute(d.RecoverRemoveRelation(preview)).changed
    expected = copy.deepcopy(authored)
    expected["constraints"] = [row for row in expected["constraints"] if row["id"] != conflict]
    assert d._json(draft.sketch) == d._json(expected)
    assert not draft.has_current_solution  # Removal itself is not a successful Check.
    encoded = store.dumps(draft)
    draft = store.restore(encoded, draft.document_json)
    assert store.dumps(draft) == encoded
    success, recovered = solve(draft)
    assert success and recovered["result"]["sketch"]["remaining_dof"] == 0
    assert draft.sketch == expected  # Checking does not rewrite authored positions.
    draft.undo()
    assert d._json(draft.sketch) == d._json(authored)
    assert not solve(draft)[0]
    draft.redo()
    assert d._json(draft.sketch) == d._json(expected)
    assert not draft.has_current_solution and solve(draft)[0]


def test_native_release_after_far_origin_driver_edit_still_uses_current_solution():
    draft = d.GeneralSketchDraft(blank())
    a, b, line = draft.execute(d.AddLine(d.PointSeed(0, 0), d.PointSeed(5, 0))).entity_ids
    fixed = draft.execute(d.AddRelation("fixed", (a,), target=(500_000, -400_000))).constraint_id
    draft.execute(d.AddRelation("horizontal", (line,)))
    driver = draft.execute(d.AddRelation("distance", (a, b), value="radius")).constraint_id
    assert solve(draft)[0]
    draft.begin_edit(driver)
    draft.update_edit("radius * 2")
    success, edited = solve(draft, trial=True)
    assert success and draft.accept_edit().changed
    solved_points = edited["result"]["sketch"]["solved"]["points"]

    def assert_same_placement(points):
        assert [row["id"] for row in points] == [row["id"] for row in solved_points]
        for actual, expected in zip(points, solved_points, strict=True):
            assert (actual["u"], actual["v"]) == pytest.approx(
                (expected["u"], expected["v"]), abs=1e-8, rel=0
            )

    assert solved_points != draft.sketch["points"]
    preview = draft.preview_delete((("constraint", fixed),))
    before, evidence = store.dumps(draft), draft._solution
    with pytest.raises(d.DraftError, match="current solved placement"):
        draft.execute(d.RecoverRemoveRelation(preview))
    assert store.dumps(draft) == before and draft._solution is evidence
    draft.execute(d.DeleteBatch(preview))
    assert draft.sketch["points"] == solved_points
    success, released = solve(draft)
    assert success and released["result"]["sketch"]["remaining_dof"] == 2
    assert_same_placement(released["result"]["sketch"]["solved"]["points"])
    draft.undo()
    assert draft.sketch["points"] != solved_points
    draft.redo()
    restored = store.restore(store.dumps(draft), draft.document_json)
    assert restored.sketch["points"] == solved_points
    assert not restored.has_current_solution
    assert_same_placement(solve(restored)[1]["result"]["sketch"]["solved"]["points"])
    target = next((row["u"], row["v"]) for row in solved_points if row["id"] == a)
    restored.execute(d.AddRelation("fixed", (a,), target=target))
    assert solve(restored)[1]["result"]["sketch"]["remaining_dof"] == 0
    restored.undo()
    restored.redo()
    assert_same_placement(solve(restored)[1]["result"]["sketch"]["solved"]["points"])


def test_native_reversed_coincident_duplicate_is_a_noop_without_collapsing_a_line():
    draft = d.GeneralSketchDraft(blank())
    a, b, _ = draft.execute(d.AddLine(d.PointSeed(0, 0), d.PointSeed(5, 0))).entity_ids
    c, _ = draft.execute(d.AddLine(d.PointRef(b), d.PointSeed(5, 5))).entity_ids
    draft.execute(d.AddLine(d.PointRef(c), d.PointRef(a)))
    (other,) = draft.execute(d.AddPoint(d.PointSeed(0, 0))).entity_ids
    relation = draft.execute(d.AddRelation("coincident", (a, other))).constraint_id
    success, initial = solve(draft)
    assert success
    before, evidence = store.dumps(draft), draft._solution
    duplicate = draft.execute(d.AddRelation("coincident", (other, a)))
    assert not duplicate.changed and duplicate.constraint_id == relation
    assert store.dumps(draft) == before and draft._solution is evidence
    success, repeated = solve(draft)
    assert success
    assert initial["result"]["sketch"]["solved"] == repeated["result"]["sketch"]["solved"]


@pytest.mark.parametrize(
    "plane",
    [
        {
            "id": "yz",
            "origin": [5, 2, 3],
            "quaternion": [0.7071067811865476, 0, 0.7071067811865476, 0],
        },
        {"id": "offset", "origin": [0, 0, 12], "quaternion": [1, 0, 0, 0]},
    ],
)
def test_general_rectangle_native_dimensions_extrusion_and_plane(plane):
    draft = d.GeneralSketchDraft(blank(), plane=plane)
    draft.execute(d.AddRectangle(d.PointSeed(0, 0), d.PointSeed(20, 10)))
    sketch = draft.sketch
    assert sketch["plane"] == plane
    success, response = solve(draft)
    assert success and response["result"]["sketch"]["remaining_dof"] == 4
    first, second = sketch["lines"][:2]
    width = draft.execute(
        d.AddRelation("distance", (first["start"], first["end"]), value=20)
    ).constraint_id
    draft.execute(d.AddRelation("distance", (second["start"], second["end"]), value=10))
    assert solve(draft)[0]
    draft.begin_edit(width)
    draft.update_edit("30")
    assert solve(draft, trial=True)[0]
    assert draft.accept_driver().changed
    candidate = draft.candidate()
    candidate["features"].append(
        {
            "id": "pad",
            "kind": "extrude",
            "params": {"length": 5},
            "inputs": {"profile": draft.feature_id},
        }
    )
    candidate["active_feature"] = "pad"
    response = process_request(
        {"protocol_version": 1, "action": "replay", "result_version": 2, "document": candidate}
    )
    assert response["ok"], response
    assert response["result"]["status"] == "ok", response
    assert response["result"]["features"][-1]["stats"]["volume"] == pytest.approx(1500)


@pytest.mark.parametrize("remove_arc", [False, True])
def test_command_authored_open_path_sweep_preserves_schema_and_world_placement(remove_arc):
    from mechanical_cad.engine import regenerate
    from mechanical_cad.kernel_ocp import OCPKernel, _shape_bounds

    draft = d.GeneralSketchDraft(
        blank(),
        journal_version=3,
        plane={
            "id": "rail_plane",
            "origin": [7, -4, 11],
            "quaternion": [math.sqrt(0.5), 0, -math.sqrt(0.5), 0],
        },
    )
    a, b, rail = draft.execute(d.AddLine(d.PointSeed(0, 0), d.PointSeed(20, 0))).entity_ids
    draft.execute(d.AddRelation("fixed", (a,), target=(0, 0)))
    draft.execute(d.AddRelation("horizontal", (rail,)))
    draft.execute(d.AddRelation("distance", (a, b), value="radius * 4"))
    relations = draft.sketch["constraints"]
    if remove_arc:
        arc = draft.execute(
            d.AddArc(d.PointSeed(30, 0), d.PointSeed(35, 0), d.PointSeed(30, 5), "ccw")
        ).entity_ids[-1]
        draft.execute(d.DeleteBatch(draft.preview_delete((("arc", arc),))))
        assert draft.sketch["schema_version"] == 3 and draft.sketch["arcs"] == []
    assert draft.sketch["constraints"] == relations
    before = draft.sketch
    success, checked = solve(draft)
    assert success, checked
    assert not checked["result"]["profile_check"]["ready"]
    assert draft.sketch == before
    request = draft.replay_request()
    assert request["result_version"] == (3 if remove_arc else 2)
    response = process_request(request)
    part_bridge = importlib.import_module(
        PACKAGE + (".result_v3" if remove_arc else ".part_result_bridge")
    )
    part_bridge.validate_response(request, response)
    assert response["ok"], response
    assert response["result"]["features"][0]["output"]["profile"]["state"] == "unavailable"
    candidate = draft.candidate()
    candidate["features"].extend(
        [
            {
                "id": "section",
                "kind": "sketch_circle",
                "params": {"radius": 2, "x": 7, "y": -4, "z": 11},
            },
            {
                "id": "rod",
                "kind": "sweep",
                "inputs": {"profile": "section", "path": draft.feature_id},
            },
        ]
    )
    candidate["active_feature"] = "rod"
    document = Document.from_dict(candidate)
    canonical = document.to_json()
    kernel = OCPKernel()
    replay = regenerate(
        Document.from_json(canonical), kernel, result_version=request["result_version"]
    )
    assert replay.ok, replay.result
    shape = replay.shapes["rod"]
    stats = kernel.inspect(shape)
    assert stats["valid"] and stats["solids"] == 1
    assert stats["volume"] == pytest.approx(math.pi * 4 * 20)
    assert _shape_bounds(shape) == pytest.approx((5, -6, 11, 9, -2, 31), abs=1e-7)
    assert kernel.manufacturing_check(shape)["mesh"]["watertight"]
    request["document"] = candidate
    response = process_request(request)
    part_bridge.validate_response(request, response)
    assert response["ok"], response
    assert document.to_json() == canonical
    assert document.features[0].sketch.schema_version == (3 if remove_arc else 2)
    assert draft.sketch == before


def test_unit_radius_driver_native_solve_replay_acceptance_and_json_reopen():
    draft, _, circle, driver, _ = authored_circle()
    candidate = draft.candidate()
    candidate["features"].append(
        {
            "id": "pad",
            "kind": "extrude",
            "params": {"length": 10},
            "inputs": {"profile": draft.feature_id},
        }
    )
    candidate["active_feature"] = "pad"
    base = Document.from_dict(candidate).to_json()
    edited = d.GeneralSketchDraft(base, draft.feature_id, True)
    edited.begin_edit(driver)
    edited.update_edit("1 in")
    assert solve(edited, trial=True)[0]
    request = edited.replay_request(trial=True)
    response = process_request(request)
    assert response["ok"]
    assert response["result"]["features"][-1]["stats"]["volume"] == pytest.approx(
        math.pi * 25.4**2 * 10
    )
    assert edited.accept_driver(replay_request=request, replay_response=response).changed
    assert next(row["value"] for row in edited.sketch["constraints"] if row["id"] == driver) == 25.4
    reopened = d.GeneralSketchDraft(
        Document.from_dict(edited.candidate()).to_json(), draft.feature_id, True
    )
    assert reopened.sketch["circles"][0]["id"] == circle
    assert solve(reopened)[0]
    reopened.begin_edit(driver)
    reopened.update_edit("1 rad")
    with pytest.raises(d.DraftError, match="length field"):
        reopened.trial_candidate()
    assert reopened.pending_edit.raw_text == "1 rad"
    assert (
        next(row["value"] for row in reopened.sketch["constraints"] if row["id"] == driver) == 25.4
    )
