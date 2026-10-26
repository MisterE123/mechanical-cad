"""Exact-solid assembly reuse with explicitly negotiated embedded sketch outputs."""

import copy
import json
import math
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from mechanical_cad.assembly_model import AssemblyDocument, replace_source
from mechanical_cad.assembly_policy import fingerprint
from mechanical_cad.assembly_service import preflight_source_update, run_assembly_action
from mechanical_cad.errors import CADException
from mechanical_cad.kernel_ocp import OCPKernel
from mechanical_cad.model import Document, Feature
from mechanical_cad.sidecar import process_request
from mechanical_cad.sketch_model import Circle, Constraint, Line, Point, SketchDefinition

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.kernel


def legacy_assembly():
    return AssemblyDocument.from_json(
        (ROOT / "examples/reused_blocks.mcad-assembly.json").read_text()
    )


def circle_document(*, independent_open=False, radius=5):
    sketch = SketchDefinition(
        "circle_sketch",
        (Point("center", 0, 0),),
        (),
        (Constraint("size", "radius", ("rim",), "radius"),),
        circles=(Circle("rim", "center", 5),),
        schema_version=2,
    )
    features = (
        Feature("profile", "sketch_constrained", "Circle", sketch=sketch),
        Feature("pad", "extrude", "Solid", {"length": 10}, {"profile": "profile"}),
    )
    if independent_open:
        open_sketch = SketchDefinition(
            "open_sketch",
            (Point("start", 0, 0), Point("end", 10, 0)),
            (Line("line", "start", "end"),),
            (),
            schema_version=2,
        )
        features += (Feature("open", "sketch_constrained", "Open", sketch=open_sketch),)
    return Document.from_dict(
        {
            "schema_version": 2,
            "id": "user_part",
            "name": "Authored circle and independent draft",
            "units": "mm",
            "parameters": {"radius": radius},
            "features": [feature.to_dict() for feature in features],
            "active_feature": "pad",
        }
    )


def assembly(**kwargs):
    return replace_source(legacy_assembly(), "user_part", circle_document(**kwargs))


def request(candidate, **kwargs):
    return {
        "protocol_version": 1,
        "kind": "assembly",
        "assembly_protocol_version": 1,
        "assembly": candidate.to_dict(),
        "action": "assembly_replay",
        **kwargs,
    }


class CountKernel(OCPKernel):
    def __init__(self):
        super().__init__()
        self.extrusions = 0
        self.checks = 0

    def extrude(self, *args, **kwargs):
        self.extrusions += 1
        return super().extrude(*args, **kwargs)

    def manufacturing_check(self, *args, **kwargs):
        self.checks += 1
        return super().manufacturing_check(*args, **kwargs)


@pytest.mark.parametrize("independent_open", [False, True])
def test_circle_and_independent_open_share_one_actual_solid(independent_open):
    candidate = assembly(independent_open=independent_open)
    before = candidate.to_json()
    # Two definitions of the same output still share one verified native solid.
    candidate = replace(
        candidate,
        parts=(*candidate.parts, replace(candidate.parts[0], id="second_definition")),
        instances=tuple(
            replace(instance, part_id="second_definition") if instance.id == "b" else instance
            for instance in candidate.instances
        ),
    )
    kernel = CountKernel()
    response = run_assembly_action(candidate, result_version=2, kernel=kernel)
    assert response["ok"], response["error"]
    assert response["result_version"] == response["request"]["result_version"] == 2
    assert kernel.extrusions == kernel.checks == 1
    assert len(response["result"]["instances"]) == 3
    assert len(response["result"]["parts"]) == 2
    assert response["result"]["parts"][0]["geometry_check"]["brep"]["volume"] == pytest.approx(
        math.pi * 25 * 10
    )
    summary = response["result"]["source_replays"][0]
    assert set(summary) == {"source_document_id", "source_digest", "status", "features"}
    assert all(
        set(row) == {"id", "status", "error", "stats", "output"} for row in summary["features"]
    )
    if independent_open:
        assert summary["features"][-1] == {
            "id": "open",
            "status": "ok",
            "error": None,
            "stats": None,
            "output": {
                "kind": "sketch",
                "display": "solved_sketch",
                "profile": {
                    "state": "unavailable",
                    "reason": {
                        "code": "open_profile",
                        "message": "Close this line chain before extrusion.",
                    },
                },
            },
        }
    assert assembly(independent_open=independent_open).to_json() == before


