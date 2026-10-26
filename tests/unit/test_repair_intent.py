"""Intent-only codec and scope rejection; no Blender/native evidence needed."""

import copy
import hashlib
import importlib
import json
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests"))
from staged_edit_cases import feature, multiple_projection_case  # noqa: E402

package = types.ModuleType("repair_intent_tests")
package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
sys.modules[package.__name__] = package
codec = importlib.import_module(package.__name__ + ".repair_intent")


@pytest.fixture
def intent():
    base, proposed = multiple_projection_case()
    partial = copy.deepcopy(proposed)
    feature(partial, "target")["projections"][0]["source"] = "replacement_ring"
    base_json = json.dumps(base)
    proposal = types.SimpleNamespace(
        base_json=base_json,
        base_hash=hashlib.sha256(base_json.encode()).hexdigest(),
        binding={"owner_id": "owner", "scale": 0.001},
        feature_id="source",
        candidate_json=json.dumps(partial),
        repairs=((json.dumps(proposed), "IGNORED_EVIDENCE"),),
        annotation_before=None,
        annotation_after=None,
    )
    return json.loads(codec.encode(proposal))


def parse(value):
    return codec.decode(json.dumps(value))


def test_exact_base_history_and_no_native_authority(intent):
    decoded = parse(intent)
    assert decoded == intent
    assert len(decoded["states"]) == 2
    assert "IGNORED_EVIDENCE" not in json.dumps(decoded)
    assert set(decoded) == codec._FIELDS
    assert "token" not in decoded and "failed_json" not in decoded


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", True),
        ("schema_version", 2),
        ("kind", "repair_v2"),
        ("owner_id", ""),
        ("owner_id", "\ud800"),
        ("scale", True),
        ("scale", 0),
        ("scale", float("inf")),
        ("feature_id", "missing"),
        ("base_hash", "0" * 64),
        ("states", []),
        ("native_token", "not_authority"),
        ("annotation_before", "{}"),
    ],
)
def test_strict_envelope_refuses_fields_and_values(intent, field, value):
    intent[field] = value
    with pytest.raises((ValueError, UnicodeError)):
        parse(intent)


def test_count_byte_depth_duplicate_and_nonfinite_limits(intent):
    intent["states"] *= 17
    with pytest.raises(ValueError, match="32"):
        parse(intent)
    for raw in (
        '{"kind":1,"kind":2}',
        "[" * 34 + "]" * 34,
        '{"v":NaN}',
        " " * (codec.MAX_BYTES + 1),
    ):
        with pytest.raises(ValueError):
            codec.decode(raw)
    with pytest.raises(ValueError):
        codec.document(" " * (codec.MAX_DOCUMENT_BYTES + 1))


@pytest.mark.parametrize(
    "change", ["unrelated", "reorder", "kind", "envelope", "surrogate", "unknown"]
)
def test_original_proposal_is_one_exact_existing_feature(intent, change):
    proposed = json.loads(intent["states"][0])
    if change == "unrelated":
        feature(proposed, "solid")["params"]["length"] = 8
    elif change == "reorder":
        proposed["features"][1:3] = reversed(proposed["features"][1:3])
    elif change == "kind":
        feature(proposed, "source")["kind"] = "sketch_circle"
    elif change == "envelope":
        proposed["name"] = "Different Part"
    elif change == "surrogate":
        feature(proposed, "source")["label"] = "\ud800"
    else:
        feature(proposed, "source")["native_evidence"] = "forged"
    intent["states"] = [json.dumps(proposed)]
    with pytest.raises((ValueError, UnicodeError)):
        parse(intent)


@pytest.mark.parametrize(
    "change", ["source", "parameters", "solid", "entity", "formula", "two_bindings"]
)
def test_each_history_transition_has_narrow_repair_scope(intent, change):
    partial = json.loads(intent["states"][1])
    target = feature(partial, "target")
    if change == "source":
        feature(partial, "source")["label"] = "Not repair"
    elif change == "parameters":
        partial["parameters"]["r"] = 99
    elif change == "solid":
        feature(partial, "solid")["params"]["length"] = 6
    elif change == "entity":
        target["sketch"]["circles"][-1]["radius"] = 7
    elif change == "formula":
        target["sketch"]["constraints"][-1]["kind"] = "diameter"
    else:
        feature(partial, "target_two")["projections"][0]["source"] = "replacement_ring"
    intent["states"][1] = json.dumps(partial)
    with pytest.raises(ValueError):
        parse(intent)


def test_annotations_paired_strict_and_scoped_to_edited_sketch(intent):
    layout = {
        "schema_version": 1,
        "kind": "sketch_annotation_layout",
        "documents": {
            "staged_projection": {
                "source": {
                    "size": {
                        "kind": "radius",
                        "refs": ["replacement_ring"],
                        "display": "radius",
                        "offset": [2, 3],
                    }
                }
            }
        },
    }
    intent["annotation_before"] = ""
    intent["annotation_after"] = json.dumps(layout)
    assert parse(intent)["annotation_after"] == json.dumps(layout)
    layout["documents"]["staged_projection"]["target"] = layout["documents"][
        "staged_projection"
    ].pop("source")
    intent["annotation_after"] = json.dumps(layout)
    with pytest.raises(ValueError, match="unrelated"):
        parse(intent)
    intent["annotation_after"] = '{"schema_version":999}'
    with pytest.raises(ValueError):
        parse(intent)


def test_repair_scope_preserves_explicit_projection_source_port(intent):
    # The persistence codec delegates schema admission. The shared pure scope
    # remains conservative when the independently versioned multi-source contract
    # is integrated: changing per-row ports cannot change source identity.
    previous = json.loads(intent["states"][0])
    candidate = json.loads(intent["states"][1])
    feature(previous, "target")["projections"][0]["input"] = "external_one"
    feature(candidate, "target")["projections"][0]["input"] = "external_two"
    with pytest.raises(ValueError, match="source port"):
        codec.repair_scope.validate_transition(previous, candidate, "source", {"target"})
