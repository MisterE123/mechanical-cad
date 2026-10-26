"""Real Operator/OperatorProperties RNA coverage; only dialog presentation is fake.

Run using native Blender --background --factory-startup --python-exit-code 1.
MCAD_ROOT selects the add-on source. No kernel, dependencies or UI popup required.
"""
import gc
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import bpy
from bpy.props import EnumProperty, StringProperty

ROOT = Path(os.environ['MCAD_ROOT'])
sys.path.insert(0, str(ROOT / 'blender_addon'))
from mechanical_cad_blender import local_recovery as recovery  # noqa: E402
from mechanical_cad_blender import recovery_store, register, unregister  # noqa: E402

CALLBACKS = []
OWNERS = {}
COMPLETED = set()
ACTION = None


def choices(properties, context):
    CALLBACKS.append((properties.as_pointer(), hasattr(properties, '_dialog_snapshot')))
    assert isinstance(properties, bpy.types.OperatorProperties)
    return recovery._entry_choices(properties, context)


class RNAProbe:
    def execute(self, context):
        ACTION(self, context)
        COMPLETED.add(type(self).__name__)
        return {'FINISHED'}


class MCADTEST_OT_recovery_a(RNAProbe, bpy.types.Operator):
    bl_idname = 'mcadtest.recovery_a'
    bl_label = 'Recovery RNA probe A'
    chooser_token: StringProperty(options={'HIDDEN', 'SKIP_SAVE'})
    entry: EnumProperty(items=choices)


class MCADTEST_OT_recovery_b(RNAProbe, bpy.types.Operator):
    bl_idname = 'mcadtest.recovery_b'
    bl_label = 'Recovery RNA probe B'
    chooser_token: StringProperty(options={'HIDDEN', 'SKIP_SAVE'})
    entry: EnumProperty(items=choices)


def record(sequence, name):
    document = json.dumps({
        'schema_version': 1, 'id': 'recovery_choice_test', 'name': name,
        'units': 'mm', 'parameters': {}, 'features': [], 'active_feature': None,
    })
    return recovery_store.decode(recovery_store.encode(
        'a' * 32, sequence, document, created=f'2026-10-25T00:00:{sequence:02d}+00:00',
    ))


def store_for(value):
    source = Mock()
    source.entries.return_value = [recovery_store.Entry(
        value.scope, value.sequence % 2, value.sequence, value.created,
        document_name=json.loads(value.document_json)['name'],
    )]
    source.read.return_value = value
    return source


def invoke(owner, source):
    presentation = Mock(return_value={'RUNNING_MODAL'})
    context = SimpleNamespace(window_manager=SimpleNamespace(invoke_props_dialog=presentation))
    with patch.object(recovery, 'store', return_value=source):
        result = recovery.MCAD_OT_restore_local_recovery.invoke(owner, context, None)
    if result == {'RUNNING_MODAL'}:
        presentation.assert_called_once_with(owner, width=650)
    return result


def scene_snapshot():
    return (
        tuple(bpy.data.scenes), bpy.context.window.scene,
        tuple((s.as_pointer(), tuple(s.objects), s.mechanical_cad.document_json,
               s.mechanical_cad.sketch_draft_json, s.mechanical_cad.document_path,
               s.mechanical_cad_assembly.document_json) for s in bpy.data.scenes),
    )


def immutable(value, key, replacement):
    try:
        value[key] = replacement
    except TypeError:
        return
    raise AssertionError('Mutable dialog snapshot')


FIRST = record(1, 'First dialog name')
ROTATED = record(3, 'Rotated second dialog name')
EMPTY = recovery._EMPTY_CHOICES


