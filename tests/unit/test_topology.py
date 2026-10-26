"""Kernel-free safety contract tests; real B-rep coverage is cataloged separately."""

import ast
import json
from dataclasses import replace
from pathlib import Path

import pytest

from mechanical_cad.topology import TopologyCandidate, TopologyReference, resolve_reference


def face(identifier="snapshot:1", **changes):
    values = {
        "id": identifier,
        "feature_id": "feature-plate",
        "role": "cap.end",
        "kind": "face",
        "body_id": "body-plate",
        "signature": {"surface": "plane", "area": 200.0, "centroid": (0.0, 0.0, 5.0)},
        "provenance": {"semantic_status": "stable", "evolution": "primitive"},
    }
    values.update(changes)
    return TopologyCandidate(**values)


def reference(**changes):
    values = {
        "id": "reference-mounting-plane",
        "feature_id": "feature-plate",
        "role": "cap.end",
        "kind": "face",
        "body_id": "body-plate",
        "signature": {"surface": "plane", "area": 200.0, "centroid": (0.0, 0.0, 5.0)},
    }
    values.update(changes)
    return TopologyReference(**values)


def test_dimension_change_preserves_semantic_reference():
    """MCAD-TOPO-001: signature changes cannot override supported semantic identity."""
    changed = face(
        "snapshot:99", signature={"surface": "plane", "area": 400.0, "centroid": (0, 0, 15)}
    )
    result = resolve_reference(reference(), [changed])
    assert result.status == "resolved"
    assert result.candidate == changed
    assert result.inferred is False
    assert result.suggestions == ()


def test_enumeration_order_never_defines_identity():
    """MCAD-TOPO-002: stable reference survives snapshot-local ID/order changes."""
    target = face("face:902")
    other = face("face:1", role="cap.start")
    assert resolve_reference(reference(), [other, target]).candidate == target
    assert resolve_reference(reference(), [target, other]).candidate == target


def test_split_role_is_ambiguous_even_with_unequal_geometry():
    """MCAD-TOPO-003: never silently pick the largest or closest split descendant."""
    left = face("left", provenance={"semantic_status": "split"})
    right = face("right", signature={"area": 2.0}, provenance={"semantic_status": "split"})
    result = resolve_reference(reference(), [left, right])
    assert result.status == "ambiguous"
    assert result.candidate is None
    assert result.reason == "multiple_semantic_matches"
    assert {candidate.id for candidate in result.candidates} == {"left", "right"}


@pytest.mark.parametrize(
    "semantic_status", ["merged", "split", "generated", "unknown", "deleted", "stable-ish", None]
)
def test_untrusted_single_match_requires_repair(semantic_status):
    """MCAD-TOPO-004: one apparent match is not proof of supported identity."""
    provenance = {} if semantic_status is None else {"semantic_status": semantic_status}
    result = resolve_reference(reference(), [face(provenance=provenance)])
    assert result.status == "ambiguous"
    assert result.reason == "untrusted_semantic_provenance"
    assert result.candidate is None


def test_deleted_face_does_not_bind_identical_replacement():
    """MCAD-TOPO-005: identical geometry from another feature remains a suggestion."""
    replacement = face("replacement", feature_id="feature-new-plate")
    result = resolve_reference(reference(), [replacement])
    assert result.status == "missing"
    assert result.candidate is None
    assert len(result.suggestions) == 1
    assert result.suggestions[0].candidate == replacement
    assert result.suggestions[0].inferred is True


def test_symmetric_geometry_ties_remain_unresolved():
    """MCAD-TOPO-006: lexical ID order is display ordering, never a tie-breaker."""
    left = face(
        "left",
        role="side.left",
        signature={"surface": "plane", "area": 200, "centroid": (-5, 0, 5)},
    )
    right = face(
        "right",
        role="side.right",
        signature={"surface": "plane", "area": 200, "centroid": (5, 0, 5)},
    )
    result = resolve_reference(reference(), [right, left])
    assert result.status == "missing"
    assert result.candidate is None
    assert [item.candidate.id for item in result.suggestions] == ["left", "right"]
    assert all(item.tied_with_best for item in result.suggestions)
    assert result.suggestions[0].score == result.suggestions[1].score
    assert result.to_dict() == resolve_reference(reference(), [left, right]).to_dict()


def test_suppressed_or_rolled_back_feature_is_missing_then_restorable():
    """MCAD-HIST-001: resolver uses only the supplied current snapshot."""
    saved = reference()
    assert resolve_reference(saved, [face()]).resolved
    assert resolve_reference(saved, []).status == "missing"
    assert resolve_reference(saved, [face("rebuilt:1")]).resolved
    assert saved.id == "reference-mounting-plane"


