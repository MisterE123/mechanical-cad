"""Native proposal geometry behind the independent, selection-only repair catalog."""

import copy
import importlib
import math
import sys
import types
from pathlib import Path

import pytest

from mechanical_cad.sidecar import process_request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests"))
from end_face_repair_cases import end_face_case, feature  # noqa: E402

package = types.ModuleType("native_end_face_catalog")
package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
sys.modules[package.__name__] = package
helper = importlib.import_module(package.__name__ + ".end_face_repair")


def replay(document, version):
    request = {"protocol_version": 1, "result_version": version, "document": document}
    response = process_request(request)
    validator = importlib.import_module(
        package.__name__ + (".part_result_bridge" if version == 2 else ".result_v3")
    )
    assert validator.validate_response(request, response) == response
    return response


@pytest.mark.parametrize("version", [2, 3])
@pytest.mark.parametrize("failure", ["split", "missing"])
def test_catalog_uses_proposed_native_planes_and_partial_explicit_repair(version, failure):
    accepted, proposed = end_face_case(failure=failure)
    assert replay(accepted, version)["ok"]
    before = copy.deepcopy(proposed)
    failed = replay(proposed, version)
    entries = helper.end_face_candidates(proposed, "tool", failed["result"])
    assert not any(
        row["target"] == "slotted" and row["face"] == "block/face/cap.end" for row in entries
    )
    assert all(not row["face"].startswith("snapshot:") for row in entries)
    choice = next(
        row
        for row in entries
        if row["target"] == "replacement" and row["face"] == "block/face/cap.end"
    )
    assert choice["reach"] == pytest.approx(7)
    assert choice["length"] == pytest.approx(6.5)
    partial = helper.replace_end_face(
        proposed, "tool", choice["target"], choice["face"], failed["result"]
    )
    part = replay(partial, version)
    assert not part["ok"]
    rows = {row["id"]: row for row in part["result"]["features"]}
    assert rows["tool"]["status"] == "ok" and rows["tool"]["stats"]["volume"] == pytest.approx(
        6.5 * math.pi
    )
    assert rows["tool2"]["error"]["code"] == "invalid_extrusion_end_face"
    complete = helper.replace_end_face(
        partial, "tool2", "replacement", "block/face/cap.end", part["result"]
    )
    good = replay(complete, version)
    assert good["ok"], good
    assert good["result"]["features"][-1]["stats"]["volume"] == pytest.approx(12.75 * math.pi)
    assert feature(complete, "tool")["params"] == feature(proposed, "tool")["params"]
    assert proposed == before


@pytest.mark.parametrize("version", [2, 3])
@pytest.mark.parametrize("kind", ["constrained", "attached_constrained", "face_primitive"])
def test_catalog_uses_actual_profile_frame_not_outward_face_or_saved_local_origin(version, kind):
    _, proposed = end_face_case(consumers=1)
    profile = feature(proposed, "profile")
    feature(proposed, "tool")["params"]["direction"] = 1
    if kind == "face_primitive":
        profile.update(
            kind="sketch_face_circle",
            params={"radius": 1, "z": 1},
            inputs={"support": "block"},
            support_face="block/face/cap.end",
        )
    else:
        proposed["schema_version"] = 2
        profile.update(
            kind="sketch_constrained",
            params={},
            inputs={},
            sketch={
                "schema_version": 2,
                "id": "circle_geometry",
                "units": "mm",
                "plane": {
                    "id": "local",
                    "origin": [0, 0, 11 if kind == "constrained" else 1],
                    "quaternion": [1, 0, 0, 0],
                },
                "points": [{"id": "center", "u": 0, "v": 0}],
                "lines": [],
                "circles": [{"id": "circle", "center": "center", "radius": 1}],
                "constraints": [
                    {"id": "anchor", "kind": "fixed", "refs": ["center"], "target": [0, 0]},
                    {"id": "radius", "kind": "radius", "refs": ["circle"], "value": 1},
                ],
            },
        )
        if kind == "attached_constrained":
            profile.update(inputs={"support": "block"}, support_face="block/face/cap.end")
    failed = replay(proposed, version)
    choices = helper.end_face_candidates(proposed, "tool", failed["result"])
    choice = next(
        row
        for row in choices
        if row["target"] == "replacement" and row["face"] == "block/face/cap.end"
    )
    assert choice["reach"] == pytest.approx(2)
    assert choice["length"] == pytest.approx(1.5)
    repaired = helper.replace_end_face(
        proposed, "tool", "replacement", choice["face"], failed["result"]
    )
    good = replay(repaired, version)
    assert good["ok"], good
    assert good["result"]["features"][-1]["stats"]["volume"] == pytest.approx(1.5 * math.pi)


