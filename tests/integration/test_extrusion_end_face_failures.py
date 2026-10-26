"""Native end-face failures are narrow, explicit, and never automatic rebinding."""

import copy
import importlib
import math
import sys
import types
from dataclasses import replace
from pathlib import Path

import pytest

import mechanical_cad.kernel_ocp as native
from mechanical_cad.engine import regenerate
from mechanical_cad.errors import CADException
from mechanical_cad.kernel_ocp import KernelError, OCPKernel, _shape_bounds
from mechanical_cad.model import Document
from mechanical_cad.sidecar import process_request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests"))
from end_face_repair_cases import end_face_case, feature  # noqa: E402

PACKAGE = "mcad_staged_end_face_native"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
sys.modules[PACKAGE] = package


def replay(document, version=3, kernel=None):
    return regenerate(Document.from_dict(document), kernel or OCPKernel(), result_version=version)


def result_feature(result, identifier):
    return next(row for row in result.result["features"] if row["id"] == identifier)


def native_target():
    kernel = OCPKernel()
    target = kernel.extrude(kernel.circle(3), 10)
    kernel.topology(target, "stop", "extrude", {})
    return kernel, target, kernel.circle(1, z=20)


@pytest.mark.parametrize("version", [1, 2, 3])
def test_accepted_end_face_has_unchanged_exact_geometry_and_saved_intent(version):
    accepted, _ = end_face_case()
    saved = Document.from_dict(accepted).to_json()
    result = replay(accepted, version)
    assert result.ok, result.result
    for identifier, volume, lower, upper in (
        ("tool", 9.5 * math.pi, 10.5, 20),
        ("tool2", 9.75 * math.pi, 0, 9.75),
    ):
        item = result_feature(result, identifier)
        assert item["stats"]["valid"] and item["stats"]["solids"] == 1
        assert item["stats"]["volume"] == pytest.approx(volume)
        bounds = _shape_bounds(result.shapes[identifier])
        assert bounds[2] == pytest.approx(lower)
        assert bounds[5] == pytest.approx(upper)
        assert {row["id"] for row in item["topology"]} == {
            f"{identifier}/face/cap.start",
            f"{identifier}/face/cap.end",
            f"{identifier}/face/side.circle",
        }
        assert "length" not in item["resolved_params"]
    assert Document.from_dict(accepted).to_json() == saved
    assert Document.from_json(saved).to_json() == saved


@pytest.mark.parametrize("version", [1, 2, 3])
@pytest.mark.parametrize("failure", ["split", "missing"])
def test_actual_cut_edit_reports_both_end_face_failures_without_fallback(version, failure):
    accepted, proposed = end_face_case(failure=failure)
    original = copy.deepcopy(proposed)
    assert replay(accepted, version).ok
    result = replay(proposed, version)
    assert not result.ok
    cut = result_feature(result, "slotted")
    assert cut["status"] == "ok" and cut["stats"]["valid"]
    assert cut["stats"]["volume"] == pytest.approx(900 if failure == "split" else 800)
    cap = "block/face/cap.end"
    assert cap not in {face["id"] for face in cut["topology"]}
    descendants = [face for face in cut["topology"] if face["provenance"].get("source_id") == cap]
    if failure == "split":
        assert len(descendants) == 2
        assert all(face["provenance"]["semantic_status"] == "split" for face in descendants)
        assert all(face["id"].startswith("snapshot:") for face in descendants)
    else:
        assert not descendants
    for identifier in ("tool", "tool2"):
        item = result_feature(result, identifier)
        assert item["status"] == "failed"
        assert item["error"]["code"] == "invalid_extrusion_end_face"
        assert item["mesh"] is item["stats"] is None and item["topology"] == []
        assert identifier not in result.shapes
        assert feature(proposed, identifier)["inputs"]["target"] == "slotted"
        assert feature(proposed, identifier)["end_face"] == cap
    assert result_feature(result, "replacement")["status"] == "ok"
    assert result_feature(result, "downstream")["status"] == "blocked"
    assert proposed == original


@pytest.mark.parametrize("version", [2, 3])
@pytest.mark.parametrize("failure", ["split", "missing"])
def test_explicit_source_substitution_preserves_upstream_edit_and_each_parameter(version, failure):
    accepted, proposed = end_face_case(failure=failure)
    original = copy.deepcopy(proposed)
    partial = copy.deepcopy(proposed)
    feature(partial, "tool")["inputs"]["target"] = "replacement"
    result = replay(partial, version)
    assert not result.ok
    assert result_feature(result, "tool")["status"] == "ok"
    assert result_feature(result, "tool2")["error"]["code"] == "invalid_extrusion_end_face"
    assert result_feature(result, "downstream")["status"] == "blocked"

    corrected = copy.deepcopy(partial)
    feature(corrected, "tool2")["inputs"]["target"] = "replacement"
    saved = Document.from_dict(corrected).to_json()
    result = replay(Document.from_json(saved).to_dict(), version)
    assert result.ok, result.result
    for identifier, volume, lower, upper in (
        ("tool", 6.5 * math.pi, 13.5, 20),
        ("tool2", 12.75 * math.pi, 0, 12.75),
    ):
        old = feature(proposed, identifier)
        new = feature(corrected, identifier)
        assert new["params"] == old["params"] == feature(accepted, identifier)["params"]
        assert new["end_face"] == old["end_face"] == "block/face/cap.end"
        assert new["inputs"]["profile"] == old["inputs"]["profile"]
        assert result_feature(result, identifier)["stats"]["volume"] == pytest.approx(volume)
        bounds = _shape_bounds(result.shapes[identifier])
        assert bounds[2] == pytest.approx(lower)
        assert bounds[5] == pytest.approx(upper)
    assert corrected["parameters"] == accepted["parameters"]
    for row in proposed["features"]:
        if row["id"] not in {"tool", "tool2"}:
            assert feature(corrected, row["id"]) == row
    assert proposed == original
    assert not replay(proposed, version).ok


