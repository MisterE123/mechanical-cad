"""Pinned slvs rank-defect regressions across native solve and geometry consumers.

No workaround guesses freedom or removes authored relations. These tests exercise
source/state and subprocess boundaries; they do not claim Blender GUI coverage.
"""

import copy
import importlib
import json
import math
import os
import subprocess
import sys
import types
from dataclasses import replace
from pathlib import Path

import pytest

pytest.importorskip("OCP")

from mechanical_cad.actions import run_geometry_action
from mechanical_cad.assembly_model import AssemblyDocument, replace_source
from mechanical_cad.assembly_service import preflight_source_update, run_assembly_action
from mechanical_cad.engine import regenerate
from mechanical_cad.kernel_ocp import OCPKernel
from mechanical_cad.model import Document, Feature, load_document
from mechanical_cad.sidecar import process_request
from mechanical_cad.sketch_model import Constraint, Line, Point, Sketch, SketchDefinition
from mechanical_cad.sketch_solver import Status, solve

slvs = pytest.importorskip("slvs")

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "mcad_dof_cycle_native_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
sys.modules[PACKAGE] = package
part_bridge = importlib.import_module(PACKAGE + ".part_result_bridge")
assembly_bridge = importlib.import_module(PACKAGE + ".assembly_bridge")
solve_bridge = importlib.import_module(PACKAGE + ".sketch_action_bridge")
bridge = importlib.import_module(PACKAGE + ".bridge")
CODE = "solver_dof_indeterminate"


LINUX_LEGACY_PROFILE = pytest.mark.skipif(
    sys.platform != "linux", reason="Linux legacy bridge replay contract"
)


def cycle_document(*, sketch_version=2):
    points = (Point("a", 0, 0), Point("b", 2, 1), Point("c", 4, 0))
    pairs = (("a", "b"), ("b", "c"), ("c", "a"))
    sketch = SketchDefinition(
        "cyclic",
        points,
        tuple(Line(f"l{i}", *pair) for i, pair in enumerate(pairs)),
        tuple(Constraint(f"c{i}", "coincident", pair) for i, pair in enumerate(pairs)),
        schema_version=sketch_version,
    )
    return Document(
        "user_part",
        "Cyclic Part",
        {},
        (
            Feature("profile", "sketch_constrained", "Sketch", sketch=sketch),
            Feature("pad", "extrude", "Pad", {"length": 10}, {"profile": "profile"}),
        ),
        "pad",
        schema_version=2,
    )


def assert_failed_replay(result, *, version=2):
    assert result["status"] == "failed"
    profile, pad = result["features"][:2]
    assert profile["status"] == "failed" and profile["error"]["code"] == CODE
    assert profile.get("sketch") is None  # No native report or invented rank exists.
    assert pad["status"] == "blocked" and pad["error"]["code"] == "upstream_failed"
    for item in (profile, pad):
        assert item["mesh"] is None and item["stats"] is None and item["topology"] == []
        if version == 2:
            assert item["output"] is None


@pytest.mark.parametrize(
    "kind,incorrect_dof", [("coincident", 0), ("horizontal", 3), ("vertical", 3)]
)
def test_pinned_native_success_is_not_sufficient_evidence_for_coordinate_cycle(kind, incorrect_dof):
    # Characterize the precise slvs 3.2 defect independently of our adapter.
    # Coincidence leaves two translations; H/V leaves four scalar freedoms.
    slvs.clear_sketch()
    try:
        wp = slvs.add_base_2d(1)
        points = [slvs.add_point_2d(2, u, v, wp) for u, v in ((0.0, 0.0), (2.0, 1.0), (4.0, 0.0))]
        lines = [slvs.add_line_2d(2, points[i], points[(i + 1) % 3], wp) for i in range(3)]
        for i in range(3):
            if kind == "coincident":
                slvs.coincident(2, points[i], points[(i + 1) % 3], wp)
            else:
                getattr(slvs, kind)(2, lines[i], wp)
        info, failed = slvs.solve_sketch(2, True)
        assert info == {"result": 0, "dof": incorrect_dof, "nbad": 0} and failed == []
    finally:
        slvs.clear_sketch()


def forest(kind):
    points = tuple(Point(name, i * 2, i % 2) for i, name in enumerate("abcd"))
    pairs = (("a", "b"), ("b", "c"), ("c", "d"))
    lines = tuple(Line(f"l{i}", *pair) for i, pair in enumerate(pairs))
    if kind == "mixed":
        constraints = (
            Constraint("co", "coincident", ("a", "b")),
            Constraint("h", "horizontal", ("l1",)),
            Constraint("v", "vertical", ("l2",)),
        )
    elif kind == "independent_axes":
        constraints = (Constraint("h", "horizontal", ("l0",)), Constraint("v", "vertical", ("l0",)))
    else:
        constraints = tuple(
            Constraint(f"c{i}", kind, pair if kind == "coincident" else (f"l{i}",))
            for i, pair in enumerate(pairs)
        )
    return Sketch("forest", points, lines, constraints, schema_version=2)


