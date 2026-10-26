"""Execute actual recovery draw code with recording layouts, without native imports.

AST extraction isolates presentation from Blender runtime/capture ownership. These
are focused UI policy tests, not a substitute for actual Blender GUI evidence.
"""
import ast
from pathlib import Path
from textwrap import wrap
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2] / 'blender_addon/mechanical_cad_blender'


class Layout:
    def __init__(self):
        self.rows = []

    def label(self, **kwargs):
        self.rows.append(('label', kwargs))

    def prop(self, _state, name, **kwargs):
        self.rows.append(('prop', dict(name=name, **kwargs)))

    def operator(self, name, **kwargs):
        self.rows.append(('operator', dict(name=name, **kwargs)))


def draw_ports(prefs, *, status=('OFF', 'Local recovery is off. Existing snapshots are retained.')):
    namespace = {
        'wrap': wrap, 'preferences': lambda _context: prefs,
        'storage_root': lambda: Path('/private/recovery-v1'),
        'recovery_store': SimpleNamespace(RecoveryError=RuntimeError),
        'status': lambda _scene: status,
    }
    helper = ast.parse((ROOT / 'compact_status.py').read_text())
    nodes = [n for n in helper.body if isinstance(n, ast.FunctionDef) and n.name == 'disclosure']
    exec(compile(ast.Module(body=nodes, type_ignores=[]), '<disclosure>', 'exec'), namespace)
    namespace['compact_status'] = SimpleNamespace(disclosure=namespace['disclosure'])
    tree = ast.parse((ROOT / 'local_recovery.py').read_text())
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef)
             and n.name in {'_label_lines', 'draw_configuration'}]
    panel = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'MCAD_PT_local_recovery')
    nodes += [n for n in panel.body if isinstance(n, ast.FunctionDef)]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), '<recovery draw>', 'exec'), namespace)
    return namespace


@pytest.mark.parametrize('enabled', [False, True])
@pytest.mark.parametrize('width', [260, 420])
def test_collapsed_consent_restore_and_no_verbose_report(enabled, width):
    prefs = SimpleNamespace(local_recovery_enabled=enabled, show_recovery_details=False)
    before = vars(prefs).copy()
    ports = draw_ports(prefs)
    layout = Layout()
    ports['draw_configuration'](layout, SimpleNamespace(region=SimpleNamespace(width=width)))
    text = ' '.join(row['text'] for kind, row in layout.rows if kind == 'label')
    for essential in ('Linux only', 'unavailable on Windows', 'Unencrypted local Part/sketch',
                      'Best effort, not Save', 'New edits may be lost', 'Off retains copies'):
        assert essential in text
    assert not any(word in text for word in ('generations', 'Folder:', 'scopes', 'Assembly'))
    assert sum(kind == 'label' for kind, _ in layout.rows) <= 8
    assert layout.rows[0] == ('prop', {'name': 'local_recovery_enabled'})
    restore = next(i for i, (kind, _) in enumerate(layout.rows) if kind == 'operator')
    disclosure = next(i for i, (kind, row) in enumerate(layout.rows)
                      if kind == 'prop' and row['name'] == 'show_recovery_details')
    assert restore < disclosure
    assert vars(prefs) == before


def test_expanded_details_keep_complete_retention_coverage_and_folder():
    prefs = SimpleNamespace(local_recovery_enabled=False, show_recovery_details=True)
    ports = draw_ports(prefs)
    layout = Layout()
    ports['draw_configuration'](layout, SimpleNamespace())
    text = ' '.join(row['text'] for kind, row in layout.rows if kind == 'label')
    for detail in ('Two generations', '32 scopes, 128 MiB', '2 seconds', 'disk stalls',
                   'Assembly, unapplied repair', 'conflict copies', 'No automatic eviction',
                   'network, Git or export', 'session, Scene and document', '/private/recovery-v1'):
        assert detail in text


@pytest.mark.parametrize('kind,message', [
    ('PENDING', 'Changes are not yet in a completed disk snapshot.'),
    ('ERROR', 'Not current on disk: quota exceeded.'),
    ('SNAPSHOT', 'Last disk snapshot: 2026-10-25T00:00:00Z'),
])
def test_current_status_is_not_collapsed(kind, message):
    prefs = SimpleNamespace(local_recovery_enabled=True, show_recovery_details=False)
    ports = draw_ports(prefs, status=(kind, message))
    layout = Layout()
    ports['draw'](SimpleNamespace(layout=layout), SimpleNamespace(scene=object()))
    text = ' '.join(row['text'] for key, row in layout.rows if key == 'label')
    assert text.startswith(message)
    assert layout.rows[0][1]['icon'] == ('ERROR' if kind == 'ERROR' else 'INFO')


def test_disclosure_defaults_closed_unsaved_and_opt_in_stays_off():
    tree = ast.parse((ROOT / 'properties.py').read_text())
    prefs = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'MCAD_Preferences')
    props = {}
    for node in prefs.body:
        if isinstance(node, ast.AnnAssign) and node.target.id in {
            'show_recovery_details', 'local_recovery_enabled'
        }:
            props[node.target.id] = {
                keyword.arg: ast.literal_eval(keyword.value)
                for keyword in node.annotation.keywords
            }
    assert props['local_recovery_enabled']['default'] is False
    assert props['show_recovery_details']['default'] is False
    assert props['show_recovery_details']['options'] == {'SKIP_SAVE'}
