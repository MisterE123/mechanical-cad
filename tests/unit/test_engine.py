"""Failure propagation tests use an explicit fake port, never fake CAD claims."""

import pytest

from mechanical_cad.engine import regenerate
from mechanical_cad.errors import CADException
from mechanical_cad.model import Document


class RecordingKernel:
    def __init__(self):
        self.calls = []

    def rectangle(self, **params):
        self.calls.append(("rectangle", params))
        return ("rectangle", params)

    def circle(self, **params):
        self.calls.append(("circle", params))
        return ("circle", params)

    def extrude(self, profile, length):
        self.calls.append(("extrude", length))
        return ("extrude", length)

    def cut(self, base, tool):
        self.calls.append(("cut", {}))
        return ("cut", {})

    def inspect(self, shape):
        return {"volume": 1, "area": 1, "solids": 1, "faces": 1}

    def topology(self, *args):
        return []

    def tessellate(self, *args, **kwargs):
        return {"vertices": [], "triangles": []}


def test_replay_follows_graph_and_resolves_parameters(plate):
    kernel = RecordingKernel()
    replay = regenerate(plate, kernel)
    assert replay.ok
    assert [call[0] for call in kernel.calls] == [
        "rectangle",
        "circle",
        "extrude",
        "extrude",
        "cut",
    ]
    assert replay.result["features"][0]["resolved_params"]["width"] == 40
    assert replay.result["features"][2]["resolved_params"]["x"] == 20


def test_invalid_dimension_blocks_only_dependent_features(plate):
    replay = regenerate(plate.with_parameter("width", -1), RecordingKernel())
    assert not replay.ok
    statuses = {item["id"]: item["status"] for item in replay.result["features"]}
    assert statuses == {
        "profile": "failed",
        "pad": "blocked",
        "hole_profile": "ok",
        "hole_tool": "ok",
        "body": "blocked",
    }
    assert "profile" not in replay.shapes and "body" not in replay.shapes
    assert replay.result["features"][0]["mesh"] is None
    assert replay.result["features"][0]["error"]["code"] == "invalid_dimension"


def test_kernel_error_is_explicit_and_not_cached(plate):
    class BrokenKernel(RecordingKernel):
        def cut(self, base, tool):
            raise RuntimeError("boolean failed")

    replay = regenerate(plate, BrokenKernel())
    body = replay.result["features"][-1]
    assert body["status"] == "failed"
    assert body["error"]["code"] == "kernel_error"
    assert body["mesh"] is None and body["stats"] is None
    assert "body" not in replay.shapes


def test_multi_solid_output_fails_closed(plate):
    class MultiSolidKernel(RecordingKernel):
        def inspect(self, shape):
            return {"solids": 2}

    replay = regenerate(plate, MultiSolidKernel())
    assert replay.result["features"][1]["error"]["code"] == "unsupported_solid_count"


@pytest.mark.parametrize("tolerance", [0, -1, 11, True, "small", float("nan")])
def test_mesh_tolerance_is_bounded(plate, tolerance):
    with pytest.raises(CADException) as error:
        regenerate(plate, RecordingKernel(), linear_deflection=tolerance)
    assert error.value.code == "invalid_tolerance"


def test_empty_document_is_valid_without_geometry():
    document = Document.from_dict(
        {
            "schema_version": 1,
            "id": "empty",
            "name": "Empty",
            "units": "mm",
            "parameters": {},
            "features": [],
            "active_feature": None,
        }
    )
    replay = regenerate(document, RecordingKernel())
    assert replay.ok and replay.shapes == {}


def test_feature_formula_error_has_feature_and_parameter(plate):
    data = plate.to_dict()
    data["features"][0]["params"]["width"] = "unknown + 1"
    replay = regenerate(Document.from_dict(data), RecordingKernel())
    error = replay.result["features"][0]["error"]
    assert error["code"] == "unknown_parameter" and "profile.width" in error["message"]
