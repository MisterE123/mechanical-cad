"""Native-free Up to Face source, replay, and assembly evidence contracts.

Synthetic geometry below exercises protocol consistency, not native shape fidelity.
"""

import copy
import importlib
import sys
import types
from pathlib import Path

import pytest

ADDON = Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender"
PACKAGE = "mcad_up_to_face_contract_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ADDON)]
sys.modules[PACKAGE] = package
legacy = importlib.import_module(PACKAGE + ".part_contracts")
v3 = importlib.import_module(PACKAGE + ".part_contracts_v3")
replay_v2 = importlib.import_module(PACKAGE + ".part_result_bridge")
replay_v3 = importlib.import_module(PACKAGE + ".result_v3")
assembly_edit = importlib.import_module(PACKAGE + ".assembly_edit")
assembly_model = importlib.import_module(PACKAGE + ".assembly_validation_model")
policy = importlib.import_module(PACKAGE + ".operation_contracts")


def document():
    return {
        "schema_version": 1,
        "id": "part",
        "name": "Up to Face",
        "units": "mm",
        "parameters": {},
        "features": [
            {
                "id": "target_profile",
                "kind": "sketch_rectangle",
                "params": {"width": 20, "height": 20, "z": 10},
            },
            {
                "id": "target",
                "kind": "extrude",
                "params": {"length": 5},
                "inputs": {"profile": "target_profile"},
            },
            {"id": "profile", "kind": "sketch_circle", "params": {"radius": 2}},
            {
                "id": "pad",
                "kind": "extrude_to_face",
                "params": {"direction": 1},
                "inputs": {"profile": "profile", "target": "target"},
                "end_face": "target/face/cap.start",
            },
        ],
        "active_feature": "pad",
    }


@pytest.mark.parametrize("contracts", [legacy, v3])
@pytest.mark.parametrize("direction", [-1, 1, -1.0, 1.0])
@pytest.mark.parametrize("offset", [None, 0, -2.5, "clearance / 2"])
def test_strict_source_defaults_and_authored_formulas_are_detached(contracts, direction, offset):
    raw = document()
    raw["features"][-1]["params"]["direction"] = direction
    if offset is not None:
        raw["features"][-1]["params"]["offset"] = offset
    before = copy.deepcopy(raw)
    canonical = contracts._expected_document(raw)
    assert raw == before
    assert canonical["features"][-1]["params"] == {
        "direction": direction,
        "offset": 0 if offset is None else offset,
    }
    assert canonical["features"][-1]["end_face"] == raw["features"][-1]["end_face"]
    assert canonical["features"][-1]["inputs"] == {"profile": "profile", "target": "target"}
    assert contracts._expected_document(canonical) == canonical
    assert legacy.canonical_equivalent(raw, canonical)


@pytest.mark.parametrize("contracts", [legacy, v3])
@pytest.mark.parametrize("direction", [True, False, 0, 2, -2, "1", "-1", "sign", None])
def test_direction_is_a_required_literal_sign(contracts, direction):
    raw = document()
    raw["features"][-1]["params"]["direction"] = direction
    with pytest.raises(ValueError):
        contracts._expected_document(raw)


@pytest.mark.parametrize("contracts", [legacy, v3])
@pytest.mark.parametrize("face", [None, "", "x" * 513, "snapshot:target:face:0", "pending:face", 1])
def test_end_face_requires_bounded_stable_reference(contracts, face):
    raw = document()
    raw["features"][-1]["end_face"] = face
    with pytest.raises(ValueError):
        contracts._expected_document(raw)


@pytest.mark.parametrize("contracts", [legacy, v3])
@pytest.mark.parametrize(
    "mutation",
    [
        "missing_face",
        "missing_direction",
        "missing_target",
        "extra_input",
        "extra_param",
        "profile_target",
        "solid_profile",
        "missing_profile",
        "missing_solid",
        "self_target",
        "later_target",
        "unexpected_face",
        "boolean_offset",
        "object_offset",
    ],
)
def test_malformed_source_and_non_earlier_solid_targets_fail_closed(contracts, mutation):
    raw = document()
    pad = raw["features"][-1]
    if mutation == "missing_face":
        pad.pop("end_face")
    elif mutation == "missing_direction":
        pad["params"].pop("direction")
    elif mutation == "missing_target":
        pad["inputs"].pop("target")
    elif mutation == "extra_input":
        pad["inputs"]["base"] = "target"
    elif mutation == "extra_param":
        pad["params"]["length"] = 10
    elif mutation == "profile_target":
        pad["inputs"]["target"] = "profile"
    elif mutation == "solid_profile":
        pad["inputs"]["profile"] = "target"
    elif mutation == "missing_profile":
        pad["inputs"]["profile"] = "missing"
    elif mutation == "missing_solid":
        pad["inputs"]["target"] = "missing"
    elif mutation == "self_target":
        pad["inputs"]["target"] = "pad"
    elif mutation == "later_target":
        raw["features"].append(raw["features"].pop(1))
    elif mutation == "unexpected_face":
        raw["features"][1]["end_face"] = pad["end_face"]
    else:
        pad["params"]["offset"] = True if mutation == "boolean_offset" else {}
    with pytest.raises(ValueError):
        contracts._expected_document(raw)


def test_profile_can_follow_extrusion_in_an_acyclic_dag():
    raw = document()
    raw["features"].append(raw["features"].pop(2))
    assert replay_v3.validate_request({"protocol_version": 1, "result_version": 3, "document": raw})


