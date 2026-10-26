"""Native drawing-only H/V badge checks, not solver or interactive qualification."""
import importlib
import os
import sys
import types
from pathlib import Path
from unittest.mock import patch

import bpy
import gpu
from mathutils import Matrix

ROOT = Path(os.environ.get('MCAD_ROOT', Path(__file__).resolve().parents[1]))
package = types.ModuleType('axis_badge_smoke')
package.__path__ = [str(ROOT / 'blender_addon/mechanical_cad_blender')]
sys.modules[package.__name__] = package
g = importlib.import_module(package.__name__ + '.general_view_geometry')
o = importlib.import_module(package.__name__ + '.general_sketch_overlay')
source = {
    'schema_version': 2, 'id': 'sketch', 'units': 'mm',
    'plane': {'id': 'plane', 'origin': [0, 0, 0], 'quaternion': [1, 0, 0, 0]},
    'points': [{'id': 'a', 'u': 80, 'v': 120}, {'id': 'b', 'u': 320, 'v': 120}],
    'lines': [{'id': 'line', 'start': 'a', 'end': 'b'}], 'circles': [],
    'constraints': [{'id': 'h', 'kind': 'horizontal', 'refs': ['line']},
                    {'id': 'length', 'kind': 'distance', 'refs': ['a', 'b'], 'value': 240}],
}
selection = [{'kind': 'line', 'id': 'line'}]
annotations = {'length': {'kind': 'distance', 'refs': ['a', 'b'],
                          'display': 'distance', 'offset': [0, 14]}}
frame = o.build_frame(g.build_geometry(source, source='authored'), lambda w: w[:2],
                      selection=selection, annotations=annotations)
assert frame.axis_badges[0].text == 'H Horizontal · authored'
objects = tuple(bpy.data.objects)
def state():
    return (gpu.state.blend_get(), gpu.state.depth_test_get(),
                 gpu.state.depth_mask_get(), gpu.state.line_width_get())
gpu.init()
offscreen = gpu.types.GPUOffScreen(720, 400)
texts = []
try:
    with offscreen.bind():
        gpu.state.viewport_set(0, 0, 720, 400)
        gpu.matrix.load_matrix(Matrix.Identity(4))
        gpu.matrix.load_projection_matrix(Matrix(((2/720,0,0,-1),(0,2/400,0,-1),(0,0,-1,0),(0,0,0,1))))
        saved = state()
        original = o._text
        def record(*args):
            texts.append(args[3])
            return original(*args)
        with patch.object(o, '_text', side_effect=record):
            bounds = o.draw_frame(frame, usable_rect=(0,0,720,400))
        assert [identifier for identifier, _ in bounds] == ['length']
        assert 'H Horizontal · authored' in texts
        assert state() == saved
        texts.clear()
        with patch.object(o, '_text', side_effect=record):
            o.draw_frame(frame, usable_rect=(0,0,35,15))
        assert not texts
finally:
    offscreen.free()
assert tuple(bpy.data.objects) == objects
print('AXIS_BADGES_SMOKE_OK: native BLF/GPU, dimension-only hit bounds, safe area and state preservation')
