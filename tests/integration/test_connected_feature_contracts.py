"""Real sidecar new-feature evidence must cross the Blender trust boundary."""

import copy
import importlib
import sys
import types
from pathlib import Path

import pytest

from mechanical_cad.sidecar import process_request

package = types.ModuleType("mcad_connected_contracts")
package.__path__ = [
    str(Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender")
]
sys.modules[package.__name__] = package
bridge = importlib.import_module(package.__name__ + ".part_result_bridge")
contracts = importlib.import_module(package.__name__ + ".part_contracts")


def document(kind):
    features = [
        {"id": "p", "kind": "sketch_rectangle", "params": {"width": 10, "height": 10, "x": 3}},
        {"id": "a", "kind": "extrude", "params": {"length": 10}, "inputs": {"profile": "p"}},
    ]
    if kind in {"union", "intersection"}:
        features.append(
            {"id": "b", "kind": "transform", "params": {"x": 5}, "inputs": {"base": "a"}}
        )
        final = {"id": "final", "kind": kind, "inputs": {"base": "a", "tool": "b"}}
    elif kind == "revolve":
        final = {
            "id": "final",
            "kind": kind,
            "params": {"angle": 360, "axis_y": 1, "axis_z": 0},
            "inputs": {"profile": "p"},
        }
    else:
        params = {
            "fillet": {"radius": 1},
            "chamfer": {"distance": 1},
            "transform": {"x": 5, "rz": 30},
            "linear_pattern": {"count": 3, "dx": 5},
            "circular_pattern": {"count": 3, "angle": 90},
            "shell": {"thickness": 1},
        }[kind]
        final = {"id": "final", "kind": kind, "params": params, "inputs": {"base": "a"}}
    return {
        "schema_version": 1,
        "id": "part",
        "name": "Connected",
        "units": "mm",
        "parameters": {},
        "active_feature": "final",
        "features": features + [final],
    }


@pytest.mark.parametrize(
    "kind",
    [
        "union",
        "intersection",
        "revolve",
        "fillet",
        "chamfer",
        "transform",
        "linear_pattern",
        "circular_pattern",
        "shell",
    ],
)
def test_native_replay_acceptance_and_explicit_topology(kind):
    req = {"protocol_version": 1, "result_version": 2, "document": document(kind)}
    response = process_request(req)
    assert response["ok"], response
    accepted = bridge.validate_response(req, response)
    faces = accepted["result"]["features"][-1]["topology"]
    assert faces
    if kind == "revolve":
        assert {face["role"] for face in faces} == {
            "side.x_min",
            "side.x_max",
            "side.y_min",
            "side.y_max",
        }
        assert all(face["feature_id"] == "final" for face in faces)
        assert all(face["provenance"]["semantic_status"] == "stable" for face in faces)
        # Exact Generated(edge) identities are now supported; a full revolution
        # must never acquire invented start/end sweep caps.
        assert not any(face["role"].startswith("cap.") for face in faces)
    elif kind not in {"fillet", "chamfer", "transform"}:
        assert all(f["provenance"]["semantic_status"] == "unknown" for f in faces)
    else:
        assert all(
            f["feature_id"] == "a" or f["provenance"]["semantic_status"] == "unknown" for f in faces
        )
    forged = copy.deepcopy(response)
    forged["result"]["features"][-1]["topology"][0]["id"] = "invented/face/stable"
    with pytest.raises(ValueError):
        bridge.validate_response(req, forged)
    canonical = contracts._expected_document(req["document"])
    assert contracts.canonical_equivalent(req["document"], canonical)


@pytest.mark.parametrize("kind", ["union", "revolve", "fillet", "chamfer", "transform"])
def test_new_solid_step_export_crosses_strict_boundary(kind, tmp_path):
    req = {
        "protocol_version": 1,
        "result_version": 2,
        "action": "export_step",
        "document": document(kind),
        "destination": str(tmp_path / (kind + ".step")),
    }
    response = process_request(req)
    assert response["ok"], response
    bridge.validate_response(req, response)
    assert (tmp_path / (kind + ".step")).stat().st_size > 0


@pytest.mark.parametrize(
    "kind",
    [
        "union",
        "intersection",
        "revolve",
        "fillet",
        "chamfer",
        "transform",
        "linear_pattern",
        "circular_pattern",
        "shell",
    ],
)
def test_capture_and_replay_new_solids_in_assembly(kind):
    edit = importlib.import_module(package.__name__ + ".assembly_edit")
    validator = importlib.import_module(package.__name__ + ".assembly_bridge")
    canonical = contracts._expected_document(document(kind))
    assembly = edit.new_from_part(canonical)
    request = {
        "protocol_version": 1,
        "kind": "assembly",
        "assembly_protocol_version": 1,
        "result_version": 2,
        "action": "assembly_replay",
        "assembly": assembly,
    }
    response = process_request(request)
    if kind == "chamfer":
        assert not response["ok"]
        assert response["report"]["status"] == "indeterminate"
        assert (
            "Stored B-rep tolerance" in response["report"]["poses"][0]["diagnostics"][0]["message"]
        )
    else:
        assert response["ok"], response
    validator.validate_response(request, response)


def test_cut_consumes_unknown_union_faces_without_promoting_identity():
    source = document("union")
    source["features"].append(
        {"id": "cut", "kind": "cut", "inputs": {"base": "final", "tool": "a"}}
    )
    source["active_feature"] = "cut"
    req = {"protocol_version": 1, "result_version": 2, "document": source}
    response = process_request(req)
    assert response["ok"], response
    bridge.validate_response(req, response)
    inherited = [
        f for f in response["result"]["features"][-1]["topology"] if f["feature_id"] != "cut"
    ]
    assert inherited and all(f["provenance"]["semantic_status"] != "stable" for f in inherited)


def test_schema3_holes_transform_export_and_assembly(tmp_path):
    import runpy

    fixture = runpy.run_path(str(Path(__file__).with_name("test_profile_regions_native.py")))
    source = fixture["_annulus_document"](schema=3).to_dict()
    source["features"].append(
        {
            "id": "moved",
            "kind": "transform",
            "params": {"x": 20},
            "inputs": {"base": source["active_feature"]},
        }
    )
    source["active_feature"] = "moved"
    req = {
        "protocol_version": 1,
        "result_version": 3,
        "action": "export_step",
        "document": source,
        "destination": str(tmp_path / "annulus.step"),
    }
    response = process_request(req)
    assert response["ok"], response
    geometry = importlib.import_module(package.__name__ + ".geometry_result_v3")
    geometry.validate_response(req, response)
    edit = importlib.import_module(package.__name__ + ".assembly_edit")
    snapshot = importlib.import_module(package.__name__ + ".part_contracts_v3")
    validator = importlib.import_module(package.__name__ + ".assembly_bridge")
    req = {
        "protocol_version": 1,
        "kind": "assembly",
        "assembly_protocol_version": 1,
        "result_version": 3,
        "action": "assembly_replay",
        "assembly": edit.new_from_part(snapshot._expected_document(source)),
    }
    response = process_request(req)
    assert response["ok"], response
    validator.validate_response(req, response)


@pytest.mark.parametrize("version", [2, 3])
def test_selected_blend_canonical_intent_is_exact(version):
    source = document("fillet")
    source["features"][-1]["edge_faces"] = ["a/face/cap.end", "a/face/side.x_min"]
    snapshot = (
        contracts
        if version == 2
        else importlib.import_module(package.__name__ + ".part_contracts_v3")
    )
    canonical = snapshot._expected_document(source)
    assert canonical["features"][-1]["edge_faces"] == source["features"][-1]["edge_faces"]
    for bad in [
        ["snapshot:a:face:0", "a/face/cap.end"],
        ["a/face/cap.end"] * 2,
        ["a/face/cap.end"],
    ]:
        invalid = copy.deepcopy(source)
        invalid["features"][-1]["edge_faces"] = bad
        with pytest.raises(ValueError):
            snapshot._expected_document(invalid)


def test_generic_arcs_hole_export_assembly_and_snapshot(tmp_path):
    import runpy

    fixture = runpy.run_path(str(Path(__file__).with_name("test_analytic_profiles_native.py")))
    source = fixture["rounded_document"](downstream=True).to_dict()
    geometry = importlib.import_module(package.__name__ + ".geometry_result_v3")
    req = {
        "protocol_version": 1,
        "result_version": 3,
        "action": "export_step",
        "document": source,
        "destination": str(tmp_path / "rounded.step"),
    }
    response = process_request(req)
    assert response["ok"], response
    geometry.validate_response(req, response)
    snapshot = importlib.import_module(package.__name__ + ".part_snapshot_bridge")
    req = {"protocol_version": 1, "action": "canonical_snapshot", "document": source}
    response = process_request(req)
    assert response["ok"], response
    receipt = snapshot.validate_response(req, response)
    edit = importlib.import_module(package.__name__ + ".assembly_edit")
    validator = importlib.import_module(package.__name__ + ".assembly_bridge")
    req = {
        "protocol_version": 1,
        "kind": "assembly",
        "assembly_protocol_version": 1,
        "result_version": 3,
        "action": "assembly_replay",
        "assembly": edit.new_from_part(receipt["canonical_document"]),
    }
    response = process_request(req)
    assert response["ok"], response
    validator.validate_response(req, response)


def test_selected_blend_chain_retains_verified_face_lineage():
    source = document("fillet")
    source["features"][-1]["edge_faces"] = ["a/face/cap.end", "a/face/side.x_min"]
    source["features"].append(
        {
            "id": "bevel",
            "kind": "chamfer",
            "params": {"distance": 0.5},
            "inputs": {"base": "final"},
            "edge_faces": ["a/face/cap.start", "a/face/side.x_max"],
        }
    )
    source["active_feature"] = "bevel"
    req = {"protocol_version": 1, "result_version": 2, "document": source}
    response = process_request(req)
    assert response["ok"], response
    bridge.validate_response(req, response)
    changed = copy.deepcopy(req)
    changed["document"]["features"][-1]["edge_faces"][0] = "a/face/cap.end"
    with pytest.raises(ValueError):
        bridge.validate_response(changed, response)


def test_upstream_dimension_edit_rebuilds_transform_union_cut_lineage():
    source = document("union")
    source["features"].append(
        {"id": "cut", "kind": "cut", "inputs": {"base": "final", "tool": "a"}}
    )
    source["active_feature"] = "cut"
    source["parameters"] = {"width": 10}
    source["features"][0]["params"]["width"] = "width"
    for width in (10, 15):
        source["parameters"]["width"] = width
        req = {"protocol_version": 1, "result_version": 2, "document": source}
        response = process_request(req)
        assert response["ok"], response
        bridge.validate_response(req, response)
        assert response["result"]["features"][-1]["stats"]["volume"] == pytest.approx(500)


def profile_feature_document(kind):
    import math

    if kind == "loft":
        features = [
            {"id": "start", "kind": "sketch_circle", "params": {"radius": 3}},
            {"id": "end", "kind": "sketch_circle", "params": {"radius": 5, "z": 10}},
            {"id": "solid", "kind": "loft", "inputs": {"start": "start", "end": "end"}},
        ]
    else:
        features = [
            {"id": "start", "kind": "sketch_circle", "params": {"radius": 2}},
            {
                "id": "path",
                "kind": "sketch_constrained",
                "sketch": {
                    "schema_version": 2,
                    "id": "path_geometry",
                    "units": "mm",
                    "plane": {
                        "id": "xz",
                        "origin": [0, 0, 0],
                        "quaternion": [math.sqrt(0.5), math.sqrt(0.5), 0, 0],
                    },
                    "points": [{"id": "a", "u": 0, "v": 0}, {"id": "b", "u": 0, "v": 10}],
                    "lines": [{"id": "path_line", "start": "a", "end": "b"}],
                    "circles": [],
                    "constraints": [],
                },
            },
            {"id": "solid", "kind": "sweep", "inputs": {"profile": "start", "path": "path"}},
        ]
    return {
        "schema_version": 2,
        "id": "profile_part",
        "name": "Profile-driven solid",
        "units": "mm",
        "parameters": {},
        "features": features,
        "active_feature": "solid",
    }


@pytest.mark.parametrize("kind", ["loft", "sweep"])
def test_profile_driven_solids_replay_export_and_capture(kind, tmp_path):
    source = profile_feature_document(kind)
    request = {
        "protocol_version": 1,
        "result_version": 2,
        "document": source,
        "action": "export_step",
        "destination": str(tmp_path / (kind + ".step")),
    }
    response = process_request(request)
    assert response["ok"], response
    bridge.validate_response(request, response)
    edit = importlib.import_module(package.__name__ + ".assembly_edit")
    validator = importlib.import_module(package.__name__ + ".assembly_bridge")
    request = {
        "protocol_version": 1,
        "kind": "assembly",
        "assembly_protocol_version": 1,
        "result_version": 2,
        "action": "assembly_replay",
        "assembly": edit.new_from_part(contracts._expected_document(source)),
    }
    response = process_request(request)
    assert response["ok"], response
    validator.validate_response(request, response)


def test_loft_blocks_open_section_but_sweep_can_consume_it_as_path():
    source = profile_feature_document("sweep")
    source["features"][-1] = {
        "id": "solid",
        "kind": "loft",
        "inputs": {"start": "start", "end": "path"},
    }
    request = {"protocol_version": 1, "result_version": 2, "document": source}
    response = process_request(request)
    assert not response["ok"]
    final = response["result"]["features"][-1]
    assert final["status"] == "blocked" and final["error"]["code"] == "profile_unavailable"
    bridge.validate_response(request, response)


def test_schema1_construction_angle_snapshot_matches_core_bytes():
    from mechanical_cad.model import Document

    source = profile_feature_document("sweep")
    sketch = source["features"][1]["sketch"]
    sketch["schema_version"] = 1
    sketch.pop("circles")
    sketch["points"].append({"id": "c", "u": 10, "v": 0})
    sketch["lines"][0]["construction"] = False
    sketch["lines"].append({"id": "reference", "start": "a", "end": "c", "construction": True})
    sketch["constraints"] = [
        {"id": "right_angle", "kind": "angle", "refs": ["path_line", "reference"], "value": 90}
    ]
    canonical = Document.from_dict(source).to_dict()
    assert contracts._expected_document(source) == canonical
    assert "construction" not in canonical["features"][1]["sketch"]["lines"][0]


def face_profile_document(kind="sketch_face_circle"):
    source = document("transform")
    source["parameters"] = {"height": 10}
    source["features"][1]["params"]["length"] = "height"
    source["features"] = source["features"][:2] + [
        {
            "id": "face_profile",
            "kind": kind,
            "params": {"radius": 2} if kind.endswith("circle") else {"width": 3, "height": 4},
            "inputs": {"support": "a"},
            "support_face": "a/face/cap.end",
        },
        {
            "id": "boss",
            "kind": "extrude",
            "params": {"length": 2},
            "inputs": {"profile": "face_profile"},
        },
    ]
    source["active_feature"] = "boss"
    return source


@pytest.mark.parametrize("kind", ["sketch_face_rectangle", "sketch_face_circle"])
def test_associative_face_profile_tracks_parent_height_and_exports(kind, tmp_path):
    source = face_profile_document(kind)
    for height in (10, 20):
        source["parameters"]["height"] = height
        request = {
            "protocol_version": 1,
            "result_version": 2,
            "document": source,
            "action": "export_step",
            "destination": str(tmp_path / (kind + ".step")),
        }
        response = process_request(request)
        assert response["ok"], response
        bridge.validate_response(request, response)
        vertices = response["result"]["features"][-1]["mesh"]["vertices"]
        assert min(p[2] for p in vertices) == pytest.approx(height)
        assert max(p[2] for p in vertices) == pytest.approx(height + 2)
    edit = importlib.import_module(package.__name__ + ".assembly_edit")
    policy = importlib.import_module(package.__name__ + ".operation_contracts")
    validator = importlib.import_module(package.__name__ + ".assembly_bridge")
    assembly = edit.new_from_part(contracts._expected_document(source))
    assert policy.result_version_for_assembly(assembly) == 3
    request = {
        "protocol_version": 1,
        "kind": "assembly",
        "assembly_protocol_version": 1,
        "result_version": 3,
        "action": "assembly_replay",
        "assembly": assembly,
    }
    response = process_request(request)
    assert response["ok"], response
    validator.validate_response(request, response)


def test_associative_support_never_guesses_missing_face_or_accepts_summary_only():
    source = face_profile_document()
    request = {"protocol_version": 1, "result_version": 2, "document": source}
    response = process_request(request)
    assert response["ok"], response
    forged_sources = contracts._expected_document(source)["features"]
    forged_sources[-2]["support_face"] = "a/face/missing"
    with pytest.raises(ValueError, match="support is missing"):
        bridge._validate_face_support(response["result"]["features"], forged_sources)
    source["features"][-2]["support_face"] = "a/face/missing"
    response = process_request({**request, "document": source})
    assert not response["ok"]
    assert response["result"]["features"][-1]["status"] == "blocked"
    bridge.validate_response({**request, "document": source}, response)
    edit = importlib.import_module(package.__name__ + ".assembly_edit")
    request = {
        "protocol_version": 1,
        "kind": "assembly",
        "assembly_protocol_version": 1,
        "result_version": 2,
        "action": "assembly_replay",
        "assembly": edit.new_from_part(contracts._expected_document(face_profile_document())),
    }
    response = process_request(request)
    assert not response["ok"] and response["error"]["code"] == "unsupported_result_version"
