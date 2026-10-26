"""Native geometry and strict independent evidence for explicit source ports."""

import copy
import sys
from pathlib import Path

import pytest
from test_solid_edge_projection import bridge

from mechanical_cad.model import Document, load_document, save_document
from mechanical_cad.projection_repair import replace_reference
from mechanical_cad.sidecar import process_request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from multi_source_cases import mixed_sources, two_sketch_sources, two_solid_sources  # noqa: E402
from staged_edit_cases import feature  # noqa: E402


def replay(data, version=3):
    request = {"protocol_version": 1, "result_version": version, "document": data}
    response = process_request(request)
    bridge()[version - 2].validate_response(request, response)
    return response


@pytest.mark.parametrize("fixture", [two_sketch_sources, mixed_sources, two_solid_sources])
@pytest.mark.parametrize("version", [2, 3])
def test_native_sources_replay_solve_persist_and_regenerate(tmp_path, fixture, version):
    data = fixture()
    result = replay(data, version)
    assert result["ok"], result
    target = next(r for r in result["result"]["features"] if r["id"] == "target")
    if fixture is two_solid_sources:
        edges = target["projection_edges"]
        assert set(edges) == {"external", "external_2"}
        assert edges["external"][0]["faces"] == edges["external_2"][0]["faces"]
        assert edges["external"][0]["center"] != edges["external_2"][0]["center"]
    request = {
        "protocol_version": 1,
        "result_version": version,
        "action": "solve_sketch",
        "feature_id": "target",
        "document": data,
    }
    solved = process_request(request)
    assert solved["ok"], solved
    if version == 3:
        bridge()[1].validate_response(request, solved)
    path = tmp_path / "sources.mcad.json"
    save_document(Document.from_dict(data), path)
    restored = load_document(path).to_dict()
    assert restored == Document.from_dict(data).to_dict()
    assert replay(restored, version)["ok"]
    if fixture is two_sketch_sources:
        feature(restored, "source_two")["sketch"]["constraints"][-1]["value"] = 7
    else:
        feature(restored, "rim_profile")["params"]["radius"] = 11
    changed = replay(restored, version)
    assert changed["ok"], changed
    target_after = next(r for r in changed["result"]["features"] if r["id"] == "target")
    assert target_after["sketch"]["solved"] != target["sketch"]["solved"]


@pytest.mark.parametrize(
    "change", ["missing", "unused", "forward", "cycle", "wrong_kind", "shared_point"]
)
def test_invalid_sources_fail_closed(change):
    data = two_sketch_sources()
    target = feature(data, "target")
    if change == "missing":
        data["features"] = [f for f in data["features"] if f["id"] != "source_two"]
    elif change == "unused":
        target["inputs"]["external_3"] = "source"
    elif change == "forward":
        source = feature(data, "source_two")
        data["features"].remove(source)
        data["features"].append(source)
    elif change == "cycle":
        target["inputs"]["external_2"] = "solid"
    elif change == "wrong_kind":
        data["features"].insert(
            0, {"id": "primitive", "kind": "sketch_circle", "params": {"radius": 3}, "inputs": {}}
        )
        target["inputs"]["external_2"] = "primitive"
    else:
        target["sketch"]["circles"][2]["center"] = "q"
    if change == "shared_point":
        response = process_request({"protocol_version": 1, "result_version": 3, "document": data})
        assert not response["ok"]
    else:
        with pytest.raises(ValueError):
            Document.from_dict(data)
        with pytest.raises(ValueError):
            bridge()[1].validate_request(
                {"protocol_version": 1, "result_version": 3, "document": data}
            )


def test_replacement_cannot_switch_bound_port_or_feature():
    data = two_sketch_sources()
    result = replay(data)
    solved = next(r for r in result["result"]["features"] if r["id"] == "source_two")["sketch"][
        "solved"
    ]
    with pytest.raises(ValueError, match="bound source"):
        replace_reference(
            data,
            "target",
            "reference2",
            {"source": "ring"},
            source_id="source",
            source_solved=solved,
        )
    with pytest.raises(ValueError, match="source fields"):
        replace_reference(
            data,
            "target",
            "reference2",
            {"source": "ring", "input": "external"},
            source_id="source_two",
            source_solved=solved,
        )
    fixed = replace_reference(
        data,
        "target",
        "reference2",
        {"source": "ring"},
        source_id="source_two",
        source_solved=solved,
    )
    assert feature(fixed, "target")["projections"][1]["input"] == "external_2"
    assert feature(fixed, "target")["inputs"] == feature(data, "target")["inputs"]
    assert replay(fixed)["ok"]


