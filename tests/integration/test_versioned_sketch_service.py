"""Real solve-only / typed replay negotiation and no-solid boundaries."""

import copy
import json
import math
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

pytest.importorskip("slvs")
pytest.importorskip("OCP")

from mechanical_cad.actions import run_geometry_action
from mechanical_cad.engine import regenerate
from mechanical_cad.errors import CADException
from mechanical_cad.kernel_ocp import OCPKernel
from mechanical_cad.model import Document, Feature
from mechanical_cad.outputs import OpenProfile, SketchOutput, SolidOutput
from mechanical_cad.part_snapshot import input_fingerprint
from mechanical_cad.sidecar import process_request
from mechanical_cad.sketch_model import Circle, Constraint, Line, Point, SketchDefinition
from mechanical_cad.sketch_service import profile_check

ROOT = Path(__file__).resolve().parents[2]


def document(kind="circle", *, consumed=False):
    if kind == "circle":
        sketch = SketchDefinition(
            "shape",
            (Point("center", 3, 4),),
            (),
            (Constraint("size", "radius", ("circle",), "r + allowance"),),
            circles=(Circle("circle", "center", 5),),
            schema_version=2,
        )
    else:
        points = (Point("a", 0, 0), Point("b", 10, 0), Point("c", 10, 10))
        lines = (Line("first", "a", "b"), Line("second", "b", "c"))
        if kind == "closed":
            lines += (Line("third", "c", "a"),)
        sketch = SketchDefinition("shape", points, lines, (), schema_version=2)
    features = (Feature("profile", "sketch_constrained", "Sketch", sketch=sketch),)
    if consumed:
        features += (Feature("pad", "extrude", "Pad", {"length": 10}, {"profile": "profile"}),)
    return Document.from_dict(
        {
            "schema_version": 2,
            "id": "doc",
            "name": "Typed sketch",
            "units": "mm",
            "parameters": {"r": 7, "allowance": 0.5},
            "features": [feature.to_dict() for feature in features],
            "active_feature": "pad" if consumed else "profile",
        }
    )


def request(doc=None, **changes):
    return {
        "protocol_version": 1,
        "action": "solve_sketch",
        "result_version": 2,
        "document": (doc or document()).to_dict(),
        "feature_id": "profile",
        **changes,
    }


def wire(value=None, *, raw=None):
    process = subprocess.run(
        [sys.executable, "-m", "mechanical_cad.sidecar"],
        input=json.dumps(value) if raw is None else raw,
        text=True,
        capture_output=True,
        timeout=30,
        env=dict(os.environ, PYTHONPATH=str(ROOT / "src")),
    )
    return process, json.loads(process.stdout)


def test_solve_only_circle_has_true_dof_resolved_radius_and_unchanged_candidate():
    candidate = document()
    before = candidate.to_json()
    req = request(candidate)
    raw = copy.deepcopy(req)
    response = process_request(req)
    assert response["ok"] and response["result_version"] == 2
    assert response["input_fingerprint"] == input_fingerprint(req)
    result = response["result"]
    assert result["document_hash"] == candidate.content_hash
    assert result["document_id"] == "doc" and result["feature_id"] == "profile"
    assert result["profile_check"] == {"ready": True, "error": None}
    report = result["sketch"]
    assert report["remaining_dof"] == 2
    assert report["dimensions"] == {"size": 7.5}
    assert report["solved"]["circles"] == [{"id": "circle", "center": "center", "radius": 7.5}]
    assert candidate.to_json() == before and req == raw
    assert report["solved"]["constraints"][0]["value"] == 7.5
    assert candidate.features[0].sketch.constraints[0].value == "r + allowance"


