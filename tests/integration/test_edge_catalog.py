"""Native one-click edge intent and its isolated transport boundary."""

import copy
import importlib
import sys
import types
from pathlib import Path

import pytest

from mechanical_cad.edge_catalog import process_edge_catalog
from mechanical_cad.engine import regenerate
from mechanical_cad.kernel_ocp import OCPKernel
from mechanical_cad.model import Document, Feature
from mechanical_cad.sidecar import process_request


@pytest.fixture
def addon():
    name = "mcad_edge_contract_test"
    module = types.ModuleType(name)
    module.__path__ = [
        str(Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender")
    ]
    sys.modules[name] = module
    yield lambda leaf: importlib.import_module(name + "." + leaf)
    for key in list(sys.modules):
        if key == name or key.startswith(name + "."):
            del sys.modules[key]


def document(circle=False):
    profile = (
        Feature("s", "sketch_circle", "Circle", {"radius": 5})
        if circle
        else Feature("s", "sketch_rectangle", "Rectangle", {"width": 10, "height": 10})
    )
    return Document(
        "part",
        "Part",
        {},
        (profile, Feature("pad", "extrude", "Pad", {"length": 10}, {"profile": "s"})),
        "pad",
    )


def request(doc=None, version=2):
    return {
        "protocol_version": 1,
        "result_version": version,
        "action": "edge_catalog",
        "document": (doc or document()).to_dict(),
        "options": {"linear_deflection": 0.1},
    }


@pytest.mark.parametrize("version", [2, 3])
def test_guarded_catalog_and_strict_client(addon, version):
    operation = request(version=version)
    contracts = addon("backend_contracts")
    guarded = contracts.compose_request(operation)
    response = process_request(guarded)
    assert response["ok"], response
    assert "mcad.edge-catalog/1" in response["backend_receipt"]["confirmed_capabilities"]
    projection = addon("edge_catalog_bridge").validate_response(
        operation, contracts.project_response(response)
    )
    assert len(projection["result"]["catalogs"]["pad"]) == 12


@pytest.mark.parametrize("kind,param", [("fillet", "radius"), ("chamfer", "distance")])
def test_each_box_edge_is_unique_native_blend_intent(kind, param):
    kernel = OCPKernel()
    replay = regenerate(document(), kernel, result_version=2)
    shape = replay.shapes["pad"]
    catalog = kernel.edge_display_catalog(shape)
    assert len(catalog) == 12
    for entry in catalog:
        assert len(entry["points"]) == 2
        result = getattr(kernel, kind)(shape, **{param: 0.5}, edge_faces=entry["faces"])
        stats = kernel.inspect(result)
        assert stats["valid"] and stats["solids"] == 1
        assert 990 < stats["volume"] < 1000


def test_cylinder_rims_not_seam():
    response = process_edge_catalog(request(document(circle=True)))
    entries = response["result"]["catalogs"]["pad"]
    assert len(entries) == 2
    assert all(len(entry["points"]) > 8 for entry in entries)
    assert all(entry["points"][0] == pytest.approx(entry["points"][-1]) for entry in entries)


@pytest.mark.parametrize("corrupt", ["extra", "duplicate", "unstable", "nan", "stale"])
def test_catalog_rejects_forged_client_fields(addon, corrupt):
    operation = request()
    response = process_edge_catalog(operation)
    entries = response["result"]["catalogs"]["pad"]
    if corrupt == "extra":
        entries[0]["edge_id"] = "not-persistent"
    elif corrupt == "duplicate":
        entries.append(copy.deepcopy(entries[0]))
    elif corrupt == "unstable":
        entries[0]["faces"][0] = "snapshot-face"
    elif corrupt == "nan":
        entries[0]["points"][0][0] = float("nan")
    else:
        operation["document"]["features"][0]["params"]["width"] = 11
    with pytest.raises(ValueError):
        addon("edge_catalog_bridge").validate_response(operation, response)


def test_v1_replay_unchanged_after_opt_in_catalog():
    legacy = {"protocol_version": 1, "document": document().to_dict()}
    before = process_request(legacy)
    process_edge_catalog(request())
    assert before == process_request(legacy)
    assert before == process_request({**legacy, "result_version": 1})
    assert all(
        set(f["mesh"]) == {"vertices", "triangles", "triangle_face_ids"}
        for f in before["result"]["features"]
    )


def test_segment_projection_is_display_only(addon):
    distance, fraction = addon("edge_catalog_bridge").nearest_segment((5, 2), (0, 0), (10, 0))
    assert distance == 2 and fraction == 0.5


def test_real_guarded_sidecar_transport(addon):
    root = Path(__file__).resolve().parents[2]
    selection = addon("backend_selection").BackendSelection.capture(
        str(root), sys.executable, generation=1, lifetime_id="edge-catalog-test"
    )
    token = object()
    evidence = addon("guarded_transport").execute(
        addon("backend_contracts").prepare_request(request()),
        selection,
        owner_token=token,
        current_selection=lambda: selection,
    )
    projection = evidence.revalidate(
        selection,
        owner_token=token,
        expected_action="edge_catalog",
        expected_result_version=2,
        require_success=True,
    )
    assert len(projection["result"]["catalogs"]["pad"]) == 12


def test_symmetric_box_has_exact_projection_endpoint_identities(addon):
    original = document().to_dict()
    original["features"][-1]["kind"] = "extrude_symmetric"
    operation = request(Document.from_dict(original), version=3)
    response = process_request(operation)
    assert response["ok"], response
    addon("edge_catalog_bridge").validate_response(operation, response)
    entries = response["result"]["catalogs"]["pad"]
    assert len(entries) == 12
    assert all(len(entry["points"]) == 2 and len(entry["endpoint_faces"]) == 2 for entry in entries)
    top = [entry for entry in entries if "pad/face/cap.end" in entry["faces"]]
    assert len(top) == 4
    assert all(point[2] == pytest.approx(5) for entry in top for point in entry["points"])
