"""Selected authored H/V badges are presentation, never solve/pick authority."""
# ruff: noqa: F811
import copy
from dataclasses import replace

import pytest
from test_arc_overlay_geometry import overlay  # noqa: F401
from test_general_view_geometry import geometry, projection, sketch


def fixture():
    source = sketch()
    source['constraints'] += [{'id': 'h', 'kind': 'horizontal', 'refs': ['line']}]
    return source


def test_selected_only_and_authored_not_inferred(overlay):
    source = fixture()
    before = copy.deepcopy(source)
    frame = overlay.build_frame(geometry(source), projection)
    assert frame.axis_badges == ()
    frame = overlay.build_frame(geometry(source), projection,
                                selection=[{'kind': 'line', 'id': 'line'}])
    badge, = frame.axis_badges
    assert badge.text == 'H Horizontal · authored'
    assert badge.constraint_ids == ('h',) and badge.line_id == 'line'
    assert badge.position == (15, 20)  # Diagonal unsolved seeds do not imply success.
    assert not frame.labels and source == before
    source['constraints'] = []
    source['points'][1]['v'] = 0
    assert not overlay.build_frame(geometry(source), projection,
        selection=[{'kind': 'line', 'id': 'line'}]).axis_badges


def test_multiple_relations_combine_without_mutation(overlay):
    source = fixture()
    source['constraints'] += [
        {'id': 'h2', 'kind': 'horizontal', 'refs': ['line']},
        {'id': 'v', 'kind': 'vertical', 'refs': ['line']},
    ]
    before = copy.deepcopy(source)
    frame = overlay.build_frame(geometry(source), projection,
        selection=[{'kind': 'line', 'id': 'line'}])
    badge, = frame.axis_badges
    assert badge.text == 'H Horizontal / V Vertical · authored'
    assert badge.constraint_ids == ('h', 'h2', 'v')
    assert source == before
    with pytest.raises(TypeError):
        geometry(source).axis_relations['new'] = ('horizontal', 'line')


def test_unavailable_projection_and_non_line_selection_are_quiet(overlay):
    selected = [{'kind': 'line', 'id': 'line'}]
    assert not overlay.build_frame(geometry(fixture()), lambda _: None,
                                   selection=selected).axis_badges
    assert not overlay.build_frame(geometry(fixture()), projection,
        selection=[{'kind': 'point', 'id': 'a'}]).axis_badges


def test_currency_guard_and_retained_intent(overlay):
    source = geometry(fixture())
    selection = [{'kind': 'line', 'id': 'line'}]
    # Synthetic detached currency record tests renderer guard, NOT native solve.
    solved = replace(source, source='solved', request_fingerprint='test-current')
    with pytest.raises(ValueError, match='current request fingerprint'):
        overlay.build_frame(solved, projection, selection=selection)
    frame = overlay.build_frame(solved, projection, selection=selection,
                                current_request_fingerprint='test-current')
    assert frame.axis_badges[0].text.endswith('authored')
    retained = replace(source, source='retained')
    assert overlay.build_frame(retained, projection, selection=selection).axis_badges


def test_crowded_selected_badges_avoid_dimensions_and_each_other(overlay):
    occupied = [(112, 114, 292, 134)]  # Existing dimension hit box at first offset.
    dimension_bounds = tuple(occupied)
    first = overlay._axis_badge_bounds((100, 100), 180, 1, (0, 0, 500, 400), occupied)
    assert first == (112, 66, 292, 86)
    occupied.append(first)
    second = overlay._axis_badge_bounds((100, 100), 180, 1, (0, 0, 500, 400), occupied)
    assert second == (112, 138, 292, 158)
    occupied.append(second)
    assert overlay._axis_badge_bounds((100, 100), 180, 1, (0, 0, 500, 400), occupied) is None
    assert tuple(occupied[:1]) == dimension_bounds
    assert overlay._axis_badge_bounds((100, 100), 180, 1, (0, 0, 100, 400), []) is None
    assert overlay._axis_badge_bounds((100, 100), 180, 1, (0, 0, 500, 15), []) is None
