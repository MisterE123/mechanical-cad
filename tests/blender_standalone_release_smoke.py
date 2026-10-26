"""Bounded exact-installed backend/save/reopen checks; never a GUI qualification.

Launched by qualify_standalone_candidate.py in independent Blender processes.
The only project imports are from the installed extension. The adjacent JSON is
inert test input, not a source checkout or substitute backend.
"""
import hashlib
import importlib
import json
import math
import os
import sys
import time
import tomllib
import zipfile
from pathlib import Path

import bpy

BASE = Path(os.environ['MCAD_VERIFY_BASE']).resolve()
ARCHIVE = Path(os.environ['MCAD_VERIFY_ARCHIVE']).resolve()
COMMIT = os.environ['MCAD_VERIFY_COMMIT']
VERSION = os.environ['MCAD_VERIFY_VERSION']
MODE = os.environ['MCAD_VERIFY_MODE']
BLENDER_VERSION = tuple(int(v) for v in os.environ['MCAD_VERIFY_BLENDER_VERSION'].split('.'))
MODULE = 'bl_ext.user_default.mechanical_cad'
ARTIFACTS = BASE / 'artifacts'
PROFILE = BASE / 'profile'
CHECKS = []


def check(condition, message):
    if not condition:
        raise AssertionError(message)
    CHECKS.append(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_json(path, value):
    # Each mode owns a new receipt. Existing results are never silently replaced.
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')


check(MODE in {'install', 'write', 'read'}, 'Known qualification mode')
check(bpy.app.version == BLENDER_VERSION, 'Exact requested Blender version')
check(len(COMMIT) == 40 and all(c in '0123456789abcdef' for c in COMMIT), 'Full source commit')
check(not any(os.environ.get(k) for k in ('MCAD_ROOT', 'MCAD_PYTHON', 'PYTHONPATH', 'BLENDER_USER_SCRIPTS')), 'No source/manual backend environment')
check(Path(os.environ['BLENDER_USER_CONFIG']).resolve() == PROFILE / 'config', 'Isolated configuration path')
check(Path(os.environ['BLENDER_USER_EXTENSIONS']).resolve() == PROFILE / 'extensions', 'Isolated extension path')
if MODE == 'install':
    check(bpy.ops.extensions.package_install_files(filepath=str(ARCHIVE), repo='user_default', enable_on_install=True) == {'FINISHED'}, 'Exact candidate installed')
else:
    check(bpy.ops.preferences.addon_enable(module=MODULE) == {'FINISHED'}, 'Installed extension enabled in independent process')
addon = importlib.import_module(MODULE)
root = Path(addon.__file__).resolve().parent
check(root.is_relative_to(PROFILE), 'Module origin belongs to isolated installed profile')
prefs = bpy.context.preferences.addons[MODULE].preferences
check(not prefs.project_root and not prefs.python_executable, 'No manual backend preferences')
check(tomllib.loads((root / 'blender_manifest.toml').read_text())['version'] == VERSION, 'Installed manifest version')
with zipfile.ZipFile(ARCHIVE) as archive:
    for item in archive.infolist():
        if item.is_dir() or item.filename.startswith(('sources/', 'licenses/')):
            continue
        path = root / item.filename
        check(path.read_bytes() == archive.read(item), 'Installed bytes: ' + item.filename)
        if os.name != 'nt':
            check(path.stat().st_mode & 0o777 == (item.external_attr >> 16) & 0o777, 'Installed mode: ' + item.filename)
identity = json.loads((root / 'release_identity.json').read_bytes())
check(identity['source_commit'] == COMMIT, 'Exact package source commit')
runtime = importlib.import_module(MODULE + '.backend_runtime')
start = time.monotonic()
while runtime.poll_bundled_setup():
    check(time.monotonic() - start < 180, 'Bounded bundled setup wait')
    time.sleep(.05)
check(runtime.bundled_mode() and runtime.bundle_status()[0] == 'ready', 'Bundled setup ready')
selection = runtime.capture(bpy.context)
check(selection.bundled_policy is not None, 'Bundled guarded launch policy selected')
cache = Path(selection.project_root)
manifest = json.loads((root / identity['manifest_path']).read_bytes())
for item in manifest['files']:
    path = cache / item['path']
    check(path.stat().st_size == item['size'] and sha(path) == item['sha256'], 'Backend inventory: ' + item['path'])
    if os.name != 'nt':
        check(path.stat().st_mode & 0o777 == item['mode'], 'Backend mode: ' + item['path'])


def check_origin():
    check('mechanical_cad_blender' not in sys.modules and 'mechanical_cad' not in sys.modules, 'No source addon/core imported in Blender')
    check(not any(n == 'OCP' or n.startswith('OCP.') or n == 'slvs' for n in sys.modules), 'Native kernels stay outside Blender')
    for name, module in tuple(sys.modules.items()):
        if (name == MODULE or name.startswith(MODULE + '.')) and getattr(module, '__file__', None):
            check(Path(module.__file__).resolve().is_relative_to(root), 'Installed import origin: ' + name)


check_origin()
ds = importlib.import_module(MODULE + '.document_state')
blend = ARTIFACTS / 'constrained-plate.blend'
snapshot = ARTIFACTS / 'model-snapshot.json'
if MODE == 'write':
    document = json.loads((Path(__file__).parent / 'fixtures/standalone_constrained_plate.mcad.json').read_text())
    state = bpy.context.scene.mechanical_cad
    check(ds._commit_candidate(bpy.context, document, state.document_path), 'Installed bundled solver and kernel replay constrained plate')
    check(state.status == 'READY' and ds.part_is_current(bpy.context), 'Fresh geometry is current')
    check(math.isclose(state.volume, 12000.0, abs_tol=.01), 'Exact 40x30x10 plate volume')
    canonical = state.document_json
    check(bpy.ops.mcad.check_geometry() == {'FINISHED'}, 'Explicit geometry validation succeeds')
    check(ds.geometry_report_is_current(bpy.context), 'Geometry report current before save')
    check(not blend.exists() and not snapshot.exists(), 'New save targets only')
    check(bpy.ops.wm.save_as_mainfile(filepath=str(blend)) == {'FINISHED'}, 'Native blend saved')
    check(blend.is_file() and state.document_json == canonical, 'Save preserves canonical model')
    save_json(snapshot, {'document_json': canonical, 'volume': state.volume, 'blend_sha256': sha(blend), 'archive_sha256': sha(ARCHIVE), 'source_commit': COMMIT})
elif MODE == 'read':
    expected = json.loads(snapshot.read_text())
    check(expected['archive_sha256'] == sha(ARCHIVE) and expected['source_commit'] == COMMIT, 'Saved model bound to exact candidate')
    check(sha(blend) == expected['blend_sha256'], 'Saved file unchanged before reopen')
    check(bpy.ops.wm.open_mainfile(filepath=str(blend)) == {'FINISHED'}, 'Saved file opened in independent process')
    state = bpy.context.scene.mechanical_cad
    check(state.document_json == expected['document_json'], 'Exact canonical model survives reopen')
    check(state.status == 'DIRTY', 'Loaded display requires fresh replay')
    check(not ds.part_is_current(bpy.context) and not ds.geometry_report_is_current(bpy.context), 'Saved authority is not trusted')
    check(bpy.ops.mcad.regenerate() == {'FINISHED'}, 'Fresh bundled replay after reopen')
    check(state.status == 'READY' and ds.part_is_current(bpy.context), 'Reopened model current after replay')
    check(state.document_json == expected['document_json'], 'Replay preserves canonical graph')
    check(math.isclose(state.volume, expected['volume'], abs_tol=.01) and math.isclose(state.volume, 12000.0, abs_tol=.01), 'Reopened exact constrained geometry')
    check(sha(blend) == expected['blend_sha256'], 'Read check does not overwrite saved file')
check_origin()
result = {'ok': True, 'mode': MODE, 'version': VERSION, 'source_commit': COMMIT,
          'blender': '.'.join(str(v) for v in bpy.app.version), 'blender_version_string': bpy.app.version_string, 'runtime_files_verified': len(manifest['files']),
          'bundle_id': identity['bundle_id'], 'archive_sha256': sha(ARCHIVE),
          'installed_module_root': str(root), 'interactive_gui': False,
          'checks': CHECKS, 'scope': 'Bounded exact-installed backend and separate-process persistence; not full regression, GUI, native dependency closure or release admission.'}
save_json(BASE / 'receipts' / f'{MODE}.json', result)
print('MCAD_STANDALONE_RESULT=' + json.dumps(result, sort_keys=True, allow_nan=False), flush=True)
