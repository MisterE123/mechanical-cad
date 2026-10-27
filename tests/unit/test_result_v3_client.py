"""Pure-wire adversaries and an offline retained capture; no native execution here."""

import ast
import copy
import hashlib
import importlib
import json
import math
import subprocess
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ADDON = ROOT / "blender_addon/mechanical_cad_blender"
PACKAGE = "mcad_result_v3_client_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ADDON)]
sys.modules[PACKAGE] = package
contracts = importlib.import_module(PACKAGE + ".sketch_contracts_v3")
result_v3 = importlib.import_module(PACKAGE + ".result_v3")
snapshots = importlib.import_module(PACKAGE + ".part_contracts_v3")
legacy = importlib.import_module(PACKAGE + ".part_contracts")


def sector_document(*, extrusion=True):
    sketch = {
        "schema_version": 3,
        "id": "geometry",
        "units": "mm",
        "plane": {"id": "xy", "origin": [0, 0, 0], "quaternion": [1, 0, 0, 0]},
        "points": [
            {"id": "o", "u": 0, "v": 0},
            {"id": "a", "u": 5, "v": 0},
            {"id": "b", "u": 0, "v": 5},
        ],
        "lines": [{"id": "oa", "start": "o", "end": "a"}, {"id": "ob", "start": "o", "end": "b"}],
        "circles": [],
        "arcs": [{"id": "rim", "center": "o", "start": "a", "end": "b", "direction": "ccw"}],
        "constraints": [],
    }
    features = [{"id": "sketch", "kind": "sketch_constrained", "sketch": sketch}]
    if extrusion:
        features.append(
            {
                "id": "extrude",
                "kind": "extrude",
                "inputs": {"profile": "sketch"},
                "params": {"length": 7},
            }
        )
    return {
        "schema_version": 2,
        "id": "part",
        "name": "Synthetic sector",
        "units": "mm",
        "parameters": {},
        "features": features,
        "active_feature": features[-1]["id"],
    }


def solve_report(sketch):
    solved = contracts.normalize_sketch_v3(sketch)
    dimensions = {
        item["id"]: item["value"]
        for item in solved["constraints"]
        if item["kind"] in {"distance", "radius"}
    }
    return {
        "solver": "libslvs",
        "solver_version": "3.2",
        "status": "okay",
        "remaining_dof": 0,
        "failed_constraints": [],
        "redundant_constraints": [],
        "max_residual_mm": 0.0,
        "solved": solved,
        "dimensions": dimensions,
    }


def solve_pair():
    document = sector_document()
    request = {
        "protocol_version": 1,
        "action": "solve_sketch",
        "result_version": 3,
        "document": document,
        "feature_id": "sketch",
    }
    canonical = snapshots._expected_document(document)
    response = {
        "protocol_version": 1,
        "action": "solve_sketch",
        "result_version": 3,
        "input_fingerprint": snapshots.input_fingerprint(request),
        "ok": True,
        "error": None,
        "result": {
            "document_id": "part",
            "document_hash": snapshots.document_hash(canonical),
            "feature_id": "sketch",
            "sketch": solve_report(document["features"][0]["sketch"]),
            "profile_check": {"ready": True, "error": None},
        },
    }
    return request, response


def _face(identifier, role):
    solid = identifier == "extrude"
    cylinder = role.startswith("side.arc.")
    signature = {"surface": "cylinder" if cylinder else "plane", "area": 1.0, "centroid": [0, 0, 0]}
    if cylinder:
        signature.update(radius=5.0, axis=[0, 0, -1])
    else:
        signature["normal"] = (
            [1, 0, 0] if role.startswith("side.") else [0, 0, -1 if role == "cap.start" else 1]
        )
    relation = (
        "generated_from_profile_edge"
        if role.startswith("side.")
        else {
            "profile": "constructed_profile",
            "cap.start": "first_shape",
            "cap.end": "last_shape",
        }[role]
    )
    provenance = {
        "semantic_status": "stable",
        "kernel": "OCCT",
        "operation": "extrude" if solid else "curve_profile",
        "operation_id": identifier,
        "relation": relation,
        "evolution": relation,
    }
    if role.startswith("side."):
        provenance["source_boundary"] = role[5:]
    return {
        "id": f"{identifier}/face/{role}",
        "feature_id": identifier,
        "kind": "face",
        "role": role,
        "signature": signature,
        "provenance": provenance,
    }


