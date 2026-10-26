"""Native source-loaded local recovery, using disposable application storage only."""
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import bpy

ROOT = Path(os.environ["MCAD_ROOT"])
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import (  # noqa: E402
    document_state,
    draft_dispatch,
    general_session,
    local_recovery,
    recovery_store,
    register,
    sketch_session,
    unregister,
    workspace,
)
from mechanical_cad_blender.general_sketch_commands import AddLine, PointSeed  # noqa: E402


def wait(owner):
    deadline = time.monotonic() + 60
    while owner.pending is not None and time.monotonic() < deadline:
        owner.tick(bpy.context)
        time.sleep(.01)
    assert owner.pending is None and not owner.error, owner.error


def files(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}


def latest():
    rows = local_recovery.store().entries()
    entry = max((row for row in rows if not row.error), key=lambda row: row.sequence)
    return entry, local_recovery.store().read(entry.scope, entry.slot)


register()
assert 'entry' in bpy.ops.mcad.restore_local_recovery.get_rna_type().properties
assert bpy.app.timers.is_registered(local_recovery.observe)
local_recovery._on_load(None)
assert bpy.app.timers.is_registered(local_recovery.observe)
entry = bpy.context.preferences.addons.new()
entry.module = "mechanical_cad_blender"
prefs = entry.preferences
prefs.project_root = str(ROOT)
prefs.python_executable = os.environ["MCAD_PYTHON"]
assert not prefs.local_recovery_enabled
window = bpy.context.window
area = next(a for a in window.screen.areas if a.type == 'VIEW_3D')
region = next(r for r in area.regions if r.type == 'WINDOW')
with tempfile.TemporaryDirectory(prefix='mcad-recovery-smoke-') as temporary:
    root = Path(temporary) / 'recovery'
    with patch.object(local_recovery, 'storage_root', return_value=root), bpy.context.temp_override(
        window=window, area=area, region=region,
    ):
        context = bpy.context
        original = context.scene
        document_state._populate_document(original, {
            'schema_version': 1, 'id': 'local_recovery_smoke', 'name': 'Unsaved',
            'units': 'mm', 'parameters': {}, 'features': [], 'active_feature': None,
        })
        state = original.mechanical_cad
        local_recovery.observe()
        assert not root.exists(), 'Default OFF must not create storage'
        prefs.local_recovery_enabled = True
        assert local_recovery.status(original)[0] == 'PENDING'
        canonical_before = state.document_json
        state.document_json = ''
        assert local_recovery.status(original)[0] == 'EMPTY'
        state.document_json = canonical_before
        original.mechanical_cad_assembly.document_json = '{}'
        assert 'Assembly' in local_recovery.status(original)[1]
        part_before = state.document_json
        state.document_json = ''
        assert 'Assembly' in local_recovery.status(original)[1]
        state.document_json = part_before
        assert local_recovery.status(original)[0] == 'ERROR'
        original.mechanical_cad_assembly.document_json = ''
        state.repair_intent_json = '{}'
        assert 'repair' in local_recovery.status(original)[1]
        assert local_recovery.status(original)[0] == 'ERROR'
        state.repair_intent_json = ''
        local_recovery.observe()
        assert local_recovery.status(original)[0] == 'SNAPSHOT'
        state.document_json += ' '
        assert local_recovery.status(original)[0] == 'PENDING'
        state.document_json = canonical_before
        _, first = latest()
        assert first.document_json == state.document_json and not first.draft_json
        owner = general_session.GeneralSession(context)
        owner.start()
        owner.execute(context, AddLine(PointSeed(0, 0), PointSeed(10, 0)))
        wait(owner)
        local_recovery.observe()
        _, accepted = latest()
        assert accepted.draft_json == draft_dispatch.dumps(owner.draft)
        # Merely inspecting invalid context must never run mutating GeneralSession checks.
        saved_owner_values = (owner.gesture_intent, owner.proposal_capture,
                              owner._failure_diagnostics, owner._build_failure)
        sentinel = object()
        owner.gesture_intent = owner._failure_diagnostics = owner._build_failure = sentinel
        owner.proposal_capture = True
        with patch.object(owner, 'workspace', None):
            try:
                local_recovery.capture_text(original)
            except recovery_store.RecoveryError:
                pass
            else:
                raise AssertionError('Invalid owner context captured')
            assert local_recovery.status(original)[0] == 'ERROR'
            assert owner.gesture_intent is sentinel and owner.proposal_capture
            assert owner._failure_diagnostics is sentinel and owner._build_failure is sentinel
        (owner.gesture_intent, owner.proposal_capture,
         owner._failure_diagnostics, owner._build_failure) = saved_owner_values
        before = files(root)
        before_draft = state.sketch_draft_json
        candidate = draft_dispatch.clone(owner.draft)
        candidate.select_tool('Circle')

        def fail_postcheck():
            local_recovery.observe()
            assert files(root) == before, 'Reentrant observation captured unpublished intent'
            raise RuntimeError('Injected postcheck rejection')

        try:
            owner.replace_authoring(candidate, postcheck=fail_postcheck)
        except RuntimeError as exc:
            assert 'Injected postcheck rejection' in str(exc)
        else:
            raise AssertionError('Injected rejection did not run')
        assert state.sketch_draft_json == before_draft
        local_recovery.observe()
        assert files(root) == before, 'Rollback advanced recovery generation'
        owner.discard()
        local_recovery.observe()
        _, discarded = latest()
        assert not discarded.draft_json, 'Discard latest must not resurrect a draft'
        # A successful native Finish must similarly replace the latest draft pair.
        owner = general_session.GeneralSession(context)
        owner.start()
        owner.execute(context, AddLine(PointSeed(0, 0), PointSeed(12, 0)))
        wait(owner)
        local_recovery.observe()
        with patch.object(workspace, 'request_workspace'):
            owner.request_finish(context)
            wait(owner)
        assert owner.finished and not sketch_session.active_session()
        local_recovery.observe()
        saved_entry, finished = latest()
        assert finished.document_json == state.document_json and not finished.draft_json
        assert state.status == 'READY'
        # Recovery I/O failure is visible, but cannot fail or rewrite the model.
        state.document_json += ' '
        canonical = state.document_json
        disk_before = files(root)
        with patch.object(recovery_store.Store, 'write', side_effect=OSError('Injected full disk')):
            local_recovery.observe()
        assert local_recovery.status(original)[0] == 'ERROR'
        assert 'Injected full disk' in local_recovery.status(original)[1]
        assert state.document_json == canonical and state.status == 'READY'
        assert files(root) == disk_before
        local_recovery.observe()
        saved_entry, finished = latest()
        assert finished.document_json == canonical
        # Same-pair polling must detect external removal/corruption instead of trusting memory.
        latest_path = root / f'{saved_entry.scope}.{saved_entry.slot}.recovery.json'
        latest_bytes = latest_path.read_bytes()
        latest_path.unlink()
        local_recovery.observe()
        assert local_recovery.status(original)[0] == 'ERROR'
        assert not latest_path.exists(), 'Observer must not silently repair external removal'
        latest_path.write_bytes(latest_bytes)
        local_recovery.observe()
        assert local_recovery.status(original)[0] == 'SNAPSHOT'
        latest_path.write_bytes(b'{externally corrupt')
        local_recovery.observe()
        assert local_recovery.status(original)[0] == 'ERROR'
        assert latest_path.read_bytes() == b'{externally corrupt'
        latest_path.write_bytes(latest_bytes)
        local_recovery.observe()
        assert local_recovery.status(original)[0] == 'SNAPSHOT'
        prefs.local_recovery_enabled = False
        disk_before = files(root)
        local_recovery.observe()
        assert files(root) == disk_before, 'Opt-out deleted or changed retained snapshots'
        assert local_recovery.status(original)[0] == 'OFF'
        # A previously selected slot may rotate before confirmation. Bind exact record,
        # including generation metadata, even when both generations contain equal data.
        old_fingerprint = local_recovery.record_fingerprint(finished)
        for sequence in (finished.sequence + 1, finished.sequence + 2):
            local_recovery.store().write(recovery_store.encode(
                finished.scope, sequence, finished.document_json, finished.draft_json,
            ))
        rotated = local_recovery.store().read(saved_entry.scope, saved_entry.slot)
        assert rotated.sequence == finished.sequence + 2
        assert local_recovery.record_fingerprint(rotated) != old_fingerprint
        scenes_before = tuple(bpy.data.scenes)
        data_before = [(s.mechanical_cad.document_json, s.mechanical_cad.sketch_draft_json,
                        s.mechanical_cad.document_path) for s in scenes_before]
        disk_before = files(root)
        try:
            local_recovery.restore_as_new(
                context, saved_entry.scope, saved_entry.slot,
                expected_fingerprint=old_fingerprint,
            )
        except recovery_store.RecoveryError as exc:
            assert 'changed on disk' in str(exc)
        else:
            raise AssertionError('Rotated selected snapshot was accepted')
        assert tuple(bpy.data.scenes) == scenes_before and window.scene == original
        assert [(s.mechanical_cad.document_json, s.mechanical_cad.sketch_draft_json,
                 s.mechanical_cad.document_path) for s in scenes_before] == data_before
        assert files(root) == disk_before
        # A direct EXEC has no dialog-local choices/bindings. Its stable RNA
        # fallback is selectable, but never grants a restore capability.
        try:
            result = bpy.ops.mcad.restore_local_recovery('EXEC_DEFAULT', entry='NONE')
        except RuntimeError as exc:
            assert 'Restore dialog first' in str(exc)
        else:
            assert result == {'CANCELLED'}
        assert tuple(bpy.data.scenes) == scenes_before and window.scene == original
        assert files(root) == disk_before
        restored = local_recovery.restore_as_new(
            context, saved_entry.scope, saved_entry.slot,
            expected_fingerprint=local_recovery.record_fingerprint(rotated),
        )
        assert restored != original and window.scene == restored
        assert restored.mechanical_cad.document_json == canonical
        assert not restored.mechanical_cad.document_path
        assert restored.mechanical_cad.status == 'DIRTY'
        assert not restored.objects and not sketch_session.active_session()
        assert state.document_json == canonical and not state.sketch_draft_json
        # Corrupt an explicit test-owned entry: failed Restore cannot mutate any scene/file.
        path = root / f'{saved_entry.scope}.{saved_entry.slot}.recovery.json'
        path.write_bytes(b'{broken')
        disk_before = files(root)
        scenes_before = tuple(bpy.data.scenes)
        try:
            local_recovery.restore_as_new(context, saved_entry.scope, saved_entry.slot)
        except recovery_store.RecoveryError:
            pass
        else:
            raise AssertionError('Corrupt snapshot was accepted')
        assert tuple(bpy.data.scenes) == scenes_before and window.scene == restored
        assert files(root) == disk_before
        assert any(row.error for row in local_recovery.store().entries())
    # .blend data cannot enable recovery; the application-profile preference survives load.
    # This smoke-only .blend is disposable, not the unsaved two-process recovery fixture.
    load_fixture = Path(temporary) / 'preference_isolation.blend'
    bpy.context.scene['local_recovery_enabled'] = True
    bpy.ops.wm.save_as_mainfile(filepath=str(load_fixture))
    prefs.local_recovery_enabled = False
    bpy.ops.wm.open_mainfile(filepath=str(load_fixture))
    assert not prefs.local_recovery_enabled
    assert bpy.app.timers.is_registered(local_recovery.observe)
    prefs.local_recovery_enabled = True
    bpy.ops.wm.open_mainfile(filepath=str(load_fixture))
    assert prefs.local_recovery_enabled
    assert bpy.app.timers.is_registered(local_recovery.observe)
    prefs.local_recovery_enabled = False
unregister()
assert not bpy.app.timers.is_registered(local_recovery.observe)
print('LOCAL_RECOVERY_SMOKE_OK', flush=True)
