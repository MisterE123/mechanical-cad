"""Detached operator ports: no Blender or native work, exactly one commit seam."""

import importlib
import json
import sys
import types
from pathlib import Path

import pytest


@pytest.fixture
def host(monkeypatch):
    name = "extrusion_operator_tests"
    package = types.ModuleType(name)
    package.__path__ = [
        str(Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender")
    ]
    monkeypatch.setitem(sys.modules, name, package)
    document = {
        "features": [
            {"id": "profile", "kind": "sketch_rectangle"},
            {"id": "base", "kind": "extrude"},
        ],
        "parameters": {},
        "active_feature": "base",
    }
    state = types.SimpleNamespace(
        document_json=json.dumps(document), document_path="saved.mcad.json"
    )
    context = types.SimpleNamespace(mode="OBJECT")
    commits, errors = [], []

    def commit(ctx, candidate, path):
        commits.append((candidate, path))
        return True

    def module(key, **values):
        value = types.ModuleType(key)
        value.__dict__.update(values)
        monkeypatch.setitem(sys.modules, key, value)
        return value

    module(
        name + ".extrusion_preview",
        start=lambda *args: None,
        apply=lambda *args: None,
        cancel=lambda *args: None,
        changed=lambda *args: True,
        modal=lambda *args: None,
    )
    module("bpy")
    module(
        "bpy.props",
        EnumProperty=lambda **kw: None,
        StringProperty=lambda **kw: None,
        BoolProperty=lambda **kw: None,
        IntProperty=lambda **kw: None,
    )
    module(
        name + ".help_ui",
        _draw_feature_help=lambda *args: None,
        _feature_help_next=lambda *args: None,
        _feature_help_previous=lambda *args: None,
    )
    module("bpy.types", Operator=type("Operator", (), {}))
    module(name + ".common", _state=lambda ctx: state)
    module(name + ".execution_lease", is_busy=lambda: False)
    module(
        name + ".document_state",
        _REPLAY_RUNNING=False,
        _read_document=lambda s: json.loads(s.document_json),
        _commit_candidate=commit,
        _new_feature=lambda ctx, kind, params, inputs, label: dict(
            id=kind + "_1", kind=kind, params=params, inputs=inputs, label=label
        ),
    )
    module(
        name + ".operators",
        _report_result=lambda *args: {"FINISHED"},
        _reject_candidate=lambda op, ctx, message: errors.append(message) or {"CANCELLED"},
    )
    module(
        name + ".solid_operators",
        _profile_choices=lambda *args: [],
        _solid_choices=lambda *args: [],
    )
    monkeypatch.delitem(sys.modules, name + ".extrusion_operators", raising=False)
    operator_module = importlib.import_module(name + ".extrusion_operators")
    operator = operator_module.MCAD_OT_extrude_boolean()
    operator.mode, operator.depth, operator.profile, operator.base = (
        "REMOVE",
        "-depth",
        "profile",
        "base",
    )
    operator.feature_label, operator.original_json = "Pocket", state.document_json
    operator.direction = "SIGNED"
    operator.end_condition = "BLIND"
    return types.SimpleNamespace(
        operator=operator,
        module=operator_module,
        context=context,
        state=state,
        commits=commits,
        errors=errors,
    )


def test_one_apply_commits_both_nodes_once_without_intermediate_state(host):
    before = host.state.document_json
    assert host.operator.execute(host.context) == {"FINISHED"}
    assert len(host.commits) == 1
    candidate, path = host.commits[0]
    assert path == "saved.mcad.json" and host.state.document_json == before
    assert [node["kind"] for node in candidate["features"][-2:]] == ["extrude", "cut"]
    assert candidate["active_feature"] == "cut_1"
    assert candidate["parameters"]["extrude_1_length"] == "-depth"


def test_stale_dialog_never_enters_commit(host):
    host.state.document_json += " "
    assert host.operator.execute(host.context) == {"CANCELLED"}
    assert not host.commits and "Document changed" in host.errors[-1]


def test_native_commit_failure_is_reported_without_local_source_mutation(host, monkeypatch):
    def failed(*args):
        raise ValueError("cut_1: Boolean produced no solid")

    before = host.state.document_json
    monkeypatch.setattr(host.module, "_commit_candidate", failed)
    assert host.operator.execute(host.context) == {"CANCELLED"}
    assert host.state.document_json == before
    assert host.errors == ["cut_1: Boolean produced no solid"]


def test_reverse_direction_preserves_the_entire_depth_formula(host):
    host.operator.direction = "REVERSE"
    host.operator.depth = "wall + clearance"
    assert host.operator.execute(host.context) == {"FINISHED"}
    candidate = host.commits[0][0]
    assert candidate["parameters"]["extrude_1_length"] == "-(wall + clearance)"


def test_negative_directional_depth_rejects_before_commit(host):
    host.operator.direction = "REVERSE"
    host.operator.depth = "-5"
    assert host.operator.execute(host.context) == {"CANCELLED"}
    assert not host.commits
    assert "Depth must be positive" in host.errors[-1]


def test_invoke_uses_selected_profile_and_preserves_explicit_operands(host):
    document = json.loads(host.state.document_json)
    document["features"].append({"id": "latest", "kind": "sketch_rectangle"})
    host.state.document_json = json.dumps(document)
    host.state.features = [types.SimpleNamespace(feature_id="profile")]
    host.state.feature_index = 0
    host.operator.properties = types.SimpleNamespace(is_property_set=lambda key: False)
    host.context.window_manager = types.SimpleNamespace(
        invoke_props_dialog=lambda *args, **kwargs: {"RUNNING_MODAL"}
    )
    assert host.operator.invoke(host.context, None) == {"RUNNING_MODAL"}
    assert host.operator.profile == "profile" and host.operator.base == "base"
    assert host.operator.direction == "NORMAL"
    assert host.operator.original_json == host.state.document_json
    host.operator.properties = types.SimpleNamespace(is_property_set=lambda key: True)
    host.operator.profile = "latest"
    host.operator.direction = "REVERSE"
    assert host.operator.invoke(host.context, None) == {"RUNNING_MODAL"}
    assert host.operator.profile == "latest" and host.operator.direction == "REVERSE"


def test_remove_default_points_into_proven_support_but_never_overrides_user(host):
    document = json.loads(host.state.document_json)
    document["features"][0].update(
        kind="sketch_constrained",
        support_face="top",
        inputs={"support": "base"},
        sketch={"plane": {"origin": [0, 0, 0], "quaternion": [1, 0, 0, 0]}},
    )
    host.state.document_json = json.dumps(document)
    host.operator.properties = types.SimpleNamespace(is_property_set=lambda key: False)
    host.context.window_manager = types.SimpleNamespace(
        invoke_props_dialog=lambda *args, **kwargs: {"RUNNING_MODAL"}
    )
    assert host.operator.invoke(host.context, None) == {"RUNNING_MODAL"}
    assert host.operator.direction == "REVERSE"
    host.operator.mode = "ADD"
    assert host.operator.invoke(host.context, None) == {"RUNNING_MODAL"}
    assert host.operator.direction == "NORMAL"
    host.operator.mode = "REMOVE"
    host.operator.properties = types.SimpleNamespace(is_property_set=lambda key: key == "direction")
    assert host.operator.invoke(host.context, None) == {"RUNNING_MODAL"}
    assert host.operator.direction == "NORMAL"
    host.operator.properties = types.SimpleNamespace(is_property_set=lambda key: key == "depth")
    assert host.operator.invoke(host.context, None) == {"RUNNING_MODAL"}
    assert host.operator.direction == "SIGNED"


def test_through_all_operator_commits_intent_without_a_depth(host):
    host.operator.end_condition = "THROUGH_ALL"
    host.operator.direction = "REVERSE"
    host.operator.depth = "ignored even if invalid"
    assert host.operator.execute(host.context) == {"FINISHED"}
    assert len(host.commits) == 1
    candidate = host.commits[0][0]
    assert candidate["parameters"] == {}
    tool = candidate["features"][-2]
    assert tool["kind"] == "extrude_through"
    assert tool["params"] == {"direction": -1}
    assert tool["inputs"] == {"base": "base", "profile": "profile"}


def test_through_all_requires_explicit_direction(host):
    host.operator.end_condition = "THROUGH_ALL"
    assert host.operator.execute(host.context) == {"CANCELLED"}
    assert not host.commits
    assert "explicit" in host.errors[-1]


@pytest.mark.parametrize("mode", ["ADD", "REMOVE"])
def test_symmetric_operator_saves_total_depth_not_directional_length(host, mode):
    host.operator.mode = mode
    host.operator.end_condition = "SYMMETRIC"
    host.operator.direction = "REVERSE"
    host.operator.depth = "total"
    assert host.operator.execute(host.context) == {"FINISHED"}
    candidate = host.commits[0][0]
    tool = candidate["features"][-2]
    assert tool["kind"] == "extrude_symmetric"
    assert candidate["parameters"]["extrude_symmetric_1_length"] == "total"
    assert tool["inputs"] == {"profile": "profile"}


@pytest.mark.parametrize("mode", ["ADD", "REMOVE"])
def test_up_to_face_operator_keeps_target_face_and_formula_without_depth(host, mode):
    op = host.operator
    op.mode, op.end_condition, op.direction = mode, "UP_TO_FACE", "REVERSE"
    op.target, op.end_face, op.offset = "base", "base/face/cap.start", "gap+1"
    # Irrelevant blind input must not be evaluated or copied into the end intent.
    op.depth = ""
    result = op.preview_candidate(host.context)
    tool = result["features"][-2]
    assert tool["kind"] == "extrude_to_face"
    assert tool["params"] == {"direction": -1, "offset": "gap+1"}
    assert tool["inputs"] == {"profile": "profile", "target": "base"}
    assert tool["end_face"] == "base/face/cap.start"
    assert result["parameters"] == {}
    assert result["features"][-1]["kind"] == ("union" if mode == "ADD" else "cut")


def test_up_to_face_requires_explicit_source_face_and_direction(host):
    op = host.operator
    op.end_condition, op.direction = "UP_TO_FACE", "SIGNED"
    op.target, op.end_face, op.offset = "base", "base/face/cap.start", "0"
    with pytest.raises(ValueError, match="explicit"):
        op.preview_candidate(host.context)
    op.direction = "NORMAL"
    op.target = "NONE"
    with pytest.raises(ValueError, match="earlier target"):
        op.preview_candidate(host.context)
    op.target, op.end_face = "base", "NONE"
    with pytest.raises(ValueError, match="stable planar end face"):
        op.preview_candidate(host.context)


@pytest.mark.parametrize("direction", ["direction", "linked_direction"])
def test_shared_up_to_face_draw_uses_short_labels_without_changing_intent(host, direction):
    op = types.SimpleNamespace(
        target="base",
        end_face="base/face/cap.start",
        offset="gap+1",
        direction="SIGNED",
        linked_direction="-1",
    )
    before = vars(op).copy()
    props, labels = [], []
    layout = types.SimpleNamespace(
        prop=lambda obj, name, **kw: props.append((name, kw["text"])),
        label=lambda **kw: labels.append(kw["text"]),
    )
    host.module.draw_up_to_face(layout, op, direction=direction)
    assert props == [
        ("target", "Earlier target solid"),
        ("end_face", "End face"),
        (direction, "Direction"),
        ("offset", "Offset (mm)"),
    ]
    assert len(labels) == 3
    assert any("infinite face plane" in text and "finite boundary" in text for text in labels)
    assert any("parallel and ahead" in text for text in labels)
    assert any("Positive offset: past plane. Negative: stop short." == text for text in labels)
    tooltip = host.module.OFFSET_DESCRIPTION
    assert "Number or formula in mm" in tooltip and "selected direction" in tooltip
    assert "Positive extends past" in tooltip and "negative stops short" in tooltip
    assert vars(op) == before
