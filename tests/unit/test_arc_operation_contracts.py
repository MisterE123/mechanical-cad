"""Current source/action admission, not solved readiness; executes no native CAD.

Connected feature contracts (f8639a0) deliberately replaced single-sector-only
structural admission. Strict schemas, owner roles and output kinds still apply.
"""

import copy
import importlib
import json
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "mcad_arc_operation_policy_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
sys.modules[PACKAGE] = package
policy = importlib.import_module(PACKAGE + ".operation_contracts")
FIXTURES = ROOT / "tests/fixtures/arc_authoring_evidence"


def sector():
    return json.loads((FIXTURES / "radius_edit_5_0_replay.operation.json").read_text())["document"]


def legacy():
    return json.loads((ROOT / "examples/viewport_rectangle.mcad.json").read_text())


def arc_empty():
    document = sector()
    sketch = document["features"][0]["sketch"]
    sketch["arcs"] = []
    sketch["constraints"] = []
    return document


@pytest.mark.parametrize("factory,version", [(legacy, 2), (sector, 3), (arc_empty, 3)])
@pytest.mark.parametrize("action", ["solve_sketch", "replay"])
def test_complete_candidate_selects_exact_schema_not_nonempty_arcs(factory, version, action):
    document = factory()
    before = json.dumps(document)
    assert policy.result_version_for(document, action=action, owner_role="general") == version
    assert json.dumps(document) == before
    detached = policy.validate_authoring_candidate(document)
    assert detached == document and detached is not document
    detached["name"] = "detached"
    assert json.dumps(document) == before


@pytest.mark.parametrize(
    "action", ["canonical_snapshot", "check_geometry", "export_step", "export_stl"]
)
@pytest.mark.parametrize("factory", [sector, arc_empty])
def test_schema3_geometry_and_capture_require_part_owned_solid_graph(factory, action):
    document = factory()
    before = copy.deepcopy(document)
    # Arc-empty/open drafts can be structurally admitted without claiming a
    # successful solve, closed profile, solid, or export. The backend proves those.
    assert policy.result_version_for(document, action=action) == (
        None if action == "canonical_snapshot" else 3
    )
    for role in ("general", "rectangle"):
        with pytest.raises(ValueError):
            policy.result_version_for(document, action=action, owner_role=role)
    assert document == before
    assert policy.result_version_for(legacy(), action=action) == (
        None if action == "canonical_snapshot" else 2
    )


@pytest.mark.parametrize("factory", [sector, arc_empty])
def test_rectangle_owner_never_selects_result3(factory):
    with pytest.raises(ValueError, match="Rectangle"):
        policy.result_version_for(factory(), owner_role="rectangle")
    assert policy.result_version_for(legacy(), owner_role="rectangle") == 2


def test_inactive_schema3_and_undo_back_to_legacy_are_whole_candidate_decisions():
    document = legacy()
    old = copy.deepcopy(document)
    feature = arc_empty()["features"][0]
    feature["id"] = "inactive_arc_empty"
    document["features"].append(feature)
    assert document["active_feature"] != feature["id"]
    assert policy.result_version_for(document) == 3
    document["features"].pop()
    assert document == old and policy.result_version_for(document) == 2


@pytest.mark.parametrize("version", [None, False, True, 3.0, "3", 0, 4])
def test_nonexact_or_unknown_embedded_schema_rejects_before_selection(version):
    document = arc_empty()
    document["features"][0]["sketch"]["schema_version"] = version
    with pytest.raises(ValueError):
        policy.result_version_for(document)


@pytest.mark.parametrize("line_count", [0, 1, 2])
def test_incomplete_arc_drafts_are_admitted_without_projecting_raw_points(line_count):
    document = sector()
    sketch = document["features"][0]["sketch"]
    sketch["lines"] = sketch["lines"][:line_count]
    sketch["constraints"] = []
    sketch["points"][1]["v"] = 6.25
    before = json.dumps(document)
    assert policy.validate_authoring_sketch(sketch) == sketch
    assert policy.validate_authoring_candidate(document) == document
    assert json.dumps(document) == before