@pytest.mark.parametrize(
    "kind,dof",
    [
        ("coincident", 2),
        ("horizontal", 5),
        ("vertical", 5),
        ("mixed", 4),
        ("independent_axes", 6),
    ],
)
@pytest.mark.parametrize("anchored", [False, True])
@pytest.mark.parametrize("duplicated", [False, True])
def test_coordinate_forests_anchors_exact_duplicates_and_separate_axes_remain_supported(
    kind, dof, anchored, duplicated
):
    source = forest(kind)
    if anchored:
        source = replace(
            source,
            constraints=source.constraints
            + (Constraint("anchor", "fixed", ("a",), target=(5, 6)),),
        )
    if duplicated:
        source = replace(
            source,
            constraints=source.constraints
            + tuple(
                replace(c, id="z_copy_" + c.id, refs=tuple(reversed(c.refs)))
                for c in source.constraints
            ),
        )
    before = source.to_json()
    result = solve(source)
    assert result.success and result.remaining_dof == dof - (2 if anchored else 0)
    assert result.status == (Status.REDUNDANT_OKAY if duplicated else Status.OKAY)
    assert result.max_residual <= 1e-7 and result.failed_constraints == ()
    assert result.sketch.constraints == source.constraints and source.to_json() == before
    assert result.redundant_constraints == tuple(
        sorted(c.id for c in source.constraints if c.id.startswith("z_copy_"))
    )
    reordered = replace(
        source,
        points=tuple(reversed(source.points)),
        lines=tuple(reversed(source.lines)),
        constraints=tuple(reversed(source.constraints)),
    )
    assert solve(reordered).sketch.to_json() == result.sketch.to_json()


@pytest.mark.parametrize(
    "name,volume",
    [
        ("viewport_rectangle", 12_000),
        ("constrained_plate", 12_000),
        ("circle_sketch_part", math.pi * 15**2 * 5),
    ],
)
def test_ordinary_rectangle_and_circle_native_results_remain_unchanged(name, volume):
    source = load_document(ROOT / "examples" / f"{name}.mcad.json")
    before = source.to_json()
    result = regenerate(source, OCPKernel(), result_version=2)
    assert result.ok
    assert result.result["features"][0]["sketch"]["remaining_dof"] == 0
    assert result.result["features"][-1]["stats"]["volume"] == pytest.approx(volume)
    assert source.to_json() == before


@pytest.mark.parametrize("version", [1, 2])
def test_full_replay_blocks_dependent_solid_with_no_native_or_current_geometry(version):
    source = cycle_document(sketch_version=version)
    before = source.to_json()
    replay = regenerate(source, OCPKernel(), result_version=version)
    assert not replay.ok and replay.shapes == {} and replay.outputs == {}
    assert_failed_replay(replay.result, version=version)
    assert source.to_json() == before


@pytest.mark.parametrize("action", ["check_geometry", "export_step", "export_stl"])
def test_geometry_actions_keep_previous_export_and_never_accept_cyclic_replay(tmp_path, action):
    source = cycle_document()
    before = source.to_json()
    destination = tmp_path / "existing.cad"
    old_bytes = b"unchanged accepted export\x00\xff"
    destination.write_bytes(old_bytes)
    response = run_geometry_action(
        source,
        action,
        result_version=2,
        destination=None if action == "check_geometry" else destination,
    )
    assert not response["ok"] and response["error"]["code"] == "regeneration_failed"
    assert response["geometry_check"] is None and response["export"] is None
    assert_failed_replay(response["result"])
    assert destination.read_bytes() == old_bytes and list(tmp_path.iterdir()) == [destination]
    assert source.to_json() == before


@pytest.mark.parametrize(
    "action", ["solve_sketch", "replay", "check_geometry", "export_step", "export_stl"]
)
def test_actual_sidecar_error_crosses_strict_bridge_without_source_or_export_mutation(
    tmp_path, action
):
    source = cycle_document()
    destination = tmp_path / "existing.cad"
    destination.write_bytes(b"last valid export")
    req = {
        "protocol_version": 1,
        "action": action,
        "result_version": 2,
        "document": source.to_dict(),
    }
    if action == "solve_sketch":
        req["feature_id"] = "profile"
    elif action.startswith("export_"):
        req["destination"] = str(destination)
    before = copy.deepcopy(req)
    process = subprocess.run(
        [sys.executable, "-m", "mechanical_cad.sidecar"],
        input=json.dumps(req),
        text=True,
        capture_output=True,
        timeout=30,
        env=dict(os.environ, PYTHONPATH=str(ROOT / "src")),
        cwd=ROOT,
    )
    assert process.returncode == 1, process.stderr
    response = json.loads(process.stdout)
    if action == "solve_sketch":
        validated = solve_bridge.validate_solve_response(response, req)
        assert response["result"] is None and response["error"]["code"] == CODE
    else:
        validated = part_bridge.validate_response(req, response)
        assert_failed_replay(response["result"])
        if action != "replay":
            assert response["geometry_check"] is None and response["export"] is None
    assert validated == response and not validated["ok"]
    assert req == before and source.to_dict() == req["document"]
    assert destination.read_bytes() == b"last valid export"


