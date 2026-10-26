"""Pure explicit overlap choice state; no native or UI qualification claims."""

import copy
import importlib
import json
import sys
import types
from pathlib import Path

import pytest

PACKAGE = "mcad_projection_choice_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender")]
sys.modules[PACKAGE] = package
M = importlib.import_module(PACKAGE + ".projection_edge_choice")


def fixture(count=2):
    entries = [{"faces": [f"pad/face/cap.{i}", "pad/face/side.arc"],
                "points": [[0, 0, i], [1, 0, i]],
                "endpoint_faces": [["a"], ["b"]]} for i in range(count)]
    picker = types.SimpleNamespace(catalog={"pad": entries}, catalog_token=object(),
                                   catalog_evidence=object(), edge_choice=None)
    candidates = [(0, "pad", e, e["points"], object()) for e in entries]
    return picker, candidates


def test_requires_explicit_post_release_selection_and_consumes_once():
    picker, candidates = fixture()
    choice = picker.edge_choice = M.EdgeChoice(picker, candidates)
    assert choice.selected is None
    with pytest.raises(ValueError, match="before Apply"):
        choice.consume(picker)
    with pytest.raises(ValueError, match="explicitly"):
        choice.select(picker, 0)
    choice.released = True
    choice.select(picker, 1)
    assert choice.consume(picker) == ("pad", candidates[1][2])
    with pytest.raises(ValueError, match="expired"):
        choice.consume(picker)


@pytest.mark.parametrize("change", ["owner", "copy", "token", "evidence", "retire", "replace"])
def test_owner_generation_copy_and_retirement_refuse(change):
    picker, candidates = fixture()
    choice = picker.edge_choice = M.EdgeChoice(picker, candidates)
    choice.released = True
    if change == "owner":
        picker = copy.copy(picker)
    elif change == "copy":
        choice = copy.copy(choice)
    elif change == "token":
        picker.catalog_token = object()
    elif change == "evidence":
        picker.catalog_evidence = object()
    elif change == "retire":
        choice.retired = True
    else:
        picker.edge_choice = object()
    with pytest.raises(ValueError, match="expired"):
        choice.select(picker, 0)


def test_freeze_is_detached_and_exact_catalog_identity_is_mandatory():
    picker, candidates = fixture()
    choice = M.EdgeChoice(picker, candidates)
    raw = choice.rows[0][1]
    candidates[0][2]["points"][0][0] = 999
    assert choice.rows[0][1] == raw
    assert json.loads(raw)["points"][0][0] == 0
    picker.catalog["pad"].append(copy.deepcopy(candidates[0][2]))
    with pytest.raises(ValueError, match="unique topology"):
        M.freeze_candidates(candidates, picker.catalog)


def test_invalid_endpoint_overlap_is_not_a_menu_option():
    picker, candidates = fixture()
    candidates[0][2].pop("endpoint_faces")
    with pytest.raises(ValueError, match="stable endpoints"):
        M.freeze_candidates(candidates, picker.catalog)


def test_overflow_never_truncates_and_duplicate_identity_never_lists():
    picker, candidates = fixture(7)
    with pytest.raises(ValueError, match="Zoom"):
        M.freeze_candidates(candidates, picker.catalog)
    picker, candidates = fixture()
    with pytest.raises(ValueError, match="unique topology"):
        M.freeze_candidates([candidates[0], candidates[0]], picker.catalog)


@pytest.mark.parametrize("kind", ["Line", "Circle", "Arc"])
def test_all_supported_curve_types(kind):
    picker, candidates = fixture()
    if kind != "Line":
        for e in picker.catalog["pad"]:
            e[kind.lower()] = {"endpoint_faces": [["a"], ["b"]]}
    assert M.projection_kind(candidates[0][2]) == kind
    assert len(M.freeze_candidates(candidates, picker.catalog)) == 2


def label_rows(specs):
    return tuple((source, json.dumps({"faces": faces, "points": [[0, 0, 0], [1, 0, 0]], "endpoint_faces": [["a"], ["b"]], **curve}))
                 for source, faces, curve in specs)


def test_compact_labels_keep_cap_context_and_remove_redundant_raw_ids():
    labels = importlib.import_module(PACKAGE + ".projection_edge_choice_labels")
    rows = label_rows([
        ("pad", ["pad/face/cap.end", "pad/face/side.arc.a_19"], {"arc": {}}),
        ("pad", ["pad/face/cap.end", "pad/face/side.line.l_6"], {}),
        ("pad", ["pad/face/cap.start", "pad/face/side.arc.a_19"], {"arc": {}}),
    ])
    assert labels.choice_labels(rows, '{"features":[{"id":"pad","label":"Pad"}]}') == [
        ("Pad · Arc", "End cap · Curved side"),
        ("Pad · Line", "End cap · Straight side"),
        ("Pad · Arc", "Start cap · Curved side"),
    ]


def test_colliding_friendly_labels_expose_full_frozen_identity():
    labels = importlib.import_module(PACKAGE + ".projection_edge_choice_labels")
    rows = label_rows([
        ("pad", ["pad/face/cap.end", f"pad/face/side.arc.{key}"], {"arc": {}})
        for key in ("a_19", "a_20")])
    result = labels.choice_labels(rows, '{"features":[{"id":"pad","label":"Pad"}]}')
    assert result[0][0] == result[1][0] == "Pad · Arc"
    for row, (_, raw) in zip(result, rows, strict=True):
        assert all(face in row[1] for face in json.loads(raw)["faces"])
    assert result[0][1] != result[1][1]


def test_compact_layout_preserves_disjoint_mouse_targets_and_all_text(monkeypatch):
    for name in ("blf", "gpu", "gpu_extras"):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    batch = types.ModuleType("gpu_extras.batch")
    batch.batch_for_shader = None
    monkeypatch.setitem(sys.modules, "gpu_extras.batch", batch)
    draw = importlib.import_module(PACKAGE + ".projection_edge_choice_draw")
    rows = label_rows([
        ("pad", ["pad/face/cap.end", "pad/face/side.arc.a_19"], {"arc": {}}),
        ("pad", ["pad/face/cap.end", "pad/face/side.line.l_6"], {}),
    ])
    picker = types.SimpleNamespace(
        region=types.SimpleNamespace(width=1200, height=800),
        edge_choice=types.SimpleNamespace(rows=rows),
        base='{"features":[{"id":"pad","label":"Pad"}]}')
    bounds, apply, cancel, labels = draw.prepare_layout(picker)
    assert bounds[0][2] - bounds[0][0] == 336
    assert all(len(lines) == 2 for lines in labels)
    assert bounds[1][3] == bounds[0][1]
    assert apply[3] < bounds[-1][1]
    assert apply[2] < cancel[0] < cancel[2] <= bounds[0][2]
    picker.region.width = 380
    with pytest.raises(ValueError, match="Enlarge"):
        draw.prepare_layout(picker)
