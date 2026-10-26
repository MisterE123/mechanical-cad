"""Radius intent never applies diameter conversion or hidden local drafts."""

import copy
import importlib.util
import sys
import types
from pathlib import Path

import pytest

root = Path(__file__).resolve().parents[2] / 'blender_addon/mechanical_cad_blender'
package = types.ModuleType('radius_edit_test')
package.__path__ = [str(root)]
sys.modules[package.__name__] = package
spec = importlib.util.spec_from_file_location(package.__name__ + '.parameter_radius_edit', root / 'parameter_radius_edit.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


@pytest.fixture(params=['sketch_circle', 'sketch_face_circle'])
def document(request):
    return {'parameters': {'hole_radius': 4, 'other': 'hole_radius * 2'}, 'features': [
        {'id': 'circle', 'kind': request.param, 'label': 'Circle', 'params': {'radius': 'hole_radius', 'x': 0}, 'inputs': {}},
        {'id': 'other', 'kind': 'sketch_circle', 'label': 'Other', 'params': {'radius': 'other'}, 'inputs': {}},
    ], 'active_feature': 'other'}


def test_shared_radius_units_and_no_diameter_conversion(document):
    before = copy.deepcopy(document)
    result = helper.edit_shared_radius(document, copy.deepcopy(document), 'circle', 'hole_radius', '0.6 cm')
    assert float(result['parameters']['hole_radius']) == 6
    assert result['features'] == before['features']
    assert result['active_feature'] == 'other'
    assert document == before


def test_untouched_radius_parameter_keeps_numeric_type(document):
    result = helper.edit_shared_radius(document, copy.deepcopy(document), 'circle', 'hole_radius', '4')
    assert type(result['parameters']['hole_radius']) is int


@pytest.mark.parametrize('value', [' hole_radius', 'hole_radius * 2', 'unknown', 4, '4'])
def test_only_exact_named_radius(document, value):
    document['features'][0]['params']['radius'] = value
    assert helper.radius_parameter(document, document['features'][0]) == ''


@pytest.mark.parametrize('change', ['link', 'kind', 'duplicate', 'missing'])
def test_rebound_or_ambiguous_circle_rejected(document, change):
    before = copy.deepcopy(document)
    candidate = copy.deepcopy(document)
    if change == 'link':
        candidate['features'][0]['params']['radius'] = '6'
    elif change == 'kind':
        candidate['features'][0]['kind'] = 'fillet'
    elif change == 'duplicate':
        candidate['features'].append(copy.deepcopy(candidate['features'][0]))
    else:
        candidate['features'].pop(0)
    with pytest.raises(ValueError):
        helper.edit_shared_radius(document, candidate, 'circle', 'hole_radius', '6')
    assert document == before


def test_empty_radius_rejects_and_formula_retained(document):
    with pytest.raises(ValueError):
        helper.edit_shared_radius(document, copy.deepcopy(document), 'circle', 'hole_radius', ' ')
    result = helper.edit_shared_radius(document, copy.deepcopy(document), 'circle', 'hole_radius', 'other / 3')
    assert result['parameters']['hole_radius'] == 'other / 3'