def test_open_feature_cannot_be_selected_as_assembly_solid():
    raw = assembly(independent_open=True).to_dict()
    raw["parts"][0]["output_feature_id"] = "open"
    with pytest.raises(CADException) as caught:
        AssemblyDocument.from_dict(raw)
    assert caught.value.code == "invalid_output"


def test_open_profile_consumed_by_declared_solid_blocks_assembly_without_stale_output():
    doc = circle_document(independent_open=True)
    raw = doc.to_dict()
    raw["features"][1]["inputs"]["profile"] = "open"
    candidate = replace_source(legacy_assembly(), "user_part", Document.from_dict(raw))
    response = run_assembly_action(candidate, result_version=2)
    assert not response["ok"] and response["error"]["code"] == "source_replay_failed"
    rows = {row["id"]: row for row in response["result"]["source_replays"][0]["features"]}
    assert rows["open"]["status"] == "ok"
    assert rows["pad"]["status"] == "blocked"
    assert rows["pad"]["error"]["code"] == "profile_unavailable"
    assert response["result"]["parts"] == [] and response["report"]["poses"] == []


def test_all_instance_source_update_requires_explicit_version_and_is_atomic():
    original = legacy_assembly()
    before = original.to_json()
    doc = circle_document(independent_open=True)
    denied = preflight_source_update(original, "user_part", doc, kernel=object())
    assert denied["error"]["code"] == "unsupported_result_version"
    assert denied["update"]["candidate"] is None and not denied["result"]["source_replays"]
    response = preflight_source_update(original, "user_part", doc, result_version=2)
    assert response["ok"]
    update = response["update"]
    assert update["affected_instances"] == ["root", "a", "b"]
    candidate = AssemblyDocument.from_dict(update["candidate"])
    assert candidate.instances == original.instances and candidate.joints == original.joints
    assert candidate.parts[0].mate_frames == original.parts[0].mate_frames
    assert candidate.source_hashes["user_part"] == doc.content_hash
    assert candidate.parts[0].source_digest == doc.content_hash
    assert original.to_json() == before


def test_version_two_request_and_blocked_default_roundtrip_real_sidecar():
    for version in (None, 2):
        candidate = request(assembly(independent_open=True))
        if version is not None:
            candidate["result_version"] = version
        completed = subprocess.run(
            [sys.executable, "-m", "mechanical_cad.sidecar"],
            input=json.dumps(candidate),
            text=True,
            capture_output=True,
            timeout=30,
        )
        response = json.loads(completed.stdout)
        assert response["input_fingerprint"] == fingerprint(candidate)
        assert response["ok"] is (version == 2)
        if version == 2:
            assert completed.returncode == 0 and response["result_version"] == 2
        else:
            assert completed.returncode == 1
            assert response["error"]["code"] == "unsupported_result_version"
            assert "result_version 2" in response["error"]["message"]
            assert "result_version" not in response
            assert not response["result"]["source_replays"]


def test_legacy_default_and_explicit_one_preserve_complete_service_shape_and_hashes():
    candidate = request(legacy_assembly())
    default = process_request(candidate)
    explicit = process_request({**candidate, "result_version": 1})
    assert default["ok"] and explicit["ok"]
    assert default["input_fingerprint"] != explicit["input_fingerprint"]
    default.pop("input_fingerprint")
    explicit.pop("input_fingerprint")
    assert default == explicit
    assert "result_version" not in default and "result_version" not in default["request"]
    upgraded = process_request({**candidate, "result_version": 2})
    assert upgraded["ok"]
    legacy_result = copy.deepcopy(upgraded["result"])
    for replay in legacy_result["source_replays"]:
        for feature in replay["features"]:
            feature.pop("output")
    assert legacy_result == default["result"]
    assert upgraded["request_fingerprint"] != default["request_fingerprint"]
    assert upgraded["report_fingerprint"] != default["report_fingerprint"]


@pytest.mark.parametrize("version", [None, False, True, 0, 4, 2.0, "2", [], {}])
def test_invalid_wire_version_is_bound_without_native_work(version, monkeypatch):
    from mechanical_cad import assembly_service

    monkeypatch.setattr(
        assembly_service, "regenerate", lambda *a, **k: pytest.fail("must validate before replay")
    )
    candidate = request(legacy_assembly(), result_version=version)
    response = process_request(candidate)
    assert not response["ok"] and response["error"]["code"] == "unsupported_result_version"
    assert response["input_fingerprint"] == fingerprint(candidate)
    assert response["request"]["result_version"] == version
    assert response["request_fingerprint"] == fingerprint(response["request"])
    assert not response["result"]["source_replays"]
    assert "native_runtime_versions" not in response["report"]
    changed = copy.deepcopy(candidate)
    changed["result_version"] = [version]
    other = process_request(changed)
    assert response["request_fingerprint"] != other["request_fingerprint"]
    assert response["report_fingerprint"] != other["report_fingerprint"]


