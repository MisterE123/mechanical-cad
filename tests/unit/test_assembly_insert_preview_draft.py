"""Stable detached insertion candidates reuse the real canonical edit helpers."""

import copy
import importlib

import pytest
from test_assembly_edit import PACKAGE, document, edit

from mechanical_cad.assembly_model import AssemblyDocument
from mechanical_cad.errors import CADException

InsertPreviewDraft = importlib.import_module(
    PACKAGE + ".assembly_insert_preview_draft"
).InsertPreviewDraft


@pytest.fixture
def inputs():
    part = document()
    accepted = edit.new_from_part(part)
    arguments = dict(
        parent=accepted["grounded_instance"], parent_frame="origin",
        child_frame="origin", kind="fixed", name="Preview child", joint_name="Attachment",
    )
    return accepted, part, arguments


def build(inputs, **overrides):
    accepted, _, arguments = inputs
    return InsertPreviewDraft(
        accepted, accepted["parts"][0]["id"], **(arguments | overrides)
    )


def test_ids_generated_once_and_all_access_is_detached(inputs, monkeypatch):
    accepted, part, arguments = inputs
    before = copy.deepcopy(inputs)
    identities = []
    real_identity = edit.identity

    def identity(prefix):
        value = real_identity(prefix)
        identities.append((prefix, value))
        return value

    monkeypatch.setattr(edit, "identity", identity)
    draft = build(inputs, working_part=part)
    expected = draft.candidate()
    assert [p for p, _ in identities] == ["instance", "joint"]
    assert draft.part_id == accepted["parts"][0]["id"]
    assert draft.instance_id == expected["instances"][-1]["id"]
    assert draft.joint_id == expected["joints"][-1]["id"]
    for _ in range(3):
        AssemblyDocument.from_dict(draft.candidate())
        draft.candidate()["instances"].clear()
        draft.original()["parts"].clear()
    assert len(identities) == 2 and inputs == before
    accepted["instances"].clear()
    part["name"] = "Changed later"
    arguments["name"] = "Changed later"
    assert draft.candidate() == expected and draft.original() == before[0]
    with pytest.raises(AttributeError):
        draft.instance_id = "replacement"


def test_new_source_capture_and_joint_are_atomic_detached_candidate(inputs):
    accepted, part, _ = inputs
    working = copy.deepcopy(part)
    working["id"] = "independent_part"
    before = copy.deepcopy((accepted, working))
    draft = build(inputs, working_part=working)
    candidate = draft.candidate()
    AssemblyDocument.from_dict(candidate)
    assert len(candidate["parts"]) == len(candidate["part_sources"]) == 2
    assert len(candidate["instances"]) == 2 and len(candidate["joints"]) == 1
    assert candidate["joints"][-1]["child"] == draft.instance_id
    assert candidate["instances"][-1]["part_id"] == draft.part_id
    assert candidate["parts"][-1]["source_document_id"] == working["id"]
    assert (accepted, working) == before
    working["parameters"].clear()
    assert draft.candidate() == candidate


def test_divergent_accepted_source_rejected_without_orphan_or_input_change(inputs):
    accepted, part, _ = inputs
    changed = copy.deepcopy(part)
    changed["parameters"]["sketch_1_width"] = 60
    before = copy.deepcopy((accepted, changed))
    with pytest.raises(edit.BridgeError, match="update available"):
        build(inputs, working_part=changed)
    assert (accepted, changed) == before


def test_failed_insert_after_capture_does_not_leave_definition(inputs):
    accepted, part, arguments = inputs
    working = copy.deepcopy(part)
    working["id"] = "independent_part"
    before = copy.deepcopy((accepted, working))
    with pytest.raises(TypeError):
        InsertPreviewDraft(accepted, "unused", working_part=working,
                           **arguments, unsupported_argument=True)
    assert (accepted, working) == before


@pytest.mark.parametrize("kind", ["fixed", "revolute", "slider", "cylindrical", "planar", "spherical"])
def test_all_existing_joint_kinds_preserve_named_fields_and_canonical_units(inputs, kind):
    extras = {
        "cylindrical": {"rotation": (0.3, [-1, 1])},
        "planar": {"translation_x": (12.5, [-20, 20]),
                   "translation_y": (-3, [-10, 10]), "rotation": (0.3, [-1, 1])},
        "spherical": {"rotation_x": (0.2, [-1, 1]),
                      "rotation_y": (-0.4, [-1, 1]), "rotation": (0.3, [-1, 1])},
    }.get(kind, {})
    arguments = dict(kind=kind, coordinate=0.75, limits=[-1, 1],
                     rotation=0.3, rotation_limits=[-1, 1], extra_coordinates=extras)
    before = copy.deepcopy(arguments)
    draft = build(inputs, **arguments)
    candidate = draft.candidate()
    model = AssemblyDocument.from_dict(candidate)
    joint = candidate["joints"][-1]
    assert model.joints[-1].kind == kind
    assert joint["name"] == "Attachment"
    if kind in {"revolute", "slider", "cylindrical"}:
        assert joint["coordinate"] == 0.75 and joint["limits"] == [-1, 1]
    else:
        assert "coordinate" not in joint and "limits" not in joint
    for key, (value, limits) in extras.items():
        assert joint[key] == value and joint[key + "_limits"] == limits
    assert arguments == before
    arguments["limits"].clear()
    extras.clear()
    assert draft.candidate() == candidate


@pytest.mark.parametrize("bad", [
    {"kind": "unknown"}, {"parent": "missing"}, {"parent_frame": "missing"},
    {"child_frame": "missing"}, {"kind": "revolute", "coordinate": True},
    {"kind": "revolute", "coordinate": float("inf")},
    {"kind": "revolute", "coordinate": 3, "limits": [-1, 1]},
])
def test_candidate_is_not_authority_invalid_edit_inputs_still_fail_canonical_validation(inputs, bad):
    before = copy.deepcopy(inputs)
    draft = build(inputs, **bad)
    with pytest.raises((CADException, ValueError)):
        AssemblyDocument.from_dict(draft.candidate())
    assert inputs == before


def test_missing_reusable_part_rejected_without_mutation(inputs):
    accepted, _, arguments = inputs
    before = copy.deepcopy(accepted)
    with pytest.raises(edit.BridgeError, match="existing reusable part"):
        InsertPreviewDraft(accepted, "missing", **arguments)
    assert accepted == before