@pytest.mark.parametrize("version", [2, 3])
@pytest.mark.parametrize("phase", ["accepted", "failed", "corrected"])
def test_real_sidecar_end_face_results_pass_strict_current_transport(version, phase):
    accepted, proposed = end_face_case()
    document = accepted if phase == "accepted" else proposed
    if phase == "corrected":
        for identifier in ("tool", "tool2"):
            feature(document, identifier)["inputs"]["target"] = "replacement"
    request = {"protocol_version": 1, "result_version": version, "document": document}
    response = process_request(request)
    assert response["ok"] is (phase != "failed")
    bridge = importlib.import_module(
        PACKAGE + (".result_v3" if version == 3 else ".part_result_bridge")
    )
    assert bridge.validate_response(request, response) == response


@pytest.mark.parametrize(
    "failure", ["missing", "ambiguous", "split", "curved", "nonparallel", "behind"]
)
def test_only_recognized_target_gates_raise_typed_end_face_error(failure):
    kernel, target, profile = native_target()
    face_id, direction, offset = "stop/face/cap.end", -1, 0
    operation = kernel._operations[id(target)]
    cap = next(pair for pair in operation.faces if pair[1]["id"] == face_id)
    if failure == "missing":
        face_id = "stop/face/missing"
    elif failure == "ambiguous":
        operation.faces.append(cap)
    elif failure == "split":
        cap[1]["provenance"]["semantic_status"] = "split"
    elif failure == "curved":
        face_id = "stop/face/side.circle"
    elif failure == "nonparallel":
        target = kernel.extrude(kernel.rectangle(10, 10), 10)
        kernel.topology(target, "stop", "extrude", {})
        face_id = "stop/face/side.x_min"
    else:
        direction, offset = 1, 100
    with pytest.raises(CADException) as caught:
        kernel.extrude_to_face(profile, target, face_id, direction, offset)
    assert caught.value.code == "invalid_extrusion_end_face"
    assert isinstance(caught.value, KernelError)  # Historical direct-adapter callers.


@pytest.mark.parametrize(
    "direction,offset",
    [
        (True, 0),
        (0, 0),
        (2, 0),
        ("-1", 0),
        (-1, "invalid"),
        (-1, math.nan),
        (-1, math.inf),
        (-1, 1e6 + 1),
        (-1, -10),
        (-1, -11),
        (-1, 1e6),
    ],
)
def test_direction_and_offset_failures_are_not_end_face_repairs(direction, offset):
    kernel, target, profile = native_target()
    with pytest.raises(KernelError) as caught:
        kernel.extrude_to_face(profile, target, "stop/face/cap.end", direction, offset)
    assert not isinstance(caught.value, CADException)


@pytest.mark.parametrize("failure", ["invalid", "unknown", "normal", "open", "curved"])
def test_profile_failures_are_not_end_face_repairs(failure):
    kernel, target, profile = native_target()
    operation = kernel._operations[id(profile)]
    if failure == "invalid":
        profile = None
    elif failure == "unknown":
        del kernel._operations[id(profile)]
    elif failure == "normal":
        operation.normal = None
    elif failure == "open":
        profile = next(iter(operation.boundaries.values()))
        kernel._operations[id(profile)] = replace(operation, shape=profile)
    else:
        profile = next(
            face
            for face, row in kernel._operations[id(target)].faces
            if row["id"] == "stop/face/side.circle"
        )
        kernel._operations[id(profile)] = replace(operation, shape=profile)
    with pytest.raises(KernelError) as caught:
        kernel.extrude_to_face(profile, target, "stop/face/cap.end", -1)
    assert not isinstance(caught.value, CADException)


@pytest.mark.parametrize("version", [1, 2, 3])
@pytest.mark.parametrize("fault", ["surface", "extrude", "typed_kernel"])
def test_unexpected_native_exceptions_stay_kernel_errors(monkeypatch, version, fault):
    accepted, _ = end_face_case()

    def crash(*args, **kwargs):
        if fault == "typed_kernel":
            raise CADException("kernel_error", "Unexpected typed native failure")
        raise RuntimeError("Unexpected native failure")

    class FaultyKernel(OCPKernel):
        def extrude_to_face(self, *args, **kwargs):
            with monkeypatch.context() as context:
                if fault == "surface":
                    context.setattr(native, "BRepAdaptor_Surface", crash)
                else:
                    context.setattr(self, "extrude", crash)
                return super().extrude_to_face(*args, **kwargs)

    result = replay(accepted, version, FaultyKernel())
    assert not result.ok
    assert result_feature(result, "slotted")["status"] == "ok"
    for identifier in ("tool", "tool2"):
        item = result_feature(result, identifier)
        assert item["status"] == "failed"
        assert item["error"]["code"] == "kernel_error"
        assert "Unexpected" in item["error"]["message"]
    assert result_feature(result, "downstream")["status"] == "blocked"


@pytest.mark.parametrize("offset,code", [(-10, "kernel_error"), (1e6 + 1, "invalid_coordinate")])
def test_replay_preserves_offset_validation_error_codes(offset, code):
    accepted, _ = end_face_case(consumers=1)
    feature(accepted, "tool")["params"]["offset"] = offset
    result = replay(accepted)
    assert not result.ok
    assert result_feature(result, "tool")["error"]["code"] == code