@pytest.mark.parametrize("action", ["assembly_replay", "assembly_check", "assembly_sample"])
def test_new_native_response_roundtrips_through_addon_client(action):
    candidate = assembly(independent_open=True)
    script = f"""
import json, sys, types
package = types.ModuleType('isolated_assembly_client')
package.__path__ = [{str(ROOT / "blender_addon/mechanical_cad_blender")!r}]
sys.modules[package.__name__] = package
from isolated_assembly_client import assembly_bridge
request = json.load(sys.stdin)
response = assembly_bridge.assembly_action(
    request['assembly'], request['action'], result_version=2,
    coordinates={{'slide_a': 100, 'slide_b': 200}},
    requirements=None if request['action'] == 'assembly_replay' else [],
    samples={{'joint_id': 'slide_a', 'values': [100, 120]}}
        if request['action'] == 'assembly_sample' else None,
    project_root={str(ROOT)!r}, python_executable=sys.executable,
)
assert response['ok'], response['error']
assert response['result_version'] == response['request']['result_version'] == 2
assert response.assert_unchanged() is response
assert not {{'bpy', 'OCP', 'slvs', 'mechanical_cad'}}.intersection(sys.modules)
print('ASSEMBLY_V2_ROUNDTRIP_OK')
"""
    completed = subprocess.run(
        [sys.executable, "-I", "-B", "-c", script],
        input=json.dumps(request(candidate, action=action)),
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    assert "ASSEMBLY_V2_ROUNDTRIP_OK" in completed.stdout


@pytest.mark.parametrize("malformation", ["document", "envelope"])
def test_pre_service_v2_wire_error_echoes_version_without_publishable_result(malformation):
    candidate = request(assembly(), result_version=2)
    if malformation == "document":
        candidate["assembly"]["part_sources"][0]["document"]["features"][0]["sketch"][
            "schema_version"
        ] = 99
    else:
        candidate["unexpected"] = "field"
    completed = subprocess.run(
        [sys.executable, "-m", "mechanical_cad.sidecar"],
        input=json.dumps(candidate),
        text=True,
        capture_output=True,
        timeout=30,
    )
    response = json.loads(completed.stdout)
    assert completed.returncode == 1
    assert response["result_version"] == 2
    assert response["ok"] is False and response["result"] is None
    assert response["error"]["code"] == (
        "unsupported_schema" if malformation == "document" else "invalid_request"
    )


def test_actual_native_source_accepts_reordered_canonical_sketch_constraints():
    raw = circle_document().to_dict()
    raw["features"][0]["sketch"]["constraints"].append(
        {"id": "anchor", "kind": "fixed", "refs": ["center"], "target": [0, 0]}
    )
    candidate = replace_source(legacy_assembly(), "user_part", Document.from_dict(raw))
    sent = request(candidate, result_version=2)
    sent["assembly"]["part_sources"][0]["document"]["features"][0]["sketch"][
        "constraints"
    ].reverse()
    response = process_request(sent)
    assert response["ok"]
    script = f"""
import json, sys, types
package = types.ModuleType('isolated_reordered_source')
package.__path__ = [{str(ROOT / "blender_addon/mechanical_cad_blender")!r}]
sys.modules[package.__name__] = package
from isolated_reordered_source import assembly_bridge
request, response = json.load(sys.stdin)
accepted = assembly_bridge.validate_response(request, response)
assert accepted['ok'] and accepted.request_snapshot() == request
assert not {{'bpy', 'OCP', 'slvs', 'mechanical_cad'}}.intersection(sys.modules)
print('REORDERED_NATIVE_SOURCE_ACCEPTED')
"""
    completed = subprocess.run(
        [sys.executable, "-I", "-B", "-c", script],
        input=json.dumps([sent, response]),
        text=True,
        capture_output=True,
        timeout=10,
    )
    assert completed.returncode == 0, completed.stderr
    assert "REORDERED_NATIVE_SOURCE_ACCEPTED" in completed.stdout
