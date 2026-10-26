"""Transport-free Hole dialog currentness, explicit selection and Cancel wiring."""

import importlib
import json
import sys
import types
from pathlib import Path

import pytest


@pytest.fixture
def host(monkeypatch):
    name = "hole_operator_test_addon"
    package = types.ModuleType(name)
    package.__path__ = [str(Path(__file__).parents[2] / "blender_addon/mechanical_cad_blender")]
    monkeypatch.setitem(sys.modules, name, package)

    def module(key, **values):
        obj = types.ModuleType(key)
        obj.__dict__.update(values)
        monkeypatch.setitem(sys.modules, key, obj)
        return obj

    document = {
        "parameters": {},
        "features": [{"id": "pad", "kind": "extrude"}],
        "active_feature": "pad",
    }
    state = types.SimpleNamespace(document_json=json.dumps(document), document_path="part.json")
    evidence = {
        "features": [
            {
                "id": "pad",
                "status": "ok",
                "topology": [
                    {
                        "id": "pad/face/cap.end",
                        "kind": "face",
                        "signature": {"surface": "plane"},
                        "provenance": {"semantic_status": "stable"},
                    }
                ],
            }
        ]
    }
    commits, errors, cancelled = [], [], []
    module(
        "bpy.props",
        **{name: lambda **kw: None for name in ("BoolProperty", "EnumProperty", "StringProperty")},
    )
    module("bpy.types", Operator=type("Operator", (), {}))
    module(name + ".common", _state=lambda context: state)
    module(name + ".execution_lease", is_busy=lambda: False)
    module(
        name + ".document_state",
        _REPLAY_RUNNING=False,
        _read_document=lambda state: json.loads(state.document_json),
        current_part_result=lambda context: evidence,
        _commit_candidate=lambda context, candidate, path: commits.append(candidate) or True,
    )
    module(
        name + ".extrusion_preview",
        apply=lambda *a: None,
        start=lambda *a: None,
        changed=lambda *a: True,
        modal=lambda *a: None,
        cancel=lambda *a: cancelled.append(True),
    )
    module(name + ".solid_operators", _solid_choices=lambda *a: [])
    module(
        name + ".operators",
        _report_result=lambda *a: {"FINISHED"},
        _reject_candidate=lambda op, ctx, text: errors.append(text) or {"CANCELLED"},
    )
    monkeypatch.delitem(sys.modules, name + ".hole_operators", raising=False)
    mod = importlib.import_module(name + ".hole_operators")
    op = mod.MCAD_OT_round_hole()
    for key, value in dict(
        base="pad",
        face="pad/face/cap.end",
        diameter="5",
        depth="10",
        counterbore=False,
        counter_diameter="10",
        counter_depth="2",
        x="0",
        y="0",
        feature_label="Hole",
        feature_id="",
        recipe_id="",
        original_json=state.document_json,
    ).items():
        setattr(op, key, value)
    return types.SimpleNamespace(
        op=op,
        state=state,
        evidence=evidence,
        commits=commits,
        errors=errors,
        cancelled=cancelled,
        context=types.SimpleNamespace(mode="OBJECT"),
        module=mod,
    )


def test_preview_is_detached_cancel_has_no_publication(host):
    before = host.state.document_json
    candidate = host.op.preview_candidate(host.context)
    assert candidate["active_feature"].startswith("hole_")
    assert candidate == host.op.preview_candidate(host.context)
    host.op.cancel(host.context)
    assert host.cancelled and not host.commits
    assert host.state.document_json == before


@pytest.mark.parametrize("bad", ["stale", "snapshot", "missing", "curved", "none"])
def test_invalid_face_evidence_or_document_refuses_publication(host, bad):
    face = host.evidence["features"][0]["topology"][0]
    if bad == "stale":
        host.state.document_json += " "
    elif bad == "snapshot":
        face["provenance"]["semantic_status"] = "unknown"
    elif bad == "missing":
        host.evidence["features"][0]["topology"] = []
    elif bad == "curved":
        face["signature"]["surface"] = "cylinder"
    else:
        host.op.face = "NONE"
    assert host.op.execute(host.context) == {"CANCELLED"}
    assert not host.commits and host.errors


def test_apply_uses_one_existing_commit_seam(host):
    assert host.op.execute(host.context) == {"FINISHED"}
    assert len(host.commits) == 1
    assert host.commits[0]["features"][-1]["kind"] == "cut"


@pytest.mark.parametrize("unset", ["", "NONE"])
def test_unselected_entry_face_guides_first_selection(host, unset):
    host.op.face = unset
    with pytest.raises(ValueError, match="^Choose an entry face to preview the hole$"):
        host.op.preview_candidate(host.context)
    assert host.op.execute(host.context) == {"CANCELLED"}
    assert not host.commits
    assert host.errors == ["Choose an entry face to preview the hole"]


@pytest.mark.parametrize("bad", ["missing", "snapshot", "curved", "ambiguous"])
def test_captured_entry_face_keeps_identity_warning(host, bad):
    topology = host.evidence["features"][0]["topology"]
    if bad == "missing":
        topology.clear()
    elif bad == "snapshot":
        topology[0]["provenance"]["semantic_status"] = "unknown"
    elif bad == "curved":
        topology[0]["signature"]["surface"] = "cylinder"
    else:
        topology.append(dict(topology[0]))
    with pytest.raises(ValueError, match="no longer has a stable planar identity; pick again"):
        host.op.preview_candidate(host.context)
    assert not host.commits


def test_changed_document_precedes_unselected_guidance(host):
    host.op.face = "NONE"
    host.state.document_json += " "
    with pytest.raises(ValueError, match="Document changed; reopen Hole"):
        host.op.preview_candidate(host.context)
