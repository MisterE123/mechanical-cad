"""Reusable box/sector project: canonical intent and one exact native journey."""

import copy
import math
from pathlib import Path

import pytest

from mechanical_cad.assembly_kinematics import evaluate
from mechanical_cad.assembly_model import AssemblyDocument, replace_source
from mechanical_cad.model import Document

EXAMPLE = Path(__file__).resolve().parents[2] / "examples/box_sector"


def project():
    return AssemblyDocument.from_json((EXAMPLE / "assembly.mcad-assembly.json").read_text())


def test_reusable_example_has_exact_sources_and_explicit_placement_intent():
    assembly = project()
    documents = {source.id: source.document for source in assembly.part_sources}
    for filename in ("base.mcad.json", "sector.mcad.json"):
        source = Document.from_json((EXAMPLE / filename).read_text())
        assert documents[source.id].to_json() == source.to_json()
        assert assembly.source_hashes[source.id] == source.content_hash
    sector = documents["box_sector_quadrant"]
    assert sector.parameters == {"height": 10, "radius": 5}
    sketch = sector.features[0].sketch
    assert sketch.schema_version == 3
    assert len(sketch.arcs) == 1 and len(sketch.lines) == 2
    assert {relation.kind for relation in sketch.constraints} == {
        "fixed",
        "horizontal",
        "vertical",
        "radius",
    }
    pose = evaluate(assembly)
    assert pose.status == "evaluated"
    assert pose.transforms["base"].xyz_mm == (0, 0, 0)
    assert pose.transforms["sector_a"].xyz_mm == (10, 10, 20)
    assert pose.transforms["sector_b"].xyz_mm == (25, 10, 20)
    assert assembly.active_verification_preset == "base_clearance"
    assert len(assembly.verification_presets[0].requirements) == 2
    assert all(row.minimum_mm == 2 for row in assembly.verification_presets[0].requirements)


@pytest.mark.kernel
def test_box_sector_radius_update_and_explicit_pose_checks_use_one_project():
    # Native imports are deliberately inside this test; the example-intent test
    # can run without constructing a kernel or calling a solver.
    from mechanical_cad.assembly_service import preflight_source_update, run_assembly_action

    original = project()
    before = original.to_json()
    first = run_assembly_action(original, "assembly_check", result_version=3)
    assert first["ok"] and first["report"]["passed"]
    parts = {row["id"]: row for row in first["result"]["parts"]}
    assert parts["box"]["geometry_check"]["brep"]["volume"] == pytest.approx(12000)
    assert parts["sector"]["geometry_check"]["brep"]["volume"] == pytest.approx(
        math.pi * 25 * 10 / 4
    )
    source = next(row.document for row in original.part_sources if row.id == "box_sector_quadrant")
    updated = source.to_dict()
    updated["parameters"]["radius"] = 7
    updated = Document.from_dict(updated)
    response = preflight_source_update(original, source.id, updated, result_version=3)
    assert response["ok"]
    assert set(response["update"]["affected_instances"]) == {"sector_a", "sector_b"}
    accepted = AssemblyDocument.from_dict(response["update"]["candidate"])
    assert accepted.parts[0].mate_frames == original.parts[0].mate_frames
    assert accepted.parts[1].mate_frames == original.parts[1].mate_frames
    assert accepted.instances == original.instances and accepted.joints == original.joints
    assert updated.features == source.features
    assert original.to_json() == before
    clear = run_assembly_action(accepted, "assembly_check", result_version=3)
    assert clear["ok"] and clear["report"]["passed"]
    parts = {row["id"]: row for row in clear["result"]["parts"]}
    assert parts["sector"]["geometry_check"]["brep"]["volume"] == pytest.approx(
        math.pi * 49 * 10 / 4
    )
    sampled = run_assembly_action(
        accepted,
        "assembly_sample",
        result_version=3,
        coordinates={"slide_a": 10, "slide_b": 10},
        samples={"joint_id": "slide_a", "values": [-5, 10]},
    )
    assert sampled["ok"] and sampled["report"]["known_interference"]
    assert not sampled["report"]["passed"]
    assert sampled["report"]["continuous_collision_guarantee"] is False
    assert [
        row["pose"]["effective_coordinates"]["slide_b"] for row in sampled["report"]["poses"]
    ] == [10, 10]
    failed_source = copy.deepcopy(updated.to_dict())
    failed_source["parameters"]["height"] = -1
    failed = replace_source(accepted, source.id, Document.from_dict(failed_source))
    failure = run_assembly_action(failed, result_version=3)
    assert not failure["ok"] and failure["error"]["code"] == "unsupported_profile_scale"
    assert failure["result"]["source_replays"] == []
    assert "native_runtime_versions" not in failure["report"]
    assert failure["result"]["parts"] == []
    assert accepted.source_hashes[source.id] == updated.content_hash
