"""A synchronous panel shares immutable display values, not action authority."""
from dataclasses import FrozenInstanceError, replace

import pytest
from test_feature_history_draw import Layout, count_proofs, first_row
from test_feature_history_draw import draw as _draw
from test_feature_history_draw import host as _host

host = _host
draw = _draw


def test_status_history_and_details_share_exactly_one_proof(host, draw, monkeypatch):
    count = count_proofs(host, monkeypatch)
    state = host.context.scene.mechanical_cad
    state.feature_index = 0
    presentation = draw.capture_presentation(host.context)
    assert presentation.is_current(host.context)
    detail = presentation.selected_detail(host.context, state.features[0].feature_id)
    assert detail.status == "ok" and detail.sketch_label is not None
    assert presentation.volume_text(host.context).startswith("Volume: ")
    shown = []
    draw.draw_history(Layout(lambda: shown.append(first_row(draw, host))), host.context,
                      "", rows=7, presentation=presentation)
    assert shown == [("CHECKMARK", False)] and count == [1]
    assert not draw._SCOPES
    assert host.doc.current_part_result(host.context)
    assert len(count) == 2
    assert draw.capture_presentation(host.context).is_current(host.context)
    assert len(count) == 3
    with pytest.raises(FrozenInstanceError):
        detail.status = "forged"


@pytest.mark.parametrize("mutation", ["document", "status", "owner", "scale", "epoch", "record", "revoked", "bytes"])
def test_every_consumer_refuses_stale_panel_presentation(host, draw, mutation):
    state = host.context.scene.mechanical_cad
    state.feature_index = 0
    feature_id = state.features[0].feature_id
    presentation = draw.capture_presentation(host.context)
    record = host.doc._RUNTIME[host.doc._scene_key(host.context.scene)]
    if mutation == "document":
        state.document_json += " "
    elif mutation == "status":
        state.status = "DIRTY"
    elif mutation == "owner":
        state.owner_id += "changed"
    elif mutation == "scale":
        host.context.scene.unit_settings.scale_length *= 2
    elif mutation == "epoch":
        host.current[0] = replace(host.current[0], generation=host.current[0].generation + 1)
    elif mutation == "revoked":
        record["evidence"].publication._state = "cancelled"
    elif mutation == "bytes":
        object.__setattr__(record["evidence"], "_response_payload", b"{}")
    else:
        host.doc._RUNTIME.pop(host.doc._scene_key(host.context.scene))
    assert not presentation.is_current(host.context)
    assert presentation.selected_detail(host.context, feature_id) is None
    assert presentation.volume_text(host.context) is None
    shown = []
    draw.draw_history(Layout(lambda: shown.append(first_row(draw, host))), host.context,
                      "", rows=7, presentation=presentation)
    assert shown == [("DOT", False)]


def test_selected_feature_change_during_guard_cannot_show_wrong_details(host, draw, monkeypatch):
    state = host.context.scene.mechanical_cad
    state.feature_index = 0
    presentation = draw.capture_presentation(host.context)
    feature_id = state.features[0].feature_id
    original = host.modules.backend_runtime.assert_current
    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        state.feature_index = 1
        return result
    monkeypatch.setattr(host.modules.backend_runtime, "assert_current", changed)
    assert presentation.selected_detail(host.context, feature_id) is None


def test_display_values_match_existing_labels(host, draw):
    from importlib import import_module
    compact = import_module(host.doc.__package__ + ".compact_status")
    state = host.context.scene.mechanical_cad
    result = host.doc.current_part_result(host.context)
    presentation = draw.capture_presentation(host.context)
    for index, source in enumerate(state.features):
        state.feature_index = index
        expected = next(row for row in result["features"] if row["id"] == source.feature_id)
        detail = presentation.selected_detail(host.context, source.feature_id)
        assert detail.status == expected["status"]
        report = expected.get("sketch")
        assert detail.sketch_label == (compact.sketch_label(report) if report is not None else None)
    active = next(row for row in result["features"] if row["id"] == result["active_feature"])
    volume = (active.get("stats") or {}).get("volume", 0.0)
    assert presentation.volume_text(host.context) == f"Volume: {volume:,.3f} mm³"


@pytest.mark.parametrize("status,icon,prefix", [
    ("redundant_okay", "INFO", "Redundancy candidates: "),
    ("inconsistent", "ERROR", "Conflict candidates: "),
])
def test_failed_detail_presentation_preserves_original_severity(host, draw, monkeypatch, status, icon, prefix):
    original = host.doc._runtime_projection
    def presentation_fixture(*args, **kwargs):
        projection = original(*args, **kwargs)
        projection[1]["result"]["features"][0]["sketch"].update(
            status=status, failed_constraints=["c1", "c2"], redundant_constraints=["c3"])
        return projection
    monkeypatch.setattr(host.doc, "_runtime_projection", presentation_fixture)
    state = host.context.scene.mechanical_cad
    state.feature_index = 0
    presentation = draw.capture_presentation(host.context)
    detail = presentation.selected_detail(host.context, state.features[0].feature_id)
    assert detail.failed_detail == prefix + "c1, c2"
    assert detail.failed_detail_icon == icon
    assert detail.redundant_detail == "Redundant constraints: c3"