def test_legacy_documents_do_not_acquire_new_fields_or_defaults():
    raw = document()
    raw["features"].pop()
    raw["active_feature"] = "target"
    canonical = legacy._expected_document(raw)
    assert canonical == v3._expected_document(raw)
    assert all(
        "end_face" not in feature and "offset" not in feature["params"]
        for feature in canonical["features"]
    )


def _face(identifier, role, *, profile=False, circle=False):
    relation = (
        "constructed_profile"
        if profile
        else {"cap.start": "first_shape", "cap.end": "last_shape"}.get(
            role, "generated_from_profile_edge"
        )
    )
    cylinder = role == "side.circle"
    return {
        "id": f"{identifier}/face/{role}",
        "feature_id": identifier,
        "role": role,
        "kind": "face",
        "signature": {
            "surface": "cylinder" if cylinder else "plane",
            "area": 1.0,
            "centroid": [0, 0, 0],
            **({"radius": 2, "axis": [0, 0, 1]} if cylinder else {"normal": [0, 0, 1]}),
        },
        "provenance": {
            "semantic_status": "stable",
            "kernel": "OCCT",
            "operation": ("circle" if circle else "rectangle") if profile else "extrude",
            "operation_id": identifier,
            "relation": relation,
            "evolution": relation,
            **({"source_boundary": role.removeprefix("side.")} if role.startswith("side.") else {}),
        },
    }


def replay_pair(version):
    raw = document()
    canonical = legacy._expected_document(raw)
    features = []
    for source in canonical["features"]:
        is_profile = source["kind"].startswith("sketch_")
        circle = source["id"] in {"profile", "pad"}
        roles = (
            ["profile"]
            if is_profile
            else ["cap.start", "cap.end"]
            + (
                ["side.circle"]
                if circle
                else ["side.x_min", "side.x_max", "side.y_min", "side.y_max"]
            )
        )
        topology = [_face(source["id"], role, profile=is_profile, circle=circle) for role in roles]
        features.append(
            {
                **{key: source[key] for key in ("id", "kind", "label", "inputs")},
                "status": "ok",
                "error": None,
                "resolved_params": copy.deepcopy(source["params"]),
                "output": {"kind": "profile" if is_profile else "solid", "display": "mesh"},
                "stats": None
                if is_profile
                else {"valid": True, "volume": 10, "area": 20, "solids": 1, "faces": len(topology)},
                "mesh": {
                    "vertices": [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
                    "triangles": [[0, 1, 2] for _ in topology],
                    "triangle_face_ids": [face["id"] for face in topology],
                },
                "topology": topology,
            }
        )
    request = {"protocol_version": 1, "result_version": version, "document": raw}
    response = {
        "protocol_version": 1,
        "result_version": version,
        "input_fingerprint": legacy.input_fingerprint(request),
        "ok": True,
        "error": None,
        "result": {
            "document_id": "part",
            "document_hash": legacy.document_hash(canonical),
            "active_feature": "pad",
            "status": "ok",
            "units": "mm",
            "parameters": {},
            "features": features,
            "result_version": version,
        },
    }
    return request, response


@pytest.mark.parametrize("version", [2, 3])
def test_prism_results_keep_exact_target_and_ordinary_provenance(version):
    request, response = replay_pair(version)
    validator = replay_v2 if version == 2 else replay_v3
    assert validator.validate_response(request, response) == response


@pytest.mark.parametrize("version", [2, 3])
@pytest.mark.parametrize(
    "mutation",
    [
        "missing_face",
        "other_target",
        "nonplanar",
        "tilted",
        "operation",
        "inherited_target",
        "resolved_direction",
    ],
)
def test_replay_rejects_unrelated_or_nonplanar_target_and_forged_prism_evidence(version, mutation):
    request, response = replay_pair(version)
    features = response["result"]["features"]
    pad, target = features[-1], features[1]
    if mutation in {"missing_face", "other_target"}:
        raw = request["document"]
        if mutation == "missing_face":
            raw["features"][-1]["end_face"] = "target/face/absent"
        else:
            raw["features"][-1]["end_face"] = "pad/face/cap.start"
        response["input_fingerprint"] = legacy.input_fingerprint(request)
        response["result"]["document_hash"] = legacy.document_hash(legacy._expected_document(raw))
    elif mutation == "nonplanar":
        target["topology"][0]["signature"] = {
            "surface": "cylinder",
            "area": 1,
            "centroid": [0, 0, 0],
            "radius": 2,
            "axis": [0, 0, 1],
        }
    elif mutation == "tilted":
        target["topology"][0]["signature"]["normal"] = [1, 0, 0]
    elif mutation == "operation":
        pad["topology"][0]["provenance"]["operation"] = "extrude_to_face"
    elif mutation == "inherited_target":
        pad["topology"][0]["feature_id"] = "target"
    else:
        pad["resolved_params"]["direction"] = -1
    validator = replay_v2 if version == 2 else replay_v3
    with pytest.raises(ValueError):
        validator.validate_response(request, response)


def test_assembly_capture_preserves_reference_and_requires_full_source_replay():
    canonical = legacy._expected_document(document())
    assembly = assembly_edit.new_from_part(canonical)
    assert assembly["part_sources"][0]["document"] == canonical
    assert assembly["part_sources"][0]["document"] is not canonical
    assert assembly["parts"][0]["output_feature_id"] == "pad"
    assert policy.result_version_for_assembly(assembly) == 3
    _, response = replay_pair(2)
    pad = response["result"]["features"][-1]
    assert assembly_model._source_output(pad, canonical["features"][-1]) == pad["output"]
