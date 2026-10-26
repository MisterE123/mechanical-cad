"""Detached finite arc frame tests; graphics are sentinels, never native execution."""

import copy
import importlib
import math
import subprocess
import sys
import types
from dataclasses import replace

import pytest
from test_general_view_geometry import ROOT, arc_sketch, g, geometry, placement, projection, sketch


@pytest.fixture
def overlay(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("Frame construction must not call graphics or native code")

    for name in ("blf", "gpu", "gpu_extras", "gpu_extras.batch"):
        module = types.ModuleType(name)
        module.__getattr__ = lambda _name: forbidden
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setattr(
        sys.modules["gpu_extras.batch"], "batch_for_shader", forbidden, raising=False
    )
    name = g.__package__ + ".general_sketch_overlay"
    monkeypatch.delitem(sys.modules, name, raising=False)
    return importlib.import_module(name)


def proposal(*, phase="end", observed=(0, 70), direction="ccw"):
    return {
        "kind": "arc",
        "phase": phase,
        "center": {"kind": "new", "position": [0, 0]},
        "start": None if phase == "start" else {"kind": "new", "position": [50, 0]},
        "observation": None if observed is None else {"kind": "new", "position": list(observed)},
        "direction": direction,
    }


def blank():
    source = arc_sketch()
    source.update(points=[], arcs=[], constraints=[])
    return geometry(source)


def test_authored_arc_frame_reuses_sampler_and_keeps_raw_end_discrepancy_visible(overlay):
    source = arc_sketch(radius=50, end_radius=70)
    before = copy.deepcopy(source)
    selected = geometry(source)
    frame = overlay.build_frame(selected, projection, selection=[{"kind": "arc", "id": "arc"}])
    sampler = g._Projection(selected.plane, projection, g.MAX_PROJECT_CALLS)
    segments, _, issues = g._curve_segments(selected.arcs["arc"], sampler, 0.5, 512)
    stroke = next(item for item in frame.strokes if item.kind == "arc")
    assert stroke.segments == tuple(segments) and stroke.selected and not issues
    gap = next(item for item in frame.strokes if item.kind == "arc_discrepancy")
    assert gap.segments[0][0] == g._arc_point(selected.arcs["arc"], 1)
    assert gap.segments[0][1] == selected.points["end"]
    end = next(item for item in frame.markers if item.identifier == "end")
    assert end.position == selected.points["end"] and end.role == "Raw end"
    assert frame.arc_labels[0].text == "CCW (local UV) +90° · minor"
    assert frame.arc_labels[0].selected
    assert (
        frame.arc_labels[0].detail
        == "Provisional until Check · support R 50 mm · raw end radius Δ +20 mm"
    )
    assert source == before and not frame.unavailable


@pytest.mark.parametrize(
    "direction,sweep,meaning",
    [
        ("ccw", 90, "minor"),
        ("ccw", 180, "semicircle"),
        ("ccw", 270, "major"),
        ("cw", -90, "minor"),
        ("cw", -180, "semicircle"),
        ("cw", -270, "major"),
    ],
)
def test_arc_direction_signed_sweep_meaning_and_camera_flip_are_local(
    overlay, direction, sweep, meaning
):
    source = arc_sketch(sweep_degrees=sweep)
    selected = geometry(source)
    frame = overlay.build_frame(selected, lambda world: (-world[0], world[1]))
    assert frame.arc_labels[0].text == f"{direction.upper()} (local UV) {sweep:+}° · {meaning}"
    assert "Provisional until Check" in frame.arc_labels[0].detail
    assert all(item.kind != "circle" for item in frame.strokes)


def test_arc_radius_annotation_uses_measured_radius_and_unchanged_layout(overlay):
    source = arc_sketch(radius=50, end_radius=70)
    annotations = {"radius": placement("radius", ["arc"], [0, 0])}
    before = copy.deepcopy((source, annotations))
    frame = overlay.build_frame(geometry(source), projection, annotations=annotations)
    assert frame.labels[0].measured_mm == 50
    assert frame.labels[0].text == "R ~50 mm"
    assert frame.labels[0].raw_value == "size / 2"
    assert frame.labels[0].position == (0, 0)
    leader = next(item for item in frame.strokes if item.kind == "constraint")
    assert leader.segments[0][1] == pytest.approx((50 / math.sqrt(2), 50 / math.sqrt(2)))
    assert (source, annotations) == before


@pytest.mark.parametrize(
    "phase,observation,roles",
    [
        ("start", None, {"Center"}),
        ("start", (50, 0), {"Center", "Observed start"}),
        ("end", None, {"Center", "Start"}),
        ("end", (0, 70), {"Center", "Start", "Observed end"}),
    ],
)
def test_arc_proposal_stages_preserve_every_raw_observation(overlay, phase, observation, roles):
    data = proposal(phase=phase, observed=observation)
    before = copy.deepcopy(data)
    frame = overlay.build_frame(blank(), projection, proposal=data)
    assert {item.role for item in frame.markers} == roles
    assert all(item.proposal for item in (*frame.markers, *frame.strokes, *frame.arc_labels))
    assert "Provisional" in frame.arc_labels[0].detail
    arcs = [item for item in frame.strokes if item.kind == "arc"]
    assert bool(arcs) == (phase == "end" and observation is not None)
    if arcs:
        assert arcs[0].segments[-1][-1] == pytest.approx((0, 50))
        assert next(item for item in frame.markers if item.role == "Observed end").position == (
            0,
            70,
        )
        assert any(item.kind == "arc_discrepancy" for item in frame.strokes)
    assert data == before and not frame.unavailable


def test_existing_point_proposal_uses_exact_source_positions_and_missing_refs_stay_unavailable(
    overlay,
):
    selected = geometry(arc_sketch(end_radius=70))
    data = proposal()
    for role, identifier in (("center", "center"), ("start", "start"), ("observation", "end")):
        data[role] = {"kind": "existing", "point_id": identifier}
    frame = overlay.build_frame(selected, projection, proposal=data)
    end = next(item for item in frame.markers if item.identifier == "preview_observation")
    assert end.position == selected.points["end"]
    data["observation"]["point_id"] = "missing"
    before = copy.deepcopy(data)
    frame = overlay.build_frame(selected, projection, proposal=data)
    assert any(issue.reason == "observation_unavailable" for issue in frame.unavailable)
    assert not any(item.kind == "arc" and item.proposal for item in frame.strokes)
    assert data == before


@pytest.mark.parametrize("observed", [(0, 0), (50, 0)])
def test_invalid_arc_observation_is_visible_and_unmodified_without_valid_stroke(overlay, observed):
    data = proposal(observed=observed)
    before = copy.deepcopy(data)
    frame = overlay.build_frame(blank(), projection, proposal=data)
    assert (
        next(item for item in frame.markers if item.identifier == "preview_observation").position
        == observed
    )
    assert any(issue.reason in {"invalid_number", "degenerate_arc"} for issue in frame.unavailable)
    assert not any(item.kind == "arc" for item in frame.strokes)
    assert "no checked sweep" in frame.arc_labels[0].detail and data == before


@pytest.mark.parametrize(
    "change",
    [
        {"unexpected": 1},
        {"phase": "center"},
        {"phase": True},
        {"direction": "CCW"},
        {"start": None},
        {"center": {"kind": "new", "position": [float("nan"), 0]}},
        {"observation": {"kind": "existing", "point_id": "end", "extra": 1}},
    ],
)
def test_malformed_arc_proposals_reject_without_repair(overlay, change):
    data = proposal()
    data.update(change)
    with pytest.raises(ValueError):
        overlay.build_frame(blank(), projection, proposal=data)


def test_arc_selection_missing_binding_remains_visible(overlay):
    frame = overlay.build_frame(blank(), projection, selection=[{"kind": "arc", "id": "missing"}])
    assert frame.unavailable == (g.ProjectionIssue("arc", "missing", "selection_unavailable"),)


def test_all_arc_circle_line_proposal_annotation_work_shares_projection_and_output_caps(overlay):
    source = arc_sketch()
    source["circles"] = [{"id": "circle", "center": "center", "radius": 5}]
    source["lines"] = [{"id": "line", "start": "center", "end": "start"}]
    selected = geometry(source)
    calls = []
    frame = overlay.build_frame(
        selected,
        lambda world: calls.append(world) or world[:2],
        proposal=proposal(),
        annotations={"radius": placement("radius", ["arc"], [0, 60])},
        max_project_calls=40,
        max_segments=10,
    )
    assert len(calls) == frame.projection_calls == 40
    assert sum(len(item.segments) for item in frame.strokes) <= 10
    assert {issue.reason for issue in frame.unavailable} >= {"segment_budget", "projection_budget"}
    refined = overlay.build_frame(selected, projection, circle_error_px=1e-6, max_circle_segments=8)
    assert any(
        issue.kind == "arc" and issue.reason == "refinement_budget" for issue in refined.unavailable
    )
    invisible = overlay.build_frame(selected, lambda world: None, proposal=proposal())
    assert not invisible.strokes and not invisible.markers and not invisible.arc_labels
    assert any(
        issue.kind == "arc" and issue.reason == "invisible_span" for issue in invisible.unavailable
    )


def test_synthetic_solved_display_currency_and_retained_provisional_meaning(overlay):
    # Detached display formatting only; this fixture creates no owner/solver evidence.
    authored = geometry(arc_sketch())
    solved = replace(authored, source="solved", request_fingerprint="display-fixture")
    with pytest.raises(ValueError):
        overlay.build_frame(solved, projection)
    current = overlay.build_frame(
        solved, projection, current_request_fingerprint="display-fixture",
        selection=[{"kind": "arc", "id": "arc"}],
    )
    assert current.arc_labels[0].detail == "R 50 mm"
    assert "Provisional" not in current.arc_labels[0].detail
    retained = overlay.build_frame(g.retained_outline(solved), projection)
    assert retained.request_fingerprint is None
    assert retained.arc_labels[0].detail.startswith("Provisional until Check · ")
    with_proposal = overlay.build_frame(
        solved, projection, current_request_fingerprint="display-fixture", proposal=proposal()
    )
    assert next(item for item in with_proposal.arc_labels if item.proposal).detail.startswith(
        "Provisional until Check"
    )


def test_legacy_circle_frames_and_proposals_remain_complete_without_arc_labels(overlay):
    frame = overlay.build_frame(
        geometry(sketch()),
        projection,
        proposal={"kind": "circle", "anchor": {"kind": "new", "position": [60, 15]}, "radius": 10},
    )
    assert not frame.unavailable and not frame.arc_labels
    assert all(item.role is None for item in frame.markers)
    assert any(item.kind == "circle" and item.proposal for item in frame.strokes)


def test_fresh_arc_build_pick_frame_import_no_native_or_core_modules():
    script = f"""
import importlib, importlib.abc, sys, types
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {{'mechanical_cad', 'bpy', 'mathutils', 'slvs', 'OCP'}}:
            raise AssertionError('Forbidden native/core import: ' + fullname)
sys.meta_path.insert(0, Block())
for name in ('blf', 'gpu', 'gpu_extras', 'gpu_extras.batch'):
    sys.modules[name] = types.ModuleType(name)
def forbidden(*args, **kwargs):
    raise AssertionError('Frame touched graphics/native code')
sys.modules['gpu_extras.batch'].batch_for_shader = forbidden
package = types.ModuleType('isolated_arc_overlay')
package.__path__ = [{str(ROOT / "blender_addon/mechanical_cad_blender")!r}]
sys.modules[package.__name__] = package
view = importlib.import_module(package.__name__ + '.general_view_geometry')
overlay = importlib.import_module(package.__name__ + '.general_sketch_overlay')
selected = view.build_geometry({arc_sketch(end_radius=70)!r}, source='authored')
frame = overlay.build_frame(selected, lambda world: world[:2], proposal={proposal()!r})
assert frame.arc_labels and any(stroke.kind == 'arc_discrepancy' for stroke in frame.strokes)
assert view.pick_geometry(selected, (50, 0), lambda world: world[:2], kinds=('arc',)).unique
print('NATIVE_FREE_ARC_FRAME_OK')
"""
    run = subprocess.run(
        [sys.executable, "-B", "-c", script], capture_output=True, text=True, check=True
    )
    assert "NATIVE_FREE_ARC_FRAME_OK" in run.stdout


def test_arc_drawing_roles_labels_and_discrepancy_use_no_dimension_hitbox_or_native_calls(
    overlay, monkeypatch
):
    state = {"blend": "ADDITIVE", "depth_test": "LESS_EQUAL", "depth_mask": True, "line_width": 2.0}
    original = state.copy()
    fake_state = types.SimpleNamespace()
    for key in state:
        setattr(fake_state, key + "_get", lambda key=key: state[key])
        setattr(fake_state, key + "_set", lambda value, key=key: state.update({key: value}))
    colors, drawn = [], []
    shader = types.SimpleNamespace(
        bind=lambda: None, uniform_float=lambda _key, color: colors.append(color)
    )
    monkeypatch.setattr(overlay.gpu, "state", fake_state, raising=False)
    monkeypatch.setattr(
        overlay.gpu,
        "shader",
        types.SimpleNamespace(from_builtin=lambda _name: shader),
        raising=False,
    )
    monkeypatch.setattr(
        overlay, "batch_for_shader", lambda *_args: types.SimpleNamespace(draw=lambda _shader: None)
    )
    for name in ("size", "position", "color"):
        monkeypatch.setattr(overlay.blf, name, lambda *_args: None, raising=False)
    monkeypatch.setattr(
        overlay.blf, "dimensions", lambda _font, text: (len(text) * 5, 12), raising=False
    )
    monkeypatch.setattr(overlay.blf, "draw", lambda _font, text: drawn.append(text), raising=False)
    frame = overlay.build_frame(
        geometry(arc_sketch(end_radius=70)),
        projection,
        annotations={"radius": placement("radius", ["arc"], [0, 60])},
        proposal=proposal(),
    )
    boxes = overlay.draw_frame(frame, usable_rect=(0, 0, 1000, 800))
    assert len(boxes) == 1 and boxes[0][0] == "radius"
    assert {"Center", "Start", "Raw end", "Observed end"} <= set(drawn)
    assert all(label.text in drawn and label.detail in drawn for label in frame.arc_labels)
    assert overlay.ERROR in colors and overlay.PROPOSAL in colors
    assert state == original
    drawn.clear()
    assert overlay.draw_frame(frame, usable_rect=(0, 0, 10, 10)) == ()
    assert not drawn and state == original

    solved = replace(
        geometry(arc_sketch()), source="solved", request_fingerprint="display-fixture"
    )
    options = {
        "current_request_fingerprint": "display-fixture",
        "annotations": {"radius": placement("radius", ["arc"], [0, 60])},
    }
    quiet = overlay.build_frame(solved, projection, **options)
    drawn.clear()
    quiet_boxes = overlay.draw_frame(
        quiet, current_request_fingerprint="display-fixture", usable_rect=(0, 0, 1000, 800)
    )
    assert [identifier for identifier, _ in quiet_boxes] == ["radius"]
    assert not {"Center", "Start", "End"}.intersection(drawn)
    assert not any("local UV" in text or "support R" in text for text in drawn)
    assert "Current solved sketch" in drawn and quiet.labels[0].text in drawn
    detailed = overlay.build_frame(
        solved, projection, selection=[{"kind": "point", "id": "end"}], **options
    )
    drawn.clear()
    assert overlay.draw_frame(
        detailed, current_request_fingerprint="display-fixture", usable_rect=(0, 0, 1000, 800)
    ) == quiet_boxes
    assert {"Center", "Start", "End"} <= set(drawn)
    assert detailed.arc_labels[0].text in drawn and state == original

    # Actual draw layout at tiny projected radii, including viewport-edge clamping.
    caption_bounds = []
    place_caption = overlay._caption_bounds

    def record_caption(*args):
        bounds = place_caption(*args)
        caption_bounds.append(bounds)
        return bounds

    monkeypatch.setattr(overlay, "_caption_bounds", record_caption)
    for scale in (0.75, 1.0, 2.0):
        for center in ((200, 200), (10, 10), (950, 790)):
            tiny = replace(
                geometry(arc_sketch(radius=2)), source="solved",
                request_fingerprint="display-fixture",
            )
            tiny_frame = overlay.build_frame(
                tiny, lambda world, center=center: (world[0] + center[0], world[1] + center[1]),
                selection=[{"kind": "arc", "id": "arc"}], **options,
            )
            before = copy.deepcopy(tiny_frame)
            caption_bounds.clear()
            drawn.clear()
            boxes = overlay.draw_frame(
                tiny_frame, current_request_fingerprint="display-fixture",
                usable_rect=(0, 0, 1000, 800), scale=scale,
            )
            assert tiny_frame == before and state == original
            assert len(caption_bounds) == 4  # Three roles and one diagnostic.
            assert {"Center", "Start", "End"} <= set(drawn)
            assert "R 2 mm" in drawn
            for index, bounds in enumerate(caption_bounds):
                x, y, right, top = bounds
                assert 0 <= x < right <= 1000 and 0 <= y < top <= 800
                marker_boxes = [
                    (m.position[0] - 6 * scale, m.position[1] - 6 * scale,
                     m.position[0] + 6 * scale, m.position[1] + 6 * scale)
                    for m in tiny_frame.markers
                ]
                others = caption_bounds[:index] + [box for _, box in boxes] + marker_boxes
                assert not any(x < b[2] and right > b[0] and y < b[3] and top > b[1]
                               for b in others)
            dimension = overlay._label_bounds(tiny_frame.labels[0], 0, scale, (0, 0, 1000, 800))
            assert boxes == (("radius", dimension),)

    # Selected arc placement must not move active construction proposal captions.
    mixed = overlay.build_frame(
        solved, projection, proposal=proposal(),
        selection=[{"kind": "arc", "id": "arc"}], **options,
    )
    assert all(not marker.contextual for marker in mixed.markers if marker.proposal)
    assert all(not label.contextual for label in mixed.arc_labels if label.proposal)
    unrelated = overlay.ArcLabel("warning", (300, 300), "Unrelated discrepancy", "Keep visible")
    mixed = replace(mixed, arc_labels=(*mixed.arc_labels, unrelated))
    caption_bounds.clear()
    overlay.draw_frame(
        mixed, current_request_fingerprint="display-fixture", usable_rect=(0, 0, 1000, 800)
    )
    assert len(caption_bounds) == 4  # Only the selected arc's roles and diagnostic move.

    def failed_batch(*_args, **_kwargs):
        raise RuntimeError("Injected drawing failure")

    monkeypatch.setattr(overlay, "batch_for_shader", failed_batch)
    with pytest.raises(RuntimeError, match="Injected"):
        overlay.draw_frame(frame)
    assert state == original


@pytest.mark.parametrize("fillet", [False, True])
def test_current_solved_arcs_quiet_until_arc_or_defining_point_selected(overlay, fillet):
    authored = geometry(arc_sketch())
    arcs = types.MappingProxyType({"arc": replace(authored.arcs["arc"], corner_fillet=fillet)})
    solved = replace(authored, arcs=arcs, source="solved", request_fingerprint="display-fixture")
    options = {
        "current_request_fingerprint": "display-fixture",
        "annotations": {"radius": placement("radius", ["arc"], [0, 60])},
    }
    quiet = overlay.build_frame(solved, projection, **options)
    assert not quiet.arc_labels and all(item.role is None for item in quiet.markers)
    assert len(quiet.markers) == len(solved.points)
    assert quiet.labels[0].constraint_id == "radius" and quiet.labels[0].text == "R 50 mm"
    assert not quiet.unavailable
    for selection in (
        [{"kind": "arc", "id": "arc"}],
        *([{"kind": "point", "id": role}] for role in ("center", "start", "end")),
    ):
        detailed = overlay.build_frame(solved, projection, selection=selection, **options)
        assert {item.role for item in detailed.markers} == {"Center", "Start", "End"}
        assert len(detailed.arc_labels) == (0 if fillet else 1)
        if not fillet:
            assert detailed.arc_labels[0].detail == "R 50 mm"
        assert detailed.labels == quiet.labels
        assert [(s.kind, s.identifier, s.segments) for s in detailed.strokes] == [
            (s.kind, s.identifier, s.segments) for s in quiet.strokes
        ]
        assert [(m.identifier, m.position) for m in detailed.markers] == [
            (m.identifier, m.position) for m in quiet.markers
        ]
    assert overlay.build_frame(solved, projection, **options) == quiet


def test_solved_discrepancy_and_incomplete_projection_are_never_silenced(overlay):
    # Synthetic display records only; do not claim a real solver produced this gap.
    solved = replace(
        geometry(arc_sketch(end_radius=70)), source="solved", request_fingerprint="display-fixture"
    )
    frame = overlay.build_frame(solved, projection, current_request_fingerprint="display-fixture")
    assert frame.arc_labels and "Δ +20 mm" in frame.arc_labels[0].detail
    assert {item.role for item in frame.markers} == {"Center", "Start", "End"}
    assert any(item.kind == "arc_discrepancy" for item in frame.strokes)
    equal = replace(
        geometry(arc_sketch()), source="solved", request_fingerprint="display-fixture"
    )
    missing = overlay.build_frame(
        equal, lambda world: None, current_request_fingerprint="display-fixture"
    )
    assert missing.unavailable and not missing.arc_labels
    assert any(item.reason == "invisible_span" for item in missing.unavailable)


@pytest.mark.parametrize("radius", [0.01, 50])
@pytest.mark.parametrize("multiple,visible", [(0.5, False), (2, True)])
def test_solved_arc_caption_discrepancy_uses_shared_absolute_relative_policy(
    overlay, radius, multiple, visible
):
    limit = min(overlay.MAX_ARC_RADIUS_RESIDUAL_MM,
                overlay.MAX_ARC_RADIUS_RELATIVE_RESIDUAL * radius)
    solved = replace(
        geometry(arc_sketch(radius=radius, end_radius=radius + multiple * limit)),
        source="solved", request_fingerprint="display-fixture",
    )
    frame = overlay.build_frame(solved, projection, current_request_fingerprint="display-fixture")
    assert bool(frame.arc_labels) is visible
    assert all(bool(marker.role) is visible for marker in frame.markers)
    # Presentation tolerance never suppresses or rewrites original gap geometry.
    assert any(stroke.kind == "arc_discrepancy" for stroke in frame.strokes)


def test_caption_layout_has_fixed_attempt_budget_and_preserves_no_space_fallback(overlay, monkeypatch):
    calls = []
    clamp = overlay._clamp_box

    def counted(*args):
        calls.append(args)
        return clamp(*args)

    monkeypatch.setattr(overlay, "_clamp_box", counted)
    # Cover all slots, including clamped edges: explanatory text is never deleted.
    occupied = [(0, index * 10, 1000, index * 10 + 8) for index in range(100)]
    result = overlay._caption_bounds((20, 500), 120, 41, 1, (0, 0, 1000, 800), occupied)
    assert result == (20, 500, 140, 541)
    assert len(calls) <= 33  # Initial clamp plus at most 16 attempts each direction.


@pytest.mark.parametrize("construction", [False, True])
def test_selected_solved_arc_omits_roundoff_but_keeps_radius_sweep_and_reference_truth(
    overlay, construction
):
    authored = geometry(arc_sketch(radius=2, end_radius=2 - 1e-15))
    arcs = types.MappingProxyType({
        "arc": replace(authored.arcs["arc"], construction=construction),
    })
    solved = replace(authored, arcs=arcs, source="solved", request_fingerprint="display-fixture")
    frame = overlay.build_frame(
        solved, projection, current_request_fingerprint="display-fixture",
        selection=[{"kind": "arc", "id": "arc"}],
    )
    assert frame.arc_labels[0].text == "CCW (local UV) +90° · minor"
    assert frame.arc_labels[0].detail == (
        "R 2 mm · construction reference" if construction else "R 2 mm"
    )
    assert "Δ" not in frame.arc_labels[0].detail
    assert "raw" not in frame.arc_labels[0].detail
    assert any(stroke.kind == "arc_discrepancy" for stroke in frame.strokes)