def second(owner, context):
    a = OWNERS['a']
    a_items, a_snapshot, a_key = a._recovery_items, a._dialog_snapshot, a._dialog_key
    a_ids = tuple(tuple(id(text) for text in row) for row in a_items)

    def unchanged():
        assert recovery._entry_choices(a.properties, context) is a_items
        assert a._dialog_snapshot is a_snapshot and recovery._DIALOGS[a_key] is a_snapshot
        assert recovery._selected_fingerprint(a) == recovery.record_fingerprint(FIRST)
        assert tuple(tuple(id(text) for text in row) for row in a_items) == a_ids

    # A copied public RNA token is not a capability for another operator.
    owner.chooser_token = a.chooser_token
    assert recovery._entry_choices(owner.properties, context) is EMPTY
    assert recovery._selected_fingerprint(owner) is None
    with patch.object(recovery, 'restore_as_new') as restore:
        assert recovery.MCAD_OT_restore_local_recovery.execute(owner, context) == {'CANCELLED'}
        restore.assert_not_called()
    unchanged()
    assert invoke(owner, store_for(ROTATED)) == {'RUNNING_MODAL'}
    assert owner.entry == a.entry, 'Fixture must rotate same scope and disk slot'
    assert owner.properties.as_pointer() != a.properties.as_pointer()
    assert (owner.properties.as_pointer(), False) in CALLBACKS
    assert 'Rotated second dialog name' in recovery._entry_choices(owner.properties, None)[0][1]
    assert recovery._selected_fingerprint(owner) == recovery.record_fingerprint(ROTATED)
    assert recovery._selected_fingerprint(owner) != recovery._selected_fingerprint(a)
    assert owner._recovery_items is not a_items
    unchanged()
    b_items = owner._recovery_items
    recovery.MCAD_OT_restore_local_recovery.cancel(owner, context)
    assert recovery._entry_choices(owner.properties, None) is EMPTY
    assert recovery._selected_fingerprint(owner) is None
    assert any(items is b_items for items in recovery._ENUM_CACHE.values())
    unchanged()

    # Failed/empty reinvocation revokes only this owner, not the other dialog.
    for source, expected in [(Mock(), 'No local snapshots'), (store_for(ROTATED), 'Injected read failure')]:
        assert invoke(owner, store_for(ROTATED)) == {'RUNNING_MODAL'}
        if expected.startswith('No'):
            source.entries.return_value = []
        else:
            source.read.side_effect = OSError(expected)
        assert invoke(owner, source) == {'CANCELLED'}
        assert recovery._entry_choices(owner.properties, None) is EMPTY
        assert owner._dialog_snapshot is None and not owner._bindings
        unchanged()

    # Real restore validator rejects a rotated exact record before scene mutation.
    assert invoke(owner, store_for(FIRST)) == {'RUNNING_MODAL'}
    before = scene_snapshot()
    with patch.object(recovery, 'store', return_value=store_for(ROTATED)):
        assert recovery.MCAD_OT_restore_local_recovery.execute(owner, context) == {'CANCELLED'}
    assert scene_snapshot() == before
    assert recovery._entry_choices(owner.properties, context) is EMPTY
    unchanged()

    # A successful execute passes the immutable fingerprint, then retires itself.
    assert invoke(owner, store_for(ROTATED)) == {'RUNNING_MODAL'}
    with patch.object(recovery, 'restore_as_new') as restore:
        assert recovery.MCAD_OT_restore_local_recovery.execute(owner, context) == {'FINISHED'}
        restore.assert_called_once_with(context, ROTATED.scope, ROTATED.sequence % 2,
                                        expected_fingerprint=recovery.record_fingerprint(ROTATED))
    assert recovery._entry_choices(owner.properties, context) is EMPTY
    gc.collect()
    unchanged()


def first(owner, context):
    global ACTION
    OWNERS['a'] = owner
    assert recovery._entry_choices(owner.properties, None) is EMPTY
    assert recovery._entry_choices(None, None) is EMPTY
    assert invoke(owner, store_for(FIRST)) == {'RUNNING_MODAL'}
    items = recovery._entry_choices(owner.properties, None)
    assert 'First dialog name' in items[0][1]
    assert owner.entry == items[0][0]  # Genuine RNA enum lookup calls callback.
    assert owner.as_pointer() != owner.properties.as_pointer()
    assert (owner.properties.as_pointer(), False) in CALLBACKS
    print('RNA_POINTER_EVIDENCE', json.dumps({
        'owner': owner.as_pointer(), 'properties': owner.properties.as_pointer(),
        'callback_has_private_snapshot': False, 'callback_count': len(CALLBACKS),
    }), flush=True)
    immutable(items, 0, ('replacement', 'replacement', ''))
    immutable(items[0], 1, 'replacement')
    immutable(owner._bindings, owner.entry, 'replacement')
    immutable(owner._dialog_snapshot, 'owner', 0)
    ACTION = second
    try:
        bpy.ops.mcadtest.recovery_b('EXEC_DEFAULT')
    except RuntimeError as exc:
        # Blender propagates expected ERROR reports after execute returns.
        for message in ('Restore dialog first', 'No local snapshots',
                        'Injected read failure', 'Selected snapshot changed on disk'):
            assert message in str(exc), str(exc)
    assert 'MCADTEST_OT_recovery_b' in COMPLETED
    assert recovery._selected_fingerprint(owner) == recovery.record_fingerprint(FIRST)
    recovery.MCAD_OT_restore_local_recovery.cancel(owner, context)
    assert recovery._entry_choices(owner.properties, None) is EMPTY
    assert recovery._entry_choices(owner.properties, context) is EMPTY
    assert any(cached is items for cached in recovery._ENUM_CACHE.values())
    OWNERS.clear()
    gc.collect()


register()
try:
    bpy.utils.register_class(MCADTEST_OT_recovery_a)
    bpy.utils.register_class(MCADTEST_OT_recovery_b)
    rna = bpy.ops.mcad.restore_local_recovery.get_rna_type()
    assert rna.properties['entry'].type == 'ENUM'
    assert rna.properties['chooser_token'].is_hidden
    assert rna.properties['chooser_token'].is_skip_save
    ACTION = first
    assert bpy.ops.mcadtest.recovery_a('EXEC_DEFAULT') == {'FINISHED'}
    before = scene_snapshot()
    with patch.object(recovery, 'restore_as_new') as restore:
        try:
            result = bpy.ops.mcad.restore_local_recovery('EXEC_DEFAULT', entry='NONE', chooser_token='forged')
        except RuntimeError as exc:
            assert 'Restore dialog first' in str(exc), str(exc)
        else:
            assert result == {'CANCELLED'}
        restore.assert_not_called()
    assert scene_snapshot() == before
    assert not recovery._DIALOGS
finally:
    bpy.utils.unregister_class(MCADTEST_OT_recovery_b)
    bpy.utils.unregister_class(MCADTEST_OT_recovery_a)
    unregister()
print('RECOVERY_RNA_SMOKE_OK', flush=True)