def replay_pair():
    document = sector_document()
    request = {"protocol_version": 1, "result_version": 3, "document": document}
    canonical = snapshots._expected_document(document)
    features = []
    for source in canonical["features"]:
        solid = source["kind"] == "extrude"
        roles = (
            ["cap.start", "cap.end", "side.line.oa", "side.line.ob", "side.arc.rim"]
            if solid
            else ["profile"]
        )
        topology = [_face(source["id"], role) for role in roles]
        feature = {
            "id": source["id"],
            "label": source["label"],
            "kind": source["kind"],
            "inputs": source["inputs"],
            "resolved_params": source["params"],
            "status": "ok",
            "error": None,
            "stats": {
                "valid": True,
                "solids": 1,
                "faces": 5,
                "volume": 25 * math.pi * 7 / 4,
                "area": 100.0,
            }
            if solid
            else None,
            "mesh": {
                "vertices": [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
                "triangles": [[0, 1, 2] for _ in roles],
                "triangle_face_ids": [face["id"] for face in topology],
            },
            "topology": topology,
            "output": {"kind": "solid", "display": "mesh"}
            if solid
            else {
                "kind": "sketch",
                "display": "solved_sketch",
                "profile": {"state": "available", "region_kind": "curve_loop"},
            },
        }
        if not solid:
            feature["sketch"] = solve_report(source["sketch"])
        features.append(feature)
    response = {
        "protocol_version": 1,
        "result_version": 3,
        "input_fingerprint": snapshots.input_fingerprint(request),
        "ok": True,
        "error": None,
        "result": {
            "result_version": 3,
            "document_id": "part",
            "document_hash": snapshots.document_hash(canonical),
            "active_feature": "extrude",
            "status": "ok",
            "units": "mm",
            "parameters": {},
            "features": features,
        },
    }
    return request, response


def test_genuine_schema_three_synthetic_solve_and_replay_are_detached():
    for factory in (solve_pair, replay_pair):
        request, response = factory()
        original = copy.deepcopy((request, response))
        accepted = result_v3.validate_response(request, response)
        assert accepted == response and accepted is not response
        assert (request, response) == original
        assert request["document"]["features"][0]["sketch"]["schema_version"] == 3


@pytest.mark.parametrize("version", [None, True, 3.0, "3", 0, 2, 4])
def test_exact_version_required(version):
    request, response = solve_pair()
    request["result_version"] = version
    with pytest.raises(ValueError):
        result_v3.validate_response(request, response)


@pytest.mark.parametrize(
    "action",
    [
        "check_geometry",
        "export_step",
        "export_stl",
        "assembly_replay",
        "canonical_snapshot",
        "future",
    ],
)
def test_only_two_explicit_action_families(action):
    request, _ = solve_pair()
    request["action"] = action
    with pytest.raises(ValueError):
        result_v3.validate_request(request)


@pytest.mark.parametrize(
    "change",
    [
        lambda s: s.update(schema_version=True),
        lambda s: s.pop("arcs"),
        lambda s: s.update(extra=1),
        lambda s: s["arcs"][0].update(direction="CCW"),
        lambda s: s["arcs"][0].update(start="o"),
        lambda s: s["arcs"][0].update(center="missing"),
        lambda s: s["arcs"][0].update(radius=5),
        lambda s: s["points"][0].update(u=True),
        lambda s: s["points"][0].update(u=float("nan")),
        lambda s: s["points"][0].update(u=10**1000),
        lambda s: s["points"][0].update(id="xy"),
        lambda s: s["plane"].update(quaternion=[1, 1, 0, 0]),
        lambda s: s["constraints"].append(
            {"id": "bad", "kind": "radius", "refs": ["oa"], "value": 5}
        ),
        lambda s: s["constraints"].append({"id": "bad", "kind": "future", "refs": []}),
    ],
)
def test_strict_normal_form_negatives(change):
    sketch = sector_document()["features"][0]["sketch"]
    change(sketch)
    with pytest.raises(ValueError):
        contracts.normalize_sketch_v3(sketch)


@pytest.mark.parametrize(
    "change",
    [
        lambda r: r.update(solver="fake"),
        lambda r: r.update(solver_version="3.3"),
        lambda r: r.update(remaining_dof=True),
        lambda r: r.update(remaining_dof=7),
        lambda r: r.update(max_residual_mm=True),
        lambda r: r.update(max_residual_mm=1e-6),
        lambda r: r.update(failed_constraints=["made_up"]),
        lambda r: r.update(redundant_constraints=["made_up"]),
        lambda r: r.update(dimensions={"extra": 5}),
        lambda r: r["solved"].update(schema_version=2),
        lambda r: r["solved"]["arcs"][0].update(direction="cw"),
        lambda r: r["solved"]["lines"][0].update(start="b"),
        lambda r: r["solved"]["points"][0].update(u=5.00001),
        lambda r: r["solved"]["plane"].update(origin=[1, 0, 0]),
        lambda r: r["solved"].update(
            constraints=[
                {"id": "invented", "kind": "radius", "refs": ["rim"], "value": 5, "target": None}
            ]
        ),
    ],
)
def test_solver_source_and_residual_adversaries(change):
    request, response = solve_pair()
    change(response["result"]["sketch"])
    with pytest.raises(ValueError):
        result_v3.validate_response(request, response)


@pytest.mark.parametrize(
    "change",
    [
        lambda r: r.update(result_version=2),
        lambda r: r.update(extra=True),
        lambda r: r.update(input_fingerprint="0" * 64),
        lambda r: r["result"].update(active_feature="sketch"),
        lambda r: r["result"]["features"].reverse(),
        lambda r: r["result"]["features"].pop(),
        lambda r: r["result"]["features"][0].update(label="changed"),
        lambda r: r["result"]["features"][1].update(inputs={"profile": "extrude"}),
        lambda r: r["result"]["features"][1]["resolved_params"].update(length=8),
        lambda r: r["result"]["features"][0]["output"]["profile"].update(region_kind="line_loop"),
        lambda r: r["result"]["features"][1]["mesh"]["triangles"][0].__setitem__(0, True),
        lambda r: r["result"]["features"][1]["mesh"]["triangle_face_ids"].__setitem__(
            0, "extrude/face/cap.end"
        ),
        lambda r: r["result"]["features"][1]["topology"][-1]["signature"].update(radius=7),
        lambda r: r["result"]["features"][1]["topology"][-1]["signature"].update(axis=[0, 0, 1]),
        lambda r: r["result"]["features"][1]["topology"][-1].update(role="side.circle.rim"),
        lambda r: r["result"]["features"][1]["topology"][0]["provenance"].update(
            relation="last_shape", evolution="last_shape"
        ),
        lambda r: r["result"]["features"][1]["topology"][0]["signature"].update(normal=[0, 0, 1]),
        lambda r: r["result"]["features"][0]["topology"][0]["provenance"].update(
            operation="polygon"
        ),
        lambda r: r["result"]["features"][1]["topology"][-1]["provenance"].update(
            source_boundary="arc.other"
        ),
        lambda r: r["result"]["features"][1]["topology"][-1]["provenance"].update(
            semantic_status="split"
        ),
        lambda r: r["result"].update(status="failed"),
        lambda r: r.update(ok=False),
    ],
)
def test_replay_algebra_topology_and_mesh_adversaries(change):
    request, response = replay_pair()
    change(response)
    with pytest.raises(ValueError):
        result_v3.validate_response(request, response)


def test_failed_native_profile_keeps_successful_report_and_blocks_extrusion():
    request, response = replay_pair()
    for index, feature in enumerate(response["result"]["features"]):
        feature.update(
            status="blocked" if index else "failed",
            output=None,
            stats=None,
            mesh=None,
            topology=[],
            error={
                "code": "upstream_failed" if index else "unsupported_native_frame",
                "message": "Synthetic native failure.",
            },
        )
    response["result"]["status"] = "failed"
    response["ok"] = False
    result_v3.validate_response(request, response)
    response["result"]["features"][1]["status"] = "failed"
    with pytest.raises(ValueError):
        result_v3.validate_response(request, response)


@pytest.mark.parametrize("action", ["solve_sketch", "replay"])
def test_arc_requests_allow_mixed_graphs_and_multiple_consumers(action):
    request, _ = solve_pair()
    request["document"]["features"].extend(
        [
            {"id": "other", "kind": "sketch_circle", "params": {"radius": 3}},
            {
                "id": "other_pad",
                "kind": "extrude",
                "params": {"length": 2},
                "inputs": {"profile": "other"},
            },
            {
                "id": "pad2",
                "kind": "extrude",
                "params": {"length": 4},
                "inputs": {"profile": "sketch"},
            },
            {
                "id": "moved",
                "kind": "transform",
                "params": {"x": 20},
                "inputs": {"base": "extrude"},
            },
        ]
    )
    request["action"] = action
    if action == "replay":
        request.pop("feature_id")
    before = copy.deepcopy(request)
    validated = result_v3.validate_request(request)
    assert validated == request == before
    validated["document"]["features"].clear()
    assert request == before


@pytest.mark.parametrize("action", ["solve_sketch", "replay"])
@pytest.mark.parametrize("fault", ["missing", "wrong_kind", "cycle"])
def test_arc_requests_still_reject_invalid_dependencies(action, fault):
    request, _ = solve_pair()
    request["action"] = action
    if action == "replay":
        request.pop("feature_id")
    features = request["document"]["features"]
    if fault == "missing":
        features[1]["inputs"]["profile"] = "absent"
        message = "invalid feature dependency"
    elif fault == "wrong_kind":
        features.append({"id": "moved", "kind": "transform", "inputs": {"base": "sketch"}})
        message = "wrong feature kind"
    else:
        features.extend(
            [
                {"id": "move1", "kind": "transform", "inputs": {"base": "move2"}},
                {"id": "move2", "kind": "transform", "inputs": {"base": "move1"}},
            ]
        )
        message = "cyclic feature dependencies"
    with pytest.raises(ValueError, match=message):
        result_v3.validate_request(request)


def test_arc_empty_three_open_retains_schema_and_original_geometry_leaf():
    request, response = solve_pair()
    source = request["document"]["features"][0]["sketch"]
    source.update(arcs=[], lines=source["lines"][:1])
    canonical = snapshots._expected_document(request["document"])
    response["input_fingerprint"] = snapshots.input_fingerprint(request)
    response["result"].update(
        document_hash=snapshots.document_hash(canonical),
        sketch=solve_report(source),
        profile_check={
            "ready": False,
            "error": {"code": "open_profile", "message": "Close chain."},
        },
    )
    result_v3.validate_response(request, response)
    assert response["result"]["sketch"]["solved"]["schema_version"] == 3
    response["result"]["profile_check"] = {"ready": True, "error": None}
    with pytest.raises(ValueError):
        result_v3.validate_response(request, response)


@pytest.mark.parametrize(
    "lines,code",
    [
        ([{"id": "chord", "start": "a", "end": "b"}], None),
        ([], "open_profile"),
        (
            [
                {"id": "chord", "start": "a", "end": "b"},
                {"id": "duplicate", "start": "a", "end": "b"},
            ],
            "unsupported_profile_form",
        ),
    ],
    ids=["closed_arc_chord", "open_arc", "branched_overlap"],
)
def test_arc_profile_diagnostic_matches_actual_boundary(lines, code):
    request, response = solve_pair()
    source = request["document"]["features"][0]["sketch"]
    source["lines"] = lines
    response["input_fingerprint"] = snapshots.input_fingerprint(request)
    response["result"].update(
        document_hash=snapshots.document_hash(snapshots._expected_document(request["document"])),
        sketch=solve_report(source),
        profile_check={
            "ready": code is None,
            "error": None if code is None else {"code": code, "message": "Invalid boundary."},
        },
    )
    result_v3.validate_response(request, response)
    # Resealed source hashes cannot make a false readiness/diagnostic claim valid.
    for wrong_code in {None, "open_profile", "unsupported_profile_form"} - {code}:
        response["result"]["profile_check"] = {
            "ready": wrong_code is None,
            "error": None if wrong_code is None else {"code": wrong_code, "message": "Forged."},
        }
        with pytest.raises(ValueError, match="analytic profile"):
            result_v3.validate_response(request, response)


def test_constraints_keep_expressions_and_bind_named_radius_and_intrinsic_residual():
    request, response = solve_pair()
    source = request["document"]["features"][0]["sketch"]
    source["constraints"] = [{"id": "radius", "kind": "radius", "refs": ["rim"], "value": "R"}]
    request["document"]["parameters"] = {"R": 5}
    response["input_fingerprint"] = snapshots.input_fingerprint(request)
    response["result"]["document_hash"] = snapshots.document_hash(
        snapshots._expected_document(request["document"])
    )
    report = response["result"]["sketch"]
    report["dimensions"] = {"radius": 5.0}
    report["solved"]["constraints"] = [
        {"id": "radius", "kind": "radius", "refs": ["rim"], "value": 5.0, "target": None}
    ]
    result_v3.validate_response(request, response)
    assert source["constraints"][0]["value"] == "R"
    report["dimensions"]["radius"] = 7
    report["solved"]["constraints"][0]["value"] = 7
    with pytest.raises(ValueError, match="residual"):
        result_v3.validate_response(request, response)


def test_sketch_cycle_and_expanding_dag_rejected_before_copy():
    cycle = {}
    cycle["cycle"] = cycle
    with pytest.raises(ValueError):
        contracts.normalize_sketch_v3(cycle)
    dag = [0]
    for _ in range(24):
        dag = [dag, dag]
    with pytest.raises(ValueError):
        contracts.normalize_sketch_v3({"dag": dag})


def test_frozen_shared_policy_pins_and_canonical_function_parity():
    expected = {
        "arc_geometry": "b2017ca26300712cdaece7325fcd12fd1330d650896a5494dea56967fa1a82aa",
        "arc_profile_primitives": "22994be172dae608d2f7334545c8b32a3b69e03d766d918ca6aab4361bfc81e0",
        "arc_profile_intervals": "88facdee48d067c5096eab12e3195d7db57bfb831a3217a5c4a3630a29457849",
        "arc_profile_sector_source": "f2eea6b9f16d5de8c6652c805847986952dc1c128353b1f2280e4f769492b6ff",
        "arc_profile_sector_policy": "c360bd15d8949ae02b03651f933743bb34c3e52cae2acfdc70fedab8995ce429",
    }
    for name, digest in expected.items():
        original = (ROOT / "src/mechanical_cad" / (name + ".py")).read_bytes()
        assert (ADDON / (name + ".py")).read_bytes() == original
        assert hashlib.sha256(original).hexdigest() == digest
    functions = []
    for name in ("part_contracts", "part_contracts_v3"):
        raw = (ADDON / (name + ".py")).read_bytes()
        node = next(
            node
            for node in ast.parse(raw).body
            if isinstance(node, ast.FunctionDef) and node.name == "_expected_document"
        )
        functions.append(b"".join(raw.splitlines(keepends=True)[node.lineno - 1 : node.end_lineno]))
    # Canonicalizers grow as feature kinds are added; freeze old document meaning
    # against the retained captures below, not the implementation's original size.
    assert functions[0] == functions[1]
    assert legacy._expected_document.__globals__["_normalize_sketch"] is legacy._normalize_sketch
    assert (
        snapshots._expected_document.__globals__["_normalize_sketch"] is snapshots._normalize_sketch
    )


@pytest.mark.parametrize(
    "name,digest",
    [
        ("viewport_rectangle", "c01ff8fc476f9eaf9d314df4c3aae607cca15da6a6075d902b5aa30054ba48c7"),
        ("circle_sketch_part", "8c69b41f7778ad55c13980dc19f3cf460db419245bb729ec97957665cbfd02f3"),
        ("open_line_sketch", "07deced3f974b8565b2be9b8dcd89681081549e445c8204195778ba61a310cb2"),
        ("drilled_plate", "777d634152cce17a17247b347e433b311410ee2c67fcc70927176e02d8ac59e9"),
    ],
)
def test_original_legacy_canonical_bytes_unchanged(name, digest):
    captured = ROOT / "tests/fixtures/result_v3/legacy_30383a1"
    original_request = json.loads((captured / f"snapshot_{name}.request.txt").read_text(encoding="utf-8"))
    original_result = json.loads((captured / f"snapshot_{name}.stdout.txt").read_text(encoding="utf-8"))["result"]
    expected = original_result["canonical_json"].encode("utf-8")
    assert hashlib.sha256(expected).hexdigest() == original_result["content_hash"] == digest
    document = json.loads((ROOT / "examples" / (name + ".mcad.json")).read_text(encoding="utf-8"))
    assert document == original_request["document"]
    for module in (snapshots, legacy):
        assert (
            module._json(module._expected_document(document), canonical=True).encode() == expected
        )
    document["name"] = "Pièce -0"
    for feature in document["features"]:
        if "sketch" in feature:
            for field in ("points", "lines", "circles", "constraints"):
                if field in feature["sketch"]:
                    feature["sketch"][field].reverse()
    expected_document = original_result["canonical_document"]
    expected_document["name"] = document["name"]
    expected = (
        json.dumps(expected_document, sort_keys=True, indent=2, allow_nan=False) + "\n"
    ).encode()
    for module in (snapshots, legacy):
        assert (
            module._json(module._expected_document(document), canonical=True).encode() == expected
        )


def test_client_import_denial_python_without_site():
    script = r"""
import builtins, importlib, sys, types
original = builtins.__import__
denied = {"mechanical_cad", "OCP", "slvs", "bpy", "engine", "bridge", "sidecar_job", "backend_contracts", "backend_selection", "guarded_transport", "guarded_evidence", "document_state", "part_publication"}
def checked(name, *args, **kwargs):
    if any(part in denied for part in name.split(".")):
        raise AssertionError("forbidden import: " + name)
    return original(name, *args, **kwargs)
builtins.__import__ = checked
package = types.ModuleType("client_only")
package.__path__ = [sys.argv[1]]
sys.modules["client_only"] = package
for name in ("result_v3", "part_contracts_v3", "sketch_contracts_v3", "sector_topology_v3"):
    importlib.import_module("client_only." + name)
assert not any(name.split(".")[0] in denied for name in sys.modules)
print("CLIENT_V3_NATIVE_FREE")
"""
    completed = subprocess.run(
        [sys.executable, "-S", "-c", script, str(ADDON)],
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
    )
    assert completed.stdout == "CLIENT_V3_NATIVE_FREE\n"


@pytest.mark.parametrize(
    "start,end,direction",
    [
        ((5, 0), (0, 5), "ccw"),
        ((5, 0), (0, 5), "cw"),
        ((5, 0), (-5, 0), "ccw"),
        ((5, 0), (-5, 0), "cw"),
        ((3, 4), (-4, 3), "ccw"),
        ((5, 0), (-3, 4), "ccw"),
        ((5.1, 0), (0, 5.1), "cw"),
        ((1, 0), (0, 1), "ccw"),
        ((1000, 0), (0, 1000), "ccw"),
        ((5, 0), (0, math.nextafter(5, math.inf)), "ccw"),
        ((5, 0), (0, math.nextafter(5, -math.inf)), "ccw"),
    ],
)
def test_complete_geometry_positive_matrix_preserves_order_and_direction(start, end, direction):
    sketch = sector_document()["features"][0]["sketch"]
    sketch["points"][1].update(u=start[0], v=start[1])
    sketch["points"][2].update(u=end[0], v=end[1])
    sketch["arcs"][0]["direction"] = direction
    for field in ("points", "lines", "arcs", "constraints"):
        sketch[field].reverse()
    for line in sketch["lines"]:
        line["start"], line["end"] = line["end"], line["start"]
    assert contracts.sector_readiness(sketch) is None


@pytest.mark.parametrize("radius", [math.nextafter(1, 0), math.nextafter(1000, math.inf)])
def test_sector_scale_neighbors_are_readiness_failures(radius):
    sketch = sector_document()["features"][0]["sketch"]
    sketch["points"][1]["u"] = radius
    sketch["points"][2]["v"] = radius
    assert contracts.sector_readiness(sketch) == "unsupported_profile_scale"


@pytest.mark.parametrize("coincidence", [False, True])
def test_distinct_point_aliases_never_supply_sector_join(coincidence):
    sketch = sector_document()["features"][0]["sketch"]
    sketch["points"].append({"id": "alias", "u": 5, "v": 0})
    sketch["lines"][0]["end"] = "alias"
    if coincidence:
        sketch["constraints"].append(
            {
                "id": "coincident",
                "kind": "coincident",
                "refs": ["a", "alias"],
                "value": None,
                "target": None,
            }
        )
    assert contracts.sector_readiness(sketch) == "unsupported_profile_coincidence"


def test_solve_readiness_is_independent_of_native_frame_support():
    sketch = sector_document()["features"][0]["sketch"]
    sketch["plane"].update(origin=[10, 20, 30], quaternion=[math.cos(0.2), 0, 0, math.sin(0.2)])
    assert contracts.sector_readiness(sketch) is None


def test_native_equation_and_active_scalar_limits():
    sketch = sector_document()["features"][0]["sketch"]
    sketch["constraints"] = [
        {"id": "c" + str(index), "kind": "fixed", "refs": ["o"], "target": [0, 0]}
        for index in range(512)
    ]
    with pytest.raises(ValueError, match="equation"):
        contracts.normalize_sketch_v3(sketch)
    sketch = sector_document()["features"][0]["sketch"]
    sketch["points"].extend({"id": "p" + str(index), "u": 0, "v": 0} for index in range(253))
    sketch["circles"] = [{"id": "circle", "center": "o", "radius": 5}]
    with pytest.raises(ValueError, match="scalar"):
        contracts.normalize_sketch_v3(sketch)


def test_shared_context_is_not_reset_when_reused():
    primitives = importlib.import_module(PACKAGE + ".arc_profile_primitives")
    sketch = sector_document()["features"][0]["sketch"]
    measured = primitives.PrimitiveContext()
    assert contracts.sector_readiness(sketch, context=measured) is None
    limit = measured.operations
    context = primitives.PrimitiveContext(max_operations=limit)
    assert contracts.sector_readiness(sketch, context=context) is None
    assert context.operations == limit
    # Failure may arise before the policy can manufacture a diagnostic report;
    # neither raised nor returned exhaustion is permission to reset the budget.
    try:
        rejected = contracts.sector_readiness(sketch, context=context)
    except primitives.PrimitiveError as error:
        assert error.code == "operation_limit"
    else:
        assert rejected == "numerically_ambiguous_profile"
    assert context.operations == limit


def test_client_ast_dependency_graph_is_acyclic_and_no_core_imports():
    roots = {"result_v3", "part_contracts_v3", "sketch_contracts_v3", "sector_topology_v3"}
    dependencies = {}

    def collect(name):
        if name in dependencies:
            return
        dependencies[name] = set()
        tree = ast.parse((ADDON / (name + ".py")).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith("mechanical_cad")
                if node.level == 1:
                    imports = (
                        [node.module.split(".")[0]]
                        if node.module
                        else [alias.name for alias in node.names]
                    )
                    dependencies[name].update(imports)
                    for dependency in imports:
                        collect(dependency)
            elif isinstance(node, ast.Import):
                assert all(not alias.name.startswith("mechanical_cad") for alias in node.names)

    for name in roots:
        collect(name)
    complete, active = set(), set()

    def visit(name):
        assert name not in active, "client validator import cycle"
        if name in complete:
            return
        active.add(name)
        for dependency in dependencies[name]:
            visit(dependency)
        active.remove(name)
        complete.add(name)

    for name in roots:
        visit(name)


@pytest.mark.parametrize("field", ["remaining_dof", "solved", "profile_check"])
def test_failed_solve_never_has_dof_geometry_or_readiness(field):
    request, response = solve_pair()
    report = response["result"]["sketch"]
    solved = report["solved"]
    report.update(status="inconsistent", remaining_dof=None, solved=None)
    response.update(
        ok=False, error={"code": "sketch_solve_failed", "message": "Synthetic failure."}
    )
    response["result"]["profile_check"] = None
    result_v3.validate_response(request, response)
    if field == "profile_check":
        response["result"][field] = {
            "ready": False,
            "error": {"code": "open_profile", "message": "No."},
        }
    else:
        report[field] = solved if field == "solved" else 0
    with pytest.raises(ValueError):
        result_v3.validate_response(request, response)


def test_intrinsic_arc_residual_cannot_be_underreported():
    request, response = solve_pair()
    solved = response["result"]["sketch"]["solved"]
    next(point for point in solved["points"] if point["id"] == "b")["v"] = 5 + 1e-10
    with pytest.raises(ValueError, match="residual"):
        result_v3.validate_response(request, response)


def test_rehashing_does_not_conceal_changed_persistent_arc_direction():
    request, response = solve_pair()
    request["document"]["features"][0]["sketch"]["arcs"][0]["direction"] = "cw"
    response["input_fingerprint"] = snapshots.input_fingerprint(request)
    response["result"]["document_hash"] = snapshots.document_hash(
        snapshots._expected_document(request["document"])
    )
    with pytest.raises(ValueError, match="topology"):
        result_v3.validate_response(request, response)


def retained_redundant_o010():
    """Read exact failed-attempt bytes, never a replacement expected response."""
    fixture = ROOT / "tests/fixtures/result_v3/redundant_okay_O010"
    raw = (fixture / "provenance.json").read_bytes()
    assert (
        hashlib.sha256(raw).hexdigest()
        == "a132e4e1c3a74c0dddf247bb123605d598a70ad8178198f4d813801f03c0d159"
    )
    provenance = json.loads(raw)
    assert provenance["original_gate_outcome"] == "FAIL"
    assert provenance["source_commit"] == "cc130e667cc30c76e0437f5994059220f1aca25e"
    for name, expected in provenance["files"].items():
        data = (fixture / name).read_bytes()
        assert (len(data), hashlib.sha256(data).hexdigest()) == (
            expected["bytes"],
            expected["sha256"],
        )
    request = json.loads((fixture / "request.raw").read_bytes())
    response = json.loads((fixture / "stdout.raw").read_bytes())
    assert response == json.loads((fixture / "RESPONSE_OBSERVED.json").read_bytes())
    failure = json.loads((fixture / "CLIENT_VALIDATION.json").read_bytes())
    assert failure["verified"] is False
    assert failure["error"] == {
        "message": "successful solve reports failed constraints",
        "type": "ValueError",
    }
    case = json.loads((fixture / "CASE_VALIDATION.json").read_bytes())
    assert case["expected_outcome_verified"] is False
    return request, response


def redundant_o010_report():
    request, response = retained_redundant_o010()
    source = request["document"]["features"][0]
    feature = response["result"]["features"][0]
    return source, feature, feature["sketch"]


def test_retained_o010_geometry_response_validates_offline_without_rewriting_diagnostics():
    request, response = retained_redundant_o010()
    before = copy.deepcopy((request, response))
    client = importlib.import_module(PACKAGE + ".geometry_result_v3")
    validated = client.validate_response(request, response)
    assert validated == response and validated is not response
    assert (request, response) == before
    report = validated["result"]["features"][0]["sketch"]
    assert report["status"] == "redundant_okay"
    assert report["failed_constraints"] == ["center_lock", "end_lock", "start_lock"]
    assert report["redundant_constraints"] == []
    assert report["remaining_dof"] == 0 and report["max_residual_mm"] == 0
    assert contracts._residual(report["solved"]) == 0
    points = {p["id"]: (p["u"], p["v"]) for p in report["solved"]["points"]}
    assert points == {"center": (0, 0), "end": (-29, 13), "start": (13, 29)}
    assert math.dist(points["center"], points["start"]) == math.sqrt(1010)


@pytest.mark.parametrize("status", ["okay", "redundant_okay"])
@pytest.mark.parametrize("candidates", [[], ["center_lock"], ["start_lock", "end_lock"]])
def test_redundancy_candidates_are_allowed_only_for_exact_redundant_okay(status, candidates):
    source, feature, report = redundant_o010_report()
    report.update(status=status, failed_constraints=candidates)
    if status == "okay" and candidates:
        with pytest.raises(ValueError, match="okay solve reports failed constraints"):
            contracts.validate_sketch_report_v3(feature, source)
    else:
        contracts.validate_sketch_report_v3(feature, source)
        assert report["failed_constraints"] == candidates
        assert report["redundant_constraints"] == []


def test_redundancy_candidate_acceptance_is_not_specific_to_zero_dof():
    source, feature, report = redundant_o010_report()
    report["remaining_dof"] = 2
    contracts.validate_sketch_report_v3(feature, source)
    assert report["remaining_dof"] == 2


@pytest.mark.parametrize("field", ["failed_constraints", "redundant_constraints"])
@pytest.mark.parametrize(
    "ids",
    [
        ["unknown"],
        ["center"],
        ["rim"],
        ["radial_start"],
        ["center_lock", "center_lock"],
        "center_lock",
        ("center_lock",),
        None,
        {},
        [True],
        [1],
        [[]],
        ["center_lock"] * 513,
    ],
)
def test_redundancy_diagnostics_stay_bounded_unique_and_authored(field, ids):
    source, feature, report = redundant_o010_report()
    report[field] = ids
    with pytest.raises(ValueError, match="diagnostic constraint IDs"):
        contracts.validate_sketch_report_v3(feature, source)


@pytest.mark.parametrize("status", ["REDUNDANT_OKAY", "redundant_okay ", 4, True, None, []])
def test_redundancy_candidate_exception_does_not_accept_unknown_status(status):
    source, feature, report = redundant_o010_report()
    report["status"] = status
    with pytest.raises(ValueError, match="native solve contract"):
        contracts.validate_sketch_report_v3(feature, source)


@pytest.mark.parametrize("status", ["inconsistent", "didnt_converge", "too_many_unknowns"])
@pytest.mark.parametrize("field", ["solved", "remaining_dof", "feature_status"])
def test_redundancy_candidates_cannot_mask_failed_solver_status(status, field):
    source, feature, report = redundant_o010_report()
    solved = report["solved"]
    feature["status"] = "failed"
    report.update(status=status, solved=None, remaining_dof=None)
    contracts.validate_sketch_report_v3(feature, source)
    if field == "feature_status":
        feature["status"] = "ok"
    else:
        report[field] = solved if field == "solved" else 0
    with pytest.raises(ValueError, match="failed solver claims"):
        contracts.validate_sketch_report_v3(feature, source)


@pytest.mark.parametrize("residual", [None, True, -1, 1.0001e-7, math.inf, math.nan])
def test_redundancy_candidates_cannot_mask_invalid_reported_residual(residual):
    source, feature, report = redundant_o010_report()
    report["max_residual_mm"] = residual
    with pytest.raises(ValueError):
        contracts.validate_sketch_report_v3(feature, source)


@pytest.mark.parametrize("dof", [None, True, -1, 7, 0.5, math.inf, math.nan])
def test_redundancy_candidates_cannot_mask_invalid_dof(dof):
    source, feature, report = redundant_o010_report()
    report["remaining_dof"] = dof
    with pytest.raises(ValueError, match="DoF/residual"):
        contracts.validate_sketch_report_v3(feature, source)


@pytest.mark.parametrize("delta", [1e-6, 1e-10])
def test_redundancy_candidates_cannot_mask_fixed_point_residual(delta):
    source, feature, report = redundant_o010_report()
    # Translate all coordinates together: radii stay equal, fixed intent does not.
    for point in report["solved"]["points"]:
        point["u"] += delta
    with pytest.raises(ValueError, match="residual"):
        contracts.validate_sketch_report_v3(feature, source)


@pytest.mark.parametrize("delta", [1e-6, 1e-10])
def test_redundancy_candidates_cannot_mask_intrinsic_arc_residual(delta):
    source, feature, report = redundant_o010_report()
    point = next(p for p in report["solved"]["points"] if p["id"] == "start")
    point["u"] += delta
    with pytest.raises(ValueError):
        contracts.validate_sketch_report_v3(feature, source)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda s: s["arcs"][0].update(direction="cw"),
        lambda s: s["lines"][0].update(start="start"),
        lambda s: s["plane"].update(origin=[1, 0, 0]),
        lambda s: s.update(id="other"),
        lambda s: s["points"].append({"id": "extra", "u": 0, "v": 0}),
        lambda s: s["constraints"][0].update(target=[1, 0]),
        lambda s: s["constraints"][0].update(id="other_lock"),
        lambda s: s["constraints"][0].update(refs=["start"]),
    ],
)
def test_redundancy_candidates_do_not_authorize_changed_solved_intent(mutation):
    source, feature, report = redundant_o010_report()
    mutation(report["solved"])
    with pytest.raises(ValueError):
        contracts.validate_sketch_report_v3(feature, source)


