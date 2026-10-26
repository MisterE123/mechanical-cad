"""Explicit opt-in, main-thread-only local recovery of settled Part intent.

No worker, network, native solve, automatic restore, or file-save hook. Timer
callbacks cannot interleave normal synchronous Blender transactions. An explicit
fence also blocks reentrant observation inside authoring postchecks.
"""
import hashlib
import threading
import uuid
from pathlib import Path
from textwrap import wrap
from types import MappingProxyType, SimpleNamespace

import bpy
from bpy.app.handlers import persistent
from bpy.props import EnumProperty, StringProperty
from bpy.types import Operator, Panel

from . import (
    bridge,
    compact_status,
    document_state,
    draft_dispatch,
    execution_lease,
    recovery_capture,
    recovery_store,
    sketch_session,
    staged_edit_store,
)

INTERVAL = 2.0
_SCOPES = {}
_STATUS = {}
_OBSERVING = False
# Blender retains enum-string pointers. Intern complete immutable item tuples
# for the module/UI lifetime; never replace or evict strings on dialog changes.
_ENUM_CACHE = {}
_EMPTY_CHOICES = (('NONE', 'No local snapshots', ''),)
_DIALOGS = {}  # Pending, pointer-and-nonce-bound snapshots; never shared selection.


def preferences(context=None):
    entry = (context or bpy.context).preferences.addons.get(__package__)
    return None if entry is None else entry.preferences


def enabled(context=None):
    prefs = preferences(context)
    return bool(prefs is not None and prefs.local_recovery_enabled)


def storage_root():
    """Installed user's application config, never document/model-provided paths."""
    config = bpy.utils.user_resource('CONFIG')
    if not config:
        raise recovery_store.RecoveryError("Blender user configuration directory is unavailable.")
    return Path(config) / 'mechanical_cad' / 'recovery-v1'


def store():
    return recovery_store.Store(storage_root())


def _main_thread():
    if threading.current_thread() is not threading.main_thread():
        raise recovery_store.RecoveryError("Recovery capture/restore requires Blender's main thread.")


def capture_text(scene):
    """Return a coherent exact pair, or refuse unsupported/unsettled work.

    Reads live pure draft intent only after its event/transaction has settled.
    Serializers exclude pending jobs, leases, solver evidence and input tokens.
    This function does not checkpoint RNA or alter any model/editor state.
    """
    _main_thread()
    if not recovery_capture.is_settled() or document_state._REPLAY_RUNNING or document_state._UI_LOCK:
        raise recovery_store.RecoveryError("Transaction pending; latest changes are not on disk.")
    if execution_lease.is_busy():
        raise recovery_store.RecoveryError("CAD operation pending; latest changes are not on disk.")
    state = scene.mechanical_cad
    if scene.mechanical_cad_assembly.document_json:
        raise recovery_store.RecoveryError("Assembly scenes are not covered by local recovery.")
    context = SimpleNamespace(scene=scene)
    if state.repair_intent_json or staged_edit_store.current(context) is not None:
        raise recovery_store.RecoveryError("Unapplied repair is not covered by local recovery.")
    if staged_edit_store.resume_reserved():
        raise recovery_store.RecoveryError("Repair Resume pending; recovery capture is paused.")
    if sketch_session.draft_recovery_notice():
        raise recovery_store.RecoveryError("Exceptional in-memory sketch copies are not covered.")
    canonical, draft = state.document_json, state.sketch_draft_json
    owner = sketch_session.active_session()
    if owner is not None and owner.scene == scene:
        if (owner.draft.document_json != canonical or owner.stored_snapshot != draft
                or not sketch_session.SketchSession.valid_context(owner)):
            raise recovery_store.RecoveryError("Conflicting sketch context is not covered.")
        draft = draft_dispatch.dumps(owner.draft)
    return canonical, draft


