"""Current native open-line evidence projected to informational UI, not readiness."""

import importlib
import sys
import types
from pathlib import Path

import pytest

pytest.importorskip("slvs")

from mechanical_cad.model import Document, Feature
from mechanical_cad.sidecar import process_request
from mechanical_cad.sketch_model import Constraint, Line, Point, SketchDefinition

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "mcad_open_status_native_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
sys.modules[PACKAGE] = package
status = importlib.import_module(PACKAGE + ".compact_status")


@pytest.mark.parametrize("version", [2, 3])
def test_native_horizontal_line_is_open_not_failed_or_extrudable(version):
    sketch = SketchDefinition(
        "shape", (Point("a", -32.34782409667969, 2.68323016166687),
                  Point("b", 6.409936904907227, 2.68323016166687)),
        (Line("line", "a", "b"),),
        (Constraint("horizontal", "horizontal", ("line",)),),
        schema_version=version,
    )
    document = Document.from_dict({
        "schema_version": 2, "id": "open_line", "name": "Open Line", "units": "mm",
        "parameters": {}, "active_feature": "profile",
        "features": [Feature("profile", "sketch_constrained", "Sketch", sketch=sketch).to_dict()],
    })
    request = {"protocol_version": 1, "action": "solve_sketch", "result_version": version,
               "document": document.to_dict(), "feature_id": "profile"}
    response = process_request(request)
    bridge = importlib.import_module(PACKAGE + (
        ".sketch_action_bridge" if version == 2 else ".result_v3"
    ))
    qualified = bridge.validate_solve_response(response, request)
    assert qualified["ok"]
    result = qualified["result"]
    assert result["profile_check"] == {"ready": False, "error": {
        "code": "open_profile", "message": "Close this line chain before extrusion.",
    }}
    assert status.profile_label(result["profile_check"]) == (
        "Open sketch · close a loop", "INFO",
    )
    assert status.sketch_label(result["sketch"]) == ("Underdefined · 3 DoF", "INFO")
    # Native replay can save open geometry, but does not provide an extrusion profile.
    replay = process_request({"protocol_version": 1, "result_version": version,
                              "document": document.to_dict()})
    assert replay["ok"]
    feature = replay["result"]["features"][0]
    assert feature["output"]["kind"] == "sketch"
    assert feature["output"]["profile"]["state"] == "unavailable"
    assert status.saved_profile_state(feature)[0] is False
