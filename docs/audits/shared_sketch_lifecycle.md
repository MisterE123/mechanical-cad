# Shared sketch lifecycle audit receipt

Date: 2026-10-16. Frozen repaired source:
`3951d395e4a00a20ff9adaf92901751b8987ce6a`.

This is a bounded native-headless lifecycle and pure-codec review. It does not
qualify the later general viewport tools, direct dimension editor, or typed Part
display publication.

## Independently repeated evidence

- Full frozen-source pytest: 2,237 passed.
- Shared native Blender 5.2.2 owner suite: 90 checks.
- Unchanged rectangle suspension suite: 208 checks, plus 18 in a separate process
  reopening the saved `.blend`.
- Unchanged viewport rectangle suite: 190 checks.
- Ruff and legacy rectangle snapshot-byte compatibility passed.

Additional independent adversarial probes covered real scene deletion and Undo,
multiple interrupted sessions, external-slot discard, newer valid snapshots,
repeated history callbacks, load quarantine, unstarted owners and full capacity.
No remaining concrete blocker was found within that reviewed scope.

## Findings closed before general editor integration

1. A missing original scene combined with an encoder failure could hide and then
   erase the only pure draft. Pure fallbacks now retain their own immutable
   session identity and visible explanation, independent of history slots.
2. Protecting an old fallback in the history map could suppress a newer draft's
   Undo restoration. Normal history slots, encoded conflicts and pure fallbacks
   now have separate responsibilities.
3. Two encoded conflicts in the same scene could replace one another. Both
   encoded and pure recovery copies now use session IDs; discarding an external
   saved slot does not discard an older interrupted session's copy.
4. Retired owners could read freed window RNA before checking lifetime. The
   lifetime guard now precedes those reads. Rectangle-only operator polls use
   explicit capabilities rather than accessing general-draft rectangle fields.
5. Escaped lone surrogates could be advertised as resumable and then fail at
   checkpoint encoding. Dispatch validates decoded text and raises its public
   snapshot error while preserving the original bytes.

## Bounded retention

A 16-session admission budget covers live/unstarted reservations and held
recovery copies. Full capacity rejects a new owner visibly before accepting its
intent. Existing copies are never silently evicted. Missing-scene encoded data
has an independent backup; its history entry is only an exact original-scene Undo
restoration index. File load quarantines held copies without scene-name rebinding.

Recovery copies are in-memory emergency retention, not durable backup. This
unreleased seam has no general restore/merge interface yet. Encoder-failure
fallbacks are count-bounded; an exact byte bound for a corrupt live object is not
claimed. Saved snapshots continue to obey their codec byte limits.

## Reproduce

Use the qualified standalone Blender 5.2.2 and configured sidecar Python. Set
`MCAD_ROOT` to the frozen source and `MCAD_PYTHON` to the sidecar interpreter.

```
python -m pytest -q tests/unit/test_draft_dispatch.py
blender --background --factory-startup --python-exit-code 1 \
  --python tests/blender_shared_sketch_owner_smoke.py
blender --background --factory-startup --python-exit-code 1 \
  --python tests/blender_draft_suspension_smoke.py
blender --background --factory-startup --python-exit-code 1 \
  --python tests/blender_viewport_sketch_smoke.py
```

Keep outputs in a persistent workspace folder. Temporary executor files are not
an evidence archive and can disappear when the execution environment changes.
