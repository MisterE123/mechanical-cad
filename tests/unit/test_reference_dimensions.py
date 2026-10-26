"""Reference annotation intent, pure measurements and persistence contracts."""

import copy
import importlib
import json
import math
import sys
import types
from dataclasses import replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "mcad_reference_dimension_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
sys.modules[PACKAGE] = package
d = importlib.import_module(PACKAGE + ".general_sketch_draft")
commands = importlib.import_module(PACKAGE + ".general_sketch_commands")
a = importlib.import_module(PACKAGE + ".general_authoring")
g = importlib.import_module(PACKAGE + ".general_view_geometry")
r = importlib.import_module(PACKAGE + ".reference_dimensions")
s = importlib.import_module(PACKAGE + ".sketch_annotation_store")
codec = importlib.import_module(PACKAGE + ".general_arc_authoring_store")


def authoring():
    base = json.dumps(
        {
            "schema_version": 1,
            "id": "part",
            "name": "Part",
            "units": "mm",
            "parameters": {},
            "features": [],
            "active_feature": None,
        }
    )
    draft = d.GeneralSketchDraft(base, journal_version=3)
    p, q, line = draft.execute(d.AddLine(d.PointSeed(0, 0), d.PointSeed(3, 4))).entity_ids
    center, circle = draft.execute(d.AddCircle(d.PointSeed(10, 10), 5)).entity_ids
    *_, arc = draft.execute(
        d.AddArc(d.PointSeed(20, 0), d.PointSeed(25, 0), d.PointSeed(20, 5), "ccw")
    ).entity_ids
    return a.GeneralSketchAuthoringState(draft, ui_version=2), (p, q, line, circle, arc)


