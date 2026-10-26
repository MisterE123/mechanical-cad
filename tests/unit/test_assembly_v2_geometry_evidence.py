"""Strict v2 assembly evidence; synthetic fixtures never certify native geometry."""

import copy
import importlib
import subprocess
import sys
from dataclasses import replace

import pytest
from test_assembly_bridge_v2 import ADDON, PACKAGE, Kernel, assembly, bridge, seal
from test_assembly_bridge_v2 import make as make  # noqa: F401

from mechanical_cad import assembly_service
from mechanical_cad.assembly_model import PartSource, replace_source
from mechanical_cad.model import Document

model = importlib.import_module(PACKAGE + ".assembly_validation_model")


def part(response):
    return response["result"]["parts"][0]


def summary(response, index=-1):
    return response["result"]["source_replays"][0]["features"][index]


def set_nested(path, value):
    def change(response):
        target = response
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value

    return change


PART = ("result", "parts", 0)
SOLID = ("result", "source_replays", 0, "features", -1)
PROFILE = ("result", "source_replays", 0, "features", 0)


@pytest.mark.parametrize(
    "change",
    [
        set_nested(SOLID + ("stats",), None),
        set_nested(SOLID + ("stats",), {}),
        set_nested(SOLID + ("stats", "volume"), 0),
        set_nested(SOLID + ("stats", "area"), -1),
        set_nested(SOLID + ("stats", "valid"), False),
        set_nested(SOLID + ("stats", "solids"), True),
        set_nested(SOLID + ("stats", "faces"), 1.0),
        set_nested(SOLID + ("stats", "faces"), 900000),
        set_nested(SOLID + ("stats", "extra"), True),
        set_nested(SOLID + ("error",), {"code": "failed", "message": "Actually failed"}),
        set_nested(SOLID + ("output",), None),
        set_nested(SOLID + ("output",), {"kind": "profile", "display": "mesh"}),
        set_nested(SOLID + ("output", "extra"), True),
        set_nested(PROFILE + ("stats",), {"valid": True}),
        set_nested(PROFILE + ("output",), {"kind": "solid", "display": "mesh"}),
        set_nested(PROFILE + ("output", "profile", "state"), "unknown"),
        set_nested(PROFILE + ("output", "profile", "region_kind"), "line_loop"),
        set_nested(PART + ("topology",), ["malformed"]),
        set_nested(PART + ("topology",), []),
        set_nested(PART + ("topology", 0, "signature"), "not an object"),
        set_nested(PART + ("topology", 0, "signature", "area"), -1),
        set_nested(PART + ("topology", 0, "signature", "normal"), [0, 0, 2]),
        set_nested(PART + ("topology", 0, "signature", "unknown"), True),
        set_nested(PART + ("topology", 0, "feature_id"), "unrelated"),
        set_nested(PART + ("topology", 0, "provenance", "operation_id"), "wrong"),
        set_nested(PART + ("topology", 0, "provenance", "kernel"), "invented"),
        set_nested(PART + ("topology", 0, "provenance", "semantic_status"), "unknown"),
        set_nested(PART + ("topology", 0, "provenance", "extra"), True),
        set_nested(PART + ("mesh", "triangle_face_ids", 0), "unrelated"),
        set_nested(PART + ("mesh", "triangle_face_ids", 0), None),
        set_nested(PART + ("geometry_check", "brep", "area"), -1),
        set_nested(PART + ("geometry_check", "brep", "volume"), 2),
        set_nested(PART + ("geometry_check", "brep", "faces"), 4),
        set_nested(PART + ("geometry_check", "brep", "extra"), True),
        set_nested(PART + ("geometry_check", "mesh", "triangles"), "wrong"),
        set_nested(PART + ("geometry_check", "mesh", "triangles"), 100),
        set_nested(PART + ("geometry_check", "mesh", "vertices"), 9000),
        set_nested(PART + ("geometry_check", "mesh", "signed_volume"), -1),
        set_nested(PART + ("geometry_check", "mesh", "weld_tolerance"), 0),
        set_nested(PART + ("geometry_check", "mesh", "extra"), True),
        lambda r: r["result"]["source_replays"][0]["features"].reverse(),
        lambda r: part(r)["topology"].append(copy.deepcopy(part(r)["topology"][0])),
        lambda r: summary(r).pop("output"),
    ],
)
def test_v2_rejects_contradictory_or_malformed_evidence_after_rehash(make, change):
    request, response, _ = make()
    assert bridge.validate_response(request, response)["ok"]
    change(response)
    seal(response)
    with pytest.raises(bridge.bridge.BridgeError, match="Malformed assembly"):
        bridge.validate_response(request, response)


