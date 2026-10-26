"""Proposal staging preserves real validated evidence only on the original draft."""

import importlib
import json
import sys
import types
from pathlib import Path
from unittest.mock import patch

import pytest

pytest.importorskip("slvs")

from mechanical_cad.sidecar import process_request

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "mcad_proposal_native_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
sys.modules[PACKAGE] = package
d = importlib.import_module(PACKAGE + ".general_sketch_draft")
a = importlib.import_module(PACKAGE + ".general_authoring")
s = importlib.import_module(PACKAGE + ".general_authoring_store")
p = importlib.import_module(PACKAGE + ".general_proposals")


@pytest.mark.parametrize("fail_serialization", [False, True])
def test_staging_never_revokes_or_copies_original_native_evidence(fail_serialization):
    base = json.dumps(
        {
            "schema_version": 1,
            "id": "proposal_part",
            "name": "Proposal Part",
            "units": "mm",
            "parameters": {},
            "features": [],
            "active_feature": None,
        }
    )
    state = a.GeneralSketchAuthoringState(d.GeneralSketchDraft(base))
    command = state.command_draft
    center, circle = command.execute(d.AddCircle(d.PointSeed(0, 0), 5)).entity_ids
    command.execute(d.AddRelation("fixed", (center,), target=(0, 0)))
    command.execute(d.AddRelation("radius", (circle,), value=5))
    request = command.solve_request()
    response = process_request(request)
    assert response["ok"] and response["result"]["sketch"]["remaining_dof"] == 0
    assert command.record_validated_solution(request, response, command.revision)
    state.begin_line(d.PointSeed(0, 0), (6, 8))
    assert command.has_current_solution
    before = s.dumps(state)
    solution = command._solution
    if fail_serialization:
        real = s.dumps

        def fail_candidate(value):
            if value is not state:
                raise s.SnapshotError("Injected combined persistence failure")
            return real(value)

        with patch.object(s, "dumps", side_effect=fail_candidate):
            with pytest.raises(s.SnapshotError, match="persistence"):
                p.prepare_proposal(state)
    else:
        candidate = p.prepare_proposal(state).replacement(state)
        assert not candidate.command_draft.has_current_solution
        assert candidate.revision == state.revision + 1
        assert candidate.proposal is None
    assert command.has_current_solution and command._solution is solution
    assert s.dumps(state) == before

@pytest.mark.parametrize("axis,end,fixed", [("horizontal", (10, 0), 1), ("vertical", (0, 10), 0)])
def test_explicit_axis_line_has_real_solver_constraint(axis, end, fixed):
    base = json.dumps({"schema_version": 1, "id": "part", "name": "Part", "units": "mm",
                       "parameters": {}, "features": [], "active_feature": None})
    state = a.GeneralSketchAuthoringState(d.GeneralSketchDraft(base))
    state.begin_line(d.PointSeed(0, 0))
    state = p.prepare_point_input(state, d.PointSeed(*end), axis=axis).replacement(state)
    command = state.command_draft
    request = command.solve_request()
    response = process_request(request)
    assert response["ok"], response
    assert response["result"]["sketch"]["remaining_dof"] == 3
    assert command.record_validated_solution(request, response, command.revision)
    solved = response["result"]["sketch"]["solved"]["points"]
    key = "v" if fixed else "u"
    assert solved[0][key] == pytest.approx(solved[1][key], abs=1e-9)