def observe():
    """Timer/API: best-effort synchronous write, never a model operation result."""
    global _OBSERVING
    _main_thread()
    if _OBSERVING or not enabled():
        return INTERVAL
    _OBSERVING = True
    try:
        for scene in tuple(bpy.data.scenes):
            uid = scene.session_uid
            if not scene.mechanical_cad.document_json:
                _STATUS[uid] = ('EMPTY', 'No Part document to snapshot.')
                continue
            try:
                canonical, draft = capture_text(scene)
                identifier = bridge.parse_document_json(canonical).get('id')
                key = (uid, identifier)
                scope = _SCOPES.setdefault(key, {
                    'id': uuid.uuid4().hex, 'sequence': 0, 'pair': None, 'created': None,
                })
                if scope['pair'] == (canonical, draft):
                    record = store().read(scope['id'], (scope['sequence'] - 1) % 2)
                    if (record.sequence != scope['sequence'] or record.document_json != canonical
                            or record.draft_json != draft):
                        raise recovery_store.RecoveryError('Last disk snapshot changed externally.')
                    _STATUS[uid] = ('SNAPSHOT', f"Last disk snapshot: {scope['created']}")
                    continue
                sequence = scope['sequence'] + 1
                payload = recovery_store.encode(scope['id'], sequence, canonical, draft)
                record = store().write(payload)
                # Update only after the actual durable write succeeds. Failed I/O
                # cannot advance the watermark or fail a published CAD operation.
                scope.update(sequence=sequence, pair=(canonical, draft), created=record.created)
                _STATUS[uid] = ('SNAPSHOT', f"Last disk snapshot: {record.created}")
            except Exception as exc:
                _STATUS[uid] = ('ERROR', "Not current on disk: " + str(exc))
    finally:
        _OBSERVING = False
    return INTERVAL


def status(scene):
    if not enabled():
        return 'OFF', 'Local recovery is off. Existing snapshots are retained.'
    if scene.mechanical_cad_assembly.document_json:
        return 'ERROR', 'Assembly scenes are not covered by local recovery.'
    if not scene.mechanical_cad.document_json:
        return 'EMPTY', 'No Part document to snapshot.'
    try:
        canonical, draft = capture_text(scene)
        identifier = bridge.parse_document_json(canonical).get('id')
        scope = _SCOPES.get((scene.session_uid, identifier))
        if scope is None or scope['pair'] != (canonical, draft):
            cached = _STATUS.get(scene.session_uid)
            if cached is not None and cached[0] == 'ERROR':
                return cached
            return 'PENDING', 'Changes are not yet in a completed disk snapshot.'
    except Exception as exc:
        return 'ERROR', 'Capture unavailable: ' + str(exc)
    # Historical last verified snapshot, not proof that disk remains untouched
    # between polls. The observer rechecks integrity even when input is unchanged.
    return _STATUS.get(scene.session_uid, ('WAITING', 'Waiting for the first settled disk snapshot.'))


@persistent
def _on_load(_unused):
    # Runtime-only stream identities: loading a file cannot inherit a stream ID
    # from the file, overwrite another process's stream or enable preferences.
    _SCOPES.clear()
    _STATUS.clear()
    _DIALOGS.clear()


def start():
    if not bpy.app.timers.is_registered(observe):
        bpy.app.timers.register(observe, first_interval=INTERVAL, persistent=True)
    if _on_load not in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.append(_on_load)


def stop():
    if bpy.app.timers.is_registered(observe):
        bpy.app.timers.unregister(observe)
    if _on_load in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(_on_load)
    _SCOPES.clear()
    _STATUS.clear()
    _DIALOGS.clear()


def record_fingerprint(record):
    """Bind a dialog choice to all validated envelope metadata and exact bytes."""
    return hashlib.sha256(recovery_store.encode(**record.__dict__)).hexdigest()


