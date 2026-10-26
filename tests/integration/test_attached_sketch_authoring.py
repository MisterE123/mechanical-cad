"""Real drawn attached draft roundtrip, solve and upstream-motion contracts."""

import copy
import importlib
import json
import sys
import types
from pathlib import Path

import pytest

from mechanical_cad.sidecar import process_request

package = types.ModuleType("mcad_attached_authoring_tests")
package.__path__ = [
    str(Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender")
]
sys.modules[package.__name__] = package
D = importlib.import_module(package.__name__ + ".general_sketch_draft")
A = importlib.import_module(package.__name__ + ".general_authoring")
S = importlib.import_module(package.__name__ + ".draft_dispatch")
G = importlib.import_module(package.__name__ + ".general_view_geometry")
E = importlib.import_module(package.__name__ + ".sketch_support_evidence")


def base_document():
    return {
        "schema_version": 2,
        "id": "part",
        "name": "Part",
        "units": "mm",
        "parameters": {"height": 10},
        "active_feature": "block",
        "features": [
            {
                "id": "base",
                "kind": "sketch_rectangle",
                "label": "Base",
                "params": {"width": 20, "height": 20},
                "inputs": {},
            },
            {
                "id": "block",
                "kind": "extrude",
                "label": "Block",
                "params": {"length": "height"},
                "inputs": {"profile": "base"},
            },
        ],
    }


@pytest.mark.parametrize("journal_version", [2, 3])
def test_drawn_face_roundtrip_local_history_and_world_solve(journal_version):
    original = json.dumps(base_document())
    draft = D.GeneralSketchDraft(
        original,
        journal_version=journal_version,
        support={"feature_id": "block", "face_id": "block/face/cap.end"},
    )
    local_plane = copy.deepcopy(draft.sketch["plane"])
    draft.execute(D.AddCircle(D.PointSeed(0, 0), 2))
    draft.undo()
    draft.redo()
    authoring = A.GeneralSketchAuthoringState(draft, ui_version=1 if journal_version == 2 else 2)
    serialized = S.dumps(authoring)
    restored = S.restore(serialized, original)
    assert S.dumps(restored) == serialized
    draft = restored.command_draft
    candidate = draft.candidate()
    feature = candidate["features"][-1]
    assert feature["inputs"] == {"support": "block"}
    assert feature["support_face"] == "block/face/cap.end"
    request = draft.solve_request()
    response = process_request(request)
    assert response["ok"], response
    geometry = G.build_geometry(
        draft.sketch, source="solved", solve_request=request, solve_response=response
    )
    assert geometry.plane.origin_mm == pytest.approx((10, 10, 10))
    assert draft.sketch["plane"] == local_plane
    candidate["parameters"]["height"] = 25
    request["document"] = candidate
    response = process_request(request)
    assert response["ok"], response
    assert response["result"]["sketch"]["solved"]["plane"]["origin"] == pytest.approx([10, 10, 25])
    edited = D.GeneralSketchDraft(
        json.dumps(candidate), feature["id"], True, journal_version=journal_version
    )
    assert edited.candidate()["features"][-1]["support_face"] == feature["support_face"]
    assert edited.sketch["plane"] == local_plane
    with pytest.raises(ValueError):
        S.restore(serialized, json.dumps(candidate))


def test_legacy_checkpoint_has_no_support_field():
    draft = D.GeneralSketchDraft(json.dumps(base_document()))
    assert "support" not in draft.checkpoint_payload()


def test_snapshot_cannot_silently_drop_invalid_support():
    draft = D.GeneralSketchDraft(json.dumps(base_document()))
    state = draft.checkpoint_payload()
    state["support"] = None
    with pytest.raises(ValueError):
        D.GeneralSketchDraft.from_checkpoint_payload(state)
    state["support"] = {"feature_id": "block", "face_id": "block/face/cap.end", "unknown": True}
    with pytest.raises(ValueError):
        D.GeneralSketchDraft.from_checkpoint_payload(state)


@pytest.mark.parametrize("journal_version", [2, 3])
def test_rectangle_on_attached_face_native_solve_extrude_and_upstream_motion(journal_version):
    draft = D.GeneralSketchDraft(
        json.dumps(base_document()),
        journal_version=journal_version,
        support={"feature_id": "block", "face_id": "block/face/cap.end"},
    )
    draft.execute(D.AddRectangle(D.PointSeed(-4, -3), D.PointSeed(4, 3)))
    authoring = A.GeneralSketchAuthoringState(draft, ui_version=1 if journal_version == 2 else 2)
    draft = S.restore(S.dumps(authoring), draft.document_json).command_draft
    request = draft.solve_request()
    solved = process_request(request)
    assert solved["ok"], solved
    assert solved["result"]["sketch"]["solved"]["plane"]["origin"] == pytest.approx([10, 10, 10])
    candidate = draft.candidate()
    candidate["features"].append(
        {
            "id": "boss",
            "kind": "extrude",
            "params": {"length": 5},
            "inputs": {"profile": draft.feature_id},
        }
    )
    candidate["active_feature"] = "boss"
    for height in (10, 25):
        candidate["parameters"]["height"] = height
        response = process_request(
            {"protocol_version": 1, "action": "replay", "result_version": 2, "document": candidate}
        )
        assert response["ok"] and response["result"]["status"] == "ok", response
        assert response["result"]["features"][-1]["stats"]["volume"] == pytest.approx(240)
        assert response["result"]["features"][-2]["sketch"]["solved"]["plane"]["origin"][
            2
        ] == pytest.approx(height)