def test_body_scope_prevents_cross_body_resolution_and_suggestions():
    """MCAD-TOPO-007: coincident bodies are distinct semantic scopes."""
    wrong_body = face("other-body", body_id="body-other")
    result = resolve_reference(reference(), [wrong_body])
    assert result.status == "missing"
    assert result.candidate is None
    assert result.suggestions == ()


def test_omitted_body_scope_cannot_hide_duplicate_roles():
    result = resolve_reference(
        reference(body_id=None), [face("a"), face("b", body_id="body-other")]
    )
    assert result.status == "ambiguous"
    assert result.candidate is None


def test_duplicate_stable_roles_are_ambiguous():
    result = resolve_reference(reference(), [face("one"), face("two")])
    assert result.status == "ambiguous"
    assert result.candidate is None


def test_entity_kind_is_part_of_identity():
    result = resolve_reference(reference(), [face(kind="edge")])
    assert result.status == "missing"
    assert result.suggestions == ()


def test_explicit_noncanonical_units_are_not_geometrically_compared():
    """MCAD-UNIT-001: input conversion must precede geometric comparison."""
    imperial = face(
        "inch-face", role="unknown", signature={"units": "in", "area": 200, "centroid": (0, 0, 5)}
    )
    assert resolve_reference(reference(), [imperial]).suggestions == ()
    # Semantic identity is independent of display units and geometry signatures.
    assert resolve_reference(reference(), [replace(imperial, role="cap.end")]).resolved


def test_nonfinite_or_malformed_signature_never_creates_resolution():
    bad = face(
        "bad",
        role="unknown",
        signature={"area": float("nan"), "centroid": [float("inf"), 0, 0], "normal": [0, 0]},
    )
    result = resolve_reference(reference(signature={"area": 20, "centroid": [0, 0, 0]}), [bad])
    assert result.status == "missing"
    assert result.suggestions == ()


def test_zero_normal_is_ignored_and_surface_mismatch_is_not_suggested():
    unknown = reference(signature={"normal": [0, 0, 0]})
    assert (
        resolve_reference(
            unknown, [face(role="unknown", signature={"normal": [0, 0, 1]})]
        ).suggestions
        == ()
    )
    assert (
        resolve_reference(
            reference(), [face(role="unknown", signature={"surface": "cylinder"})]
        ).suggestions
        == ()
    )


def test_dict_contract_round_trips_without_mutating_input():
    saved, current = reference().to_dict(), face().to_dict()
    before = json.dumps([saved, current], sort_keys=True)
    result = resolve_reference(saved, [current])
    assert result.resolved
    assert result.to_dict()["candidate"]["feature_id"] == "feature-plate"
    assert json.dumps([saved, current], sort_keys=True) == before


def test_duplicate_snapshot_ids_fail_loudly():
    with pytest.raises(ValueError, match="duplicate snapshot candidate id"):
        resolve_reference(reference(), [face(), face(role="cap.start")])


@pytest.mark.parametrize(
    "field,value", [("feature_id", ""), ("role", " "), ("kind", None), ("body_id", 1)]
)
def test_invalid_reference_contract_is_rejected(field, value):
    with pytest.raises(ValueError):
        resolve_reference(replace(reference(), **{field: value}), [face()])


def test_user_correction_requires_an_explicit_new_semantic_reference():
    """MCAD-INTENT-001: showing a guess and accepting a correction are separate."""
    replacement = face("new-cap", feature_id="feature-new-plate")
    original = reference()
    proposed = resolve_reference(original, [replacement])
    assert proposed.status == "missing"
    assert original.feature_id == "feature-plate"
    # An explicit UI confirmation would create this replacement selection in the
    # document and store old/new reference + user decision in its repair history.
    corrected = replace(original, feature_id="feature-new-plate")
    assert resolve_reference(corrected, [replacement]).resolved
    assert resolve_reference(original, [replacement]).status == "missing"


def test_implemented_catalog_test_links_exist():
    """Keep the catalog honest: planned coverage is distinct from executable tests."""
    root = Path(__file__).resolve().parents[2]
    catalog = json.loads((root / "docs/regressions/catalog.json").read_text())
    ids = [case["id"] for case in catalog["cases"]]
    assert len(ids) == len(set(ids))
    assert catalog["schema_version"] == 1
    for case in catalog["cases"]:
        assert case["category_path"] and case["acceptance"] and case["repair_policy"]
        for test in case["tests"]:
            assert test["status"] in {"implemented", "planned"}
            if test["status"] == "planned":
                continue
            path, separator, function = test["nodeid"].partition("::")
            source = root / path
            assert source.is_file(), f"{case['id']}: missing test file {source}"
            names = {
                node.name
                for node in ast.walk(ast.parse(source.read_text()))
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            if separator:
                assert function in names, f"{case['id']}: missing test function {function}"