def restore_as_new(context, scope, slot, *, expected_fingerprint=None):
    """Explicit data-only fresh Scene; original scenes/files never overwritten."""
    _main_thread()
    if not recovery_capture.is_settled() or document_state._REPLAY_RUNNING or execution_lease.is_busy():
        raise recovery_store.RecoveryError('Wait for the current CAD operation before Restore.')
    if context.window is None or sketch_session.active_session() is not None:
        raise recovery_store.RecoveryError('Suspend or finish the live sketch before Restore.')
    if staged_edit_store.resume_reserved() or staged_edit_store.current(context) is not None:
        raise recovery_store.RecoveryError('Finish or discard the active repair operation before Restore.')
    # Decode, checksums, strict schema and exact draft/base match before any RNA.
    record = store().read(scope, slot)
    if expected_fingerprint is not None and record_fingerprint(record) != expected_fingerprint:
        raise recovery_store.RecoveryError('Selected snapshot changed on disk. Reopen Restore to review the new generation.')
    document = bridge.parse_document_json(record.document_json)
    previous = context.window.scene
    scene = bpy.data.scenes.new('Recovered CAD (unsaved)')
    try:
        document_state._populate_document(scene, document, '')
        state = scene.mechanical_cad
        # _populate_document prepares UI rows but its serialization must not
        # normalize away the exact byte binding needed by explicit Resume.
        state.document_json = record.document_json
        state.document_path = ''
        state.sketch_draft_json = record.draft_json
        state.sketch_draft_scene_id = uuid.uuid4().hex if record.draft_json else ''
        state.repair_intent_json = ''
        state.status = 'DIRTY'
        state.error = 'Recovered intent only. Regenerate for fresh geometry.'
        state.sketch_notice = (
            'Recovered sketch is suspended. Resume requires fresh validation.'
            if record.draft_json else ''
        )
        # A brand-new Scene carries no Assembly source binding, display mesh,
        # native evidence, draft owner, queued acceptance or source file path.
        assert not scene.mechanical_cad_assembly.document_json
        context.window.scene = scene
        return scene
    except Exception:
        context.window.scene = previous
        bpy.data.scenes.remove(scene)
        raise


def _properties_pointer(value):
    # Enum callbacks receive OperatorProperties, not the Python Operator owner.
    # Both wrappers expose the same RNA token but have different pointers.
    return getattr(value, 'properties', value).as_pointer()


def _entry_choices(self, _context):
    try:
        key = (_properties_pointer(self), self.chooser_token)
    except (AttributeError, ReferenceError):
        return _EMPTY_CHOICES
    snapshot = _DIALOGS.get(key)
    return _EMPTY_CHOICES if snapshot is None else snapshot['items']


def _retire_dialog(owner):
    key = getattr(owner, '_dialog_key', None)
    snapshot = getattr(owner, '_dialog_snapshot', None)
    if key is not None and _DIALOGS.get(key) is snapshot:
        _DIALOGS.pop(key, None)
    owner._dialog_key = owner._dialog_snapshot = None
    owner._recovery_items = _EMPTY_CHOICES
    owner._bindings = MappingProxyType({})


def _bind_dialog(owner, choices, bindings):
    items = tuple(choices)
    items = _ENUM_CACHE.setdefault(items, items)
    owner.chooser_token = uuid.uuid4().hex
    key = (_properties_pointer(owner), owner.chooser_token)
    snapshot = MappingProxyType({
        'items': items, 'bindings': MappingProxyType(dict(bindings)),
        'owner': owner.as_pointer(),
    })
    _DIALOGS[key] = snapshot
    owner._dialog_key, owner._dialog_snapshot = key, snapshot
    owner._recovery_items, owner._bindings = items, snapshot['bindings']


def _selected_fingerprint(owner):
    key = (_properties_pointer(owner), owner.chooser_token)
    snapshot = _DIALOGS.get(key)
    if (snapshot is None or getattr(owner, '_dialog_key', None) != key
            or getattr(owner, '_dialog_snapshot', None) is not snapshot
            or snapshot['owner'] != owner.as_pointer()):
        return None
    return snapshot['bindings'].get(owner.entry)


