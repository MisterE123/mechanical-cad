"""Everyday solid defaults remain explicit, formula-preserving and mesh-independent."""

import importlib
import sys
import types
from pathlib import Path

import pytest

package = types.ModuleType("solid_dialog_tests")
package.__path__ = [
    str(Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender")
]
sys.modules[package.__name__] = package
values = importlib.import_module(package.__name__ + ".solid_dialog_values")


def document():
    return {
        "features": [
            {"id": "profile_a", "kind": "sketch_rectangle"},
            {"id": "base_a", "kind": "extrude"},
            {"id": "base_b", "kind": "extrude"},
            {"id": "face_profile", "kind": "sketch_face_circle", "inputs": {"support": "base_a"}},
            {"id": "latest_profile", "kind": "sketch_circle"},
        ],
        "active_feature": "base_b",
    }


def test_selected_history_profile_beats_most_recent_profile():
    assert values.solid_dialog_defaults(document(), "profile_a") == {
        "profile": "profile_a",
        "base": "base_b",
    }


def test_face_sketch_uses_canonical_support_not_unrelated_active_solid():
    assert values.solid_dialog_defaults(document(), "face_profile") == {
        "profile": "face_profile",
        "base": "base_a",
    }


def test_selected_solid_beats_active_output():
    assert values.solid_dialog_defaults(document(), "base_a")["base"] == "base_a"


def test_missing_history_selection_and_empty_document_are_safe():
    assert values.selected_history_id(types.SimpleNamespace()) is None
    assert values.selected_history_id(types.SimpleNamespace(features=[], feature_index=0)) is None
    assert values.solid_dialog_defaults({"features": []}) == {"profile": None, "base": None}


@pytest.mark.parametrize(
    "direction, expected",
    [
        ("NORMAL", "  height + gap "),
        ("REVERSE", "-(  height + gap )"),
        ("SIGNED", "  height + gap "),
    ],
)
def test_depth_conversion_does_not_evaluate_round_or_drop_formula(direction, expected):
    assert values.extrusion_depth("  height + gap ", direction) == expected


@pytest.mark.parametrize("depth", ["-2", "0", "nan", "inf", "-inf", ""])
def test_directional_depth_rejects_invalid_literals(depth):
    with pytest.raises(ValueError):
        values.extrusion_depth(depth, "REVERSE")


def test_advanced_signed_formula_is_unchanged():
    assert values.extrusion_depth("-(wall + gap)", "SIGNED") == "-(wall + gap)"


def attached_document():
    return {
        "features": [
            {
                "id": "p",
                "kind": "sketch_constrained",
                "support_face": "top",
                "inputs": {"support": "base"},
                "sketch": {"plane": {"origin": [0, 0, 0], "quaternion": [1, 0, 0, 0]}},
            }
        ]
    }


def test_standard_attached_profile_proves_outward_intent():
    source = attached_document()
    assert values.outward_support_profile(source, "p", "base")
    assert not values.outward_support_profile(source, "p", "other")
    source["features"][0]["sketch"]["plane"]["quaternion"] = [-1, 0, 0, 0]
    assert values.outward_support_profile(source, "p", "base")


@pytest.mark.parametrize(
    "plane",
    [
        {"origin": [0, 0, 1], "quaternion": [1, 0, 0, 0]},
        {"origin": [0, 0, 0], "quaternion": [0, 1, 0, 0]},
        {"origin": [0, 0, 0], "quaternion": [0.707, 0.707, 0, 0]},
        {"origin": [0, 0, "offset"], "quaternion": [1, 0, 0, 0]},
    ],
)
def test_offset_flipped_tilted_or_formula_planes_do_not_imply_inward(plane):
    source = attached_document()
    source["features"][0]["sketch"]["plane"] = plane
    assert not values.outward_support_profile(source, "p", "base")


def test_free_profile_does_not_imply_inward_and_primitive_requires_zero_offset():
    source = attached_document()
    source["features"][0].pop("support_face")
    assert not values.outward_support_profile(source, "p", "base")
    source["features"][0].update(kind="sketch_face_circle", support_face="top", params={"z": "0"})
    assert values.outward_support_profile(source, "p", "base")
    source["features"][0]["params"]["z"] = "offset"
    assert not values.outward_support_profile(source, "p", "base")


def test_picked_faces_require_current_distinct_stable_identities():
    source = {"features": [{"id": "base", "kind": "extrude"}]}
    result = {
        "features": [
            {
                "id": "base",
                "status": "ok",
                "topology": [
                    {"id": key, "kind": "face", "provenance": {"semantic_status": "stable"}}
                    for key in ("top", "side")
                ],
            }
        ]
    }
    assert values.picked_blend_faces(source, result, "base", "top", "side") == (
        "base",
        "top",
        "side",
    )
    for a, b in (("top", "top"), ("top", "missing")):
        with pytest.raises(ValueError):
            values.picked_blend_faces(source, result, "base", a, b)
    with pytest.raises(ValueError):
        values.picked_blend_faces(source, None, "base", "top", "side")
    result["features"][0]["topology"][1]["provenance"]["semantic_status"] = "ambiguous"
    with pytest.raises(ValueError):
        values.picked_blend_faces(source, result, "base", "top", "side")


def test_picked_shell_requires_unique_current_stable_planar_face():
    doc = {"features": [{"id": "box", "kind": "extrude"}]}
    face = {
        "id": "box/face/cap.end",
        "kind": "face",
        "provenance": {"semantic_status": "stable"},
        "signature": {"surface": "plane"},
    }
    row = {"id": "box", "status": "ok", "topology": [face]}
    result = {"features": [row]}
    assert values.picked_shell_face(doc, result, "box", face["id"]) == ("box", face["id"])
    for invalid in (
        None,
        {"features": [{**row, "status": "failed"}]},
        {"features": [{**row, "topology": [face, face]}]},
        {"features": [{**row, "topology": [{**face, "signature": {"surface": "cylinder"}}]}]},
        {"features": [{**row, "topology": [{**face, "provenance": {"semantic_status": "split"}}]}]},
    ):
        with pytest.raises(ValueError):
            values.picked_shell_face(doc, invalid, "box", face["id"])


def test_consent_resume_retains_only_bounded_authored_strings():
    from types import SimpleNamespace

    fields = {key: "" for key in values.CONSENT_RESUME_FIELDS}
    fields.update(feature_id="cut", original_json="{}", tool="tool", linked_depth_scope="PARAMETER", linked_end_condition="BLIND", linked_direction="1", depth_parameter_value="12")
    operator = SimpleNamespace(**fields, linked_tool_id="tool", allow_shared_extrusion=True)
    retained = values.consent_resume_values(operator)
    assert retained == fields and "allow_shared_extrusion" not in retained
    operator.depth_parameter_value = "changed"
    assert retained["depth_parameter_value"] == "12"
    for update in ({"tool": "rebound"}, {"depth_parameter_value": "x" * 4097}, {"linked_depth_scope": "unknown"}, {"allow_shared_extrusion": "True"}):
        with pytest.raises(ValueError):
            values.validate_consent_resume({**retained, **update}, "{}", "cut", "tool")
    with pytest.raises(ValueError):
        values.validate_consent_resume(retained, "new document", "cut", "tool")


@pytest.mark.parametrize("kind", ["sketch_circle", "sketch_face_circle"])
def test_circle_expression_return_copies_only_supported_bounded_strings(kind):
    fields = {key: "" for key in values.circle_expression_fields(kind)}
    fields.update(feature_id="circle", original_json="{}", radius="missing_radius",
                  radius_edit_scope="PARAMETER", radius_parameter_value="width/2")
    operator = types.SimpleNamespace(
        **fields, kind=kind, radius_parameter_name="r", allow_shared_extrusion=True,
    )
    retained = values.circle_expression_resume_values(operator)
    assert retained == fields and "allow_shared_extrusion" not in retained
    operator.radius = "changed"
    assert retained["radius"] == "missing_radius"
    for update in (
        {"feature_id": "different"}, {"original_json": "new"}, {"radius": "x" * 4097},
        {"radius": 3}, {"radius_edit_scope": "OTHER"}, {"allow_shared_extrusion": "True"},
        {"radius_parameter_name": "rebound"},
    ):
        with pytest.raises(ValueError):
            values.validate_circle_expression_resume(
                {**retained, **update}, "{}", "circle", kind, "r",
            )
    with pytest.raises(ValueError):
        values.validate_circle_expression_resume(retained, "{}", "circle", kind, "")
    with pytest.raises(ValueError):
        values.validate_circle_expression_resume(retained, "{}", "circle", "extrude", "r")