@pytest.fixture
def overlay(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Pure frame generation cannot call graphics")

    for name in ("blf", "gpu", "gpu_extras", "gpu_extras.batch"):
        module = types.ModuleType(name)
        module.__getattr__ = lambda name: forbidden
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setattr(
        sys.modules["gpu_extras.batch"], "batch_for_shader", forbidden, raising=False
    )
    return importlib.import_module(PACKAGE + ".general_sketch_overlay")


def test_add_move_remove_are_ui_only_and_no_measured_values_are_saved():
    state, (_, _, line, circle, arc) = authoring()
    before = copy.deepcopy(state.command_draft.checkpoint_payload())
    candidate = state.candidate()
    for kind, source_kind, target in (
        ("length", "line", line),
        ("radius", "circle", circle),
        ("diameter", "arc", arc),
    ):
        key, changed = state.place_reference(kind, source_kind, target, (8, 8))
        assert changed and state.annotations[key]["role"] == "reference"
        assert "value" not in state.annotations[key] and "measured" not in state.annotations[key]
        assert state.place_reference(kind, source_kind, target, (99, 99)) == (key, False)
        assert state.move_annotation(key, (11, 12))
    assert state.command_draft.checkpoint_payload() == before
    assert state.candidate() == candidate
    assert not state.status.conflicts
    saved = codec.dumps(state)
    restored = codec.restore(saved, state.document_json)
    assert codec.dumps(restored) == saved
    for key in tuple(restored.annotations):
        assert restored.remove_annotation(key)
    assert not restored.annotations
    assert restored.command_draft.checkpoint_payload() == before


@pytest.mark.parametrize(
    "kind,source_kind,index,expected,prefix",
    [
        ("length", "line", 2, 5, ""),
        ("radius", "circle", 3, 5, "R "),
        ("diameter", "circle", 3, 10, "⌀ "),
        ("radius", "arc", 4, 5, "R "),
        ("diameter", "arc", 4, 10, "⌀ "),
    ],
)
def test_measured_labels_are_read_only_and_authored_estimates_are_explicit(
    overlay, kind, source_kind, index, expected, prefix
):
    state, ids = authoring()
    key, _ = state.place_reference(kind, source_kind, ids[index], (8, 8))
    geometry = g.build_geometry(state.command_draft.sketch, source="authored")
    frame = overlay.build_frame(geometry, lambda world: world[:2], annotations=state.annotations)
    label = frame.labels[0]
    assert label.constraint_id == key and label.raw_value is None
    assert label.measured_mm == pytest.approx(expected)
    assert label.text == f"{prefix}~{expected} mm (REF)"
    assert label.detail == "Read-only reference · unsolved estimate"
    # Source qualification is provided by the existing owner, never by metadata.
    solved = replace(geometry, source="solved", request_fingerprint="a" * 64)
    label = overlay.build_frame(
        solved,
        lambda world: world[:2],
        annotations=state.annotations,
        current_request_fingerprint="a" * 64,
    ).labels[0]
    assert "~" not in label.text and label.detail == "Read-only reference"


def test_measurement_follows_geometry_not_stored_radius_or_label_cache(overlay):
    state, (_, endpoint, line, circle, _) = authoring()
    length, _ = state.place_reference("length", "line", line, (8, 8))
    diameter, _ = state.place_reference("diameter", "circle", circle, (8, 8))
    original = state.annotations
    state.command_draft.execute(commands.MovePoint(endpoint, (6, 8)))
    source = state.command_draft.sketch
    source["circles"][0]["radius"] = 7
    frame = overlay.build_frame(
        g.build_geometry(source, source="authored"),
        lambda world: world[:2],
        annotations=state.annotations,
    )
    values = {label.constraint_id: label.measured_mm for label in frame.labels}
    assert values[length] == pytest.approx(10) and values[diameter] == pytest.approx(14)
    assert state.annotations == original


def test_deleted_entity_reference_is_unavailable_and_only_exact_id_undo_revives(overlay):
    state, (_, _, _, _, arc) = authoring()
    key, _ = state.place_reference("diameter", "arc", arc, (8, 8))
    original = state.annotations
    state.command_draft.undo()  # Remove the AddArc command, not the UI annotation.
    assert state.annotations == original
    assert state.status.annotations[0].state == "missing"
    restored = codec.restore(codec.dumps(state), state.document_json)
    frame = overlay.build_frame(
        g.build_geometry(restored.command_draft.sketch, source="authored"),
        lambda world: world[:2],
        annotations=restored.annotations,
    )
    assert not frame.labels and frame.unavailable
    state.command_draft.redo()
    assert state.status.annotations[0].available
    frame = overlay.build_frame(
        g.build_geometry(state.command_draft.sketch, source="authored"),
        lambda world: world[:2],
        annotations=state.annotations,
    )
    assert frame.labels[0].constraint_id == key


def test_scene_store_roundtrip_missing_changed_target_and_explicit_remove():
    state, (_, _, line, _, _) = authoring()
    key, _ = state.place_reference("length", "line", line, (8, -0.0))
    raw = s.replace_annotations("", "part", state.feature_id, state.annotations)
    assert s.replace_annotations(raw, "part", state.feature_id, state.annotations) == raw
    source = state.command_draft.sketch
    assert s.annotations_for(raw, "part", state.feature_id, source).annotations == state.annotations
    source["lines"] = []
    missing = s.annotations_for(raw, "part", state.feature_id, source)
    assert not missing.annotations and missing.unavailable[key].state == "missing"
    # Equal shape with another ID does not recover the old binding.
    source["lines"] = [
        {"id": "replacement", "start": source["points"][0]["id"], "end": source["points"][1]["id"]}
    ]
    assert not s.annotations_for(raw, "part", state.feature_id, source).annotations
    source["circles"].append({"id": line, "center": source["points"][0]["id"], "radius": 1})
    assert (
        s.annotations_for(raw, "part", state.feature_id, source).unavailable[key].state == "changed"
    )
    assert not s.annotations_for(
        s.replace_annotations(raw, "part", state.feature_id, {}), "part", state.feature_id, source
    ).all_annotations


@pytest.mark.parametrize(
    "mutation",
    [
        lambda x: x.update(value=5),
        lambda x: x.update(role="driving"),
        lambda x: x.update(kind="angle"),
        lambda x: x.update(source_kind="point"),
        lambda x: x.update(refs=["another_id"]),
        lambda x: x.update(offset=[math.inf, 0]),
    ],
)
def test_malformed_reference_metadata_is_rejected_without_rewriting(mutation):
    state, (_, _, line, _, _) = authoring()
    key, _ = state.place_reference("length", "line", line, (8, 8))
    binding = state.annotations[key]
    mutation(binding)
    with pytest.raises(ValueError):
        s.replace_annotations("", "part", state.feature_id, {key: binding})


def test_wrong_selection_and_missing_new_target_fail_without_command_changes():
    state, (_, _, line, circle, _) = authoring()
    before = codec.dumps(state)
    for args in (
        ("radius", "line", line),
        ("length", "circle", circle),
        ("length", "line", "missing"),
    ):
        with pytest.raises(ValueError):
            state.place_reference(*args, (8, 8))
        assert codec.dumps(state) == before


def test_committed_missing_reference_can_be_opened_and_explicitly_removed():
    state, (_, _, _, _, arc) = authoring()
    key, _ = state.place_reference("diameter", "arc", arc, (8, 8))
    original = state.annotations
    state.command_draft.undo()
    committed = json.dumps(state.candidate())
    draft = d.GeneralSketchDraft(committed, state.feature_id, True, journal_version=3)
    ui = a.empty_ui(ui_version=2)
    ui["annotations"] = original
    reopened = a.GeneralSketchAuthoringState(draft, ui, ui_version=2)
    assert reopened.status.annotations[0].state == "missing"
    assert reopened.remove_annotation(key)
    assert not reopened.annotations and reopened.candidate() == draft.candidate()