@pytest.mark.parametrize("kind", ["second_arc", "full_circle", "third_line"])
def test_general_analytic_draft_admission_is_detached_and_not_profile_readiness(kind):
    document = sector()
    sketch = document["features"][0]["sketch"]
    if kind == "second_arc":
        sketch["arcs"].append({**sketch["arcs"][0], "id": "second_arc"})
    elif kind == "full_circle":
        sketch["circles"].append({"id": "full_circle", "center": "center", "radius": 5})
    else:
        sketch["lines"].append({"id": "chord", "start": "start", "end": "end"})
    before = json.dumps(document)
    for validator, value in (
        (policy.validate_authoring_sketch, sketch),
        (policy.validate_authoring_candidate, document),
    ):
        accepted = validator(value)
        assert accepted == value and accepted is not value
        accepted["name"] = "detached mutation"
        assert json.dumps(document) == before


@pytest.mark.parametrize("kind", ["second_extrude", "unrelated_profile", "cut", "wrong_source"])
def test_arc_admission_checks_entire_part_graph(kind):
    document = sector()
    if kind == "wrong_source":
        document["features"][1]["inputs"]["profile"] = "missing"
    elif kind == "second_extrude":
        document["features"].append({**copy.deepcopy(document["features"][1]), "id": "second"})
    elif kind == "unrelated_profile":
        document["features"].append(
            {"id": "extra", "kind": "sketch_rectangle", "params": {"width": 2, "height": 3}}
        )
    else:
        document["features"].append(
            {"id": "cut", "kind": "cut", "inputs": {"base": "pad", "tool": "pad"}}
        )
    before = json.dumps(document)
    if kind == "wrong_source":
        with pytest.raises(ValueError):
            policy.validate_authoring_candidate(document)
    else:
        # Additional profiles/solids and Cut nodes are now supported graph types.
        # This does not promise that self-cut produces a valid solid at replay.
        accepted = policy.validate_authoring_candidate(document)
        assert accepted == document and accepted is not document
        accepted["features"][0]["name"] = "detached mutation"
    assert json.dumps(document) == before


@pytest.mark.parametrize("action", ["assembly_replay", "assembly_check", "assembly_sample"])
def test_assembly_checks_all_source_schemas_including_unused_arc_empty(action):
    assembly = json.loads((ROOT / "examples/reused_blocks.mcad-assembly.json").read_text())
    assert policy.result_version_for_assembly(assembly, action=action) == 2
    for document in (sector(), arc_empty()):
        candidate = copy.deepcopy(assembly)
        candidate["part_sources"].append(
            {"source_document_id": document["id"], "source_digest": "0" * 64, "document": document}
        )
        before = json.dumps(candidate)
        assert policy.result_version_for_assembly(candidate, action=action) == 3
        assert json.dumps(candidate) == before
        # Unused sources are still validated in full, not ignored for selection.
        candidate["part_sources"][-1]["document"]["features"][1]["inputs"]["profile"] = "missing"
        invalid = copy.deepcopy(candidate)
        with pytest.raises(ValueError):
            policy.result_version_for_assembly(candidate, action=action)
        assert candidate == invalid


@pytest.mark.parametrize(
    "action",
    [
        "assembly_replay",
        "assembly_check",
        "assembly_sample",
    ],
)
def test_assembly3_dispatch_requires_its_strict_assembly_envelope(action):
    operation = {"protocol_version": 1, "action": action, "result_version": 3, "document": sector()}
    with pytest.raises(RuntimeError, match="Assembly result version 3"):
        policy.validate_response(operation, {})


@pytest.mark.parametrize("version", [None, False, True, 2.0, 3.0, "3", 0, 1, 4, [2, 3]])
def test_dispatch_rejects_unknown_or_coerced_result_versions(version):
    operation = {"protocol_version": 1, "result_version": version, "document": legacy()}
    with pytest.raises(ValueError, match="explicit typed"):
        policy.validate_response(operation, {})


def test_snapshot_dispatch_has_no_numeric_result_version():
    operation = {"protocol_version": 1, "action": "canonical_snapshot", "document": legacy()}
    for version in (None, 2, 3):
        with pytest.raises(ValueError, match="Snapshots have no"):
            policy.validate_response({**operation, "result_version": version}, {})


