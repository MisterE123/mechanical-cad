"""Pure lossless snapshot, exact-base and fail-closed persistence regressions."""

import copy
import importlib.util
import json
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def module(name):
    spec = importlib.util.spec_from_file_location(
        "mcad_pure_" + name, ROOT / "blender_addon/mechanical_cad_blender" / (name + ".py")
    )
    result = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = result
    spec.loader.exec_module(result)
    return result


drafts, store = module("sketch_draft"), module("draft_store")


def placed():
    draft = drafts.RectangleDraft(
        json.dumps(
            {
                "schema_version": 1,
                "id": "doc",
                "name": "Part",
                "units": "mm",
                "parameters": {},
                "features": [],
                "active_feature": None,
            }
        )
    )
    draft.first_point((5, 7))
    draft.second_point((45, 37))
    return draft


def roundtrip(draft):
    return store.restore(store.dumps(draft), draft.document_json, drafts.RectangleDraft)


@pytest.mark.parametrize(
    "width,height",
    [
        ("  nonsense + (  ", "30mm"),
        ("-5", "unknown_parameter"),
        ("60.123456789123456", "\t 30.123456789123456 \n"),
        ("", "  "),
        ("1e309", "NaN"),
        ("width × 2 🛠", "unterminated(\n"),
    ],
)
def test_raw_input_and_last_good_outline_are_exact(width, height):
    draft = placed()
    draft.set_dimensions(width, height)
    restored = roundtrip(draft)
    assert asdict(restored) == asdict(draft)
    assert restored.width_text == width and restored.height_text == height
    assert restored.points() == draft.points()
    assert restored.candidate() == draft.candidate()


@pytest.mark.parametrize("phase", ["FIRST_POINT", "SECOND_POINT", "DIMENSIONS"])
def test_all_placement_phases_resume(phase):
    draft = placed()
    if phase == "FIRST_POINT":
        draft = drafts.RectangleDraft(draft.document_json)
    elif phase == "SECOND_POINT":
        draft = drafts.RectangleDraft(draft.document_json)
        draft.first_point((-22.123456789, 4.5))
        draft.move((-5, 9))
    assert asdict(roundtrip(draft)) == asdict(draft)


def test_pending_dialog_raw_values_survive_without_applying_or_solving():
    draft = placed()
    draft.pending_dimensions = {"width": "  width + ( ", "height": "wrong", "fix_corner": False}
    restored = roundtrip(draft)
    assert restored.pending_dimensions == draft.pending_dimensions
    assert restored.candidate() == draft.candidate()
    assert restored.fix_corner is True


def test_released_and_refixed_seed_intent_survives_without_reinitialization():
    draft = placed()
    points = [
        {"id": f"p{i}", "u": x, "v": y}
        for i, (x, y) in enumerate([(5, 7), (65, 7), (65, 37), (5, 37)])
    ]
    draft.last_solved_points = copy.deepcopy(points)
    draft.width = 60
    draft.set_dimensions("60", "30", fix_corner=False)
    restored = roundtrip(draft)
    assert restored.seed_override == points == restored.last_solved_points
    assert restored.candidate() == draft.candidate()
    restored.anchor = (8.123456789, 11.234567891)
    restored.set_dimensions("60", "30", fix_corner=True)
    refixed = roundtrip(restored)
    assert refixed.fixed_target == restored.fixed_target
    assert refixed.seed_override == points
    assert refixed.candidate() == restored.candidate()


def test_edit_identity_original_double_and_downstream_output_survive():
    document = placed().candidate()
    document["parameters"]["sketch_1_height"] = 30.123456789123456
    document["features"].append({"id": "pad", "kind": "extrude", "inputs": {"profile": "sketch_1"}})
    document["active_feature"] = "pad"
    draft = drafts.RectangleDraft(json.dumps(document), feature_id="sketch_1", is_edit=True)
    draft.set_dimensions("  60.123456789123456  ", draft.height_text, fix_corner=False)
    restored = roundtrip(draft)
    assert asdict(restored) == asdict(draft)
    assert restored.candidate() == draft.candidate()
    assert restored.candidate()["parameters"]["sketch_1_height"] == 30.123456789123456
    assert restored.candidate()["active_feature"] == "pad"


def test_restoration_drops_all_solver_currentness_without_dropping_seeds():
    draft = placed()
    draft.last_solved_points = draft.candidate()["features"][0]["sketch"]["points"]
    draft.solver_report = {"status": "okay", "remaining_dof": 0}
    draft.validated_json = json.dumps(draft.candidate())
    restored = roundtrip(draft)
    assert restored.solver_report is None and restored.validated_json == ""
    assert restored.last_solved_points == draft.last_solved_points
    assert draft.solver_report is not None and draft.validated_json


@pytest.mark.parametrize("change", ["name", "whitespace", "feature", "parameter"])
def test_external_revision_change_rejected_without_mutating_snapshot(change):
    draft = placed()
    snapshot = store.dumps(draft)
    current = json.loads(draft.document_json)
    if change == "name":
        current["name"] = "Edited elsewhere"
    elif change == "feature":
        current["features"].append({"id": "other"})
    elif change == "parameter":
        current["parameters"]["other"] = 12
    serialized = json.dumps(current) + (" " if change == "whitespace" else "")
    with pytest.raises(store.SnapshotError, match="different committed document revision"):
        store.restore(snapshot, serialized, drafts.RectangleDraft)
    assert snapshot == store.dumps(draft)
    assert roundtrip(draft).document_json == draft.document_json


@pytest.mark.parametrize(
    "mutation",
    [
        lambda s: s.update(unknown="retain me"),
        lambda s: s.update(schema_version=2),
        lambda s: s.update(schema_version=True),
        lambda s: s.update(base_sha256="wrong"),
        lambda s: s["draft"].update(unknown="retain me"),
        lambda s: s["draft"].pop("seed_override"),
        lambda s: s["draft"].update(phase="UNKNOWN"),
        lambda s: s["draft"].update(width=True),
        lambda s: s["draft"].update(width=float("nan")),
        lambda s: s["draft"].update(anchor=[1e7, 0]),
        lambda s: s["draft"].update(seed_override=[{"id": "p0", "u": 1, "v": 2}]),
        lambda s: s["draft"].update(solver_report={"remaining_dof": 0}),
        lambda s: s["draft"].update(validated_json="old proof"),
        lambda s: s["draft"].update(pending_dimensions={"width": 4}),
        lambda s: s["draft"].update(fixed_target=None),
    ],
)
def test_unknown_corrupt_or_unverified_claims_fail_closed(mutation):
    draft = placed()
    payload = json.loads(store.dumps(draft))
    mutation(payload)
    serialized = json.dumps(payload)
    with pytest.raises(store.SnapshotError):
        store.restore(serialized, draft.document_json, drafts.RectangleDraft)
    assert serialized == json.dumps(payload)


def test_duplicate_fields_are_rejected():
    with pytest.raises(store.SnapshotError, match="Duplicate"):
        store.loads('{"schema_version": 1, "schema_version": 2}')


def test_oversized_snapshot_is_rejected():
    with pytest.raises(store.SnapshotError, match="bounded"):
        store.loads(" " * (store.MAX_SNAPSHOT_BYTES + 1))


def test_parameter_identity_tampering_does_not_rebase():
    draft = placed()
    payload = json.loads(store.dumps(draft))
    payload["draft"]["width_key"] = "another_width"
    with pytest.raises(store.SnapshotError, match="identity"):
        store.restore(json.dumps(payload), draft.document_json, drafts.RectangleDraft)