@pytest.mark.parametrize("version", [1, 2])
@LINUX_LEGACY_PROFILE
def test_real_blender_bridge_replay_retains_failure_in_both_negotiated_versions(version):
    source = cycle_document(sketch_version=version)
    before = source.to_json()
    result = bridge.replay(
        source.to_dict(),
        result_version=version,
        project_root=str(ROOT),
        python_executable=sys.executable,
    )
    assert_failed_replay(result, version=version)
    assert source.to_json() == before


@pytest.mark.parametrize(
    "field,value",
    [
        ("output", {"kind": "solid", "display": "mesh"}),
        ("mesh", {"vertices": [], "triangles": [], "triangle_face_ids": []}),
        ("stats", {"valid": True, "volume": 1, "area": 1, "faces": 0, "solids": 1}),
        ("topology", [{"id": "old_face"}]),
        ("remaining_dof", 0),
    ],
)
def test_failed_replay_cannot_publish_geometry_or_extend_protocol(field, value):
    req = {"protocol_version": 1, "result_version": 2, "document": cycle_document().to_dict()}
    response = process_request(req)
    assert_failed_replay(response["result"])
    response["result"]["features"][0][field] = value
    with pytest.raises(ValueError):
        part_bridge.validate_response(req, response)


def test_independent_success_does_not_allow_export_after_cycle_failure(tmp_path):
    source = cycle_document()
    source = replace(
        source,
        features=source.features
        + (
            Feature("safe_profile", "sketch_rectangle", "Independent", {"width": 5, "height": 6}),
            Feature(
                "safe_pad", "extrude", "Independent pad", {"length": 7}, {"profile": "safe_profile"}
            ),
        ),
        active_feature="safe_pad",
    )
    replay = regenerate(source, OCPKernel(), result_version=2)
    assert not replay.ok and set(replay.shapes) == {"safe_profile", "safe_pad"}
    assert "profile" not in replay.outputs and "pad" not in replay.outputs
    assert replay.result["features"][-1]["stats"]["volume"] == pytest.approx(210)
    destination = tmp_path / "keep.step"
    destination.write_bytes(b"old export")
    response = run_geometry_action(source, "export_step", destination=destination, result_version=2)
    assert not response["ok"] and response["export"] is None
    assert destination.read_bytes() == b"old export"


@pytest.mark.parametrize("action", ["assembly_replay", "assembly_check"])
def test_assembly_source_cycle_retains_diagnostic_without_part_geometry_or_pose_evidence(action):
    original = AssemblyDocument.from_json(
        (ROOT / "examples/reused_blocks.mcad-assembly.json").read_text()
    )
    candidate = replace_source(original, "user_part", cycle_document())
    before = candidate.to_json()
    req = assembly_bridge.build_request(candidate.to_dict(), action, result_version=2)
    response = process_request(req)
    validated = assembly_bridge.validate_response(req, response)
    assert not validated["ok"] and response["error"]["code"] == "source_replay_failed"
    assert response["result"]["parts"] == []
    assert response["result"]["instances"] == [item.to_dict() for item in candidate.instances]
    assert all(set(item) == {"id", "part_id", "name"} for item in response["result"]["instances"])
    assert response["report"]["poses"] == [] and not response["report"]["complete"]
    assert not response["report"]["passed"]
    rows = response["result"]["source_replays"][0]["features"]
    assert rows[0]["error"]["code"] == CODE and rows[0]["output"] is None
    assert rows[1]["status"] == "blocked" and rows[1]["output"] is None
    assert all(row["stats"] is None for row in rows)
    assert candidate.to_json() == before
    direct = run_assembly_action(candidate, action, result_version=2)
    assert direct["error"]["code"] == "source_replay_failed" and direct["result"]["parts"] == []


def test_failed_assembly_source_update_keeps_accepted_snapshot_and_offers_no_candidate():
    original = AssemblyDocument.from_json(
        (ROOT / "examples/reused_blocks.mcad-assembly.json").read_text()
    )
    before = original.to_json()
    replacement = cycle_document()
    replacement_before = replacement.to_json()
    response = preflight_source_update(original, "user_part", replacement, result_version=2)
    assert not response["ok"] and response["error"]["code"] == "source_replay_failed"
    assert response["update"]["candidate"] is None and response["result"]["parts"] == []
    assert response["result"]["source_replays"][0]["features"][0]["error"]["code"] == CODE
    assert original.to_json() == before and replacement.to_json() == replacement_before