@pytest.mark.parametrize("action", ["check_geometry", "export_step", "export_stl"])
def test_geometry3_response_uses_its_exact_validator_without_fallback(monkeypatch, action):
    from test_geometry_result_v3 import pair

    request, response = pair(action)
    monkeypatch.setattr(
        policy.result_v3, "validate_response", lambda *_: pytest.fail("replay route")
    )
    assert policy.validate_response(request, response) == response
    with pytest.raises(ValueError):
        policy.validate_response(request, {**response, "result_version": 2})


@pytest.mark.parametrize("action", ["check_geometry", "export_step", "export_stl"])
@pytest.mark.parametrize(
    "variant",
    [
        "profile",
        "selected",
        "origin",
        "near_origin",
        "quaternion",
        "near_quaternion",
        "alias",
        "inactive",
        "second_extrude",
    ],
)
def test_geometry_selection_distinguishes_solid_graph_admission_from_profile_readiness(action, variant):
    document = sector()
    sketch = document["features"][0]["sketch"]
    if variant == "profile":
        document["features"].pop()
        document["active_feature"] = document["features"][0]["id"]
    elif variant == "selected":
        document["active_feature"] = document["features"][0]["id"]
    elif variant in {"origin", "near_origin"}:
        sketch["plane"]["origin"] = [1 if variant == "origin" else 1e-300, 0, 0]
    elif variant in {"quaternion", "near_quaternion"}:
        sketch["plane"]["quaternion"] = (
            [-1, 0, 0, 0] if variant == "quaternion" else [1, 0, 0, 1e-15]
        )
    elif variant == "alias":
        sketch["points"].append({"id": "alias", "u": 0, "v": 0})
        sketch["lines"][0]["start"] = "alias"
    elif variant == "inactive":
        extra = arc_empty()["features"][0]
        extra["id"] = "inactive_schema3"
        document["features"].append(extra)
    else:
        document["features"].append({**copy.deepcopy(document["features"][1]), "id": "second"})
    before = copy.deepcopy(document)
    if variant in {"profile", "selected"}:
        with pytest.raises(ValueError, match="selected solid"):
            policy.result_version_for(document, action=action)
    else:
        # Transformed planes, shared-coordinate distinct IDs, inactive sketches,
        # and connected feature histories are legal source graphs. Result and
        # geometry validators remain responsible for actual solved output.
        assert policy.result_version_for(document, action=action) == 3
        with pytest.raises(ValueError):
            policy.result_version_for(document, action=action, owner_role="general")
    assert document == before


def test_geometry_source_selection_preserves_unsolved_seeds_and_nonzero_freedom():
    document = sector()
    sketch = document["features"][0]["sketch"]
    sketch["constraints"] = []
    sketch["points"][1]["u"] = 7.25
    before = copy.deepcopy(document)
    assert policy.result_version_for(document, action="check_geometry") == 3
    assert document == before


@pytest.mark.parametrize("mutation", ["duplicate_arc_id", "missing_endpoint", "unknown_arc_field"])
def test_general_analytic_draft_rejects_malformed_entities_without_mutation(mutation):
    document = sector()
    sketch = document["features"][0]["sketch"]
    if mutation == "duplicate_arc_id":
        sketch["arcs"].append(copy.deepcopy(sketch["arcs"][0]))
    elif mutation == "missing_endpoint":
        sketch["arcs"][0]["end"] = "missing"
    else:
        sketch["arcs"][0]["unrecognized"] = True
    before = copy.deepcopy(document)
    for validator, value in (
        (policy.validate_authoring_sketch, sketch),
        (policy.validate_authoring_candidate, document),
    ):
        with pytest.raises(ValueError):
            validator(value)
        assert document == before


@pytest.mark.parametrize("mutation", ["duplicate_feature", "feature_cycle", "unsupported_kind"])
def test_general_connected_graph_rejects_invalid_structure_atomically(mutation):
    document = sector()
    if mutation == "duplicate_feature":
        document["features"].append(copy.deepcopy(document["features"][-1]))
    elif mutation == "feature_cycle":
        document["features"][-1]["inputs"]["profile"] = document["features"][-1]["id"]
    else:
        document["features"][-1]["kind"] = "unrecognized_solid"
    before = copy.deepcopy(document)
    for action in ("replay", "canonical_snapshot", "check_geometry", "export_step", "export_stl"):
        with pytest.raises(ValueError):
            policy.result_version_for(document, action=action)
        assert document == before