def test_solve_only_does_not_import_kernel_or_replay_invalid_downstream():
    req = request(document(consumed=True))
    req["document"]["features"][-1]["params"]["length"] = -1
    script = """
import json,sys
from mechanical_cad.sidecar import process_request
response=process_request(json.loads(sys.stdin.read()))
assert response['ok']
assert not any(name == 'OCP' or name.startswith('OCP.') for name in sys.modules)
assert 'mechanical_cad.kernel_ocp' not in sys.modules
print(json.dumps(response))
"""
    process = subprocess.run(
        [sys.executable, "-c", script],
        input=json.dumps(req),
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert process.returncode == 0, process.stderr
    assert json.loads(process.stdout)["ok"]


def test_open_solver_success_is_separate_from_profile_readiness_and_replay():
    candidate = document("open")
    response = process_request(request(candidate))
    assert response["ok"] and response["error"] is None
    assert response["result"]["sketch"]["remaining_dof"] == 6
    assert response["result"]["profile_check"]["error"]["code"] == "open_profile"
    replay = regenerate(candidate, OCPKernel(), result_version=2)
    assert replay.ok and replay.shapes == {}
    output = replay.outputs["profile"]
    assert isinstance(output, SketchOutput) and isinstance(output.profile, OpenProfile)
    item = replay.result["features"][0]
    assert item["status"] == "ok" and item["mesh"] is None and item["stats"] is None
    assert item["topology"] == [] and item["output"]["profile"]["state"] == "unavailable"
    assert replay.result["result_version"] == 2


def test_open_consumed_sketch_blocks_extrusion_without_losing_valid_sketch():
    replay = regenerate(document("open", consumed=True), OCPKernel(), result_version=2)
    sketch, pad = replay.result["features"]
    assert not replay.ok and sketch["status"] == "ok"
    assert pad["status"] == "blocked" and pad["error"]["code"] == "profile_unavailable"
    assert "profile" in pad["error"]["message"]
    assert pad["output"] is None and pad["mesh"] is None
    assert set(replay.outputs) == {"profile"} and not replay.shapes


@pytest.mark.parametrize("action", ["check_geometry", "export_step", "export_stl"])
def test_active_open_sketch_is_not_a_solid_and_preserves_destination(tmp_path, action):
    destination = tmp_path / "previous.file"
    destination.write_bytes(b"keep")
    outcome = run_geometry_action(
        document("open"),
        action,
        result_version=2,
        destination=None if action == "check_geometry" else destination,
    )
    assert not outcome["ok"] and outcome["error"]["code"] == "not_a_solid"
    assert outcome["result"]["status"] == "ok" and outcome["result_version"] == 2
    assert outcome["export"] is None and outcome["geometry_check"] is None
    assert destination.read_bytes() == b"keep" and list(tmp_path.iterdir()) == [destination]


def test_circle_edit_replays_exact_solid_and_exports_with_requested_result(tmp_path):
    candidate = document(consumed=True)
    before = candidate.to_json()
    replay = regenerate(candidate, OCPKernel(), result_version=2)
    assert replay.ok and isinstance(replay.outputs["pad"], SolidOutput)
    assert replay.result["features"][-1]["stats"]["volume"] == pytest.approx(math.pi * 7.5**2 * 10)
    edited = candidate.with_parameter("r", 9)
    outcome = process_request(
        {
            "protocol_version": 1,
            "result_version": 2,
            "action": "export_step",
            "document": edited.to_dict(),
            "destination": str(tmp_path / "circle.step"),
        }
    )
    assert outcome["ok"] and outcome["result_version"] == outcome["result"]["result_version"] == 2
    assert outcome["result"]["features"][-1]["stats"]["volume"] == pytest.approx(
        math.pi * 9.5**2 * 10
    )
    assert candidate.to_json() == before


def test_unrelated_solid_can_export_beside_independent_open_sketch(tmp_path):
    candidate = document("open").to_dict()
    candidate["features"].extend(
        [
            {"id": "disk", "kind": "sketch_circle", "params": {"radius": 2}},
            {
                "id": "body",
                "kind": "extrude",
                "params": {"length": 3},
                "inputs": {"profile": "disk"},
            },
        ]
    )
    candidate["active_feature"] = "body"
    outcome = run_geometry_action(
        Document.from_dict(candidate),
        "export_step",
        result_version=2,
        destination=tmp_path / "body.step",
    )
    assert outcome["ok"] and outcome["result"]["status"] == "ok"


@pytest.mark.parametrize("version", [None, False, True, 0, 4, "2", [], {}])
def test_unknown_result_version_fails_before_native_execution(version):
    req = {"protocol_version": 1, "document": document().to_dict(), "result_version": version}
    with pytest.raises(CADException) as caught:
        process_request(req)
    assert caught.value.code == "unsupported_result_version"


def test_explicit_three_replays_the_same_existing_typed_document():
    candidate = document()
    before = candidate.to_json()
    req = {"protocol_version": 1, "document": candidate.to_dict(), "result_version": 3}
    original = copy.deepcopy(req)
    response = process_request(req)
    assert response["ok"] and response["result_version"] == 3
    assert response["input_fingerprint"] == input_fingerprint(req)
    assert response["result"]["result_version"] == 3
    feature = response["result"]["features"][0]
    assert feature["status"] == "ok"
    assert feature["sketch"]["status"] == "okay"
    assert feature["sketch"]["solved"]["schema_version"] == 2
    assert feature["sketch"]["dimensions"] == {"size": 7.5}
    assert feature["output"]["profile"] == {"state": "available", "region_kind": "circle"}
    assert feature["mesh"]["vertices"] and feature["mesh"]["triangles"]
    assert candidate.to_json() == before and req == original


def test_new_document_cannot_silently_downgrade_to_legacy_result():
    with pytest.raises(CADException, match="Upgrade") as caught:
        process_request({"protocol_version": 1, "document": document().to_dict()})
    assert caught.value.code == "unsupported_result_version"


@pytest.mark.parametrize("extra", [{"options": {}}, {"destination": "bad"}, {"command": "run"}])
def test_solve_only_rejects_export_and_geometry_options(extra):
    result = process_request(request(**extra))
    assert not result["ok"] and result["result"] is None
    assert result["error"]["code"] == "invalid_request"
    assert result["input_fingerprint"] == input_fingerprint(request(**extra))


@pytest.mark.parametrize(
    "feature_id,code",
    [
        (None, "invalid_feature"),
        ([], "invalid_feature"),
        ("missing", "missing_feature"),
        ("pad", "invalid_feature"),
    ],
)
def test_solve_only_bad_selection_is_bound_to_exact_request(feature_id, code):
    req = request(document(consumed=True), feature_id=feature_id)
    response = process_request(req)
    assert response["error"]["code"] == code and response["result"] is None
    assert response["input_fingerprint"] == input_fingerprint(req)


def test_failed_solve_has_no_geometry_dof_or_profile_result():
    candidate = document()
    sketch = candidate.features[0].sketch
    sketch = replace(
        sketch,
        constraints=sketch.constraints + (Constraint("conflict", "radius", ("circle",), 20),),
    )
    candidate = replace(candidate, features=(replace(candidate.features[0], sketch=sketch),))
    response = process_request(request(candidate))
    assert not response["ok"] and response["error"]["code"] == "sketch_solve_failed"
    report = response["result"]["sketch"]
    assert report["solved"] is None and report["remaining_dof"] is None
    assert response["result"]["profile_check"] is None


def test_successful_solver_with_crossed_region_is_not_mislabeled_conflict():
    sketch = SketchDefinition(
        "crossed",
        (Point("a", 0, 0), Point("b", 10, 10), Point("c", 0, 10), Point("d", 10, 0)),
        (Line("ab", "a", "b"), Line("bc", "b", "c"), Line("cd", "c", "d"), Line("da", "d", "a")),
        (),
        schema_version=2,
    )
    candidate = replace(
        document(), features=(Feature("profile", "sketch_constrained", "Crossed", sketch=sketch),)
    )
    response = process_request(request(candidate))
    assert response["ok"] and response["result"]["sketch"]["status"] == "okay"
    assert not response["result"]["profile_check"]["ready"]
    replay = regenerate(candidate, OCPKernel(), result_version=2)
    item = replay.result["features"][0]
    assert item["status"] == "failed" and item["sketch"]["status"] == "okay"
    assert item["error"]["code"] in {"degenerate_profile", "self_intersecting_profile"}
    assert item["output"] is None and not replay.outputs and not replay.shapes


def test_profile_check_does_not_disguise_unexpected_errors(monkeypatch):
    import mechanical_cad.sketch_service as service

    def unexpected(_):
        raise CADException("internal_bug", "Unexpected")

    monkeypatch.setattr(service, "classify_profile", unexpected)
    with pytest.raises(CADException, match="Unexpected"):
        profile_check(None)


def test_wire_solve_success_and_long_numeric_token_rejection():
    process, response = wire(request())
    assert process.returncode == 0 and response["ok"]
    text = json.dumps(request())
    long_token = "7." + "0" * 130
    text = text.replace('"r": 7', '"r": ' + long_token)
    process, response = wire(raw=text)
    assert process.returncode == 1 and response["error"]["code"] == "resource_limit"


def test_direct_cyclic_and_nonfinite_requests_are_rejected_before_solver():
    req = request()
    req["document"]["cycle"] = req
    with pytest.raises(CADException) as caught:
        process_request(req)
    assert caught.value.code == "invalid_json"
    req = request()
    req["document"]["parameters"]["r"] = float("nan")
    with pytest.raises(CADException) as caught:
        process_request(req)
    assert caught.value.code == "invalid_json"


def test_checked_in_v2_examples_roundtrip_and_cli_requires_explicit_opt_in(tmp_path):
    from mechanical_cad.model import load_document, save_document

    for name in ("circle_sketch_part", "open_line_sketch"):
        path = ROOT / "examples" / (name + ".mcad.json")
        candidate = load_document(path)
        saved = tmp_path / path.name
        save_document(candidate, saved)
        assert load_document(saved).to_json() == candidate.to_json()
        assert load_document(saved).content_hash == candidate.content_hash
        process = subprocess.run(
            [
                sys.executable,
                "-m",
                "mechanical_cad.cli",
                "replay",
                str(saved),
                "--result-version",
                "2",
            ],
            text=True,
            capture_output=True,
            timeout=30,
        )
        assert process.returncode == 0, process.stderr
        result = json.loads(process.stdout)
        assert result["result_version"] == 2 and result["status"] == "ok"
        if name == "circle_sketch_part":
            assert result["features"][-1]["stats"]["volume"] == pytest.approx(math.pi * 15**2 * 5)
        else:
            assert result["features"][0]["output"]["profile"]["state"] == "unavailable"
        process = subprocess.run(
            [sys.executable, "-m", "mechanical_cad.cli", "replay", str(saved)],
            text=True,
            capture_output=True,
            timeout=30,
        )
        assert process.returncode == 1 and "unsupported_result_version" in process.stderr


def test_unpersistable_identity_is_rejected_before_native_solve_or_geometry(monkeypatch):
    import mechanical_cad.sketch_service as service

    candidate = document()
    calls = []

    def reject_hash(_):
        raise CADException("document_too_large", "Canonical snapshot exceeds budget")

    def forbidden_solve(*args):
        calls.append("solver")
        raise AssertionError("Native solver must not run")

    class ForbiddenKernel:
        def __getattr__(self, name):
            calls.append(name)
            raise AssertionError("Native geometry must not run")

    monkeypatch.setattr(Document, "content_hash", property(reject_hash))
    monkeypatch.setattr(service, "evaluate_sketch", forbidden_solve)
    with pytest.raises(CADException) as caught:
        service.solve_sketch(candidate, "profile")
    assert caught.value.code == "document_too_large"
    with pytest.raises(CADException) as caught:
        regenerate(candidate, ForbiddenKernel(), result_version=2)
    assert caught.value.code == "document_too_large" and calls == []


def test_solve_only_enforces_standalone_budget_for_legacy_embedded_sketch(monkeypatch):
    import mechanical_cad.sketch_service as service

    first, second = "a" * 128, "b" * 128
    oversized = SketchDefinition(
        "legacy",
        (Point(first, 0, 0), Point(second, 1, 0)),
        (),
        tuple(
            Constraint(f"c{i:0127d}", "distance", (first, second), "1" + " " * 255)
            for i in range(512)
        ),
    )
    candidate = Document(
        "legacy_doc",
        "Legacy oversized",
        {},
        (Feature("profile", "sketch_constrained", "Legacy", sketch=oversized),),
        "profile",
        schema_version=2,
    )
    # Preserve the old structural acceptance and bytes; harden only new solve action.
    assert Document.from_dict(candidate.to_dict()).content_hash == candidate.content_hash
    calls = []
    monkeypatch.setattr(service, "evaluate_sketch", lambda *args: calls.append(args))
    response = process_request(request(candidate))
    assert response["ok"] is False and response["result"] is None
    assert response["error"]["code"] == "sketch_too_large" and not calls


def test_solve_only_rejects_legacy_aggregate_canonical_expansion_before_native(monkeypatch):
    import mechanical_cad.sketch_service as service

    sketch = SketchDefinition(
        "legacy",
        (Point("a", 0, 0), Point("b", 1, 0)),
        (),
        tuple(Constraint(f"c{i}", "distance", ("a", "b"), 1) for i in range(512)),
    )
    assert len(sketch.to_json().encode()) < 256 * 1024
    candidate = Document(
        "legacy_doc",
        "Legacy aggregate",
        {},
        tuple(Feature(f"f{i}", "sketch_constrained", f"f{i}", sketch=sketch) for i in range(20)),
        "f0",
        schema_version=2,
    )
    assert len(json.dumps(candidate.to_dict(), separators=(",", ":"))) < 2 * 1024 * 1024
    # Frozen legacy constructor/serializer behavior is intentionally retained.
    assert len(candidate.to_json().encode()) > 2 * 1024 * 1024
    calls = []
    monkeypatch.setattr(service, "evaluate_sketch", lambda *args: calls.append(args))
    response = process_request(request(candidate, feature_id="f0"))
    assert not response["ok"] and response["result"] is None
    assert response["error"]["code"] == "document_too_large" and not calls
