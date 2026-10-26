"""Host dialog seams only; this is not Blender GUI qualification."""

import importlib
import sys
import types
from pathlib import Path

import pytest


@pytest.fixture
def ui(monkeypatch):
    name = "mcad_projection_repair_ui_tests"
    package = types.ModuleType(name)
    package.__path__ = [
        str(Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender")
    ]
    monkeypatch.setitem(sys.modules, name, package)

    def module(suffix, **attrs):
        result = types.ModuleType(suffix)
        result.__dict__.update(attrs)
        monkeypatch.setitem(sys.modules, suffix, result)
        return result

    module("bpy")
    module(
        "bpy.props",
        BoolProperty=lambda **k: None,
        EnumProperty=lambda **k: None,
        StringProperty=lambda **k: None,
    )
    module("bpy.types", Operator=type("Operator", (), {}))
    for suffix in ("backend_contracts", "backend_runtime", "document_state", "guarded_transport"):
        module(name + "." + suffix)
    module(name + ".common", _state=lambda c: c.state)
    module(name + ".history_operators", _HistoryDialog=type("History", (), {}))
    module(
        name + ".operators",
        _reject_candidate=lambda op, c, message: ("REJECTED", message),
        _report_result=lambda op, c, result: result,
    )
    for suffix in ("projection_repair_ui", "projection_repair", "sketch_projection"):
        sys.modules.pop(name + "." + suffix, None)
    return importlib.import_module(name + ".projection_repair_ui")


def test_dialog_stale_document_rejects_before_evidence_or_write(ui):
    operator = ui.MCAD_OT_replace_projection_reference()
    operator.poll = lambda c: True
    operator._original = lambda c: (_ for _ in ()).throw(ValueError("document changed"))
    operator._candidate = lambda: pytest.fail("Must not build from a stale dialog")
    result = operator.execute(types.SimpleNamespace())
    assert result == ("REJECTED", "document changed")


def test_failed_complete_rebuild_leaves_publication_to_atomic_sink_and_releases(ui):
    operator = ui.MCAD_OT_replace_projection_reference()
    operator.poll = lambda c: True
    operator._review = lambda c: {}
    candidate = {"candidate": True}
    operator._candidate = lambda: candidate
    calls = []
    operator._catalog_evidence = types.SimpleNamespace(
        publication=types.SimpleNamespace(cancel=lambda: calls.append("released"))
    )

    def commit(context, received, path):
        assert received is candidate
        calls.append("checked")
        raise ValueError("Dependent Cut would remove no material")

    ui.document_state._commit_candidate = commit
    context = types.SimpleNamespace(state=types.SimpleNamespace(document_path=""))
    assert operator.execute(context) == ("REJECTED", "Dependent Cut would remove no material")
    assert calls == ["checked", "released"]
    assert operator._catalog_evidence is None


def test_cancel_releases_read_only_evidence_without_publishing(ui):
    operator = ui.MCAD_OT_replace_projection_reference()
    calls = []
    for name in ("_catalog_evidence", "_plane_evidence"):
        setattr(
            operator,
            name,
            types.SimpleNamespace(
                publication=types.SimpleNamespace(cancel=lambda: calls.append("released"))
            ),
        )
    operator.cancel(None)
    operator.cancel(None)
    assert calls == ["released", "released"]


def test_enum_callbacks_use_rna_presentation_data_not_python_owner_attrs(ui):
    import json

    data = {
        "targets": [["guide", "Line · guide", "Keep identities"]],
        "sources": {"guide": [["1", "Line · source", "source"]]},
        "defaults": {"guide": ["1", True]},
    }
    wrapper = types.SimpleNamespace(choice_data_json=json.dumps(data), target="guide")
    assert ui._targets(wrapper, None)[0][0] == "guide"
    assert ui._sources(wrapper, None)[0][0] == "1"
    ui._target_changed(wrapper, None)
    assert wrapper.replacement == "1" and wrapper.reverse is True
    assert ui._targets(types.SimpleNamespace(choice_data_json=""), None)[0][0] == "NONE"


def test_identical_reference_labels_remain_bound_to_each_source(ui):
    import json

    feature = {
        "inputs": {"external": "body_a", "external_2": "body_b"},
        "sketch": {
            "lines": [],
            "circles": [{"id": "a", "construction": True}, {"id": "b", "construction": True}],
        },
        "projections": [
            {"kind": "circle", "faces": ["shared/end", "shared/side"], "target": "a"},
            {
                "kind": "circle",
                "faces": ["shared/end", "shared/side"],
                "target": "b",
                "input": "external_2",
            },
        ],
    }
    entries = [
        {
            "kind": "circle",
            "source_id": source,
            "label": "Same edge label",
            "row": {"kind": "circle", "faces": ["shared/end", "shared/side"]},
        }
        for source in ("body_a", "body_b")
    ]
    choices = json.loads(ui._choice_data(feature, entries))
    assert [row[0] for row in choices["sources"]["a"]] == ["0"]
    assert [row[0] for row in choices["sources"]["b"]] == ["1"]
    assert choices["defaults"]["a"][0] == "0"
    assert choices["defaults"]["b"][0] == "1"