@pytest.mark.parametrize(
    "change",
    [
        set_nested(SOLID + ("stats",), None),
        set_nested(SOLID + ("error",), {"code": "failed", "message": "Actually failed"}),
        set_nested(PART + ("topology",), ["malformed"]),
        set_nested(PART + ("topology", 0, "signature"), "malformed"),
        set_nested(PART + ("mesh", "triangle_face_ids", 0), "unrelated"),
        set_nested(PART + ("geometry_check", "brep", "area"), -1),
        set_nested(PART + ("geometry_check", "mesh", "triangles"), "wrong"),
        set_nested(PART + ("geometry_check", "mesh", "extra"), True),
    ],
)
def test_legacy_one_acceptance_remains_deliberately_unchanged(make, change):
    request, response, _ = make(new_sketch=False, result_version=1)
    change(response)
    seal(response)
    assert bridge.validate_response(request, response)["ok"]


def validate_parts(response, *, complete=False):
    result = response["result"]
    canonical = result["canonical_assembly"]
    definitions = {definition["id"]: definition for definition in canonical["parts"]}
    return model._parts(result, canonical, definitions, complete, strict=True)


def blocked(response):
    response["result"]["parts"] = []
    replay = response["result"]["source_replays"][0]
    replay["status"] = "failed"
    summary(response).update(
        status="failed",
        stats=None,
        output=None,
        error={"code": "kernel_error", "message": "No solid"},
    )
    return response


@pytest.mark.parametrize(
    "change",
    [
        set_nested(SOLID + ("stats",), {"valid": True}),
        set_nested(SOLID + ("output",), {"kind": "solid", "display": "mesh"}),
        set_nested(SOLID + ("error",), None),
        set_nested(SOLID + ("error",), {"code": "bad", "message": ""}),
        set_nested(("result", "source_replays", 0, "status"), "ok"),
    ],
)
def test_failed_summaries_require_null_outputs_stats_and_readable_error(make, change):
    _, response, _ = make()
    blocked(response)
    validate_parts(response)
    change(response)
    with pytest.raises(ValueError):
        validate_parts(response)


def test_successful_dependent_cannot_survive_failed_profile(make):
    _, response, _ = make()
    response["result"]["parts"] = []
    response["result"]["source_replays"][0]["status"] = "failed"
    summary(response, 0).update(
        status="failed",
        stats=None,
        output=None,
        error={"code": "sketch_solve_failed", "message": "Conflicting"},
    )
    with pytest.raises(ValueError, match="failed or blocked dependency"):
        validate_parts(response)
    summary(response).update(
        status="blocked",
        stats=None,
        output=None,
        error={"code": "upstream_failed", "message": "Waiting for profile"},
    )
    validate_parts(response)


def test_unavailable_open_profile_blocks_successful_extrude_without_geometry_inference(make):
    _, response, _ = make()
    source = response["result"]["canonical_assembly"]["part_sources"][0]["document"]["features"][0]
    source["sketch"].update(
        circles=[],
        points=[{"id": "a", "u": 0, "v": 0}, {"id": "b", "u": 5, "v": 0}],
        lines=[{"id": "edge", "start": "a", "end": "b"}],
        constraints=[],
    )
    summary(response, 0)["output"]["profile"] = {
        "state": "unavailable",
        "reason": {"code": "open_profile", "message": "Close the chain"},
    }
    with pytest.raises(ValueError, match="unavailable or wrong input port"):
        validate_parts(response)
    blocked(response)
    summary(response).update(
        status="blocked", error={"code": "profile_unavailable", "message": "Close the chain"}
    )
    validate_parts(response)
    summary(response)["error"]["code"] = "upstream_failed"
    with pytest.raises(ValueError, match="no unavailable input port"):
        validate_parts(response)


def response_for(candidate):
    request = bridge.build_request(candidate.to_dict(), result_version=2)
    response = assembly_service.run_assembly_action(candidate, result_version=2, kernel=Kernel())
    response.update(
        protocol_version=1,
        kind="assembly",
        assembly_protocol_version=1,
        input_fingerprint=bridge.fingerprint(request),
    )
    return request, response


def test_source_replay_order_and_prefix_are_bound(make):
    make()  # Install only the synthetic replay port, never a native solver.
    candidate = assembly()
    other = replace(candidate.part_sources[0].document, id="other_source")
    candidate = replace(
        candidate, part_sources=(*candidate.part_sources, PartSource.from_document(other))
    )
    request, response = response_for(candidate)
    assert bridge.validate_response(request, response)["ok"]
    response["result"]["source_replays"].reverse()
    seal(response)
    with pytest.raises(bridge.bridge.BridgeError, match="source replay order"):
        bridge.validate_response(request, response)


