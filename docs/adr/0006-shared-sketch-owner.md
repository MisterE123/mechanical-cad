# ADR 0006: one sketch owner, explicit independent draft codecs

Status: accepted; shared owner implemented, general viewport editor not yet wired.

## Decision

`draft_dispatch.py` selects the strict rectangle-v1, general-v1 command, or general-v2 authoring envelope codec by explicit kind and version. Each codec retains its own internal schema/version rules. Dispatch does not migrate, guess an editor, reinterpret payloads or rewrite exact base bytes. Unknown/corrupt text stays available for explicit Discard. A saved general draft is recognized but Resume reports the unavailable editor until that editor is integrated.

`sketch_session.py` owns the one active registry, original-scene checkpoint compare-and-swap, history tombstones, transient recovery maps and common resource cleanup. `viewport_sketch.py` retains rectangle placement/validation/operators and reexports the common lifecycle functions for existing registration and workspace gates. There is one set of registration callbacks, not one per editor kind.

A session binds its original scene/window/workspace/viewport and exact base. Checkpoints write only its original scene slot. Existing cross-scene navigation notices remain visible; those notices transfer no canonical data, draft slot, geometry, selection or evidence. Slot conflicts preserve both the external saved bytes and a per-session recovery copy carrying its original-scene identity. Later conflicting sessions cannot overwrite an earlier copy. Missing-scene recovery uses runtime identity, never a similar scene name.

Cleanup retires ownership first, calls the editor's token/lease invalidation hook, then attempts every owned resource cleanup independently. An unstarted owner cannot restore another owner's cursor/status. Partial startup uses the same teardown. Saved snapshots contain pure intent, never solver authority or native resources. If encoding itself fails during suspension, the pure draft stays in a separate session-ID-keyed recovery registry with its error; this is not durable backup. It never replaces or disables ordinary history-slot tracking for a later draft in that scene. File load quarantines encoded and pure fallback copies without binding them to any new scene. A missing-scene encoded copy also has an independent session-keyed backup; its history index is only for exact original-scene Undo restoration. The backup is released only after those exact bytes are restored to the original persistent slot.

Recovery admission is capped at 16 sessions across encoded backups, pure fallbacks and live/unstarted owners. Each owner reserves capacity before accepting intent; cleanup releases its reservation, and interruption replaces that reservation with the same session-ID recovery record. Full capacity visibly blocks new owners before they can lose intent. Existing copies are never automatically evicted. Encoding retains the codec's existing byte limits; an encoder-failure fallback is count-bounded, not a promised durable backup or exact byte-size guarantee. The recovery registry remains in-memory and currently has no general restore/merge UI; this narrow gate protects copies while that UI is developed.

## Consequences and scope

- Existing rectangle snapshot bytes and behavior remain the regression baseline.
- General draft history and raw-input state reuse the same lifecycle rather than introducing parallel handlers.
- Snapshot Resume remains explicit and requires exact original base bytes. Reopening never solves or accepts pending text automatically.
- The common editor-detachment hook is a lifecycle seam, not qualification of the isolated inline text editor.
- Shared owner tests do not implement a general viewport tool or typed open-sketch display. Those are separate integration steps.

## Verification

Run the unchanged `tests/blender_draft_suspension_smoke.py` and `tests/blender_viewport_sketch_smoke.py` under qualified native Blender 5.2.2, alongside `tests/blender_shared_sketch_owner_smoke.py` and `tests/unit/test_draft_dispatch.py`. The added native test covers registry exclusivity, general kind/status routing, unavailable-editor Resume, original-scene slot ownership, shared history/save/disable hooks, external-slot conflict, double encoding failure, partial startup and cleanup fault injection. Interactive GUI behavior is still a separate acceptance gate.

## General authoring envelope integration

The general-v2 wrapper now passes through the same owner checkpoint, save, history,
disable and exact-base reopen paths. It does not enable a general viewport editor.
Rebinding Blender RNA callbacks preserves the original canonical JSON bytes and
geometry-report labels: callback setup is not a model edit. Native Blender 5.2.2
coverage lives in `tests/blender_general_authoring_owner_smoke.py`, including
161 lifecycle checks and 37 separate-process reopen checks. Rectangle/general-v1
snapshot bytes remain unchanged.