def test_same_face_labels_do_not_allow_swapping_bound_source_evidence():
    data = two_solid_sources()
    request = {"protocol_version": 1, "result_version": 3, "document": data}
    response = process_request(request)
    target = next(r for r in response["result"]["features"] if r["id"] == "target")
    swapped = copy.deepcopy(response)
    changed = next(r for r in swapped["result"]["features"] if r["id"] == "target")
    changed["projection_edges"]["external"] = target["projection_edges"]["external_2"]
    with pytest.raises(ValueError):
        bridge()[1].validate_response(request, swapped)


def test_legacy_projection_rows_are_not_implicitly_rewritten():
    data = two_sketch_sources()
    target = feature(data, "target")
    legacy = copy.deepcopy(target["projections"][0])
    restored = Document.from_dict(data).to_dict()
    assert feature(restored, "target")["projections"][0] == legacy
    assert "input" not in feature(restored, "target")["projections"][0]


@pytest.mark.parametrize("port", ["external_1", "external_02", "other", "external_0"])
def test_noncanonical_projection_ports_are_rejected(port):
    data = two_sketch_sources()
    target = feature(data, "target")
    target["inputs"][port] = target["inputs"].pop("external_2")
    target["projections"][1]["input"] = port
    with pytest.raises(ValueError):
        Document.from_dict(data)


def test_distinct_ports_cannot_alias_same_source():
    data = two_sketch_sources()
    feature(data, "target")["inputs"]["external_2"] = "source"
    with pytest.raises(ValueError, match="distinct earlier"):
        Document.from_dict(data)


def test_legacy_dependency_order_meaning_is_preserved():
    from staged_edit_cases import same_sketch_projection_case

    data, _ = same_sketch_projection_case()
    source = feature(data, "source")
    data["features"].remove(source)
    data["features"].append(source)
    assert replay(data)["ok"]


@pytest.mark.parametrize("version", [2, 3])
def test_coordinated_wrong_source_geometry_rejects_against_genuine_source_rows(version):
    data = two_solid_sources()
    request = {"protocol_version": 1, "result_version": version, "document": data}
    honest = process_request(request)
    swapped_data = copy.deepcopy(data)
    inputs = feature(swapped_data, "target")["inputs"]
    inputs["external"], inputs["external_2"] = inputs["external_2"], inputs["external"]
    wrong = process_request({**request, "document": swapped_data})
    wrong["input_fingerprint"] = honest["input_fingerprint"]
    wrong["result"]["document_hash"] = honest["result"]["document_hash"]
    target = next(row for row in wrong["result"]["features"] if row["id"] == "target")
    target["inputs"] = feature(data, "target")["inputs"]
    for source_id in ("moved_one", "moved_two"):
        assert next(row for row in honest["result"]["features"] if row["id"] == source_id) == next(
            row for row in wrong["result"]["features"] if row["id"] == source_id
        )
    with pytest.raises(ValueError, match="bound source cylinder"):
        bridge()[version - 2].validate_response(request, wrong)


def test_optional_axis_evidence_preserves_legacy_reference_and_response_meaning():
    from staged_edit_cases import same_sketch_projection_case

    data = two_solid_sources()
    canonical_before = Document.from_dict(data).to_json()
    response = replay(data)
    assert Document.from_dict(data).to_json() == canonical_before
    for row in response["result"]["features"]:
        for face in row["topology"]:
            face["signature"].pop("axis_origin", None)
    # Prior native transcripts remain readable; stronger incidence applies when present.
    request = {"protocol_version": 1, "result_version": 3, "document": data}
    bridge()[1].validate_response(request, response)
    old_data, _ = same_sketch_projection_case()
    assert replay(old_data)["ok"]


@pytest.mark.parametrize("origin", [[0, 0], [0, 0, float("nan")], [0, 0, "bad"]])
def test_cylinder_axis_origin_is_strict_finite_evidence(origin):
    data = two_solid_sources()
    request = {"protocol_version": 1, "result_version": 3, "document": data}
    response = process_request(request)
    row = next(row for row in response["result"]["features"] if row["id"] == "moved_one")
    next(face for face in row["topology"] if face["signature"]["surface"] == "cylinder")[
        "signature"
    ]["axis_origin"] = origin
    with pytest.raises(ValueError):
        bridge()[1].validate_response(request, response)


def test_exact_cylinder_incidence_accepts_reversed_axis_and_face_normal():
    data = two_solid_sources()
    request = {"protocol_version": 1, "result_version": 3, "document": data}
    response = process_request(request)
    for row in response["result"]["features"]:
        if row["id"] not in {"moved_one", "moved_two"}:
            continue
        for face in row["topology"]:
            signature = face["signature"]
            key = "axis" if signature["surface"] == "cylinder" else "normal"
            signature[key] = [-v for v in signature[key]]
    bridge()[1].validate_response(request, response)