class MCAD_OT_restore_local_recovery(Operator):
    bl_idname = 'mcad.restore_local_recovery'
    bl_label = 'Restore Local Snapshot as New Scene'
    bl_description = 'Validate and restore intent as a new unsaved Scene; originals stay unchanged'
    chooser_token: StringProperty(options={'HIDDEN', 'SKIP_SAVE'})
    entry: EnumProperty(name='Snapshot', items=_entry_choices)

    def invoke(self, context, _event):
        # A failed/repeated invoke cannot retain a previous selection capability.
        _retire_dialog(self)
        try:
            rows = sorted(store().entries(), key=lambda item: (item.created or '', item.sequence or 0), reverse=True)
            choices = []
            bindings = {}
            for item in rows:
                label = f"{getattr(item, 'document_name', 'Part')} / {item.scope[:8]} / #{item.sequence or '?'} / {item.created or 'unreadable'}"
                if item.error:
                    label += ' / INVALID'
                choice = f'{item.scope}:{item.slot}'
                choices.append((choice, label, item.error or f'Scope {item.scope}; restore a new unsaved copy'))
                if not item.error:
                    selected = store().read(item.scope, item.slot)
                    if selected.sequence != item.sequence or selected.created != item.created:
                        raise recovery_store.RecoveryError('Snapshot changed while listing; reopen Restore.')
                    bindings[choice] = record_fingerprint(selected)
            if not choices:
                raise recovery_store.RecoveryError('No local snapshots are available.')
            _bind_dialog(self, choices, bindings)
            self.entry = self._recovery_items[0][0]
            return context.window_manager.invoke_props_dialog(self, width=650)
        except Exception as exc:
            _retire_dialog(self)
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}

    def cancel(self, _context):
        _retire_dialog(self)

    def draw(self, _context):
        layout = self.layout
        layout.prop(self, 'entry')
        layout.label(text='New unsaved Scene only. Current scenes and original files stay unchanged.')
        layout.label(text='Sketch stays suspended; Resume and Regenerate require fresh validation.')
        layout.label(text='Snapshots contain unencrypted Part/sketch intent, not native geometry.')

    def execute(self, context):
        try:
            fingerprint = _selected_fingerprint(self)
            if fingerprint is None:
                raise recovery_store.RecoveryError('Select a valid snapshot in the Restore dialog first.')
            scope, slot = self.entry.split(':')
            restore_as_new(context, scope, int(slot), expected_fingerprint=fingerprint)
            self.report({'INFO'}, 'Restored as a new unsaved Scene. No geometry or solver authority restored.')
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, 'Snapshot retained unchanged: ' + str(exc))
            return {'CANCELLED'}
        finally:
            _retire_dialog(self)


def _label_lines(layout, context, text, *, icon='NONE'):
    region = getattr(context, 'region', None)
    width = max(20, min(72, int((getattr(region, 'width', 420) - 50) / 7)))
    for index, line in enumerate(wrap(text, width=width)):
        layout.label(text=line, icon=icon if index == 0 else 'NONE')


def draw_configuration(layout, context):
    prefs = preferences(context)
    if prefs is not None:
        layout.prop(prefs, 'local_recovery_enabled')
    else:
        layout.label(text='Enable the add-on normally to configure local recovery.')
    # Essential consent and loss warnings remain visible before opt-in, even
    # with details closed. Restore stays above optional explanatory material.
    for text in (
        'Linux only; unavailable on Windows.',
        'Unencrypted local Part/sketch copies.',
        'Best effort, not Save. New edits may be lost.',
        'Off retains copies.',
    ):
        _label_lines(layout, context, text)
    layout.operator('mcad.restore_local_recovery', text='Restore as New Scene', icon='RECOVER_LAST')
    if prefs is None or not compact_status.disclosure(
        layout, prefs, 'show_recovery_details', 'Storage and coverage details'
    ):
        return
    for text in (
        'Two generations per session/Scene/document; 32 scopes, 128 MiB total.',
        'Checks every 2 seconds when idle; busy work and disk stalls delay capture.',
        'Changes after the last disk snapshot can be lost, even after a snapshot.',
        'Assembly, unapplied repair and conflict copies are not covered.',
        'No automatic eviction, network, Git or export.',
        'Separate runtime scope for each session, Scene and document identity.',
    ):
        _label_lines(layout, context, text)
    try:
        _label_lines(layout, context, 'Folder: ' + str(storage_root()))
    except recovery_store.RecoveryError as exc:
        layout.label(text=str(exc), icon='ERROR')


class MCAD_PT_local_recovery(Panel):
    bl_label = 'Local Recovery'
    bl_idname = 'MCAD_PT_local_recovery'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'CAD'
    bl_options = {'DEFAULT_CLOSED'}

    def draw_header(self, context):
        kind, _message = status(context.scene)
        self.layout.label(text=kind, icon='ERROR' if kind == 'ERROR' else 'INFO')

    def draw(self, context):
        kind, message = status(context.scene)
        _label_lines(self.layout, context, message, icon='ERROR' if kind == 'ERROR' else 'INFO')
        draw_configuration(self.layout, context)


CLASSES = (MCAD_OT_restore_local_recovery, MCAD_PT_local_recovery)