def test_supported_sketch_record_reordering_normalizes_before_assembly_comparison(make):
    make()
    candidate = assembly()
    raw = candidate.part_sources[0].document.to_dict()
    raw["features"][0]["sketch"]["constraints"].append(
        {"id": "anchor", "kind": "fixed", "refs": ["center"], "target": [0, 0]}
    )
    candidate = replace_source(candidate, "user_part", Document.from_dict(raw))
    request, response = response_for(candidate)
    request["assembly"]["part_sources"][0]["document"]["features"][0]["sketch"][
        "constraints"
    ].reverse()
    response["input_fingerprint"] = bridge.fingerprint(request)
    assert bridge.validate_response(request, response)["ok"]
    # No normalization relaxation escapes the embedded Part document boundary.
    request["assembly"]["instances"].reverse()
    response["input_fingerprint"] = bridge.fingerprint(request)
    with pytest.raises(bridge.bridge.BridgeError, match="canonical input changed"):
        bridge.validate_response(request, response)


def test_selected_solid_summary_stats_bind_geometry_even_when_report_is_blocked(make):
    _, response, _ = make()
    summary(response)["stats"]["area"] = 999
    with pytest.raises(ValueError, match="area"):
        validate_parts(response)


def test_cut_base_ancestor_is_allowed_but_tool_or_unrelated_identity_is_rejected(make):
    _, response, _ = make(new_sketch=False)
    result = response["result"]
    features = result["canonical_assembly"]["part_sources"][0]["document"]["features"]
    features.extend(
        [
            {
                "id": "tool_profile",
                "kind": "sketch_circle",
                "label": "Tool",
                "params": {"radius": 0.1, "x": 0, "y": 0, "z": 0},
                "inputs": {},
            },
            {
                "id": "tool",
                "kind": "extrude",
                "label": "Tool solid",
                "params": {"length": 2},
                "inputs": {"profile": "tool_profile"},
            },
            {
                "id": "cut",
                "kind": "cut",
                "label": "Cut",
                "params": {},
                "inputs": {"base": "pad", "tool": "tool"},
            },
        ]
    )
    source_summaries = result["source_replays"][0]["features"]
    source_summaries.extend(
        [
            {
                "id": "tool_profile",
                "status": "ok",
                "error": None,
                "stats": None,
                "output": {"kind": "profile", "display": "mesh"},
            },
            {**copy.deepcopy(summary(response)), "id": "tool"},
            {**copy.deepcopy(summary(response)), "id": "cut"},
        ]
    )
    selected = part(response)
    result["canonical_assembly"]["parts"][0]["output_feature_id"] = selected[
        "output_feature_id"
    ] = "cut"
    for face in selected["topology"]:
        face["provenance"].update(
            operation="cut",
            operation_id="cut",
            relation="unchanged",
            evolution="unchanged",
            source_id=face["id"],
            modifying_feature_id="cut",
            source_count=1,
            image_count=1,
        )
        face["provenance"].pop("source_boundary", None)
    validate_parts(response, complete=True)
    selected["topology"][0]["feature_id"] = "tool"
    with pytest.raises(ValueError, match="unrelated face origin"):
        validate_parts(response, complete=True)


@pytest.mark.parametrize("target", ["request", "response"])
@pytest.mark.parametrize("container", ["shared", "cyclic"])
def test_v2_bounds_direct_python_containers_before_finite_tree(target, container):
    script = f"""
import sys, types
package = types.ModuleType('isolated_assembly_resource')
package.__path__ = [{str(ADDON)!r}]
sys.modules[package.__name__] = package
from isolated_assembly_resource import assembly_bridge
request = {{'protocol_version': 1, 'result_version': 2}}
response = {{}}
node = []
if {container!r} == 'shared':
    for _ in range(29):
        node = [node, node]
else:
    node.append(node)
if {target!r} == 'request':
    request['extra'] = node
else:
    response['extra'] = node
try:
    assembly_bridge.validate_response(request, response)
except assembly_bridge.bridge.BridgeError:
    print('BOUNDED_REJECTION')
else:
    raise AssertionError('unbounded response accepted')
"""
    completed = subprocess.run(
        [sys.executable, "-I", "-B", "-c", script],
        text=True,
        capture_output=True,
        timeout=5,
    )
    assert completed.returncode == 0, completed.stderr
    assert "BOUNDED_REJECTION" in completed.stdout


def test_empty_or_whitespace_failed_error_is_not_readable(make):
    _, response, _ = make()
    blocked(response)
    summary(response)["error"]["message"] = "   "
    with pytest.raises(ValueError, match="readable"):
        validate_parts(response)
