"""Source-preview hashes are exact comparison hints, never evidence authority."""

import copy
import importlib
from types import SimpleNamespace as NS

import pytest
from test_assembly_publication_binding import PACKAGE, state

contract = importlib.import_module(PACKAGE + ".assembly_source_preview_contract")


@pytest.fixture
def response():
    return {
        "ok": True,
        "result": {
            "canonical_assembly": {"id": "a", "name": "Assembly"},
            "assembly_digest": "a" * 64,
            "source_hashes": {"source": "b" * 64},
            "instances": [{"id": "instance", "part_id": "part"}],
            "parts": [
                {
                    "id": "part",
                    "mesh": {"vertices": [[0, 1, 2]], "triangles": [[0, 0, 0]]},
                    "topology": [{"id": "face"}],
                    "resolved_mate_frames": {"origin": {"xyz_mm": [0, 0, 0]}},
                    "datum_policy": "stable_planar_face_or_literal",
                }
            ],
            "source_replays": [
                {"id": "source", "replay": {"features": [{"id": "f", "status": "ok"}]}}
            ],
        },
        "report": {
            "base_pose": {
                "transforms": {"instance": {"xyz_mm": [0, 0, 0]}},
                "effective_coordinates": {"joint": 0},
            }
        },
    }


@pytest.mark.parametrize(
    "change",
    [
        "geometry",
        "topology",
        "mates",
        "datum",
        "source-replay",
        "pose",
        "canonical",
        "instance",
        "digest",
        "source-hash",
        "bool-int",
        "ordered-list",
    ],
)
def test_each_complete_projection_field_changes_digest(response, change):
    before = copy.deepcopy(response)
    expected = contract.source_preview_fingerprint(response)
    result = response["result"]
    if change == "geometry":
        result["parts"][0]["mesh"]["vertices"][0][0] = 1
    elif change == "topology":
        result["parts"][0]["topology"][0]["id"] = "other"
    elif change == "mates":
        result["parts"][0]["resolved_mate_frames"]["origin"]["xyz_mm"][0] = 1
    elif change == "datum":
        result["parts"][0]["datum_policy"] = "literal_part_local_coordinates"
    elif change == "source-replay":
        result["source_replays"][0]["replay"]["features"][0]["status"] = "failed"
    elif change == "pose":
        response["report"]["base_pose"]["transforms"]["instance"]["xyz_mm"][0] = 1
    elif change == "canonical":
        result["canonical_assembly"]["name"] = "Changed"
    elif change == "instance":
        result["instances"][0]["part_id"] = "other"
    elif change == "digest":
        result["assembly_digest"] = "c" * 64
    elif change == "source-hash":
        result["source_hashes"]["source"] = "c" * 64
    elif change == "bool-int":
        result["parts"][0]["mesh"]["vertices"][0][0] = False
    else:
        result["parts"][0]["mesh"]["vertices"][0].reverse()
    assert contract.source_preview_fingerprint(response) != expected
    with pytest.raises(state.bridge.BridgeError, match="differs"):
        contract.require_source_preview(response, expected)
    assert contract.source_preview_fingerprint(before) == expected


@pytest.mark.parametrize(
    "change",
    [
        "missing-field",
        "tuple",
        "nan",
        "non-string-key",
        "empty-pose",
        "missing-pose",
        "bool-list",
        "bad-hash",
        "failed",
    ],
)
def test_invalid_projection_fails_closed(response, change):
    if change == "missing-field":
        del response["result"]["source_replays"]
    elif change == "tuple":
        response["result"]["parts"][0]["mesh"]["vertices"] = ((0, 1, 2),)
    elif change == "nan":
        response["result"]["parts"][0]["mesh"]["vertices"][0][0] = float("nan")
    elif change == "non-string-key":
        response["result"]["parts"][0][1] = "coerced"
    elif change == "empty-pose":
        response["report"]["base_pose"] = {}
    elif change == "missing-pose":
        del response["report"]["base_pose"]
    elif change == "bool-list":
        response["result"]["instances"] = True
    elif change == "bad-hash":
        response["result"]["assembly_digest"] = True
    else:
        response["ok"] = False
    with pytest.raises(state.bridge.BridgeError):
        contract.source_preview_fingerprint(response)


@pytest.mark.parametrize("digest", [True, 1, b"a" * 64, "A" * 64, "a" * 63, "g" * 64])
def test_expected_digest_must_be_immutable_exact_hex(response, digest):
    with pytest.raises(state.bridge.BridgeError):
        contract.require_source_preview(response, digest)


def test_mapping_order_and_unprojected_request_metadata_do_not_change_digest(response):
    before = copy.deepcopy(response)
    digest = contract.source_preview_fingerprint(response)
    response["result"] = dict(reversed(list(response["result"].items())))
    response["request_id"] = "fresh request"
    response["report"]["timing"] = 3
    assert contract.source_preview_fingerprint(response) == digest
    assert before != response


@pytest.mark.parametrize("change", ["same", "geometry", "pose", "invalid-digest", "guard-fails"])
def test_commit_sink_compares_after_guard_before_stage_without_canonical_mutation(
    response, monkeypatch, change
):
    expected = contract.source_preview_fingerprint(response)
    if change == "geometry":
        response["result"]["parts"][0]["mesh"]["vertices"][0][0] = 2
    if change == "pose":
        response["report"]["base_pose"]["effective_coordinates"]["joint"] = 2
    if change == "invalid-digest":
        expected = True
    storage = NS(owner_id="owner", document_json="unchanged canonical")
    scene = NS(mechanical_cad_assembly=storage)
    context = NS(scene=scene)
    calls = []
    monkeypatch.setattr(state, "_key", lambda scene: "scene")
    monkeypatch.setattr(state, "_BUSY", {"scene"})
    monkeypatch.setattr(state, "_recover_failure", lambda *a, **kw: None)
    monkeypatch.setattr(state, "_assert_current", lambda *a, **kw: calls.append("guard"))

    def projection(*args, **kwargs):
        calls.append("projection")
        if change == "guard-fails":
            raise state.bridge.BridgeError("Evidence revoked")
        return copy.deepcopy(response)

    def stage(*args, **kwargs):
        calls.append("stage")
        raise state.bridge.BridgeError("stage sentinel")

    monkeypatch.setattr(state, "_projection", projection)
    monkeypatch.setattr(state.assembly_display, "stage", stage, raising=False)
    before = vars(storage).copy()
    with pytest.raises(state.bridge.BridgeError):
        state._commit_candidate_evidence(
            context,
            {"owner_token": object()},
            object(),
            scene=scene,
            expected_source_preview=expected,
        )
    assert calls == (
        ["guard", "projection", "stage"] if change == "same" else ["guard", "projection"]
    )
    assert vars(storage) == before
