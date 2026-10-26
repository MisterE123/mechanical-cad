"""Saved logical-plane intent is bounded, immutable and native-free."""

import copy
from pathlib import Path

import pytest

from mechanical_cad.errors import CADException
from mechanical_cad.model import Feature
from mechanical_cad.support_intent import validate_intent

INTENT = {
    "version": 1,
    "policy": "preserve_plane",
    "signature": {"surface": "plane", "area": 400, "centroid": [10, 10, 10], "normal": [0, 0, 1]},
}


@pytest.mark.parametrize(
    "mutation",
    [
        lambda v: v.__setitem__("version", True),
        lambda v: v.__setitem__("version", 2),
        lambda v: v.__setitem__("policy", "closest_face"),
        lambda v: v.__setitem__("selected_face_index", 3),
        lambda v: v["signature"].__setitem__("area", float("nan")),
        lambda v: v["signature"].__setitem__("area", 10**500),
        lambda v: v["signature"].__setitem__("normal", [0, 0, 2]),
        lambda v: v["signature"].__setitem__("centroid", [0, 0, float("inf")]),
    ],
)
def test_invalid_intent_rejected(mutation):
    intent = copy.deepcopy(INTENT)
    mutation(intent)
    with pytest.raises(ValueError):
        validate_intent(intent)


def test_intent_not_permitted_on_unrelated_feature():
    with pytest.raises(CADException, match="attached constrained"):
        Feature.from_dict(
            {
                "id": "x",
                "kind": "sketch_rectangle",
                "params": {"width": 2, "height": 2},
                "support_intent": INTENT,
            }
        )


def test_native_free_policy_is_identical_in_blender():
    root = Path(__file__).resolve().parents[2]
    assert (root / "src/mechanical_cad/support_intent.py").read_text() == (
        root / "blender_addon/mechanical_cad_blender/support_intent.py"
    ).read_text()


def test_source_baseline_is_validated_not_treated_as_untrusted_extra_metadata():
    intent = copy.deepcopy(INTENT)
    intent["source_signature"] = copy.deepcopy(INTENT["signature"])
    validate_intent(intent)
    intent["source_signature"]["normal"] = [0, 0, 0]
    with pytest.raises(ValueError, match="unit length"):
        validate_intent(intent)


@pytest.mark.parametrize(
    "orientation",
    [
        {"policy": "material_spin", "tangent": [1, 0, 0]},
        {"policy": "minimal_twist", "tangent": [0, 0, 0]},
        {"policy": "minimal_twist", "tangent": [0, 0, 1]},
        {"policy": "minimal_twist", "tangent": [True, 0, 0]},
        {"policy": "minimal_twist", "tangent": [float("nan"), 0, 0]},
        {"policy": "minimal_twist", "tangent": [1, 0, 0], "roll_guess": 20},
    ],
)
def test_invalid_or_unsupported_orientation_intent_is_rejected(orientation):
    intent = copy.deepcopy(INTENT)
    intent["orientation"] = orientation
    with pytest.raises(ValueError):
        validate_intent(intent)


@pytest.mark.parametrize("source", [True, "snapshot:cut:face:0", "", "missing space", "a" * 129])
def test_source_feature_is_only_an_authored_identifier(source):
    intent = copy.deepcopy(INTENT)
    intent.update(source_feature=source, source_signature=copy.deepcopy(INTENT["signature"]))
    with pytest.raises(ValueError):
        validate_intent(intent)


def test_source_feature_requires_its_explicit_saved_frame_and_full_replay():
    from mechanical_cad.support_intent import resolve_support_signature

    intent = copy.deepcopy(INTENT)
    intent["source_feature"] = "block"
    with pytest.raises(ValueError):
        validate_intent(intent)
    intent["source_signature"] = copy.deepcopy(INTENT["signature"])
    validate_intent(intent)
    with pytest.raises(ValueError, match="complete current replay"):
        resolve_support_signature("block/face/cap.end", intent, [])


def test_cut_chain_rule_is_identical_and_native_free_in_blender():
    root = Path(__file__).resolve().parents[2]
    assert (root / "src/mechanical_cad/cut_support_ancestry.py").read_text() == (
        root / "blender_addon/mechanical_cad_blender/cut_support_ancestry.py"
    ).read_text()