def test_redundancy_candidates_do_not_authorize_added_dimensions_or_okay_duplicates():
    source, feature, report = redundant_o010_report()
    report["dimensions"]["center_lock"] = 1
    with pytest.raises(ValueError):
        contracts.validate_sketch_report_v3(feature, source)
    report["dimensions"].clear()
    report.update(status="okay", failed_constraints=[], redundant_constraints=["center_lock"])
    with pytest.raises(ValueError, match="unreported redundant equations"):
        contracts.validate_sketch_report_v3(feature, source)


@pytest.mark.parametrize("schema", [1, 2])
def test_non_schema_three_still_delegates_to_unchanged_legacy_validator(monkeypatch, schema):
    source, feature, _report = redundant_o010_report()
    source["sketch"]["schema_version"] = schema
    called = []

    def legacy_validator(actual_feature, actual_source):
        assert actual_feature is feature and actual_source is source
        called.append(True)
        raise ValueError("legacy validation retained")

    monkeypatch.setattr(contracts, "validate_sketch_report_v2", legacy_validator)
    with pytest.raises(ValueError, match="legacy validation retained"):
        contracts.validate_sketch_report_v3(feature, source)
    assert called == [True]


def test_successful_redundant_report_cannot_become_failure_diagnostics(monkeypatch):
    # A synthetic solve envelope around the retained report tests failure-only
    # admission. This is explicitly separate from the unchanged O010 capture.
    source, _feature, report = redundant_o010_report()
    request, response = solve_pair()
    request["document"]["features"][0]["sketch"] = source["sketch"]
    response["input_fingerprint"] = snapshots.input_fingerprint(request)
    response["result"].update(
        sketch=report,
        document_hash=snapshots.document_hash(snapshots._expected_document(request["document"])),
    )
    result_v3.validate_response(request, response)
    diagnostics = importlib.import_module(PACKAGE + ".constraint_diagnostics")
    # The production authority dispatcher remains closed. Exercise the existing
    # failure-only guard after the strict schema-3 validator without activating it.
    monkeypatch.setattr(
        diagnostics.operation_contracts, "validate_response", result_v3.validate_response
    )
    with pytest.raises(diagnostics.ConstraintDiagnosticsError, match="failed native solve report"):
        diagnostics.FailureDiagnostics(
            response,
            request,
            session_id="session",
            command_revision=0,
            input_token="input",
            input_revision=0,
        )
