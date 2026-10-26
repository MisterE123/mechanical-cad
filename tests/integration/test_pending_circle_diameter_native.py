"""Direct diameter candidates through the real isolated-development solver/kernel.

These core/state checks do not establish Blender owner or interactive GUI behavior.
"""
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
PACKAGE = "mcad_diameter_native_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
sys.modules[PACKAGE] = package
a, c, d, p, s = [importlib.import_module(PACKAGE + "." + name) for name in (
    "general_authoring", "general_sketch_commands", "general_sketch_draft",
    "pending_circle_diameter", "draft_dispatch")]
BASE = '{"schema_version":1,"id":"doc","name":"Part","units":"mm","parameters":{},"features":[],"active_feature":null}'


def solve(commands, *, trial=False):
    request = commands.solve_request(trial=trial)
    response = process_request(request)
    assert response["ok"], response
    return request, response


def solved(response):
    return response["result"]["sketch"]["solved"]


@pytest.mark.parametrize("raw,radius", [("20", 10), ("2 cm", 10), ("0.5 in", 6.35)])
def test_native_first_diameter_retains_center_and_creates_only_radius_driver(raw, radius):
    original = a.GeneralSketchAuthoringState(d.GeneralSketchDraft(BASE))
    original.begin_circle(c.PointSeed(3, 4))
    original.begin_pending_diameter({}, raw_text=raw)
    snapshot = s.dumps(original)
    candidate, receipt = p.prepare_diameter_candidate(original)
    _, response = solve(candidate.command_draft)
    result = solved(response)
    assert result["points"][0]["u"] == pytest.approx(3, abs=1e-7)
    assert result["points"][0]["v"] == pytest.approx(4, abs=1e-7)
    assert result["circles"][0]["radius"] == pytest.approx(radius, abs=1e-7)
    assert response["result"]["sketch"]["remaining_dof"] == 2
    assert len(candidate.command_draft.sketch["constraints"]) == 1
    assert candidate.command_draft.sketch["constraints"][0]["id"] == receipt.constraint_id
    assert s.dumps(original) == snapshot and original.document_json == BASE


def test_native_reused_center_and_existing_driven_and_free_circle_sizes_stay_put():
    commands = d.GeneralSketchDraft(BASE)
    center, circle = commands.execute(c.AddCircle(c.PointSeed(0, 0), 9)).entity_ids
    commands.execute(c.AddRelation("fixed", (center,), target=(10, 20)))
    commands.execute(c.AddRelation("radius", (circle,), value=7))
    commands.execute(c.AddCircle(c.PointSeed(40, 50), 6))
    _, baseline = solve(commands)
    before = solved(baseline)
    points = {point["id"]: (point["u"], point["v"]) for point in before["points"]}
    original = a.GeneralSketchAuthoringState(commands)
    original.begin_circle(c.PointRef(center))
    original.begin_pending_diameter(points, raw_text="4 mm")
    candidate, _ = p.prepare_diameter_candidate(original)
    _, response = solve(candidate.command_draft)
    after = solved(response)
    assert after["points"] == before["points"]
    assert after["circles"][:-1] == before["circles"]
    assert after["circles"][-1]["radius"] == pytest.approx(2)
    assert after["circles"][-1]["center"] == center
    assert candidate.command_draft.candidate()["parameters"] == {}


def test_native_diameter_driver_replays_exact_cylinder_and_remains_formula_editable():
    commands = d.GeneralSketchDraft(BASE)
    receipt = commands.execute(c.AddDiameterCircle(c.PointSeed(3, 4), 20))
    document = commands.candidate()
    document["features"].append({"id": "pad", "kind": "extrude", "params": {"length": 5},
                                 "inputs": {"profile": commands.feature_id}})
    document["active_feature"] = "pad"
    base = Document.from_dict(document).to_json()
    commands = d.GeneralSketchDraft(base, commands.feature_id, True)
    response = process_request(commands.replay_request())
    assert response["ok"], response
    assert response["result"]["features"][-1]["stats"]["volume"] == pytest.approx(math.pi * 100 * 5)
    commands.begin_edit(receipt.constraint_id)
    commands.update_edit("10 + 2")
    request, response = solve(commands, trial=True)
    assert commands.record_validated_solution(request, response, commands.revision,
                                              expected_input_revision=commands.pending_edit.input_revision)
    with pytest.raises(c.DraftError, match="full replay"):
        commands.accept_driver()
    request = commands.replay_request(trial=True)
    response = process_request(request)
    assert response["ok"], response
    assert response["result"]["features"][-1]["stats"]["volume"] == pytest.approx(math.pi * 144 * 5)
    assert commands.accept_driver(replay_request=request, replay_response=response).changed
    assert commands.document_json == base


def test_native_consumed_disjoint_circle_is_draft_only_and_final_replay_refuses():
    base = (ROOT / "examples/viewport_rectangle.mcad.json").read_text()
    original = a.GeneralSketchAuthoringState(d.GeneralSketchDraft(base, "sketch_1", True))
    _, baseline = solve(original.command_draft)
    original.begin_circle(c.PointSeed(100, 100))
    original.begin_pending_diameter({}, raw_text="5 mm")
    candidate, _ = p.prepare_diameter_candidate(original)
    _, response = solve(candidate.command_draft)
    assert solved(response)["points"][:-1] == solved(baseline)["points"]
    replay = process_request(candidate.command_draft.replay_request())
    assert not replay["ok"]
    assert candidate.document_json == original.document_json == base
    assert json.loads(base)["active_feature"] == "extrude_1"