@pytest.mark.parametrize("version", [2, 3])
def test_retarget_exposes_a_later_reference_failure_without_reverting_first_repair(version):
    accepted, proposed = end_face_case()
    for document in (accepted, proposed):
        feature(document, "profile2")["params"]["z"] = 12
        feature(document, "tool2").update(
            inputs={"profile": "profile2", "target": "tool"},
            end_face="tool/face/cap.end",
            params={"direction": -1, "offset": 0},
        )
    assert replay(accepted, version)["ok"]
    failed = replay(proposed, version)
    assert (
        next(row for row in failed["result"]["features"] if row["id"] == "tool2")["status"]
        == "blocked"
    )
    first = helper.replace_end_face(
        proposed, "tool", "replacement", "block/face/cap.end", failed["result"]
    )
    partial = replay(first, version)
    rows = {row["id"]: row for row in partial["result"]["features"]}
    assert rows["tool"]["status"] == "ok"
    assert rows["tool2"]["error"]["code"] == "invalid_extrusion_end_face"
    assert "ahead" in rows["tool2"]["error"]["message"]
    complete = helper.replace_end_face(
        first, "tool2", "block", "block/face/cap.end", partial["result"]
    )
    good = replay(complete, version)
    assert good["ok"], good
    assert good["result"]["features"][-1]["stats"]["volume"] == pytest.approx(2 * math.pi)
    assert feature(complete, "tool")["inputs"]["target"] == "replacement"


@pytest.mark.parametrize("version", [2, 3])
def test_rotated_profile_catalog_respects_authored_normal_and_direction(version):
    _, proposed = end_face_case(consumers=1)
    proposed["schema_version"] = 2
    feature(proposed, "replacement")["params"].update(rx=90)
    feature(proposed, "profile").update(
        kind="sketch_constrained",
        params={},
        inputs={},
        sketch={
            "schema_version": 2,
            "id": "rotated_geometry",
            "units": "mm",
            "plane": {
                "id": "rotated",
                "origin": [0, -20, 0],
                "quaternion": [math.sqrt(0.5), math.sqrt(0.5), 0, 0],
            },
            "points": [{"id": "center", "u": 0, "v": 0}],
            "lines": [],
            "circles": [{"id": "circle", "center": "center", "radius": 1}],
            "constraints": [
                {"id": "anchor", "kind": "fixed", "refs": ["center"], "target": [0, 0]},
                {"id": "radius", "kind": "radius", "refs": ["circle"], "value": 1},
            ],
        },
    )
    failed = replay(proposed, version)
    choices = helper.end_face_candidates(proposed, "tool", failed["result"])
    choice = next(
        row
        for row in choices
        if row["target"] == "replacement" and row["face"] == "block/face/cap.end"
    )
    assert choice["reach"] == pytest.approx(10)
    assert choice["length"] == pytest.approx(9.5)
    fixed = helper.replace_end_face(
        proposed, "tool", choice["target"], choice["face"], failed["result"]
    )
    good = replay(fixed, version)
    assert good["ok"], good
    assert good["result"]["features"][-1]["stats"]["volume"] == pytest.approx(9.5 * math.pi)


def test_prepared_accepted_example_matches_qualified_fixture():
    import json

    prepared = json.loads(
        (ROOT / "examples/topology_end_face/staged_end_face_repair.mcad.json").read_text()
    )
    assert prepared == end_face_case()[0]
    assert replay(prepared, 3)["ok"]
